import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.models.question import Question
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_validator import EnrichmentValidator
from scripts.test_gemini_batch import (
    GeminiAPIKeyError,
    GeminiClient,
    QuestionInput,
    RequestPacer,
    parse_question_nos,
    process_benchmark_item,
    run_batch,
    sanitize_secret,
    validate_request_interval,
    write_benchmark_reports,
)


@pytest.fixture
def sample_question_data():
    return {
        "id": 101,
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
        "explanation": "After which connects the relative clause.",
    }


@pytest.fixture
def valid_enrichment_dict():
    return {
        "grammar_topic": "Preposition in Relative Clause",
        "sentence_structure": "S + V + at [Time], [Prep] + which + S + V",
        "pattern": "after + which + clause",
        "vocabulary": [
            {
                "word": "lecture",
                "meaning": "bài giảng",
                "part_of_speech": "noun",
            },
            {
                "word": "attendees",
                "meaning": "người tham dự",
                "part_of_speech": "noun",
            },
        ],
        "explanation": "Đáp án B (after) tạo nên cụm giới từ 'after which' phù hợp với ngữ nghĩa thời gian.",
        "distractor_analysis": {
            "A": "Đáp án A (across) không phù hợp với ngữ cảnh thời gian.",
            "B": "Đáp án B (after) đúng và phù hợp với cấu trúc câu.",
            "C": "Đáp án C (inside) không phù hợp với ngữ cảnh thời gian.",
            "D": "Đáp án D (among) không phù hợp vì among đi với danh từ số nhiều.",
        },
        "difficulty": "medium",
    }


