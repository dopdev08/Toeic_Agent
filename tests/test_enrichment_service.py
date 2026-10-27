import json
from unittest.mock import MagicMock
import pytest

from app.models.question import Question
from app.schemas.enrichment import QuestionEnrichment
from app.services.enrichment_response_parser import (
    EnrichmentJSONDecodeError,
    EnrichmentValidationError,
)
from app.services.enrichment_service import EnrichmentService
from app.services.llm_client import LLMConnectionError


class FakeLLMService:
    def __init__(self, response_text: str = "") -> None:
        self.response_text = response_text
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response_text


@pytest.fixture
def sample_question():
    return Question(
        id=999,
        test_id="ETS2026",
        part=5,
        question_no=101,
        question_text="Ms. Davis requested that the marketing report ______ revised before the executive meeting.",
        option_a="is",
        option_b="was",
        option_c="be",
        option_d="being",
        correct_answer="C",
        explanation="Subjunctive mood question.",
    )


@pytest.fixture
def valid_enrichment_payload():
    return {
        "grammar_topic": "Subjunctive Mood",
        "sentence_structure": "S + requested + that + S + (should) + V-bare",
        "pattern": "request that somebody (should) do something",
        "vocabulary": [
            {
                "word": "request",
                "meaning": "yêu cầu",
                "part_of_speech": "verb",
            }
        ],
        "explanation": "Động từ theo sau 'requested that' ở thể giả định thức.",
        "distractor_analysis": {
            "A": "Sai vì dùng 'is'",
            "B": "Sai vì dùng 'was'",
            "C": "Đúng vì 'be' là dạng nguyên thể",
            "D": "Sai vì 'being' là phân từ",
        },
        "difficulty": "hard",
    }


def test_build_ai_input_matches_contract(sample_question):
    ai_input = EnrichmentService.build_ai_input(sample_question)

    assert ai_input == {
        "question_text": "Ms. Davis requested that the marketing report ______ revised before the executive meeting.",
        "option_a": "is",
        "option_b": "was",
        "option_c": "be",
        "option_d": "being",
        "correct_answer": "C",
    }
    # Ensure database-only metadata fields are NOT present in AI input
    assert "id" not in ai_input
    assert "test_id" not in ai_input
    assert "part" not in ai_input
    assert "question_no" not in ai_input
    assert "created_at" not in ai_input
    assert "status" not in ai_input


def test_expected_prompt_sent_to_llm(sample_question, valid_enrichment_payload):
    fake_llm = FakeLLMService(response_text=json.dumps(valid_enrichment_payload))
    service = EnrichmentService(llm_service=fake_llm)

    service.enrich_question(sample_question)

    assert fake_llm.last_prompt is not None
    assert "Ms. Davis requested that the marketing report ______ revised" in fake_llm.last_prompt
    assert "Option A: is" in fake_llm.last_prompt
    assert "Option B: was" in fake_llm.last_prompt
    assert "Option C: be" in fake_llm.last_prompt
    assert "Option D: being" in fake_llm.last_prompt
    assert "Authoritative correct answer: C — be" in fake_llm.last_prompt
    assert "grammar_topic" in fake_llm.last_prompt


def test_enrich_question_success(sample_question, valid_enrichment_payload):
    fake_llm = FakeLLMService(response_text=json.dumps(valid_enrichment_payload))
    service = EnrichmentService(llm_service=fake_llm)

    result = service.enrich_question(sample_question)

    assert isinstance(result, QuestionEnrichment)
    assert result.grammar_topic == "Subjunctive Mood"
    assert result.difficulty == "hard"
    assert result.distractor_analysis.C == "Đúng vì 'be' là dạng nguyên thể"
    assert len(result.vocabulary) == 1
    assert result.vocabulary[0].word == "request"


def test_invalid_json_propagates_decode_error(sample_question):
    fake_llm = FakeLLMService(response_text="Not valid json string at all")
    service = EnrichmentService(llm_service=fake_llm)

    with pytest.raises(EnrichmentJSONDecodeError) as exc_info:
        service.enrich_question(sample_question)

    assert "Failed to decode JSON" in str(exc_info.value)


def test_invalid_schema_propagates_validation_error(sample_question):
    incomplete_json = json.dumps({"grammar_topic": "Only one field"})
    fake_llm = FakeLLMService(response_text=incomplete_json)
    service = EnrichmentService(llm_service=fake_llm)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        service.enrich_question(sample_question)

    assert "QuestionEnrichment validation" in str(exc_info.value)


