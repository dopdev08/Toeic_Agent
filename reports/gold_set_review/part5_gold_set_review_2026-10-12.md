# TOEIC Part 5 Enrichment Gold Set Calibration Audit

**Document Date:** 2026-10-12  
**Target Scope:** ETS2026 Part 5 Seed Set (12 Questions: 101, 102, 104, 105, 108, 110, 112, 114, 119, 124, 127, 130)  
**Evaluator:** Independent Linguistic & Pedagogical Calibration Audit  
**Overall Status:** `DRAFT_NEEDS_HUMAN_REVIEW` (All 12 items remain unapproved pending human reviewer sign-off)  

---

## 1. Executive Summary & Purpose

The objective of this calibration audit is to establish an authoritative, human-reviewable reference set for evaluating the pedagogical correctness of automated TOEIC Part 5 enrichment. Following Task 1's strict schema enforcement, this review audits the candidate enrichments to prevent LLM hallucinations, prompt leakage, and superficial justifications from silently compromising downstream model evaluations or CI regression test fixtures.

### Key Audit Policies
1. **Zero Silent Approvals:** An LLM-generated draft is never treated as ground truth. Every item remains `DRAFT_NEEDS_HUMAN_REVIEW` until independently signed off by a human English teacher or the project owner.
2. **Authoritative Answer Keys:** Question source records from `toeic_agent.db` are the single source of truth. Generated explanations can never override the source answer key.
3. **Linguistic Separation:** Observed source facts (exact question text, options, answer keys, database counts) are strictly separated from linguistic and pedagogical judgments.
4. **No Production Modifications:** Production code, database records, prompts, schemas, and validators were left completely untouched in read-only mode.

---

## 2. Benchmark & Source Provenance

| Source Artifact | Location / Identifier | Status / Finding |
| :--- | :--- | :--- |
| **Source Database** | `toeic_agent.db` (read-only snapshot) | Verified 30 Part 5 questions; 12 target records extracted without modification. |
| **Qwen Benchmark** | `reports/part5_batch_qwen2.5_3b_20261012_123315.json` | 11/12 `PASS_QUALITY_VALIDATED`, 1/12 `REJECTED_QUALITY` (Q112 ungrounded `expansion`). Pervasive hallucinated formulas (SVOO, `vary with to`, `fee: (verb form): (verb form)`), schema violations (extra keys E in Q119, `Explanation` in Q127). |
| **Gemini Benchmark** | `reports/part5_batch_gemini-3.5-flash-lite_20261012_122158.json` | 11/12 `PASS_QUALITY_VALIDATED`, 1/12 `FAIL_JSON_DECODE` (Q102). Better vocabulary coverage but still exhibits positional vs semantic ambiguities. |
| **Initial Gold Draft** | `reports/part5_gold_set_draft_12_2026-10-12.json` | 12 seed draft enrichments created to patch catastrophic Qwen failures. Passes basic schema/grounding but exhibits 6 recurring pedagogical defect categories detailed below. |

---

## 3. Recurring Issue Types & Defect Taxonomy

Our dimension-by-dimension audit of the initial draft revealed six recurring defect categories:

1. **Positional vs. Semantic Grammar Classification:**
   - *Symptom:* Classifying a blank strictly by its surrounding parts of speech rather than what the test item actually differentiates.
   - *Examples:* In Q114, all 4 options are adverbs (`lightly`, `loyally`, `actively`, `cleanly`), yet the draft labeled it "Adverb modifying a present-progressive verb phrase" (implying a word-form test). In Q127, all 4 options are abstract nouns in `-tion`, yet the draft labeled it "Noun form / collocation".
   - *Impact:* Misleads learners into believing they need to identify parts of speech rather than understand contextual semantic collocation.

2. **Incomplete Sentence Structure & Omitted Constituents:**
   - *Symptom:* Abbreviating full sentences as generic formulas like "main clause", omitting fronted attributions (`According to CEO...`), prepositional phrases (`in Pepper Valley`), or agent phrases (`by residents and visitors`). In Q119, a trailing whitespace was preserved in the string.
   - *Impact:* Deprives learners of clause-level role parsing.

