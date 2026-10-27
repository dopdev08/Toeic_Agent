# Luồng Xử lý Thực tế của Hệ thống (System Processing Flows)

> **File:** `docs/system-analysis/flows.md`  
> **Phương pháp phân tích:** Trích xuất luồng điều khiển, thứ tự gọi hàm và cấu trúc tham số trực tiếp từ code thực thi trong `app/`.

---

## 1. Luồng 1: Khởi động Ứng dụng (Application Startup)

Luồng khởi động được định nghĩa tại `app/main.py` thông qua cơ chế `lifespan` context manager của FastAPI.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer / Uvicorn
    participant Main as app.main (FastAPI)
    participant Lifespan as app.main:lifespan
    participant DB as app.db.database:init_db
    participant Base as SQLAlchemy:Base.metadata
    participant Engine as SQLAlchemy:Engine (SQLite)

    Dev->>Main: Chạy Uvicorn (uvicorn app.main:app)
    Main->>Lifespan: Kích hoạt lifespan context manager
    Lifespan->>DB: Gọi init_db()
    Note over DB: Import Question & QuestionEnrichment<br/>để đăng ký models vào Base
    DB->>Base: Base.metadata.create_all(bind=engine)
    Base->>Engine: Thực thi DDL tạo bảng nếu chưa tồn tại
    Note over Engine: SQLite PRAGMA foreign_keys=ON<br/>được gán tự động khi connect
    Engine-->>DB: Hoàn tất khởi tạo bảng (questions, question_enrichments)
    DB-->>Lifespan: Database sẵn sàng
    Lifespan-->>Main: yield (Ứng dụng bắt đầu nhận HTTP traffic)
```

**Bằng chứng code:**
- [app/main.py:L10-L21](file:///d:/project/Toeic_Agent/app/main.py#L10-L21)
- [app/db/database.py:L15-L21](file:///d:/project/Toeic_Agent/app/db/database.py#L15-L21)
- [app/db/database.py:L39-L44](file:///d:/project/Toeic_Agent/app/db/database.py#L39-L44)

---

## 2. Luồng 2: Lấy Danh sách & Chi tiết Câu hỏi (Question Querying)

Bao gồm 2 endpoint: lấy danh sách có phân trang và lọc (`GET /api/v1/questions`) và lấy chi tiết câu hỏi kèm enrichment (`GET /api/v1/questions/{question_id}`).

```mermaid
sequenceDiagram
    autonumber
    actor Client as API Client / Frontend
    participant Router as app.api.questions:router
    participant DBDep as app.db.database:get_db
    participant Repo as QuestionRepository
    participant Svc as QuestionImportService
    participant Session as SQLAlchemy Session
    participant DB as SQLite (toeic_agent.db)

    alt 2A. Lấy danh sách câu hỏi (List & Filter)
        Client->>Router: GET /api/v1/questions?test_id=ETS_2026&part=5&limit=50&offset=0
        Router->>DBDep: get_db() -> Inject Session
        Router->>Svc: get_questions(db, test_id, part, limit, offset)
        Svc->>Session: select(Question).where(...).order_by(...).limit().offset()
        Session->>DB: Execute SQL SELECT
        DB-->>Session: Danh sách bản ghi Question
        Session-->>Svc: List[Question]
        Router->>Svc: count_questions(db, test_id, part)
        Svc->>Session: select(func.count(Question.id)).where(...)
        Session->>DB: Execute SQL COUNT
        DB-->>Session: Tổng số câu hỏi phù hợp
        Session-->>Svc: int (total)
        Router-->>Client: 200 OK {"total": total, "limit": 50, "offset": 0, "items": [...]}
    else 2B. Lấy chi tiết câu hỏi kèm Enrichment (Get by ID)
        Client->>Router: GET /api/v1/questions/101
        Router->>DBDep: get_db() -> Inject Session
        Router->>Repo: get_question_by_id(db, question_id=101)
        Repo->>Svc: get_question_by_id(db, 101)
        Svc->>Session: db.get(Question, 101)
        Session->>DB: SQL SELECT questions WHERE id=101
        DB-->>Session: Record Question (kèm relationship enrichment nếu có)
        Session-->>Router: Question instance | None
        alt Câu hỏi không tồn tại
            Router-->>Client: 404 Not Found {"detail": "Question with ID 101 not found"}
        else Câu hỏi hợp lệ
            Note over Router: Map question.enrichment sang DTO QuestionEnrichment nếu có
            Router-->>Client: 200 OK QuestionWithEnrichmentResponse
        end
    end