def test_llm_service_error_propagates_directly(sample_question):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = LLMConnectionError("Connection refused")
    service = EnrichmentService(llm_service=mock_llm)

    with pytest.raises(LLMConnectionError) as exc_info:
        service.enrich_question(sample_question)

    assert "Connection refused" in str(exc_info.value)


def test_service_does_not_access_database(sample_question, valid_enrichment_payload, monkeypatch):
    fake_llm = FakeLLMService(response_text=json.dumps(valid_enrichment_payload))
    service = EnrichmentService(llm_service=fake_llm)

    # Monkeypatch database session commit/add to ensure no DB calls are attempted
    def forbidden_db_call(*args, **kwargs):
        raise AssertionError("Database access is forbidden in EnrichmentService")

    monkeypatch.setattr("sqlalchemy.orm.Session.add", forbidden_db_call)
    monkeypatch.setattr("sqlalchemy.orm.Session.commit", forbidden_db_call)

    # Execution must complete cleanly without touching SQLAlchemy session
    result = service.enrich_question(sample_question)
    assert isinstance(result, QuestionEnrichment)


def test_question_with_none_option_d(sample_question, valid_enrichment_payload):
    # Simulate a Part 2 question or question where option_d is None
    sample_question.option_d = None
    fake_llm = FakeLLMService(response_text=json.dumps(valid_enrichment_payload))
    service = EnrichmentService(llm_service=fake_llm)

    ai_input = service.build_ai_input(sample_question)
    assert ai_input["option_d"] is None

    result = service.enrich_question(sample_question)
    assert isinstance(result, QuestionEnrichment)
    assert "Option D: None" in fake_llm.last_prompt


def test_correct_answer_passed_through_unchanged(sample_question, valid_enrichment_payload):
    sample_question.correct_answer = "B"
    fake_llm = FakeLLMService(response_text=json.dumps(valid_enrichment_payload))
    service = EnrichmentService(llm_service=fake_llm)

    ai_input = service.build_ai_input(sample_question)
    assert ai_input["correct_answer"] == "B"

    service.enrich_question(sample_question)
    assert "Authoritative correct answer: B — was" in fake_llm.last_prompt


def test_get_correct_option_text_derived_for_all_options():
    ai_input = {
        "question_text": "Sample text",
        "option_a": "alpha",
        "option_b": "beta",
        "option_c": "gamma",
        "option_d": "delta",
    }

    # Verify uppercase A, B, C, D
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": "A"}) == "alpha"
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": "B"}) == "beta"
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": "C"}) == "gamma"
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": "D"}) == "delta"

    # Verify case-insensitivity and whitespace handling
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": "a"}) == "alpha"
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": " b "}) == "beta"
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": "c\n"}) == "gamma"
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": " d"}) == "delta"

    # Verify invalid or missing correct_answer yields empty string
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": "E"}) == ""
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": ""}) == ""
    assert EnrichmentService.get_correct_option_text({**ai_input, "correct_answer": None}) == ""


def test_prompt_includes_authoritative_answer_letter_and_option_text():
    sample_data = {
        "question_text": "The lecture will take place at 6:00 P.M., _____ which attendees may ask questions.",
        "option_a": "across",
        "option_b": "after",
        "option_c": "inside",
        "option_d": "among",
        "correct_answer": "B",
    }
    prompt = EnrichmentService.build_prompt(sample_data)

    # Must explicitly state authoritative correct answer letter and option text
    assert "Authoritative correct answer: B — after" in prompt
    # Must preserve standard option listings
    assert "Option A: across" in prompt
    assert "Option B: after" in prompt
    assert "Option C: inside" in prompt
    assert "Option D: among" in prompt


def test_prompt_requests_all_enrichment_json_fields():
    ai_input = {
        "question_text": "Test question",
        "option_a": "one",
        "option_b": "two",
        "option_c": "three",
        "option_d": "four",
        "correct_answer": "A",
    }
    prompt = EnrichmentService.build_prompt(ai_input)

    # Verify all 7 required schema fields are requested in the prompt
    for field in [
        "grammar_topic",
        "sentence_structure",
        "pattern",
        "vocabulary",
        "explanation",
        "distractor_analysis",
        "difficulty",
    ]:
        assert f'"{field}"' in prompt


