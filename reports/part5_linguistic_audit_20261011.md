# Linguistic Quality Audit: TOEIC Part 5 Enrichment Baseline

**Audit Date:** 2026-10-11  
**Project:** `D:\project\Toeic_Agent`  
**Primary Benchmark Report:** `reports/part5_batch_qwen2.5_3b_20261011_142856.json`  
**Historical Comparison Report:** `reports/part5_batch_qwen2.5_3b_20261010_161846.json`  
**Model Under Audit:** `qwen2.5:3b` (via local Ollama)  
**Dataset Scope:** ETS2026 Part 5 (Q101–Q130, 30 questions)  
**Authoritative Answers:** Q107 = C (`and`) and Q109 = A (`seeks`) confirmed by user against original answer key; remaining 28 answers are internally consistent across workbook and database but unconfirmed by independent external primary source.

---

## 1. Executive Summary

This audit evaluates the actual linguistic and pedagogical quality of the 30-question Part 5 enrichment baseline produced by `qwen2.5:3b`. A comprehensive rubric covering correct-answer reasoning, grammar topic accuracy, sentence structure/pattern fidelity, vocabulary grounding/translation, explanation quality, and distractor analysis was applied to every record.

### Baseline Status Breakdown:
* **Total Question Records Audited:** 30
* **Pipeline Pass Count (`PASS_QUALITY_VALIDATED`):** 25 (83.3%)
* **Deterministic Quality Rejections (`REJECTED_QUALITY`):** 3 (10.0%) — Q109, Q112, Q113
* **Pydantic Schema Validation Failures (`FAIL_SCHEMA_VALIDATION`):** 1 (3.3%) — Q118
* **JSON Decode Failures (`FAIL_JSON_DECODE`):** 1 (3.3%) — Q127

### Key Audit Finding:
While the pipeline reports a **83.3% pass rate** (25/30), in-depth linguistic review reveals that **23 out of the 25 passing questions (92.0%) contain substantial linguistic defects** (15 HIGH severity, 8 MEDIUM severity). Only **2 questions (Q106, Q119)** exhibit sound linguistic and pedagogical quality with only minor, low-severity stylistic imperfections.

Across all 30 questions:
* **HIGH Severity Issues:** 20 questions (66.7%) — teach false grammar rules, contain severe mistranslations, or present contradictory reasoning.
* **MEDIUM Severity Issues:** 8 questions (26.7%) — materially weak metadata or prompt contamination that degrades learning value.
* **LOW Severity Issues:** 2 questions (6.7%) — minor formula clutter or slight labeling imprecision with sound pedagogical substance.

> [!WARNING]
> A status of `PASS_QUALITY_VALIDATED` in the current pipeline does **not** signify linguistic correctness. The deterministic validator currently only enforces token grounding of vocabulary words, non-empty distractor fields, and the absence of explicit contradiction keywords in the correct-answer distractor field. It cannot detect false grammatical assertions, prompt leakage, mistranslations, or foreign-language pollution.

---

## 2. Per-Question Audit Table

