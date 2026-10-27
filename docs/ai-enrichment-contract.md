# AI Enrichment Contract

## 1. Document Purpose

This document serves as the formal specification and contractual agreement between the TOEIC Agent application and the Large Language Model (LLM) for the Question Enrichment capability.

- **Contract Role:** Acts as the immutable source of truth for downstream implementation phases (Prompt engineering, LLM services, and orchestration).
- **Core Objective:** Guarantees that the LLM generates structured, deterministic, and schema-compliant outputs that pass Pydantic validation before any persistence.
- **Access Boundary:** The LLM **never** has direct access to the database. It operates strictly as an isolated analytical component that accepts specific input parameters and returns enriched educational analysis.

---

## 2. Processing Context

The enrichment pipeline sits between Question ingestion and database persistence:

```text
Question Bank
    ↓
Question (Source Data)
    ↓
Build AI Input (Application Boundary)
    ↓
LLM (Inference)
    ↓
Raw LLM Output (Untrusted Data)
    ↓
Pydantic Validation (QuestionEnrichment Schema)
    ↓
QuestionEnrichment Model (Persistence Boundary)
    ↓
Database (toeic_agent.db)
```

### Component Responsibilities:
1. **Question:** Persistent source entity containing the raw test question and correct answer.
2. **Build AI Input:** Prepares a sanitized, isolated payload devoid of internal database metadata.
3. **LLM:** Generates educational analysis, grammar explanations, distractor rationale, and difficulty evaluation.
4. **Pydantic Validation (`QuestionEnrichment`):** Hard security and schema validation gatekeeper. Rejects malformed or hallucinated responses.
5. **Database:** Only receives and stores data that has strictly passed Pydantic validation.

> **Strict Rule:** Bypassing Pydantic validation (`Question -> LLM -> Database`) is strictly prohibited.

---

## 3. AI Input Contract

The LLM is invoked with a strictly bounded input payload:

```json
{
  "question_text": "string",
  "option_a": "string",
  "option_b": "string",
  "option_c": "string",
  "option_d": "string",
  "correct_answer": "A | B | C | D"
}
```

### Field Definitions:
- `question_text` (*string*, required): Full text of the TOEIC question containing the blank (`______`).
- `option_a` (*string*, required): Choice A.
- `option_b` (*string*, required): Choice B.
- `option_c` (*string*, required): Choice C.
- `option_d` (*string*, required): Choice D. For Reading scope (Parts 5, 6, and 7), all four options are strictly required. Missing answer options must not be accepted as valid Reading questions.
- `correct_answer` (*string*, required): Authoritative correct answer key (`A`, `B`, `C`, or `D`) supplied directly by the Question Bank.

> **Strict Rule:** The supplied `correct_answer` is authoritative input. The enrichment process and LLM **must never** attempt to reassign, dispute, or silently override `correct_answer`.

---

## 4. Input Boundary

The following application-level fields are **excluded** from the AI Input Contract:
- `id` / `question_id` (Primary keys)
- `test_id` (Exam identifier)
- Database status (`status`, `PENDING`, `COMPLETED`, etc.)
- Timestamps (`created_at`, `updated_at`)
- Internal database metadata or schema configurations

**Rationale:** The LLM solely analyzes pedagogical content. State management, persistence identity, and workflow state belong exclusively to the application layer.

---

## 5. AI Responsibilities

The LLM is responsible for generating seven pedagogical dimensions:
1. **`grammar_topic`:** Identify the primary grammatical point being tested (e.g., "Subject-Verb Agreement", "Gerund vs. Infinitive", "Causative Verbs").
2. **`sentence_structure`:** Outline the high-level syntax of the sentence (e.g., `S + V + O + to-V`, `Although + S + V, S + V`).
3. **`pattern`:** Extract the actionable pattern or collocation directly applicable to solving the question (e.g., `encourage someone to do something`).
4. **`vocabulary`:** Extract high-value, TOEIC-relevant words or expressions with Vietnamese meanings and parts of speech.
5. **`explanation`:** Provide an overarching explanation of why the correct option satisfies the context and grammatical rules.
6. **`distractor_analysis`:** Detail why the correct option is right and explicitly why each incorrect option is wrong (grammatical incompatibility, wrong part of speech, wrong tense, semantic contradiction).
7. **`difficulty`:** Objectively assess overall question difficulty (`easy`, `medium`, or `hard`).

---

## 6. AI Non-Responsibilities

The LLM **must never**:
- Query, insert, update, or delete database records.
- Generate or modify `id`, `question_id`, or foreign keys.
- Modify `question_text`, `option_a`, `option_b`, `option_c`, `option_d`.
- Alter or question `correct_answer`.
- Determine database `status` or orchestrate background jobs.
- Produce markdown commentary or explanations outside the JSON payload.

---

## 7. AI Output Contract

The LLM must return exclusively a valid JSON object matching the following structure:

```json
{
  "grammar_topic": "string",
  "sentence_structure": "string",
  "pattern": "string",
  "vocabulary": [
    {
      "word": "string",
      "meaning": "string",
      "part_of_speech": "string"
    }
  ],
  "explanation": "string",
  "distractor_analysis": {
    "A": "string",
    "B": "string",
    "C": "string",
    "D": "string"
  },
  "difficulty": "easy | medium | hard"
}
```

> **Constraint:** No additional root or nested fields are permitted.

---

## 8. Output Field Specification

| Field | Type | Required | Language | Constraints / Rules | Educational Purpose |
|---|---|---|---|---|---|
| `grammar_topic` | `string` | Yes | English | Non-empty string; concise, consistent terminology; avoid overly generic labels such as `"Grammar"` or `"Part 5"`. | Identifies the specific grammar or language concept tested for student diagnostic and weakness tagging. |
| `sentence_structure` | `string` | Yes | English | Non-empty string; concise structural syntax formula; make the blank's grammatical role clear. Prefer reusable formula over copying the entire sentence. | Outlines the syntactic skeleton relevant to solving the question so learners recognize sentence patterns. |
| `pattern` | `string` | Yes | English | Non-empty string; key grammar pattern, construction, or collocation (e.g., `prior to + V-ing`, `preposition + which + clause`). | Provides an actionable, transferable formula for rapid test-taking. |
| `vocabulary` | `list[object]` | Yes | English / Vietnamese | List of `VocabularyItem`; 1–4 items. Words must strictly occur in the question text or options. | High-yield vocabulary glossary relevant to workplace/business context in the question. |
| `explanation` | `string` | Yes | Vietnamese | Non-empty string; clear, pedagogical explanation; must identify grammatical evidence, structure, or contextual clues; must explain why authoritative answer fits; **must not contradict the authoritative answer**. | Main comprehensive explanation for the student explaining the solution logic step-by-step. |
| `distractor_analysis` | `object` | Yes | Vietnamese | Object with keys `"A"`, `"B"`, `"C"`, `"D"` (all required, non-empty strings). Correct option explains why it fits; each distractor identifies the specific grammatical, structural, or contextual problem. **Avoid generic explanations like "This answer is incorrect"**. | Explains each choice individually, dissecting common traps and elimination reasons. |
| `difficulty` | `string` | Yes | English | Strictly one of: `"easy"`, `"medium"`, `"hard"`. | Calibrates student progress, adaptive practice, and question bank analytics. |

---

## 9. Vocabulary Rules

- Extract approximately 1–4 high-yield words or collocations from the question.
- **Strict Grounding Rule:** Only select words or expressions that **actually occur in the question text or answer options**. Do **not** invent vocabulary items not present in the question context.
- Skip basic grammatical stop words (e.g., "is", "the", "and", "in").
- Each item must strictly contain:
  - `word` (*string*): The base or contextual word found in the question.
  - `meaning` (*string*): Vietnamese definition appropriate to the specific sentence context.
  - `part_of_speech` (*string*): Concise English grammatical class (`noun`, `verb`, `adjective`, `adverb`, `preposition`, `conjunction`, etc.).

---

## 10. Distractor Analysis Rules

- Must contain entries for all four options: `"A"`, `"B"`, `"C"`, and `"D"`.
- Every option must receive a question-specific explanation in Vietnamese.
- **For the authoritative correct answer:** Explicitly explain why it fits the sentence structure, syntax, and context.
- **For distractors:** Pinpoint the exact reason each choice is eliminated:
  - Grammatical incompatibility (e.g., incorrect part of speech, wrong verb tense/voice, subject-verb agreement failure).
  - Structural mismatch (e.g., preposition cannot take this complement, conjunction requires a full clause).
  - Semantic contradiction or inappropriate collocation.
- **Strictly Prohibited:** Generic placeholders such as `"Đáp án này sai"`, `"A is correct"`, `"B is wrong"`, or `"Không phù hợp"`.

---

## 11. Difficulty Rules

| Level | Criteria |
|---|---|
| `easy` | Transparent sentence structure; direct grammar rule; basic vocabulary; distractors easily eliminated. |
| `medium` | Standard TOEIC question; requires identifying clause structure or common collocation; distractors share similar roots or parts of speech. |
| `hard` | Complex/inverted structure, double clauses, subtle word choice/collocation, deceptive distractors requiring both grammatical and contextual analysis. |

---

## 12. Validation Boundary & Potential Contradictions

The LLM is an **untrusted system component**. Its response is treated as raw text:

```text
Raw LLM String Output
    ↓
JSON Parser (json.loads)
    ↓
Pydantic Validation (QuestionEnrichment.model_validate)
    ├─► Valid   ──► Semantic Consistency Checks (Phase 3.3.12.2B.2) ──► Commit to DB
    └─► Invalid ──► ValidationError Raised ──► Rejected (No DB Write)
```

No unvalidated LLM output may ever reach SQLite or SQLAlchemy.

### Potential Contradictions & Semantic Limitations:

1. **Authoritative Input Guarantee:**
   - The correct answer supplied by the Question Bank (`correct_answer`) is authoritative input.
   - If the supplied answer appears inconsistent or debatable in the question context, the system **must not silently change the answer or fabricate an explanation** to justify an incorrect choice.

