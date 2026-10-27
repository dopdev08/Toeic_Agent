import json
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.schemas.enrichment import DistractorAnalysis, QuestionEnrichment, VocabularyItem
from app.services.enrichment_response_parser import EnrichmentJSONDecodeError
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_validator import (
    EnrichmentContradictionError,
    EnrichmentGroundingError,
    EnrichmentMissingDistractorError,
    EnrichmentQualityError,
    EnrichmentScriptLeakageError,
    EnrichmentValidator,
    QualityValidationStatus,
)
from app.services.enrichment_workflow import EnrichmentWorkflow
from app.services.batch_enrichment_workflow import BatchEnrichmentWorkflow


@pytest.fixture
def db_session():
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = testing_session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        test_engine.dispose()


@pytest.fixture
def example_question():
    return Question(
        id=201,
        test_id="TEST_ETS",
        part=5,
        question_no=101,
        question_text="The lecture will take place at 6:00 P.M., _____ which attendees may ask questions.",
        option_a="across",
        option_b="after",
        option_c="inside",
        option_d="among",
        correct_answer="B",
        explanation="Authoritative reference explanation.",
    )


@pytest.fixture
def valid_enrichment_for_example():
    return QuestionEnrichment(
        grammar_topic="Preposition + Relative Pronoun",
        sentence_structure="S + V + at [Time], [Prep] + which + S + V",
        pattern="preposition + which + clause",
        vocabulary=[
            VocabularyItem(word="lecture", meaning="bài giảng", part_of_speech="noun"),
            VocabularyItem(word="take place", meaning="diễn ra", part_of_speech="phrase"),
            VocabularyItem(word="after", meaning="sau khi", part_of_speech="preposition"),
        ],
        explanation="Đáp án B là đáp án chính xác vì 'after which' tạo thành mệnh đề quan hệ chỉ thời gian.",
        distractor_analysis=DistractorAnalysis(
            A="Sai vì 'across' chỉ vị trí không gian, không dùng chỉ mốc thời gian.",
            B="Đúng vì 'after which' diễn tả thời điểm sau bài giảng khi người tham dự có thể đặt câu hỏi.",
            C="Sai vì 'inside' dùng cho không gian khép kín, không hợp ngữ cảnh.",
            D="Sai vì 'among' dùng cho số nhiều giữa nhiều đối tượng.",
        ),
        difficulty="medium",
    )