def test_gemini_missing_api_key_raises_error(monkeypatch):
    """When GEMINI_API_KEY is not set, GeminiClient raises GeminiAPIKeyError with clear guidance."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiAPIKeyError) as exc_info:
        GeminiClient(api_key=None)
    assert "GEMINI_API_KEY environment variable is not set" in str(exc_info.value)


def test_parse_question_nos_variants():
    """Verify single, multi-number, whitespace, and invalid question number parsing."""
    assert parse_question_nos("120") == [120]
    assert parse_question_nos("102,104,106,112,120,124,126,130") == [
        102, 104, 106, 112, 120, 124, 126, 130
    ]
    assert parse_question_nos("  101 , 102  , 103 ") == [101, 102, 103]
    assert parse_question_nos(None) == []
    assert parse_question_nos("") == []

    with pytest.raises(ValueError) as exc:
        parse_question_nos("101,abc,103")
    assert "Invalid question number: 'abc'" in str(exc.value)


def test_gemini_client_generate_success_and_usage(valid_enrichment_dict):
    """Verify mock Gemini client records text and usage metadata."""
    mock_models = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(valid_enrichment_dict)

    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 350
    mock_usage.candidates_token_count = 180
    mock_usage.total_token_count = 530
    mock_response.usage_metadata = mock_usage

    mock_models.generate_content.return_value = mock_response

    mock_sdk_client = MagicMock()
    mock_sdk_client.models = mock_models

    gemini_client = GeminiClient(
        api_key="fake-test-key",
        model="gemini-3.5-flash-lite",
        client=mock_sdk_client,
    )

    out = gemini_client.generate("Test prompt")
    assert json.loads(out) == valid_enrichment_dict
    assert gemini_client.last_usage == {
        "prompt_tokens": 350,
        "candidates_tokens": 180,
        "total_tokens": 530,
    }


def test_gemini_process_item_pass_quality_validated(sample_question_data, valid_enrichment_dict):
    """Successful generation, schema validation, and quality validation yield PASS_QUALITY_VALIDATED."""
    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps(valid_enrichment_dict)
    mock_client.last_raw_response = json.dumps(valid_enrichment_dict)
    mock_client.last_usage = {
        "prompt_tokens": 400,
        "candidates_tokens": 200,
        "total_tokens": 600,
    }
    mock_client.api_key = "fake-key"

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    res = process_benchmark_item(
        source=sample_question_data,
        service=service,
        validator=validator,
        gemini_client=mock_client,
    )

    assert res["status"] == "PASS_QUALITY_VALIDATED"
    assert res["schema_valid"] is True
    assert res["quality_valid"] is True
    assert res["quality_status"] == "VALID"
    assert res["token_usage"]["total_tokens"] == 600
    assert res["enrichment"]["grammar_topic"] == "Preposition in Relative Clause"


def test_gemini_process_item_json_decode_error(sample_question_data):
    """Malformed JSON response yields FAIL_JSON_DECODE without crashing the process."""
    mock_client = MagicMock()
    malformed = "This is not valid JSON at all"
    mock_client.generate.return_value = malformed
    mock_client.last_raw_response = malformed
    mock_client.last_usage = {}
    mock_client.api_key = "fake-key"

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    res = process_benchmark_item(
        source=sample_question_data,
        service=service,
        validator=validator,
        gemini_client=mock_client,
    )

    assert res["status"] == "FAIL_JSON_DECODE"
    assert res["schema_valid"] is False
    assert res["quality_valid"] is False
    assert res["error_type"] == "EnrichmentJSONDecodeError"


def test_gemini_process_item_schema_validation_error(sample_question_data):
    """JSON missing required fields yields FAIL_SCHEMA_VALIDATION."""
    mock_client = MagicMock()
    invalid_schema = json.dumps({"grammar_topic": "Only one field"})
    mock_client.generate.return_value = invalid_schema
    mock_client.last_raw_response = invalid_schema
    mock_client.last_usage = {}
    mock_client.api_key = "fake-key"

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    res = process_benchmark_item(
        source=sample_question_data,
        service=service,
        validator=validator,
        gemini_client=mock_client,
    )

    assert res["status"] == "FAIL_SCHEMA_VALIDATION"
    assert res["schema_valid"] is False
    assert res["error_type"] == "EnrichmentValidationError"


def test_gemini_process_item_quality_rejection(sample_question_data, valid_enrichment_dict):
    """Ungrounded vocabulary item correctly yields REJECTED_QUALITY."""
    valid_enrichment_dict["vocabulary"] = [
        {
            "word": "unrelated_hallucination",
            "meaning": "không có trong đề",
            "part_of_speech": "noun",
        }
    ]

    mock_client = MagicMock()
    response_text = json.dumps(valid_enrichment_dict)
    mock_client.generate.return_value = response_text
    mock_client.last_raw_response = response_text
    mock_client.last_usage = {}
    mock_client.api_key = "fake-key"

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    res = process_benchmark_item(
        source=sample_question_data,
        service=service,
        validator=validator,
        gemini_client=mock_client,
    )

    assert res["status"] == "REJECTED_QUALITY"
    assert res["schema_valid"] is True
    assert res["quality_valid"] is False
    assert res["quality_error_code"] == "UNGROUNDED_VOCABULARY"


def test_gemini_process_item_api_failure_handling(sample_question_data):
    """API connection, timeout, or rate-limit error yields FAIL_LLM_SERVICE."""
    mock_client = MagicMock()
    mock_client.generate.side_effect = RuntimeError("ResourceExhausted: 429 Rate limit exceeded")
    mock_client.last_raw_response = None
    mock_client.last_usage = {}
    mock_client.api_key = "fake-key"

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    res = process_benchmark_item(
        source=sample_question_data,
        service=service,
        validator=validator,
        gemini_client=mock_client,
    )

    assert res["status"] == "FAIL_LLM_SERVICE"
    assert res["llm_received"] is False
    assert "429 Rate limit exceeded" in res["error"]


def test_gemini_run_batch_read_only_no_db_writes(sample_question_data, valid_enrichment_dict, monkeypatch, tmp_path):
    """Batch execution strictly performs read-only inference without writing to database."""
    def forbidden_db_mutation(*args, **kwargs):
        raise AssertionError("Database mutation is strictly forbidden during benchmark execution")

    monkeypatch.setattr("sqlalchemy.orm.Session.add", forbidden_db_mutation)
    monkeypatch.setattr("sqlalchemy.orm.Session.commit", forbidden_db_mutation)

    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps(valid_enrichment_dict)
    mock_client.last_raw_response = json.dumps(valid_enrichment_dict)
    mock_client.last_usage = {"prompt_tokens": 100, "candidates_tokens": 50, "total_tokens": 150}

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    results, json_path, csv_path = run_batch(
        source_questions=[sample_question_data],
        service=service,
        validator=validator,
        gemini_client=mock_client,
        report_dir=tmp_path,
    )

    assert len(results) == 1
    assert results[0]["status"] == "PASS_QUALITY_VALIDATED"
    assert json_path.exists()
    assert csv_path.exists()


def test_gemini_report_generation_sanitizes_secrets(sample_question_data, tmp_path):
    """Verify API keys and credentials are masked from logs and report files."""
    fake_secret = "AIzaSyFakeSecretKey123456789012345678"
    raw_error_with_key = f"API error connecting to https://generativelanguage.googleapis.com?key={fake_secret}"

    mock_client = MagicMock()
    mock_client.generate.side_effect = RuntimeError(raw_error_with_key)
    mock_client.last_raw_response = None
    mock_client.last_usage = {}
    mock_client.api_key = fake_secret

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    results, json_path, csv_path = run_batch(
        source_questions=[sample_question_data],
        service=service,
        validator=validator,
        gemini_client=mock_client,
        report_dir=tmp_path,
    )

    json_content = json_path.read_text(encoding="utf-8")
    csv_content = csv_path.read_text(encoding="utf-8")

    assert fake_secret not in json_content
    assert fake_secret not in csv_content
    assert "[REDACTED_API_KEY]" in json_content
    assert "[REDACTED_API_KEY]" in csv_content


def test_enrichment_service_prompt_generation(sample_question_data):
    """Verify that EnrichmentService generates correct prompt structure."""
    question_input = QuestionInput(sample_question_data)

    ai_input = EnrichmentService.build_ai_input(question_input)
    prompt = EnrichmentService.build_prompt(ai_input)

    assert sample_question_data["question_text"] in prompt
    assert f"Option A: {sample_question_data['option_a']}" in prompt
    assert f"Option B: {sample_question_data['option_b']}" in prompt
    assert f"Option C: {sample_question_data['option_c']}" in prompt
    assert f"Option D: {sample_question_data['option_d']}" in prompt
    assert f"Authoritative correct answer: B — after" in prompt


def test_gemini_main_missing_key_returns_exit_code_1(monkeypatch):
    """Running main() without GEMINI_API_KEY returns exit code 1."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("scripts.test_gemini_batch.load_env_file", lambda: None)
    monkeypatch.setattr("sys.argv", ["test_gemini_batch.py"])

    from scripts.test_gemini_batch import main
    exit_code = main()
    assert exit_code == 1


