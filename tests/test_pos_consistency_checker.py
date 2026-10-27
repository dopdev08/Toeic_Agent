import ast
import csv
import hashlib
import json
from pathlib import Path
from typing import Any
import pytest

from app.schemas.enrichment import VALID_PARTS_OF_SPEECH
from app.services.pos_consistency_checker import (
    CSV_FIELDNAMES,
    OUTCOME_PHRASE_EVIDENCE_ONLY,
    OUTCOME_POS_ACCEPTABLE_VARIANT,
    OUTCOME_POS_AMBIGUOUS,
    OUTCOME_POS_CONTEXT_MISMATCH,
    OUTCOME_POS_MATCH,
    OUTCOME_SKIPPED_HYPHENATED_TARGET,
    OUTCOME_SKIPPED_INVALID_INPUT,
    OUTCOME_SKIPPED_MULTIPLE_OCCURRENCES,
    OUTCOME_SKIPPED_MULTIWORD_TARGET,
    OUTCOME_SKIPPED_NOT_IN_SENTENCE,
    OUTCOME_SKIPPED_UNSUPPORTED_EXPECTED_POS,
    PosConsistencyChecker,
    build_completed_sentence,
    evaluate_single_token_pos,
)


class StubToken:
    def __init__(
        self,
        text: str,
        pos_: str,
        tag_: str = "",
        lemma_: str = "",
        dep_: str = "dep",
        idx: int = 0,
        head: Any = None,
    ):
        self.text = text
        self.pos_ = pos_
        self.tag_ = tag_
        self.lemma_ = lemma_ or text.lower()
        self.dep_ = dep_
        self.idx = idx
        self.head = head or self

    @property
    def i(self) -> int:
        return self.idx


class StubSpan:
    def __init__(self, tokens: list[StubToken]):
        self.tokens = tokens
        self.text = " ".join(t.text for t in tokens)
        self.start_char = tokens[0].idx if tokens else 0
        self.end_char = tokens[-1].idx + len(tokens[-1].text) if tokens else 0
        self.root = tokens[-1] if tokens else None

    def __iter__(self):
        return iter(self.tokens)

    def __getitem__(self, item):
        return self.tokens[item]


class StubDoc:
    def __init__(self, tokens: list[StubToken], noun_chunks: list[StubSpan] | None = None):
        self.tokens = tokens
        self.noun_chunks = noun_chunks or []

    def __iter__(self):
        return iter(self.tokens)

    def __len__(self):
        return len(self.tokens)

    def __getitem__(self, item):
        if isinstance(item, slice):
            return StubSpan(self.tokens[item])
        return self.tokens[item]


class StubPipeline:
    _spacy_version = "3.8.16-stub"
    _model_version = "3.8.0-stub"

    def __init__(self, doc_factory):
        self.doc_factory = doc_factory

    def __call__(self, text: str):
        return self.doc_factory(text)


# ---------------------------------------------------------------------------
# Test 1: Clear matches for representative labels
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "expected_pos, token_text, pos_, tag_, expected_outcome",
    [
        ("noun", "report", "NOUN", "NN", OUTCOME_POS_MATCH),
        ("proper noun", "London", "PROPN", "NNP", OUTCOME_POS_MATCH),
        ("adjective", "annual", "ADJ", "JJ", OUTCOME_POS_MATCH),
        ("adverb", "quickly", "ADV", "RB", OUTCOME_POS_MATCH),
        ("verb", "examine", "VERB", "VB", OUTCOME_POS_MATCH),
        ("preposition", "under", "ADP", "IN", OUTCOME_POS_MATCH),
        ("conjunction", "although", "SCONJ", "IN", OUTCOME_POS_MATCH),
        ("conjunction", "and", "CCONJ", "CC", OUTCOME_POS_MATCH),
        ("determiner", "every", "DET", "DT", OUTCOME_POS_MATCH),
        ("pronoun", "they", "PRON", "PRP", OUTCOME_POS_MATCH),
        ("numeral", "fifteen", "NUM", "CD", OUTCOME_POS_MATCH),
        ("auxiliary verb", "is", "AUX", "VBZ", OUTCOME_POS_MATCH),
    ],
)
def test_clear_matches_for_representative_labels(expected_pos, token_text, pos_, tag_, expected_outcome):
    tok = StubToken(token_text, pos_=pos_, tag_=tag_)
    outcome, rule, rationale = evaluate_single_token_pos(expected_pos, tok)
    assert outcome == expected_outcome
    assert rule is not None
    assert rationale is not None


