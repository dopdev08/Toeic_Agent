import io
import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    from app.db.database import Base, engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

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


def create_excel_stream(rows: list[list[object]]) -> io.BytesIO:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def test_import_valid_excel_success():
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "The contract will be signed tomorrow.", "on", "at", "by", "to", "B"],
        ["ETS2026", 5, 102, "All employees must register online.", "early", "easily", "each", "either", "A"],
        [None, None, None, None, None, None, None, None, None],  # Empty row to test ignoring
    ]
    file_stream = create_excel_stream(data)

    response = client.post(
        "/api/v1/imports/questions",
        files={"file": ("questions.xlsx", file_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["test_id"] == "ETS2026"
    assert res_json["total_questions"] == 2
    assert len(res_json["questions"]) == 2
    assert res_json["questions"][0]["question_no"] == 101
    assert res_json["questions"][0]["correct_answer"] == "B"
    assert res_json["questions"][1]["question_no"] == 102
    assert res_json["questions"][1]["correct_answer"] == "A"


def test_import_missing_required_column():
    incomplete_headers = [
        "test_id",
        "part",
        "question_no",
        "question_text",
        "option_a",
        "option_b",
        "option_c",
        # missing option_d and correct_answer
    ]
    data = [
        incomplete_headers,
        ["ETS2026", 5, 101, "Sample text", "optA", "optB", "optC"],
    ]
    file_stream = create_excel_stream(data)

    response = client.post(
        "/api/v1/imports/questions",
        files={"file": ("questions.xlsx", file_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert "Missing required columns" in response.json()["detail"]


def test_import_invalid_file_extension():
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "Sample text", "A", "B", "C", "D", "A"],
    ]
    file_stream = create_excel_stream(data)

    response = client.post(
        "/api/v1/imports/questions",
        files={"file": ("questions.csv", file_stream, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File must have a .xlsx extension"


def test_import_empty_required_field():
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "", "optA", "optB", "optC", "optD", "A"],
    ]
    file_stream = create_excel_stream(data)

    response = client.post(
        "/api/v1/imports/questions",
        files={"file": ("questions.xlsx", file_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert "Row 2: question_text cannot be empty" in response.json()["detail"]


def test_import_invalid_part():
    data = [
        HEADERS,
        ["ETS2026", 8, 101, "Sample text", "A", "B", "C", "D", "A"],
    ]
    file_stream = create_excel_stream(data)

    response = client.post(
        "/api/v1/imports/questions",
        files={"file": ("questions.xlsx", file_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Row 2: part must be an integer from 1 to 7"


def test_import_invalid_correct_answer():
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "Sample text", "A", "B", "C", "D", "E"],
    ]
    file_stream = create_excel_stream(data)

    response = client.post(
        "/api/v1/imports/questions",
        files={"file": ("questions.xlsx", file_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Row 2: correct_answer must be one of A, B, C, D"


def test_import_duplicate_question_no():
    data = [
        HEADERS,
        ["ETS2026", 5, 101, "Question 1", "A", "B", "C", "D", "A"],
        ["ETS2026", 5, 101, "Question 2 with same number", "A", "B", "C", "D", "B"],
    ]
    file_stream = create_excel_stream(data)

    response = client.post(
        "/api/v1/imports/questions",
        files={"file": ("questions.xlsx", file_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert "Row 3: duplicate question_no 101 for test_id 'ETS2026'" in response.json()["detail"]


def test_import_and_query_part5_questions():
    headers_with_explanation = HEADERS + ["explanation"]
    data = [
        headers_with_explanation,
        [
            "PART5_TEST_01",
            5,
            101,
            "Mr. Henderson reviewed the budget proposal ______ presenting it to the board.",
            "before",
            "during",
            "while",
            "between",
            "A",
            "'Before' is followed by a gerund (-ing) indicating prior action.",
        ],
        [
            "PART5_TEST_01",
            5,
            102,
            "The customer service team answered all inquiries ______.",
            "prompt",
            "promptly",
            "promptness",
            "prompting",
            "B",
            "An adverb 'promptly' modifies the verb 'answered'.",
        ],
    ]
    file_stream = create_excel_stream(data)

    # 1. Import Excel and save
    post_res = client.post(
        "/api/v1/imports/questions",
        files={"file": ("part5_questions.xlsx", file_stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert post_res.status_code == 200
    res_data = post_res.json()
    assert res_data["saved_count"] == 2
    assert res_data["questions"][0]["explanation"] == "'Before' is followed by a gerund (-ing) indicating prior action."

    # 2. Query questions by test_id & part
    get_res = client.get("/api/v1/questions?test_id=PART5_TEST_01&part=5")
    assert get_res.status_code == 200
    query_data = get_res.json()
    assert query_data["total"] >= 2
    items = query_data["items"]
    assert any(q["question_no"] == 101 and q["correct_answer"] == "A" for q in items)
    assert any(q["question_no"] == 102 and q["correct_answer"] == "B" for q in items)

    # 3. Query single question by id
    item_101 = next(q for q in items if q["question_no"] == 101)
    single_res = client.get(f"/api/v1/questions/{item_101['id']}")
    assert single_res.status_code == 200
    assert single_res.json()["question_text"] == "Mr. Henderson reviewed the budget proposal ______ presenting it to the board."
    assert single_res.json()["explanation"] == "'Before' is followed by a gerund (-ing) indicating prior action."


def test_duplicate_check_and_skipped_count():
    data_batch1 = [
        HEADERS,
        ["PHASE2_TEST", 5, 101, "Text 1", "A", "B", "C", "D", "A"],
        ["PHASE2_TEST", 5, 102, "Text 2", "A", "B", "C", "D", "B"],
    ]
    stream1 = create_excel_stream(data_batch1)
    res1 = client.post(
        "/api/v1/imports/questions",
        files={"file": ("batch1.xlsx", stream1, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res1.status_code == 200
    json1 = res1.json()
    assert json1["imported_count"] == 2
    assert json1["skipped_count"] == 0

    # Batch 2 contains question 102 (duplicate) and question 103 (new)
    data_batch2 = [
        HEADERS,
        ["PHASE2_TEST", 5, 102, "Text 2 duplicate", "A", "B", "C", "D", "B"],
        ["PHASE2_TEST", 5, 103, "Text 3 new", "A", "B", "C", "D", "C"],
    ]
    stream2 = create_excel_stream(data_batch2)
    res2 = client.post(
        "/api/v1/imports/questions",
        files={"file": ("batch2.xlsx", stream2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res2.status_code == 200
    json2 = res2.json()
    assert json2["imported_count"] == 1
    assert json2["skipped_count"] == 1


def test_transaction_rollback_on_db_error(monkeypatch):
    from app.services.question_import_service import QuestionImportService  # noqa: F401

    def mock_add(self, item):
        raise RuntimeError("Simulated DB failure")

    # Monkeypatch to force failure during model addition
    monkeypatch.setattr("sqlalchemy.orm.Session.add", mock_add)

    data = [
        HEADERS,
        ["FAIL_TEST", 5, 101, "Text will fail", "A", "B", "C", "D", "A"],
    ]
    stream = create_excel_stream(data)
    res = client.post(
        "/api/v1/imports/questions",
        files={"file": ("fail.xlsx", stream, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 500
    assert "Database transaction error" in res.json()["detail"]


