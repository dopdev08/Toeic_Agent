from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.orm import Session

from app.db.database import Base, SessionLocal, engine
from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.repositories.enrichment_repository import EnrichmentRepository
from app.repositories.question_repository import QuestionRepository
from app.schemas.enrichment import DistractorAnalysis, QuestionEnrichment, VocabularyItem
from app.services.batch_enrichment_workflow import BatchEnrichmentWorkflow
from app.services.enrichment_service import EnrichmentService
from app.services.enrichment_workflow import EnrichmentWorkflow
from app.services.gemini_client import GeminiClient
from app.services.llm_client import LLMConnectionError, LLMTimeoutError


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


def create_sample_question(session: Session, question_no: int) -> Question:
    q = Question(
        test_id="BATCH_TEST_2026",
        part=5,
        question_no=question_no,
        question_text=f"Sample question text for question number {question_no} ______ here.",
        option_a="option A",
        option_b="option B",
        option_c="option C",
        option_d="option D",
        correct_answer="A",
        explanation=f"Explanation for {question_no}",
    )
    session.add(q)
    session.commit()
    session.refresh(q)
    return q


def create_sample_enrichment_schema(grammar_topic: str = "Tenses") -> QuestionEnrichment:
    return QuestionEnrichment(
        grammar_topic=grammar_topic,
        sentence_structure="Subject + Verb + Object",
        pattern="Standard SVO pattern",
        vocabulary=[
            VocabularyItem(word="sample", meaning="ví dụ", part_of_speech="noun")
        ],
        explanation="Standard explanation text.",
        distractor_analysis=DistractorAnalysis(
            A="Correct option",
            B="Incorrect distractor",
            C="Incorrect distractor",
            D="Incorrect distractor",
        ),
        difficulty="medium",
    )


def test_empty_batch(db_session):
    """Test 1 & 9 & 10 & 11: Empty batch returns zero counts and empty results."""
    workflow = BatchEnrichmentWorkflow()
    result = workflow.execute(session=db_session, items=[])

    assert result.total == 0
    assert result.success == 0
    assert result.failed == 0
    assert result.results == []
    assert result.to_dict() == {
        "total": 0,
        "success": 0,
        "failed": 0,
        "results": [],
    }


def test_single_question_batch_succeeds(db_session):
    """Test 2: Single-question batch succeeds and persists record."""
    q = create_sample_question(db_session, 101)

    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.return_value = create_sample_enrichment_schema()
    inner_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    result = batch_workflow.execute(session=db_session, items=[q.id])

    assert result.total == 1
    assert result.success == 1
    assert result.failed == 0
    assert len(result.results) == 1
    assert result.results[0].question_id == q.id
    assert result.results[0].status == "COMPLETED"
    assert result.results[0].error is None

    # Check persistence in DB
    record = EnrichmentRepository.get_by_question_id(db_session, q.id)
    assert record is not None
    assert record.question_id == q.id


def test_multiple_questions_all_succeed(db_session):
    """Test 3: Multiple questions all succeed and results preserve order."""
    q1 = create_sample_question(db_session, 101)
    q2 = create_sample_question(db_session, 102)
    q3 = create_sample_question(db_session, 103)

    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.side_effect = [
        create_sample_enrichment_schema("Topic 1"),
        create_sample_enrichment_schema("Topic 2"),
        create_sample_enrichment_schema("Topic 3"),
    ]
    inner_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    result = batch_workflow.execute(session=db_session, items=[q1.id, q2.id, q3.id])

    assert result.total == 3
    assert result.success == 3
    assert result.failed == 0
    assert [r.question_id for r in result.results] == [q1.id, q2.id, q3.id]
    assert all(r.status == "COMPLETED" for r in result.results)

    # All three persisted
    assert EnrichmentRepository.get_by_question_id(db_session, q1.id) is not None
    assert EnrichmentRepository.get_by_question_id(db_session, q2.id) is not None
    assert EnrichmentRepository.get_by_question_id(db_session, q3.id) is not None


