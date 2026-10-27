# TOEIC AI Agent - Tài liệu Phân tích Hệ thống & Kiến trúc Thực tế

> **Phiên bản tài liệu:** 1.0.0  
> **Thời điểm lập:** Tháng 10/2026  
> **Phương pháp phân tích:** Reverse Engineering trực tiếp từ mã nguồn thực tế (Code-First Analysis)  
> **Trạng thái Codebase:** Question Ingestion & AI Enrichment Pipeline hoàn chỉnh; Test/Tutor Mode chưa triển khai.

---

## 1. Mục đích và Phạm vi Tài liệu

Tài liệu này được lập ra nhằm phản ánh **chính xác 100% hiện trạng triển khai** của dự án `Toeic_Agent` dựa trên code thực tế, tuyệt đối không suy đoán từ tài liệu thiết kế hoặc mong muốn nghiệp vụ ban đầu.

Mọi kết luận trong bộ tài liệu này đều tuân thủ các nguyên tắc:
1. **Kiểm chứng qua mã nguồn:** Mọi thành phần đều có đường dẫn tương đối trỏ đến file, class, method cụ thể trong thư mục `app/`, `scripts/`, `docs/`, `tests/`.
2. **Phân loại trạng thái minh bạch:**
   - `IMPLEMENTED`: Đã triển khai đầy đủ code, có router/service/repository và test xác thực.
   - `PARTIAL`: Đã có nền tảng cấu trúc (schema, model hoặc script) nhưng chưa có API hoàn chỉnh hoặc chưa tích hợp vào luồng chính.
   - `NOT IMPLEMENTED`: Chưa tìm thấy bất kỳ dòng code triển khai nào trong codebase.
   - `UNVERIFIED`: Chưa đủ dữ liệu hoặc điều kiện môi trường để xác nhận hoạt động thực tế.
3. **Bảo toàn hiện trạng:** Không can thiệp sửa đổi code, không chạy migration thay đổi cơ sở dữ liệu `toeic_agent.db`.

---

## 2. Tóm tắt Hiện trạng Hệ thống (Executive Summary)

### 2.1. Hệ thống thực sự làm được gì hiện nay?
Hiện tại, **hệ thống KHÔNG PHẢI là một web app luyện thi hoàn chỉnh**, mà là một **Hệ thống Ingestion và AI Enrichment chất lượng cao cho Ngân hàng Câu hỏi TOEIC Part 5**:
1. **Quản lý & Ingestion Đề thi:** Cho phép đọc file Excel câu hỏi TOEIC Part 5 (`.xlsx`), thẩm định cấu trúc dữ liệu, phát hiện lỗi dòng, kiểm tra trùng lặp và tính toán diff (thay đổi) so với database hiện tại thông qua endpoint preview (`POST /api/v1/imports/questions/preview`).
2. **Lưu trữ Question Bank:** Thực hiện transaction an toàn để ghi nhận câu hỏi vào SQLite (`POST /api/v1/imports/questions`), hỗ trợ chế độ ghi đè có kiểm soát (`allow_updates=True/False`).
3. **AI Pedagogical Enrichment:** Trích xuất câu hỏi, tạo prompt sư phạm nghiêm ngặt, gọi LLM Cloud (Google Gemini thông qua giao diện trừu tượng Clean Architecture `LLMService`), phân tích 7 chiều sư phạm:
   - Chủ điểm ngữ pháp (`grammar_topic`)
   - Cấu trúc câu (`sentence_structure`)
   - Công thức/mẫu câu áp dụng (`pattern`)
   - Từ vựng cốt lõi kèm từ loại chuẩn hóa (`vocabulary`)
   - Giải thích đáp án đúng bằng tiếng Việt (`explanation`)
   - Phân tích chi tiết 4 phương án A, B, C, D bằng tiếng Việt (`distractor_analysis`)
   - Đánh giá độ khó (`difficulty`: easy, medium, hard)
4. **Cổng Thẩm định Chất lượng AI Độc lập (Deterministic Quality Gates):** Trước khi lưu trữ, kết quả LLM bắt buộc phải vượt qua:
   - Sanitizer JSON loại bỏ markdown code fence, dấu phẩy thừa, re-map key lệch format.
   - Grounding từ vựng: Từ vựng xuất ra bắt buộc phải xuất hiện nguyên văn hoặc biến thể hình thái học chính quy trong đề hoặc câu hoàn chỉnh.
   - Phát hiện rò rỉ ký tự ngoại lai CJK (Chinese, Japanese, Korean).
   - Phát hiện mâu thuẫn đáp án: Nghiêm cấm LLM kết luận đáp án đúng từ Question Bank là "sai/không phù hợp", hoặc khẳng định phương án nhiễu là "đúng".
