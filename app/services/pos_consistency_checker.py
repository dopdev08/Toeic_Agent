"""Offline spaCy Part-of-Speech Consistency Checker for TOEIC Part 5 Enrichment.

This component performs offline linguistic diagnostics by comparing vocabulary items'
declared parts of speech against contextual spaCy annotations within the authoritative
completed question sentence.

CRITICAL ARCHITECTURAL BOUNDARIES:
- Offline only; zero LLM calls.
- Read-only; MUST NOT import app.db.*, create SQLAlchemy sessions, or access databases.
- Advisory only; produces diagnostic warnings for human review without modifying
  enrichment statuses (PASS_QUALITY_VALIDATED, etc.).
- Does not validate semantic truth, general syntax correctness, or topic accuracy.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from app.schemas.enrichment import VALID_PARTS_OF_SPEECH


# Explicit outcome codes (Section 9)
OUTCOME_POS_MATCH = "POS_MATCH"
OUTCOME_POS_ACCEPTABLE_VARIANT = "POS_ACCEPTABLE_VARIANT"
OUTCOME_POS_CONTEXT_MISMATCH = "POS_CONTEXT_MISMATCH"
OUTCOME_POS_AMBIGUOUS = "POS_AMBIGUOUS"
OUTCOME_SKIPPED_NOT_IN_SENTENCE = "SKIPPED_NOT_IN_SENTENCE"
OUTCOME_SKIPPED_MULTIPLE_OCCURRENCES = "SKIPPED_MULTIPLE_OCCURRENCES"
OUTCOME_SKIPPED_MULTIWORD_TARGET = "SKIPPED_MULTIWORD_TARGET"
OUTCOME_SKIPPED_HYPHENATED_TARGET = "SKIPPED_HYPHENATED_TARGET"
OUTCOME_SKIPPED_INVALID_INPUT = "SKIPPED_INVALID_INPUT"
OUTCOME_SKIPPED_UNSUPPORTED_EXPECTED_POS = "SKIPPED_UNSUPPORTED_EXPECTED_POS"
OUTCOME_PHRASE_EVIDENCE_ONLY = "PHRASE_EVIDENCE_ONLY"
OUTCOME_PHRASE_NOT_AUTOMATICALLY_VERIFIED = "PHRASE_NOT_AUTOMATICALLY_VERIFIED"

MULTIWORD_POS_LABELS = frozenset({"noun phrase", "verb phrase", "prepositional phrase", "phrase"})

CSV_FIELDNAMES = [
    "source_report",
    "question_id",
    "question_no",
    "vocabulary_word",
    "expected_pos",
    "spacy_pos",
    "spacy_tag",
    "spacy_lemma",
    "spacy_dep",
    "match_mode",
    "checker_outcome",
    "mapping_rationale",
    "completed_sentence_sha256",
    "human_verdict",
    "reviewer_notes",
]

# Prominent disclaimer text regarding scope limits (Section 2)
NOT_COVERED_BY_THIS_CHECKER_TEXT = """Not covered by this checker:
This diagnostic checker strictly compares declared vocabulary item part_of_speech tags
against contextual spaCy annotations in the authoritative completed question sentence.
It does NOT determine whether an entire enrichment is correct, and specifically does NOT validate:
1. Grammar topic appropriateness (e.g., Q104's grammar topic tested pronoun distinction but was labeled generally).
2. Sentence structure and pattern formula validity or reusability (e.g., Q110's generic SVO formulas).
3. Pedagogical soundness of explanations and distractor analyses (e.g., Q106's incorrect distractor rationale, Q120 missing distractor analysis).
4. Vietnamese translation accuracy (e.g., Q114's English-only meaning, Q130's translation/topic defects).
5. General grammatical syntax, subject-verb agreement, or tense harmony outside the target token.
6. The correctness of the authoritative answer key itself.

A status of zero POS warnings indicates only that no clear part-of-speech mismatches were detected
among items the checker could analyze. It must NEVER be paraphrased as 'the enrichment is correct'
or 'there are no errors'."""


@dataclass
class CompletedSentenceResult:
    """Holds authoritative completed sentence and blank-filling metadata."""

    completed_sentence: str
    completed_sentence_sha256: str
    fill_case_adjustment: bool
    authoritative_option_text: str
    correct_answer: str
    blank_found: bool
    skip_reason: str | None = None


def build_completed_sentence(question_data: dict[str, Any]) -> CompletedSentenceResult:
    """Construct authoritative completed sentence using authoritative correct option.

    - Validates correct_answer in A, B, C, D.
    - Replaces exactly the single designated blank run (r'_{3,}').
    - Applies deterministic sentence-initial capitalization if needed, recording fill_case_adjustment.
    - Computes reproducible SHA-256 hash of the exact UTF-8 sentence.
    """
    raw_question_text = question_data.get("question_text") or ""
    raw_correct_answer = question_data.get("correct_answer")

    if not isinstance(raw_correct_answer, str) or raw_correct_answer.strip().upper() not in {"A", "B", "C", "D"}:
        return CompletedSentenceResult(
            completed_sentence="",
            completed_sentence_sha256="",
            fill_case_adjustment=False,
            authoritative_option_text="",
            correct_answer=str(raw_correct_answer),
            blank_found=False,
            skip_reason=f"Missing or invalid authoritative correct_answer: {raw_correct_answer!r}",
        )

    ans_letter = raw_correct_answer.strip().upper()
    options_dict = question_data.get("options")
    if isinstance(options_dict, dict):
        option_text = options_dict.get(ans_letter)
    else:
        option_text = question_data.get(f"option_{ans_letter.lower()}")

    if option_text is None or not isinstance(option_text, str) or not option_text.strip():
        return CompletedSentenceResult(
            completed_sentence="",
            completed_sentence_sha256="",
            fill_case_adjustment=False,
            authoritative_option_text="",
            correct_answer=ans_letter,
            blank_found=False,
            skip_reason=f"Missing or empty option text for correct answer '{ans_letter}'",
        )

    # Locate designated blank run (3 or more underscores)
    blank_matches = list(re.finditer(r"_{3,}", raw_question_text))
    if not blank_matches:
        return CompletedSentenceResult(
            completed_sentence="",
            completed_sentence_sha256="",
            fill_case_adjustment=False,
            authoritative_option_text=option_text,
            correct_answer=ans_letter,
            blank_found=False,
            skip_reason="No designated blank marker (_{3,}) found in question_text",
        )

    if len(blank_matches) > 1:
        return CompletedSentenceResult(
            completed_sentence="",
            completed_sentence_sha256="",
            fill_case_adjustment=False,
            authoritative_option_text=option_text,
            correct_answer=ans_letter,
            blank_found=False,
            skip_reason=f"Ambiguous blank markers: found {len(blank_matches)} blanks in question_text",
        )

    match = blank_matches[0]
    start_idx, end_idx = match.start(), match.end()

    # Determine sentence-initial blank placement
    prefix = raw_question_text[:start_idx]
    is_sentence_initial = len(prefix.strip()) == 0

    fill_case_adjustment = False
    fill_text = option_text.strip()
    if is_sentence_initial and fill_text and fill_text[0].islower():
        fill_text = fill_text[0].upper() + fill_text[1:]
        fill_case_adjustment = True

    completed_sentence = prefix + fill_text + raw_question_text[end_idx:]
    sentence_hash = hashlib.sha256(completed_sentence.encode("utf-8")).hexdigest()

    return CompletedSentenceResult(
        completed_sentence=completed_sentence,
        completed_sentence_sha256=sentence_hash,
        fill_case_adjustment=fill_case_adjustment,
        authoritative_option_text=option_text,
        correct_answer=ans_letter,
        blank_found=True,
        skip_reason=None,
    )


def evaluate_single_token_pos(expected_pos: str, token: Any) -> tuple[str, str, str]:
    """Apply conservative, explicit POS mapping table (Section 7).

    Returns:
        (outcome_code, mapping_rule, mapping_rationale)
    """
    pos_tag = getattr(token, "pos_", "")
    fine_tag = getattr(token, "tag_", "")
    dep_tag = getattr(token, "dep_", "")
    lemma = getattr(token, "lemma_", "")
    token_text = getattr(token, "text", "")

    # 1. noun
    if expected_pos == "noun":
        if pos_tag == "NOUN":
            return (OUTCOME_POS_MATCH, "NOUN -> noun", "Token tagged as NOUN")
        if pos_tag == "PROPN":
            return (
                OUTCOME_POS_ACCEPTABLE_VARIANT,
                "PROPN -> noun (acceptable variant)",
                f"Token '{token_text}' tagged as PROPN; accepted as proper noun variant of noun",
            )
        if pos_tag == "VERB" and fine_tag == "VBG":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "VBG -> noun (ambiguous)",
                "Token is a -ing verbal/gerund form with plausible nominal or verbal usage",
            )
        if pos_tag == "ADJ":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "ADJ -> noun (ambiguous)",
                "Token tagged as ADJ with possible nominal head or modifier role",
            )
        if pos_tag in {"ADV", "ADP", "CCONJ", "SCONJ", "DET"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != noun",
                f"Token clearly functions as {pos_tag} in context, clashing with expected noun",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> noun (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 2. proper noun
    if expected_pos == "proper noun":
        if pos_tag == "PROPN":
            return (OUTCOME_POS_MATCH, "PROPN -> proper noun", "Token tagged as PROPN")
        if pos_tag == "NOUN":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "NOUN -> proper noun (ambiguous)",
                "Token tagged as common NOUN, but may represent an unfamiliar name, brand, or place",
            )
        if pos_tag in {"ADP", "ADV", "CCONJ", "SCONJ", "DET"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != proper noun",
                f"Token functions as {pos_tag}, clashing with proper noun",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> proper noun (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 3. adjective
    if expected_pos == "adjective":
        if pos_tag == "ADJ":
            return (OUTCOME_POS_MATCH, "ADJ -> adjective", "Token tagged as ADJ")
        if pos_tag == "VERB" and fine_tag in {"VBN", "VBG"}:
            return (
                OUTCOME_POS_AMBIGUOUS,
                f"{fine_tag} -> adjective (ambiguous)",
                f"Token is a participle ({fine_tag}) with plausible participial adjective role",
            )
        if pos_tag == "NOUN" and dep_tag in {"compound", "nmod"}:
            return (
                OUTCOME_POS_AMBIGUOUS,
                "NOUN (compound) -> adjective (ambiguous)",
                "Token tagged as NOUN in compound or noun-modifier position",
            )
        if pos_tag in {"ADV", "ADP", "CCONJ", "SCONJ", "PRON"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != adjective",
                f"Token clearly functions as {pos_tag}, clashing with adjective",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> adjective (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 4. adverb
    if expected_pos == "adverb":
        if pos_tag == "ADV":
            return (OUTCOME_POS_MATCH, "ADV -> adverb", "Token tagged as ADV")
        if pos_tag == "ADJ":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "ADJ -> adverb (ambiguous)",
                "Token tagged as ADJ; syntactic attachment or predicate role makes classification ambiguous",
            )
        if pos_tag in {"NOUN", "ADP", "CCONJ", "SCONJ", "DET"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != adverb",
                f"Token clearly functions as {pos_tag}, clashing with adverb",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> adverb (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 5. verb
    if expected_pos == "verb":
        if pos_tag == "VERB":
            return (OUTCOME_POS_MATCH, "VERB -> verb", "Token tagged as VERB")
        if pos_tag == "AUX":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "AUX -> verb (ambiguous)",
                "Token tagged as AUX; auxiliary vs main verb polyfunctionality",
            )
        if fine_tag in {"VBG", "VBN"}:
            return (
                OUTCOME_POS_AMBIGUOUS,
                f"{fine_tag} -> verb (ambiguous)",
                "Participle or gerund form with uncertain clausal vs modifier role",
            )
        if pos_tag in {"NOUN", "ADJ", "ADV", "ADP", "DET"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != verb",
                f"Token clearly functions as {pos_tag} without verbal evidence in context",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> verb (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 6. auxiliary verb
    if expected_pos == "auxiliary verb":
        if pos_tag == "AUX" and fine_tag != "MD":
            return (OUTCOME_POS_MATCH, "AUX (!= MD) -> auxiliary verb", "Token tagged as non-modal AUX")
        if pos_tag == "AUX" and fine_tag == "MD":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "AUX (MD) -> auxiliary verb (ambiguous)",
                "Modal auxiliary overlap with general auxiliary category",
            )
        if pos_tag == "VERB" and lemma.lower() in {"be", "have", "do"}:
            return (
                OUTCOME_POS_AMBIGUOUS,
                "VERB (be/have/do) -> auxiliary verb (ambiguous)",
                "Main-verb vs auxiliary ambiguity for primary verb",
            )
        if pos_tag in {"NOUN", "ADJ", "ADV", "ADP", "DET"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != auxiliary verb",
                f"Token clearly functions as {pos_tag}, not auxiliary",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> auxiliary verb (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 7. modal verb
    if expected_pos == "modal verb":
        if pos_tag == "AUX" and fine_tag == "MD":
            return (OUTCOME_POS_MATCH, "AUX (MD) -> modal verb", "Token tagged as modal auxiliary (MD)")
        if pos_tag == "AUX":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "AUX (!= MD) -> modal verb (ambiguous)",
                "Auxiliary without fine-grained MD tag",
            )
        if pos_tag in {"NOUN", "ADJ", "ADV", "ADP"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != modal verb",
                f"Token clearly functions as {pos_tag}, clashing with modal verb",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> modal verb (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 8. preposition
    if expected_pos == "preposition":
        if pos_tag == "ADP":
            return (OUTCOME_POS_MATCH, "ADP -> preposition", "Token tagged as ADP")
        if pos_tag == "SCONJ":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "SCONJ -> preposition (ambiguous)",
                "Subordinating conjunction / preposition syntactic overlap",
            )
        if pos_tag in {"NOUN", "ADV", "CCONJ"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != preposition",
                f"Token clearly functions as {pos_tag}, clashing with preposition",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> preposition (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 9. conjunction
    if expected_pos == "conjunction":
        if pos_tag in {"CCONJ", "SCONJ"}:
            return (OUTCOME_POS_MATCH, f"{pos_tag} -> conjunction", "Token tagged as CCONJ or SCONJ")
        if pos_tag == "ADP":
            return (
                OUTCOME_POS_AMBIGUOUS,
                "ADP -> conjunction (ambiguous)",
                "Preposition / subordinator polyfunctional overlap",
            )
        if pos_tag in {"NOUN", "ADJ", "ADV"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != conjunction",
                f"Token clearly functions as {pos_tag}, clashing with conjunction",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> conjunction (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 10. pronoun
    if expected_pos == "pronoun":
        if pos_tag == "PRON":
            if fine_tag == "PRP$":
                return (
                    OUTCOME_POS_ACCEPTABLE_VARIANT,
                    "PRON (PRP$) -> pronoun (acceptable variant)",
                    "Possessive pronoun/determiner taxonomy variation (e.g. her)",
                )
            return (OUTCOME_POS_MATCH, "PRON -> pronoun", "Token tagged as PRON")
        if pos_tag == "DET" or fine_tag == "PRP$":
            return (
                OUTCOME_POS_ACCEPTABLE_VARIANT,
                "DET/PRP$ -> pronoun (acceptable variant)",
                "Possessive pronoun/determiner taxonomy split",
            )
        if pos_tag in {"NOUN", "VERB", "ADP"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != pronoun",
                f"Token clearly functions as {pos_tag}, clashing with pronoun",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> pronoun (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 11. determiner
    if expected_pos == "determiner":
        if pos_tag == "DET":
            return (OUTCOME_POS_MATCH, "DET -> determiner", "Token tagged as DET")
        if pos_tag == "PRON" and fine_tag == "PRP$":
            return (
                OUTCOME_POS_ACCEPTABLE_VARIANT,
                "PRON (PRP$) -> determiner (acceptable variant)",
                "Possessive determiner/pronoun variation (e.g. her)",
            )
        if pos_tag in {"NOUN", "VERB", "ADP"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != determiner",
                f"Token clearly functions as {pos_tag}, clashing with determiner",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> determiner (unlisted)", f"Uncertain POS combination: {pos_tag}")

    # 12. numeral
    if expected_pos == "numeral":
        if pos_tag == "NUM":
            return (OUTCOME_POS_MATCH, "NUM -> numeral", "Token tagged as NUM")
        if pos_tag in {"ADJ", "NOUN"}:
            return (
                OUTCOME_POS_AMBIGUOUS,
                f"{pos_tag} -> numeral (ambiguous)",
                "Numeric expression represented as ADJ or NOUN",
            )
        if pos_tag in {"ADP", "CCONJ", "VERB", "ADV"}:
            return (
                OUTCOME_POS_CONTEXT_MISMATCH,
                f"{pos_tag} != numeral",
                f"Token clearly functions as {pos_tag}, clashing with numeral",
            )
        return (OUTCOME_POS_AMBIGUOUS, f"{pos_tag} -> numeral (unlisted)", f"Uncertain POS combination: {pos_tag}")

    return (OUTCOME_POS_AMBIGUOUS, f"unsupported -> {expected_pos}", f"Unlisted POS category: {expected_pos}")


class PosConsistencyChecker:
    """Offline linguistic consistency checker comparing vocabulary POS against spaCy annotations."""

    def __init__(self, nlp: Any = None, model_name: str = "en_core_web_sm") -> None:
        self.model_name = model_name
        self.model_version: str | None = None
        self.spacy_version: str | None = None

        if nlp is not None:
            self.nlp = nlp
            self.spacy_version = getattr(nlp, "_spacy_version", "stub")
            self.model_version = getattr(nlp, "_model_version", "stub")
        else:
            try:
                import spacy
            except ImportError as exc:
                raise ImportError(
                    "spaCy is not installed. To run the POS consistency checker, install optional NLP dependencies:\n"
                    "  pip install -r requirements-nlp.txt\n"
                    "  python -m spacy validate"
                ) from exc

            self.spacy_version = spacy.__version__
            try:
                self.nlp = spacy.load(model_name)
                # Extract model version from meta if available
                meta = getattr(self.nlp, "meta", {})
                self.model_version = meta.get("version") if isinstance(meta, dict) else None
            except OSError as exc:
                raise OSError(
                    f"spaCy model '{model_name}' is not installed.\n"
                    f"Install it via:\n"
                    f"  pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl\n"
                    f"Or run:\n"
                    f"  python -m spacy validate"
                ) from exc

    def check_vocabulary_item(
        self,
        vocab_item: Any,
        doc: Any,
        completed_sentence_res: CompletedSentenceResult,
        source_report: str,
        question_id: Any,
        question_no: Any,
        original_status: str,
    ) -> dict[str, Any]:
        """Check a single vocabulary item against spaCy parsed completed sentence."""
        record: dict[str, Any] = {
            "source_report": source_report,
            "question_id": question_id,
            "question_no": question_no,
            "original_status": original_status,
            "vocabulary_word": None,
            "expected_pos": None,
            "completed_sentence": completed_sentence_res.completed_sentence,
            "completed_sentence_sha256": completed_sentence_res.completed_sentence_sha256,
            "fill_case_adjustment": completed_sentence_res.fill_case_adjustment,
            "authoritative_option_text": completed_sentence_res.authoritative_option_text,
            "correct_answer": completed_sentence_res.correct_answer,
            "match_mode": "none",
            "token_text": None,
            "token_index": None,
            "token_span": None,
            "spacy_pos": None,
            "spacy_tag": None,
            "spacy_lemma": None,
            "spacy_dep": None,
            "head_token": None,
            "head_pos": None,
            "candidate_occurrences": [],
            "noun_chunk_match": None,
            "checker_outcome": None,
            "mapping_rule": None,
            "mapping_rationale": None,
        }

        # 1. Validate vocabulary item dictionary
        if not isinstance(vocab_item, dict):
            record["checker_outcome"] = OUTCOME_SKIPPED_INVALID_INPUT
            record["mapping_rationale"] = f"Vocabulary item must be a dictionary, got {type(vocab_item).__name__}"
            return record

        word = vocab_item.get("word")
        expected_pos = vocab_item.get("part_of_speech")

        record["vocabulary_word"] = word
        record["expected_pos"] = expected_pos

        if not isinstance(word, str) or not word.strip() or not isinstance(expected_pos, str) or not expected_pos.strip():
            record["checker_outcome"] = OUTCOME_SKIPPED_INVALID_INPUT
            record["mapping_rationale"] = f"Missing or empty word ({word!r}) or part_of_speech ({expected_pos!r})"
            return record

        word_clean = word.strip()
        expected_pos_clean = expected_pos.strip().lower()

        if expected_pos_clean not in VALID_PARTS_OF_SPEECH:
            record["checker_outcome"] = OUTCOME_SKIPPED_UNSUPPORTED_EXPECTED_POS
            record["mapping_rationale"] = f"Expected part_of_speech '{expected_pos_clean}' not in canonical VALID_PARTS_OF_SPEECH"
            return record

        if not completed_sentence_res.blank_found:
            record["checker_outcome"] = OUTCOME_SKIPPED_INVALID_INPUT
            record["mapping_rationale"] = f"Cannot analyze item: {completed_sentence_res.skip_reason}"
            return record

        # 2. Multiword-unit evaluation (Section 8)
        if expected_pos_clean in MULTIWORD_POS_LABELS:
            return self._evaluate_multiword_item(word_clean, expected_pos_clean, doc, record)

        # 3. Single-word token edge cases (Section 6)
        if "-" in word_clean:
            record["checker_outcome"] = OUTCOME_SKIPPED_HYPHENATED_TARGET
            record["mapping_rationale"] = (
                f"Hyphenated compound '{word_clean}' skipped for single-token POS comparison to prevent tokenizer fragment comparison"
            )
            return record

        if " " in word_clean:
            record["checker_outcome"] = OUTCOME_SKIPPED_MULTIWORD_TARGET
            record["mapping_rationale"] = (
                f"Target '{word_clean}' contains multiple words but was declared as single-word POS '{expected_pos_clean}'"
            )
            return record

        # 4. Token alignment in completed sentence
        target_lower = word_clean.lower()
        surface_matches = [t for t in doc if t.text.lower() == target_lower]

        if len(surface_matches) == 1:
            record["match_mode"] = "surface"
            token = surface_matches[0]
        elif len(surface_matches) > 1:
            record["match_mode"] = "surface"
            record["checker_outcome"] = OUTCOME_SKIPPED_MULTIPLE_OCCURRENCES
            record["candidate_occurrences"] = [
                {"token_index": t.i, "token_text": t.text, "pos": t.pos_, "tag": t.tag_}
                for t in surface_matches
            ]
            record["mapping_rationale"] = f"Word '{word_clean}' occurs {len(surface_matches)} times in completed sentence"
            return record
        else:
            # Conservative lemma fallback
            lemma_matches = [t for t in doc if t.lemma_.lower() == target_lower]
            if len(lemma_matches) == 1:
                record["match_mode"] = "lemma"
                token = lemma_matches[0]
            elif len(lemma_matches) > 1:
                record["match_mode"] = "lemma"
                record["checker_outcome"] = OUTCOME_SKIPPED_MULTIPLE_OCCURRENCES
                record["candidate_occurrences"] = [
                    {"token_index": t.i, "token_text": t.text, "lemma": t.lemma_, "pos": t.pos_, "tag": t.tag_}
                    for t in lemma_matches
                ]
                record["mapping_rationale"] = f"Lemma '{target_lower}' matches {len(lemma_matches)} tokens in completed sentence"
                return record
            else:
                record["match_mode"] = "none"
                record["checker_outcome"] = OUTCOME_SKIPPED_NOT_IN_SENTENCE
                record["mapping_rationale"] = f"Word '{word_clean}' (or lemma) not found in completed authoritative sentence"
                return record

        # Populate token metadata
        record["token_text"] = token.text
        record["token_index"] = token.i
        record["token_span"] = (token.idx, token.idx + len(token.text))
        record["spacy_pos"] = token.pos_
        record["spacy_tag"] = token.tag_
        record["spacy_lemma"] = token.lemma_
        record["spacy_dep"] = token.dep_
        record["head_token"] = token.head.text if token.head is not None else None
        record["head_pos"] = token.head.pos_ if token.head is not None else None

        # 5. Evaluate mapping rules
        outcome, rule, rationale = evaluate_single_token_pos(expected_pos_clean, token)
        record["checker_outcome"] = outcome
        record["mapping_rule"] = rule
        record["mapping_rationale"] = rationale
        return record

    def _evaluate_multiword_item(
        self,
        word_clean: str,
        expected_pos_clean: str,
        doc: Any,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Align multiword phrase target across tokens and record evidence without single-token forcing."""
        phrase_tokens = [w.lower() for w in word_clean.split()]
        num_target_tokens = len(phrase_tokens)

        doc_tokens = [t.text.lower() for t in doc]
        matches = []
        for i in range(len(doc_tokens) - num_target_tokens + 1):
            if doc_tokens[i : i + num_target_tokens] == phrase_tokens:
                matches.append(i)

        if not matches:
            record["match_mode"] = "none"
            record["checker_outcome"] = OUTCOME_SKIPPED_NOT_IN_SENTENCE
            record["mapping_rationale"] = f"Multiword phrase '{word_clean}' not found in completed sentence"
            return record

        if len(matches) > 1:
            record["checker_outcome"] = OUTCOME_SKIPPED_MULTIPLE_OCCURRENCES
            record["candidate_occurrences"] = [{"start_index": m, "length": num_target_tokens} for m in matches]
            record["mapping_rationale"] = f"Multiword phrase '{word_clean}' matches multiple spans in sentence"
            return record

        start_token_idx = matches[0]
        end_token_idx = start_token_idx + num_target_tokens
        span = doc[start_token_idx:end_token_idx]

        record["match_mode"] = "surface"
        record["token_text"] = span.text
        record["token_index"] = start_token_idx
        record["token_span"] = (span.start_char, span.end_char)
        record["spacy_pos"] = " ".join(t.pos_ for t in span)
        record["spacy_tag"] = " ".join(t.tag_ for t in span)
        record["spacy_lemma"] = " ".join(t.lemma_ for t in span)
        record["spacy_dep"] = " ".join(t.dep_ for t in span)
        head_t = span.root if hasattr(span, "root") else span[-1]
        record["head_token"] = head_t.text
        record["head_pos"] = head_t.pos_

        if expected_pos_clean == "noun phrase":
            # Check noun_chunks if available
            noun_chunks = getattr(doc, "noun_chunks", [])
            target_norm = " ".join(phrase_tokens)
            chunk_texts = [" ".join(t.text.lower().split()) for t in noun_chunks]
            is_matched = any(target_norm == ct or target_norm in ct for ct in chunk_texts)
            record["noun_chunk_match"] = is_matched
            record["checker_outcome"] = OUTCOME_PHRASE_EVIDENCE_ONLY
            record["mapping_rule"] = "multiword -> noun phrase"
            record["mapping_rationale"] = (
                f"Multiword noun phrase span recorded (noun_chunk_match={is_matched}); span evidence only"
            )
        elif expected_pos_clean in {"verb phrase", "prepositional phrase"}:
            record["checker_outcome"] = OUTCOME_PHRASE_EVIDENCE_ONLY
            record["mapping_rule"] = f"multiword -> {expected_pos_clean}"
            record["mapping_rationale"] = (
                f"Multiword {expected_pos_clean} span recorded; phrase-level evidence only (not automatically verified)"
            )
        else:
            record["checker_outcome"] = OUTCOME_PHRASE_EVIDENCE_ONLY
            record["mapping_rule"] = "multiword -> phrase"
            record["mapping_rationale"] = "Generic multiword phrase span recorded; evidence only"

        return record

    def check_item(self, item: dict[str, Any], source_report: str = "unknown") -> list[dict[str, Any]]:
        """Run POS consistency check for all vocabulary items in a question record."""
        q_id = item.get("id") or item.get("question_id")
        q_no = item.get("question_no")
        original_status = item.get("status") or item.get("review_status") or "UNKNOWN"

        completed_res = build_completed_sentence(item)

        enrichment_data = item.get("enrichment")
        if not isinstance(enrichment_data, dict):
            raw_resp = item.get("raw_response")
            if isinstance(raw_resp, str) and raw_resp.strip():
                try:
                    enrichment_data = json.loads(raw_resp)
                except Exception:
                    enrichment_data = None

        if not isinstance(enrichment_data, dict):
            return [
                {
                    "source_report": source_report,
                    "question_id": q_id,
                    "question_no": q_no,
                    "original_status": original_status,
                    "vocabulary_word": None,
                    "expected_pos": None,
                    "completed_sentence": completed_res.completed_sentence,
                    "completed_sentence_sha256": completed_res.completed_sentence_sha256,
                    "fill_case_adjustment": completed_res.fill_case_adjustment,
                    "authoritative_option_text": completed_res.authoritative_option_text,
                    "correct_answer": completed_res.correct_answer,
                    "match_mode": "none",
                    "checker_outcome": OUTCOME_SKIPPED_INVALID_INPUT,
                    "mapping_rationale": "Item does not contain valid enrichment object or parseable raw_response",
                }
            ]

        vocab_list = enrichment_data.get("vocabulary")
        if not isinstance(vocab_list, list) or not vocab_list:
            return [
                {
                    "source_report": source_report,
                    "question_id": q_id,
                    "question_no": q_no,
                    "original_status": original_status,
                    "vocabulary_word": None,
                    "expected_pos": None,
                    "completed_sentence": completed_res.completed_sentence,
                    "completed_sentence_sha256": completed_res.completed_sentence_sha256,
                    "fill_case_adjustment": completed_res.fill_case_adjustment,
                    "authoritative_option_text": completed_res.authoritative_option_text,
                    "correct_answer": completed_res.correct_answer,
                    "match_mode": "none",
                    "checker_outcome": OUTCOME_SKIPPED_INVALID_INPUT,
                    "mapping_rationale": "Enrichment contains no vocabulary list",
                }
            ]

        # Parse completed sentence with spaCy
        if completed_res.blank_found:
            doc = self.nlp(completed_res.completed_sentence)
        else:
            doc = None

        records = []
        for v in vocab_list:
            rec = self.check_vocabulary_item(
                vocab_item=v,
                doc=doc,
                completed_sentence_res=completed_res,
                source_report=source_report,
                question_id=q_id,
                question_no=q_no,
                original_status=original_status,
            )
            records.append(rec)
        return records

    def check_report_data(
        self,
        report_data: dict[str, Any],
        source_path: str | None = None,
    ) -> dict[str, Any]:
        """Process all items in a report and return structured diagnostics report payload."""
        source_name = Path(source_path).name if source_path else "memory_report"
        raw_items = report_data.get("results")
        if raw_items is None:
            raw_items = report_data.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("Report data must contain a 'results' or 'items' list")

        all_records: list[dict[str, Any]] = []
        outcome_counts: dict[str, int] = {}

        for item in raw_items:
            recs = self.check_item(item, source_report=source_name)
            all_records.extend(recs)
            for r in recs:
                code = r.get("checker_outcome") or "UNKNOWN"
                outcome_counts[code] = outcome_counts.get(code, 0) + 1

        total_checked = sum(
            1 for r in all_records
            if r.get("checker_outcome") in {
                OUTCOME_POS_MATCH,
                OUTCOME_POS_ACCEPTABLE_VARIANT,
                OUTCOME_POS_CONTEXT_MISMATCH,
                OUTCOME_POS_AMBIGUOUS,
                OUTCOME_PHRASE_EVIDENCE_ONLY,
                OUTCOME_PHRASE_NOT_AUTOMATICALLY_VERIFIED,
            }
        )
        total_mismatches = outcome_counts.get(OUTCOME_POS_CONTEXT_MISMATCH, 0)

        return {
            "metadata": {
                "source_report_path": str(source_path) if source_path else None,
                "source_report_sha256": None,  # to be injected by caller
                "python_version": sys.version,
                "spacy_version": self.spacy_version,
                "spacy_model": self.model_name,
                "spacy_model_version": self.model_version,
                "schema_revision": "Task 3.3 POS consistency diagnostic schema",
            },
            "summary": {
                "total_questions_processed": len(raw_items),
                "total_vocabulary_items": len(all_records),
                "total_items_aligned_and_checked": total_checked,
                "total_pos_mismatch_warnings": total_mismatches,
                "outcome_counts": outcome_counts,
            },
            "not_covered_by_this_checker": NOT_COVERED_BY_THIS_CHECKER_TEXT,
            "diagnostics": all_records,
        }

    @staticmethod
    def generate_human_adjudication_rows(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract rows for human adjudication template with verdicts left blank."""
        rows = []
        for r in diagnostics:
            # Include warnings, ambiguous items, and acceptable variants
            outcome = r.get("checker_outcome")
            if outcome in {OUTCOME_POS_CONTEXT_MISMATCH, OUTCOME_POS_AMBIGUOUS, OUTCOME_POS_ACCEPTABLE_VARIANT}:
                row = {
                    "source_report": r.get("source_report"),
                    "question_id": r.get("question_id"),
                    "question_no": r.get("question_no"),
                    "vocabulary_word": r.get("vocabulary_word"),
                    "expected_pos": r.get("expected_pos"),
                    "spacy_pos": r.get("spacy_pos"),
                    "spacy_tag": r.get("spacy_tag"),
                    "spacy_lemma": r.get("spacy_lemma"),
                    "spacy_dep": r.get("spacy_dep"),
                    "match_mode": r.get("match_mode"),
                    "checker_outcome": r.get("checker_outcome"),
                    "mapping_rationale": r.get("mapping_rationale"),
                    "completed_sentence_sha256": r.get("completed_sentence_sha256"),
                    "human_verdict": "",  # Blank for human review
                    "reviewer_notes": "",
                }
                rows.append(row)
        return rows