def test_one_question_fails_and_remaining_questions_continue(db_session):
    """Test 4 & 12: One question fails, batch does not stop, remaining questions continue."""
    q1 = create_sample_question(db_session, 101)
    q2 = create_sample_question(db_session, 102)
    q3 = create_sample_question(db_session, 103)
    q4 = create_sample_question(db_session, 104)

    mock_service = MagicMock(spec=EnrichmentService)

    def side_effect(question):
        if question.id == q3.id:
            raise LLMConnectionError("Cannot reach LLM for question 103")
        return create_sample_enrichment_schema(f"Topic for {question.id}")

    mock_service.enrich_question.side_effect = side_effect
    inner_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    result = batch_workflow.execute(session=db_session, items=[q1.id, q2.id, q3.id, q4.id])

    assert result.total == 4
    assert result.success == 3
    assert result.failed == 1

    # Preservation of order
    assert [r.question_id for r in result.results] == [q1.id, q2.id, q3.id, q4.id]
    assert result.results[0].status == "COMPLETED"
    assert result.results[1].status == "COMPLETED"
    assert result.results[2].status == "FAILED"
    assert "Cannot reach LLM for question 103" in result.results[2].error
    assert isinstance(result.results[2].exception, LLMConnectionError)
    assert result.results[3].status == "COMPLETED"


def test_multiple_questions_fail_independently(db_session):
    """Test 5: Multiple questions fail with distinct causes independently."""
    q1 = create_sample_question(db_session, 101)
    q2 = create_sample_question(db_session, 102)
    q3 = create_sample_question(db_session, 103)
    q4 = create_sample_question(db_session, 104)

    mock_service = MagicMock(spec=EnrichmentService)

    def side_effect(question):
        if question.id == q2.id:
            raise LLMTimeoutError("Timeout on Q2")
        if question.id == q3.id:
            raise ValueError("Validation error on Q3")
        return create_sample_enrichment_schema(f"Topic {question.id}")

    mock_service.enrich_question.side_effect = side_effect
    inner_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    result = batch_workflow.execute(session=db_session, items=[q1.id, q2.id, q3.id, q4.id])

    assert result.total == 4
    assert result.success == 2
    assert result.failed == 2

    assert result.results[0].status == "COMPLETED"
    assert result.results[1].status == "FAILED"
    assert isinstance(result.results[1].exception, LLMTimeoutError)
    assert result.results[2].status == "FAILED"
    assert isinstance(result.results[2].exception, ValueError)
    assert result.results[3].status == "COMPLETED"