3. **Overly Lexicalized / Generic Patterns:**
   - *Symptom:* Emitting patterns that are simply the raw phrase string (e.g., Q108 pattern `product line`, Q104 pattern `her + noun phrase`) instead of reusable grammatical syntactic templates.
   - *Impact:* Fails to teach a transferable grammatical rule.

4. **Taxonomy Inconsistency in Multi-Word Expressions:**
   - *Symptom:* In `app/schemas/enrichment.py`, multi-word grammatical collocations (e.g., `product line`, `antique shop`, `solicit feedback`) are designated as `phrase`. In Q110, `cash register` was labeled as `noun`, creating taxonomy drift.
   - *Impact:* Causes inconsistent evaluation metrics for POS accuracy across the dataset.

5. **Superficial Distractor Rationales:**
   - *Symptom:* Dismissing distractors with vague claims like "không phù hợp với ý cần diễn đạt" rather than explaining the exact structural or transitivity reason.
   - *Example:* In Q119, options A (`reply`), B (`capture`), D (`accumulate`) fail because `reply` requires `to`, while `capture` and `accumulate` are direct transitive verbs that cannot take `for + V-ing` to mean compensating.

6. **Subjective Difficulty Underestimation:**
   - *Symptom:* Labeling questions requiring fine distinctions between two adjectives (`diagnostic` vs. `diagnosable` in Q130) or business IT collocations (`the spread of viruses` in Q105) as `easy`.
   - *Impact:* Distorts test calibration.

---

## 4. Prioritized Defect Summary Table

| Priority | Question | Field / Dimension | Observed Defect in Initial Draft | Calibrated Correction in Candidate |
| :--- | :--- | :--- | :--- | :--- |
| **P1 (High)** | Q127 | `grammar_topic` | Labeled "Noun form / collocation" when all 4 options are nouns in `-tion`. | Calibrated to "Noun vocabulary / collocation (with great + noun)". |
| **P1 (High)** | Q114 | `grammar_topic` | Labeled as positional word form modifier when all 4 options are adverbs. | Calibrated to "Adverb vocabulary / collocation with verb phrase". |
| **P1 (High)** | Q110 | `part_of_speech` | `cash register` labeled as `noun` instead of canonical `phrase` for multi-word compounds. | Updated POS to `phrase` to align with Q102, Q108, Q127. |
| **P1 (High)** | Q119 | `distractor_analysis` | Superficial semantic dismissal of distractors A, B, D without transitivity rules. | Documented explicit prepositional constraints (`reply to`, transitive verbs without `for`). |
| **P2 (Med)** | Q104 | `pattern` | "her + noun phrase" is an ungeneralizable literal template. | Abstracted to "possessive determiner + many + plural count noun". |
| **P2 (Med)** | Q108 | `pattern` | Pattern "product line" was merely a repetition of the vocabulary lemma. | Abstracted to "compound noun: noun + noun (product line)". |
| **P2 (Med)** | Q105 | `grammar_topic` | Merged outer clause context into topic ("Noun collocation / purpose infinitive"). | Focused directly on blank: "Noun vocabulary / collocation". |
| **P2 (Med)** | Q112 | `sentence_structure` | Omitted fronted attribution "According to CEO Mayu Yamada" and real subject infinitive clause. | Full constituency: Attributive PrepP + Dummy Subject + Predicate VP + Real Subject to-inf clause. |
| **P2 (Med)** | Q124 | `sentence_structure` | Omitted agent prepositional phrase `by residents and visitors`. | Articulated full passive predicate with agent prepositional phrase. |
| **P3 (Low)** | Q119 | `sentence_structure` | Trailing whitespace at end of string in JSON payload. | Cleaned whitespace; structured relative clause constituents. |
| **P3 (Low)** | Q130 | `difficulty` | Marked "easy" despite requiring distinction between two valid adjectives (`diagnostic` vs `diagnosable`). | Calibrated to "medium" with explicit distractor rationale. |
| **P3 (Low)** | Q105 | `difficulty` | Marked "easy" despite semantic noun distinction in IT context. | Calibrated to "medium". |

---

## 5. Detailed Question-by-Question Rubric Audit

Review Rubric Dimensions:
1. `answer_key_and_completed_sentence`
2. `grammar_topic`
3. `sentence_structure`
4. `pattern`
5. `vocabulary_grounding`
6. `part_of_speech`
7. `vietnamese_meaning`
8. `main_explanation`
9. `distractor_analysis`
10. `difficulty`