# ---------------------------------------------------------------------------
# Test 2: Clear mismatch produces POS_CONTEXT_MISMATCH with evidence
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "expected_pos, token_text, pos_, tag_",
    [
        ("noun", "very", "ADV", "RB"),
        ("adjective", "in", "ADP", "IN"),
        ("verb", "the", "DET", "DT"),
        ("preposition", "conference", "NOUN", "NN"),
        ("numeral", "carefully", "ADV", "RB"),
        ("modal verb", "manager", "NOUN", "NN"),
    ],
)
def test_clear_mismatch_produces_pos_context_mismatch(expected_pos, token_text, pos_, tag_):
    tok = StubToken(token_text, pos_=pos_, tag_=tag_)
    outcome, rule, rationale = evaluate_single_token_pos(expected_pos, tok)
    assert outcome == OUTCOME_POS_CONTEXT_MISMATCH
    assert pos_ in rule
    assert pos_ in rationale


# ---------------------------------------------------------------------------
# Test 3: noun accepts PROPN as acceptable variant (e.g. Auckland)
# ---------------------------------------------------------------------------
def test_noun_accepts_propn_as_acceptable_variant():
    tok = StubToken("Auckland", pos_="PROPN", tag_="NNP")
    outcome, rule, rationale = evaluate_single_token_pos("noun", tok)
    assert outcome == OUTCOME_POS_ACCEPTABLE_VARIANT
    assert "proper noun variant" in rationale


# ---------------------------------------------------------------------------
# Test 4: Modal AUX with tag_ == MD is distinguished (e.g. can)
# ---------------------------------------------------------------------------
def test_modal_aux_with_md_distinguished():
    tok_can = StubToken("can", pos_="AUX", tag_="MD")
    outcome, rule, rationale = evaluate_single_token_pos("modal verb", tok_can)
    assert outcome == OUTCOME_POS_MATCH

    # Non-modal AUX fails modal verb as ambiguous or mismatch
    tok_is = StubToken("is", pos_="AUX", tag_="VBZ")
    outcome_is, _, _ = evaluate_single_token_pos("modal verb", tok_is)
    assert outcome_is == OUTCOME_POS_AMBIGUOUS


# ---------------------------------------------------------------------------
# Test 5: Participles (leading, fixed, ongoing) and her are ambiguous/variants
# ---------------------------------------------------------------------------
def test_participles_and_her_are_conservative_ambiguous_or_variants():
    # 'leading' tagged as VBG compared against adjective
    tok_leading = StubToken("leading", pos_="VERB", tag_="VBG")
    outcome, _, _ = evaluate_single_token_pos("adjective", tok_leading)
    assert outcome == OUTCOME_POS_AMBIGUOUS

    # 'fixed' tagged as VBN compared against adjective
    tok_fixed = StubToken("fixed", pos_="VERB", tag_="VBN")
    outcome_f, _, _ = evaluate_single_token_pos("adjective", tok_fixed)
    assert outcome_f == OUTCOME_POS_AMBIGUOUS

    # 'her' tagged as PRON with PRP$ compared against determiner
    tok_her = StubToken("her", pos_="PRON", tag_="PRP$")
    outcome_her_det, _, _ = evaluate_single_token_pos("determiner", tok_her)
    assert outcome_her_det == OUTCOME_POS_ACCEPTABLE_VARIANT

    # 'her' tagged as PRON with PRP$ compared against pronoun
    outcome_her_pron, _, _ = evaluate_single_token_pos("pronoun", tok_her)
    assert outcome_her_pron == OUTCOME_POS_ACCEPTABLE_VARIANT


# ---------------------------------------------------------------------------
# Test 6: Multiword labels are never compared directly to single token POS
# ---------------------------------------------------------------------------
def test_multiword_labels_produce_phrase_evidence_only():
    tok1 = StubToken("media", pos_="NOUN", tag_="NN", idx=0)
    tok2 = StubToken("organization", pos_="NOUN", tag_="NN", idx=6)
    span = StubSpan([tok1, tok2])
    doc = StubDoc([tok1, tok2], noun_chunks=[span])

    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: doc))

    question_item = {
        "question_text": "She leads a _____ in London.",
        "option_a": "media organization",
        "option_b": "other",
        "option_c": "another",
        "option_d": "neither",
        "correct_answer": "A",
        "enrichment": {
            "vocabulary": [
                {"word": "media organization", "meaning": "tổ chức truyền thông", "part_of_speech": "noun phrase"}
            ]
        },
    }
    recs = checker.check_item(question_item)
    assert len(recs) == 1
    assert recs[0]["checker_outcome"] == OUTCOME_PHRASE_EVIDENCE_ONLY
    assert recs[0]["noun_chunk_match"] is True
    assert recs[0]["spacy_pos"] == "NOUN NOUN"