def test_critical_transaction_isolation_101_success_102_failure_103_success(db_session):
    """Test 6 & 7 & Critical Transaction Test:
    Verifies that:
      Q101 -> SUCCESS (committed)
      Q102 -> FAILURE (rolled back)
      Q103 -> SUCCESS (committed)

    Database state:
      101 -> enrichment exists
      102 -> enrichment does NOT exist
      103 -> enrichment exists

    Proves batch does NOT wrap all items in a single transaction.
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

    # Real EnrichmentWorkflow with real session and real EnrichmentRepository
    real_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=real_workflow)

    result = batch_workflow.execute(session=db_session, items=[q101.id, q102.id, q103.id])

    assert result.total == 3
    assert result.success == 2
    assert result.failed == 1

    # Verify exact database state
    enr_101 = EnrichmentRepository.get_by_question_id(db_session, q101.id)
    enr_102 = EnrichmentRepository.get_by_question_id(db_session, q102.id)
    enr_103 = EnrichmentRepository.get_by_question_id(db_session, q103.id)

    assert enr_101 is not None, "Question 101 must be committed and present in DB"
    assert enr_101.question_id == q101.id

    assert enr_102 is None, "Question 102 must NOT leave a committed enrichment record in DB"

    assert enr_103 is not None, "Question 103 must be committed and present in DB"
    assert enr_103.question_id == q103.id


def test_question_not_found_is_recorded_as_failed_and_does_not_stop_batch(db_session):
    """Test 8: Non-existing question ID is recorded as FAILED without stopping the batch."""
    q1 = create_sample_question(db_session, 101)
    q2 = create_sample_question(db_session, 102)
    non_existent_id = 999999

    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.return_value = create_sample_enrichment_schema()
    inner_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    result = batch_workflow.execute(session=db_session, items=[q1.id, non_existent_id, q2.id])

    assert result.total == 3
    assert result.success == 2
    assert result.failed == 1

    assert result.results[0].question_id == q1.id
    assert result.results[0].status == "COMPLETED"

    assert result.results[1].question_id == non_existent_id
    assert result.results[1].status == "FAILED"
    assert "not found" in result.results[1].error

    assert result.results[2].question_id == q2.id
    assert result.results[2].status == "COMPLETED"


def test_batch_does_not_call_llm_directly(db_session):
    """Test 13 & 14: Batch delegates to EnrichmentWorkflow and never calls LLM directly."""
    q = create_sample_question(db_session, 101)

    mock_workflow = MagicMock(spec=EnrichmentWorkflow)
    fake_record = QuestionEnrichmentModel(question_id=q.id, grammar_topic="T", sentence_structure="S", pattern="P", vocabulary=[], explanation="E", distractor_analysis={}, difficulty="easy")
    mock_workflow.execute.return_value = fake_record

    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=mock_workflow)

    with patch.object(GeminiClient, "generate", side_effect=AssertionError("Batch called LLM directly!")):
        result = batch_workflow.execute(session=db_session, items=[q.id])

        assert result.total == 1
        assert result.success == 1
        assert mock_workflow.execute.call_count == 1


def test_batch_accepts_direct_question_objects(db_session):
    """Test accepting Question instances directly to avoid extra DB lookups."""
    q1 = create_sample_question(db_session, 101)
    q2 = create_sample_question(db_session, 102)

    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.return_value = create_sample_enrichment_schema()
    inner_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    result = batch_workflow.execute(session=db_session, items=[q1, q2])

    assert result.total == 2
    assert result.success == 2
    assert result.failed == 0
    assert result.results[0].question_id == q1.id
    assert result.results[1].question_id == q2.id


def test_batch_result_to_dict_matches_conceptual_structure():
    """Verify to_dict structure format."""
    workflow = BatchEnrichmentWorkflow()
    # Mocking results directly
    result = workflow.execute(session=MagicMock(), items=[])
    result.total = 4
    result.success = 3
    result.failed = 1
    result.results = [
        MagicMock(to_dict=lambda: {"question_id": 101, "status": "COMPLETED"}),
        MagicMock(to_dict=lambda: {"question_id": 102, "status": "COMPLETED"}),
        MagicMock(to_dict=lambda: {"question_id": 103, "status": "FAILED", "error": "LLM failed"}),
        MagicMock(to_dict=lambda: {"question_id": 104, "status": "COMPLETED"}),
    ]

    expected = {
        "total": 4,
        "success": 3,
        "failed": 1,
        "results": [
            {"question_id": 101, "status": "COMPLETED"},
            {"question_id": 102, "status": "COMPLETED"},
            {"question_id": 103, "status": "FAILED", "error": "LLM failed"},
            {"question_id": 104, "status": "COMPLETED"},
        ],
    }
    assert result.to_dict() == expected


def test_mixed_batch_with_already_completed_question_does_not_regenerate(db_session):
    q1 = create_sample_question(db_session, 201)
    q2 = create_sample_question(db_session, 202)

    mock_service = MagicMock(spec=EnrichmentService)
    mock_service.enrich_question.return_value = create_sample_enrichment_schema("Initial Topic")

    inner_workflow = EnrichmentWorkflow(enrichment_service=mock_service)
    batch_workflow = BatchEnrichmentWorkflow(enrichment_workflow=inner_workflow)

    # 1. First enrich Q1 so it is COMPLETED in DB
    record1 = inner_workflow.execute(session=db_session, question=q1)
    assert record1.status == "COMPLETED"

    # Reset mock call counter
    mock_service.enrich_question.reset_mock()

    # 2. Execute batch with [q1, q2]
    result = batch_workflow.execute(session=db_session, items=[q1.id, q2.id])

    assert result.total == 2
    assert result.success == 2
    assert result.failed == 0

    # Crucial assertion: enrich_question was called EXACTLY ONCE (for Q2), NOT for Q1!
    assert mock_service.enrich_question.call_count == 1
    call_arg_question = mock_service.enrich_question.call_args[0][0]
    assert call_arg_question.id == q2.id

    # Verify both records exist in DB
    e1 = db_session.query(QuestionEnrichmentModel).filter_by(question_id=q1.id).first()
    e2 = db_session.query(QuestionEnrichmentModel).filter_by(question_id=q2.id).first()
    assert e1 is not None and e1.id == record1.id
    assert e2 is not None

