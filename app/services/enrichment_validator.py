"""Enrichment quality validator module for deterministic validation before persistence.

Phase 3.3.12.2B.2.2A:
1. Vocabulary grounding:
   Each vocabulary item's `word` must be grounded in the question text or one of the options.
2. Required distractor analysis:
   Analysis for all options (A, B, C, D) must be present and non-empty.
3. Suspicious analysis of authoritative correct answer:
   The analysis of the authoritative correct answer must not contradict the answer by asserting
   that the correct option is incorrect, wrong, or unsuitable.
4. Source-of-truth preservation:
   Does not modify Question.correct_answer or any field of QuestionEnrichment.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any

from app.models.question import Question
from app.schemas.enrichment import QuestionEnrichment


class QualityValidationStatus(str, Enum):
    VALID = "VALID"
    REJECTED = "REJECTED"
    SUSPICIOUS = "SUSPICIOUS"


@dataclass
class QualityValidationResult:
    """Outcome of deterministic enrichment quality validation."""

    status: QualityValidationStatus
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_code": self.error_code,
        }


class EnrichmentQualityError(Exception):
    """Base exception for deterministic quality validation failures."""

    def __init__(self, message: str, code: str, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or []


class EnrichmentGroundingError(EnrichmentQualityError):
    """Raised when vocabulary items are not grounded in question text or options."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message, code="UNGROUNDED_VOCABULARY", details=details)


class EnrichmentContradictionError(EnrichmentQualityError):
    """Raised when distractor analysis contradicts the authoritative correct answer."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message, code="CORRECT_ANSWER_CONTRADICTION", details=details)


class EnrichmentMissingDistractorError(EnrichmentQualityError):
    """Raised when required distractor analysis options are missing or empty."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message, code="MISSING_DISTRACTOR_ANALYSIS", details=details)


