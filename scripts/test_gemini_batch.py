import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.db.database import DATABASE_URL, SessionLocal
from app.models.question import Question
from app.services.enrichment_response_parser import (
    EnrichmentJSONDecodeError,
    EnrichmentValidationError,
)
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_validator import EnrichmentValidator

try:
    from google import genai
    from google.genai import errors
except ImportError:
    genai = None  # type: ignore
    errors = None  # type: ignore


class GeminiAPIKeyError(Exception):
    """Raised when GEMINI_API_KEY environment variable is not provided."""
    pass


class QuestionInput:
    """Attribute-compatible container for source question data used in enrichment and validation."""

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


CSV_FIELDNAMES = [
    "question_id",
    "test_id",
    "part",
    "question_no",
    "status",
    "schema_valid",
    "quality_valid",
    "quality_status",
    "quality_error_code",
    "error_type",
    "error",
    "elapsed_seconds",
    "prompt_tokens",
    "candidates_tokens",
    "total_tokens",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_answer",
    "enrichment",
    "raw_response",
]


def sanitize_secret(text: str | None, secret: str | None = None) -> str:
    """Mask sensitive API keys or credential patterns from logs and reports."""
    if not text:
        return ""
    masked = str(text)
    if secret:
        s = secret.strip().strip('"').strip("'")
        if s:
            masked = masked.replace(s, "[REDACTED_API_KEY]")
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        env_k = env_key.strip().strip('"').strip("'")
        if env_k:
            masked = masked.replace(env_k, "[REDACTED_API_KEY]")
    # Mask common Google API key patterns (e.g. AIzaSy...)
    masked = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", masked)
    masked = re.sub(
        r"((?:api[_-]?)?key=)[^&\s'\"]+",
        r"\1[REDACTED_API_KEY]",
        masked,
        flags=re.IGNORECASE,
    )
    return masked


def parse_question_nos(raw: str | None) -> list[int]:
    """Parse comma-separated question numbers (e.g. '120' or '102,104,106')."""
    if not raw or not raw.strip():
        return []
    result = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        if not p.isdigit():
            raise ValueError(f"Invalid question number: '{p}'. Must be positive integers.")
        result.append(int(p))
    return result


def load_env_file() -> None:
    """Optionally load GEMINI_API_KEY from .env file if present in project root."""
    env_file = project_root / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY=") and not os.getenv("GEMINI_API_KEY"):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["GEMINI_API_KEY"] = val
        except Exception:
            pass


def validate_request_interval(raw: Any) -> float:
    """Validate and convert request interval string to non-negative float."""
    try:
        val = float(raw)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(
            f"Invalid request interval: '{raw}'. Must be a valid number."
        )
    if val < 0:
        raise argparse.ArgumentTypeError(
            f"Request interval must be non-negative, got {val}."
        )
    return val


class RequestPacer:
    """Enforces a minimum time interval between consecutive request starts using time.monotonic()."""

    def __init__(self, interval: float = 4.5) -> None:
        if interval < 0:
            raise ValueError(f"Request interval must be non-negative, got {interval}")
        self.interval = float(interval)
        self.last_request_start: float | None = None
        self.total_sleep_time: float = 0.0

    def wait(self) -> float:
        """Wait if needed to ensure self.interval seconds since previous request start.

        Returns the number of seconds slept (0.0 if no sleep occurred).
        """
        if self.interval <= 0:
            self.last_request_start = time.monotonic()
            return 0.0

        now = time.monotonic()
        slept = 0.0
        if self.last_request_start is not None:
            elapsed = max(0.0, now - self.last_request_start)
            remaining = self.interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
                slept = remaining
                self.total_sleep_time += slept

        self.last_request_start = time.monotonic()
        return slept