def test_gemini_process_item_google_api_error_instance(sample_question_data):
    """Direct google.genai.errors.APIError instance maps to FAIL_LLM_SERVICE."""
    from google.genai import errors as genai_errors

    mock_client = MagicMock()
    mock_client.generate.side_effect = genai_errors.APIError(429, "Resource has been exhausted")
    mock_client.last_raw_response = None
    mock_client.last_usage = {}
    mock_client.api_key = "fake-key"

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    res = process_benchmark_item(
        source=sample_question_data,
        service=service,
        validator=validator,
        gemini_client=mock_client,
    )

    assert res["status"] == "FAIL_LLM_SERVICE"
    assert res["error_type"] == "APIError"
    assert "Resource has been exhausted" in res["error"]


def test_gemini_client_generate_multi_param_exception_not_reinstantiated():
    """Verify exceptions with multi-argument __init__ are not re-instantiated with 1 argument."""
    class StrictMultiArgError(Exception):
        def __init__(self, code: int, response_json: dict):
            super().__init__(f"{code}: {response_json}")
            self.code = code
            self.response_json = response_json

    secret_key = "AIzaSySecretMultiArgTestKey99999999"
    underlying_mock = MagicMock()
    underlying_mock.models.generate_content.side_effect = StrictMultiArgError(
        429, {"error": f"Quota exceeded for key {secret_key}"}
    )

    client = GeminiClient(api_key=secret_key, client=underlying_mock)

    with pytest.raises(StrictMultiArgError) as exc_info:
        client.generate("Test prompt")

    caught = exc_info.value
    assert isinstance(caught, StrictMultiArgError)
    assert caught.code == 429
    # Ensure secret is sanitized from args
    assert secret_key not in str(caught)
    assert "[REDACTED_API_KEY]" in str(caught)


