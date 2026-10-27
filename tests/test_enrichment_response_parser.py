import json
import pytest
from pydantic import ValidationError

from app.schemas.enrichment import QuestionEnrichment
from app.services.enrichment_response_parser import (
    EnrichmentJSONDecodeError,
    EnrichmentParseError,
    EnrichmentValidationError,
    parse_and_validate_enrichment,
)


@pytest.fixture
def valid_payload_dict():
    return {
        "grammar_topic": "Word Form (Adverb modifying Adjective)",
        "sentence_structure": "S + is + [adverb] + Adj + Prep Phrase",
        "pattern": "be + extremely + adjective",
        "vocabulary": [
            {
                "word": "extremely",
                "meaning": "vô cùng, cực kỳ",
                "part_of_speech": "adverb",
            }
        ],
        "explanation": "Extremely bổ nghĩa cho tính từ important.",
        "distractor_analysis": {
            "A": "Extreme là tính từ, không bổ nghĩa cho tính từ khác.",
            "B": "Extremely là phó từ, bổ nghĩa chính xác.",
            "C": "Extremist là danh từ chỉ người.",
            "D": "Extremity là danh từ.",
        },
        "difficulty": "easy",
    }


@pytest.fixture
def valid_raw_json(valid_payload_dict):
    return json.dumps(valid_payload_dict)


def test_valid_json_returns_question_enrichment(valid_raw_json):
    result = parse_and_validate_enrichment(valid_raw_json)
    assert isinstance(result, QuestionEnrichment)
    assert result.grammar_topic == "Word Form (Adverb modifying Adjective)"
    assert result.difficulty == "easy"
    assert len(result.vocabulary) == 1
    assert result.vocabulary[0].word == "extremely"
    assert result.distractor_analysis.A.startswith("Extreme")
    assert result.distractor_analysis.B.startswith("Extremely")


@pytest.mark.parametrize(
    "invalid_json_str",
    [
        '{"grammar_topic": "Verb Form",',  # truncated JSON
        "{invalid_json}",
        "Not a JSON at all",
        "",  # empty string
        "   ",  # whitespace string
    ],
)
def test_invalid_json_syntax_raises_decode_error(invalid_json_str):
    with pytest.raises(EnrichmentJSONDecodeError) as exc_info:
        parse_and_validate_enrichment(invalid_json_str)

    assert issubclass(EnrichmentJSONDecodeError, EnrichmentParseError)
    assert (
        "Failed to decode JSON" in str(exc_info.value)
        or "empty or not a string" in str(exc_info.value)
    )


@pytest.mark.parametrize(
    "missing_field",
    [
        "grammar_topic",
        "sentence_structure",
        "pattern",
        "vocabulary",
        "explanation",
        "distractor_analysis",
        "difficulty",
    ],
)
def test_missing_required_field_raises_validation_error(
    valid_payload_dict, missing_field
):
    payload = dict(valid_payload_dict)
    payload.pop(missing_field)
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    assert issubclass(EnrichmentValidationError, EnrichmentParseError)
    assert "LLM response failed QuestionEnrichment validation" in str(exc_info.value)


def test_invalid_difficulty_raises_validation_error(valid_payload_dict):
    payload = dict(valid_payload_dict)
    payload["difficulty"] = "very_easy"  # Not allowed
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    assert "difficulty" in str(exc_info.value)


def test_invalid_vocabulary_item_raises_validation_error(valid_payload_dict):
    payload = dict(valid_payload_dict)
    payload["vocabulary"] = [
        {"word": "extremely", "meaning": "vô cùng"}  # missing part_of_speech
    ]
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    assert "vocabulary" in str(exc_info.value)


@pytest.mark.parametrize("missing_option", ["A", "B", "C", "D"])
def test_missing_distractor_option_raises_validation_error(
    valid_payload_dict, missing_option
):
    payload = dict(valid_payload_dict)
    distractors = dict(payload["distractor_analysis"])
    distractors.pop(missing_option)
    payload["distractor_analysis"] = distractors
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    assert "distractor_analysis" in str(exc_info.value)


def test_extra_unexpected_field_raises_validation_error(valid_payload_dict):
    # Under strict QuestionEnrichment with extra='forbid',
    # extra root fields are rejected with EnrichmentValidationError.
    payload = dict(valid_payload_dict)
    payload["unexpected_extra_key"] = "extra_value"
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    err = exc_info.value
    assert err.raw_response == raw_json
    assert err.raw_data == payload
    assert err.validation_error is not None
    assert any("unexpected_extra_key" in str(e["loc"]) for e in err.errors)