| Question | Pipeline Status | Answer Reasoning | Grammar Topic | Structure & Pattern | Vocab & POS | Explanation Quality | Distractor Analysis | Highest Severity | Key Observations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Q101** | `PASS_QUALITY_VALIDATED` | PARTIAL | CORRECT | PARTIAL | INCORRECT | PARTIAL | PARTIAL | **HIGH** | Vocab severely mistranslated: *which* -> *nhớ*, *questions* -> *đề nghị*. Claims *after* takes position of prep *at*. |
| **Q102** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | CORRECT | INCORRECT | INCORRECT | **HIGH** | Teaches false grammar: claims adjective *last* is a preposition in an *[at which]* clause. Prompt leakage. |
| **Q103** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | INCORRECT | INCORRECT | PARTIAL | **HIGH** | Chinese characters in POS (`名词`, `形容词`). Claims *update* is a gerund subject. Topic is compound noun. |
| **Q104** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | CORRECT | INCORRECT | PARTIAL | **HIGH** | Prompt leakage: hallucinates relative clause connecting pronoun *her* via *which*. |
| **Q105** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | INCORRECT | INCORRECT | INCORRECT | **HIGH** | Bizarre mistranslation: *spread* -> *nóng ròng rã*. Fabricates *Verb + of + Infinitive* rule for noun slot. |
| **Q106** | `PASS_QUALITY_VALIDATED` | CORRECT | CORRECT | PARTIAL | CORRECT | CORRECT | CORRECT | **LOW** | Sound pedagogical analysis: accurately explains adverb of manner *carefully* modifying *considered*. |
| **Q107** | `PASS_QUALITY_VALIDATED` | PARTIAL | CORRECT | INCORRECT | CORRECT | PARTIAL | CORRECT | **HIGH** | Authoritative answer confirmed C (*and*). Explanation contaminated by prompt leakage (*Preposition + which + clause*). |
| **Q108** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | CORRECT | INCORRECT | PARTIAL | **HIGH** | Fabricates relative clause for compound noun *product line*, claiming *over-the-counter* is preposition. |
| **Q109** | `REJECTED_QUALITY` | INCORRECT | INCORRECT | INCORRECT | INCORRECT | INCORRECT | INCORRECT | **HIGH** | Authoritative answer confirmed A (*seeks*). Rejected for ungrounded *which*. Claims *seeks* is a gerund (*thúy* typo). |
| **Q110** | `PASS_QUALITY_VALIDATED` | PARTIAL | INCORRECT | INCORRECT | INCORRECT | PARTIAL | PARTIAL | **HIGH** | Chinese character in POS (`名词`). Prompt leakage. Garbled pseudo-jargon in distractors (*đồ lý*, *động quy*). |
| **Q111** | `PASS_QUALITY_VALIDATED` | CORRECT | CORRECT | INCORRECT | PARTIAL | CORRECT | CORRECT | **MEDIUM** | Explains adverb *precisely*. Prompt leakage in structure/pattern. *minerals* left untranslated. |
| **Q112** | `REJECTED_QUALITY` | PARTIAL | CORRECT | INCORRECT | INCORRECT | PARTIAL | PARTIAL | **HIGH** | Rejected for ungrounded *expanding*. Portuguese word *responsável* injected into Vietnamese explanation text. |
| **Q113** | `REJECTED_QUALITY` | INCORRECT | INCORRECT | INCORRECT | INCORRECT | PARTIAL | INCORRECT | **HIGH** | Rejected for direct contradiction on answer A (*Đáp án này sai vì nó đúng...*). Topic wrongly labeled Adverb. |
| **Q114** | `PASS_QUALITY_VALIDATED` | CORRECT | PARTIAL | INCORRECT | PARTIAL | CORRECT | CORRECT | **MEDIUM** | Solid semantic reasoning. Prompt leakage. 4 out of 4 vocabulary items left untranslated in English. |
| **Q115** | `PASS_QUALITY_VALIDATED` | CORRECT | CORRECT | PARTIAL | CORRECT | PARTIAL | PARTIAL | **MEDIUM** | Meaning of *absorb* valid, but structure contradicts pattern (*S + V + to + V-ing* vs *Verb + to + Infinitive*). |
| **Q116** | `PASS_QUALITY_VALIDATED` | PARTIAL | PARTIAL | PARTIAL | CORRECT | PARTIAL | INCORRECT | **HIGH** | Chinese characters in explanation (`名词化`). Distractor D falsely asserts *productivity* is an adjective. |
| **Q117** | `PASS_QUALITY_VALIDATED` | CORRECT | INCORRECT | INCORRECT | PARTIAL | CORRECT | PARTIAL | **MEDIUM** | Valid explanation of *role in obtaining*. Prompt leakage in topic/structure. *obtaining* mistranslated as *khám phá*. |
| **Q118** | `FAIL_SCHEMA_VALIDATION` | NOT_ASSESSABLE | INCORRECT | INCORRECT | PARTIAL | INCORRECT | INCORRECT | **HIGH** | Pydantic schema failure: missing key B, duplicate key A. Raw response shows conditional clause confusion. |
| **Q119** | `PASS_QUALITY_VALIDATED` | CORRECT | PARTIAL | PARTIAL | CORRECT | CORRECT | CORRECT | **LOW** | High pedagogical value: clear explanation of *compensate for* and solid distractor analysis. |
| **Q120** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | CORRECT | INCORRECT | PARTIAL | **HIGH** | Self-contradictory reasoning: claims B cannot be right, then says B is right. Hallucinates quotation marks. |
| **Q121** | `PASS_QUALITY_VALIDATED` | INCORRECT | PARTIAL | INCORRECT | INCORRECT | INCORRECT | PARTIAL | **HIGH** | Chinese grammar token in POS (`n谓语`). Mistranslates *despite* as *thay vì* (instead of). Pattern invents *Despite + Clause*. |
| **Q122** | `PASS_QUALITY_VALIDATED` | PARTIAL | CORRECT | INCORRECT | CORRECT | PARTIAL | PARTIAL | **MEDIUM** | Prompt leakage in structure. Bizarrely calls *sell* an *động từ lóng* (slang verb). Distractors call participles *trạng thái*. |
| **Q123** | `PASS_QUALITY_VALIDATED` | CORRECT | INCORRECT | INCORRECT | CORRECT | CORRECT | CORRECT | **MEDIUM** | Clear semantic explanation of *cooperative agreement*. Topic and structure contaminated by prompt leakage. |
| **Q124** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | PARTIAL | INCORRECT | INCORRECT | **HIGH** | Teaches false grammar: repeatedly asserts plural noun *restrictions* is a V-ing verb / gerund. Invented jargon. |
| **Q125** | `PASS_QUALITY_VALIDATED` | CORRECT | CORRECT | INCORRECT | CORRECT | CORRECT | PARTIAL | **MEDIUM** | Correct adverb reasoning for *diligently*. Sentence structure contaminated by prompt leakage. |
| **Q126** | `PASS_QUALITY_VALIDATED` | PARTIAL | INCORRECT | INCORRECT | CORRECT | INCORRECT | PARTIAL | **HIGH** | Hallucinates that noun *assurance* is followed by *which* to form a relative clause. Prompt leakage. |
| **Q127** | `FAIL_JSON_DECODE` | NOT_ASSESSABLE | PARTIAL | INCORRECT | PARTIAL | INCORRECT | NOT_ASSESSABLE | **HIGH** | JSON decode failure: syntax error in distractor delimiters. Raw text claims noun *dedication* is a verb. |
| **Q128** | `PASS_QUALITY_VALIDATED` | CORRECT | PARTIAL | INCORRECT | INCORRECT | CORRECT | PARTIAL | **HIGH** | Explanation valid, but vocabulary severely corrupted: *serves* -> *chose*, *only* -> *only*, *weekdays* -> *giờ làm việc*. |
| **Q129** | `PASS_QUALITY_VALIDATED` | CORRECT | INCORRECT | INCORRECT | INCORRECT | CORRECT | CORRECT | **MEDIUM** | Good semantic distinction for *commercial supplier*. Prompt leakage in topic. Non-standard POS (`n-Noun`, `V3`). |
| **Q130** | `PASS_QUALITY_VALIDATED` | INCORRECT | INCORRECT | INCORRECT | INCORRECT | INCORRECT | INCORRECT | **HIGH** | Chinese characters in POS (`动词`, `形容词`). Falsely asserts *diagnostic* takes *at* in *at [Prep] + which + S + V*. |

