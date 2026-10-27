import re

# Pedagogical warning tests

def check_pedagogical_warnings(enrichment):
    warnings = []
    
    # 1. Generic explanation check
    expl = (enrichment.explanation or "").strip().lower()
    generic_expl_pattern = re.compile(
        r"^(?:đáp\s+án\s+)?(?:đúng|chính\s+xác)?\s*(?:vì\s+)?phù\s+hợp(?:\s+với)?\s*(?:ngữ\s+cảnh|nghĩa\s+của\s+câu|câu)?[\.\!]?$"
    )
    if generic_expl_pattern.match(expl) or expl in ("correct in context", "fits the context", "phù hợp với ngữ cảnh"):
        warnings.append("[GENERIC_EXPLANATION] Answer explanation relies solely on generic context assertion ('phù hợp với ngữ cảnh') without specifying grammatical rules or lexical distinctions.")
        
    # 2. Boilerplate / trivial distractor explanations
    dist_texts = [
        getattr(enrichment.distractor_analysis, k, "").strip()
        for k in ("A", "B", "C", "D")
    ]
    # Check if multiple distractors are identical
    cleaned_d = [d.lower() for d in dist_texts if d]
    if len(cleaned_d) == 4:
        unique_d = set(cleaned_d)
        if len(unique_d) <= 2:
            warnings.append("[BOILERPLATE_DISTRACTOR_ANALYSIS] Distractor analysis contains repeated or near-identical boilerplate across multiple options.")
            
    # Check for trivial length (< 6 chars)
    for k in ("A", "B", "C", "D"):
        val = getattr(enrichment.distractor_analysis, k, "").strip()
        if val and len(val) <= 5 and val.lower() in ("sai", "sai.", "đúng", "wrong", "right"):
            warnings.append(f"[TRIVIAL_DISTRACTOR_ANALYSIS] Distractor analysis for option {k} is trivially short ('{val}') and lacks instructional value.")
            
    # 3. Generic pattern / sentence_structure
    struct = (enrichment.sentence_structure or "").strip().upper()
    if struct in ("SVO", "S+V+O", "S V O", "S-V-O", "S+V", "SV", "GRAMMAR", "SENTENCE"):
        warnings.append(f"[GENERIC_SENTENCE_STRUCTURE] Sentence structure '{enrichment.sentence_structure}' is an uninformative generic formula.")
        
    pat = (enrichment.pattern or "").strip().lower()
    if pat in ("grammar", "verb form", "word form", "vocabulary", "pattern", "structure", "svo", "s+v+o"):
        warnings.append(f"[GENERIC_PATTERN] Pattern '{enrichment.pattern}' is an uninformative generic label.")
        
    # 4. Suspicious vocabulary meaning
    for v in enrichment.vocabulary:
        w = (v.word or "").strip().lower()
        m = (v.meaning or "").strip().lower()
        if w and m and w == m:
            warnings.append(f"[SUSPICIOUS_VOCABULARY_MEANING] Vocabulary item '{v.word}' has identical English text in meaning field instead of Vietnamese translation.")
            
    return warnings

class DummyObj:
    pass

class DummyEnrich:
    def __init__(self, explanation, dist_A, dist_B, dist_C, dist_D, sentence_structure, pattern, vocab):
        self.explanation = explanation
        self.distractor_analysis = DummyObj()
        self.distractor_analysis.A = dist_A
        self.distractor_analysis.B = dist_B
        self.distractor_analysis.C = dist_C
        self.distractor_analysis.D = dist_D
        self.sentence_structure = sentence_structure
        self.pattern = pattern
        self.vocabulary = vocab

class DummyVocab:
    def __init__(self, word, meaning):
        self.word = word
        self.meaning = meaning

# Case 1: All generic
e_bad = DummyEnrich(
    explanation="Phù hợp với ngữ cảnh.",
    dist_A="Sai.",
    dist_B="Đúng.",
    dist_C="Sai.",
    dist_D="Sai.",
    sentence_structure="SVO",
    pattern="verb form",
    vocab=[DummyVocab("calculate", "calculate")]
)
w_bad = check_pedagogical_warnings(e_bad)
print("Bad warnings count:", len(w_bad))
for w in w_bad:
    print("  ", w)
assert len(w_bad) >= 5, "Expected warnings for all generic fields"

# Case 2: Good candidate (should have 0 warnings)
e_good = DummyEnrich(
    explanation="Chọn B (after). Cụm after which có nghĩa là sau thời điểm đó...",
    dist_A="Across thường chỉ sự di chuyển...",
    dist_B="After kết hợp với which...",
    dist_C="Inside chỉ vị trí bên trong...",
    dist_D="Among chỉ quan hệ giữa các thành viên...",
    sentence_structure="Main clause [The lecture will take place at 6:00 P.M.], + relative clause [after which + S + V]",
    pattern="after which + clause",
    vocab=[DummyVocab("attendees", "người tham dự")]
)
w_good = check_pedagogical_warnings(e_good)
print("Good warnings count:", len(w_good))
assert len(w_good) == 0, f"Expected 0 warnings for good candidate, got: {w_good}"
print("Warning tests PASSED!")
