import json
from pathlib import Path
import pytest

from app.services.report_revalidator import ReportRevalidator


@pytest.fixture
def sample_question_payload():
    return {
        "question_id": 119,
        "test_id": "ETS2026",
        "part": 5,
        "question_no": 119,
        "question_text": "The newspaper article describes ways job seekers can _____ for having little workplace experience.",
        "option_a": "reply",
        "option_b": "capture",
        "option_c": "compensate",
        "option_d": "accumulate",
        "correct_answer": "C",
    }


def test_revalidate_q119_raw_with_extra_key_e_fails_schema(sample_question_payload):
    """Q119 raw response containing extra key 'E' in distractor_analysis must become FAIL_SCHEMA_VALIDATION."""
    raw_response_with_extra_e = json.dumps({
        "grammar_topic": "verb tense",
        "sentence_structure": "SVOO (Subject-Verb-Object-Object)",
        "pattern": "V to compensate for X",
        "vocabulary": [
            {"word": "compensate", "meaning": "bồi thường, đền bù", "part_of_speech": "verb"}
        ],
        "explanation": "Động từ 'compensate' đi với giới từ 'for'.",
        "distractor_analysis": {
            "A": "reply không phù hợp",
            "B": "capture không phù hợp",
            "C": "compensate phù hợp",
            "D": "accumulate không phù hợp",
            "E": "lựa chọn thừa không hợp lệ"
        },
        "difficulty": "medium"
    })

    item = dict(sample_question_payload, status="PASS_QUALITY_VALIDATED", raw_response=raw_response_with_extra_e)
    revalidator = ReportRevalidator()
    reval = revalidator.revalidate_item(item)

    assert reval["previous_status"] == "PASS_QUALITY_VALIDATED"
    assert reval["status"] == "FAIL_SCHEMA_VALIDATION"
    assert reval["schema_valid"] is False
    assert reval["quality_valid"] is False
    assert reval["error_type"] == "EnrichmentValidationError"
    assert reval["status_transition"] == "PASS_QUALITY_VALIDATED -> FAIL_SCHEMA_VALIDATION"
    assert reval["raw_response"] == raw_response_with_extra_e


def test_revalidate_q127_raw_with_extra_key_explanation_fails_schema():
    """Q127 raw response containing extra key 'Explanation' in distractor_analysis must become FAIL_SCHEMA_VALIDATION."""
    raw_response_with_extra_key = json.dumps({
        "grammar_topic": "preposition",
        "sentence_structure": "S + V + P",
        "pattern": "S + V + Prep",
        "vocabulary": [
            {"word": "dedication", "meaning": "sự cống hiến", "part_of_speech": "noun"}
        ],
        "explanation": "Collocation 'with great dedication'.",
        "distractor_analysis": {
            "A": "deduction sai nghĩa",
            "B": "duplication sai nghĩa",
            "C": "declaration sai nghĩa",
            "D": "dedication đúng",
            "Explanation": "Khóa thừa ngoài hợp đồng"
        },
        "difficulty": "medium"
    })

    item = {
        "question_id": 127,
        "test_id": "ETS2026",
        "part": 5,
        "question_no": 127,
        "question_text": "As chief analytics officer, Mr. Ko has worked at Lochstan Ltd. with great _____ for more than twenty years.",
        "option_a": "deduction",
        "option_b": "duplication",
        "option_c": "declaration",
        "option_d": "dedication",
        "correct_answer": "D",
        "status": "PASS_QUALITY_VALIDATED",
        "raw_response": raw_response_with_extra_key,
    }

    revalidator = ReportRevalidator()
    reval = revalidator.revalidate_item(item)

    assert reval["previous_status"] == "PASS_QUALITY_VALIDATED"
    assert reval["status"] == "FAIL_SCHEMA_VALIDATION"
    assert reval["schema_valid"] is False
    assert reval["error_type"] == "EnrichmentValidationError"
    assert reval["status_transition"] == "PASS_QUALITY_VALIDATED -> FAIL_SCHEMA_VALIDATION"


