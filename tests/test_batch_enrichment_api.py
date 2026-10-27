from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.api.enrichments import get_batch_enrichment_workflow
from app.db.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models.question import Question
from app.repositories.enrichment_repository import EnrichmentRepository
from app.schemas.enrichment import DistractorAnalysis, QuestionEnrichment, VocabularyItem
from app.services.batch_enrichment_workflow import (
    BatchEnrichmentResult,
    BatchEnrichmentWorkflow,
    BatchItemResult,
)
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_workflow import EnrichmentWorkflow
from app.services.gemini_client import GeminiClient
from app.services.llm_client import LLMConnectionError

client = TestClient(app)


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


def create_sample_question(session, question_no: int) -> Question:
    q = Question(
        test_id="API_BATCH_TEST",
        part=5,
        question_no=question_no,
        question_text=f"Question test text {question_no} ______ correctly.",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="A",
        explanation=f"Explanation {question_no}",
    )
    session.add(q)
    session.commit()
    session.refresh(q)
    return q


def create_sample_enrichment_schema(grammar_topic: str = "Tenses") -> QuestionEnrichment:
    return QuestionEnrichment(
        grammar_topic=grammar_topic,
        sentence_structure="S + V + O",
        pattern="Pattern rule",
        vocabulary=[VocabularyItem(word="test", meaning="kiểm tra", part_of_speech="verb")],
        explanation="Explanation text",
        distractor_analysis=DistractorAnalysis(A="Correct", B="Wrong", C="Wrong", D="Wrong"),
        difficulty="medium",
    )


def test_valid_batch_all_success_returns_200_and_matches_order(db_session):
    """Test 1 & 5 & 6 & 7 & 8: Valid batch with all questions successful returns 200, correct counts and order."""
    q1 = create_sample_question(db_session, 101)
    q2 = create_sample_question(db_session, 102)

    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.side_effect = [
        create_sample_enrichment_schema("Topic 1"),
        create_sample_enrichment_schema("Topic 2"),
    ]
    workflow = BatchEnrichmentWorkflow(
        enrichment_workflow=EnrichmentWorkflow(enrichment_service=mock_service)
    )

    app.dependency_overrides[get_batch_enrichment_workflow] = lambda: workflow
    try:
        response = client.post("/api/v1/enrichments/batch", json={"question_ids": [q1.id, q2.id]})
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert data["success"] == 2
        assert data["failed"] == 0
        assert len(data["results"]) == 2
        assert data["results"][0] == {"question_id": q1.id, "status": "COMPLETED"}
        assert data["results"][1] == {"question_id": q2.id, "status": "COMPLETED"}
    finally:
        app.dependency_overrides.pop(get_batch_enrichment_workflow, None)


def test_empty_question_ids_returns_422():
    """Test 2: Empty question_ids list returns 422."""
    response = client.post("/api/v1/enrichments/batch", json={"question_ids": []})
    assert response.status_code == 422


def test_invalid_question_ids_return_422():
    """Test 3: Non-positive IDs or duplicate IDs return 422."""
    # Negative ID
    res1 = client.post("/api/v1/enrichments/batch", json={"question_ids": [-1, 102]})
    assert res1.status_code == 422

    # Zero ID
    res2 = client.post("/api/v1/enrichments/batch", json={"question_ids": [0]})
    assert res2.status_code == 422

    # Duplicate IDs
    res3 = client.post("/api/v1/enrichments/batch", json={"question_ids": [101, 101]})
    assert res3.status_code == 422


def test_batch_with_one_failed_question_returns_200_and_serializable_error(db_session):
    """Test 4 & 10: Batch with one failed question returns HTTP 200 with serializable error."""
    q1 = create_sample_question(db_session, 101)
    q2 = create_sample_question(db_session, 102)

    mock_service = MagicMock(spec=EnrichmentService)

    def side_effect(question):
        if question.id == q2.id:
            raise LLMConnectionError("Cannot connect to LLM")
        return create_sample_enrichment_schema("Topic 101")

    mock_service.enrich_question.side_effect = side_effect
    workflow = BatchEnrichmentWorkflow(
        enrichment_workflow=EnrichmentWorkflow(enrichment_service=mock_service)
    )

    app.dependency_overrides[get_batch_enrichment_workflow] = lambda: workflow
    try:
        response = client.post("/api/v1/enrichments/batch", json={"question_ids": [q1.id, q2.id]})
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert data["success"] == 1
        assert data["failed"] == 1
        assert data["results"][0] == {"question_id": q1.id, "status": "COMPLETED"}
        assert data["results"][1]["question_id"] == q2.id
        assert data["results"][1]["status"] == "FAILED"
        assert "Cannot connect to LLM" in data["results"][1]["error"]
        # Ensure only serializable primitives are in the response
        assert isinstance(data["results"][1]["error"], str)
    finally:
        app.dependency_overrides.pop(get_batch_enrichment_workflow, None)