```

**Bằng chứng code:**
- [app/api/questions.py:L36-L54](file:///d:/project/Toeic_Agent/app/api/questions.py#L36-L54)
- [app/api/questions.py:L56-L100](file:///d:/project/Toeic_Agent/app/api/questions.py#L56-L100)
- [app/services/question_import_service.py:L93-L129](file:///d:/project/Toeic_Agent/app/services/question_import_service.py#L93-L129)

---

## 3. Luồng 3: Xem trước Import & So sánh Diff (Import Preview)

Cho phép giáo viên/quản trị viên upload file Excel để xem trước các câu hợp lệ, câu lỗi, và sự khác biệt giữa file và cơ sở dữ liệu hiện tại mà **hoàn toàn không ghi đè hoặc can thiệp database**.

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Content Curator
    participant Router as app.api.import_questions:router
    participant ExcelParser as app.services.excel_parser
    participant Session as SQLAlchemy Session
    participant DB as SQLite (toeic_agent.db)

    Admin->>Router: POST /api/v1/imports/questions/preview (file.xlsx)
    Router->>ExcelParser: validate_file_extension(filename)
    alt Không phải file .xlsx
        ExcelParser-->>Router: raise ExcelImportError("File must have a .xlsx extension")
        Router-->>Admin: 400 Bad Request
    end
    Router->>ExcelParser: generate_import_preview(file_content, filename, db)
    Note over ExcelParser: 1. openpyxl.load_workbook(stream)<br/>2. Kiểm tra header REQUIRED_COLUMNS<br/>3. Duyệt từng hàng, validate QuestionItem<br/>4. Phát hiện duplicate nội bộ file
    ExcelParser->>Session: select(Question).where(Question.test_id.in_(detected_test_ids))
    Session->>DB: Query các câu hỏi hiện có trong DB
    DB-->>Session: List[Question]
    Note over ExcelParser: 5. So sánh từng trường (question_text, options, correct_answer)<br/>6. Phân loại action: INSERT, UNCHANGED, UPDATE, INVALID<br/>7. Phát hiện Answer Key Conflicts (cảnh báo đổi đáp án)
    ExcelParser-->>Router: QuestionImportPreviewResponse DTO
    Router-->>Admin: 200 OK QuestionImportPreviewResponse (summary, changes, conflicts, questions)
```

