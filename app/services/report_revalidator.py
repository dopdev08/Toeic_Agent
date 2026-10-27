"""Offline batch report revalidation service.

Replays historical LLM batch reports through the current Pydantic QuestionEnrichment
schema and deterministic EnrichmentValidator without calling any LLM.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from app.services.enrichment_response_parser import (
    EnrichmentJSONDecodeError,
    EnrichmentValidationError,
    parse_and_validate_enrichment,
)
from app.services.enrichment_validator import EnrichmentValidator


class QuestionInput:
    """Attribute-compatible container for question data used in validation."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id = data.get("id") or data.get("question_id")
        self.test_id = data.get("test_id")
        self.part = data.get("part")
        self.question_no = data.get("question_no")
        self.question_text = data.get("question_text")
        self.option_a = data.get("option_a")
        self.option_b = data.get("option_b")
        self.option_c = data.get("option_c")
        self.option_d = data.get("option_d")
        self.correct_answer = data.get("correct_answer")
        self.explanation = data.get("explanation")


def get_git_revision() -> dict[str, Any]:
    """Extract git commit and branch metadata if available, otherwise return descriptive fallback."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, timeout=2
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL, timeout=2
        ).decode().strip()
        return {"commit": commit, "branch": branch}
    except Exception:
        return {"commit": None, "branch": None}


class ReportRevalidator:
    """Performs offline revalidation of stored batch report raw responses."""

    def __init__(self, validator: EnrichmentValidator | None = None, sanitize: bool = False) -> None:
        self.validator = validator or EnrichmentValidator()
        self.sanitize = sanitize

    def revalidate_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Revalidate a single historical report item using its stored raw_response."""
        if not isinstance(item, dict):
            raise ValueError(f"Report item must be a dictionary, got {type(item).__name__}")
        prev_status = item.get("status")
        if not isinstance(prev_status, str) or not prev_status.strip():
            identifier = item.get("question_no") or item.get("question_id") or item.get("id") or "unknown"
            raise ValueError(f"Report item {identifier} is missing a valid 'status' string (got {prev_status!r})")

        q_id = item.get("id") or item.get("question_id")
        q_no = item.get("question_no")
        raw_response = item.get("raw_response")

        revalidated_item: dict[str, Any] = {
            "question_id": q_id,
            "test_id": item.get("test_id"),
            "part": item.get("part"),
            "question_no": q_no,
            "question_text": item.get("question_text"),
            "option_a": item.get("option_a"),
            "option_b": item.get("option_b"),
            "option_c": item.get("option_c"),
            "option_d": item.get("option_d"),
            "correct_answer": item.get("correct_answer"),
            "previous_status": prev_status,
            "status": "NOT_REVALIDATABLE",
            "status_transition": f"{prev_status} -> NOT_REVALIDATABLE",
            "schema_valid": False,
            "schema_errors": [],
            "quality_valid": False,
            "quality_status": None,
            "quality_error_code": None,
            "quality_errors": [],
            "quality_warnings": [],
            "error_type": None,
            "error": None,
            "raw_response": raw_response,
            "enrichment": None,
        }

        # Case 1: No raw response was captured originally
        if raw_response is None or not isinstance(raw_response, str) or not raw_response.strip():
            if prev_status in ("FAIL_LLM_SERVICE", "FAIL_UNEXPECTED"):
                revalidated_item["status"] = prev_status
                revalidated_item["error_type"] = item.get("error_type")
                revalidated_item["error"] = item.get("error")
                revalidated_item["status_transition"] = f"{prev_status} -> {prev_status}"
            else:
                revalidated_item["status"] = "NOT_REVALIDATABLE"
                revalidated_item["error_type"] = "MissingRawResponse"
                revalidated_item["error"] = "Item does not contain raw_response for offline replay"
                revalidated_item["status_transition"] = f"{prev_status} -> NOT_REVALIDATABLE"
            return revalidated_item

        # Case 2: Attempt JSON parse and Pydantic schema validation
        try:
            enrichment = parse_and_validate_enrichment(raw_response, sanitize=self.sanitize)
            revalidated_item["schema_valid"] = True
            if hasattr(enrichment, "model_dump"):
                revalidated_item["enrichment"] = enrichment.model_dump()
            elif hasattr(enrichment, "dict"):
                revalidated_item["enrichment"] = enrichment.dict()
            else:
                revalidated_item["enrichment"] = enrichment

            # Case 3: Run deterministic quality validation
            question_input = QuestionInput(item)
            val_result = self.validator.validate(question=question_input, enrichment=enrichment)

            revalidated_item["quality_status"] = val_result.status.value
            revalidated_item["quality_errors"] = val_result.errors
            revalidated_item["quality_warnings"] = val_result.warnings
            revalidated_item["quality_error_code"] = val_result.error_code

            if val_result.is_valid:
                revalidated_item["quality_valid"] = True
                revalidated_item["status"] = "PASS_QUALITY_VALIDATED"
            else:
                revalidated_item["quality_valid"] = False
                revalidated_item["status"] = "REJECTED_QUALITY"
                revalidated_item["error_type"] = val_result.error_code or "EnrichmentQualityError"
                revalidated_item["error"] = "; ".join(val_result.errors)

        except EnrichmentJSONDecodeError as exc:
            revalidated_item["schema_valid"] = False
            revalidated_item["quality_valid"] = False
            revalidated_item["status"] = "FAIL_JSON_DECODE"
            revalidated_item["error_type"] = "EnrichmentJSONDecodeError"
            revalidated_item["error"] = exc.message

        except EnrichmentValidationError as exc:
            revalidated_item["schema_valid"] = False
            revalidated_item["quality_valid"] = False
            revalidated_item["status"] = "FAIL_SCHEMA_VALIDATION"
            revalidated_item["error_type"] = "EnrichmentValidationError"
            revalidated_item["error"] = exc.message
            clean_errors = []
            for err in exc.errors:
                err_copy = dict(err)
                if "ctx" in err_copy and isinstance(err_copy["ctx"], dict):
                    err_copy["ctx"] = {
                        k: str(v) if isinstance(v, Exception) else v
                        for k, v in err_copy["ctx"].items()
                    }
                clean_errors.append(err_copy)
            revalidated_item["schema_errors"] = clean_errors

        except Exception as exc:
            revalidated_item["schema_valid"] = False
            revalidated_item["quality_valid"] = False
            revalidated_item["status"] = "FAIL_UNEXPECTED"
            revalidated_item["error_type"] = type(exc).__name__
            revalidated_item["error"] = str(exc)

        revalidated_item["status_transition"] = f"{prev_status} -> {revalidated_item['status']}"
        return revalidated_item

    def revalidate_report_data(
        self,
        report_data: dict[str, Any],
        source_path: str | None = None,
    ) -> dict[str, Any]:
        """Revalidate all items in a report dictionary and compute transitions and warnings."""
        if not isinstance(report_data, dict):
            raise ValueError(f"Report data must be a dictionary, got {type(report_data).__name__}")

        if "results" not in report_data and "items" not in report_data:
            raise ValueError("Report data must contain a 'results' or 'items' list")

        raw_items = report_data.get("results")
        if raw_items is None:
            raw_items = report_data.get("items")
        if not isinstance(raw_items, list):
            raise ValueError(f"Report items/results must be a list, got {type(raw_items).__name__}")

        revalidated_results = []
        transitions: dict[str, int] = {}
        prev_status_counts: dict[str, int] = {}
        recalc_status_counts: dict[str, int] = {}
        warning_counts: dict[str, int] = {}
        total_warnings = 0

        for it in raw_items:
            res = self.revalidate_item(it)
            revalidated_results.append(res)

            prev_st = res["previous_status"]
            new_st = res["status"]
            prev_status_counts[prev_st] = prev_status_counts.get(prev_st, 0) + 1
            recalc_status_counts[new_st] = recalc_status_counts.get(new_st, 0) + 1

            trans = res["status_transition"]
            transitions[trans] = transitions.get(trans, 0) + 1

            for w in res.get("quality_warnings", []):
                total_warnings += 1
                # Extract warning code if formatted like [CODE]
                if w.startswith("[") and "]" in w:
                    w_code = w[1 : w.index("]")]
                else:
                    w_code = "OTHER_WARNING"
                warning_counts[w_code] = warning_counts.get(w_code, 0) + 1

        total_questions = len(revalidated_results)
        if sum(recalc_status_counts.values()) != total_questions:
            raise RuntimeError(
                f"Recalculated status counts sum ({sum(recalc_status_counts.values())}) "
                f"does not match total results ({total_questions})"
            )
        if sum(transitions.values()) != total_questions:
            raise RuntimeError(
                f"Status transitions sum ({sum(transitions.values())}) "
                f"does not match total results ({total_questions})"
            )
        if sum(prev_status_counts.values()) != total_questions:
            raise RuntimeError(
                f"Previous status counts sum ({sum(prev_status_counts.values())}) "
                f"does not match total results ({total_questions})"
            )

        revalidation_ts = datetime.now(timezone.utc).isoformat()
        git_info = get_git_revision()

        # Extract source timestamp from filename or metadata if possible
        source_ts = None
        if source_path:
            p = Path(source_path)
            for part in p.stem.split("_"):
                if len(part) == 14 and part.isdigit():
                    source_ts = part
                    break

        return {
            "revalidation_metadata": {
                "source_report_path": str(source_path) if source_path else None,
                "source_report_timestamp": source_ts,
                "revalidation_timestamp": revalidation_ts,
                "schema_revision": "Task 3.2 aligned schema (extra='forbid', exact A-D distractors, 16 canonical POS/phrase tags)",
                "validator_revision": "Task 3 conservative linguistic quality checks and pedagogical warning lints",
                "git_commit": git_info.get("commit"),
                "git_branch": git_info.get("branch"),
            },
            "summary": {
                "total_questions": len(revalidated_results),
                "previous_status_counts": prev_status_counts,
                "recalculated_status_counts": recalc_status_counts,
                "status_transitions": transitions,
                "total_warnings": total_warnings,
                "warning_counts_by_code": warning_counts,
            },
            "results": revalidated_results,
        }

    def revalidate_file(
        self,
        input_path: str | Path,
        output_dir: str | Path = "reports/revalidation",
    ) -> tuple[Path, dict[str, Any]]:
        """Read historical report file, run offline revalidation, and save result under output_dir."""
        in_p = Path(input_path).resolve()
        if not in_p.exists():
            raise FileNotFoundError(f"Source report file not found: {in_p}")

        with open(in_p, "r", encoding="utf-8") as f:
            data = json.load(f)

        out_data = self.revalidate_report_data(data, source_path=str(in_p))

        out_d = Path(output_dir)
        out_d.mkdir(parents=True, exist_ok=True)

        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_filename = f"revalidated_{in_p.stem}_{now_str}.json"
        out_p = out_d / out_filename

        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)

        return out_p, out_data