def test_q119_extra_distractor_key_e_raises_validation_error(valid_payload_dict):
    payload = dict(valid_payload_dict)
    distractors = dict(payload["distractor_analysis"])
    distractors["E"] = "Extra distractor option"
    payload["distractor_analysis"] = distractors
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    err = exc_info.value
    assert err.raw_response == raw_json
    assert err.raw_data == payload
    assert any(e["loc"] == ("distractor_analysis", "E") for e in err.errors)


def test_q127_extra_distractor_key_explanation_raises_validation_error(valid_payload_dict):
    payload = dict(valid_payload_dict)
    distractors = dict(payload["distractor_analysis"])
    distractors["Explanation"] = "Extra explanation field inside distractor analysis"
    payload["distractor_analysis"] = distractors
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    err = exc_info.value
    assert err.raw_response == raw_json
    assert err.raw_data == payload
    assert any(e["loc"] == ("distractor_analysis", "Explanation") for e in err.errors)


def test_invalid_pos_raises_validation_error(valid_payload_dict):
    payload = dict(valid_payload_dict)
    payload["vocabulary"] = [
        {"word": "test", "meaning": "nghĩa", "part_of_speech": "名词"}
    ]
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    assert "Invalid part of speech" in str(exc_info.value)


@pytest.mark.parametrize(
    "non_object_json",
    [
        "[]",  # empty array
        '[{"grammar_topic": "Test"}]',  # array of objects
        '"just a string"',  # JSON string primitive
        "12345",  # JSON integer primitive
        "true",  # JSON boolean primitive
        "null",  # JSON null
    ],
)
def test_non_object_json_rejected(non_object_json):
    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(non_object_json)

    assert "Expected JSON object (dict)" in str(exc_info.value)


def test_decode_error_preserves_underlying_cause_and_raw_response():
    bad_json = '{"grammar_topic": "incomplete'
    with pytest.raises(EnrichmentJSONDecodeError) as exc_info:
        parse_and_validate_enrichment(bad_json)

    err = exc_info.value
    assert err.raw_response == bad_json
    assert isinstance(err.json_error, json.JSONDecodeError)
    assert err.__cause__ is err.json_error
    assert "Failed to decode JSON" in err.message


def test_validation_error_preserves_underlying_cause_raw_data_and_details(valid_payload_dict):
    payload = dict(valid_payload_dict)
    payload.pop("grammar_topic")  # missing required field
    raw_json = json.dumps(payload)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        parse_and_validate_enrichment(raw_json)

    err = exc_info.value
    assert err.raw_response == raw_json
    assert err.raw_data == payload
    assert err.validation_error is not None
    assert err.__cause__ is err.validation_error
    assert isinstance(err.errors, list)
    assert len(err.errors) > 0
    assert any(e["loc"] == ("grammar_topic",) for e in err.errors)


def test_sanitize_json_text_markdown_code_fences():
    from app.services.enrichment_response_parser import sanitize_json_text

    raw = """Here is your analysis:
```json
{
  "test_key": "test_val"
}
```
Thank you!"""
    cleaned = sanitize_json_text(raw)
    parsed = json.loads(cleaned)
    assert parsed == {"test_key": "test_val"}


def test_sanitize_json_text_trailing_commas_and_preserves_internal_commas():
    from app.services.enrichment_response_parser import sanitize_json_text

    raw = """{
      "key": "value, with internal, commas",
      "items": [1, 2, 3, ],
      "nested": {
         "a": 1,
         "b": 2,
      },
    }"""
    cleaned = sanitize_json_text(raw)
    parsed = json.loads(cleaned)
    assert parsed["key"] == "value, with internal, commas"
    assert parsed["items"] == [1, 2, 3]
    assert parsed["nested"] == {"a": 1, "b": 2}


def test_parse_and_validate_enrichment_recovers_from_trailing_comma(valid_payload_dict):
    # Inject trailing commas into the serialized JSON
    raw_with_trailing_comma = f"""{{
        "grammar_topic": "{valid_payload_dict['grammar_topic']}",
        "sentence_structure": "{valid_payload_dict['sentence_structure']}",
        "pattern": "{valid_payload_dict['pattern']}",
        "vocabulary": [
            {{
                "word": "extremely",
                "meaning": "vô cùng",
                "part_of_speech": "adverb",
            }},
        ],
        "explanation": "{valid_payload_dict['explanation']}",
        "distractor_analysis": {{
            "A": "{valid_payload_dict['distractor_analysis']['A']}",
            "B": "{valid_payload_dict['distractor_analysis']['B']}",
            "C": "{valid_payload_dict['distractor_analysis']['C']}",
            "D": "{valid_payload_dict['distractor_analysis']['D']}",
        }},
        "difficulty": "easy",
    }}"""

    result = parse_and_validate_enrichment(raw_with_trailing_comma)
    assert isinstance(result, QuestionEnrichment)
    assert result.grammar_topic == valid_payload_dict["grammar_topic"]
    assert result.distractor_analysis.D == valid_payload_dict["distractor_analysis"]["D"]