def test_revalidate_item_valid_passes_quality():
    """Valid raw response without extra keys or quality errors yields PASS_QUALITY_VALIDATED."""
    raw_response = json.dumps({
        "grammar_topic": "Preposition + relative pronoun",
        "sentence_structure": "Main clause + after which + S + V + O",
        "pattern": "after which + clause",
        "vocabulary": [
            {"word": "attendees", "meaning": "người tham dự", "part_of_speech": "noun"}
        ],
        "explanation": "Chọn B (after). Cụm after which có nghĩa là sau thời điểm đó.",
        "distractor_analysis": {
            "A": "Across chỉ không gian, không dùng cho thời gian.",
            "B": "After kết hợp với which tạo thành after which.",
            "C": "Inside chỉ không gian bên trong.",
            "D": "Among chỉ quan hệ giữa các thành viên."
        },
        "difficulty": "medium"
    })

    item = {
        "question_id": 101,
        "test_id": "ETS2026",
        "part": 5,
        "question_no": 101,
        "question_text": "The lecture will take place at 6:00 P.M., _____ which attendees may ask questions.",
        "option_a": "across",
        "option_b": "after",
        "option_c": "inside",
        "option_d": "among",
        "correct_answer": "B",
        "status": "PASS_QUALITY_VALIDATED",
        "raw_response": raw_response,
    }

    revalidator = ReportRevalidator()
    reval = revalidator.revalidate_item(item)

    assert reval["status"] == "PASS_QUALITY_VALIDATED"
    assert reval["schema_valid"] is True
    assert reval["quality_valid"] is True
    assert reval["status_transition"] == "PASS_QUALITY_VALIDATED -> PASS_QUALITY_VALIDATED"


def test_revalidate_missing_raw_response_is_not_revalidatable():
    """An item missing raw_response that was marked passed cannot be safely replayed."""
    item = {
        "question_id": 105,
        "question_no": 105,
        "status": "PASS_QUALITY_VALIDATED",
        "raw_response": None,
    }

    revalidator = ReportRevalidator()
    reval = revalidator.revalidate_item(item)

    assert reval["status"] == "NOT_REVALIDATABLE"
    assert reval["error_type"] == "MissingRawResponse"
    assert reval["status_transition"] == "PASS_QUALITY_VALIDATED -> NOT_REVALIDATABLE"


def test_revalidate_llm_service_failure_preserved():
    """An item where LLM call failed originally retains FAIL_LLM_SERVICE."""
    item = {
        "question_id": 103,
        "question_no": 103,
        "status": "FAIL_LLM_SERVICE",
        "error_type": "LLMTimeoutError",
        "error": "Request timed out",
        "raw_response": None,
    }

    revalidator = ReportRevalidator()
    reval = revalidator.revalidate_item(item)

    assert reval["status"] == "FAIL_LLM_SERVICE"
    assert reval["error_type"] == "LLMTimeoutError"
    assert reval["status_transition"] == "FAIL_LLM_SERVICE -> FAIL_LLM_SERVICE"


def test_revalidate_file_never_modifies_source_file(tmp_path):
    """Revalidation must read source file without mutating it, and write to a new output path."""
    source_file = tmp_path / "mock_report.json"
    initial_content = json.dumps({
        "results": [
            {
                "question_id": 101,
                "question_no": 101,
                "status": "PASS_QUALITY_VALIDATED",
                "raw_response": '{"invalid": json syntax}',
            }
        ]
    })
    source_file.write_text(initial_content, encoding="utf-8")

    out_dir = tmp_path / "revalidation"
    revalidator = ReportRevalidator()
    out_path, res_data = revalidator.revalidate_file(source_file, output_dir=out_dir)

    # 1. Source file content must remain byte-for-byte identical
    assert source_file.read_text(encoding="utf-8") == initial_content

    # 2. Output file must exist in out_dir and contain recalculated result
    assert out_path.exists()
    assert out_path.parent == out_dir
    assert res_data["results"][0]["status"] == "FAIL_JSON_DECODE"
    assert res_data["results"][0]["status_transition"] == "PASS_QUALITY_VALIDATED -> FAIL_JSON_DECODE"


def test_revalidate_historical_qwen_report_if_present(tmp_path):
    """Replay historical Qwen benchmark report if present in workspace and verify Q119/Q127 rejection."""
    qwen_report_path = Path("reports/part5_batch_qwen2.5_3b_20261012_123315.json")
    if not qwen_report_path.exists():
        pytest.skip("Historical Qwen report not found in workspace.")

    revalidator = ReportRevalidator()
    out_path, res_data = revalidator.revalidate_file(qwen_report_path, output_dir=tmp_path)

    assert out_path.exists()
    summary = res_data["summary"]
    assert summary["total_questions"] == 30

    # Locate Q119 and Q127 in results
    by_no = {r["question_no"]: r for r in res_data["results"]}
    assert by_no[119]["previous_status"] == "PASS_QUALITY_VALIDATED"
    assert by_no[119]["status"] == "FAIL_SCHEMA_VALIDATION"

    assert by_no[127]["previous_status"] == "PASS_QUALITY_VALIDATED"
    assert by_no[127]["status"] == "FAIL_SCHEMA_VALIDATION"

    # Status transitions must include the two schema failures
    transitions = summary["status_transitions"]
    assert transitions.get("PASS_QUALITY_VALIDATED -> FAIL_SCHEMA_VALIDATION") == 2