def test_gemini_client_generate_google_api_error_preserves_type_and_sanitizes():
    """Verify real google.genai.errors.APIError preserves its exact type and sanitizes in-place."""
    from google.genai import errors as genai_errors

    secret_key = "AIzaSyGoogleRealAPIErrorKey88888888"
    raw_api_err = genai_errors.APIError(
        429,
        {"error": {"message": f"RESOURCE_EXHAUSTED key={secret_key}", "status": "RESOURCE_EXHAUSTED"}},
    )

    underlying_mock = MagicMock()
    underlying_mock.models.generate_content.side_effect = raw_api_err

    client = GeminiClient(api_key=secret_key, client=underlying_mock)

    with pytest.raises(genai_errors.APIError) as exc_info:
        client.generate("Test prompt")

    caught = exc_info.value
    assert isinstance(caught, genai_errors.APIError)
    assert secret_key not in str(caught)
    assert "[REDACTED_API_KEY]" in str(caught)


def test_gemini_batch_continues_on_item_error(sample_question_data, valid_enrichment_dict, tmp_path):
    """Batch execution records failure for a failed question and continues processing subsequent questions."""
    from google.genai import errors as genai_errors

    q1 = dict(sample_question_data)
    q1["id"] = 101
    q1["question_no"] = 101

    q2 = dict(sample_question_data)
    q2["id"] = 102
    q2["question_no"] = 102

    mock_client = MagicMock()
    # First call fails with 429 APIError, second call succeeds with valid JSON
    api_err = genai_errors.APIError(429, {"error": {"message": "429 Quota exhausted", "status": "RESOURCE_EXHAUSTED"}})
    valid_resp = json.dumps(valid_enrichment_dict)

    mock_client.generate.side_effect = [api_err, valid_resp]
    mock_client.last_raw_response = None
    mock_client.last_usage = {"prompt_tokens": 50, "candidates_tokens": 20, "total_tokens": 70}
    mock_client.api_key = "fake-key"

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    results, json_path, csv_path = run_batch(
        source_questions=[q1, q2],
        service=service,
        validator=validator,
        gemini_client=mock_client,
        report_dir=tmp_path,
    )

    assert len(results) == 2
    # Item 1 failed with FAIL_LLM_SERVICE
    assert results[0]["question_no"] == 101
    assert results[0]["status"] == "FAIL_LLM_SERVICE"
    assert results[0]["error_type"] == "APIError"
    assert "Quota exhausted" in results[0]["error"]

    # Item 2 succeeded with PASS_QUALITY_VALIDATED
    assert results[1]["question_no"] == 102
    assert results[1]["status"] == "PASS_QUALITY_VALIDATED"

    # Report accurately summarizes 1 failed and 1 passed
    report_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert report_data["total_questions"] == 2
    assert report_data["llm_failed"] == 1
    assert report_data["quality_passed"] == 1
    assert report_data["unexpected_failed"] == 0


def test_request_pacer_first_request_not_delayed(monkeypatch):
    """First request must not be delayed unnecessarily."""
    sleep_mock = MagicMock()
    monkeypatch.setattr("time.sleep", sleep_mock)
    monkeypatch.setattr("time.monotonic", lambda: 100.0)

    pacer = RequestPacer(interval=4.5)
    slept = pacer.wait()

    sleep_mock.assert_not_called()
    assert slept == 0.0
    assert pacer.last_request_start == 100.0


def test_request_pacer_next_request_delayed_by_remaining_time(monkeypatch):
    """Next request is delayed by exactly the remaining time."""
    sleep_mock = MagicMock()
    current_time = 100.0

    def fake_monotonic():
        return current_time

    def fake_sleep(secs):
        nonlocal current_time
        sleep_mock(secs)
        current_time += secs

    monkeypatch.setattr("time.monotonic", fake_monotonic)
    monkeypatch.setattr("time.sleep", fake_sleep)

    pacer = RequestPacer(interval=4.5)

    # Request 1 starts at 100.0
    slept1 = pacer.wait()
    assert slept1 == 0.0

    # Advance time by 2.0s (request 1 took 2.0s)
    current_time = 102.0

    # Request 2 is initiated at 102.0: remaining = 4.5 - 2.0 = 2.5s
    slept2 = pacer.wait()
    assert round(slept2, 2) == 2.5
    sleep_mock.assert_called_once_with(2.5)
    assert round(current_time, 2) == 104.5