# ---------------------------------------------------------------------------
# Test 7: Hyphenated targets and split tokenizations are skipped explicitly
# ---------------------------------------------------------------------------
def test_hyphenated_and_multiword_single_targets_skipped_explicitly():
    tok = StubToken("over-the-counter", pos_="ADJ", idx=0)
    doc = StubDoc([tok])
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: doc))

    # Hyphenated target
    q_hyphen = {
        "question_text": "This medication is _____ without a prescription.",
        "option_a": "available",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "enrichment": {
            "vocabulary": [
                {"word": "over-the-counter", "meaning": "không cần đơn", "part_of_speech": "adjective"}
            ]
        },
    }
    recs = checker.check_item(q_hyphen)
    assert recs[0]["checker_outcome"] == OUTCOME_SKIPPED_HYPHENATED_TARGET

    # Multiword target declared with single-word POS
    q_multiword_single = {
        "question_text": "Please submit your _____ before Friday.",
        "option_a": "application",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "enrichment": {
            "vocabulary": [
                {"word": "application form", "meaning": "đơn đăng ký", "part_of_speech": "noun"}
            ]
        },
    }
    recs2 = checker.check_item(q_multiword_single)
    assert recs2[0]["checker_outcome"] == OUTCOME_SKIPPED_MULTIWORD_TARGET


# ---------------------------------------------------------------------------
# Test 8: Multiword correct answer inserted intact; capitalization reported
# ---------------------------------------------------------------------------
def test_multiword_answer_and_sentence_initial_capitalization():
    # Sentence-initial blank
    q_initial = {
        "question_text": "_____ it was raining, the event continued outdoors.",
        "option_a": "even though",
        "option_b": "despite",
        "option_c": "in spite",
        "option_d": "regardless",
        "correct_answer": "A",
    }
    res_initial = build_completed_sentence(q_initial)
    assert res_initial.blank_found is True
    assert res_initial.fill_case_adjustment is True
    assert res_initial.completed_sentence.startswith("Even though it was raining")

    # Non-initial blank
    q_mid = {
        "question_text": "The event continued _____ it was raining.",
        "option_a": "even though",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
    }
    res_mid = build_completed_sentence(q_mid)
    assert res_mid.blank_found is True
    assert res_mid.fill_case_adjustment is False
    assert "continued even though it was" in res_mid.completed_sentence


# ---------------------------------------------------------------------------
# Test 9: Surface match preferred over lemma fallback; reports match_mode
# ---------------------------------------------------------------------------
def test_surface_match_preferred_over_lemma_fallback():
    tok_att = StubToken("attendees", pos_="NOUN", tag_="NNS", lemma_="attendee", idx=0)
    doc = StubDoc([tok_att])
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: doc))

    # Surface match: target is 'attendees'
    q_surf = {
        "question_text": "Many _____ arrived early.",
        "option_a": "attendees",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "enrichment": {"vocabulary": [{"word": "attendees", "meaning": "người tham dự", "part_of_speech": "noun"}]},
    }
    recs_surf = checker.check_item(q_surf)
    assert recs_surf[0]["match_mode"] == "surface"
    assert recs_surf[0]["checker_outcome"] == OUTCOME_POS_MATCH

    # Lemma fallback: target in vocab is lemma 'attendee'
    q_lem = {
        "question_text": "Many _____ arrived early.",
        "option_a": "attendees",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "enrichment": {"vocabulary": [{"word": "attendee", "meaning": "người tham dự", "part_of_speech": "noun"}]},
    }
    recs_lem = checker.check_item(q_lem)
    assert recs_lem[0]["match_mode"] == "lemma"
    assert recs_lem[0]["checker_outcome"] == OUTCOME_POS_MATCH


# ---------------------------------------------------------------------------
# Test 10: Word absent from completed sentence yields SKIPPED_NOT_IN_SENTENCE
# ---------------------------------------------------------------------------
def test_word_absent_yields_skipped_not_in_sentence():
    tok = StubToken("lecture", pos_="NOUN", idx=0)
    doc = StubDoc([tok])
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: doc))

    q = {
        "question_text": "The lecture _____ at noon.",
        "option_a": "begins",
        "option_b": "expansion",  # distractor not in completed sentence
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "enrichment": {"vocabulary": [{"word": "expansion", "meaning": "sự mở rộng", "part_of_speech": "noun"}]},
    }
    recs = checker.check_item(q)
    assert recs[0]["checker_outcome"] == OUTCOME_SKIPPED_NOT_IN_SENTENCE
    assert recs[0]["match_mode"] == "none"