5. **Công cụ Đánh giá & Giám định Ngôn ngữ Ngoại tuyến (Offline Diagnostics):**
   - Bộ kiểm tra tính nhất quán từ loại bằng spaCy NLP (`pos_consistency_checker.py`).
   - Bộ thẩm định lại báo cáo lịch sử mà không cần gọi lại LLM (`report_revalidator.py`).

### 2.2. Ba khoảng trống lớn nhất so với kỳ vọng TOEIC AI Tutor
1. **Hoàn toàn chưa có Test Mode & Practice Mode:** Chưa có cơ chế cho học viên nhận đề làm bài, tính giờ, nộp bài, chấm điểm hay lưu lịch sử trả lời.
2. **Chưa có Learner Model & Quản lý Trạng thái Năng lực:** Chưa có bảng lưu trữ người dùng (`users`), lịch sử làm bài (`attempts`), chẩn đoán lỗi (`error_diagnostics`), hay điểm thành thạo kỹ năng (`mastery_scores`).
3. **Chưa có Interactive Tutor Mode:** Chưa có luồng hội thoại AI giải thích trực tiếp, gợi ý thích ứng (hinting), hay hàng đợi ôn tập ngắt quãng (Spaced Repetition).

---

## 3. Cấu trúc Thư mục và Tech Stack

```text
Toeic_Agent/
├── app/
│   ├── api/                     # Router FastAPI (REST API Endpoints)
│   │   ├── enrichments.py       # Batch enrichment endpoint
│   │   ├── import_questions.py  # Import & preview endpoints
│   │   └── questions.py         # Question CRUD & single enrichment endpoints
│   ├── db/                      # Database connection & session factory
│   │   └── database.py          # SQLAlchemy 2.0 SQLite engine, SessionLocal, init_db
│   ├── models/                  # SQLAlchemy ORM Models
│   │   ├── question.py          # Bảng 'questions'
│   │   └── question_enrichment.py # Bảng 'question_enrichments'
│   ├── repositories/            # Data Access Layer
│   │   ├── enrichment_repository.py
│   │   └── question_repository.py
│   ├── schemas/                 # Pydantic Schemas / DTOs
│   │   ├── enrichment.py        # QuestionEnrichment, VocabularyItem, DistractorAnalysis
│   │   └── question.py          # QuestionItem, QuestionDetail, Import Preview/Response
│   └── services/                # Business Logic, Workflows & LLM Integration
│       ├── batch_enrichment_workflow.py # Xử lý làm giàu hàng loạt theo chuỗi
│       ├── enrichment_response_parser.py # Sanitize & validate JSON từ LLM
│       ├── enrichment_service.py # Xây dựng prompt & dispatch LLM
│       ├── enrichment_validator.py # Kiểm tra grounding, mâu thuẫn, CJK
│       ├── enrichment_workflow.py # Use case workflow quản trị transaction
│       ├── excel_parser.py       # Phân tích cú pháp Excel, preview diff
│       ├── gemini_client.py     # Gemini Cloud AI Adapter (google-genai SDK)
│       ├── llm_client.py        # Clean Architecture Port Protocol & Domain Exceptions
│       ├── pos_consistency_checker.py # Offline spaCy diagnostic checker
│       ├── question_import_service.py # Xử lý import transactional
│       └── report_revalidator.py # Thẩm định lại báo cáo hàng loạt
├── docs/                        # Tài liệu hợp đồng & đặc tả kỹ thuật
│   ├── ai-enrichment-contract.md
│   ├── ai-enrichment-prompt.md
│   ├── llm-service-contract.md
│   └── system-analysis/         # [TÀI LIỆU NÀY] Phân tích toàn diện hệ thống
├── reports/                     # Dữ liệu thực nghiệm đánh giá mô hình
│   ├── gold_set_review/         # Bộ dữ liệu mẫu chuẩn (Gold Set)
│   ├── pos_consistency/         # Báo cáo chẩn đoán spaCy POS
│   └── revalidation/            # Báo cáo tái thẩm định ngoại tuyến
├── scripts/                     # Scripts CLI phục vụ thử nghiệm & benchmark
│   ├── check_pos_consistency.py
│   ├── revalidate_batch_report.py
│   ├── test_gemini_batch.py
│   └── test_real_gemini.py
├── tests/                       # 19 file test tự động (349 tests passing)
├── toeic_agent.db               # SQLite database chính (30 câu hỏi, 0 enrichment)
├── test_runner.db               # SQLite database biệt lập cho automated tests
├── requirements.txt             # Phụ thuộc runtime lõi
└── requirements-nlp.txt         # Phụ thuộc spaCy ngoại tuyến
```