---

## 3. Defect Frequency Table

Issues are grouped into distinct defect categories across all 30 audited records. Each affected question is counted exactly once per category.

| Defect Category | Questions Affected | Percentage (of 30) | Exemplar Questions |
| :--- | :---: | :---: | :--- |
| **Incorrect sentence structure** | 26 | **86.7%** | Q102, Q103, Q104, Q105, Q108, Q114, Q121, Q124, Q126, Q130 |
| **Incorrect pattern** | 25 | **83.3%** | Q101, Q102, Q104, Q105, Q107, Q108, Q110, Q113, Q120, Q121 |
| **Prompt / example leakage** | 23 | **76.7%** | Q101, Q102, Q103, Q104, Q107, Q108, Q109, Q110, Q117, Q123, Q126, Q130 |
| **Incorrect grammar topic** | 16 | **53.3%** | Q102, Q103, Q104, Q105, Q108, Q109, Q110, Q113, Q120, Q124, Q126, Q130 |
| **Weak or incorrect distractor analysis** | 15 | **50.0%** | Q102, Q103, Q105, Q108, Q109, Q110, Q113, Q116, Q120, Q124, Q130 |
| **Incorrect answer reasoning** | 14 | **46.7%** | Q102, Q103, Q104, Q105, Q108, Q109, Q113, Q120, Q121, Q124, Q126, Q130 |
| **Incorrect POS (Part of Speech)** | 13 | **43.3%** | Q102, Q103, Q105, Q109, Q110, Q113, Q116, Q121, Q124, Q129, Q130 |
| **Incorrect vocabulary meaning / translation** | 9 | **30.0%** | Q101, Q103, Q105, Q111, Q114, Q117, Q120, Q121, Q128 |
| **Other (Multilingual / Chinese / Portuguese / Ungrounded)** | 7 | **23.3%** | Q103, Q109, Q110, Q112, Q116, Q121, Q130 |
| **JSON / schema failure** | 2 | **6.7%** | Q118, Q127 |

