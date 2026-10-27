import re

CJK_CHAR_REGEX = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]"
)

# Test CJK detector
vietnamese_sample = "Từ 'after which' có nghĩa là sau thời điểm đó, bổ nghĩa cho mốc thời gian 6:00 P.M. Người tham dự có thể đặt câu hỏi."
chinese_sample = "选择 B 是正确的。因为 after which 表示在那之后。"
japanese_sample = "正解はBです。"
korean_sample = "정답은 B입니다."

assert not CJK_CHAR_REGEX.search(vietnamese_sample), "Vietnamese falsely flagged as CJK"
assert CJK_CHAR_REGEX.search(chinese_sample), "Chinese not detected"
assert CJK_CHAR_REGEX.search(japanese_sample), "Japanese not detected"
assert CJK_CHAR_REGEX.search(korean_sample), "Korean not detected"
print("CJK test: PASSED")

# Test explanation contradiction
def check_explanation_contradiction(correct_letter, explanation):
    if not explanation or not correct_letter:
        return []
    text_lower = explanation.strip().lower()
    cl = correct_letter.lower()
    
    # Pattern 1: e.g. "Đáp án B là sai", "Lựa chọn B không chính xác", "Option B is incorrect"
    p1 = re.compile(
        rf"\b(?:đáp\s+án|lựa\s+chọn|phương\s+án|câu|option|choice|answer)\s*{re.escape(cl)}\s*(?:là\s+)?(?:sai|không\s+đúng|không\s+chính\s+xác|không\s+phù\s+hợp|bị\s+loại|is\s+incorrect|is\s+wrong|is\s+not\s+correct)\b",
        re.IGNORECASE
    )
    # Pattern 2: Leading e.g. "B là sai vì...", "B: Sai do..."
    p2 = re.compile(
        rf"^\s*(?:[A-D]\s*[:\-]?)?\s*{re.escape(cl)}\s*[:\-]?\s*(?:sai\s+(?:vì|do|khi)|is\s+incorrect|is\s+wrong)\b",
        re.IGNORECASE
    )
    if p1.search(text_lower) or p2.search(text_lower):
        return [f"Explanation asserts that authoritative correct answer '{correct_letter}' is incorrect/unsuitable."]
    return []

assert check_explanation_contradiction("B", "Đáp án B là sai vì thiếu giới từ."), "Failed to catch explanation contradiction"
assert check_explanation_contradiction("B", "Option B is incorrect because of tense."), "Failed to catch English explanation contradiction"
assert not check_explanation_contradiction("B", "Chọn B (after). Cụm after which có nghĩa là sau thời điểm đó."), "False positive on valid explanation"
assert not check_explanation_contradiction("B", "Đáp án A là sai, vì vậy chọn B."), "False positive when mentioning wrong option is sai"
print("Explanation contradiction test: PASSED")

# Test wrong option claimed correct
def check_wrong_option_claimed_correct(correct_letter, distractor_analysis):
    contradictions = []
    for opt in ("A", "B", "C", "D"):
        if opt == correct_letter:
            continue
        text = getattr(distractor_analysis, opt, None) or ""
        text_lower = text.strip().lower()
        if not text_lower:
            continue
        ol = opt.lower()
        
        # Check negative assertion first to avoid false positive
        is_negated = bool(re.search(r"\b(?:không\s+(?:phải|đúng|chính\s+xác|phù\s+hợp)|chưa\s+chính\s+xác|sai\b|incorrect\b|wrong\b|not\s+correct|not\s+the\s+correct)\b", text_lower))
        
        # Check positive assertion: e.g. "Đáp án A là đúng", "Chọn A", "Đúng vì...", "A is the correct answer"
        p_claim = re.compile(
            rf"(?:^\s*(?:đáp\s+án|lựa\s+chọn|phương\s+án)?\s*{re.escape(ol)}\s*[:\-]?(?:là\s+)?(?:đáp\s+án\s+)?(?:đúng|chính\s+xác)\b|^\s*(?:chọn\s+{re.escape(ol)}\b|đúng\s+(?:vì|do|khi)|is\s+correct\b|correct\b)|\b(?:đáp\s+án|lựa\s+chọn|phương\s+án|option|choice|answer)\s*{re.escape(ol)}\s*(?:là\s+)?(?:đáp\s+án\s+)?(?:đúng|chính\s+xác|phù\s+hợp\s+nhất|is\s+correct|is\s+the\s+correct\s+answer)\b)",
            re.IGNORECASE
        )
        if p_claim.search(text_lower) and not is_negated:
            contradictions.append(f"Distractor analysis for incorrect option '{opt}' asserts that it is the correct answer: '{text[:60]}...'")
    return contradictions

class DummyDist:
    def __init__(self, A, B, C, D):
        self.A = A
        self.B = B
        self.C = C
        self.D = D

# Test case 1: Option A (wrong, correct is B) claims to be correct
d1 = DummyDist(A="Đúng vì across chỉ sự di chuyển qua một khu vực.", B="Đúng vì after tạo cụm after which.", C="Sai vì...", D="Sai vì...")
assert check_wrong_option_claimed_correct("B", d1), "Failed to detect wrong option claiming correct"

# Test case 2: Option A (wrong) says it is NOT correct
d2 = DummyDist(A="Sai vì across chỉ vị trí không gian, không dùng chỉ thời gian.", B="Đúng vì after which tạo mệnh đề thời gian.", C="Sai vì...", D="Sai vì...")
assert not check_wrong_option_claimed_correct("B", d2), "False positive on normal distractor"

# Test case 3: Option A (wrong) mentions "không phải là đáp án đúng"
d3 = DummyDist(A="Đáp án A không phải là đáp án đúng vì thiếu ngữ cảnh.", B="Đúng.", C="Sai.", D="Sai.")
assert not check_wrong_option_claimed_correct("B", d3), "False positive on negated phrase"
print("Wrong option claimed correct test: PASSED")