def test_revalidate_summary_counts_match_final_statuses_and_total_count():
    """Summary counts must match final statuses, and sum to total_questions == len(results)."""
    valid_raw = json.dumps({
        "grammar_topic": "preposition",
        "sentence_structure": "S + V + Prep + O",
        "pattern": "Prep + N",
        "vocabulary": [{"word": "sample", "meaning": "mẫu", "part_of_speech": "noun"}],
        "explanation": "Chọn A.",
        "distractor_analysis": {"A": "đúng", "B": "sai", "C": "sai", "D": "sai"},
        "difficulty": "easy"
    })
    invalid_schema_raw = json.dumps({
        "grammar_topic": "preposition",
        "sentence_structure": "S + V + Prep + O",
        "pattern": "Prep + N",
        "vocabulary": [{"word": "sample", "meaning": "mẫu", "part_of_speech": "noun"}],
        "explanation": "Chọn A.",
        "distractor_analysis": {"A": "đúng", "B": "sai", "C": "sai", "D": "sai", "EXTRA": "forbidden"},
        "difficulty": "easy"
    })
    invalid_json_raw = "INVALID_JSON{}"

    report_data = {
        "results": [
            {
                "question_id": 1,
                "question_no": 1,
                "status": "PASS_QUALITY_VALIDATED",
                "raw_response": valid_raw,
                "question_text": "Please inspect this sample before finalizing.",
                "option_a": "sample",
                "option_b": "other",
                "option_c": "another",
                "option_d": "neither",
                "correct_answer": "A",
            },
            {
                "question_id": 2,
                "question_no": 2,
                "status": "PASS_QUALITY_VALIDATED",
                "raw_response": invalid_schema_raw,
                "question_text": "Please inspect this sample before finalizing.",
                "option_a": "sample",
                "option_b": "other",
                "option_c": "another",
                "option_d": "neither",
                "correct_answer": "A",
            },
            {
                "question_id": 3,
                "question_no": 3,
                "status": "PASS_QUALITY_VALIDATED",
                "raw_response": invalid_json_raw,
                "question_text": "Please inspect this sample before finalizing.",
                "option_a": "sample",
                "option_b": "other",
                "option_c": "another",
                "option_d": "neither",
                "correct_answer": "A",
            },
            {
                "question_id": 4,
                "question_no": 4,
                "status": "FAIL_LLM_SERVICE",
                "raw_response": None,
                "error_type": "TimeoutError",
                "error": "timed out",
            },
        ]
    }

    revalidator = ReportRevalidator()
    reval_data = revalidator.revalidate_report_data(report_data)

    results = reval_data["results"]
    summary = reval_data["summary"]

    assert len(results) == 4
    assert summary["total_questions"] == 4

    # Count final statuses directly from results array
    direct_counts = {}
    for r in results:
        direct_counts[r["status"]] = direct_counts.get(r["status"], 0) + 1

    assert direct_counts == summary["recalculated_status_counts"]
    assert sum(summary["recalculated_status_counts"].values()) == 4
    assert summary["recalculated_status_counts"]["PASS_QUALITY_VALIDATED"] == 1
    assert summary["recalculated_status_counts"]["FAIL_SCHEMA_VALIDATION"] == 1
    assert summary["recalculated_status_counts"]["FAIL_JSON_DECODE"] == 1
    assert summary["recalculated_status_counts"]["FAIL_LLM_SERVICE"] == 1


def test_revalidate_transition_counts_sum_to_number_of_results():
    """Transition counts must account for every result exactly once."""
    report_data = {
        "results": [
            {
                "question_id": 10,
                "question_no": 10,
                "status": "PASS_QUALITY_VALIDATED",
                "raw_response": "not json",
            },
            {
                "question_id": 11,
                "question_no": 11,
                "status": "FAIL_LLM_SERVICE",
                "raw_response": None,
            },
        ]
    }

    revalidator = ReportRevalidator()
    reval_data = revalidator.revalidate_report_data(report_data)

    summary = reval_data["summary"]
    transitions = summary["status_transitions"]

    assert sum(transitions.values()) == len(reval_data["results"]) == 2
    assert transitions["PASS_QUALITY_VALIDATED -> FAIL_JSON_DECODE"] == 1
    assert transitions["FAIL_LLM_SERVICE -> FAIL_LLM_SERVICE"] == 1


