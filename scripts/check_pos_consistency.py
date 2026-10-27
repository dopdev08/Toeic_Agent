#!/usr/bin/env python3
"""CLI for Offline spaCy Part-of-Speech Consistency Checker for TOEIC Part 5 Enrichment.

Usage:
  python scripts/check_pos_consistency.py --input-report reports/revalidation/revalidated_part5_batch_qwen2.5_3b_20261012_123315_20261012_163717.json
  python scripts/check_pos_consistency.py --input-report reports/revalidation/revalidated_part5_batch_gemini-3.5-flash-lite_20261012_122158_20261012_163717.json

Produces:
  1. Timestamped diagnostic JSON report under reports/pos_consistency/
  2. Timestamped human adjudication CSV under reports/pos_consistency/
"""

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Safe stdout reconfiguration for Windows terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.services.pos_consistency_checker import PosConsistencyChecker


DEFAULT_INPUT_REPORTS = [
    "reports/revalidation/revalidated_part5_batch_qwen2.5_3b_20261012_123315_20261012_163717.json",
    "reports/revalidation/revalidated_part5_batch_gemini-3.5-flash-lite_20261012_122158_20261012_163717.json",
]

CSV_FIELDNAMES = [
    "source_report",
    "question_id",
    "question_no",
    "vocabulary_word",
    "expected_pos",
    "spacy_pos",
    "spacy_tag",
    "spacy_lemma",
    "spacy_dep",
    "match_mode",
    "checker_outcome",
    "mapping_rationale",
    "completed_sentence_sha256",
    "human_verdict",
    "reviewer_notes",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline spaCy Part-of-Speech Consistency Checker for TOEIC Part 5 Enrichment"
    )
    parser.add_argument(
        "--input-report",
        "-i",
        nargs="*",
        default=[],
        help="Path(s) to benchmark / revalidation JSON reports or gold set candidate. If omitted, defaults to latest Task 3.2 revalidation artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="reports/pos_consistency",
        help="Directory to store diagnostics and adjudication CSVs (default: reports/pos_consistency).",
    )
    parser.add_argument(
        "--spacy-model",
        default="en_core_web_sm",
        help="Installed spaCy model package to load (default: en_core_web_sm). Does NOT download models.",
    )
    return parser.parse_args()


def calculate_file_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    args = parse_args()
    input_files = args.input_report or DEFAULT_INPUT_REPORTS

    print("================================================================================")
    print("TOEIC Part 5 Offline spaCy Part-of-Speech Consistency Checker")
    print("================================================================================")
    print(f"Model requested: {args.spacy_model}")
    print(f"Output directory: {args.output_dir}\n")

    # Initialize checker (will raise actionable error if spaCy or model missing)
    try:
        checker = PosConsistencyChecker(model_name=args.spacy_model)
    except Exception as exc:
        print(f"[ERROR] Failed to initialize spaCy POS consistency checker:\n  {exc}\n", file=sys.stderr)
        print("Installation guidance:", file=sys.stderr)
        print("  pip install -r requirements-nlp.txt", file=sys.stderr)
        print("  python -m spacy validate", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    now_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for file_str in input_files:
        in_path = Path(file_str).resolve()
        if not in_path.exists():
            print(f"[SKIP] Source file not found: {file_str}")
            continue

        print(f"--- Processing: {in_path.name} ---")
        sha_before = calculate_file_sha256(in_path)

        try:
            with open(in_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)
        except Exception as exc:
            print(f"  [ERROR] Failed to load JSON from {in_path.name}: {exc}\n")
            exit_code = 1
            continue

        report_result = checker.check_report_data(report_data, source_path=str(in_path))
        report_result["metadata"]["source_report_sha256"] = sha_before

        summary = report_result["summary"]
        outcomes = summary["outcome_counts"]

        # 1. Write timestamped diagnostic JSON
        out_json_path = out_dir / f"pos_consistency_{in_path.stem}_{now_ts}.json"
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(report_result, f, indent=2, ensure_ascii=False)

        # 2. Write timestamped human adjudication CSV
        out_csv_path = out_dir / f"pos_adjudication_{in_path.stem}_{now_ts}.csv"
        adjudication_rows = checker.generate_human_adjudication_rows(report_result["diagnostics"])

        with open(out_csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            for r in adjudication_rows:
                writer.writerow(r)

        # Verify source file immutability
        sha_after = calculate_file_sha256(in_path)
        assert sha_before == sha_after, f"Source file mutated during processing: {in_path}"

        print(f"  Saved JSON diagnostics: {out_json_path}")
        print(f"  Saved Adjudication CSV: {out_csv_path}")
        print(f"  Questions processed: {summary['total_questions_processed']}")
        print(f"  Vocabulary items: {summary['total_vocabulary_items']} (aligned & checked: {summary['total_items_aligned_and_checked']})")
        print(f"  POS mismatch warnings: {summary['total_pos_mismatch_warnings']}")
        print("  Outcome distribution:")
        for code, cnt in sorted(outcomes.items()):
            print(f"    * {code}: {cnt}")
        print()

    print("POS consistency check complete.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
