# Danh mục API Hệ thống Thực tế (API Inventory)

> **File:** `docs/system-analysis/api-inventory.md`  
> **Phương pháp phân tích:** Trích xuất toàn bộ router đăng ký trong `app/main.py`, tham số đường dẫn, query params, request body, response model và error handler.

---

## 1. Bảng Tổng hợp Toàn bộ REST API Hiện có

Hiện tại, ứng dụng FastAPI đăng ký chính xác **6 endpoints** phân bổ trong 3 router:

| STT | HTTP Method | Endpoint URL | Chức năng Nghiệp vụ | Request Schema / Params | Response Schema | Service / Workflow được gọi | Trạng thái | File Bằng chứng |
|---|---|---|---|---|---|---|---|---|
| 1 | `POST` | `/api/v1/imports/questions/preview` | Xem trước kết quả import Excel & so sánh diff với DB (Read-Only) | `file: UploadFile (.xlsx)` | `QuestionImportPreviewResponse` | `ExcelParser.generate_import_preview` | `IMPLEMENTED` | [app/api/import_questions.py:L20](file:///d:/project/Toeic_Agent/app/api/import_questions.py#L20) |
| 2 | `POST` | `/api/v1/imports/questions` | Import chính thức danh sách câu hỏi Part 5 từ Excel vào Database | `file: UploadFile (.xlsx)`, `allow_updates: bool = False` | `QuestionImportResponse` | `QuestionImportService.import_questions` | `IMPLEMENTED` | [app/api/import_questions.py:L51](file:///d:/project/Toeic_Agent/app/api/import_questions.py#L51) |
| 3 | `GET` | `/api/v1/questions` | Lấy danh sách câu hỏi kèm lọc đề, phần thi và phân trang | `test_id: str?`, `part: int = 5`, `limit: int = 50`, `offset: int = 0` | `dict{"total", "limit", "offset", "items": List[QuestionDetail]}` | `QuestionImportService.get_questions` & `count_questions` | `IMPLEMENTED` | [app/api/questions.py:L36](file:///d:/project/Toeic_Agent/app/api/questions.py#L36) |
| 4 | `GET` | `/api/v1/questions/{question_id}` | Lấy chi tiết một câu hỏi kèm phân tích làm giàu (nếu có) | Path: `question_id: int` | `QuestionWithEnrichmentResponse` | `QuestionRepository.get_question_by_id` | `IMPLEMENTED` | [app/api/questions.py:L56](file:///d:/project/Toeic_Agent/app/api/questions.py#L56) |
| 5 | `POST` | `/api/v1/questions/{question_id}/enrich` | Kích hoạt AI làm giàu sư phạm cho 1 câu hỏi & lưu DB | Path: `question_id: int`, Query: `force: bool = False` | `QuestionEnrichmentResponse` | `EnrichmentWorkflow.execute` | `IMPLEMENTED` | [app/api/questions.py:L102](file:///d:/project/Toeic_Agent/app/api/questions.py#L102) |
| 6 | `POST` | `/api/v1/enrichments/batch` | Làm giàu tuần tự hàng loạt theo danh sách ID câu hỏi | Body: `BatchEnrichmentRequest (question_ids: List[int])` | `BatchEnrichmentResponse` | `BatchEnrichmentWorkflow.execute` | `IMPLEMENTED` | [app/api/enrichments.py:L20](file:///d:/project/Toeic_Agent/app/api/enrichments.py#L20) |

---

## 2. Chi tiết Từng Endpoint

### 2.1. `POST /api/v1/imports/questions/preview`
- **Mục đích:** Hỗ trợ người dùng kiểm tra file Excel trước khi lưu. Phát hiện lỗi cú pháp, thiếu cột, hàng trống, câu trùng số thứ tự trong file, và phát hiện thay đổi đáp án đúng (Answer Key Conflict) so với database.
- **Request:**
  - Content-Type: `multipart/form-data`
  - Body: `file: UploadFile` (bắt buộc đuôi `.xlsx`).
- **Response Model:** `QuestionImportPreviewResponse` (HTTP 200)
  ```json
  {
    "filename": "part5_sample.xlsx",
    "test_id": "ETS_2026_TEST_01",
    "part": 5,
    "min_question_no": 101,
    "max_question_no": 105,
    "missing_question_numbers": [],
    "summary": {
      "total_rows": 5,
      "valid_questions": 5,
      "invalid_rows": 0,
      "to_insert": 0,
      "unchanged": 5,
      "to_update": 0,
      "conflicts": 0,
      "duplicates_in_file": 0
    },
    "validation_errors": [],
    "duplicates_in_file": [],
    "changes": [],
    "requires_confirmation": [],
    "questions": [...]
  }
  ```
- **Xử lý Mã Lỗi:**
  - `400 Bad Request`: Tệp không có đuôi `.xlsx`, file rỗng, thiếu một trong các cột bắt buộc (`REQUIRED_COLUMNS`), file hỏng.
  - `500 Internal Server Error`: Lỗi hệ thống bất ngờ khi đọc streaming byte.
- **Bằng chứng Code:** [app/api/import_questions.py:L20-L49](file:///d:/project/Toeic_Agent/app/api/import_questions.py#L20-L49), [app/services/excel_parser.py:L140-L521](file:///d:/project/Toeic_Agent/app/services/excel_parser.py#L140-L521).

---

### 2.2. `POST /api/v1/imports/questions`
- **Mục đích:** Thực thi import thực tế vào bảng `questions`. Hỗ trợ chế độ bỏ qua (`allow_updates=False`) hoặc cập nhật ghi đè in-place (`allow_updates=True`).
- **Request:**
  - Content-Type: `multipart/form-data`
  - Query Parameter: `allow_updates: bool = False`
  - Body: `file: UploadFile`
- **Response Model:** `QuestionImportResponse` (HTTP 200)
  ```json
  {
    "test_id": "ETS_2026_TEST_01",
    "total_questions": 5,
    "imported_count": 5,
    "skipped_count": 0,
    "updated_count": 0,
    "saved_count": 5,
    "questions": [...],
    "conflicts": []
  }
  ```
- **Xử lý Mã Lỗi:**
  - `400 Bad Request`: Lỗi định dạng Excel hoặc dữ liệu câu hỏi vi phạm Pydantic `QuestionItem`.
  - `500 Internal Server Error`: Lỗi transaction cơ sở dữ liệu (tự động rollback toàn bộ batch).
- **Bằng chứng Code:** [app/api/import_questions.py:L51-L95](file:///d:/project/Toeic_Agent/app/api/import_questions.py#L51-L95), [app/services/question_import_service.py:L11-L91](file:///d:/project/Toeic_Agent/app/services/question_import_service.py#L11-L91).

---

### 2.3. `GET /api/v1/questions`
- **Mục đích:** Truy vấn danh sách câu hỏi từ Question Bank, hỗ trợ lọc theo mã đề thi và phần thi, có phân trang an toàn.
- **Request Parameters (Query):**
  - `test_id: str | None = None`
  - `part: int | None = 5` (mặc định lấy Part 5)
  - `limit: int = 50` ($1 \le limit \le 200$)
  - `offset: int = 0` ($offset \ge 0$)
- **Response (HTTP 200):**
  ```json
  {
    "total": 30,
    "limit": 50,
    "offset": 0,
    "items": [
      {
        "id": 1,
        "test_id": "ETS_2026_TEST_01",
        "part": 5,
        "question_no": 101,
        "question_text": "Customer satisfaction is ______ important to the management of Grand Hotel.",
        "option_a": "extreme",
        "option_b": "extremely",
        "option_c": "extremist",
        "option_d": "extremity",
        "correct_answer": "B",
        "explanation": "Phó từ 'extremely' đứng trước tính từ 'important' để bổ nghĩa.",
        "created_at": "2026-10-25T17:00:00"
      }
    ]
  }
  ```
- **Xử lý Mã Lỗi:**
  - `422 Unprocessable Entity`: Khi `limit` hoặc `offset` nằm ngoài khoảng ràng buộc.
- **Bằng chứng Code:** [app/api/questions.py:L36-L54](file:///d:/project/Toeic_Agent/app/api/questions.py#L36-L54).

---

### 2.4. `GET /api/v1/questions/{question_id}`
- **Mục đích:** Lấy toàn bộ thông tin của một câu hỏi cụ thể, kèm theo bản ghi phân tích làm giàu (nếu câu hỏi đó đã được enrich).
- **Request Parameters (Path):** `question_id: int`
- **Response Model:** `QuestionWithEnrichmentResponse` (HTTP 200)
  ```json
  {
    "id": 1,
    "test_id": "ETS_2026_TEST_01",
    "part": 5,
    "question_no": 101,
    "question_text": "Customer satisfaction is ______ important to the management of Grand Hotel.",
    "option_a": "extreme",
    "option_b": "extremely",
    "option_c": "extremist",
    "option_d": "extremity",
    "correct_answer": "B",
    "explanation": "Phó từ 'extremely' đứng trước tính từ 'important' để bổ nghĩa.",
    "created_at": "2026-10-25T17:00:00",
    "enrichment": null
  }
  ```
- **Xử lý Mã Lỗi:**
  - `404 Not Found`: Không tìm thấy câu hỏi tương ứng trong bảng `questions`.
- **Bằng chứng Code:** [app/api/questions.py:L56-L100](file:///d:/project/Toeic_Agent/app/api/questions.py#L56-L100).

---

### 2.5. `POST /api/v1/questions/{question_id}/enrich`
- **Mục đích:** Thực thi quy trình làm giàu AI hoàn chỉnh cho một câu hỏi: trích xuất câu hỏi $\to$ tạo prompt $\to$ gọi LLM $\to$ sanitize JSON $\to$ thẩm định schema Pydantic $\to$ kiểm định chất lượng ngôn ngữ (Grounding, CJK, Contradiction) $\to$ lưu trữ vào DB.
- **Request:**
  - Path: `question_id: int`
  - Query: `force: bool = False` (nếu `True`, buộc gọi lại LLM và ghi đè bản ghi cũ).
- **Response Model:** `QuestionEnrichmentResponse` (HTTP 200)
  ```json
  {
    "question_id": 1,
    "grammar_topic": "Word Form (Adverb modifying Adjective)",
    "sentence_structure": "S + V + [adverb] + adj + prep + O",
    "pattern": "adverb + adjective",
    "vocabulary": [
      {
        "word": "satisfaction",
        "meaning": "sự hài lòng",
        "part_of_speech": "noun"
      },
      {
        "word": "extremely",
        "meaning": "vô cùng, cực kỳ",
        "part_of_speech": "adverb"
      }
    ],
    "explanation": "Cần một phó từ đứng trước tính từ 'important' để bổ nghĩa cho tính từ đó. Do đó 'extremely' là đáp án đúng.",
    "distractor_analysis": {
      "A": "extreme là tính từ, không thể đứng trước bổ nghĩa cho tính từ important.",
      "B": "extremely là phó từ phù hợp đứng trước bổ nghĩa cho tính từ important.",
      "C": "extremist là danh từ chỉ người (người cực đoan), không hợp ngữ nghĩa và ngữ pháp.",
      "D": "extremity là danh từ chỉ sự cực độ, không đứng ở vị trí bổ nghĩa cho tính từ."
    },
    "difficulty": "easy"
  }
  ```
- **Xử lý Toàn diện Mã Lỗi (Comprehensive Error Mapping):**
  - `401 Unauthorized`: `LLMAuthenticationError` (Thiếu hoặc sai GEMINI_API_KEY).
  - `404 Not Found`: `Question with ID {question_id} not found`.
  - `503 Service Unavailable`: `LLMConnectionError` (Lỗi mạng hoặc dịch vụ Gemini tạm thời quá tải).
  - `504 Gateway Timeout`: `LLMTimeoutError` (Mô hình LLM suy luận quá thời gian quy định).
  - `502 Bad Gateway`:
    - `LLMProviderError` (Lỗi HTTP/API từ phía nhà cung cấp LLM).
    - `EnrichmentJSONDecodeError` (LLM không trả về JSON hợp lệ sau khi đã sanitize).
    - `EnrichmentValidationError` (JSON trả về không đúng cấu trúc `QuestionEnrichment`).
    - `EnrichmentQualityError` (Vi phạm quy tắc Grounding, Mâu thuẫn đáp án hoặc Rò rỉ chữ CJK).
  - `409 Conflict`: `IntegrityError` (Xung đột khóa ngoại hoặc khóa duy nhất trong DB).
  - `500 Internal Server Error`: Lỗi hệ thống không dự liệu được.
- **Bằng chứng Code:** [app/api/questions.py:L102-L177](file:///d:/project/Toeic_Agent/app/api/questions.py#L102-L177).

---

### 2.6. `POST /api/v1/enrichments/batch`
- **Mục đích:** Làm giàu hàng loạt cho danh sách ID câu hỏi một cách tuần tự và an toàn, hỗ trợ cô lập lỗi độc lập cho từng câu.
- **Request Body:** `BatchEnrichmentRequest`
  ```json
  {
    "question_ids": [1, 2, 3]
  }
  ```
  *(Có validator kiểm tra danh sách không rỗng, các ID phải là số nguyên dương $> 0$ và không bị trùng lặp).*
- **Response Model:** `BatchEnrichmentResponse` (HTTP 200)
  ```json
  {
    "total": 3,
    "success": 2,
    "failed": 1,
    "results": [
      {
        "question_id": 1,
        "status": "COMPLETED"
      },
      {
        "question_id": 2,
        "status": "FAILED",
        "error": "Ungrounded vocabulary: Vocabulary item 'unforeseen' is not grounded in question text or options."
      },
      {
        "question_id": 3,
        "status": "COMPLETED"
      }
    ]
  }
  ```
- **Xử lý Mã Lỗi:**
  - `422 Unprocessable Entity`: Body rỗng, ID $\le 0$, hoặc ID trùng lặp.
- **Bằng chứng Code:** [app/api/enrichments.py:L20-L54](file:///d:/project/Toeic_Agent/app/api/enrichments.py#L20-L54).

---

## 3. Khoảng trống Danh mục API (Missing APIs for AI Tutor)

Để hoàn thiện ứng dụng TOEIC AI Tutor theo nghiệp vụ học tập, hệ thống còn thiếu toàn bộ các nhóm API sau:

| Nhóm API Còn Thiếu | Endpoint Dự kiến | Phương thức | Mục đích | Lý do hiện tại chưa có |
|---|---|---|---|---|
| **Test Mode (Thi thử)** | `/api/v1/tests/{test_id}/start` | `POST` | Bắt đầu bài thi Part 5 có bấm giờ | Chưa có mô hình `test_sessions` |
| | `/api/v1/tests/sessions/{session_id}/submit` | `POST` | Nộp bài toàn bộ đề thi, tính điểm & xếp loại | Chưa có logic chấm bài |
| **Practice Mode (Luyện tập)** | `/api/v1/practice/questions/next` | `GET` | Lấy câu hỏi luyện tập tiếp theo theo chủ điểm | Chưa có thuật toán chọn câu thích ứng |
| | `/api/v1/practice/questions/{id}/answer` | `POST` | Học viên gửi câu trả lời, nhận ngay phản hồi đúng/sai | Chưa có bảng lưu `user_answers` |
| **Interactive Tutor** | `/api/v1/tutor/chat` | `POST` | Học viên trao đổi với Gia sư AI về câu hỏi | Chưa có hội thoại nhiều lượt (Multi-turn chat) |
| | `/api/v1/tutor/hint/{question_id}` | `GET` | Xin gợi ý từng bước (scaffolding hint) mà không lộ đáp án | Chưa có prompt sinh gợi ý sư phạm |
| **Learner Profile** | `/api/v1/learners/me/stats` | `GET` | Xem báo cáo năng lực: điểm mạnh/yếu theo grammar topic | Chưa có bảng tính điểm `mastery_score` |
| | `/api/v1/learners/me/review-queue` | `GET` | Danh sách câu hỏi cần ôn tập lại theo Spaced Repetition | Chưa có bảng hàng đợi ôn tập ngắt quãng |
| **Question Management CRUD** | `/api/v1/questions/{id}` | `PUT` / `DELETE` | Sửa nội dung hoặc xóa từng câu hỏi trực tiếp | Hiện chỉ hỗ trợ import hàng loạt qua Excel |