2. **Structural Validation vs. Semantic Correctness:**
   - **Structural validation (Pydantic schema) alone cannot guarantee semantic correctness.**
   - Pydantic enforces data types, key presence, non-empty strings, and schema formats, but cannot determine whether the explanation text linguistically supports or contradicts the authoritative answer.
   - Therefore, educational quality requires a multi-layered boundary:
     - **Layer 1: Structural Validation (Pydantic):** Hard gatekeeper against syntax errors, missing fields, or invalid keys.
     - **Layer 2: Prompt Anchoring & Instruction:** Directs the model to ground its analysis on proving the authoritative answer and eliminating distractors.
     - **Layer 3: Lightweight Semantic Consistency Checks:** Programmatic validation verifying that the distractor analysis for `correct_answer` does not contain contradiction signals, and incorrect options are not marked as correct.

---

## 13. Source of Truth

Hierarchy of authority in case of discrepancies:
1. **Application Pydantic Schema (`app/schemas/enrichment.py`)** — Highest authority.
2. **AI Enrichment Contract (`docs/ai-enrichment-contract.md`)** — Specification standard.
3. **Prompt Definition (`docs/ai-enrichment-prompt.md`)** — Prompt implementation.
4. **LLM Output** — Lowest authority (must adapt to the schema, never the reverse).

---

## 14. Example

### Input:
```json
{
  "question_text": "Ms. Davis requested that the marketing report ______ revised before the executive meeting.",
  "option_a": "is",
  "option_b": "was",
  "option_c": "be",
  "option_d": "being",
  "correct_answer": "C"
}
```

### Output:
```json
{
  "grammar_topic": "Subjunctive Mood",
  "sentence_structure": "S + requested + that + S + (should) + V-bare",
  "pattern": "request that somebody (should) do something",
  "vocabulary": [
    {
      "word": "request",
      "meaning": "yêu cầu, đề nghị",
      "part_of_speech": "verb"
    },
    {
      "word": "revise",
      "meaning": "chỉnh sửa, sửa đổi",
      "part_of_speech": "verb"
    },
    {
      "word": "executive",
      "meaning": "cấp quản lý, điều hành",
      "part_of_speech": "noun"
    }
  ],
  "explanation": "Động từ 'request' theo sau bởi mệnh đề 'that' sử dụng cấu trúc giả định thức (Subjunctive Mood): động từ trong mệnh đề phụ luôn ở dạng nguyên thể không 'to' (be) dù chủ ngữ là số ít hay thì quá khứ.",
  "distractor_analysis": {
    "A": "Sai ngữ pháp vì trong thức giả định sau 'requested that', động từ không chia theo thì hiện tại 'is'.",
    "B": "Sai ngữ pháp vì không lùi thì về quá khứ 'was' trong cấu trúc thức giả định.",
    "C": "Đúng vì 'be' là động từ nguyên thể không 'to' chuẩn xác theo sau cấu trúc giả định thức 'request that + S + V-bare'.",
    "D": "Sai vì dạng phân từ 'being' không thể làm động từ vị ngữ chính trong mệnh đề phụ này."
  },
  "difficulty": "hard"
}
```

---

## 15. Error Scenarios & Rejection Policy

1. **Invalid JSON / Syntax Errors:** Output contains trailing commas, missing quotes, or extra conversational text (e.g. `Here is the response:`). ➔ **Rejected**.
2. **Missing Required Fields:** Omission of `pattern`, `explanation`, or any other key. ➔ **Rejected**.
3. **Invalid Difficulty:** Value outside `["easy", "medium", "hard"]` (e.g. `"very_hard"`). ➔ **Rejected**.
4. **Malformed Vocabulary:** Item missing `meaning` or `part_of_speech`. ➔ **Rejected**.
5. **Incomplete Distractor Analysis:** Missing options `A`, `B`, `C`, or `D`. ➔ **Rejected**.
6. **Hallucinated Attributes:** Fields such as `id`, `question_id`, `created_at` or `notes`. ➔ **Rejected**.

---

## 16. Implementation Constraints

For coding agents in subsequent phases:
- Do **not** bypass Pydantic `QuestionEnrichment.model_validate()`.
- Do **not** inject database operations or credentials into the prompt.
- Do **not** add unnecessary abstractions, wrapper classes, or microservices.
- Ensure all prompt variables strictly map to the Input Contract.

---

## 17. Out of Scope

This contract intentionally does not cover:
- Detailed prompt templates (defined in `docs/ai-enrichment-prompt.md`).
- Cloud LLM provider transport and network retry mechanisms.
- Batch processing or Celery workers.
- Front-end / UI rendering logic.

---

## 18. Definition of Done

- [x] Input contract explicitly defined without database identity fields.
- [x] Output contract strictly aligns with `app/schemas/enrichment.py`.
- [x] All 7 pedagogical fields specified with type, constraints, and intent.
- [x] Security and validation boundary established.
- [x] Error and rejection scenarios comprehensively listed.
- [x] Concrete pedagogical example provided.