### Bảng tóm tắt Công nghệ & Thư viện

| Thành phần | Công nghệ / Thư viện | Phiên bản | Mục đích thực tế |
|---|---|---|---|
| **Web Framework** | FastAPI | `>=0.110.0` | Cung cấp RESTful API cho import, question, enrichment |
| **ASGI Server** | Uvicorn | `>=0.28.0` | Máy chủ chạy ứng dụng FastAPI |
| **ORM & Database** | SQLAlchemy + SQLite | `>=2.0.0` | Quản lý schema, transaction, session và truy vấn dữ liệu |
| **Data Validation** | Pydantic v2 | `>=2.6.0` | Validate DTOs, cấu trúc JSON từ LLM, input Excel |
| **Excel Parser** | OpenPyXL | `>=3.1.2` | Đọc bảng tính `.xlsx`, thẩm định header, hàng và diff |
| **LLM Architecture Port** | Clean Architecture Protocol (`LLMService`) | N/A | Trừu tượng hóa hoàn toàn LLM khỏi vendor-specific logic (`llm_client.py`) |
| **LLM Cloud Adapter** | Google GenAI SDK (`google-genai`) | `>=1.0.0` | Client gọi Cloud API (`gemini-3.5-flash-lite`), sanitize secrets & error mapping |
| **NLP Diagnostics** | spaCy + `en_core_web_sm` | `3.8.16` | Thẩm định từ loại (POS) ngoại tuyến trong script |
| **Testing** | Pytest | `>=8.0.0` | Bộ kiểm thử tự động toàn diện (349 unit/integration tests) |

---

## 4. Mục lục Tài liệu Chi tiết

Hệ thống tài liệu phân tích kiến trúc được tổ chức theo các chuyên đề riêng biệt:

1. [**Kiến trúc Hệ thống (`architecture.md`)**](file:///d:/project/Toeic_Agent/docs/system-analysis/architecture.md)  
   *Mô tả chi tiết các Layer thực tế, System Context Diagram, Component Architecture Diagram, nguyên tắc phân định trách nhiệm và tính toàn vẹn transaction.*

2. [**Luồng Xử lý Thực tế (`flows.md`)**](file:///d:/project/Toeic_Agent/docs/system-analysis/flows.md)  
   *Các sơ đồ tuần tự (Sequence Diagrams) bằng Mermaid cho: Khởi động app, lấy câu hỏi, import Excel & preview diff, làm giàu AI đơn câu, làm giàu hàng loạt, và đối chiếu hành trình người dùng thực tế vs kỳ vọng.*

3. [**Mô hình Cơ sở Dữ liệu (`database.md`)**](file:///d:/project/Toeic_Agent/docs/system-analysis/database.md)  
   *Sơ đồ ERD thực tế, chi tiết bảng `questions` và `question_enrichments`, đối chiếu model code với dữ liệu thực có trong `toeic_agent.db`, danh sách các thực thể nghiệp vụ còn thiếu.*

4. [**Danh mục API Thực tế (`api-inventory.md`)**](file:///d:/project/Toeic_Agent/docs/system-analysis/api-inventory.md)  
   *Bảng chi tiết 6 REST endpoint hiện có kèm request/response schemas, service gọi tới, mã lỗi HTTP xử lý và bằng chứng file code.*

5. [**Đánh giá Trạng thái Tính năng (`feature-status.md`)**](file:///d:/project/Toeic_Agent/docs/system-analysis/feature-status.md)  
   *Bảng đối chiếu toàn diện 19 tính năng nghiệp vụ theo định dạng chuẩn: Feature \| Status \| Evidence \| Missing parts \| Next action.*

6. [**Kế hoạch Triển khai Tiếp theo (`next-steps.md`)**](file:///d:/project/Toeic_Agent/docs/system-analysis/next-steps.md)  
   *Lộ trình phát triển được phân bổ ưu tiên nghiêm ngặt theo các tầng P0 (Củng cố nền tảng), P1 (MVP Part 5 Practice/Test), P2 (Adaptive & AI Tutor), P3 (Mở rộng Part 6 & 7).*