def test_parse_and_validate_enrichment_recovers_from_markdown_fences_with_prose(valid_payload_dict):
    raw_fenced = f"""Certainly! Below is the requested JSON profile:

```json
{json.dumps(valid_payload_dict, indent=2)}
```

Hope this helps your TOEIC preparation!"""

    result = parse_and_validate_enrichment(raw_fenced)
    assert isinstance(result, QuestionEnrichment)
    assert result.grammar_topic == valid_payload_dict["grammar_topic"]


def test_normalize_enrichment_dict_remaps_single_unrecognized_distractor_key(valid_payload_dict):
    from app.services.enrichment_response_parser import normalize_enrichment_dict

    # Suppose key 'D' was mistakenly labeled with the choice text 'Whoever'
    payload = dict(valid_payload_dict)
    dist = dict(payload["distractor_analysis"])
    d_val = dist.pop("D")
    dist["Whoever"] = d_val
    payload["distractor_analysis"] = dist

    normalized = normalize_enrichment_dict(payload)
    assert "Whoever" not in normalized["distractor_analysis"]
    assert "D" in normalized["distractor_analysis"]
    assert normalized["distractor_analysis"]["D"] == d_val

    # Ensure it validates cleanly via QuestionEnrichment
    enr = QuestionEnrichment.model_validate(normalized)
    assert enr.distractor_analysis.D == d_val


def test_normalize_enrichment_dict_preserves_extra_keys_beyond_four(valid_payload_dict):
    from app.services.enrichment_response_parser import normalize_enrichment_dict

    # Extra key 'E' should NOT be masked or dropped
    payload = dict(valid_payload_dict)
    dist = dict(payload["distractor_analysis"])
    dist["E"] = "Extra distractor explanation"
    payload["distractor_analysis"] = dist

    normalized = normalize_enrichment_dict(payload)
    assert "E" in normalized["distractor_analysis"]
    with pytest.raises(ValidationError):
        QuestionEnrichment.model_validate(normalized)


def test_normalize_enrichment_dict_remaps_pos_name_as_key_in_vocabulary(valid_payload_dict):
    from app.services.enrichment_response_parser import normalize_enrichment_dict

    payload = dict(valid_payload_dict)
    payload["vocabulary"] = [
        {"word": "training", "meaning": "đào tạo", "noun": "training"},
        {"word": "increase", "meaning": "tăng lên", "verb": "increase"},
    ]

    normalized = normalize_enrichment_dict(payload)
    assert normalized["vocabulary"][0]["part_of_speech"] == "noun"
    assert "noun" not in normalized["vocabulary"][0]
    assert normalized["vocabulary"][1]["part_of_speech"] == "verb"
    assert "verb" not in normalized["vocabulary"][1]

    enr = QuestionEnrichment.model_validate(normalized)
    assert enr.vocabulary[0].part_of_speech == "noun"
    assert enr.vocabulary[1].part_of_speech == "verb"


def test_normalize_enrichment_dict_drops_redundant_metadata_keys(valid_payload_dict):
    from app.services.enrichment_response_parser import normalize_enrichment_dict

    payload = dict(valid_payload_dict)
    payload["vocabulary"] = [
        {"word": "finance", "meaning": "tài chính", "name": "noun", "part_of_speech": "noun"}
    ]

    normalized = normalize_enrichment_dict(payload)
    assert "name" not in normalized["vocabulary"][0]
    assert normalized["vocabulary"][0]["part_of_speech"] == "noun"

    enr = QuestionEnrichment.model_validate(normalized)
    assert enr.vocabulary[0].part_of_speech == "noun"


def test_normalize_enrichment_dict_relocates_misplaced_top_level_keys(valid_payload_dict):
    from app.services.enrichment_response_parser import normalize_enrichment_dict

    payload = dict(valid_payload_dict)
    # Simulate LLM mistakenly putting 'difficulty' inside 'distractor_analysis'
    payload.pop("difficulty")
    payload["distractor_analysis"]["difficulty"] = "easy"

    normalized = normalize_enrichment_dict(payload)
    assert "difficulty" not in normalized["distractor_analysis"]
    assert normalized["difficulty"] == "easy"
    assert set(normalized["distractor_analysis"].keys()) == {"A", "B", "C", "D"}

    enr = QuestionEnrichment.model_validate(normalized)
    assert enr.difficulty == "easy"