---

### Question 101

- **Source Question:** "The lecture will take place at 6:00 P.M., _____ which attendees may ask questions."
- **Options:** A: `across`, B: `after`, C: `inside`, D: `among`
- **Authoritative Answer Key:** `B` (`after`)
- **Completed Sentence:** "The lecture will take place at 6:00 P.M., after which attendees may ask questions."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative B; verified temporal relative clause).
2. `grammar_topic`: `PASS` ("Preposition + relative pronoun").
3. `sentence_structure`: `NEEDS_EDIT` (Draft "Main clause, after which + subject + modal verb + base verb" omitted object and clause boundary).
4. `pattern`: `PASS` ("after which + clause").
5. `vocabulary_grounding`: `PASS` (`attendees` grounded in text; candidate adds high-value grounded phrase `take place`).
6. `part_of_speech`: `PASS` (`attendees` = noun, `take place` = phrase).
7. `vietnamese_meaning`: `PASS` ("người tham dự", "diễn ra").
8. `main_explanation`: `PASS` (Clear analysis of relative pronoun referencing 6:00 P.M.).
9. `distractor_analysis`: `PASS` (Distinguishes spatial across/inside/among from temporal after).
10. `difficulty`: `PASS` ("medium" — non-defining relative clause with preposition).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Sentence structure was truncated and lacked the object `questions`.
- *Correction:* `Main clause [The lecture will take place at 6:00 P.M.], + relative clause [after which + S (attendees) + modal verb (may) + V (ask) + O (questions)]`.
- *Remaining Uncertainty:* None on grammar. Human reviewer to decide whether `take place` should be mandatory in the vocabulary list or optional.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 102

- **Source Question:** "The _____ antique shop in Pepper Valley will close down next month."
- **Options:** A: `last`, B: `lasts`, C: `lasted`, D: `lasting`
- **Authoritative Answer Key:** `A` (`last`)
- **Completed Sentence:** "The last antique shop in Pepper Valley will close down next month."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative A; modifier before noun phrase).
2. `grammar_topic`: `PASS` ("Word form / modifier before a noun").
3. `sentence_structure`: `NEEDS_EDIT` (Draft omitted prepositional phrase `in Pepper Valley`).
4. `pattern`: `PASS` ("the last + singular count noun").
5. `vocabulary_grounding`: `PASS` (`last`, `antique shop`, `close down` all grounded in source text/options).
6. `part_of_speech`: `PASS` (`last` = adjective, `antique shop` = phrase, `close down` = phrase).
7. `vietnamese_meaning`: `PASS` ("cuối cùng; còn lại cuối cùng", "cửa hàng đồ cổ").
8. `main_explanation`: `PASS` (Explains adjective role between determiner 'The' and noun phrase).
9. `distractor_analysis`: `PASS` (Distinguishes finite verbs lasts/lasted and participle lasting).
10. `difficulty`: `PASS` ("easy" — canonical determiner + adjective + noun position).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Truncated prepositional phrase in sentence structure.
- *Correction:* `Subject NP [The + modifier (last) + NP (antique shop) + PrepP (in Pepper Valley)] + Predicate VP [will close down + Time Adv (next month)]`.
- *Remaining Uncertainty:* Whether `last` should be tagged strictly as `adjective` or `determiner` in the taxonomy. Both are valid in grammar; `adjective` fits the existing schema.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 104