def test_revalidate_mixed_statuses_remain_independent_across_batch():
    """Failures on one question must not leak into adjacent questions in the batch."""
    valid_raw = json.dumps({
        "grammar_topic": "pronoun",
        "sentence_structure": "S + V + O",
        "pattern": "Subject pronoun",
        "vocabulary": [{"word": "they", "meaning": "họ", "part_of_speech": "pronoun"}],
        "explanation": "Chọn A.",
        "distractor_analysis": {"A": "đúng", "B": "sai", "C": "sai", "D": "sai"},
        "difficulty": "easy"
    })
    q_dict = {
        "question_text": "When they arrive, please notify the director.",
        "option_a": "they",
        "option_b": "them",
        "option_c": "their",
        "option_d": "theirs",
        "correct_answer": "A",
    }
    report_data = {
        "results": [
            dict(q_dict, question_id=1, question_no=1, status="PASS_QUALITY_VALIDATED", raw_response=valid_raw),
            dict(q_dict, question_id=2, question_no=2, status="PASS_QUALITY_VALIDATED", raw_response="{broken json"),
            dict(q_dict, question_id=3, question_no=3, status="PASS_QUALITY_VALIDATED", raw_response=valid_raw),
        ]
    }

    revalidator = ReportRevalidator()
    reval_data = revalidator.revalidate_report_data(report_data)
    results = reval_data["results"]

    assert results[0]["status"] == "PASS_QUALITY_VALIDATED"
    assert results[0]["schema_valid"] is True
    assert results[0]["error"] is None

    assert results[1]["status"] == "FAIL_JSON_DECODE"
    assert results[1]["schema_valid"] is False
    assert results[1]["error_type"] == "EnrichmentJSONDecodeError"

    assert results[2]["status"] == "PASS_QUALITY_VALIDATED"
    assert results[2]["schema_valid"] is True
    assert results[2]["error"] is None


def test_revalidate_malformed_or_missing_status_data_fails_clearly():
    """Malformed or missing status in items or reports must raise descriptive exceptions."""
    revalidator = ReportRevalidator()

    # 1. Item missing 'status' field entirely
    with pytest.raises(ValueError, match="missing a valid 'status' string"):
        revalidator.revalidate_item({"question_no": 101, "raw_response": "{}"})

    # 2. Item with empty/whitespace status
    with pytest.raises(ValueError, match="missing a valid 'status' string"):
        revalidator.revalidate_item({"question_no": 102, "status": "   ", "raw_response": "{}"})

    # 3. Item that is not a dictionary
    with pytest.raises(ValueError, match="Report item must be a dictionary"):
        revalidator.revalidate_item("not a dict")  # type: ignore

    # 4. Report data not a dictionary
    with pytest.raises(ValueError, match="Report data must be a dictionary"):
        revalidator.revalidate_report_data(["not", "a", "dict"])  # type: ignore

    # 5. Report data missing results or items list
    with pytest.raises(ValueError, match="must contain a 'results' or 'items' list"):
        revalidator.revalidate_report_data({"metadata": {}})

    # 6. Report results is not a list
    with pytest.raises(ValueError, match="must be a list"):
        revalidator.revalidate_report_data({"results": "not a list"})


def test_revalidate_historical_gemini_report_if_present(tmp_path):
    """Replay historical Gemini benchmark report under aligned taxonomy: 28 PASS, 1 SCHEMA, 1 JSON DECODE."""
    gemini_report_path = Path("reports/part5_batch_gemini-3.5-flash-lite_20261012_122158.json")
    if not gemini_report_path.exists():
        pytest.skip("Historical Gemini report not found in workspace.")

    revalidator = ReportRevalidator()
    out_path, res_data = revalidator.revalidate_file(gemini_report_path, output_dir=tmp_path)

    assert out_path.exists()
    summary = res_data["summary"]
    assert summary["total_questions"] == 30

    recalc = summary["recalculated_status_counts"]
    # With noun phrase, verb phrase, and prepositional phrase accepted, 11 questions now pass
    assert recalc["PASS_QUALITY_VALIDATED"] == 28
    # Only Q120 (missing distractor D) remains a schema failure
    assert recalc["FAIL_SCHEMA_VALIDATION"] == 1
    # Only Q102 remains a JSON decode failure
    assert recalc["FAIL_JSON_DECODE"] == 1
    assert sum(recalc.values()) == 30

    transitions = summary["status_transitions"]
    assert transitions["PASS_QUALITY_VALIDATED -> PASS_QUALITY_VALIDATED"] == 28
    assert transitions["FAIL_SCHEMA_VALIDATION -> FAIL_SCHEMA_VALIDATION"] == 1
    assert transitions["FAIL_JSON_DECODE -> FAIL_JSON_DECODE"] == 1
    assert sum(transitions.values()) == 30

