import pytest
from pydantic import ValidationError

from app.schemas.enrichment import DistractorAnalysis, QuestionEnrichment, VocabularyItem


@pytest.fixture
def valid_enrichment_data():
    return {
        "grammar_topic": "Verb pattern",
        "sentence_structure": "S + V + O + to V",
        "pattern": "encourage somebody to V",
        "vocabulary": [
            {
                "word": "encourage",
                "meaning": "khuyến khích",
                "part_of_speech": "verb",
            }
        ],
        "explanation": "The verb 'encourage' is followed by an object and 'to + verb'.",
        "distractor_analysis": {
            "A": "Incorrect verb form",
            "B": "Correct answer",
            "C": "Incorrect grammatical structure",
            "D": "Incorrect word form",
        },
        "difficulty": "medium",
    }


def test_valid_enrichment_passes_validation(valid_enrichment_data):
    enrichment = QuestionEnrichment.model_validate(valid_enrichment_data)
    assert enrichment.grammar_topic == "Verb pattern"
    assert enrichment.sentence_structure == "S + V + O + to V"
    assert enrichment.pattern == "encourage somebody to V"
    assert len(enrichment.vocabulary) == 1
    assert isinstance(enrichment.vocabulary[0], VocabularyItem)
    assert enrichment.vocabulary[0].word == "encourage"
    assert enrichment.vocabulary[0].meaning == "khuyến khích"
    assert enrichment.vocabulary[0].part_of_speech == "verb"
    assert isinstance(enrichment.distractor_analysis, DistractorAnalysis)
    assert enrichment.distractor_analysis.A == "Incorrect verb form"
    assert enrichment.distractor_analysis.B == "Correct answer"
    assert enrichment.distractor_analysis.C == "Incorrect grammatical structure"
    assert enrichment.distractor_analysis.D == "Incorrect word form"
    assert enrichment.difficulty == "medium"


@pytest.mark.parametrize("valid_difficulty", ["easy", "medium", "hard"])
def test_valid_difficulty_options(valid_enrichment_data, valid_difficulty):
    valid_enrichment_data["difficulty"] = valid_difficulty
    enrichment = QuestionEnrichment.model_validate(valid_enrichment_data)
    assert enrichment.difficulty == valid_difficulty


def test_invalid_difficulty_fails_validation(valid_enrichment_data):
    valid_enrichment_data["difficulty"] = "very_easy"
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(valid_enrichment_data)

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("difficulty",) for err in errors)


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
def test_missing_required_field_fails_validation(valid_enrichment_data, missing_field):
    data = dict(valid_enrichment_data)
    data.pop(missing_field)
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(data)

    errors = exc_info.value.errors()
    assert any(err["loc"] == (missing_field,) for err in errors)


def test_invalid_vocabulary_item_fails_validation(valid_enrichment_data):
    valid_enrichment_data["vocabulary"] = [
        {"word": "encourage", "part_of_speech": "verb"}  # missing 'meaning'
    ]
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(valid_enrichment_data)

    errors = exc_info.value.errors()
    assert any("vocabulary" in err["loc"] for err in errors)


def test_vocabulary_not_a_list_fails_validation(valid_enrichment_data):
    valid_enrichment_data["vocabulary"] = "not_a_list"
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(valid_enrichment_data)

    errors = exc_info.value.errors()
    assert any(err["loc"] == ("vocabulary",) for err in errors)


@pytest.mark.parametrize("missing_option", ["A", "B", "C", "D"])
def test_missing_distractor_option_fails_validation(valid_enrichment_data, missing_option):
    distractor_data = dict(valid_enrichment_data["distractor_analysis"])
    distractor_data.pop(missing_option)
    valid_enrichment_data["distractor_analysis"] = distractor_data

    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(valid_enrichment_data)

    errors = exc_info.value.errors()
    assert any(
        err["loc"] == ("distractor_analysis", missing_option) for err in errors
    )


def test_empty_vocabulary_list_fails_validation(valid_enrichment_data):
    """Enforce contract rule that vocabulary must contain at least 1 item."""
    valid_enrichment_data["vocabulary"] = []
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(valid_enrichment_data)

    errors = exc_info.value.errors()
    assert any("vocabulary" in err["loc"] for err in errors)