- **Source Question:** "As a result of _____ many years leading media organizations, Ms. Ayo was selected for the Dowel Journalism Prize."
- **Options:** A: `she`, B: `her`, C: `hers`, D: `herself`
- **Authoritative Answer Key:** `B` (`her`)
- **Completed Sentence:** "As a result of her many years leading media organizations, Ms. Ayo was selected for the Dowel Journalism Prize."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative B; possessive determiner before noun phrase).
2. `grammar_topic`: `PASS` ("Possessive determiner before a noun phrase").
3. `sentence_structure`: `NEEDS_EDIT` (Draft abbreviated main clause as generic formula).
4. `pattern`: `NEEDS_EDIT` (Draft "her + noun phrase" is an ungeneralized literal).
5. `vocabulary_grounding`: `PASS` (`her`, `lead`, `media organization` grounded).
6. `part_of_speech`: `PASS` (`her` = determiner, `lead` = verb, `media organization` = phrase).
7. `vietnamese_meaning`: `PASS` ("của cô ấy", "lãnh đạo/điều hành", "tổ chức truyền thông").
8. `main_explanation`: `PASS` (Explains object of preposition `of` requiring possessive determiner before `many years`).
9. `distractor_analysis`: `PASS` (Contrasts subject pronoun, possessive pronoun, and reflexive pronoun).
10. `difficulty`: `PASS` ("medium" — intervening quantifier 'many years' tests determiner hierarchy).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Pattern `her + noun phrase` failed to articulate the pedagogical rule.
- *Correction:* Update pattern to `possessive determiner + many + plural count noun`. Fully articulate main clause passive predicate `was selected for...`.
- *Remaining Uncertainty:* Pedagogical choice: Should function word `her` be listed in the vocabulary list, or should vocabulary focus solely on lexical content words?
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 105

- **Source Question:** "To stop the _____ of computer viruses, do not open suspicious e-mails."
- **Options:** A: `break`, B: `spread`, C: `balance`, D: `surface`
- **Authoritative Answer Key:** `B` (`spread`)
- **Completed Sentence:** "To stop the spread of computer viruses, do not open suspicious e-mails."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative B; noun collocation `the spread of`).
2. `grammar_topic`: `NEEDS_EDIT` (Draft conflated purpose infinitive context into the blank's topic).
3. `sentence_structure`: `PASS` (Accurately parsed purpose infinitive phrase + imperative clause).
4. `pattern`: `PASS` ("the spread of + noun").
5. `vocabulary_grounding`: `PASS` (`spread`, `computer virus`, `suspicious` grounded).
6. `part_of_speech`: `PASS` (`spread` = noun, `computer virus` = phrase, `suspicious` = adjective).
7. `vietnamese_meaning`: `PASS` ("sự lan truyền/sự lây lan", "vi-rút máy tính", "đáng ngờ").
8. `main_explanation`: `PASS` (Explicitly clarifies that `spread` is a noun here, not a verb).
9. `distractor_analysis`: `PASS` (Explains semantic misfit of break, balance, surface).
10. `difficulty`: `NEEDS_EDIT` (Draft rated "easy"; calibrated to "medium" due to noun vs verb dual-role of `spread`).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Grammar topic included irrelevant clause-level detail ("purpose infinitive"). Difficulty was underestimated.
- *Correction:* Update topic to `Noun vocabulary / collocation`. Calibrate difficulty to `medium`.
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 108

- **Source Question:** "Tarateer Pharmaceuticals is varying its product _____ to include over-the-counter medications."
- **Options:** A: `to line`, B: `lining`, C: `lined`, D: `line`
- **Authoritative Answer Key:** `D` (`line`)
- **Completed Sentence:** "Tarateer Pharmaceuticals is varying its product line to include over-the-counter medications."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative D; compound noun `product line`).
2. `grammar_topic`: `PASS` ("Compound noun / collocation").
3. `sentence_structure`: `NEEDS_EDIT` (Draft lacked specific constituent tagging).
4. `pattern`: `NEEDS_EDIT` (Draft pattern was literally `product line`).
5. `vocabulary_grounding`: `PASS` (`product line`, `over-the-counter`, `vary` grounded).
6. `part_of_speech`: `PASS` (`product line` = phrase, `over-the-counter` = adjective, `vary` = verb).
7. `vietnamese_meaning`: `PASS` ("dòng sản phẩm", "không cần kê đơn", "đa dạng hóa").
8. `main_explanation`: `PASS` (Correctly analyzes compound noun acting as direct object of `vary`).
9. `distractor_analysis`: `PASS` (Analyzes why infinitive, gerund, and past participle fail).
10. `difficulty`: `PASS` ("medium" — distractor verb forms tempt test takers).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Pattern was a bare phrase string; sentence structure was ungrounded.
- *Correction:* Pattern updated to `compound noun: noun + noun (product line)`. Sentence structure explicitly maps `Subject + present-continuous VP + Object NP + Infinitive phrase of purpose`.
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 110

