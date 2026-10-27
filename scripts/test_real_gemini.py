#!/usr/bin/env python3
"""Manual smoke-test integration script for verifying the TOEIC Agent enrichment pipeline against Google Gemini Cloud LLM.

Usage:
    python scripts/test_real_gemini.py
    python scripts/test_real_gemini.py --question-id 101
    python scripts/test_real_gemini.py --model gemini-3.5-flash-lite
    python scripts/test_real_gemini.py --question-id 1 --model gemini-3.5-flash-lite

Constraints:
    - Read-only with respect to application data (no DB persistence, no commits).
    - Reuses existing GeminiClient, EnrichmentService, and parse_and_validate_enrichment.
    - Captures raw LLM response for diagnostic inspection.
    - Exits with 0 on SUCCESS, non-zero on any FAILURE.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

# Ensure project root is in python path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Configure stdout and stderr for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.db.database import SessionLocal
from app.models.question import Question
from app.services.enrichment_response_parser import (
    EnrichmentJSONDecodeError,
    EnrichmentValidationError,
)
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_validator import EnrichmentValidator
from app.services.gemini_client import (
    GeminiAPIKeyError,
    GeminiClient,
)
from app.services.llm_client import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMTimeoutError,
)


def load_question_from_db(question_id: int) -> Question | None:
    session = SessionLocal()
    try:
        return session.get(Question, question_id)
    finally:
        session.close()


def print_section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify TOEIC enrichment pipeline with Google Gemini Cloud API."
    )
    parser.add_argument(
        "--question-id",
        type=int,
        default=None,
        help="Target Question ID in database (default: sample question)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        help="Gemini model name (default: gemini-3.5-flash-lite)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("GEMINI_TIMEOUT", "60.0")),
        help="Gemini HTTP timeout in seconds (default: 60.0s)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print_section("SECTION 1: TARGET QUESTION ACQUISITION")

    question = None
    if args.question_id is not None:
        question = load_question_from_db(args.question_id)
        if question:
            print(f"Loaded question ID {args.question_id} from database.")
        else:
            print(f"[WARN] Question ID {args.question_id} not found in database. Falling back to built-in sample.")

    if question is None:
        class DummyQuestion:
            id = 101
            test_id = "ETS_2026_TEST_01"
            part = 5
            question_no = 101
            question_text = "Customer satisfaction is ______ important to the management of Grand Hotel."
            option_a = "extreme"
            option_b = "extremely"
            option_c = "extremist"
            option_d = "extremity"
            correct_answer = "B"
            explanation = "Phó từ 'extremely' đứng trước tính từ 'important' để bổ nghĩa."

        question = DummyQuestion()
        print("Using built-in sample Part 5 question.")

    print(f"Question text : {question.question_text}")
    print(f"Option A      : {question.option_a}")
    print(f"Option B      : {question.option_b}")
    print(f"Option C      : {question.option_c}")
    print(f"Option D      : {question.option_d}")
    print(f"Correct answer: {question.correct_answer}")

    print_section("SECTION 2: GEMINI CLIENT INITIALIZATION")
    try:
        client = GeminiClient(
            model=args.model,
            timeout=args.timeout,
        )
        print(f"Gemini Model  : {client.model}")
        print(f"Gemini Timeout: {client.timeout}s")
        print("Gemini API Key: [Configured]")
    except GeminiAPIKeyError as exc:
        print(f"[ERROR] Gemini Authentication Error: {exc}")
        return 1

    service = EnrichmentService(llm_service=client)
    validator = EnrichmentValidator()

    print_section("SECTION 3: AI ENRICHMENT EXECUTION")
    print("Sending prompt to Google Gemini Cloud API...")

    try:
        enrichment = service.enrich_question(question)
        print("\nRaw LLM JSON response successfully parsed and validated against schema!")
        print(json.dumps(enrichment.model_dump(), indent=2, ensure_ascii=False))

        print_section("SECTION 4: QUALITY VALIDATION GATES")
        val_result = validator.validate(question, enrichment)
        print(f"Quality Status : {val_result.status.value}")
        print(f"Quality Valid  : {val_result.is_valid}")
        if val_result.warnings:
            print(f"Warnings       : {val_result.warnings}")
        if val_result.errors:
            print(f"Errors         : {val_result.errors}")

        if val_result.is_valid:
            print("\n[SUCCESS] Google Gemini enrichment pipeline completed successfully!")
            return 0
        else:
            print(f"\n[FAILURE] Quality validation rejected enrichment: {val_result.error_code}")
            return 2

    except LLMAuthenticationError as exc:
        print(f"[ERROR] LLM Authentication Error: {exc}")
        return 1
    except LLMConnectionError as exc:
        print(f"[ERROR] LLM Connection Error: {exc}")
        return 1
    except LLMTimeoutError as exc:
        print(f"[ERROR] LLM Timeout Error: {exc}")
        return 1
    except LLMProviderError as exc:
        print(f"[ERROR] LLM Provider Error: {exc}")
        return 1
    except (EnrichmentJSONDecodeError, EnrichmentValidationError) as exc:
        print(f"[ERROR] Schema Parsing / Validation Error: {exc}")
        return 1
    except Exception as exc:
        print(f"[ERROR] Unexpected Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