---

## 4. Concrete Examples of Problematic Output

### Example 1: Severe Prompt Leakage & False Grammar Rule (Q102)
* **Question Text:** `The _____ antique shop in Pepper Valley will close down next month.`
* **Options:** `A. last | B. lasts | C. lasted | D. lasting` (Correct: `A`)
* **Problematic Output:**
  ```json
  "grammar_topic": "Preposition + Relative Pronoun",
  "sentence_structure": "S + V + [Prep] + which + S + V",
  "pattern": "at [Prep] + which + S + V",
  "explanation": "Đáp án A (last) chính xác vì nó đóng vai trò làm prep trong cấu trúc [at which] và xác định một tiệm đồ cổ..."
  ```
* **Why it is wrong:** The sentence is a simple clause requiring an adjective modifier (*last*) before the noun phrase *antique shop*. There is no preposition, no relative pronoun, and no relative clause. The model copied the few-shot examples from the prompt (`"Preposition + Relative Pronoun"`, `"S + V + at [Time], [Prep] + which + S + V"`) and fabricated an absurd explanation claiming *last* is a preposition.
* **Recommended Correction Direction:** Strip the few-shot examples from `SYSTEM_PROMPT`. Teach the model to identify the head noun and recognize pre-nominal adjective modification: `The + [Adjective] + Noun Phrase + will + Verb`.

### Example 2: Inverted Grammatical Category & Pseudo-Grammar (Q124)
* **Question Text:** `The City of Doyle's new downtown parking _____ have been met with opposition by residents and visitors.`
* **Options:** `A. restricts | B. restricted | C. restrictions | D. restricting` (Correct: `C`)
* **Problematic Output:**
  ```json
  "grammar_topic": "Verb in Gerund Form",
  "explanation": "Đáp án C là đáp án chính xác bởi vì nó sử dụng từ động từ đang được (V-ing) trong cấu trúc preposition + V-ing... 'Restrictions' là từ đồng thời cũng là từ đang được (V-ing)...",
  "distractor_analysis": {
    "A": "Đáp án A sai vì nó sử dụng bất động词 restrict (đóng vai một động từ)..."
  }
  ```
* **Why it is wrong:** *restrictions* is a plural count noun functioning as the subject head of the plural finite verb *have been met*. The model misclassifies it as a gerund/V-ing form, fabricates a non-existent prepositional structure, and generates bizarre pseudo-grammatical jargon mixed with Chinese characters (`bất động词`).
* **Recommended Correction Direction:** Constrain POS classifications to a strict English taxonomy (e.g. `noun`, `verb`, `adjective`, `adverb`, `preposition`, `conjunction`, `pronoun`). Enforce agreement rules for subject-verb structures.

