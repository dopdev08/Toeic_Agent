"""Script helper to create a sample Part 5 Excel file for testing import."""
import openpyxl

headers = [
    "test_id",
    "part",
    "question_no",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_answer",
    "explanation",
]

sample_questions = [
    [
        "ETS_2026_TEST_01",
        5,
        101,
        "Customer satisfaction is ______ important to the management of Grand Hotel.",
        "extreme",
        "extremely",
        "extremist",
        "extremity",
        "B",
        "Phó từ 'extremely' đứng trước tính từ 'important' để bổ nghĩa.",
    ],
    [
        "ETS_2026_TEST_01",
        5,
        102,
        "All employees must submit their travel expenses ______ Friday at 5:00 PM.",
        "by",
        "at",
        "on",
        "in",
        "A",
        "Giới từ 'by' chỉ thời hạn chót (deadline) trước một thời điểm cụ thể.",
    ],
    [
        "ETS_2026_TEST_01",
        5,
        103,
        "The newly appointed director gave a brief ______ at the beginning of the seminar.",
        "presentation",
        "present",
        "presenter",
        "presenting",
        "A",
        "Sau tính từ 'brief' cần một danh từ chỉ sự vật/hoạt động: 'presentation' (bài thuyết trình).",
    ],
    [
        "ETS_2026_TEST_01",
        5,
        104,
        "Although the weather was unfavorable, the construction crew worked ______ to finish the project on time.",
        "hard",
        "hardly",
        "hardest",
        "hardness",
        "A",
        "'Work hard' là cụm từ cố định nghĩa là làm việc chăm chỉ. 'Hardly' mang nghĩa phủ định (hầu như không).",
    ],
    [
        "ETS_2026_TEST_01",
        5,
        105,
        "Ms. Davis requested that the marketing report ______ revised before the executive meeting.",
        "is",
        "was",
        "be",
        "being",
        "C",
        "Cấu trúc giả định thức (Subjunctive mood): S + request + that + S + (should) + V-nguyên thể ('be').",
    ],
]

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Part5_Questions"
ws.append(headers)

for row in sample_questions:
    ws.append(row)

output_filename = "part5_sample.xlsx"
wb.save(output_filename)
print(f"Created sample Excel file '{output_filename}' with {len(sample_questions)} Part 5 questions.")