class GeminiClient:
    """Client for generating responses using official google-genai SDK conforming to LLMService protocol."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-3.5-flash-lite",
        timeout: float = 180.0,
        request_interval: float = 4.5,
        client: Any = None,
        pacer: RequestPacer | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key or not self.api_key.strip():
            raise GeminiAPIKeyError(
                "GEMINI_API_KEY environment variable is not set. "
                "Please set GEMINI_API_KEY in your environment, pass --api-key, or place GEMINI_API_KEY in a .env file."
            )
        self.model = model
        self.timeout = timeout
        if request_interval < 0:
            raise ValueError(f"Request interval must be non-negative, got {request_interval}")
        self.request_interval = float(request_interval)
        self.pacer = pacer or RequestPacer(interval=self.request_interval)
        self.last_raw_response: str | None = None
        self.last_usage: dict[str, int | None] = {}

        if client is not None:
            self.client = client
        else:
            if genai is None:
                raise ImportError(
                    "The 'google-genai' package is required. Install it using 'pip install google-genai'."
                )
            self.client = genai.Client(api_key=self.api_key.strip())

    def generate(self, prompt: str) -> str:
        """Generate response text for the provided prompt and record usage statistics."""
        self.last_raw_response = None
        self.last_usage = {}

        if self.pacer is not None:
            slept = self.pacer.wait()
            if slept > 0:
                print(f"  Pacing: waited {slept:.2f}s (target interval: {self.pacer.interval}s)")

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
        except Exception as exc:
            # Sanitize exception attributes in-place to prevent leaking credentials
            # without re-instantiating exc via type(exc)(sanitized_msg), which fails
            # on SDK exception classes that require multiple __init__ positional arguments
            # (such as google.genai.errors.APIError requiring code and response_json).
            if hasattr(exc, "args") and exc.args:
                try:
                    exc.args = tuple(
                        sanitize_secret(str(arg), self.api_key) if isinstance(arg, str) else arg
                        for arg in exc.args
                    )
                except Exception:
                    pass
            if hasattr(exc, "message") and isinstance(exc.message, str):
                try:
                    exc.message = sanitize_secret(exc.message, self.api_key)
                except Exception:
                    pass
            raise

        raw_text = getattr(response, "text", "") or ""
        self.last_raw_response = raw_text

        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta is not None:
            self.last_usage = {
                "prompt_tokens": getattr(usage_meta, "prompt_token_count", None),
                "candidates_tokens": getattr(usage_meta, "candidates_token_count", None),
                "total_tokens": getattr(usage_meta, "total_token_count", None),
            }
        else:
            self.last_usage = {}

        return raw_text


def process_benchmark_item(
    source: dict[str, Any],
    service: EnrichmentService,
    validator: EnrichmentValidator,
    gemini_client: GeminiClient | Any,
) -> dict[str, Any]:
    """Execute inference, schema validation, and content quality validation in-memory for a single question."""
    qid = source.get("id") or source.get("question_id")
    qno = source.get("question_no")

    start = time.perf_counter()

    result: dict[str, Any] = {
        "question_id": qid,
        "test_id": source.get("test_id"),
        "part": source.get("part"),
        "question_no": qno,
        "question_text": source.get("question_text"),
        "option_a": source.get("option_a"),
        "option_b": source.get("option_b"),
        "option_c": source.get("option_c"),
        "option_d": source.get("option_d"),
        "correct_answer": source.get("correct_answer"),
        "status": "FAIL_UNEXPECTED",
        "llm_received": False,
        "schema_valid": False,
        "quality_valid": False,
        "quality_status": None,
        "quality_error_code": None,
        "quality_errors": [],
        "quality_warnings": [],
        "error_type": None,
        "error": None,
        "elapsed_seconds": None,
        "token_usage": {},
        "raw_response": None,
        "enrichment": None,
    }

    question_input = QuestionInput(source)

    try:
        enrichment = service.enrich_question(question_input)

        raw_response = getattr(gemini_client, "last_raw_response", None)
        result["raw_response"] = raw_response
        result["llm_received"] = raw_response is not None
        result["token_usage"] = getattr(gemini_client, "last_usage", {}) or {}

        if hasattr(enrichment, "model_dump"):
            parsed = enrichment.model_dump()
        elif hasattr(enrichment, "dict"):
            parsed = enrichment.dict()
        else:
            parsed = enrichment

        result["enrichment"] = parsed
        result["schema_valid"] = True

        validation_result = validator.validate(
            question=question_input, enrichment=enrichment
        )

        result["quality_status"] = validation_result.status.value
        result["quality_errors"] = validation_result.errors
        result["quality_warnings"] = validation_result.warnings
        result["quality_error_code"] = validation_result.error_code

        if validation_result.is_valid:
            result["quality_valid"] = True
            result["status"] = "PASS_QUALITY_VALIDATED"
            print("  PASS_QUALITY_VALIDATED - Schema valid & quality checks passed")
        else:
            result["quality_valid"] = False
            result["status"] = "REJECTED_QUALITY"
            result["error_type"] = (
                validation_result.error_code or "EnrichmentQualityError"
            )
            result["error"] = "; ".join(validation_result.errors)
            print(
                f"  REJECTED_QUALITY - [{validation_result.error_code}]: {result['error']}"
            )

    except EnrichmentJSONDecodeError as exc:
        raw_response = getattr(gemini_client, "last_raw_response", None) or getattr(
            exc, "raw_response", None
        )
        result["raw_response"] = raw_response
        result["llm_received"] = raw_response is not None
        result["token_usage"] = getattr(gemini_client, "last_usage", {}) or {}
        result["schema_valid"] = False
        result["quality_valid"] = False
        result["status"] = "FAIL_JSON_DECODE"
        result["error_type"] = "EnrichmentJSONDecodeError"
        result["error"] = sanitize_secret(exc.message, getattr(gemini_client, "api_key", None))
        print(f"  FAIL_JSON_DECODE - {result['error']}")

    except EnrichmentValidationError as exc:
        raw_response = getattr(gemini_client, "last_raw_response", None) or getattr(
            exc, "raw_response", None
        )
        result["raw_response"] = raw_response
        result["llm_received"] = raw_response is not None
        result["token_usage"] = getattr(gemini_client, "last_usage", {}) or {}
        result["schema_valid"] = False
        result["quality_valid"] = False
        result["status"] = "FAIL_SCHEMA_VALIDATION"
        result["error_type"] = "EnrichmentValidationError"
        result["error"] = sanitize_secret(exc.message, getattr(gemini_client, "api_key", None))
        print(f"  FAIL_SCHEMA_VALIDATION - {result['error']}")

    except Exception as exc:
        raw_response = getattr(gemini_client, "last_raw_response", None)
        result["raw_response"] = raw_response
        result["llm_received"] = raw_response is not None
        result["token_usage"] = getattr(gemini_client, "last_usage", {}) or {}
        result["schema_valid"] = False
        result["quality_valid"] = False

        err_name = type(exc).__name__
        err_msg = sanitize_secret(str(exc), getattr(gemini_client, "api_key", None))

        # Check if it's an API / connection / rate-limit / timeout error
        is_api_error = (
            (errors is not None and isinstance(exc, (errors.APIError, errors.ClientError, errors.ServerError)))
            or "APIError" in err_name
            or "ClientError" in err_name
            or "ServerError" in err_name
            or "Timeout" in err_name
            or "Connection" in err_name
            or "RateLimit" in err_name
            or "ResourceExhausted" in err_name
            or "HTTP" in err_name
            or "Network" in err_name
            or "429" in err_msg
            or "rate limit" in err_msg.lower()
            or "quota" in err_msg.lower()
        )

        if is_api_error:
            result["status"] = "FAIL_LLM_SERVICE"
            result["error_type"] = err_name
            result["error"] = err_msg
            print(f"  FAIL_LLM_SERVICE - {err_name}: {err_msg}")
        else:
            result["status"] = "FAIL_UNEXPECTED"
            result["error_type"] = err_name
            result["error"] = err_msg
            print(f"  FAIL_UNEXPECTED - {err_name}: {err_msg}")

    result["elapsed_seconds"] = round(time.perf_counter() - start, 2)
    return result


def write_benchmark_reports(
    results: list[dict[str, Any]],
    model: str,
    total_elapsed: float,
    report_dir: Path | None = None,
    database_url: str = DATABASE_URL,
    request_interval: float = 4.5,
) -> tuple[Path, Path]:
    """Write benchmark outcome reports to JSON and CSV with UTF-8 BOM encoding."""
    if report_dir is None:
        report_dir = project_root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_model = model.replace(":", "_").replace("/", "_")
    stem = f"part5_batch_{sanitized_model}_{timestamp}"

    json_path = report_dir / f"{stem}.json"
    csv_path = report_dir / f"{stem}.csv"

    total = len(results)
    quality_passed = sum(r["status"] == "PASS_QUALITY_VALIDATED" for r in results)
    quality_rejected = sum(r["status"] == "REJECTED_QUALITY" for r in results)
    schema_failed = sum(r["status"] == "FAIL_SCHEMA_VALIDATION" for r in results)
    json_decode_failed = sum(r["status"] == "FAIL_JSON_DECODE" for r in results)
    llm_failed = sum(r["status"] == "FAIL_LLM_SERVICE" for r in results)
    unexpected_failed = sum(r["status"] == "FAIL_UNEXPECTED" for r in results)
    total_failed = total - quality_passed

    total_prompt_tokens = sum(
        (r.get("token_usage") or {}).get("prompt_tokens") or 0 for r in results
    )
    total_candidates_tokens = sum(
        (r.get("token_usage") or {}).get("candidates_tokens") or 0 for r in results
    )
    total_tokens = sum(
        (r.get("token_usage") or {}).get("total_tokens") or 0 for r in results
    )

    safe_interval = 4.5
    if isinstance(request_interval, (int, float)):
        safe_interval = float(request_interval)

    report = {
        "provider": "gemini",
        "model": model,
        "database_url": database_url,
        "part_filter": 5,
        "read_only": True,
        "request_interval": safe_interval,
        "total_questions": total,
        "quality_passed": quality_passed,
        "quality_rejected": quality_rejected,
        "schema_failed": schema_failed,
        "json_decode_failed": json_decode_failed,
        "llm_failed": llm_failed,
        "unexpected_failed": unexpected_failed,
        "passed": quality_passed,
        "failed": total_failed,
        "elapsed_seconds": total_elapsed,
        "average_seconds_per_question": (
            round(total_elapsed / total, 2) if total else 0.0
        ),
        "total_prompt_tokens": total_prompt_tokens,
        "total_candidates_tokens": total_candidates_tokens,
        "total_tokens": total_tokens,
        "status_semantics": {
            "PASS_QUALITY_VALIDATED": "Passed JSON parsing, Pydantic schema validation, and deterministic EnrichmentValidator quality checks.",
            "REJECTED_QUALITY": "Passed JSON decode and Pydantic schema validation, but rejected or flagged as suspicious by EnrichmentValidator.",
            "FAIL_SCHEMA_VALIDATION": "Decoded valid JSON, but failed Pydantic QuestionEnrichment validation.",
            "FAIL_JSON_DECODE": "Failed to decode LLM response as valid JSON.",
            "FAIL_LLM_SERVICE": "LLM connection, timeout, or provider error.",
            "FAIL_UNEXPECTED": "Unexpected runtime exception.",
        },
        "results": results,
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for result in results:
            usage = result.get("token_usage") or {}
            row = {
                "question_id": result.get("question_id"),
                "test_id": result.get("test_id"),
                "part": result.get("part"),
                "question_no": result.get("question_no"),
                "status": result.get("status"),
                "schema_valid": result.get("schema_valid"),
                "quality_valid": result.get("quality_valid"),
                "quality_status": result.get("quality_status"),
                "quality_error_code": result.get("quality_error_code"),
                "error_type": result.get("error_type"),
                "error": result.get("error"),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "candidates_tokens": usage.get("candidates_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "question_text": result.get("question_text"),
                "option_a": result.get("option_a"),
                "option_b": result.get("option_b"),
                "option_c": result.get("option_c"),
                "option_d": result.get("option_d"),
                "correct_answer": result.get("correct_answer"),
                "enrichment": (
                    json.dumps(result.get("enrichment"), ensure_ascii=False)
                    if result.get("enrichment") is not None
                    else None
                ),
                "raw_response": result.get("raw_response"),
            }
            writer.writerow(row)

    return json_path, csv_path


def run_batch(
    source_questions: list[dict[str, Any]],
    service: EnrichmentService,
    validator: EnrichmentValidator,
    gemini_client: GeminiClient | Any,
    model: str = "gemini-3.5-flash-lite",
    report_dir: Path | None = None,
    database_url: str = DATABASE_URL,
    request_interval: float | None = None,
) -> tuple[list[dict[str, Any]], Path, Path]:
    """Execute in-memory batch processing across question dictionaries without writing to the database."""
    total = len(source_questions)
    results = []
    batch_start = time.perf_counter()

    for index, source in enumerate(source_questions, start=1):
        qid = source.get("id") or source.get("question_id")
        qno = source.get("question_no")
        print(f"\n[{index}/{total}] ID={qid}, Question No={qno}")

        item_result = process_benchmark_item(
            source=source,
            service=service,
            validator=validator,
            gemini_client=gemini_client,
        )
        results.append(item_result)
        print(f"  Time: {item_result['elapsed_seconds']}s")

    total_elapsed = round(time.perf_counter() - batch_start, 2)
    eff_interval = 4.5
    if request_interval is not None and isinstance(request_interval, (int, float)):
        eff_interval = float(request_interval)
    elif hasattr(gemini_client, "request_interval"):
        val = getattr(gemini_client, "request_interval")
        if isinstance(val, (int, float)):
            eff_interval = float(val)
    json_path, csv_path = write_benchmark_reports(
        results=results,
        model=model,
        total_elapsed=total_elapsed,
        report_dir=report_dir,
        database_url=database_url,
        request_interval=eff_interval,
    )

    quality_passed = sum(r["status"] == "PASS_QUALITY_VALIDATED" for r in results)
    quality_rejected = sum(r["status"] == "REJECTED_QUALITY" for r in results)
    schema_failed = sum(r["status"] == "FAIL_SCHEMA_VALIDATION" for r in results)
    json_decode_failed = sum(r["status"] == "FAIL_JSON_DECODE" for r in results)
    llm_failed = sum(r["status"] == "FAIL_LLM_SERVICE" for r in results)
    unexpected_failed = sum(r["status"] == "FAIL_UNEXPECTED" for r in results)

    print("\n" + "=" * 72)
    print("GEMINI BATCH TEST SUMMARY")
    print("=" * 72)
    print(f"Provider                : Gemini")
    print(f"Model                   : {model}")
    print(f"Request Interval        : {eff_interval}s")
    print(f"Total Questions         : {total}")
    print(f"PASS (Quality Validated): {quality_passed}")
    print(f"REJECTED (Quality Check): {quality_rejected}")
    print(f"FAIL (Schema Validation): {schema_failed}")
    print(f"FAIL (JSON Decode Error): {json_decode_failed}")
    print(f"FAIL (LLM / Network)    : {llm_failed}")
    print(f"FAIL (Unexpected)       : {unexpected_failed}")
    print(f"Elapsed                 : {total_elapsed}s")
    print(
        f"Average                 : {total_elapsed / total:.2f}s/question"
        if total
        else "N/A"
    )
    print(f"JSON report             : {json_path}")
    print(f"CSV report              : {csv_path}")

    return results, json_path, csv_path


def main() -> int:
    load_env_file()

    parser = argparse.ArgumentParser(
        description="Batch test Part 5 questions using Gemini cloud model."
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Gemini API Key (optional, defaults to GEMINI_API_KEY environment variable or .env file)",
    )
    parser.add_argument(
        "--model",
        default="gemini-3.5-flash-lite",
        help="Gemini text model ID (default: gemini-3.5-flash-lite)",
    )
    parser.add_argument(
        "--question-nos",
        type=str,
        default=None,
        help="Comma-separated question numbers to test (e.g. '120' or '102,104,106')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Test only the first N questions; 0 means all matching questions.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Per-request timeout in seconds (default: 180s)",
    )
    parser.add_argument(
        "--request-interval",
        type=validate_request_interval,
        default=4.5,
        help="Minimum interval in seconds between consecutive request starts (default: 4.5s)",
    )
    args = parser.parse_args()

    # Fast validation of API key before querying questions
    try:
        gemini_client = GeminiClient(
            api_key=args.api_key,
            model=args.model,
            timeout=args.timeout,
            request_interval=args.request_interval,
        )
    except GeminiAPIKeyError as err:
        print(f"\nError: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"\nFailed to initialize Gemini client: {err}", file=sys.stderr)
        return 1

    try:
        selected_qnos = parse_question_nos(args.question_nos)
    except ValueError as err:
        print(f"\nError: {err}", file=sys.stderr)
        return 1

    print("=" * 72)
    print("TOEIC PART 5 - GEMINI BATCH ENRICHMENT TEST")
    print("=" * 72)
    print(f"Database : {DATABASE_URL}")
    print(f"Provider : Gemini")
    print(f"Model    : {args.model}")
    print(f"Interval : {args.request_interval}s minimum between requests")
    print(f"Timeout  : {args.timeout}s")
    if selected_qnos:
        print(f"Filter   : question_no in {selected_qnos}")
    else:
        print(f"Filter   : Part 5 (all)")
    print("Mode     : READ-ONLY; no enrichment is saved to the database.")

    # Load source questions and close the session immediately before calling the LLM.
    session = SessionLocal()
    try:
        query = (
            session.query(Question)
            .filter(Question.part == 5)
            .order_by(Question.test_id, Question.question_no, Question.id)
        )
        if selected_qnos:
            query = query.filter(Question.question_no.in_(selected_qnos))
        if args.limit > 0:
            query = query.limit(args.limit)

        questions = query.all()

        source_questions = []
        for q in questions:
            source_questions.append({
                "id": q.id,
                "test_id": q.test_id,
                "part": q.part,
                "question_no": q.question_no,
                "question_text": q.question_text,
                "option_a": q.option_a,
                "option_b": q.option_b,
                "option_c": q.option_c,
                "option_d": q.option_d,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
            })
    finally:
        session.close()

    total = len(source_questions)
    print(f"\nQuestions selected: {total}")

    if total == 0:
        print("No matching Part 5 questions found. Nothing to test.")
        return 1

    service = EnrichmentService(llm_service=gemini_client)
    validator = EnrichmentValidator()

    results, _, _ = run_batch(
        source_questions=source_questions,
        service=service,
        validator=validator,
        gemini_client=gemini_client,
        model=args.model,
        request_interval=args.request_interval,
    )

    failed = sum(r["status"] != "PASS_QUALITY_VALIDATED" for r in results)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