**Bằng chứng code:**
- [app/api/import_questions.py:L20-L49](file:///d:/project/Toeic_Agent/app/api/import_questions.py#L20-L49)
- [app/services/excel_parser.py:L140-L521](file:///d:/project/Toeic_Agent/app/services/excel_parser.py#L140-L521)

---

## 4. Luồng 4: Thực thi Import Câu hỏi Giao dịch (Atomic Ingestion)

Lưu trữ chính thức danh sách câu hỏi vào bảng `questions` với chế độ giao dịch toàn vẹn:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Content Curator
    participant Router as app.api.import_questions:router
    participant ExcelParser as app.services.excel_parser
    participant ImportSvc as QuestionImportService
    participant Session as SQLAlchemy Session
    participant DB as SQLite (toeic_agent.db)

    Admin->>Router: POST /api/v1/imports/questions?allow_updates=false (file.xlsx)
    Router->>ExcelParser: parse_and_validate_questions(content)
    ExcelParser-->>Router: parsed_result (List[QuestionItem])
    Router->>ImportSvc: import_questions(db, questions, allow_updates)
    
    rect rgb(240, 248, 255)
        Note over ImportSvc,Session: Bắt đầu Khối Transaction Atomic
        ImportSvc->>Session: Truy vấn existing (test_id, part, question_no) trong DB
        Session->>DB: SELECT questions
        DB-->>Session: existing_records
        loop Duyệt từng QuestionItem
            alt Trùng lặp nội bộ batch
                Note over ImportSvc: Bỏ qua (skipped_count += 1)
            else Đã tồn tại trong DB & allow_updates == False
                Note over ImportSvc: Bỏ qua (skipped_count += 1)
            else Đã tồn tại trong DB & allow_updates == True
                Note over ImportSvc: Cập nhật in-place các fields (updated_count += 1)
            else Chưa có trong DB
                ImportSvc->>Session: db.add(Question(...)) (imported_count += 1)
            end
        end
        alt Xảy ra lỗi bất kỳ trong quá trình ghi
            ImportSvc->>Session: db.rollback()
            ImportSvc-->>Router: raise Exception
            Router-->>Admin: 500 Internal Server Error (Rollback hoàn toàn)
        else Hoàn tất an toàn
            ImportSvc->>Session: db.commit()
            Session->>DB: Lưu vĩnh viễn dữ liệu
            ImportSvc-->>Router: (imported_count, skipped_count, updated_count)
        end
    end
    Router-->>Admin: 200 OK QuestionImportResponse (counts, questions)
```

**Bằng chứng code:**
- [app/api/import_questions.py:L51-L95](file:///d:/project/Toeic_Agent/app/api/import_questions.py#L51-L95)
- [app/services/question_import_service.py:L11-L91](file:///d:/project/Toeic_Agent/app/services/question_import_service.py#L11-L91)

---

## 5. Luồng 5: Làm giàu AI Đơn câu & Cổng Kiểm định Chất lượng (Single Enrichment Flow)

Đây là luồng phức tạp nhất của hệ thống, kết hợp giữa mô hình ngôn ngữ và các cổng kiểm định chất lượng:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as User / Curator
    participant Router as app.api.questions:router
    participant WF as EnrichmentWorkflow (Transaction Owner)
    participant Svc as EnrichmentService
    participant LLM as GeminiClient (google-genai SDK)
    participant Parser as EnrichmentResponseParser
    participant Validator as EnrichmentValidator
    participant Repo as EnrichmentRepository
    participant Session as SQLAlchemy Session
    participant DB as SQLite (toeic_agent.db)

    Admin->>Router: POST /api/v1/questions/101/enrich?force=false
    Router->>Session: Lấy Question theo ID 101
    Session-->>Router: question instance
    Router->>WF: execute(session=db, question=question, force=false)

    Note over WF: Bước 1: Kiểm tra Idempotency<br/>Nếu question.enrichment == COMPLETED và force==False
    alt Đã tồn tại bản ghi hoàn thành & force=False
        WF-->>Router: Trả về existing record ngay lập tức (Không gọi LLM)
    else Cần làm giàu (Chưa có hoặc force=True)
        rect rgb(255, 250, 240)
            Note over WF,Validator: Bắt đầu Pipeline Sinh AI & Thẩm định Chất lượng
            WF->>Svc: enrich_question(question)
            Svc->>Svc: build_ai_input(question) [Tách metadata DB]
            Svc->>Svc: build_prompt(ai_input) [Gắn System & User Prompt]
            Svc->>LLM: generate(prompt)
            LLM-->>Svc: raw_response (string)
            Svc->>Parser: parse_and_validate_enrichment(raw_response)
            Note over Parser: - Bỏ codefence ```json<br/>- Bỏ trailing commas<br/>- Normalize key misalignment<br/>- Pydantic model_validate()
            Parser-->>Svc: QuestionEnrichment (Pydantic Schema)
            Svc-->>WF: enrichment_schema

            WF->>Validator: validate_and_raise(question, enrichment_schema)
            Note over Validator: Chạy 4 Cổng Kiểm định Chất lượng Cứng:<br/>1. Distractor analysis đầy đủ 4 options A, B, C, D<br/>2. Không rò rỉ ký tự ngoại lai CJK (Trung/Nhật/Hàn)<br/>3. Grounding từ vựng: Từ vựng xuất hiện trong text/options<br/>4. Contradiction: Không bảo đáp án đúng là sai / nhiễu là đúng
            
            alt Vi phạm bất kỳ cổng chất lượng nào
                Validator-->>WF: raise EnrichmentQualityError (Grounding/Contradiction/CJK)
                WF->>Session: session.rollback()
                WF-->>Router: raise EnrichmentQualityError
                Router-->>Admin: 502 Bad Gateway (Thông báo chi tiết lỗi sư phạm)
            else Vượt qua toàn bộ kiểm định
                Validator-->>WF: Hợp lệ (Status = VALID)
                WF->>Repo: save_enrichment(session, question_id, schema, existing)
                Repo->>Session: session.flush() (Kiểm tra constraint DB, tạo ID)
                WF->>Session: session.commit()
                Session->>DB: Lưu bản ghi vào question_enrichments
                WF-->>Router: QuestionEnrichmentModel
                Router-->>Admin: 200 OK QuestionEnrichmentResponse
            end
        end
    end
```

**Bằng chứng code:**
- [app/api/questions.py:L102-L177](file:///d:/project/Toeic_Agent/app/api/questions.py#L102-L177)
- [app/services/enrichment_workflow.py:L31-L80](file:///d:/project/Toeic_Agent/app/services/enrichment_workflow.py#L31-L80)
- [app/services/enrichment_service.py:L155-L161](file:///d:/project/Toeic_Agent/app/services/enrichment_service.py#L155-L161)
- [app/services/enrichment_response_parser.py:L193-L256](file:///d:/project/Toeic_Agent/app/services/enrichment_response_parser.py#L193-L256)
- [app/services/enrichment_validator.py:L587-L682](file:///d:/project/Toeic_Agent/app/services/enrichment_validator.py#L587-L682)
- [app/repositories/enrichment_repository.py:L11-L59](file:///d:/project/Toeic_Agent/app/repositories/enrichment_repository.py#L11-L59)

---

## 6. Luồng 6: Làm giàu Hàng loạt & Cô lập Lỗi (Batch Enrichment Flow)

Xử lý danh sách các câu hỏi theo thứ tự tuần tự với nguyên tắc lỗi độc lập từng câu:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as User / Curator
    participant Router as app.api.enrichments:router
    participant BatchWF as BatchEnrichmentWorkflow
    participant SingleWF as EnrichmentWorkflow
    participant Session as SQLAlchemy Session

    Admin->>Router: POST /api/v1/enrichments/batch {"question_ids": [101, 102, 103]}
    Router->>BatchWF: execute(session=db, items=[101, 102, 103])
    
    loop Lặp qua từng question_id trong items
        Note over BatchWF: Item 1: question_id = 101
        BatchWF->>SingleWF: execute(session, question_101)
        SingleWF-->>BatchWF: Success (status: COMPLETED)
        Note over BatchWF: Item 2: question_id = 102 (Giả sử bị lỗi timeout hoặc CJK leakage)
        BatchWF->>SingleWF: execute(session, question_102)
        SingleWF-->>BatchWF: raise EnrichmentQualityError
        Note over BatchWF: Bắt exception, ghi nhận status="FAILED", error="...", KHÔNG dừng loop
        Note over BatchWF: Item 3: question_id = 103
        BatchWF->>SingleWF: execute(session, question_103)
        SingleWF-->>BatchWF: Success (status: COMPLETED)
    end

    BatchWF-->>Router: BatchEnrichmentResult (total: 3, success: 2, failed: 1, results: [...])
    Router-->>Admin: 200 OK BatchEnrichmentResponse
```

**Bằng chứng code:**
- [app/api/enrichments.py:L20-L54](file:///d:/project/Toeic_Agent/app/api/enrichments.py#L20-L54)
- [app/services/batch_enrichment_workflow.py:L77-L148](file:///d:/project/Toeic_Agent/app/services/batch_enrichment_workflow.py#L77-L148)

---

## 7. Luồng 7: Giám định Ngôn ngữ Ngoại tuyến (Offline Linguistic Auditing)

Luồng kiểm định chất lượng nâng cao dành cho chuyên gia ngôn ngữ để đánh giá nhãn từ loại của LLM bằng công cụ NLP ngữ cảnh:

```mermaid
sequenceDiagram
    autonumber
    actor Reviewer as Linguistic Reviewer
    participant CLI as scripts/check_pos_consistency.py
    participant Checker as app.services.pos_consistency_checker
    participant SpaCy as spaCy NLP (en_core_web_sm)
    participant FileSys as reports/pos_consistency/

    Reviewer->>CLI: python scripts/check_pos_consistency.py --input-report report.json
    CLI->>Checker: check_report_consistency(report_data)
    loop Với mỗi câu hỏi trong báo cáo
        Checker->>Checker: Tạo completed_sentence (điền đáp án đúng vào blank)
        Checker->>SpaCy: Parse completed_sentence qua nlp()
        loop Với mỗi từ vựng trong enrichment.vocabulary
            Checker->>Checker: Tìm token vị trí trong câu
            Checker->>Checker: So sánh expected_pos vs spacy.pos_ / spacy.tag_
            Note over Checker: Ánh xạ kết quả: POS_MATCH, POS_ACCEPTABLE_VARIANT,<br/>POS_CONTEXT_MISMATCH, SKIPPED_MULTIWORD_TARGET...
        end
    end
    Checker-->>CLI: pos_report_dict
    CLI->>FileSys: Ghi pos_consistency_*.json
    CLI->>FileSys: Ghi pos_adjudication_*.csv (hỗ trợ human adjudication)
    CLI-->>Reviewer: In tóm tắt chẩn đoán ra terminal (Match rate, Mismatch count)
```

**Bằng chứng code:**
- [scripts/check_pos_consistency.py](file:///d:/project/Toeic_Agent/scripts/check_pos_consistency.py)
- [app/services/pos_consistency_checker.py](file:///d:/project/Toeic_Agent/app/services/pos_consistency_checker.py)

---

## 8. Đối chiếu Hành trình Người dùng: Thực tế vs Kỳ vọng

```mermaid
flowchart TD
    subgraph Current_Journey["HÀNH TRÌNH THỰC TẾ HIỆN TẠI (Admin / Curator Focus)"]
        A1["1. Chuẩn bị file Excel (.xlsx) 30-100 câu Part 5"] --> A2["2. Gọi API /imports/questions/preview để kiểm tra lỗi & diff"]
        A2 --> A3["3. Gọi API /imports/questions để import vào Question Bank"]
        A3 --> A4["4. Gọi API /questions/{id}/enrich hoặc /enrichments/batch"]
        A4 --> A5["5. Kiểm tra dữ liệu được làm giàu qua /questions/{id}"]
        A5 --> A6["6. (Tùy chọn) Chạy script spaCy đánh giá chất lượng từ vựng"]
    end

    subgraph Expected_Journey["HÀNH TRÌNH KỲ VỌNG CHO HỌC VIÊN (Learner Focus - CHƯA TRIỂN KHAI)"]
        L1["1. Học viên đăng nhập & chọn Test Mode hoặc Practice Mode"] -.-> L2["2. Hệ thống cấp đề thi hoặc câu hỏi thích ứng theo Skill State"]
        L2 -.-> L3["3. Học viên làm bài, chọn đáp án & submit"]
        L3 -.-> L4["4. Hệ thống chấm điểm, lưu lịch sử, cập nhật Mastery Score"]
        L4 -.-> L5["5. Error Diagnosis: Phân tích nguyên nhân sai dựa trên Distractor Analysis"]
        L5 -.-> L6["6. Tutor Mode: Gia sư ảo trò chuyện, đưa gợi ý (hint) & giải thích"]
        L6 -.-> L7["7. Adaptive Review: Đưa vào hàng đợi ôn tập Spaced Repetition"]
    end

    classDef current fill:#27ae60,stroke:#1e8449,stroke-width:2px,color:#fff;
    classDef expected fill:#c0392b,stroke:#922b21,stroke-width:2px,stroke-dasharray: 5 5,color:#fff;

    class A1,A2,A3,A4,A5,A6 current;
    class L1,L2,L3,L4,L5,L6,L7 expected;
```
