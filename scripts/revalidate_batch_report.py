#!/usr/bin/env python3
"""CLI utility to revalidate historical TOEIC Part 5 batch reports offline.

Reruns stored raw LLM responses through the current strict schema and deterministic
EnrichmentValidator without invoking any LLM or mutating source reports.
"""

import argparse
import json
from pathlib import Path
import sys

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.services.report_revalidator import ReportRevalidator


DEFAULT_HISTORICAL_REPORTS = [
    "reports/part5_batch_qwen2.5_3b_20261012_123315.json",
    "reports/part5_batch_gemini-3.5-flash-lite_20261012_122158.json",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline batch report revalidator for TOEIC Part 5 enrichment."
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="*",
        default=[],
        help="Path(s) to historical report JSON files to revalidate. If omitted, defaults to known historical reports.",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="reports/revalidation",
        help="Directory to store revalidation reports (default: reports/revalidation).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_files = args.input or DEFAULT_HISTORICAL_REPORTS
    revalidator = ReportRevalidator()

    print("================================================================================")
    print("TOEIC Part 5 Batch Report Offline Revalidation")
    print("================================================================================")
    print(f"Output directory: {args.output_dir}\n")

    for file_str in input_files:
        p = Path(file_str)
        if not p.exists():
            print(f"[SKIP] Report file not found: {file_str}")
            continue

        print(f"--- Revalidating: {p.name} ---")
        try:
            out_path, result_data = revalidator.revalidate_file(p, output_dir=args.output_dir)
            summary = result_data["summary"]
            print(f"  Saved revalidation report to: {out_path}")
            print(f"  Total questions processed: {summary['total_questions']}")
            print("  Status transitions:")
            for trans, count in summary["status_transitions"].items():
                print(f"    * {trans}: {count}")
            print("  Recalculated status distribution:")
            for st, count in summary["recalculated_status_counts"].items():
                print(f"    * {st}: {count}")
            print(f"  Total quality warnings flagged: {summary['total_warnings']}")
            if summary["warning_counts_by_code"]:
                for code, count in summary["warning_counts_by_code"].items():
                    print(f"    * {code}: {count}")
            print()
        except Exception as exc:
            print(f"  [ERROR] Failed to revalidate {p.name}: {exc}\n")

    print("Revalidation complete.")


if __name__ == "__main__":
    main()