### Example 3: Chinese Language Bleed in Structured Fields (Q103, Q110, Q130)
* **Problematic Outputs:**
  * Q103: `status (名词)`, `ongoing (形容词)`, `construction (名词)`, `project (名词)`
  * Q110: `inventory (名词)`
  * Q121: `cost (n谓语)`
  * Q130: `diagnosed (动词)`, `diagnostic (形容词)`
* **Why it is wrong:** `qwen2.5:3b` has strong bilingual Chinese-English pretraining weights. When generating structured linguistics fields without strict schema validation or explicit output constraints, it defaults to Chinese grammatical terminology (`名词` = noun, `形容词` = adjective, `动词` = verb, `谓语` = predicate).
* **Recommended Correction Direction:** Implement a Pydantic enum validator or regex check on `vocabulary[].part_of_speech` ensuring only standard ASCII English grammatical labels are accepted.

### Example 4: Bizarre Vocabulary Hallucinations & Mistranslations (Q105, Q101)
* **Problematic Outputs:**
  * Q105: `word: "spread", meaning: "nóng ròng rã", part_of_speech: "verb"`
  * Q101: `word: "which", meaning: "nhớ", part_of_speech: "relative pronoun"`, `word: "questions", meaning: "đề nghị"`
* **Why it is wrong:** In Q105, *the spread of computer viruses* refers to "sự lây lan / sự bùng phát", but the model outputs *"nóng ròng rã"* (sweltering heat). In Q101, *which* is translated as *"nhớ"* (remember), and *questions* (câu hỏi) is translated as *"đề nghị"* (requests).
* **Recommended Correction Direction:** Add post-generation linguistic validation and refine Vietnamese instruction prompts for contextual terminology.

---

## 5. Pass-versus-Quality Comparison

The pipeline marked **25 questions** as `PASS_QUALITY_VALIDATED`. However, **23 of those 25 (92.0%)** contain substantial linguistic or pedagogical errors.

### Why Did the Current Deterministic Validator Not Detect Them?

Inspecting `app/services/enrichment_validator.py` reveals the structural limitations of the current quality validator:

1. **Vocabulary Grounding Only Checks Substring Presence in Source Text:**
   * The validator checks `if normalized_word in normalized_source`.
   * It checks whether the English *word* appeared in the question text or options.
   * **What it misses:** It performs **zero** validation on `part_of_speech` (allowing Chinese characters `名词`, Portuguese, or non-standard tokens) and **zero** semantic validation on Vietnamese `meaning`. Thus, Q103 passed even with Chinese characters in POS, and Q105 passed even with *"nóng ròng rã"*.

2. **Distractor Analysis Validation Only Checks Key Completeness:**
   * The validator checks `if not analysis.get(opt, "").strip(): raise EnrichmentMissingDistractorError`.
   * **What it misses:** Any non-empty string satisfies the check. Even completely erroneous or absurd statements (e.g. claiming *productivity* is an adjective in Q116, or claiming *restrictions* is a gerund in Q124) pass without warning.

3. **Contradiction Check Relies on Naive Substring Trigger Words:**
   * The check searches for phrases like `"đáp án này sai"`, `"không chính xác"`, `"không phù hợp"` inside the analysis of the *authoritative correct answer*.
   * In Q113, the model explicitly wrote `"Đáp án này sai vì nó đúng..."`, which caught the trigger word `"sai"` and was rejected.
   * In Q102, Q104, Q108, Q120, Q124, and Q130, the model wrote affirmative boilerplate (e.g. `"Đáp án A đúng và phù hợp với cấu trúc ngữ pháp..."`), so the validator was blind to the fact that the underlying grammar explanation was completely false.

4. **Zero Structural or Field-Consistency Checks:**
   * The validator does not inspect `grammar_topic`, `sentence_structure`, or `pattern`.
   * As a result, prompt leakage (`"Preposition + which + clause"`) was allowed to pass unflagged in 23 questions.

---

## 6. Historical Comparison

Comparing the primary benchmark (`20261011_142856`) with the historical baseline (`20261010_161846`):