class EnrichmentScriptLeakageError(EnrichmentQualityError):
    """Raised when learner-facing enrichment fields contain foreign CJK script leakage."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message, code="LANGUAGE_SCRIPT_LEAKAGE", details=details)


class EnrichmentValidator:
    """Performs deterministic quality validation on parsed QuestionEnrichment."""

    @staticmethod
    def normalize_text_for_grounding(text: str) -> str:
        """Normalize text by converting to lowercase, replacing punctuation with space,

        and collapsing whitespace.
        """
        if not text:
            return ""
        cleaned = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def extract_source_text(cls, question: Question | Any) -> str:
        """Extract and normalize question text, options, and authoritative completed sentence into a single string.

        When a question has a blank and an authoritative correct_answer from the database,
        the blank is filled with the authoritative correct option to form the completed sentence.
        This provides grounding evidence for valid collocations formed across the blank
        (e.g., 'product _____' + 'line' -> 'product line') without speculating on incorrect options.
        """
        q_text = (
            getattr(question, "question_text", None)
            or (question.get("question_text") if isinstance(question, dict) else None)
            or ""
        )
        opt_a = (
            getattr(question, "option_a", None)
            or (question.get("option_a") if isinstance(question, dict) else None)
            or ""
        )
        opt_b = (
            getattr(question, "option_b", None)
            or (question.get("option_b") if isinstance(question, dict) else None)
            or ""
        )
        opt_c = (
            getattr(question, "option_c", None)
            or (question.get("option_c") if isinstance(question, dict) else None)
            or ""
        )
        opt_d = (
            getattr(question, "option_d", None)
            or (question.get("option_d") if isinstance(question, dict) else None)
            or ""
        )
        correct_letter = (
            getattr(question, "correct_answer", None)
            or (question.get("correct_answer") if isinstance(question, dict) else None)
            or ""
        ).strip().upper()

        completed_sentence = ""
        if correct_letter in ("A", "B", "C", "D") and q_text:
            correct_map = {"A": opt_a, "B": opt_b, "C": opt_c, "D": opt_d}
            correct_option_text = correct_map.get(correct_letter, "")
            if correct_option_text:
                # Replace blank (2 or more underscores) with authoritative correct option
                completed_sentence = re.sub(r"_{2,}", correct_option_text, q_text)

        parts = [
            q_text,
            completed_sentence,
            opt_a,
            opt_b,
            opt_c,
            opt_d,
        ]
        combined = " ".join(p for p in parts if p)
        return cls.normalize_text_for_grounding(combined)

    @classmethod
    def _get_single_word_inflections(cls, token: str) -> list[str]:
        """Generate common, unambiguous inflection variants of a single normalized token.

        Rules:
        1. Always includes the exact normalized token.
        2. Regular forward inflections (len >= 3):
           - Suffix 's' (e.g. attendee -> attendees, report -> reports)
           - Suffix 'es' (e.g. virus -> viruses, process -> processes, watch -> watches)
           - Suffix 'ed' (e.g. request -> requested, review -> reviewed)
           - Suffix 'ing' (e.g. request -> requesting)
           - Suffix 'd' ONLY if word ends in 'e' (e.g. revise -> revised)
           - Drop 'e' and suffix 'ing' if word ends in 'e' (e.g. revise -> revising)
        3. Regular reverse inflections / de-inflections (plural -> singular, etc.):
           - Drop 'ies' -> 'y' if word ends in 'ies' and len >= 5 (e.g. companies -> company)
           - Drop 'es' if word ends in 'es' and len >= 5 (e.g. viruses -> virus, boxes -> box)
           - Drop 's' if word ends in 'es' and len >= 5 (e.g. houses -> house)
           - Drop 's' if word ends in 's' (not 'ss') and len >= 4 (e.g. registers -> register, systems -> system)
           - Drop 'ed' / 'd' if word ends in 'ed' and len >= 5 (e.g. reviewed -> review, revised -> revise)
           - Drop 'ing' / 'ing'+'e' if word ends in 'ing' and len >= 6 (e.g. reviewing -> review)
        """
        candidates = [token]
        if len(token) < 3:
            return candidates

        # Forward inflections
        candidates.append(f"{token}s")
        candidates.append(f"{token}es")
        candidates.append(f"{token}ed")
        candidates.append(f"{token}ing")
        if token.endswith("e"):
            candidates.append(f"{token}d")
            if len(token) >= 4:
                candidates.append(f"{token[:-1]}ing")

        # Reverse inflections (de-inflection to base form)
        if token.endswith("ies") and len(token) >= 5:
            candidates.append(f"{token[:-3]}y")
        if token.endswith("es") and len(token) >= 5:
            candidates.append(token[:-2])
            candidates.append(token[:-1])
        elif token.endswith("s") and not token.endswith("ss") and len(token) >= 4:
            candidates.append(token[:-1])

        if token.endswith("ed") and len(token) >= 5:
            candidates.append(token[:-2])
            candidates.append(token[:-1])
        if token.endswith("ing") and len(token) >= 6:
            candidates.append(token[:-3])
            candidates.append(f"{token[:-3]}e")

        seen = set()
        unique = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    @classmethod
    def _get_candidate_inflections(cls, norm_word: str) -> list[str]:
        """Generate common, unambiguous inflection variants of a normalized word or phrase.

        For single words: delegates to _get_single_word_inflections.
        For multiword phrases: inflects head noun (last token) and/or first token (phrasal verb),
        preserving exact token boundary structure across the entire phrase.
        """
        if not norm_word:
            return []

        if " " not in norm_word:
            return cls._get_single_word_inflections(norm_word)

        tokens = norm_word.split()
        candidates = [norm_word]

        # Inflect last token (head noun, e.g. "computer virus" -> "computer viruses")
        prefix = " ".join(tokens[:-1])
        last_inflections = cls._get_single_word_inflections(tokens[-1])
        for li in last_inflections:
            candidates.append(f"{prefix} {li}")

        # If exactly two tokens, also support inflecting first token (phrasal verb, e.g. "take place" -> "takes place")
        if len(tokens) == 2:
            first_inflections = cls._get_single_word_inflections(tokens[0])
            suffix = tokens[1]
            for fi in first_inflections:
                candidates.append(f"{fi} {suffix}")

        seen = set()
        unique = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    @classmethod
    def is_word_grounded(cls, word: str, normalized_source: str) -> bool:
        """Check if a vocabulary word or multiword phrase is grounded in normalized source text.

        Guarantees that vocabulary items must match whole tokens or unambiguous inflections,
        never arbitrary prefixes or sub-sequences of unrelated tokens (e.g. 'car' does not match
        'carpet', 'act' does not match 'active', 'for' does not match 'information').
        """
        norm_word = cls.normalize_text_for_grounding(word)
        if not norm_word:
            return False

        candidates = cls._get_candidate_inflections(norm_word)
        for cand in candidates:
            pattern = rf"\b{re.escape(cand)}\b"
            if re.search(pattern, normalized_source):
                return True

        return False

    @classmethod
    def check_vocabulary_grounding(
        cls,
        normalized_source: str,
        enrichment: QuestionEnrichment,
    ) -> list[str]:
        """Verify each vocabulary word appears in the question or options.

        Uses token boundary-aware matching and unambiguous regular inflection
        rules to prevent vocabulary items from matching unrelated longer tokens
        (e.g., 'car' in 'carpet', 'act' in 'active', 'for' in 'information').
        """
        ungrounded = []
        for item in enrichment.vocabulary:
            if not cls.is_word_grounded(item.word, normalized_source):
                ungrounded.append(
                    f"Vocabulary item '{item.word}' is not grounded in question text or options."
                )
        return ungrounded

    @staticmethod
    def check_distractor_completeness(enrichment: QuestionEnrichment) -> list[str]:
        """Verify distractor analysis contains non-empty entries for A, B, C, D."""
        missing = []
        for key in ("A", "B", "C", "D"):
            val = getattr(enrichment.distractor_analysis, key, None)
            if val is None or not str(val).strip():
                missing.append(f"Distractor analysis for option {key} is missing or empty.")
        return missing

    # Unicode range covering CJK Unified Ideographs, Extensions, Compatibility, Hiragana, Katakana, and Hangul
    CJK_CHAR_REGEX = re.compile(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]"
    )

    @classmethod
    def detect_language_script_leakage(cls, enrichment: QuestionEnrichment) -> list[str]:
        """Detect obvious foreign CJK script characters in learner-facing enrichment fields.

        Enrichment content is expected to use English grammatical terms and Vietnamese explanations.
        CJK script characters indicate model training/prompt leakage. Vietnamese diacritics and
        standard Latin symbols are fully accepted.
        """
        leakages = []
        fields_to_check = [
            ("grammar_topic", enrichment.grammar_topic),
            ("sentence_structure", enrichment.sentence_structure),
            ("pattern", enrichment.pattern),
            ("explanation", enrichment.explanation),
        ]
        for fname, fval in fields_to_check:
            if fval and cls.CJK_CHAR_REGEX.search(fval):
                leakages.append(
                    f"Field '{fname}' contains foreign CJK characters: '{fval[:50]}...'"
                )

        for opt in ("A", "B", "C", "D"):
            dval = getattr(enrichment.distractor_analysis, opt, None)
            if dval and cls.CJK_CHAR_REGEX.search(dval):
                leakages.append(
                    f"Distractor analysis for option {opt} contains foreign CJK characters: '{dval[:50]}...'"
                )

        for v in enrichment.vocabulary:
            if v.meaning and cls.CJK_CHAR_REGEX.search(v.meaning):
                leakages.append(
                    f"Vocabulary item '{v.word}' meaning contains foreign CJK characters: '{v.meaning}'"
                )

        return leakages

    @classmethod
    def check_explanation_contradiction(
        cls,
        question: Question | Any,
        enrichment: QuestionEnrichment,
    ) -> list[str]:
        """Detect explicit assertions in the main explanation claiming the authoritative correct answer is wrong."""
        correct_letter = (getattr(question, "correct_answer", None) or "").strip().upper()
        if correct_letter not in ("A", "B", "C", "D"):
            return []

        expl = getattr(enrichment, "explanation", "") or ""
        expl_lower = expl.strip().lower()
        if not expl_lower:
            return []

        cl = correct_letter.lower()

        # Pattern 1: e.g. "Đáp án B là sai", "Lựa chọn B không chính xác", "Option B is incorrect"
        p_explicit = re.compile(
            rf"\b(?:đáp\s+án|lựa\s+chọn|phương\s+án|câu|option|choice|answer)\s*{re.escape(cl)}\s*(?:là\s+)?(?:sai|không\s+đúng|không\s+chính\s+xác|không\s+phù\s+hợp|bị\s+loại|is\s+incorrect|is\s+wrong|is\s+not\s+correct)\b",
            re.IGNORECASE,
        )
        # Pattern 2: Leading e.g. "B là sai vì...", "B: Sai do..."
        p_leading = re.compile(
            rf"^\s*(?:[A-D]\s*[:\-]?)?\s*{re.escape(cl)}\s*[:\-]?\s*(?:sai\s+(?:vì|do|khi)|is\s+incorrect|is\s+wrong)\b",
            re.IGNORECASE,
        )
        if p_explicit.search(expl_lower) or p_leading.search(expl_lower):
            return [
                f"Explanation asserts that authoritative correct answer '{correct_letter}' is incorrect or unsuitable."
            ]
        return []

    @classmethod
    def check_wrong_distractor_claimed_correct(
        cls,
        question: Question | Any,
        enrichment: QuestionEnrichment,
    ) -> list[str]:
        """Detect explicit assertions in distractor analyses claiming an incorrect option is the correct answer."""
        correct_letter = (getattr(question, "correct_answer", None) or "").strip().upper()
        if correct_letter not in ("A", "B", "C", "D"):
            return []

        contradictions = []
        for opt in ("A", "B", "C", "D"):
            if opt == correct_letter:
                continue
            text = getattr(enrichment.distractor_analysis, opt, "") or ""
            text_lower = text.strip().lower()
            if not text_lower:
                continue
            ol = opt.lower()

            # Ensure the statement is not negated (e.g. "không phải là đáp án đúng")
            is_negated = bool(
                re.search(
                    r"\b(?:không\s+(?:phải|đúng|chính\s+xác|phù\s+hợp)|chưa\s+chính\s+xác|sai\b|incorrect\b|wrong\b|not\s+correct|not\s+the\s+correct)\b",
                    text_lower,
                )
            )

            p_claim = re.compile(
                rf"(?:^\s*(?:đáp\s+án|lựa\s+chọn|phương\s+án)?\s*{re.escape(ol)}\s*[:\-]?(?:là\s+)?(?:đáp\s+án\s+)?(?:đúng|chính\s+xác)\b|^\s*(?:chọn\s+{re.escape(ol)}\b|đúng\s+(?:vì|do|khi)|is\s+correct\b|correct\b)|\b(?:đáp\s+án|lựa\s+chọn|phương\s+án|option|choice|answer)\s*{re.escape(ol)}\s*(?:là\s+)?(?:đáp\s+án\s+)?(?:đúng|chính\s+xác|phù\s+hợp\s+nhất|is\s+correct|is\s+the\s+correct\s+answer)\b)",
                re.IGNORECASE,
            )
            if p_claim.search(text_lower) and not is_negated:
                contradictions.append(
                    f"Distractor analysis for incorrect option '{opt}' asserts that it is the correct answer: '{text[:60]}...'"
                )

        return contradictions

    @classmethod
    def check_correct_answer_contradiction(
        cls,
        question: Question | Any,
        enrichment: QuestionEnrichment,
    ) -> list[str]:
        """Detect high-confidence contradiction patterns in the analysis of the authoritative answer."""
        correct_letter = (getattr(question, "correct_answer", None) or "").strip().upper()
        if correct_letter not in ("A", "B", "C", "D"):
            return []

        analysis_text = getattr(enrichment.distractor_analysis, correct_letter, "") or ""
        analysis_lower = analysis_text.strip().lower()
        if not analysis_lower:
            return []

        # Get option text for this letter
        option_attr = f"option_{correct_letter.lower()}"
        raw_option_text = getattr(question, option_attr, None) or ""
        norm_option_text = raw_option_text.strip().lower()

        contradictions = []

        # Rule 1: Leading negative judgment: e.g., "Sai vì...", "B: Sai do...", "Incorrect because..."
        leading_negative_pattern = re.compile(
            r"^\s*(?:đáp án|lựa chọn|phương án)?\s*(?:[A-D]\s*[:\-]?)?\s*(?:sai\s+(?:vì|do|khi|ngữ pháp|ngữ cảnh|trong)|sai\s*[:\.\-]|incorrect\b|is\s+incorrect\b|is\s+wrong\b)",
            re.IGNORECASE,
        )
        if leading_negative_pattern.search(analysis_lower):
            contradictions.append(
                f"Distractor analysis for authoritative answer '{correct_letter}' starts with an explicit negative judgment: '{analysis_text[:60]}...'"
            )
            return contradictions

        # Rule 2: Option-specific unsuitability assertion: e.g. "after - không phù hợp", "b - không phù hợp"
        # Handles option unsuitability contradiction: "after - không phù hợp với ngữ cảnh của câu..."
        if norm_option_text:
            escaped_opt = re.escape(norm_option_text)
            opt_unsuitable_pattern = re.compile(
                rf"\b{escaped_opt}\s*[-–:]\s*không\s+phù\s+hợp",
                re.IGNORECASE,
            )
            if opt_unsuitable_pattern.search(analysis_lower):
                contradictions.append(
                    f"Distractor analysis for authoritative answer '{correct_letter}' asserts option text '{norm_option_text}' is unsuitable: '{analysis_text[:60]}...'"
                )
                return contradictions

        letter_unsuitable_pattern = re.compile(
            rf"\b(?:đáp án|lựa chọn|phương án)?\s*{re.escape(correct_letter.lower())}\s*[-–:]\s*không\s+phù\s+hợp",
            re.IGNORECASE,
        )
        if letter_unsuitable_pattern.search(analysis_lower):
            contradictions.append(
                f"Distractor analysis for authoritative answer '{correct_letter}' asserts option '{correct_letter}' is unsuitable."
            )
            return contradictions

        # Rule 3: Direct statement that this option is wrong or unsuitable
        # e.g., "đáp án này là sai", "lựa chọn này không phù hợp", "đáp án b không chính xác"
        this_option_negative_pattern = re.compile(
            r"(?:đáp án|lựa chọn|phương án)\s*(?:này|[A-D])\s*(?:là\s+)?(?:sai|không\s+đúng|không\s+chính\s+xác|không\s+phù\s+hợp|bị\s+loại)",
            re.IGNORECASE,
        )
        if this_option_negative_pattern.search(analysis_lower):
            contradictions.append(
                f"Distractor analysis for authoritative answer '{correct_letter}' describes the option as incorrect or unsuitable."
            )
            return contradictions

        # Rule 4: English contradiction assertions
        # e.g., "is not correct", "is unsuitable", "is not the correct answer", "cannot be chosen"
        english_negative_pattern = re.compile(
            r"\b(?:is\s+not\s+correct|is\s+incorrect|is\s+unsuitable|is\s+inappropriate|is\s+wrong|not\s+the\s+correct\s+answer|cannot\s+be\s+chosen|cannot\s+be\s+used)\b",
            re.IGNORECASE,
        )
        if english_negative_pattern.search(analysis_lower):
            match = english_negative_pattern.search(analysis_lower)
            start_pos = match.start()
            prefix = analysis_lower[max(0, start_pos - 30):start_pos]
            if not any(other in prefix for other in ("other", "distractor", "remaining", "another")):
                contradictions.append(
                    f"Distractor analysis for authoritative answer '{correct_letter}' contains English negative judgment."
                )
                return contradictions

        return contradictions

    @classmethod
    def check_all_answer_contradictions(
        cls,
        question: Question | Any,
        enrichment: QuestionEnrichment,
    ) -> list[str]:
        """Aggregate all deterministic answer contradiction checks across distractor analyses and explanation."""
        contradictions = []
        contradictions.extend(cls.check_correct_answer_contradiction(question, enrichment))
        contradictions.extend(cls.check_explanation_contradiction(question, enrichment))
        contradictions.extend(cls.check_wrong_distractor_claimed_correct(question, enrichment))
        return contradictions

    @classmethod
    def check_pedagogical_warnings(cls, enrichment: QuestionEnrichment) -> list[str]:
        """Collect non-fatal pedagogical warnings for review.

        Warnings indicate quality risk signals (e.g. generic templates, boilerplate justifications)
        that require human attention, but do not invalidate deterministic schema/hard-quality validity.
        """
        warnings = []

        # 1. Generic explanation check
        expl = (enrichment.explanation or "").strip().lower()
        generic_expl_pattern = re.compile(
            r"^(?:đáp\s+án\s+)?(?:đúng|chính\s+xác)?\s*(?:vì\s+)?phù\s+hợp(?:\s+với)?\s*(?:ngữ\s+cảnh(?:\s+của\s+câu)?|nghĩa(?:\s+của\s+câu)?|câu)?[\.\!]?$"
        )
        if generic_expl_pattern.match(expl) or expl in ("correct in context", "fits the context", "phù hợp với ngữ cảnh"):
            warnings.append(
                "[GENERIC_EXPLANATION] Answer explanation relies solely on generic context assertion ('phù hợp với ngữ cảnh') without specifying grammatical rules or lexical distinctions."
            )

        # 2. Boilerplate / trivial distractor explanations
        dist_texts = [
            getattr(enrichment.distractor_analysis, k, "").strip()
            for k in ("A", "B", "C", "D")
        ]
        cleaned_d = [d.lower() for d in dist_texts if d]
        if len(cleaned_d) == 4:
            unique_d = set(cleaned_d)
            if len(unique_d) <= 2:
                warnings.append(
                    "[BOILERPLATE_DISTRACTOR_ANALYSIS] Distractor analysis contains repeated or near-identical boilerplate across multiple options."
                )

        for k in ("A", "B", "C", "D"):
            val = getattr(enrichment.distractor_analysis, k, "").strip()
            if val and len(val) <= 5 and val.lower() in ("sai", "sai.", "đúng", "wrong", "right"):
                warnings.append(
                    f"[TRIVIAL_DISTRACTOR_ANALYSIS] Distractor analysis for option {k} is trivially short ('{val}') and lacks instructional value."
                )

        # 3. Generic pattern / sentence_structure
        struct = (enrichment.sentence_structure or "").strip().upper()
        if struct in ("SVO", "S+V+O", "S V O", "S-V-O", "S+V", "SV", "GRAMMAR", "SENTENCE"):
            warnings.append(
                f"[GENERIC_SENTENCE_STRUCTURE] Sentence structure '{enrichment.sentence_structure}' is an uninformative generic formula."
            )

        pat = (enrichment.pattern or "").strip().lower()
        if pat in ("grammar", "verb form", "word form", "vocabulary", "pattern", "structure", "svo", "s+v+o"):
            warnings.append(
                f"[GENERIC_PATTERN] Pattern '{enrichment.pattern}' is an uninformative generic label."
            )

        # 4. Suspicious vocabulary meaning
        for v in enrichment.vocabulary:
            w = (v.word or "").strip().lower()
            m = (v.meaning or "").strip().lower()
            if w and m and w == m:
                warnings.append(
                    f"[SUSPICIOUS_VOCABULARY_MEANING] Vocabulary item '{v.word}' has identical English text in meaning field instead of Vietnamese translation."
                )

        return warnings

    def validate(
        self,
        question: Question | Any,
        enrichment: QuestionEnrichment,
    ) -> QualityValidationResult:
        """Run all deterministic quality checks and return a structured QualityValidationResult."""
        # 1. Distractor analysis completeness check
        distractor_errors = self.check_distractor_completeness(enrichment)
        if distractor_errors:
            return QualityValidationResult(
                status=QualityValidationStatus.REJECTED,
                is_valid=False,
                errors=distractor_errors,
                error_code="MISSING_DISTRACTOR_ANALYSIS",
            )

        # 2. Language-script leakage check (CJK foreign characters)
        leakage_errors = self.detect_language_script_leakage(enrichment)
        if leakage_errors:
            return QualityValidationResult(
                status=QualityValidationStatus.REJECTED,
                is_valid=False,
                errors=leakage_errors,
                error_code="LANGUAGE_SCRIPT_LEAKAGE",
            )

        # 3. Vocabulary grounding check
        normalized_source = self.extract_source_text(question)
        grounding_errors = self.check_vocabulary_grounding(normalized_source, enrichment)
        if grounding_errors:
            return QualityValidationResult(
                status=QualityValidationStatus.REJECTED,
                is_valid=False,
                errors=grounding_errors,
                error_code="UNGROUNDED_VOCABULARY",
            )

        # 4. Authoritative answer contradiction check
        contradictions = self.check_all_answer_contradictions(question, enrichment)
        if contradictions:
            return QualityValidationResult(
                status=QualityValidationStatus.SUSPICIOUS,
                is_valid=False,
                warnings=contradictions,
                errors=contradictions,
                error_code="CORRECT_ANSWER_CONTRADICTION",
            )

        # 5. Non-fatal pedagogical review warnings
        warnings = self.check_pedagogical_warnings(enrichment)

        return QualityValidationResult(
            status=QualityValidationStatus.VALID,
            is_valid=True,
            errors=[],
            warnings=warnings,
            error_code=None,
        )

    def validate_and_raise(
        self,
        question: Question | Any,
        enrichment: QuestionEnrichment,
    ) -> None:
        """Validate enrichment and raise appropriate EnrichmentQualityError if invalid or suspicious."""
        result = self.validate(question, enrichment)
        if result.is_valid:
            return

        if result.error_code == "UNGROUNDED_VOCABULARY":
            raise EnrichmentGroundingError(
                message=f"Ungrounded vocabulary: {'; '.join(result.errors)}",
                details=result.errors,
            )
        elif result.error_code == "CORRECT_ANSWER_CONTRADICTION":
            raise EnrichmentContradictionError(
                message=f"Contradictory answer analysis: {'; '.join(result.errors)}",
                details=result.errors,
            )
        elif result.error_code == "MISSING_DISTRACTOR_ANALYSIS":
            raise EnrichmentMissingDistractorError(
                message=f"Missing distractor analysis: {'; '.join(result.errors)}",
                details=result.errors,
            )
        elif result.error_code == "LANGUAGE_SCRIPT_LEAKAGE":
            raise EnrichmentScriptLeakageError(
                message=f"Foreign language script leakage: {'; '.join(result.errors)}",
                details=result.errors,
            )
        else:
            raise EnrichmentQualityError(
                message=f"Enrichment quality validation failed: {'; '.join(result.errors)}",
                code=result.error_code or "QUALITY_VALIDATION_ERROR",
                details=result.errors,
            )