# ---------------------------------------------------------------------------
# Test 11: Repeated occurrences yield SKIPPED_MULTIPLE_OCCURRENCES
# ---------------------------------------------------------------------------
def test_repeated_occurrences_yield_ambiguity_skipped():
    tok1 = StubToken("time", pos_="NOUN", idx=0)
    tok2 = StubToken("after", pos_="ADP", idx=5)
    tok3 = StubToken("time", pos_="NOUN", idx=11)
    doc = StubDoc([tok1, tok2, tok3])
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: doc))

    q = {
        "question_text": "Time after _____ he arrived.",
        "option_a": "time",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "enrichment": {"vocabulary": [{"word": "time", "meaning": "thời gian", "part_of_speech": "noun"}]},
    }
    recs = checker.check_item(q)
    assert recs[0]["checker_outcome"] == OUTCOME_SKIPPED_MULTIPLE_OCCURRENCES
    assert len(recs[0]["candidate_occurrences"]) == 2


# ---------------------------------------------------------------------------
# Test 12: One malformed vocabulary item does not stop batch processing
# ---------------------------------------------------------------------------
def test_malformed_vocabulary_item_does_not_stop_batch():
    tok = StubToken("report", pos_="NOUN", idx=0)
    doc = StubDoc([tok])
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: doc))

    q = {
        "question_text": "Please read the _____ carefully.",
        "option_a": "report",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "enrichment": {
            "vocabulary": [
                "not_a_dict",  # malformed
                {"word": "", "part_of_speech": "noun"},  # empty word
                {"word": "report", "meaning": "báo cáo", "part_of_speech": "noun"},  # valid
            ]
        },
    }
    recs = checker.check_item(q)
    assert len(recs) == 3
    assert recs[0]["checker_outcome"] == OUTCOME_SKIPPED_INVALID_INPUT
    assert recs[1]["checker_outcome"] == OUTCOME_SKIPPED_INVALID_INPUT
    assert recs[2]["checker_outcome"] == OUTCOME_POS_MATCH


# ---------------------------------------------------------------------------
# Test 13: Missing/incompatible spaCy/model causes clear actionable error
# ---------------------------------------------------------------------------
def test_missing_model_raises_actionable_os_error():
    with pytest.raises(OSError, match="is not installed"):
        PosConsistencyChecker(model_name="nonexistent_spacy_model_xyz_999")


# ---------------------------------------------------------------------------
# Test 14: Malformed input report fails cleanly without mutating input
# ---------------------------------------------------------------------------
def test_malformed_input_report_fails_cleanly(tmp_path):
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: StubDoc([])))
    with pytest.raises(ValueError, match="must contain a 'results' or 'items' list"):
        checker.check_report_data({"metadata": "only"})


# ---------------------------------------------------------------------------
# Test 15: Every completed sentence has a reproducible SHA-256
# ---------------------------------------------------------------------------
def test_completed_sentence_has_reproducible_sha256():
    q = {
        "question_text": "Customer satisfaction is _____ important.",
        "option_a": "extremely",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
    }
    res1 = build_completed_sentence(q)
    res2 = build_completed_sentence(q)

    assert res1.completed_sentence == "Customer satisfaction is extremely important."
    expected_hash = hashlib.sha256(res1.completed_sentence.encode("utf-8")).hexdigest()
    assert res1.completed_sentence_sha256 == expected_hash
    assert res1.completed_sentence_sha256 == res2.completed_sentence_sha256


# ---------------------------------------------------------------------------
# Test 16: Checker module and CLI have NO app.db.* imports
# ---------------------------------------------------------------------------
def test_checker_has_no_app_db_imports():
    """Static AST check verifying pos_consistency_checker and CLI do not import app.db."""
    paths = [
        Path("app/services/pos_consistency_checker.py"),
        Path("scripts/check_pos_consistency.py"),
    ]
    for p in paths:
        assert p.exists(), f"File {p} does not exist"
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.db"), f"Forbidden import '{alias.name}' in {p}"
                    assert not alias.name.startswith("sqlalchemy"), f"Forbidden import '{alias.name}' in {p}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith("app.db"), f"Forbidden import from '{node.module}' in {p}"
                    assert not node.module.startswith("sqlalchemy"), f"Forbidden import from '{node.module}' in {p}"


