from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.db.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment as QuestionEnrichmentModel
from app.services.gemini_client import GeminiClient

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


@pytest.fixture
def sample_question(db_session):
    q = Question(
        test_id="ETS2026_TEST1",
        part=5,
        question_no=105,
        question_text="The committee will announce the winner ______ noon tomorrow.",
        option_a="by",
        option_b="at",
        option_c="during",
        option_d="with",
        correct_answer="B",
        explanation="Time preposition question.",
    )
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    return q


@pytest.fixture
def sample_question_with_enrichment(db_session, sample_question):
    enrichment = QuestionEnrichmentModel(
        question_id=sample_question.id,
        grammar_topic="Prepositions of Time",
        sentence_structure="Subject + Modal Verb + Main Verb + Object + Prepositional Phrase",
        pattern="Preposition + specific clock time (at noon)",
        vocabulary=[
            {"word": "announce", "meaning": "thông báo", "part_of_speech": "verb"},
            {"word": "committee", "meaning": "ủy ban", "part_of_speech": "noun"},
        ],
        explanation="'At' is specifically used with exact clock times and points in time like 'noon'.",
        distractor_analysis={
            "A": "'By' suggests a deadline, not a specific point of time occurrence here.",
            "B": "Correct. 'At' collocates with 'noon'.",
            "C": "'During' requires a time period duration, not an instantaneous clock point.",
            "D": "'With' cannot indicate specific time of day.",
        },
        difficulty="easy",
        status="COMPLETED",
    )
    db_session.add(enrichment)
    db_session.commit()
    db_session.refresh(sample_question)
    return sample_question


def test_get_existing_question_with_enrichment_returns_200(sample_question_with_enrichment):
    """Test 1 & 3 & 4: Existing question with enrichment returns 200 with correct question and enrichment data."""
    q_id = sample_question_with_enrichment.id
    response = client.get(f"/api/v1/questions/{q_id}")

    assert response.status_code == 200
    data = response.json()

    # Question fields verification
    assert data["id"] == q_id
    assert data["test_id"] == "ETS2026_TEST1"
    assert data["part"] == 5
    assert data["question_no"] == 105
    assert data["question_text"] == "The committee will announce the winner ______ noon tomorrow."
    assert data["option_a"] == "by"
    assert data["option_b"] == "at"
    assert data["option_c"] == "during"
    assert data["option_d"] == "with"
    assert data["correct_answer"] == "B"
    assert data["explanation"] == "Time preposition question."

    # Enrichment fields verification
    enr = data["enrichment"]
    assert enr is not None
    assert enr["grammar_topic"] == "Prepositions of Time"
    assert enr["sentence_structure"] == "Subject + Modal Verb + Main Verb + Object + Prepositional Phrase"
    assert enr["pattern"] == "Preposition + specific clock time (at noon)"
    assert enr["difficulty"] == "easy"
    assert enr["explanation"] == "'At' is specifically used with exact clock times and points in time like 'noon'."
    assert len(enr["vocabulary"]) == 2
    assert enr["vocabulary"][0] == {"word": "announce", "meaning": "thông báo", "part_of_speech": "verb"}
    assert enr["distractor_analysis"]["B"] == "Correct. 'At' collocates with 'noon'."

    # Ensure internal DB fields are not exposed in enrichment schema
    assert "status" not in enr
    assert "id" not in enr
    assert "created_at" not in enr


def test_get_existing_question_without_enrichment_returns_200_and_null_enrichment(sample_question):
    """Test 2: Existing question without enrichment returns 200 with enrichment null."""
    response = client.get(f"/api/v1/questions/{sample_question.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == sample_question.id
    assert data["test_id"] == "ETS2026_TEST1"
    assert data["question_no"] == 105
    assert data["enrichment"] is None


def test_get_non_existing_question_returns_404(db_session):
    """Test 5: Non-existing question returns HTTP 404."""
    response = client.get("/api/v1/questions/999999")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "999999" in data["detail"]


def test_endpoint_does_not_call_llm(sample_question):
    """Test 6: Read-only endpoint must never invoke GeminiClient."""
    with patch.object(GeminiClient, "generate", side_effect=AssertionError("LLM was invoked!")) as mock_llm:
        response = client.get(f"/api/v1/questions/{sample_question.id}")
        assert response.status_code == 200
        assert mock_llm.call_count == 0


def test_endpoint_does_not_create_enrichment(db_session, sample_question):
    """Test 7: Read-only endpoint must never create enrichment in DB."""
    # Verify count is 0 before
    count_before = db_session.scalar(
        select(func.count()).select_from(QuestionEnrichmentModel).where(QuestionEnrichmentModel.question_id == sample_question.id)
    )
    assert count_before == 0

    response = client.get(f"/api/v1/questions/{sample_question.id}")
    assert response.status_code == 200

    # Verify count is still 0 after
    count_after = db_session.scalar(
        select(func.count()).select_from(QuestionEnrichmentModel).where(QuestionEnrichmentModel.question_id == sample_question.id)
    )
    assert count_after == 0


def test_endpoint_does_not_commit_or_rollback(sample_question):
    """Test 8 & 9: Read-only endpoint must not explicitly commit or rollback."""
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

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get(f"/api/v1/questions/{sample_question.id}")
        assert response.status_code == 200

        # Neither commit nor rollback should be explicitly called by the endpoint
        assert spy_commit.call_count == 0
        assert spy_rollback.call_count == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
        real_session.close()