- **Source Question:** "The cash registers at Pirkle Books automatically _____ the remaining inventory of books available."
- **Options:** A: `calculate`, B: `calculator`, C: `calculating`, D: `calculation`
- **Authoritative Answer Key:** `A` (`calculate`)
- **Completed Sentence:** "The cash registers at Pirkle Books automatically calculate the remaining inventory of books available."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative A; finite verb agreeing with plural subject).
2. `grammar_topic`: `PASS` ("Word form / Main verb (subject-verb agreement)").
3. `sentence_structure`: `NEEDS_EDIT` (Draft omitted prepositional phrases `at Pirkle Books` and `of books available`).
4. `pattern`: `PASS` ("plural subject + adverb + base verb + object").
5. `vocabulary_grounding`: `PASS` (`cash register`, `inventory`, `automatically` grounded).
6. `part_of_speech`: `NEEDS_EDIT` (Draft labeled `cash register` as `noun` while all other multi-word compounds are `phrase`).
7. `vietnamese_meaning`: `PASS` ("máy tính tiền", "hàng tồn kho", "tự động").
8. `main_explanation`: `PASS` (Correctly explains finite verb required after plural subject and adverb).
9. `distractor_analysis`: `PASS` (Contrasts concrete noun calculator, participle calculating, abstract noun calculation).
10. `difficulty`: `PASS` ("easy" — canonical verb position).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* `cash register` POS labeled `noun` instead of canonical `phrase`.
- *Correction:* Update POS of `cash register` to `phrase` to maintain strict taxonomy compliance. Elaborate sentence structure constituents.
- *Remaining Uncertainty:* Confirmation by project owner that multi-word compound nouns should always take the tag `phrase` rather than `noun`.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 112

- **Source Question:** "According to CEO Mayu Yamada, it would not be _____ responsible to expand the warehouse at this time."
- **Options:** A: `finance`, B: `financials`, C: `financially`, D: `financing`
- **Authoritative Answer Key:** `C` (`financially`)
- **Completed Sentence:** "According to CEO Mayu Yamada, it would not be financially responsible to expand the warehouse at this time."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative C; adverb modifying predicate adjective).
2. `grammar_topic`: `PASS` ("Adverb modifying an adjective / word form").
3. `sentence_structure`: `NEEDS_EDIT` (Draft omitted fronted attribution and to-infinitive clause details).
4. `pattern`: `NEEDS_EDIT` (Draft pattern had redundant semicolon-separated clauses).
5. `vocabulary_grounding`: `PASS` (`financially`, `responsible`, `expand`, `warehouse` grounded; fixed Qwen's ungrounded `expansion`).
6. `part_of_speech`: `PASS` (`financially` = adverb, `responsible` = adjective, `expand` = verb, `warehouse` = noun).
7. `vietnamese_meaning`: `PASS` ("về mặt tài chính", "hợp lý/có trách nhiệm", "mở rộng", "nhà kho").
8. `main_explanation`: `PASS` (Accurately explains adverbial modification of `responsible`).
9. `distractor_analysis`: `PASS` (Rejects nouns/verbs in modifier slot).
10. `difficulty`: `PASS` ("medium" — adverb modifying predicate adjective in extraposed clause).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Pattern cluttered with semicolons; fronted phrase omitted in structure.
- *Correction:* Pattern streamlined to `be + adverb + adjective (financially responsible)`. Sentence structure maps full dummy-it extraposition construction.
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 114

- **Source Question:** "As part of its marketing campaign, Elegancia Dishware is _____ soliciting feedback from customers."
- **Options:** A: `lightly`, B: `loyally`, C: `actively`, D: `cleanly`
- **Authoritative Answer Key:** `C` (`actively`)
- **Completed Sentence:** "As part of its marketing campaign, Elegancia Dishware is actively soliciting feedback from customers."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative C; adverb collocation with progressive verb).
2. `grammar_topic`: `NEEDS_EDIT` (Draft labeled positional environment "Adverb modifying a present-progressive verb phrase", obscuring that all 4 options are adverbs).
3. `sentence_structure`: `NEEDS_EDIT` (Draft constituents lacked precise bracketed mapping).
4. `pattern`: `PASS` ("be + actively + V-ing").
5. `vocabulary_grounding`: `PASS` (`actively`, `solicit feedback`, `marketing campaign` grounded).
6. `part_of_speech`: `PASS` (`actively` = adverb, `solicit feedback` = phrase, `marketing campaign` = phrase).
7. `vietnamese_meaning`: `PASS` ("tích cực/chủ động", "thu thập ý kiến phản hồi", "chiến dịch tiếp thị").
8. `main_explanation`: `PASS` (Clarifies semantic collocation in a marketing context).
9. `distractor_analysis`: `PASS` (Analyzes subtle lexical mismatch of lightly, loyally, cleanly).
10. `difficulty`: `PASS` ("medium" — adverb semantic selection).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Grammar topic described the slot rather than the tested skill.
- *Correction:* Calibrate `grammar_topic` to `Adverb vocabulary / collocation with verb phrase`.
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 119

