import pytest
from sqlalchemy.exc import IntegrityError

from app.db.database import Base, SessionLocal, engine
from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.repositories.enrichment_repository import EnrichmentRepository
from app.schemas.enrichment import (
    DistractorAnalysis,
    QuestionEnrichment as QuestionEnrichmentSchema,
    VocabularyItem,
)


@pytest.fixture
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_question(db_session):
    q = Question(
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
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    return q


@pytest.fixture
def valid_pydantic_enrichment():
    return QuestionEnrichmentSchema(
        grammar_topic="Subjunctive Mood",
        sentence_structure="S + requested + that + S + (should) + V-bare",
        pattern="request that somebody (should) do something",
        vocabulary=[
            VocabularyItem(
                word="request",
                meaning="yêu cầu",
                part_of_speech="verb",
            ),
            VocabularyItem(
                word="executive",
                meaning="cấp quản lý",
                part_of_speech="noun",
            ),
        ],
        explanation="Động từ theo sau 'requested that' ở thể giả định thức.",
        distractor_analysis=DistractorAnalysis(
            A="Sai vì dùng thì hiện tại 'is'",
            B="Sai vì dùng thì quá khứ 'was'",
            C="Đúng vì 'be' là dạng nguyên thể",
            D="Sai vì 'being' là phân từ",
        ),
        difficulty="hard",
    )


def test_successful_persistence(db_session, sample_question, valid_pydantic_enrichment):
    record = EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
        status="COMPLETED",
    )
    db_session.commit()

    assert record.id is not None
    assert record.question_id == sample_question.id
    assert record.status == "COMPLETED"
    assert record.grammar_topic == "Subjunctive Mood"
    assert record.difficulty == "hard"


def test_reload_from_db_returns_identical_data(
    db_session, sample_question, valid_pydantic_enrichment
):
    saved_record = EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    db_session.commit()

    db_session.expire_all()
    reloaded = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)

    assert reloaded is not None
    assert reloaded.id == saved_record.id
    assert reloaded.grammar_topic == valid_pydantic_enrichment.grammar_topic
    assert reloaded.sentence_structure == valid_pydantic_enrichment.sentence_structure
    assert reloaded.pattern == valid_pydantic_enrichment.pattern
    assert reloaded.explanation == valid_pydantic_enrichment.explanation
    assert reloaded.difficulty == valid_pydantic_enrichment.difficulty


def test_vocabulary_json_round_trip(
    db_session, sample_question, valid_pydantic_enrichment
):
    EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    db_session.commit()

    db_session.expire_all()
    reloaded = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)

    assert reloaded is not None
    assert isinstance(reloaded.vocabulary, list)
    assert len(reloaded.vocabulary) == 2
    assert reloaded.vocabulary[0] == {
        "word": "request",
        "meaning": "yêu cầu",
        "part_of_speech": "verb",
    }
    assert reloaded.vocabulary[1] == {
        "word": "executive",
        "meaning": "cấp quản lý",
        "part_of_speech": "noun",
    }


def test_distractor_analysis_json_round_trip(
    db_session, sample_question, valid_pydantic_enrichment
):
    EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    db_session.commit()

    db_session.expire_all()
    reloaded = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)

    assert reloaded is not None
    assert isinstance(reloaded.distractor_analysis, dict)
    assert reloaded.distractor_analysis["A"] == "Sai vì dùng thì hiện tại 'is'"
    assert reloaded.distractor_analysis["B"] == "Sai vì dùng thì quá khứ 'was'"
    assert reloaded.distractor_analysis["C"] == "Đúng vì 'be' là dạng nguyên thể"
    assert reloaded.distractor_analysis["D"] == "Sai vì 'being' là phân từ"


def test_difficulty_persistence(
    db_session, sample_question, valid_pydantic_enrichment
):
    valid_pydantic_enrichment.difficulty = "medium"
    record = EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    db_session.commit()

    db_session.expire_all()
    reloaded = db_session.get(QuestionEnrichmentModel, record.id)
    assert reloaded.difficulty == "medium"


def test_question_relationship(
    db_session, sample_question, valid_pydantic_enrichment
):
    record = EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    db_session.commit()

    db_session.expire_all()
    question = db_session.get(Question, sample_question.id)
    assert question.enrichment is not None
    assert question.enrichment.id == record.id
    assert question.enrichment.question.id == sample_question.id


def test_duplicate_question_id_is_rejected(
    db_session, sample_question, valid_pydantic_enrichment
):
    # First save succeeds
    EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    db_session.commit()

    # Second save with same question_id must raise IntegrityError on flush
    with pytest.raises(IntegrityError):
        EnrichmentRepository.save_enrichment(
            session=db_session,
            question_id=sample_question.id,
            enrichment=valid_pydantic_enrichment,
        )
    db_session.rollback()


def test_invalid_nonexistent_question_id_fails_integrity(
    db_session, valid_pydantic_enrichment
):
    non_existent_id = 999999
    with pytest.raises(IntegrityError):
        EnrichmentRepository.save_enrichment(
            session=db_session,
            question_id=non_existent_id,
            enrichment=valid_pydantic_enrichment,
        )
    db_session.rollback()


def test_no_commit_occurs_inside_persistence_component(
    db_session, sample_question, valid_pydantic_enrichment
):
    # Call save_enrichment (flushes, but does not commit)
    record = EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    assert record.id is not None

    # Roll back the transaction
    db_session.rollback()

    # Because save_enrichment did not commit, rollback discards the flushed record
    db_session.expire_all()
    queried = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert queried is None


def test_update_existing_enrichment_in_place_when_supplied(
    db_session, sample_question, valid_pydantic_enrichment
):
    # 1. First save creates new record
    original = EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=valid_pydantic_enrichment,
    )
    db_session.commit()
    original_id = original.id

    # 2. Update with modified schema and existing record passed
    updated_schema = valid_pydantic_enrichment.model_copy(
        update={"grammar_topic": "Updated Topic"}
    )
    updated = EnrichmentRepository.save_enrichment(
        session=db_session,
        question_id=sample_question.id,
        enrichment=updated_schema,
        existing=original,
    )
    db_session.commit()

    assert updated.id == original_id
    assert updated.grammar_topic == "Updated Topic"