@pytest.mark.parametrize("option_key", ["A", "B", "C", "D"])
def test_empty_distractor_string_fails_validation(valid_enrichment_data, option_key):
    """Enforce that all 4 distractor options must be non-empty strings."""
    distractor_data = dict(valid_enrichment_data["distractor_analysis"])
    distractor_data[option_key] = ""
    valid_enrichment_data["distractor_analysis"] = distractor_data

    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(valid_enrichment_data)

    errors = exc_info.value.errors()
    assert any(
        err["loc"] == ("distractor_analysis", option_key) for err in errors
    )


def test_reading_question_requires_all_four_options_and_valid_answer():
    """Verify QuestionItem enforces 4 non-empty options and valid correct_answer for Reading scope."""
    from app.schemas.question import QuestionItem

    valid_question_payload = {
        "test_id": "ETS2026",
        "part": 5,
        "question_no": 101,
        "question_text": "Sample text ______ here.",
        "option_a": "choice A",
        "option_b": "choice B",
        "option_c": "choice C",
        "option_d": "choice D",
        "correct_answer": "B",
    }
    q = QuestionItem.model_validate(valid_question_payload)
    assert q.option_d == "choice D"
    assert q.correct_answer == "B"

    # Missing option_d
    missing_d = dict(valid_question_payload)
    missing_d.pop("option_d")
    with pytest.raises(ValidationError):
        QuestionItem.model_validate(missing_d)

    # Empty option_d
    empty_d = dict(valid_question_payload)
    empty_d["option_d"] = ""
    with pytest.raises(ValidationError):
        QuestionItem.model_validate(empty_d)

    # Invalid correct_answer
    invalid_ans = dict(valid_question_payload)
    invalid_ans["correct_answer"] = "E"
    with pytest.raises(ValidationError):
        QuestionItem.model_validate(invalid_ans)


# ---------------------------------------------------------------------------
# Strict Schema Enforcement Regression Tests (Task 1)
# ---------------------------------------------------------------------------


def test_extra_root_field_fails_validation(valid_enrichment_data):
    """Enforce contract rule that unexpected root fields are forbidden."""
    data = dict(valid_enrichment_data)
    data["extra_unexpected_field"] = "hallucinated_value"
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(data)

    errors = exc_info.value.errors()
    assert any(
        err["type"] == "extra_forbidden" and err["loc"] == ("extra_unexpected_field",)
        for err in errors
    )


def test_q119_style_extra_distractor_key_e_fails_validation(valid_enrichment_data):
    """Q119 reproduction: extra key 'E' in distractor_analysis must be strictly rejected."""
    data = dict(valid_enrichment_data)
    distractors = dict(data["distractor_analysis"])
    distractors["E"] = "Extra distractor option E explanation"
    data["distractor_analysis"] = distractors

    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(data)

    errors = exc_info.value.errors()
    assert any(
        err["type"] == "extra_forbidden"
        and err["loc"] == ("distractor_analysis", "E")
        for err in errors
    )


def test_q127_style_extra_distractor_key_explanation_fails_validation(valid_enrichment_data):
    """Q127 reproduction: extra key 'Explanation' in distractor_analysis must be strictly rejected."""
    data = dict(valid_enrichment_data)
    distractors = dict(data["distractor_analysis"])
    distractors["Explanation"] = "Extraneous summary inside distractor analysis dict"
    data["distractor_analysis"] = distractors

    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(data)

    errors = exc_info.value.errors()
    assert any(
        err["type"] == "extra_forbidden"
        and err["loc"] == ("distractor_analysis", "Explanation")
        for err in errors
    )


def test_extra_vocabulary_item_field_fails_validation(valid_enrichment_data):
    """Enforce contract rule that unexpected fields on VocabularyItem are forbidden."""
    data = dict(valid_enrichment_data)
    data["vocabulary"] = [
        {
            "word": "encourage",
            "meaning": "khuyến khích",
            "part_of_speech": "verb",
            "phonetic": "/ɪnˈkʌr.ɪdʒ/",  # Extra forbidden field
        }
    ]
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(data)

    errors = exc_info.value.errors()
    assert any(
        err["type"] == "extra_forbidden"
        and "phonetic" in err["loc"]
        for err in errors
    )