def test_question_not_found_appears_as_failed_item_not_404(db_session):
    """Test 9: Missing question in batch appears as FAILED item, not HTTP 404."""
    q1 = create_sample_question(db_session, 101)
    missing_id = 999999

    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.return_value = create_sample_enrichment_schema()
    workflow = BatchEnrichmentWorkflow(
        enrichment_workflow=EnrichmentWorkflow(enrichment_service=mock_service)
    )

    app.dependency_overrides[get_batch_enrichment_workflow] = lambda: workflow
    try:
        response = client.post("/api/v1/enrichments/batch", json={"question_ids": [q1.id, missing_id]})
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert data["success"] == 1
        assert data["failed"] == 1
        assert data["results"][1]["question_id"] == missing_id
        assert data["results"][1]["status"] == "FAILED"
        assert "not found" in data["results"][1]["error"].lower()
    finally:
        app.dependency_overrides.pop(get_batch_enrichment_workflow, None)


def test_api_delegates_to_batch_workflow_and_does_not_call_llm_directly(db_session):
    """Test 11 & 12: API delegates directly to BatchEnrichmentWorkflow without calling LLM."""
    mock_workflow = MagicMock(spec=BatchEnrichmentWorkflow)
    mock_workflow.execute.return_value = BatchEnrichmentResult(
        total=1,
        success=1,
        failed=0,
        results=[BatchItemResult(question_id=101, status="COMPLETED")],
    )

    app.dependency_overrides[get_batch_enrichment_workflow] = lambda: mock_workflow
    try:
        with patch.object(GeminiClient, "generate", side_effect=AssertionError("API called LLM directly!")):
            response = client.post("/api/v1/enrichments/batch", json={"question_ids": [101]})
            assert response.status_code == 200
            assert mock_workflow.execute.call_count == 1
    finally:
        app.dependency_overrides.pop(get_batch_enrichment_workflow, None)


def test_api_does_not_call_commit_or_rollback_directly(db_session):
    """Test 13 & 14: Batch API endpoint does NOT call commit or rollback directly."""
    real_session = SessionLocal()
    spy_commit = MagicMock(wraps=real_session.commit)
    spy_rollback = MagicMock(wraps=real_session.rollback)
    real_session.commit = spy_commit
    real_session.rollback = spy_rollback

    def override_get_db():
        try:
            yield real_session
        finally:
            real_session.close()

    mock_workflow = MagicMock(spec=BatchEnrichmentWorkflow)
    mock_workflow.execute.return_value = BatchEnrichmentResult(total=1, success=1, failed=0, results=[BatchItemResult(question_id=101, status="COMPLETED")])

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_batch_enrichment_workflow] = lambda: mock_workflow
    try:
        response = client.post("/api/v1/enrichments/batch", json={"question_ids": [101]})
        assert response.status_code == 200

        # API itself must not call commit or rollback
        assert spy_commit.call_count == 0
        assert spy_rollback.call_count == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_batch_enrichment_workflow, None)
        real_session.close()


def test_integration_q101_success_q102_failure_q103_success(db_session):
    """Important Integration Test:
    Verify:
      Q101 -> SUCCESS
      Q102 -> FAILURE
      Q103 -> SUCCESS

    HTTP Response:
      status_code == 200
      total = 3, success = 2, failed = 1

    Database state:
      Q101 enrichment exists.
      Q102 enrichment does not exist.
      Q103 enrichment exists.

    Proves API preserves per-question transaction boundary without batch-level rollback.
    """
    q101 = create_sample_question(db_session, 101)
    q102 = create_sample_question(db_session, 102)
    q103 = create_sample_question(db_session, 103)

    mock_service = MagicMock(spec=EnrichmentService)

    def side_effect(question):
        if question.id == q102.id:
            raise LLMConnectionError("Failure on 102")
        return create_sample_enrichment_schema(f"Topic {question.id}")

    mock_service.enrich_question.side_effect = side_effect

    # Real workflow stack using real session
    real_workflow = BatchEnrichmentWorkflow(
        enrichment_workflow=EnrichmentWorkflow(enrichment_service=mock_service)
    )

    app.dependency_overrides[get_batch_enrichment_workflow] = lambda: real_workflow
    try:
        response = client.post(
            "/api/v1/enrichments/batch",
            json={"question_ids": [q101.id, q102.id, q103.id]},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 3
        assert data["success"] == 2
        assert data["failed"] == 1

        assert data["results"][0] == {"question_id": q101.id, "status": "COMPLETED"}
        assert data["results"][1]["question_id"] == q102.id
        assert data["results"][1]["status"] == "FAILED"
        assert "Failure on 102" in data["results"][1]["error"]
        assert data["results"][2] == {"question_id": q103.id, "status": "COMPLETED"}

        # Verify DB state directly
        enr_101 = EnrichmentRepository.get_by_question_id(db_session, q101.id)
        enr_102 = EnrichmentRepository.get_by_question_id(db_session, q102.id)
        enr_103 = EnrichmentRepository.get_by_question_id(db_session, q103.id)

        assert enr_101 is not None, "Q101 must be committed and persisted"
        assert enr_102 is None, "Q102 must NOT exist in DB"
        assert enr_103 is not None, "Q103 must be committed and persisted"
    finally:
        app.dependency_overrides.pop(get_batch_enrichment_workflow, None)
