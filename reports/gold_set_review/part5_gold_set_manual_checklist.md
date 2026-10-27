# TOEIC Part 5 Enrichment Gold Set — Manual Review & Approval Checklist

**Document Date:** 2026-10-12  
**Target Reference File:** [`reports/gold_set_review/part5_gold_set_candidate_2026-10-12.json`](file:///d:/project/Toeic_Agent/reports/gold_set_review/part5_gold_set_candidate_2026-10-12.json)  
**Detailed Audit Report:** [`reports/gold_set_review/part5_gold_set_review_2026-10-12.md`](file:///d:/project/Toeic_Agent/reports/gold_set_review/part5_gold_set_review_2026-10-12.md)  
**Target Items:** Q101, Q102, Q104, Q105, Q108, Q110, Q112, Q114, Q119, Q124, Q127, Q130 (12 items)  

> [!IMPORTANT]
> **This candidate set is strictly unapproved (`DRAFT_NEEDS_HUMAN_REVIEW`).**  
> Automated validation (Pydantic schema check or deterministic validator pass) does NOT constitute pedagogical correctness. This set MUST be manually reviewed, calibrated, and signed off by a qualified English teacher or the project owner before it can be used as a CI regression test fixture, model benchmark leaderboard, or database ground truth.

---

## 1. Field Verification Rubric & Acceptance Standards

For each question, the reviewer must verify the following 10 dimensions against authoritative English grammar principles:

| Dimension | Review Criterion | Acceptance Standard |
| :--- | :--- | :--- |
| **1. Answer Key & Sentence** | Is the correct answer independently verified against authoritative test materials? | Exactly matches source database; completed sentence is grammatically flawless. |
| **2. Grammar Topic** | Is the topic specific, standard, and directly focused on the blank? | No broad or misleading labels (e.g., must NOT label a pure vocabulary question as "word form"). |
| **3. Sentence Structure** | Does it accurately depict the complete sentence's constituents? | Accurately identifies Subject, Predicate, clauses, and key adjuncts without irrelevant formulas. |
| **4. Pattern** | Is the pattern reusable, instructive, and properly abstracted? | Teaches a generalizable rule (e.g., `the spread of + noun`), not just a literal echo of the question. |
| **5. Vocabulary Grounding** | Does every word/phrase exist in the question or options? | Strictly grounded under project lemmatization rules; no hallucinated related words (e.g. no `expansion`). |
| **6. Part of Speech** | Does the POS tag belong to the approved taxonomy? | Belongs to `VALID_PARTS_OF_SPEECH`; multi-word expressions consistently tagged as `phrase`. |
| **7. Vietnamese Meaning** | Is the translation natural, accurate, and context-appropriate? | Preserves professional business English nuance; natural Vietnamese phrasing with correct diacritics. |
| **8. Main Explanation** | Does it explain *why* the correct answer fits grammatically/semantically? | Explicit linguistic reasoning; no invented tenses or false grammatical rules. |
| **9. Distractor Analysis** | Are all distractors (A, B, C, D) analyzed with concrete linguistic reasons? | Explains transitivity, missing auxiliaries, or semantic mismatch; never merely states "không phù hợp". |
| **10. Difficulty** | Is the difficulty rating calibrated with justifiable pedagogical rationale? | Justifiable rating (`easy`, `medium`, `hard`) based on distractor plausibility and subtlety. |

---

## 2. Item-by-Item Review & Sign-Off Matrix

Review each question by checking off the 10 dimensions below:

### Question 101 (`after which`)
- [ ] 1. Answer Key: `B` (`after`) verified in source
- [ ] 2. Grammar Topic: `Preposition + relative pronoun`
- [ ] 3. Sentence Structure: Full clause breakdown verified
- [ ] 4. Pattern: `after which + clause`
- [ ] 5. Vocabulary Grounding: `attendees`, `take place`
- [ ] 6. Part of Speech: `attendees` (noun), `take place` (phrase)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains `which` referencing 6:00 P.M.
- [ ] 9. Distractors: A, C, D contrast spatial vs temporal meaning
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 102 (`the last antique shop`)
- [ ] 1. Answer Key: `A` (`last`) verified in source
- [ ] 2. Grammar Topic: `Word form / modifier before a noun`
- [ ] 3. Sentence Structure: Includes `in Pepper Valley`
- [ ] 4. Pattern: `the last + singular count noun`
- [ ] 5. Vocabulary Grounding: `last`, `antique shop`, `close down`
- [ ] 6. Part of Speech: `last` (adjective), `antique shop` (phrase)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains adjective modifying shop
- [ ] 9. Distractors: B, C, D verb forms rejected
- [ ] 10. Difficulty: `easy` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 104 (`her many years`)
- [ ] 1. Answer Key: `B` (`her`) verified in source
- [ ] 2. Grammar Topic: `Possessive determiner before a noun phrase`
- [ ] 3. Sentence Structure: Prepositional object + main clause passive
- [ ] 4. Pattern: `possessive determiner + many + plural count noun`
- [ ] 5. Vocabulary Grounding: `her`, `lead`, `media organization`
- [ ] 6. Part of Speech: `her` (determiner), `lead` (verb), `media organization` (phrase)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains possessive determiner before `many years`
- [ ] 9. Distractors: Contrasts she, hers, herself
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 105 (`the spread of`)
- [ ] 1. Answer Key: `B` (`spread`) verified in source
- [ ] 2. Grammar Topic: `Noun vocabulary / collocation`
- [ ] 3. Sentence Structure: Purpose infinitive + imperative clause
- [ ] 4. Pattern: `the spread of + noun`
- [ ] 5. Vocabulary Grounding: `spread`, `computer virus`, `suspicious`
- [ ] 6. Part of Speech: `spread` (noun), `computer virus` (phrase)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Emphasizes `spread` as a noun
- [ ] 9. Distractors: Explains break, balance, surface semantic mismatch
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 108 (`product line`)
- [ ] 1. Answer Key: `D` (`line`) verified in source
- [ ] 2. Grammar Topic: `Compound noun / collocation`
- [ ] 3. Sentence Structure: Full progressive predicate + infinitive
- [ ] 4. Pattern: `compound noun: noun + noun (product line)`
- [ ] 5. Vocabulary Grounding: `product line`, `over-the-counter`, `vary`
- [ ] 6. Part of Speech: `product line` (phrase), `over-the-counter` (adjective)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains compound noun object of `vary`
- [ ] 9. Distractors: Explains why to line, lining, lined fail
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 110 (`automatically calculate`)
- [ ] 1. Answer Key: `A` (`calculate`) verified in source
- [ ] 2. Grammar Topic: `Word form / Main verb (subject-verb agreement)`
- [ ] 3. Sentence Structure: Plural subject NP + adverb + main verb + object
- [ ] 4. Pattern: `plural subject + adverb + base verb + object`
- [ ] 5. Vocabulary Grounding: `cash register`, `inventory`, `automatically`
- [ ] 6. Part of Speech: `cash register` (phrase), `inventory` (noun)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains base verb agreeing with plural subject
- [ ] 9. Distractors: Contrasts calculator, calculating, calculation
- [ ] 10. Difficulty: `easy` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 112 (`financially responsible`)
- [ ] 1. Answer Key: `C` (`financially`) verified in source
- [ ] 2. Grammar Topic: `Adverb modifying an adjective / word form`
- [ ] 3. Sentence Structure: Attribution + dummy it + predicate adjective + real subject
- [ ] 4. Pattern: `be + adverb + adjective (financially responsible)`
- [ ] 5. Vocabulary Grounding: `financially`, `responsible`, `expand`, `warehouse`
- [ ] 6. Part of Speech: `financially` (adverb), `responsible` (adjective)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains adverb modifying `responsible`
- [ ] 9. Distractors: Rejects noun/verb forms finance, financials, financing
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 114 (`actively soliciting`)
- [ ] 1. Answer Key: `C` (`actively`) verified in source
- [ ] 2. Grammar Topic: `Adverb vocabulary / collocation with verb phrase`
- [ ] 3. Sentence Structure: PrepP + S + progressive VP + O
- [ ] 4. Pattern: `be + actively + V-ing`
- [ ] 5. Vocabulary Grounding: `actively`, `solicit feedback`, `marketing campaign`
- [ ] 6. Part of Speech: `actively` (adverb), `solicit feedback` (phrase)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains semantic adverb choice in marketing context
- [ ] 9. Distractors: Explains mismatch of lightly, loyally, cleanly
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 119 (`compensate for`)
- [ ] 1. Answer Key: `C` (`compensate`) verified in source
- [ ] 2. Grammar Topic: `Verb + preposition collocation`
- [ ] 3. Sentence Structure: S + V + O (ways + contact relative clause)
- [ ] 4. Pattern: `compensate for + noun / V-ing`
- [ ] 5. Vocabulary Grounding: `compensate for`, `workplace experience`, `job seeker`
- [ ] 6. Part of Speech: All multi-word items tagged `phrase`
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains `compensate for` + gerund phrase
- [ ] 9. Distractors: Explains `reply to`, direct transitive `capture`/`accumulate`
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 124 (`parking restrictions`)
- [ ] 1. Answer Key: `C` (`restrictions`) verified in source
- [ ] 2. Grammar Topic: `Word form / plural noun subject`
- [ ] 3. Sentence Structure: Plural subject NP + passive VP + agent PrepP
- [ ] 4. Pattern: `parking restrictions; plural subject + have + past participle`
- [ ] 5. Vocabulary Grounding: `restriction`, `opposition`, `resident`
- [ ] 6. Part of Speech: `restriction` (noun), `opposition` (noun)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains head noun agreeing with plural verb `have`
- [ ] 9. Distractors: Rejects restricts, restricted, restricting
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 127 (`with great dedication`)
- [ ] 1. Answer Key: `D` (`dedication`) verified in source
- [ ] 2. Grammar Topic: `Noun vocabulary / collocation (with great + noun)`
- [ ] 3. Sentence Structure: Role PrepP + S + present-perfect VP + place/manner/duration
- [ ] 4. Pattern: `with great + abstract noun (with great dedication)`
- [ ] 5. Vocabulary Grounding: `dedication`, `chief analytics officer`, `analytics`
- [ ] 6. Part of Speech: `dedication` (noun), `chief analytics officer` (phrase)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains professional dedication collocation
- [ ] 9. Distractors: Contrasts deduction, duplication, declaration
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

### Question 130 (`diagnostic fee`)
- [ ] 1. Answer Key: `B` (`diagnostic`) verified in source
- [ ] 2. Grammar Topic: `Adjective modifying a noun / word form`
- [ ] 3. Sentence Structure: Fee PrepP + main clause + noun clause object
- [ ] 4. Pattern: `adjective + fee (diagnostic fee)`
- [ ] 5. Vocabulary Grounding: `diagnostic`, `fee`, `mechanic`, `repair`
- [ ] 6. Part of Speech: `diagnostic` (adjective), `fee` (noun), `mechanic` (noun)
- [ ] 7. Vietnamese Translation: Natural and accurate
- [ ] 8. Main Explanation: Explains why `diagnostic` fits and `diagnosable` fails
- [ ] 9. Distractors: Distinguishes diagnose (verb), diagnosed (participle), diagnosable (adj)
- [ ] 10. Difficulty: `medium` agreed
- **Decision:** [ ] APPROVED / [ ] NEEDS REVISION  
*Reviewer Notes:* __________________________________________________

---

## 3. Specific Design Questions for Project Owner / Reviewer

The reviewer should review and resolve these four project-level conventions:

1. **POS Classification for Compound Nouns:**
   - *Current Convention:* Multi-word nouns (e.g., `product line`, `antique shop`, `cash register`) are designated as `phrase` in accordance with `app/schemas/enrichment.py` line 7-8.
   - *Decision:* Confirm whether `phrase` is preferred over `noun` for all multi-word nominal expressions.

2. **Function Words in Vocabulary Glossaries:**
   - *Case:* In Q104, `her` is included as a vocabulary item tagged `determiner`.
   - *Decision:* Confirm whether high-frequency grammatical function words (determiners, pronouns) should be included in vocabulary lists, or if vocabulary items should be restricted to lexical content words (nouns, verbs, adjectives).

3. **Difficulty Calibration Scale:**
   - *Case:* Questions testing subtle adjective distinctions (Q130 `diagnostic` vs `diagnosable`) or IT collocations (Q105 `spread of viruses`) were re-calibrated from `easy` to `medium`.
   - *Decision:* Confirm acceptance of the calibrated 3-tier difficulty distribution (`easy`: 2 items, `medium`: 10 items, `hard`: 0 items in this seed set).

4. **Approval Transition Sign-Off:**
   - Once all 12 questions are approved, update `review_status` in `part5_gold_set_candidate_2026-10-12.json` to `APPROVED` and commit the file to `tests/fixtures/gold_sets/part5_gold_seed_12.json`.

---

**Reviewer Name:** __________________________________  
**Review Date:** ____________________________________  
**Signature / Decision:** [ ] FULLY APPROVED  [ ] CONDITIONALLY APPROVED  [ ] REJECTED  