@pytest.mark.parametrize(
    "pos",
    [
        # 13 legacy approved canonical tags
        "noun",
        "verb",
        "adjective",
        "adverb",
        "preposition",
        "conjunction",
        "pronoun",
        "determiner",
        "auxiliary verb",
        "modal verb",
        "numeral",
        "proper noun",
        "phrase",
        # 3 new approved multiword phrase tags
        "noun phrase",
        "verb phrase",
        "prepositional phrase",
        # Case and whitespace tolerance during parsing
        "  Noun  ",
        "VERB",
        "Preposition",
        "PHRASE",
        "  Noun Phrase  ",
        "VERB PHRASE",
        "Prepositional Phrase",
    ],
)
def test_valid_part_of_speech_accepted(valid_enrichment_data, pos):
    """Verify that all canonical TOEIC Part 5 POS labels are accepted and normalized."""
    data = dict(valid_enrichment_data)
    data["vocabulary"] = [
        {"word": "sample", "meaning": "mẫu", "part_of_speech": pos}
    ]
    enrichment = QuestionEnrichment.model_validate(data)
    assert enrichment.vocabulary[0].part_of_speech == pos.strip().lower()


@pytest.mark.parametrize(
    "invalid_pos",
    [
        "名词",  # Non-English Chinese characters
        "动词",
        "unknown",  # Placeholder
        "N/A",
        "placeholder",
        "nouns",  # Plural variant
        "verbs",
        "n",  # Abbreviation
        "v",
        "n/v",  # Slashed abbreviation
        "noun phrase (NP)",  # Annotated label
        "verb phrase (phrasal)",  # Annotated label
        "random_pos",  # Arbitrary made-up label
        "clause",
        "sentence",
        "",
        "   ",
    ],
)
def test_invalid_part_of_speech_fails_validation(valid_enrichment_data, invalid_pos):
    """Verify that non-canonical or non-English POS labels are rejected."""
    data = dict(valid_enrichment_data)
    data["vocabulary"] = [
        {"word": "sample", "meaning": "mẫu", "part_of_speech": invalid_pos}
    ]
    with pytest.raises(ValidationError) as exc_info:
        QuestionEnrichment.model_validate(data)

    errors = exc_info.value.errors()
    assert any("part_of_speech" in err["loc"] for err in errors)


def test_taxonomy_contract_alignment_all_16_labels():
    """Verify VALID_PARTS_OF_SPEECH contains exactly 16 immutable canonical labels."""
    from app.schemas.enrichment import VALID_PARTS_OF_SPEECH

    expected_16 = {
        "noun",
        "verb",
        "adjective",
        "adverb",
        "preposition",
        "conjunction",
        "pronoun",
        "determiner",
        "auxiliary verb",
        "modal verb",
        "numeral",
        "proper noun",
        "phrase",
        "noun phrase",
        "verb phrase",
        "prepositional phrase",
    }
    assert isinstance(VALID_PARTS_OF_SPEECH, frozenset)
    assert VALID_PARTS_OF_SPEECH == expected_16
    assert len(VALID_PARTS_OF_SPEECH) == 16


def test_vietnamese_diacritics_preserved_in_enrichment_payload(valid_enrichment_data):
    """Verify full Vietnamese diacritics are accepted and preserved across all fields."""
    vietnamese_payload = dict(valid_enrichment_data)
    vietnamese_payload["vocabulary"] = [
        {"word": "media organization", "meaning": "tổ chức truyền thông", "part_of_speech": "noun phrase"},
        {"word": "take place", "meaning": "diễn ra", "part_of_speech": "verb phrase"},
        {"word": "as a result of", "meaning": "do kết quả của", "part_of_speech": "prepositional phrase"},
    ]
    vietnamese_payload["explanation"] = "Giải thích chi tiết: 'take place' là cụm động từ chỉ sự kiện diễn ra tại một thời điểm xác định."
    vietnamese_payload["distractor_analysis"] = {
        "A": "Đáp án A sai ngữ pháp và ngữ nghĩa.",
        "B": "Đáp án B hoàn toàn chính xác theo ngữ cảnh.",
        "C": "Đáp án C không phù hợp với cấu trúc câu.",
        "D": "Đáp án D sai từ loại trong ngữ cảnh này.",
    }

    enrichment = QuestionEnrichment.model_validate(vietnamese_payload)
    assert enrichment.vocabulary[0].meaning == "tổ chức truyền thông"
    assert enrichment.vocabulary[0].part_of_speech == "noun phrase"
    assert enrichment.vocabulary[1].meaning == "diễn ra"
    assert enrichment.vocabulary[1].part_of_speech == "verb phrase"
    assert enrichment.vocabulary[2].meaning == "do kết quả của"
    assert enrichment.vocabulary[2].part_of_speech == "prepositional phrase"
    assert "Giải thích chi tiết" in enrichment.explanation
    assert enrichment.distractor_analysis.B == "Đáp án B hoàn toàn chính xác theo ngữ cảnh."