def test_request_pacer_next_request_no_delay_if_interval_elapsed(monkeypatch):
    """Next request is not delayed if the minimum interval has already elapsed."""
    sleep_mock = MagicMock()
    current_time = 100.0

    monkeypatch.setattr("time.monotonic", lambda: current_time)
    monkeypatch.setattr("time.sleep", sleep_mock)

    pacer = RequestPacer(interval=4.5)

    # Request 1 starts at 100.0
    pacer.wait()

    # Advance time by 5.0s (> 4.5s)
    current_time = 105.0

    # Request 2 starts at 105.0: remaining = 4.5 - 5.0 <= 0 -> no sleep
    slept2 = pacer.wait()
    assert slept2 == 0.0
    sleep_mock.assert_not_called()


def test_gemini_client_failed_request_enforces_pacing_for_next_request(monkeypatch):
    """A failed request still records its start time and enforces pacing for the next request."""
    from google.genai import errors as genai_errors

    sleep_mock = MagicMock()
    current_time = 100.0

    def fake_monotonic():
        return current_time

    def fake_sleep(secs):
        nonlocal current_time
        sleep_mock(secs)
        current_time += secs

    monkeypatch.setattr("time.monotonic", fake_monotonic)
    monkeypatch.setattr("time.sleep", fake_sleep)

    underlying_mock = MagicMock()
    # First call fails with 429 APIError, second call succeeds
    api_err = genai_errors.APIError(429, {"error": {"message": "429 Rate limit", "status": "RESOURCE_EXHAUSTED"}})
    mock_resp = MagicMock()
    mock_resp.text = '{"success": true}'
    mock_resp.usage_metadata = None
    underlying_mock.models.generate_content.side_effect = [api_err, mock_resp]

    client = GeminiClient(api_key="fake-key", client=underlying_mock, request_interval=4.5)

    # First call starts at 100.0, fails
    with pytest.raises(genai_errors.APIError):
        client.generate("prompt 1")
    sleep_mock.assert_not_called()

    # Suppose failure happened quickly, and next request is attempted 1.5s later (t = 101.5)
    current_time = 101.5

    # Second call must wait remaining: 4.5 - 1.5 = 3.0s
    client.generate("prompt 2")
    sleep_mock.assert_called_once_with(3.0)


def test_request_interval_cli_parsing_and_validation():
    """Verify --request-interval is parsed correctly and rejects negative or invalid values."""
    import argparse

    assert validate_request_interval("4.5") == 4.5
    assert validate_request_interval("0") == 0.0
    assert validate_request_interval(2) == 2.0

    with pytest.raises(argparse.ArgumentTypeError):
        validate_request_interval("-1.0")

    with pytest.raises(argparse.ArgumentTypeError):
        validate_request_interval("not_a_number")

    with pytest.raises(ValueError, match="non-negative"):
        RequestPacer(interval=-0.5)

    with pytest.raises(ValueError, match="non-negative"):
        GeminiClient(api_key="fake-key", request_interval=-1.0, client=MagicMock())


def test_benchmark_reports_include_request_interval(sample_question_data, valid_enrichment_dict, tmp_path):
    """Verify reports include request_interval in metadata."""
    mock_client = MagicMock()
    mock_client.generate.return_value = json.dumps(valid_enrichment_dict)
    mock_client.last_raw_response = json.dumps(valid_enrichment_dict)
    mock_client.last_usage = {}
    mock_client.api_key = "fake-key"
    mock_client.request_interval = 3.5

    service = EnrichmentService(llm_service=mock_client)
    validator = EnrichmentValidator()

    results, json_path, csv_path = run_batch(
        source_questions=[sample_question_data],
        service=service,
        validator=validator,
        gemini_client=mock_client,
        report_dir=tmp_path,
        request_interval=3.5,
    )

    report_data = json.loads(json_path.read_text(encoding="utf-8"))
    assert report_data["request_interval"] == 3.5

