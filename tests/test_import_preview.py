import io
from typing import Any
import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, get_db
from app.main import app
from app.models.question import Question

client = TestClient(app)

HEADERS = [
    "test_id",
    "part",
    "question_no",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_answer",
]


@pytest.fixture
def isolated_db():
    """Create an isolated, in-memory SQLite database for testing without touching toeic_agent.db."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        session.close()
        app.dependency_overrides.pop(get_db, None)
        test_engine.dispose()


def create_excel_stream(rows: list[list[Any]]) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "questions"
    for row in rows:
        ws.append(row)
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def test_preview_parses_valid_workbook_without_database_writes(isolated_db):
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "The lecture will take place at 6:00 P.M.", "across", "after", "inside", "among", "B"],
        ["ETS2026", 5, 102, "The antique shop will close down next month.", "last", "lasts", "lasted", "lasting", "A"],
        ["ETS2026", 5, 103, "Residents will receive an online update.", "update", "change", "payment", "request", "A"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions/preview",
        files={"file": ("valid_preview.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "valid_preview.xlsx"
    assert body["test_id"] == "ETS2026"
    assert body["part"] == 5
    assert body["min_question_no"] == 101
    assert body["max_question_no"] == 103
    assert body["missing_question_numbers"] == []

    summary = body["summary"]
    assert summary["total_rows"] == 3
    assert summary["valid_questions"] == 3
    assert summary["invalid_rows"] == 0
    assert summary["to_insert"] == 3
    assert summary["unchanged"] == 0
    assert summary["to_update"] == 0
    assert summary["conflicts"] == 0

    assert len(body["questions"]) == 3
    for q_item in body["questions"]:
        assert q_item["action"] == "INSERT"
        assert q_item["question_text"] is not None
        assert q_item["option_a"] is not None
        assert q_item["option_b"] is not None
        assert q_item["option_c"] is not None
        assert q_item["option_d"] is not None
        assert q_item["correct_answer"] in ("A", "B", "C", "D")

    # Strict check: Preview MUST NEVER write to database
    assert isolated_db.query(Question).count() == 0


def test_preview_detects_invalid_and_missing_answers_with_row_identifiers(isolated_db):
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "Valid question text.", "A", "B", "C", "D", "A"],
        ["ETS2026", 5, 102, "Question with invalid answer.", "A", "B", "C", "D", "Z"],  # Invalid
        ["ETS2026", 5, 103, "Question with empty answer.", "A", "B", "C", "D", ""],    # Missing
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions/preview",
        files={"file": ("invalid_answers.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["valid_questions"] == 1
    assert body["summary"]["invalid_rows"] == 2

    errors = body["validation_errors"]
    assert len(errors) == 2

    # Check row identifiers
    row_numbers = [e["row_no"] for e in errors]
    assert 3 in row_numbers
    assert 4 in row_numbers

    err_102 = next(e for e in errors if e["row_no"] == 3)
    assert err_102["question_no"] == 102
    assert err_102["field"] == "correct_answer"
    assert "must be one of a, b, c, d" in err_102["error"].lower()

    err_103 = next(e for e in errors if e["row_no"] == 4)
    assert err_103["question_no"] == 103
    assert err_103["field"] == "correct_answer"

    # Preview must not write
    assert isolated_db.query(Question).count() == 0


def test_preview_detects_duplicate_question_numbers_within_workbook(isolated_db):
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "First instance of 101", "A", "B", "C", "D", "A"],
        ["ETS2026", 5, 101, "Duplicate instance of 101", "A", "B", "C", "D", "B"],  # Duplicate row
        ["ETS2026", 5, 102, "Valid 102", "A", "B", "C", "D", "C"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions/preview",
        files={"file": ("duplicates.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["duplicates_in_file"] == 1

    dup = body["duplicates_in_file"][0]
    assert dup["question_no"] == 101
    assert dup["first_row"] == 2
    assert dup["duplicate_row"] == 3

    assert any("Duplicate question_no 101" in e["error"] for e in body["validation_errors"])
    assert isolated_db.query(Question).count() == 0


def test_preview_detects_gaps_in_question_number_range(isolated_db):
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "Text 101", "A", "B", "C", "D", "A"],
        ["ETS2026", 5, 102, "Text 102", "A", "B", "C", "D", "B"],
        # Missing 103
        ["ETS2026", 5, 104, "Text 104", "A", "B", "C", "D", "C"],
        ["ETS2026", 5, 105, "Text 105", "A", "B", "C", "D", "D"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions/preview",
        files={"file": ("range_gap.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["min_question_no"] == 101
    assert body["max_question_no"] == 105
    assert body["missing_question_numbers"] == [103]


def test_preview_detects_existing_records_unchanged_vs_conflicting_diff(isolated_db):
    # Setup existing database state
    q101 = Question(
        test_id="ETS2026",
        part=5,
        question_no=101,
        question_text="Existing sentence 101.",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="B",
        explanation=None,
    )
    q102 = Question(
        test_id="ETS2026",
        part=5,
        question_no=102,
        question_text="Existing sentence 102.",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="A",
        explanation="Exp 102",
    )
    isolated_db.add_all([q101, q102])
    isolated_db.commit()

    # Incoming workbook:
    # Q101: unchanged (identical)
    # Q102: conflict (different answer key C instead of A, and updated text)
    # Q103: new (to insert)
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "Existing sentence 101.", "A", "B", "C", "D", "B"],
        ["ETS2026", 5, 102, "Modified sentence 102.", "A", "B", "C", "D", "C"],
        ["ETS2026", 5, 103, "New question 103.", "A", "B", "C", "D", "D"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions/preview",
        files={"file": ("compare.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200
    body = res.json()
    summary = body["summary"]
    assert summary["unchanged"] == 1
    assert summary["to_update"] == 1
    assert summary["to_insert"] == 1
    assert summary["conflicts"] == 1

    # Check before-and-after change diff for Q102
    assert len(body["changes"]) == 1
    ch = body["changes"][0]
    assert ch["question_no"] == 102
    assert ch["old_correct_answer"] == "A"
    assert ch["new_correct_answer"] == "C"
    assert ch["is_answer_change"] is True

    diff_fields = {d["field"]: d for d in ch["diffs"]}
    assert "correct_answer" in diff_fields
    assert diff_fields["correct_answer"]["old_value"] == "A"
    assert diff_fields["correct_answer"]["new_value"] == "C"
    assert "question_text" in diff_fields
    assert diff_fields["question_text"]["old_value"] == "Existing sentence 102."
    assert diff_fields["question_text"]["new_value"] == "Modified sentence 102."

    # Check authoritative confirmation flag
    assert len(body["requires_confirmation"]) == 1
    req = body["requires_confirmation"][0]
    assert req["question_no"] == 102
    assert req["old_answer"] == "A"
    assert req["new_answer"] == "C"
    assert "requires confirmation" in req["reason"].lower()

    # Database still has 2 records, completely unchanged
    assert isolated_db.query(Question).count() == 2
    reloaded_q102 = isolated_db.query(Question).filter(Question.question_no == 102).first()
    assert reloaded_q102.correct_answer == "A"


def test_no_silent_overwrite_when_allow_updates_false(isolated_db):
    q102 = Question(
        test_id="ETS2026",
        part=5,
        question_no=102,
        question_text="Original text.",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="A",
    )
    isolated_db.add(q102)
    isolated_db.commit()

    # Conflicting workbook has answer C
    data = [
        HEADERS,
        ["ETS2026", 5, 102, "Modified text.", "A", "B", "C", "D", "C"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions?allow_updates=false",
        files={"file": ("no_overwrite.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["imported_count"] == 0
    assert body["skipped_count"] == 1
    assert body["updated_count"] == 0

    # Ensure existing record in DB was NOT overwritten
    isolated_db.expire_all()
    db_item = isolated_db.query(Question).filter(Question.question_no == 102).first()
    assert db_item.correct_answer == "A"
    assert db_item.question_text == "Original text."


def test_safe_atomic_update_when_allow_updates_true(isolated_db):
    q102 = Question(
        test_id="ETS2026",
        part=5,
        question_no=102,
        question_text="Original text.",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="A",
    )
    isolated_db.add(q102)
    isolated_db.commit()

    data = [
        HEADERS,
        ["ETS2026", 5, 102, "Updated text.", "A", "B", "C", "D", "C"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions?allow_updates=true",
        files={"file": ("allow_update.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["imported_count"] == 0
    assert body["updated_count"] == 1
    assert body["saved_count"] == 1

    # Record was updated in place
    isolated_db.expire_all()
    db_item = isolated_db.query(Question).filter(Question.question_no == 102).first()
    assert db_item.correct_answer == "C"
    assert db_item.question_text == "Updated text."


def test_correct_handling_of_q107_c_and_q109_a_in_fixture(isolated_db):
    # Pre-populate with historical incorrect keys (Q107=D, Q109=D)
    q107 = Question(
        test_id="ETS2026",
        part=5,
        question_no=107,
        question_text="In October, Mr. Sakamoto will leave for New Zealand _____ will oversee the opening of the new Auckland branch.",
        option_a="because",
        option_b="in addition",
        option_c="and",
        option_d="prior to",
        correct_answer="D",  # Historical error
    )
    q109 = Question(
        test_id="ETS2026",
        part=5,
        question_no=109,
        question_text="Dynart, Inc. continuously _____ new ways to reduce its use of plastics.",
        option_a="seeks",
        option_b="seeker",
        option_c="to seek",
        option_d="seeking",
        correct_answer="D",  # Historical error
    )
    isolated_db.add_all([q107, q109])
    isolated_db.commit()

    # Workbook has user-confirmed authoritative answers (Q107=C, Q109=A)
    data = [
        HEADERS,
        ["ETS2026", 5, 107, q107.question_text, "because", "in addition", "and", "prior to", "C"],
        ["ETS2026", 5, 109, q109.question_text, "seeks", "seeker", "to seek", "seeking", "A"],
    ]
    stream = create_excel_stream(data)

    # 1. Preview
    res_prev = client.post(
        "/api/v1/imports/questions/preview",
        files={"file": ("reconcile_fixture.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res_prev.status_code == 200
    prev_body = res_prev.json()
    assert prev_body["summary"]["conflicts"] == 2
    assert len(prev_body["requires_confirmation"]) == 2

    # Check Q107 flagged diff
    q107_conf = next(c for c in prev_body["requires_confirmation"] if c["question_no"] == 107)
    assert q107_conf["old_answer"] == "D"
    assert q107_conf["new_answer"] == "C"

    # Check Q109 flagged diff
    q109_conf = next(c for c in prev_body["requires_confirmation"] if c["question_no"] == 109)
    assert q109_conf["old_answer"] == "D"
    assert q109_conf["new_answer"] == "A"

    # 2. Apply import with allow_updates=True
    stream.seek(0)
    res_import = client.post(
        "/api/v1/imports/questions?allow_updates=true",
        files={"file": ("reconcile_fixture.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res_import.status_code == 200
    assert res_import.json()["updated_count"] == 2

    # Check DB now stores C and A
    isolated_db.expire_all()
    assert isolated_db.query(Question).filter(Question.question_no == 107).first().correct_answer == "C"
    assert isolated_db.query(Question).filter(Question.question_no == 109).first().correct_answer == "A"


def test_atomic_rollback_on_persistence_failure(isolated_db, monkeypatch):
    q101 = Question(
        test_id="ETS2026",
        part=5,
        question_no=101,
        question_text="Existing sentence 101.",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="A",
    )
    isolated_db.add(q101)
    isolated_db.commit()

    # Simulate database crash during commit
    def mock_commit():
        raise RuntimeError("Forced DB commit crash")

    monkeypatch.setattr(isolated_db, "commit", mock_commit)

    data = [
        HEADERS,
        ["ETS2026", 5, 102, "New sentence 102.", "A", "B", "C", "D", "B"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions",
        files={"file": ("crash.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 500

    # Ensure rollback kept initial state intact
    isolated_db.expire_all()
    assert isolated_db.query(Question).count() == 1
    assert isolated_db.query(Question).filter(Question.question_no == 102).first() is None


def test_preservation_of_unrelated_database_records(isolated_db):
    unrelated = Question(
        test_id="OTHER_TEST",
        part=5,
        question_no=101,
        question_text="Unrelated test question.",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="A",
    )
    isolated_db.add(unrelated)
    isolated_db.commit()

    data = [
        HEADERS,
        ["ETS2026", 5, 101, "ETS2026 text.", "A", "B", "C", "D", "B"],
    ]
    stream = create_excel_stream(data)

    res = client.post(
        "/api/v1/imports/questions",
        files={"file": ("import_ets.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 200

    isolated_db.expire_all()
    # Both records exist; OTHER_TEST is completely unaffected
    assert isolated_db.query(Question).count() == 2
    unrelated_reloaded = isolated_db.query(Question).filter(Question.test_id == "OTHER_TEST").first()
    assert unrelated_reloaded.correct_answer == "A"
    assert unrelated_reloaded.question_text == "Unrelated test question."