- **Source Question:** "The newspaper article describes ways job seekers can _____ for having little workplace experience."
- **Options:** A: `reply`, B: `capture`, C: `compensate`, D: `accumulate`
- **Authoritative Answer Key:** `C` (`compensate`)
- **Completed Sentence:** "The newspaper article describes ways job seekers can compensate for having little workplace experience."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative C; phrasal verb/collocation `compensate for`).
2. `grammar_topic`: `PASS` ("Verb + preposition collocation").
3. `sentence_structure`: `NEEDS_EDIT` (Draft contained trailing whitespace and lacked contact clause breakdown).
4. `pattern`: `PASS` ("compensate for + noun / V-ing").
5. `vocabulary_grounding`: `PASS` (`compensate for`, `workplace experience`, `job seeker` grounded).
6. `part_of_speech`: `PASS` (All phrases tagged as `phrase`).
7. `vietnamese_meaning`: `PASS` ("bù đắp cho/bồi hoàn cho", "kinh nghiệm làm việc", "người tìm việc").
8. `main_explanation`: `PASS` (Focuses on `compensate for` followed by gerund phrase).
9. `distractor_analysis`: `NEEDS_EDIT` (Draft offered vague "không diễn đạt ý bù đắp" without transitivity rules).
10. `difficulty`: `PASS` ("medium" — phrasal preposition complementation).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Trailing whitespace in sentence structure. Distractor analysis failed to state that `reply` requires `to`, while `capture` and `accumulate` are direct transitive verbs.
- *Correction:* Strip whitespace; articulate full relative clause. Update distractors: A requires `reply to`, B is a direct transitive verb (`capture sth`), D is a direct transitive verb (`accumulate sth`).
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 124

- **Source Question:** "The City of Doyle's new downtown parking _____ have been met with opposition by residents and visitors."
- **Options:** A: `restricts`, B: `restricted`, C: `restrictions`, D: `restricting`
- **Authoritative Answer Key:** `C` (`restrictions`)
- **Completed Sentence:** "The City of Doyle's new downtown parking restrictions have been met with opposition by residents and visitors."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative C; plural noun head agreeing with `have`).
2. `grammar_topic`: `PASS` ("Word form / plural noun subject").
3. `sentence_structure`: `NEEDS_EDIT` (Draft omitted agent phrase `by residents and visitors`).
4. `pattern`: `NEEDS_EDIT` (Draft pattern was cluttered with semicolons).
5. `vocabulary_grounding`: `PASS` (`restriction`, `opposition`, `resident` grounded).
6. `part_of_speech`: `PASS` (`restriction` = noun, `opposition` = noun, `resident` = noun).
7. `vietnamese_meaning`: `PASS` ("quy định hạn chế", "sự phản đối", "cư dân").
8. `main_explanation`: `PASS` (Explains compound noun head agreeing with plural passive auxiliary `have`).
9. `distractor_analysis`: `PASS` (Contrasts singular verb restricts, participle restricted, gerund restricting).
10. `difficulty`: `PASS` ("medium" — compound subject agreement with distal predicate).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Omitted agent prepositional phrase; semicolons in pattern.
- *Correction:* Add `Agent PrepP [by residents and visitors]`. Clean pattern to `parking restrictions; plural subject + have + past participle`.
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 127