# ---------------------------------------------------------------------------
# Test 17: Source enrichment status is preserved
# ---------------------------------------------------------------------------
def test_source_enrichment_status_preserved():
    tok = StubToken("lecture", pos_="NOUN", idx=0)
    doc = StubDoc([tok])
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: doc))

    q = {
        "question_text": "The lecture _____ at noon.",
        "option_a": "begins",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "status": "PASS_QUALITY_VALIDATED",
        "enrichment": {"vocabulary": [{"word": "lecture", "meaning": "bài giảng", "part_of_speech": "noun"}]},
    }
    recs = checker.check_item(q)
    assert recs[0]["original_status"] == "PASS_QUALITY_VALIDATED"


# ---------------------------------------------------------------------------
# Test 18: Source report SHA-256 is unchanged; output path is new
# ---------------------------------------------------------------------------
def test_source_report_sha256_unchanged_after_processing(tmp_path):
    report_file = tmp_path / "mock_report.json"
    content = json.dumps({
        "results": [
            {
                "question_id": 1,
                "question_no": 101,
                "question_text": "The lecture _____ at noon.",
                "option_a": "begins",
                "option_b": "b",
                "option_c": "c",
                "option_d": "d",
                "correct_answer": "A",
                "status": "PASS_QUALITY_VALIDATED",
                "enrichment": {
                    "vocabulary": [{"word": "lecture", "meaning": "bài giảng", "part_of_speech": "noun"}]
                },
            }
        ]
    })
    report_file.write_text(content, encoding="utf-8")
    sha_before = hashlib.sha256(report_file.read_bytes()).hexdigest()

    tok = StubToken("lecture", pos_="NOUN", idx=0)
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: StubDoc([tok])))

    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = checker.check_report_data(data, source_path=str(report_file))
    sha_after = hashlib.sha256(report_file.read_bytes()).hexdigest()

    assert sha_before == sha_after
    assert result["summary"]["total_questions_processed"] == 1


# ---------------------------------------------------------------------------
# Test 19: Manual annotation template contains required columns and blank verdicts
# ---------------------------------------------------------------------------
def test_manual_annotation_template_columns_and_blank_verdicts():
    tok = StubToken("very", pos_="ADV", tag_="RB", idx=0)
    checker = PosConsistencyChecker(nlp=StubPipeline(lambda s: StubDoc([tok])))

    q = {
        "question_text": "He is _____ tall.",
        "option_a": "very",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_answer": "A",
        "status": "PASS_QUALITY_VALIDATED",
        "enrichment": {"vocabulary": [{"word": "very", "meaning": "rất", "part_of_speech": "noun"}]},
    }
    recs = checker.check_item(q, source_report="test_report.json")
    rows = PosConsistencyChecker.generate_human_adjudication_rows(recs)

    assert len(rows) == 1
    row = rows[0]
    for col in CSV_FIELDNAMES:
        assert col in row, f"Missing required column '{col}' in template"
    assert row["human_verdict"] == ""
    assert row["reviewer_notes"] == ""
    assert row["checker_outcome"] == OUTCOME_POS_CONTEXT_MISMATCH


# ---------------------------------------------------------------------------
# Test 20: Optional real-model smoke test (skipped if model not installed)
# ---------------------------------------------------------------------------
def test_real_model_smoke_test_skipped_if_model_absent():
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
    except Exception:
        pytest.skip("spaCy or en_core_web_sm model not installed; skipping real-model smoke test")

    checker = PosConsistencyChecker(nlp=nlp, model_name="en_core_web_sm")
    item = {
        "question_text": "The lecture will take place at 6:00 P.M., _____ which attendees may ask questions.",
        "option_a": "across",
        "option_b": "after",
        "option_c": "inside",
        "option_d": "among",
        "correct_answer": "B",
        "status": "PASS_QUALITY_VALIDATED",
        "enrichment": {
            "vocabulary": [
                {"word": "attendees", "meaning": "người tham dự", "part_of_speech": "noun"},
                {"word": "take place", "meaning": "diễn ra", "part_of_speech": "verb phrase"},
            ]
        },
    }
    recs = checker.check_item(item, source_report="smoke_test")
    assert len(recs) == 2

    # 'attendees' should match noun
    attendees_rec = [r for r in recs if r["vocabulary_word"] == "attendees"][0]
    assert attendees_rec["checker_outcome"] == OUTCOME_POS_MATCH
    assert attendees_rec["spacy_pos"] == "NOUN"

    # 'take place' should produce phrase evidence only
    phrase_rec = [r for r in recs if r["vocabulary_word"] == "take place"][0]
    assert phrase_rec["checker_outcome"] == OUTCOME_PHRASE_EVIDENCE_ONLY