| Metric / Dimension | Historical Baseline (`20261010_161846`) | Primary Baseline (`20261011_142856`) | Comparative Observation |
| :--- | :---: | :---: | :--- |
| **Total Questions** | 30 | 30 | Identical ETS2026 Part 5 scope. |
| **Passed (`PASS_QUALITY_VALIDATED`)** | 24 (80.0%) | 25 (83.3%) | +1 net passing record. |
| **Quality Rejected (`REJECTED_QUALITY`)** | 4 (13.3%) | 3 (10.0%) | Q101, Q104, Q116, Q126 vs Q109, Q112, Q113. |
| **Schema Failed (`FAIL_SCHEMA_VALIDATION`)** | 1 (3.3%) | 1 (3.3%) | **Identical failure:** Q118 failed both runs due to duplicate/missing distractor keys. |
| **JSON Decode Failed (`FAIL_JSON_DECODE`)** | 1 (3.3%) | 1 (3.3%) | Q121 failed in historical; Q127 failed in primary. |
| **Prompt Leakage (`which` in structure/pattern)** | 17 / 30 (56.7%) | 21 / 30 (70.0%) | Recurring systemic behavior across runs. |
| **Chinese Characters in Enrichment** | 4 / 30 (13.3%) | 6 / 30 (20.0%) | Systematic Chinese pretraining bleed in structured fields. |
| **Total Elapsed Time** | 349.17s (11.64s/q) | 353.23s (11.77s/q) | Consistent generation latency. |

### Cautious Analysis:
1. **Schema Instability on Distractor Keys:** In both runs, Q118 generated malformed distractor keys (`A`, `C`, `D`, `A`, missing `B`), proving that `qwen2.5:3b` occasionally loses track of dictionary keys when generating long Vietnamese distractor analyses.
2. **Rejection Fluctuations:** In the historical run, Q101 (*reviewing*), Q104 (*resulting*), and Q116 (*production*) were rejected because the model generated morphological derivations not present verbatim in the text. In the new run, Q109 (*which*) was rejected because prompt leakage spilled *which* into vocabulary, and Q112 (*expanding*) was rejected because the text had *to expand*.
3. **Core Defect Permanence:** Prompt leakage and Chinese POS tokens are **not** transient random noise; they recurred systematically across both benchmark runs with high consistency.

---

## 7. Recommended Next Engineering Task

### Priority Selection:
**Task: Eliminate Prompt Contamination and Neutralize Pattern/Structure Specification in `SYSTEM_PROMPT`**

### Justification:

1. **Frequency (76.7% affected):**
   Prompt leakage is the single most widespread defect in the entire pipeline, contaminating 23 out of 30 questions.

2. **Severity (Root Cause of False Grammar):**
   The few-shot examples in `SYSTEM_PROMPT` (lines 50–52 of `app/services/enrichment_service.py`):
   ```text
   - 'grammar_topic': (e.g., "Preposition + Relative Pronoun", "Word Form (Adverb)")
   - 'sentence_structure': (e.g., "S + V + at [Time], [Prep] + which + S + V")
   - 'pattern': (e.g., "preposition + which + clause", "prior to + V-ing")
   ```
   act as an overwhelming prior for the compact 3B model. The model forces almost every question into this exact template, directly causing false explanations (claiming *last* is a preposition, *update* is a gerund, *her* connects via *which*, *assurance* connects via *which*). Removing this contamination eliminates the primary driver of hallucinated grammar rules.

3. **Impact on Downstream Learner Diagnosis:**
   If the TOEIC agent diagnoses a learner's error on Q102 as a failure of "Preposition + Relative Pronoun" rather than "Word Form (Adjective)", the adaptive learning engine will update the wrong knowledge node and recommend irrelevant remedial practice.

4. **Smallest Implementation Scope:**
   This requires zero schema changes, zero database migrations, and zero validator re-architectures. It only requires neutralizing the prompt examples in `app/services/enrichment_service.py` to use abstract, non-leading placeholders (or distinct domain-relevant examples), yielding immediate, high-leverage linguistic improvements across the entire Part 5 dataset.