- **Source Question:** "As chief analytics officer, Mr. Ko has worked at Lochstan Ltd. with great _____ for more than twenty years."
- **Options:** A: `deduction`, B: `duplication`, C: `declaration`, D: `dedication`
- **Authoritative Answer Key:** `D` (`dedication`)
- **Completed Sentence:** "As chief analytics officer, Mr. Ko has worked at Lochstan Ltd. with great dedication for more than twenty years."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative D; noun collocation `with great dedication`).
2. `grammar_topic`: `NEEDS_EDIT` (Draft mislabeled as "Noun form / collocation" when all 4 options are nouns in `-tion`).
3. `sentence_structure`: `NEEDS_EDIT` (Draft omitted appositive role clause `As chief analytics officer` and adjuncts).
4. `pattern`: `NEEDS_EDIT` (Draft pattern was repetitive).
5. `vocabulary_grounding`: `PASS` (`dedication`, `chief analytics officer`, `analytics` grounded).
6. `part_of_speech`: `PASS` (`dedication` = noun, `chief analytics officer` = phrase, `analytics` = noun).
7. `vietnamese_meaning`: `PASS` ("sự tận tụy/sự cống hiến", "giám đốc phân tích", "phân tích dữ liệu").
8. `main_explanation`: `PASS` (Explains idiom/collocation `with great dedication`).
9. `distractor_analysis`: `PASS` (Eliminated Qwen's extra key `Explanation` and provides crisp definitions).
10. `difficulty`: `PASS` ("medium" — abstract noun vocabulary in professional context).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Incorrect topic ("Noun form"). Omitted clause constituents in structure.
- *Correction:* Update topic to `Noun vocabulary / collocation (with great + noun)`. Expand sentence structure to include role clause, place, manner, and duration adjuncts.
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

### Question 130

- **Source Question:** "For a $95 _____ fee, our mechanics will determine what repairs are needed."
- **Options:** A: `diagnosed`, B: `diagnostic`, C: `diagnosable`, D: `diagnose`
- **Authoritative Answer Key:** `B` (`diagnostic`)
- **Completed Sentence:** "For a $95 diagnostic fee, our mechanics will determine what repairs are needed."

#### Dimension-by-Dimension Rubric
1. Answer Key & Completed Sentence: `PASS` (Authoritative B; adjective modifying noun `diagnostic fee`).
2. `grammar_topic`: `PASS` ("Adjective modifying a noun / word form").
3. `sentence_structure`: `NEEDS_EDIT` (Draft abbreviated main clause as generic formula).
4. `pattern`: `NEEDS_EDIT` (Draft pattern was repetitive).
5. `vocabulary_grounding`: `PASS` (`diagnostic`, `fee`, `mechanic`, `repair` grounded).
6. `part_of_speech`: `PASS` (`diagnostic` = adjective, `fee` = noun, `mechanic` = noun, `repair` = noun).
7. `vietnamese_meaning`: `PASS` ("thuộc chẩn đoán/kiểm tra", "phí dịch vụ", "thợ máy", "sửa chữa").
8. `main_explanation`: `PASS` (Clearly distinguishes `diagnostic` from `diagnosable`).
9. `distractor_analysis`: `PASS` (Explains why `diagnosable` is unsuitable for commercial fees).
10. `difficulty`: `NEEDS_EDIT` (Draft rated "easy"; calibrated to "medium" due to two competing adjective forms).

#### Defects in Initial Draft & Proposed Corrections
- *Defect:* Truncated sentence structure; undercalibrated difficulty.
- *Correction:* Expand structure: `PrepP [For a $95 + Adj + N], + Main clause [S + future VP + Object noun clause]`. Calibrate difficulty to `medium`.
- *Remaining Uncertainty:* None.
- **Review Status:** `DRAFT_NEEDS_HUMAN_REVIEW`

---

## 6. Audit Verdict & Deliverable Links

- **Candidate JSON Artifact:** [`reports/gold_set_review/part5_gold_set_candidate_2026-10-12.json`](file:///d:/project/Toeic_Agent/reports/gold_set_review/part5_gold_set_candidate_2026-10-12.json)
- **Manual Checklist Artifact:** [`reports/gold_set_review/part5_gold_set_manual_checklist.md`](file:///d:/project/Toeic_Agent/reports/gold_set_review/part5_gold_set_manual_checklist.md)
- **Approval Status:** All 12 items remain in `DRAFT_NEEDS_HUMAN_REVIEW`. Do not import or treat as validated CI gold data until human verification is completed via the checklist.
