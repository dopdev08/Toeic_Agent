import json
from unittest.mock import MagicMock
import pytest
from sqlalchemy.exc import IntegrityError

from app.db.database import Base, SessionLocal, engine
from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.repositories.enrichment_repository import EnrichmentRepository
from app.services.enrichment_response_parser import (
    EnrichmentJSONDecodeError,
    EnrichmentValidationError,
)
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_workflow import EnrichmentWorkflow
from app.services.llm_client import LLMConnectionError


class FakeLLMService:
    def __init__(self, response_text: str = "") -> None:
        self.response_text = response_text
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response_text


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
def valid_llm_json_response():
    return json.dumps({
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
    })


def test_successful_enrichment_and_persistence(
    db_session, sample_question, valid_llm_json_response
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    service = EnrichmentService(llm_service=fake_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    record = workflow.execute(session=db_session, question=sample_question)

    assert record is not None
    assert record.id is not None
    assert record.question_id == sample_question.id
    assert record.status == "COMPLETED"


def test_verify_record_exists_in_database(
    db_session, sample_question, valid_llm_json_response
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    service = EnrichmentService(llm_service=fake_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    created_record = workflow.execute(session=db_session, question=sample_question)

    # Clean query from database
    db_session.expire_all()
    persisted = db_session.get(QuestionEnrichmentModel, created_record.id)

    assert persisted is not None
    assert persisted.id == created_record.id
    assert persisted.question_id == sample_question.id


def test_persisted_data_matches_validated_schema(
    db_session, sample_question, valid_llm_json_response
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    service = EnrichmentService(llm_service=fake_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    workflow.execute(session=db_session, question=sample_question)

    db_session.expire_all()
    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)

    assert persisted is not None
    assert persisted.grammar_topic == "Subjunctive Mood"
    assert persisted.sentence_structure == "S + requested + that + S + (should) + V-bare"
    assert persisted.pattern == "request that somebody (should) do something"
    assert persisted.difficulty == "hard"
    assert len(persisted.vocabulary) == 1
    assert persisted.vocabulary[0]["word"] == "request"
    assert persisted.distractor_analysis["C"] == "Đúng vì 'be' là dạng nguyên thể"


def test_llm_failure_results_in_no_committed_enrichment(db_session, sample_question):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = LLMConnectionError("Failed to connect to LLM")
    service = EnrichmentService(llm_service=mock_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    with pytest.raises(LLMConnectionError) as exc_info:
        workflow.execute(session=db_session, question=sample_question)

    assert "Failed to connect to LLM" in str(exc_info.value)

    # Verify no enrichment was saved in DB
    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert persisted is None


def test_json_parsing_failure_results_in_no_committed_enrichment(
    db_session, sample_question
):
    fake_llm = FakeLLMService(response_text="Truncated JSON {bad")
    service = EnrichmentService(llm_service=fake_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    with pytest.raises(EnrichmentJSONDecodeError) as exc_info:
        workflow.execute(session=db_session, question=sample_question)

    assert "Failed to decode JSON" in str(exc_info.value)

    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert persisted is None


def test_validation_failure_results_in_no_committed_enrichment(
    db_session, sample_question
):
    fake_llm = FakeLLMService(response_text=json.dumps({"grammar_topic": "Incomplete"}))
    service = EnrichmentService(llm_service=fake_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    with pytest.raises(EnrichmentValidationError) as exc_info:
        workflow.execute(session=db_session, question=sample_question)

    assert "QuestionEnrichment validation" in str(exc_info.value)

    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert persisted is None


def test_repository_database_failure_triggers_rollback(
    db_session, sample_question, valid_llm_json_response
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    service = EnrichmentService(llm_service=fake_llm)

    # Mock repository to simulate a DB persistence failure
    mock_repo = MagicMock()
    mock_repo.save_enrichment.side_effect = IntegrityError(
        "INSERT INTO ...", {}, Exception("DB Constraint Violation")
    )

    workflow = EnrichmentWorkflow(
        enrichment_service=service, enrichment_repository=mock_repo
    )

    with pytest.raises(IntegrityError):
        workflow.execute(session=db_session, question=sample_question)

    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert persisted is None


def test_after_rollback_no_partial_enrichment_record_exists(
    db_session, sample_question, valid_llm_json_response, monkeypatch
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    service = EnrichmentService(llm_service=fake_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    # Simulate an error during session.commit()
    def failing_commit():
        raise RuntimeError("Commit failed unexpectedly")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(RuntimeError) as exc_info:
        workflow.execute(session=db_session, question=sample_question)

    assert "Commit failed unexpectedly" in str(exc_info.value)

    # Confirm rollback ensured no partial record exists
    db_session.expire_all()
    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert persisted is None


def test_commit_is_owned_by_workflow_not_components(
    db_session, sample_question, valid_llm_json_response, monkeypatch
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    service = EnrichmentService(llm_service=fake_llm)
    workflow = EnrichmentWorkflow(enrichment_service=service)

    commit_called = False
    original_commit = db_session.commit

    def tracked_commit():
        nonlocal commit_called
        commit_called = True
        original_commit()

    monkeypatch.setattr(db_session, "commit", tracked_commit)

    record = workflow.execute(session=db_session, question=sample_question)

    assert commit_called is True
    assert record.id is not None


def test_existing_completed_enrichment_with_force_false_returns_existing_without_llm(
    db_session, sample_question, valid_llm_json_response
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    workflow = EnrichmentWorkflow(enrichment_service=EnrichmentService(llm_service=fake_llm))

    # 1. First execution populates DB
    first_record = workflow.execute(session=db_session, question=sample_question)
    assert first_record.status == "COMPLETED"
    assert fake_llm.last_prompt is not None

    # Reset tracking
    fake_llm.last_prompt = None

    # 2. Second execution with force=False returns existing record without calling LLM
    second_record = workflow.execute(session=db_session, question=sample_question, force=False)
    assert second_record.id == first_record.id
    assert second_record.grammar_topic == first_record.grammar_topic
    assert fake_llm.last_prompt is None  # LLM was not invoked!


def test_force_true_updates_existing_enrichment_in_place_preserving_row_id(
    db_session, sample_question, valid_llm_json_response
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    workflow = EnrichmentWorkflow(enrichment_service=EnrichmentService(llm_service=fake_llm))

    # 1. Initial persistence
    record1 = workflow.execute(session=db_session, question=sample_question)
    original_id = record1.id

    # Prepare updated payload
    updated_payload = json.loads(valid_llm_json_response)
    updated_payload["grammar_topic"] = "Subjunctive Mood (Advanced)"
    updated_payload["difficulty"] = "medium"
    fake_llm.response_text = json.dumps(updated_payload)
    fake_llm.last_prompt = None

    # 2. Forced execution updates in place
    record2 = workflow.execute(session=db_session, question=sample_question, force=True)

    # Must preserve exact same row ID and question_id
    assert record2.id == original_id
    assert record2.question_id == sample_question.id
    assert record2.grammar_topic == "Subjunctive Mood (Advanced)"
    assert record2.difficulty == "medium"
    assert record2.status == "COMPLETED"
    assert fake_llm.last_prompt is not None


def test_forced_failure_preserves_original_enrichment_data(
    db_session, sample_question, valid_llm_json_response
):
    fake_llm = FakeLLMService(response_text=valid_llm_json_response)
    workflow = EnrichmentWorkflow(enrichment_service=EnrichmentService(llm_service=fake_llm))

    # 1. Initial successful persistence
    record1 = workflow.execute(session=db_session, question=sample_question)
    original_id = record1.id
    original_topic = record1.grammar_topic

    # Mock failure on subsequent call (e.g. LLM connection failure or timeout)
    fake_llm.generate = MagicMock(side_effect=LLMConnectionError("Service unavailable"))

    # 2. Forced call fails
    with pytest.raises(LLMConnectionError):
        workflow.execute(session=db_session, question=sample_question, force=True)

    # 3. Verify original enrichment is preserved in database unharmed
    db_session.expire_all()
    preserved = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert preserved is not None
    assert preserved.id == original_id
    assert preserved.grammar_topic == original_topic
    assert preserved.status == "COMPLETED"


def test_failed_attempt_on_question_without_enrichment_leaves_no_row(
    db_session, sample_question
):
    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.side_effect = EnrichmentJSONDecodeError("Malformed JSON")
    workflow = EnrichmentWorkflow(enrichment_service=mock_service)

    with pytest.raises(EnrichmentJSONDecodeError):
        workflow.execute(session=db_session, question=sample_question)

    db_session.expire_all()
    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert persisted is None

