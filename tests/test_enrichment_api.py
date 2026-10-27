import json
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.questions import get_enrichment_workflow
from app.db.database import Base, SessionLocal, engine
from app.main import app
from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.repositories.enrichment_repository import EnrichmentRepository
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_workflow import EnrichmentWorkflow
from app.services.llm_client import (
    LLMConnectionError,
    LLMProviderError,
    LLMTimeoutError,
)

client = TestClient(app)


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
def valid_llm_json():
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


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


def test_post_valid_question_id_returns_200_and_persists(
    db_session, sample_question, valid_llm_json
):
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=FakeLLMService(valid_llm_json))
    )
    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 200

    data = response.json()
    assert data["question_id"] == sample_question.id
    assert data["grammar_topic"] == "Subjunctive Mood"
    assert data["difficulty"] == "hard"
    assert len(data["vocabulary"]) == 1
    assert data["vocabulary"][0]["word"] == "request"
    assert data["distractor_analysis"]["C"] == "Đúng vì 'be' là dạng nguyên thể"

    # Verify internal DB fields are NOT exposed in API response
    assert "id" not in data
    assert "status" not in data
    assert "created_at" not in data

    # Verify actual persistence in database
    db_session.expire_all()
    persisted = EnrichmentRepository.get_by_question_id(db_session, sample_question.id)
    assert persisted is not None
    assert persisted.question_id == sample_question.id
    assert persisted.grammar_topic == "Subjunctive Mood"


def test_nonexistent_question_returns_404(db_session):
    non_existent_id = 99999
    response = client.post(f"/api/v1/questions/{non_existent_id}/enrich")
    assert response.status_code == 404
    assert f"Question with ID {non_existent_id} not found" in response.json()["detail"]


def test_llm_connection_failure_returns_503(db_session, sample_question):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = LLMConnectionError("Connection refused")
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=mock_llm)
    )
    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 503
    assert "LLM service connection failed" in response.json()["detail"]


def test_llm_timeout_returns_504(db_session, sample_question):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = LLMTimeoutError("Request timed out after 60s")
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=mock_llm)
    )
    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 504
    assert "LLM service timed out" in response.json()["detail"]


def test_llm_provider_error_returns_502(db_session, sample_question):
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = LLMProviderError("HTTP 500: Model failed", status_code=500)
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=mock_llm)
    )
    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 502
    assert "LLM provider error" in response.json()["detail"]


def test_invalid_llm_json_syntax_returns_502(db_session, sample_question):
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=FakeLLMService("Invalid json {,"))
    )
    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 502
    assert "Failed to parse LLM response as JSON" in response.json()["detail"]


def test_invalid_enrichment_schema_returns_502(db_session, sample_question):
    incomplete_json = json.dumps({"grammar_topic": "Only one field"})
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=FakeLLMService(incomplete_json))
    )
    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 502
    assert "LLM response failed schema validation" in response.json()["detail"]


def test_database_integrity_failure_returns_409(db_session, sample_question):
    mock_workflow = MagicMock()
    mock_workflow.execute.side_effect = IntegrityError("duplicate key", params=None, orig=Exception("UNIQUE constraint failed"))
    app.dependency_overrides[get_enrichment_workflow] = lambda: mock_workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 409
    assert "Enrichment database integrity conflict" in response.json()["detail"]


def test_re_enrichment_without_force_is_idempotent(db_session, sample_question, valid_llm_json):
    fake_llm = FakeLLMService(valid_llm_json)
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=fake_llm)
    )
    # 1. First enrichment persists to DB
    record1 = workflow.execute(session=db_session, question=sample_question)
    assert record1.status == "COMPLETED"

    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    # Reset fake_llm tracking
    fake_llm.last_prompt = None

    # 2. Second request without force returns existing record (HTTP 200) without calling LLM
    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 200
    assert fake_llm.last_prompt is None  # LLM was not invoked!
    data = response.json()
    assert data["question_id"] == sample_question.id
    assert data["grammar_topic"] == "Subjunctive Mood"


def test_forced_re_enrichment_updates_record(db_session, sample_question, valid_llm_json):
    fake_llm = FakeLLMService(valid_llm_json)
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=fake_llm)
    )
    # 1. First enrichment persists to DB
    record1 = workflow.execute(session=db_session, question=sample_question)
    original_id = record1.id

    # Create new LLM response with updated topic
    updated_payload = json.loads(valid_llm_json)
    updated_payload["grammar_topic"] = "Advanced Subjunctive"
    fake_llm.response_text = json.dumps(updated_payload)
    fake_llm.last_prompt = None

    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    # 2. Request with force=true calls LLM and updates record in-place
    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich?force=true")
    assert response.status_code == 200
    assert fake_llm.last_prompt is not None  # LLM was invoked!
    data = response.json()
    assert data["grammar_topic"] == "Advanced Subjunctive"

    # Verify same row ID in DB
    db_session.expire_all()
    refreshed = workflow.enrichment_repository.get_by_question_id(db_session, sample_question.id)
    assert refreshed.id == original_id
    assert refreshed.grammar_topic == "Advanced Subjunctive"


def test_api_does_not_call_session_commit_or_rollback_directly(
    db_session, sample_question, valid_llm_json, monkeypatch
):
    mock_workflow = MagicMock()
    mock_record = QuestionEnrichmentModel(
        question_id=sample_question.id,
        grammar_topic="Word Form",
        sentence_structure="S + V + O",
        pattern="test pattern",
        vocabulary=[{"word": "test", "meaning": "thu nghiem", "part_of_speech": "noun"}],
        explanation="Test explanation",
        distractor_analysis={"A": "ok", "B": "no", "C": "no", "D": "no"},
        difficulty="easy",
        status="COMPLETED",
    )
    mock_workflow.execute.return_value = mock_record
    app.dependency_overrides[get_enrichment_workflow] = lambda: mock_workflow

    # Mock session commit and rollback on DB session to assert the API endpoint does not touch them
    session_commit_called = False
    session_rollback_called = False

    def tracked_commit():
        nonlocal session_commit_called
        session_commit_called = True

    def tracked_rollback():
        nonlocal session_rollback_called
        session_rollback_called = True

    monkeypatch.setattr(db_session, "commit", tracked_commit)
    monkeypatch.setattr(db_session, "rollback", tracked_rollback)

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 200

    # API itself must NOT call commit or rollback; workflow owns it
    assert session_commit_called is False
    assert session_rollback_called is False
    assert mock_workflow.execute.called is True


def test_quality_validation_failure_returns_502(db_session, sample_question, valid_llm_json):
    payload = json.loads(valid_llm_json)
    # Inject ungrounded vocabulary item
    payload["vocabulary"] = [{"word": "nonexistent_banana", "meaning": "chuối", "part_of_speech": "noun"}]
    workflow = EnrichmentWorkflow(
        enrichment_service=EnrichmentService(llm_service=FakeLLMService(json.dumps(payload)))
    )
    app.dependency_overrides[get_enrichment_workflow] = lambda: workflow

    response = client.post(f"/api/v1/questions/{sample_question.id}/enrich")
    assert response.status_code == 502
    assert "Enrichment quality validation failed" in response.json()["detail"]
    assert "UNGROUNDED_VOCABULARY" in response.json()["detail"]

