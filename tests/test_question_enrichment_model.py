import pytest
from sqlalchemy.exc import IntegrityError

from app.db.database import Base, SessionLocal, engine
from app.models.question import Question
from app.models.question_enrichment import QuestionEnrichment


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
        question_text="Mr. Henderson reviewed the budget proposal ______ presenting it to the board.",
        option_a="before",
        option_b="during",
        option_c="while",
        option_d="between",
        correct_answer="A",
        explanation="Before is followed by a gerund.",
    )
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    return q


@pytest.fixture
def sample_enrichment_payload(sample_question):
    return {
        "question_id": sample_question.id,
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
        "status": "PENDING",
    }


def test_create_question_and_enrichment_successfully(
    db_session, sample_question, sample_enrichment_payload
):
    enrichment = QuestionEnrichment(**sample_enrichment_payload)
    db_session.add(enrichment)
    db_session.commit()

    db_session.refresh(sample_question)
    db_session.refresh(enrichment)

    assert sample_question.id is not None
    assert enrichment.id is not None
    assert enrichment.question_id == sample_question.id
    assert enrichment.grammar_topic == "Verb pattern"


def test_one_to_one_relationship(
    db_session, sample_question, sample_enrichment_payload
):
    enrichment = QuestionEnrichment(**sample_enrichment_payload)
    db_session.add(enrichment)
    db_session.commit()

    # Expire and reload to ensure clean query from DB
    db_session.expire_all()

    fetched_question = db_session.get(Question, sample_question.id)
    fetched_enrichment = db_session.get(QuestionEnrichment, enrichment.id)

    assert fetched_question is not None
    assert fetched_enrichment is not None
    assert fetched_question.enrichment is not None
    assert fetched_question.enrichment.id == fetched_enrichment.id
    assert fetched_enrichment.question is not None
    assert fetched_enrichment.question.id == fetched_question.id


def test_question_id_uniqueness_rejected(
    db_session, sample_question, sample_enrichment_payload
):
    enrichment_a = QuestionEnrichment(**sample_enrichment_payload)
    db_session.add(enrichment_a)
    db_session.commit()

    # Attempt to add a second enrichment referencing the same question_id
    duplicate_payload = dict(sample_enrichment_payload)
    duplicate_payload["grammar_topic"] = "Another topic"
    enrichment_b = QuestionEnrichment(**duplicate_payload)
    db_session.add(enrichment_b)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    "required_field",
    [
        "question_id",
        "grammar_topic",
        "sentence_structure",
        "pattern",
        "vocabulary",
        "explanation",
        "distractor_analysis",
        "difficulty",
        "status",
    ],
)
def test_required_fields_disallow_null(
    db_session, sample_enrichment_payload, required_field
):
    payload = dict(sample_enrichment_payload)
    payload[required_field] = None

    with pytest.raises((IntegrityError, ValueError)):
        enrichment = QuestionEnrichment(**payload)
        db_session.add(enrichment)
        db_session.commit()
    db_session.rollback()


def test_json_storage_preserves_python_structures(
    db_session, sample_question, sample_enrichment_payload
):
    vocab_data = [
        {
            "word": "encourage",
            "meaning": "khuyến khích",
            "part_of_speech": "verb",
        }
    ]
    distractor_data = {
        "A": "Incorrect",
        "B": "Correct",
        "C": "Incorrect",
        "D": "Incorrect",
    }
    sample_enrichment_payload["vocabulary"] = vocab_data
    sample_enrichment_payload["distractor_analysis"] = distractor_data

    enrichment = QuestionEnrichment(**sample_enrichment_payload)
    db_session.add(enrichment)
    db_session.commit()

    db_session.expire_all()
    loaded = db_session.get(QuestionEnrichment, enrichment.id)

    assert loaded is not None
    assert isinstance(loaded.vocabulary, list)
    assert len(loaded.vocabulary) == 1
    assert loaded.vocabulary[0]["word"] == "encourage"
    assert loaded.vocabulary[0]["meaning"] == "khuyến khích"
    assert loaded.vocabulary[0]["part_of_speech"] == "verb"

    assert isinstance(loaded.distractor_analysis, dict)
    assert loaded.distractor_analysis["A"] == "Incorrect"
    assert loaded.distractor_analysis["B"] == "Correct"
    assert loaded.distractor_analysis["C"] == "Incorrect"
    assert loaded.distractor_analysis["D"] == "Incorrect"


@pytest.mark.parametrize("valid_difficulty", ["easy", "medium", "hard"])
def test_difficulty_valid_values(
    db_session, sample_question, sample_enrichment_payload, valid_difficulty
):
    payload = dict(sample_enrichment_payload)
    payload["difficulty"] = valid_difficulty
    enrichment = QuestionEnrichment(**payload)
    db_session.add(enrichment)
    db_session.commit()
    db_session.refresh(enrichment)
    assert enrichment.difficulty == valid_difficulty


def test_difficulty_invalid_value_rejected(sample_enrichment_payload):
    payload = dict(sample_enrichment_payload)
    payload["difficulty"] = "very_easy"
    with pytest.raises((ValueError, IntegrityError)):
        QuestionEnrichment(**payload)


@pytest.mark.parametrize(
    "valid_status", ["PENDING", "PROCESSING", "COMPLETED", "FAILED"]
)
def test_status_valid_values(
    db_session, sample_question, sample_enrichment_payload, valid_status
):
    payload = dict(sample_enrichment_payload)
    payload["status"] = valid_status
    enrichment = QuestionEnrichment(**payload)
    db_session.add(enrichment)
    db_session.commit()
    db_session.refresh(enrichment)
    assert enrichment.status == valid_status


def test_status_defaults_to_pending(
    db_session, sample_question, sample_enrichment_payload
):
    payload = dict(sample_enrichment_payload)
    payload.pop("status", None)
    enrichment = QuestionEnrichment(**payload)
    assert enrichment.status == "PENDING"

    db_session.add(enrichment)
    db_session.commit()
    db_session.refresh(enrichment)
    assert enrichment.status == "PENDING"


def test_status_invalid_value_rejected(sample_enrichment_payload):
    payload = dict(sample_enrichment_payload)
    payload["status"] = "UNKNOWN_STATUS"
    with pytest.raises((ValueError, IntegrityError)):
        QuestionEnrichment(**payload)