# ---------------------------------------------------------------------------
# Point 1: Vocabulary present in the question
# ---------------------------------------------------------------------------
def test_vocabulary_present_in_question_passes(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()
    # "lecture" and "attendees" are in question_text
    valid_enrichment_for_example.vocabulary = [
        VocabularyItem(word="lecture", meaning="bài giảng", part_of_speech="noun"),
        VocabularyItem(word="attendees", meaning="người tham dự", part_of_speech="noun"),
    ]
    result = validator.validate(example_question, valid_enrichment_for_example)
    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID
    assert result.errors == []


# ---------------------------------------------------------------------------
# Point 2: Vocabulary present in an option
# ---------------------------------------------------------------------------
def test_vocabulary_present_in_option_passes(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()
    # "across" is in option_a, "after" is in option_b, "inside" is in option_c
    valid_enrichment_for_example.vocabulary = [
        VocabularyItem(word="across", meaning="băng qua", part_of_speech="preposition"),
        VocabularyItem(word="inside", meaning="bên trong", part_of_speech="preposition"),
    ]
    result = validator.validate(example_question, valid_enrichment_for_example)
    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID
    assert result.errors == []


# ---------------------------------------------------------------------------
# Point 3: Vocabulary absent from all source text
# ---------------------------------------------------------------------------
def test_vocabulary_absent_from_all_source_text_fails(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()
    valid_enrichment_for_example.vocabulary = [
        VocabularyItem(word="banana", meaning="quả chuối", part_of_speech="noun"),
    ]
    result = validator.validate(example_question, valid_enrichment_for_example)
    assert result.is_valid is False
    assert result.status == QualityValidationStatus.REJECTED
    assert result.error_code == "UNGROUNDED_VOCABULARY"
    assert any("banana" in err for err in result.errors)

    with pytest.raises(EnrichmentGroundingError) as exc_info:
        validator.validate_and_raise(example_question, valid_enrichment_for_example)
    assert "banana" in str(exc_info.value)


def test_vocabulary_subsequence_of_unrelated_word_is_rejected():
    validator = EnrichmentValidator()
    question = Question(
        question_text="The company relocated to provide detailed information and effective management.",
        option_a="first",
        option_b="second",
        option_c="third",
        option_d="fourth",
        correct_answer="A",
    )
    # "cat" is inside "relocated", "for" is inside "information", "age" is inside "management"
    enrichment = QuestionEnrichment(
        grammar_topic="Topic",
        sentence_structure="SVO",
        pattern="Pattern",
        vocabulary=[
            VocabularyItem(word="cat", meaning="mèo", part_of_speech="noun"),
            VocabularyItem(word="for", meaning="cho", part_of_speech="preposition"),
            VocabularyItem(word="age", meaning="tuổi", part_of_speech="noun"),
        ],
        explanation="Exp",
        distractor_analysis=DistractorAnalysis(A="Đúng", B="Sai", C="Sai", D="Sai"),
        difficulty="easy",
    )
    result = validator.validate(question, enrichment)
    assert result.is_valid is False
    assert result.status == QualityValidationStatus.REJECTED
    assert result.error_code == "UNGROUNDED_VOCABULARY"
    assert len(result.errors) == 3
    assert any("cat" in err for err in result.errors)
    assert any("for" in err for err in result.errors)
    assert any("age" in err for err in result.errors)


def test_tightened_vocabulary_grounding_edge_cases():
    """Regression test for Phase 3.3.12.2B.2.2A.2:

    1. 'car' must not match 'carpet'.
    2. 'act' must not match 'active'.
    3. 'for' must not match 'information'.
    4. 'attendee' may match 'attendees'.
    5. 'request' may match 'requested'.
    6. Grounded multiword phrase with punctuation or repeated whitespace is accepted.
    """
    validator = EnrichmentValidator()

    # Negative edge cases: prefix or sub-sequence of an unrelated token must be rejected
    source_carpet = "The new red carpet was delivered."
    normalized_carpet = validator.normalize_text_for_grounding(source_carpet)
    assert validator.is_word_grounded("car", normalized_carpet) is False

    source_active = "She has been an active participant in all sessions."
    normalized_active = validator.normalize_text_for_grounding(source_active)
    assert validator.is_word_grounded("act", normalized_active) is False

    source_info = "The detailed information was kept confidential."
    normalized_info = validator.normalize_text_for_grounding(source_info)
    assert validator.is_word_grounded("for", normalized_info) is False

    # Positive inflection cases: regular inflections accepted unambiguously
    source_attendees = "All attendees may submit questions in writing."
    normalized_attendees = validator.normalize_text_for_grounding(source_attendees)
    assert validator.is_word_grounded("attendee", normalized_attendees) is True

    source_requested = "The manager requested that revisions be made."
    normalized_requested = validator.normalize_text_for_grounding(source_requested)
    assert validator.is_word_grounded("request", normalized_requested) is True

    # Positive multiword phrase cases: punctuation and repeated whitespace handled cleanly
    source_multiword = "The meeting will take place at 6:00 P.M., prior to the dinner."
    normalized_multiword = validator.normalize_text_for_grounding(source_multiword)
    assert validator.is_word_grounded("  take   place  ", normalized_multiword) is True
    assert validator.is_word_grounded("6:00 P.M.", normalized_multiword) is True
    assert validator.is_word_grounded("prior   to", normalized_multiword) is True



# ---------------------------------------------------------------------------
# Point 4: Case and whitespace normalization
# ---------------------------------------------------------------------------
def test_vocabulary_case_and_whitespace_normalization(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()
    valid_enrichment_for_example.vocabulary = [
        VocabularyItem(word="  LECTURE  ", meaning="bài giảng", part_of_speech="noun"),
        VocabularyItem(word="take   place", meaning="diễn ra", part_of_speech="phrase"),
        VocabularyItem(word="6:00 P.M.", meaning="6 giờ chiều", part_of_speech="phrase"),
    ]
    result = validator.validate(example_question, valid_enrichment_for_example)
    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID


# ---------------------------------------------------------------------------
# Point 5: Correct-answer analysis containing an explicitly supported contradiction pattern
# ---------------------------------------------------------------------------
def test_option_unsuitability_contradiction_pattern_flagged(example_question, valid_enrichment_for_example):
    """Verifies that an option unsuitability contradiction pattern is detected."""
    validator = EnrichmentValidator()
    # Contradictory output for option B:
    valid_enrichment_for_example.distractor_analysis.B = (
        'after - không phù hợp với ngữ cảnh của câu. "After" không phù hợp với việc diễn tả thời điểm cụ thể như 6:00 P.M.'
    )
    result = validator.validate(example_question, valid_enrichment_for_example)
    assert result.is_valid is False
    assert result.status == QualityValidationStatus.SUSPICIOUS
    assert result.error_code == "CORRECT_ANSWER_CONTRADICTION"

    with pytest.raises(EnrichmentContradictionError):
        validator.validate_and_raise(example_question, valid_enrichment_for_example)


def test_leading_negative_judgment_on_correct_answer_flagged(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()
    valid_enrichment_for_example.distractor_analysis.B = "Sai vì 'after' là giới từ chỉ thời gian nhưng mệnh đề sau không tương thích."
    result = validator.validate(example_question, valid_enrichment_for_example)
    assert result.is_valid is False
    assert result.status == QualityValidationStatus.SUSPICIOUS
    assert result.error_code == "CORRECT_ANSWER_CONTRADICTION"


def test_english_negative_judgment_on_correct_answer_flagged(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()
    valid_enrichment_for_example.distractor_analysis.B = "Option B is incorrect because 'after' cannot modify this clause."
    result = validator.validate(example_question, valid_enrichment_for_example)
    assert result.is_valid is False
    assert result.status == QualityValidationStatus.SUSPICIOUS
    assert result.error_code == "CORRECT_ANSWER_CONTRADICTION"


# ---------------------------------------------------------------------------
# Point 6: Legitimate wording that should not trigger the contradiction rule
# ---------------------------------------------------------------------------
def test_legitimate_explanations_do_not_trigger_contradiction(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()

    legitimate_cases = [
        "Đúng vì 'after which' tạo thành mệnh đề quan hệ chỉ thời gian, các đáp án khác không phù hợp với ngữ cảnh.",
        "Đáp án B chính xác vì cụm 'after which' là thành phần không thể thiếu trong cấu trúc câu này.",
        "Không giống như các đáp án khác, 'after' tạo nên cụm từ chỉ thời gian hoàn chỉnh và chính xác.",
        "Option B is correct because 'after which' functions as a relative phrase. Other choices are not suitable.",
    ]

    for explanation in legitimate_cases:
        valid_enrichment_for_example.distractor_analysis.B = explanation
        result = validator.validate(example_question, valid_enrichment_for_example)
        assert result.is_valid is True, f"Failed for legitimate explanation: {explanation}"
        assert result.status == QualityValidationStatus.VALID


# ---------------------------------------------------------------------------
# Point 7: Validation failure prevents persistence
# ---------------------------------------------------------------------------
def test_validation_failure_prevents_persistence(db_session, example_question, valid_enrichment_for_example):
    db_session.add(example_question)
    db_session.commit()
    db_session.refresh(example_question)

    # Invalidate with ungrounded vocabulary
    valid_enrichment_for_example.vocabulary = [
        VocabularyItem(word="hallucinated_word", meaning="không có", part_of_speech="noun")
    ]

    fake_service = MagicMock(spec=EnrichmentService)
    fake_service.enrich_question.return_value = valid_enrichment_for_example

    workflow = EnrichmentWorkflow(enrichment_service=fake_service)

    with pytest.raises(EnrichmentQualityError):
        workflow.execute(session=db_session, question=example_question)

    # Verify no enrichment was saved in DB
    saved = db_session.query(QuestionEnrichmentModel).filter_by(question_id=example_question.id).first()
    assert saved is None


# ---------------------------------------------------------------------------
# Point 8: Transaction rollback behavior on failure
# ---------------------------------------------------------------------------
def test_transaction_rollback_behavior_on_quality_failure(db_session, example_question, valid_enrichment_for_example):
    db_session.add(example_question)
    db_session.commit()
    db_session.refresh(example_question)

    # Make distractor analysis contradictory
    valid_enrichment_for_example.distractor_analysis.B = "B - không phù hợp với cấu trúc câu."

    fake_service = MagicMock(spec=EnrichmentService)
    fake_service.enrich_question.return_value = valid_enrichment_for_example

    workflow = EnrichmentWorkflow(enrichment_service=fake_service)

    with pytest.raises(EnrichmentContradictionError):
        workflow.execute(session=db_session, question=example_question)

    # Session is cleanly rolled back and usable for subsequent queries
    assert db_session.is_active
    persisted_count = db_session.query(QuestionEnrichmentModel).count()
    assert persisted_count == 0


# ---------------------------------------------------------------------------
# Point 9: Batch processing continues after one item fails validation
# ---------------------------------------------------------------------------
def test_batch_processing_continues_after_one_item_fails_validation(db_session):
    q1 = Question(
        test_id="BATCH_V",
        part=5,
        question_no=1,
        question_text="Q1 text ______ here.",
        option_a="one",
        option_b="two",
        option_c="three",
        option_d="four",
        correct_answer="A",
    )
    q2 = Question(
        test_id="BATCH_V",
        part=5,
        question_no=2,
        question_text="Q2 text ______ here.",
        option_a="alpha",
        option_b="beta",
        option_c="gamma",
        option_d="delta",
        correct_answer="B",
    )
    q3 = Question(
        test_id="BATCH_V",
        part=5,
        question_no=3,
        question_text="Q3 text ______ here.",
        option_a="apple",
        option_b="banana",
        option_c="cherry",
        option_d="date",
        correct_answer="C",
    )
    db_session.add_all([q1, q2, q3])
    db_session.commit()
    for q in (q1, q2, q3):
        db_session.refresh(q)

    def side_effect(question):
        if question.id == q2.id:
            # Ungrounded vocabulary for Q2
            return QuestionEnrichment(
                grammar_topic="Topic 2",
                sentence_structure="SVO",
                pattern="Pattern",
                vocabulary=[VocabularyItem(word="unrelated", meaning="m", part_of_speech="noun")],
                explanation="Explanation",
                distractor_analysis=DistractorAnalysis(A="Sai", B="Đúng", C="Sai", D="Sai"),
                difficulty="easy",
            )
        elif question.id == q1.id:
            return QuestionEnrichment(
                grammar_topic="Topic 1",
                sentence_structure="SVO",
                pattern="Pattern",
                vocabulary=[VocabularyItem(word="one", meaning="m", part_of_speech="noun")],
                explanation="Explanation",
                distractor_analysis=DistractorAnalysis(A="Đúng", B="Sai", C="Sai", D="Sai"),
                difficulty="easy",
            )
        else:
            return QuestionEnrichment(
                grammar_topic="Topic 3",
                sentence_structure="SVO",
                pattern="Pattern",
                vocabulary=[VocabularyItem(word="cherry", meaning="m", part_of_speech="noun")],
                explanation="Explanation",
                distractor_analysis=DistractorAnalysis(A="Sai", B="Sai", C="Đúng", D="Sai"),
                difficulty="easy",
            )

    fake_service = MagicMock(spec=EnrichmentService)
    fake_service.enrich_question.side_effect = side_effect

    inner_workflow = EnrichmentWorkflow(enrichment_service=fake_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    result = batch_workflow.execute(session=db_session, items=[q1.id, q2.id, q3.id])

    assert result.total == 3
    assert result.success == 2
    assert result.failed == 1

    # Verify per-item status
    assert result.results[0].status == "COMPLETED"
    assert result.results[1].status == "FAILED"
    assert "Ungrounded vocabulary" in result.results[1].error
    assert result.results[2].status == "COMPLETED"


# ---------------------------------------------------------------------------
# Point 10: A valid batch item persists while a rejected item does not
# ---------------------------------------------------------------------------
def test_valid_batch_item_persists_while_rejected_item_does_not(db_session):
    q1 = Question(
        test_id="BATCH_V2",
        part=5,
        question_no=11,
        question_text="Q11 text ______ here.",
        option_a="first",
        option_b="second",
        option_c="third",
        option_d="fourth",
        correct_answer="A",
    )
    q2 = Question(
        test_id="BATCH_V2",
        part=5,
        question_no=12,
        question_text="Q12 text ______ here.",
        option_a="north",
        option_b="south",
        option_c="east",
        option_d="west",
        correct_answer="B",
    )
    db_session.add_all([q1, q2])
    db_session.commit()
    db_session.refresh(q1)
    db_session.refresh(q2)

    def side_effect(question):
        if question.id == q1.id:
            return QuestionEnrichment(
                grammar_topic="Topic 11",
                sentence_structure="SVO",
                pattern="Pattern",
                vocabulary=[VocabularyItem(word="first", meaning="m", part_of_speech="noun")],
                explanation="Explanation",
                distractor_analysis=DistractorAnalysis(A="Đúng", B="Sai", C="Sai", D="Sai"),
                difficulty="easy",
            )
        else:
            # Contradictory distractor for Q2
            return QuestionEnrichment(
                grammar_topic="Topic 12",
                sentence_structure="SVO",
                pattern="Pattern",
                vocabulary=[VocabularyItem(word="south", meaning="m", part_of_speech="noun")],
                explanation="Explanation",
                distractor_analysis=DistractorAnalysis(
                    A="Sai",
                    B="south - không phù hợp với ngữ cảnh câu.",
                    C="Sai",
                    D="Sai",
                ),
                difficulty="easy",
            )

    fake_service = MagicMock(spec=EnrichmentService)
    fake_service.enrich_question.side_effect = side_effect

    inner_workflow = EnrichmentWorkflow(enrichment_service=fake_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    batch_workflow.execute(session=db_session, items=[q1.id, q2.id])

    # Q1 enrichment must exist in DB
    e1 = db_session.query(QuestionEnrichmentModel).filter_by(question_id=q1.id).first()
    assert e1 is not None
    assert e1.grammar_topic == "Topic 11"

    # Q2 enrichment must NOT exist in DB
    e2 = db_session.query(QuestionEnrichmentModel).filter_by(question_id=q2.id).first()
    assert e2 is None


# ---------------------------------------------------------------------------
# Point 11: The authoritative answer in Question Bank remains unchanged
# ---------------------------------------------------------------------------
def test_authoritative_answer_in_question_bank_remains_unchanged(example_question, valid_enrichment_for_example):
    validator = EnrichmentValidator()
    assert example_question.correct_answer == "B"

    # Run on valid
    validator.validate(example_question, valid_enrichment_for_example)
    assert example_question.correct_answer == "B"

    # Run on invalid
    valid_enrichment_for_example.vocabulary = [VocabularyItem(word="missing", meaning="m", part_of_speech="noun")]
    validator.validate(example_question, valid_enrichment_for_example)
    assert example_question.correct_answer == "B"


# ---------------------------------------------------------------------------
# Point 12: Existing malformed-JSON behavior still prevents persistence
# ---------------------------------------------------------------------------
def test_malformed_json_still_prevents_persistence(db_session, example_question):
    db_session.add(example_question)
    db_session.commit()
    db_session.refresh(example_question)

    fake_service = MagicMock(spec=EnrichmentService)
    fake_service.enrich_question.side_effect = EnrichmentJSONDecodeError("Expecting ',' delimiter")

    workflow = EnrichmentWorkflow(enrichment_service=fake_service)

    with pytest.raises(EnrichmentJSONDecodeError):
        workflow.execute(session=db_session, question=example_question)

    # Nothing persisted
    saved = db_session.query(QuestionEnrichmentModel).filter_by(question_id=example_question.id).first()
    assert saved is None


# ---------------------------------------------------------------------------
# Regression tests for Issue B — Vocabulary grounding inflections & completed sentence
# ---------------------------------------------------------------------------

def test_vocabulary_grounding_multiword_inflections_q105_computer_virus():
    """Q105: 'computer virus' correctly matches 'computer viruses' in question text."""
    validator = EnrichmentValidator()
    source = "Employees must report any suspicious emails to prevent the spread of computer viruses."
    norm_source = validator.normalize_text_for_grounding(source)
    assert validator.is_word_grounded("computer virus", norm_source) is True


def test_vocabulary_grounding_multiword_inflections_q110_cash_register():
    """Q110: 'cash register' correctly matches 'cash registers' in question text."""
    validator = EnrichmentValidator()
    source = "The new store installed five computerized cash registers to streamline checkout."
    norm_source = validator.normalize_text_for_grounding(source)
    assert validator.is_word_grounded("cash register", norm_source) is True


def test_vocabulary_grounding_multiword_inflections_q115_rain_garden():
    """Q115: 'rain garden' correctly matches 'Rain gardens' in question text."""
    validator = EnrichmentValidator()
    source = "Rain gardens help reduce stormwater runoff and improve water quality in urban areas."
    norm_source = validator.normalize_text_for_grounding(source)
    assert validator.is_word_grounded("rain garden", norm_source) is True


def test_vocabulary_grounding_multiword_inflections_q116_manufacturing_system():
    """Q116: 'manufacturing system' correctly matches 'manufacturing systems' in question text."""
    validator = EnrichmentValidator()
    source = "Upgrades to our automated manufacturing systems significantly increased output."
    norm_source = validator.normalize_text_for_grounding(source)
    assert validator.is_word_grounded("manufacturing system", norm_source) is True


def test_vocabulary_grounding_completed_sentence_q108_product_line():
    """Q108: 'product line' is accepted when 'line' is official answer and sentence has 'product _____ '."""
    validator = EnrichmentValidator()
    q108 = {
        "question_text": "Tarateer Pharmaceuticals is varying its product _____ to include over-the-counter medications.",
        "option_a": "to line",
        "option_b": "lining",
        "option_c": "lined",
        "option_d": "line",
        "correct_answer": "D",
    }
    norm_source = validator.extract_source_text(q108)
    assert validator.is_word_grounded("product line", norm_source) is True


def test_vocabulary_grounding_unrelated_phrase_rejected():
    """Phrases not appearing in question, options, or completed sentence must be rejected."""
    validator = EnrichmentValidator()
    q = {
        "question_text": "The lecture will take place at 6:00 P.M., _____ which attendees may ask questions.",
        "option_a": "across",
        "option_b": "after",
        "option_c": "inside",
        "option_d": "among",
        "correct_answer": "B",
    }
    norm_source = validator.extract_source_text(q)
    assert validator.is_word_grounded("unrelated hallucinated phrase", norm_source) is False


def test_vocabulary_grounding_boundary_no_false_positives():
    """Word boundary matching prevents partial token false positives."""
    validator = EnrichmentValidator()
    source = "The red carpet was installed by an active team with detailed information."
    norm_source = validator.normalize_text_for_grounding(source)

    assert validator.is_word_grounded("car", norm_source) is False
    assert validator.is_word_grounded("act", norm_source) is False
    assert validator.is_word_grounded("for", norm_source) is False


def test_vocabulary_grounding_speculative_incorrect_answer_not_used():
    """Grounding must NOT form completed sentence using incorrect options."""
    validator = EnrichmentValidator()
    q108 = {
        "question_text": "Tarateer Pharmaceuticals is varying its product _____ to include over-the-counter medications.",
        "option_a": "to line",
        "option_b": "lining",
        "option_c": "lined",
        "option_d": "line",
        "correct_answer": "D",
    }
    norm_source = validator.extract_source_text(q108)
    # Option A 'to line' was NOT the correct answer, so 'product to line' was not created in completed sentence
    assert validator.is_word_grounded("product to line", norm_source) is False


def test_validator_full_validation_q105_and_q108_accepted(example_question):
    """Full EnrichmentValidator.validate() accepts Q105 and Q108 enrichments with multiword inflections and collocations."""
    validator = EnrichmentValidator()

    # Q105 simulation
    q105 = Question(
        id=105,
        test_id="ETS2026",
        part=5,
        question_no=105,
        question_text="Security protocols help prevent the spread of computer viruses across the corporate network.",
        option_a="rapidly",
        option_b="rapid",
        option_c="rapidity",
        option_d="rapids",
        correct_answer="A",
    )
    enrichment_105 = QuestionEnrichment(
        grammar_topic="Adverbs of Manner",
        sentence_structure="S + V + O + Adv",
        pattern="prevent + spread + adverb",
        vocabulary=[
            VocabularyItem(word="computer virus", meaning="vi-rút máy tính", part_of_speech="noun"),
            VocabularyItem(word="spread", meaning="sự lây lan", part_of_speech="noun"),
        ],
        explanation="Đáp án A (rapidly) là trạng từ bổ nghĩa cho động từ/cụm vị ngữ.",
        distractor_analysis=DistractorAnalysis(
            A="Đáp án A (rapidly) đúng vì cần một trạng từ bổ nghĩa.",
            B="Đáp án B (rapid) là tính từ, không phù hợp bổ nghĩa cho hành động.",
            C="Đáp án C (rapidity) là danh từ, sai vị trí ngữ pháp.",
            D="Đáp án D (rapids) là danh từ số nhiều, không đúng ngữ cảnh.",
        ),
        difficulty="medium",
    )
    res_105 = validator.validate(q105, enrichment_105)
    assert res_105.is_valid is True
    assert res_105.status == QualityValidationStatus.VALID

    # Q108 simulation
    q108 = Question(
        id=108,
        test_id="ETS2026",
        part=5,
        question_no=108,
        question_text="Tarateer Pharmaceuticals is varying its product _____ to include over-the-counter medications.",
        option_a="to line",
        option_b="lining",
        option_c="lined",
        option_d="line",
        correct_answer="D",
    )
    enrichment_108 = QuestionEnrichment(
        grammar_topic="Compound Noun",
        sentence_structure="S + V + its + Compound Noun (product + line)",
        pattern="product line",
        vocabulary=[
            VocabularyItem(word="product line", meaning="dòng sản phẩm", part_of_speech="noun"),
            VocabularyItem(word="vary", meaning="đa dạng hóa", part_of_speech="verb"),
        ],
        explanation="Đáp án D (line) kết hợp với danh từ 'product' tạo thành danh từ ghép 'product line' (dòng sản phẩm).",
        distractor_analysis=DistractorAnalysis(
            A="Đáp án A (to line) là dạng to-infinitive, không phù hợp làm tân ngữ sau tính từ sở hữu 'its product'.",
            B="Đáp án B (lining) là danh động từ hoặc danh từ mang nghĩa lớp lót, không tạo thành thuật ngữ kinh doanh hợp ngữ cảnh.",
            C="Đáp án C (lined) là dạng quá khứ/phân từ, không phù hợp với cấu trúc cụm danh từ ở vị trí này.",
            D="Đáp án D (line) là đáp án đúng, tạo thành cụm danh từ 'product line' hoàn chỉnh và tự nhiên trong ngữ cảnh.",
        ),
        difficulty="medium",
    )
    res_108 = validator.validate(q108, enrichment_108)
    assert res_108.is_valid is True
    assert res_108.status == QualityValidationStatus.VALID


# ---------------------------------------------------------------------------
# Phase B1: Extended Contradiction and Language Script Leakage Tests
# ---------------------------------------------------------------------------

def test_contradiction_in_explanation_asserting_correct_answer_is_wrong(example_question, valid_enrichment_for_example):
    """When the main explanation claims the authoritative correct answer is wrong, it must be rejected."""
    validator = EnrichmentValidator()
    # Authoritative answer is B
    valid_enrichment_for_example.explanation = "Đáp án B là sai do không phù hợp với thì của câu."
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is False
    assert result.status == QualityValidationStatus.SUSPICIOUS
    assert result.error_code == "CORRECT_ANSWER_CONTRADICTION"
    assert any("asserts that authoritative correct answer 'B' is incorrect" in err for err in result.errors)


def test_contradiction_in_wrong_distractor_claiming_it_is_correct(example_question, valid_enrichment_for_example):
    """When a wrong option's distractor analysis claims that wrong option is the correct answer, it must be rejected."""
    validator = EnrichmentValidator()
    # Authoritative answer is B. Distractor A (across) claims to be correct.
    valid_enrichment_for_example.distractor_analysis.A = "Đáp án A là đáp án đúng vì across phù hợp nhất."
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is False
    assert result.status == QualityValidationStatus.SUSPICIOUS
    assert result.error_code == "CORRECT_ANSWER_CONTRADICTION"
    assert any("for incorrect option 'A' asserts that it is the correct answer" in err for err in result.errors)


def test_positive_correct_answer_rationale_does_not_falsely_trigger_contradiction(example_question, valid_enrichment_for_example):
    """Positive rationale for the correct answer must not trigger contradiction checks."""
    validator = EnrichmentValidator()
    valid_enrichment_for_example.explanation = "Chọn B (after). Cụm after which có nghĩa là sau thời điểm đó và bổ nghĩa chính xác."
    valid_enrichment_for_example.distractor_analysis.B = "After kết hợp với which tạo thành after which chỉ thời điểm sau sự việc."
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID
    assert result.errors == []


@pytest.mark.parametrize("cjk_text,field_name", [
    ("选择 B 是正确的语法结构", "explanation"),
    ("正解はBです", "grammar_topic"),
    ("정답은 B입니다", "sentence_structure"),
    ("词汇 pattern X", "pattern"),
])
def test_cjk_language_script_leakage_rejected(example_question, valid_enrichment_for_example, cjk_text, field_name):
    """Obvious CJK script leakage in learner-facing fields must be rejected."""
    validator = EnrichmentValidator()
    setattr(valid_enrichment_for_example, field_name, cjk_text)
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is False
    assert result.status == QualityValidationStatus.REJECTED
    assert result.error_code == "LANGUAGE_SCRIPT_LEAKAGE"
    assert any("contains foreign CJK characters" in err for err in result.errors)


def test_vietnamese_diacritics_accepted_without_cjk_false_positive(example_question, valid_enrichment_for_example):
    """Vietnamese diacritics and tones must not trigger CJK leakage false positives."""
    validator = EnrichmentValidator()
    valid_enrichment_for_example.explanation = "Chọn B (sau khi). Người tham dự có thể đặt câu hỏi ở hội trường một cách rõ ràng và chuẩn xác."
    valid_enrichment_for_example.distractor_analysis.A = "Không phù hợp vì across chỉ sự di chuyển ngang qua một khu vực."
    valid_enrichment_for_example.vocabulary = [
        VocabularyItem(word="attendees", meaning="người tham dự cuộc họp", part_of_speech="noun")
    ]
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID
    assert not any("CJK" in err for err in result.errors)


# ---------------------------------------------------------------------------
# Phase B2: Warning-Only Pedagogical Lints Tests
# ---------------------------------------------------------------------------

def test_generic_explanation_triggers_warning_not_hard_rejection(example_question, valid_enrichment_for_example):
    """Generic explanation ('phù hợp với ngữ cảnh') produces a warning but keeps is_valid=True."""
    validator = EnrichmentValidator()
    valid_enrichment_for_example.explanation = "Phù hợp với ngữ cảnh của câu."
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID
    assert result.errors == []
    assert any("[GENERIC_EXPLANATION]" in w for w in result.warnings)


def test_boilerplate_and_trivial_distractors_trigger_warnings(example_question, valid_enrichment_for_example):
    """Trivial ('sai', 'đúng') or repeated boilerplate distractors produce warnings without failing validity."""
    validator = EnrichmentValidator()
    valid_enrichment_for_example.distractor_analysis = DistractorAnalysis(
        A="Sai.",
        B="Đúng.",
        C="Sai.",
        D="Sai.",
    )
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID
    assert any("[BOILERPLATE_DISTRACTOR_ANALYSIS]" in w for w in result.warnings)
    assert any("[TRIVIAL_DISTRACTOR_ANALYSIS]" in w for w in result.warnings)


def test_generic_pattern_and_structure_trigger_warnings(example_question, valid_enrichment_for_example):
    """Generic patterns like 'SVO' or 'verb form' produce warnings without failing validity."""
    validator = EnrichmentValidator()
    valid_enrichment_for_example.sentence_structure = "SVO"
    valid_enrichment_for_example.pattern = "verb form"
    result = validator.validate(example_question, valid_enrichment_for_example)

    assert result.is_valid is True
    assert result.status == QualityValidationStatus.VALID
    assert any("[GENERIC_SENTENCE_STRUCTURE]" in w for w in result.warnings)
    assert any("[GENERIC_PATTERN]" in w for w in result.warnings)


def test_validate_and_raise_script_leakage_error(example_question, valid_enrichment_for_example):
    """validate_and_raise must raise EnrichmentScriptLeakageError on foreign CJK characters."""
    validator = EnrichmentValidator()
    valid_enrichment_for_example.explanation = "这是中文解析。"
    with pytest.raises(EnrichmentScriptLeakageError) as exc_info:
        validator.validate_and_raise(example_question, valid_enrichment_for_example)

    assert exc_info.value.code == "LANGUAGE_SCRIPT_LEAKAGE"
    assert "Foreign language script leakage" in str(exc_info.value)