def test_six_field_input_contract_unchanged(sample_question):
    ai_input = EnrichmentService.build_ai_input(sample_question)
    expected_keys = {
        "question_text",
        "option_a",
        "option_b",
        "option_c",
        "option_d",
        "correct_answer",
    }
    assert set(ai_input.keys()) == expected_keys
    # No extra derived field is added to the public input contract
    assert "correct_option_text" not in ai_input


def test_production_prompt_and_documentation_consistency():
    from pathlib import Path
    from app.services.enrichment_service import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

    doc_path = Path("docs/ai-enrichment-prompt.md")
    assert doc_path.exists(), "docs/ai-enrichment-prompt.md must exist"

    doc_content = doc_path.read_text(encoding="utf-8")

    # Verify documented system prompt matches production SYSTEM_PROMPT
    assert SYSTEM_PROMPT.strip() in doc_content
    # Verify documented user prompt template matches production USER_PROMPT_TEMPLATE
    assert USER_PROMPT_TEMPLATE.strip() in doc_content


def test_prompt_does_not_contain_contaminated_examples():
    """Ensure biased few-shot example patterns identified in the linguistic audit are excluded."""
    from app.services.enrichment_service import SYSTEM_PROMPT

    problematic_tokens = [
        "Preposition + Relative Pronoun",
        "at [Time]",
        "which",
        "preposition + which + clause",
        "prior to + V-ing",
    ]
    for token in problematic_tokens:
        assert token not in SYSTEM_PROMPT, f"Problematic token '{token}' found in SYSTEM_PROMPT"


def test_prompt_contains_precise_sentence_analysis_instructions():
    """Verify presence of core analysis instructions preventing hallucinated structures."""
    from app.services.enrichment_service import SYSTEM_PROMPT

    required_phrases = [
        "Analyze the exact sentence and the position of the blank",
        "Use the four answer choices to identify the actual distinction being tested",
        "Never force a question into a relative-clause, preposition, or any complex pattern",
        "Never introduce words, prepositions, clauses, or relationships that are not present",
        "standard English parts of speech",
    ]
    for phrase in required_phrases:
        assert phrase in SYSTEM_PROMPT, f"Required instruction phrase '{phrase}' missing from SYSTEM_PROMPT"


def test_prompt_incorporates_full_question_payload_and_authoritative_answer(sample_question):
    """Verify prompt faithfully renders all question fields through the service interface."""
    from app.services.enrichment_service import EnrichmentService

    ai_input = EnrichmentService.build_ai_input(sample_question)
    prompt = EnrichmentService.build_prompt(ai_input)

    assert sample_question.question_text in prompt
    assert f"Option A: {sample_question.option_a}" in prompt
    assert f"Option B: {sample_question.option_b}" in prompt
    assert f"Option C: {sample_question.option_c}" in prompt
    assert f"Option D: {sample_question.option_d}" in prompt
    assert f"Authoritative correct answer: {sample_question.correct_answer} — {sample_question.option_c}" in prompt


def test_prompt_enforces_strict_distractor_analysis_guardrails():
    """Verify prompt strictly requires exactly A, B, C, D and forbids extra keys (E, Explanation)."""
    from app.services.enrichment_service import SYSTEM_PROMPT

    required_rules = [
        "Mandatory 4 Keys: \"A\", \"B\", \"C\", \"D\"",
        "EXACTLY four keys: \"A\", \"B\", \"C\", and \"D\"",
        "NEVER omit any option letter",
        "NEVER add extra keys",
        "Strictly FORBIDDEN keys include \"E\", \"Explanation\"",
    ]
    for rule in required_rules:
        assert rule in SYSTEM_PROMPT, f"Guardrail phrase '{rule}' missing from SYSTEM_PROMPT"


def test_prompt_enforces_strict_verbatim_vocabulary_grounding_guardrails():
    """Verify prompt strictly enforces verbatim vocabulary presence and forbids morphological derivations."""
    from app.services.enrichment_service import SYSTEM_PROMPT

    required_rules = [
        "Strict Verbatim Presence in Question or Options",
        "VERBATIM PRESENCE ONLY",
        "NO DERIVED WORDS OR WORD-FAMILY EXPANSIONS",
        "expand\", you must NOT extract the derived noun \"expansion\"",
        "NO EXTERNAL SYNONYMS",
        "Do NOT use \"phrasal verb\"",
        "NEVER leave trailing commas",
    ]
    for rule in required_rules:
        assert rule in SYSTEM_PROMPT, f"Grounding guardrail phrase '{rule}' missing from SYSTEM_PROMPT"


