# Revalidation Report and Database Integrity Reconciliation Audit

- **Date:** 2026-10-12
- **Repository:** `D:\project\Toeic_Agent`
- **Execution Mode:** Offline only; zero LLM calls; read-only SQLite database inspection (`mode=ro`).
- **Audit Target:** Historical benchmark revalidation artifacts, report revalidator implementation, and production database integrity.

---

## 1. Executive Summary & Root Cause Analysis

This audit resolves four critical discrepancies identified in previous execution reports:

1. **Qwen Report Discrepancy ("26 passed" vs 27 PASS):**
   - **Root Cause:** A narrative summarization error in the Task 3 execution report. The text copied an older 26-pass baseline description ("26 PASS_QUALITY_VALIDATED, 1 REJECTED_QUALITY...").
   - **Empirical Evidence:** The actual source report file (`reports/part5_batch_qwen2.5_3b_20261012_123315.json`) contained **29** `PASS_QUALITY_VALIDATED` and **1** `REJECTED_QUALITY` (30 total). When revalidated under the strict Task 1 schema (`extra='forbid'`, exact distractors A–D), 2 items (Q119 with extra key `E`, Q127 with extra key `Explanation`) failed schema validation. This resulted in exactly **27 PASS_QUALITY_VALIDATED**, **2 FAIL_SCHEMA_VALIDATION**, and **1 REJECTED_QUALITY** ($27 + 2 + 1 = 30$). The underlying result array was correct; the narrative introduction was erroneous.

2. **Gemini Report Discrepancy ("26 passed" vs 17 PASS):**
   - **Root Cause:** The same narrative copy-paste error from the older baseline text.
   - **Empirical Evidence:** The actual source report file (`reports/part5_batch_gemini-3.5-flash-lite_20261012_122158.json`) contained **28** `PASS_QUALITY_VALIDATED`, **1** `FAIL_SCHEMA_VALIDATION` (Q120 missing distractor D), and **1** `FAIL_JSON_DECODE` (Q102 invalid syntax) (30 total). Under Task 1 strict schema, 11 previously passed items failed schema validation due to non-canonical part-of-speech labels (`noun phrase`, `verb phrase`, `prepositional phrase`), yielding exactly **17 PASS_QUALITY_VALIDATED**, **12 FAIL_SCHEMA_VALIDATION**, and **1 FAIL_JSON_DECODE** ($17 + 12 + 1 = 30$).

3. **Database Integrity Reconciliation (`question_enrichments` empty vs absent):**
   - **Empirical Evidence:** Safe inspection of `toeic_agent.db` via SQLite read-only URI mode confirmed that `sqlite_master` contains tables `questions` (30 rows) and `question_enrichments` (0 rows). The table `alembic_version` is **absent**.
   - **Resolution:** The table `question_enrichments` is **PRESENT and EMPTY (0 rows)**. The statement from earlier reports that `question_enrichments` had zero rows was accurate; the Task 3 claim that the database had only `questions` and `alembic_version` was incorrect.

4. **Gemini POS Taxonomy Compatibility:**
   - **Empirical Evidence:** Gemini raw responses across 11 questions contain 14 instances of non-canonical POS tags (`noun phrase`: 10, `verb phrase`: 3, `prepositional phrase`: 1).
   - **Resolution:** In accordance with task constraints, `VALID_PARTS_OF_SPEECH` was **not modified**, and no unapproved labels were coerced. The compatibility issue is documented for a formal schema decision.

---

## 2. Recomputed Status Counts from Source & Revalidated Reports

### A. Qwen 2.5 3B (`part5_batch_qwen2.5_3b_20261012_123315.json`)
- **Source File Path:** `reports/part5_batch_qwen2.5_3b_20261012_123315.json`
- **Source SHA-256:** `fe964bdb2611772ee460a39f1ff47d8d542989c22f82af0d47893b6e25461e57`
- **Revalidation Output File:** `reports/revalidation/revalidated_part5_batch_qwen2.5_3b_20261012_123315_20261012_135704.json`

| Metric / Status | Source Report Header | Direct Source Results Array | Recalculated Final Summary | Direct Revalidated Results Array |
| :--- | :---: | :---: | :---: | :---: |
| `PASS_QUALITY_VALIDATED` | 29 | 29 | 27 | 27 |
| `FAIL_SCHEMA_VALIDATION` | 0 | 0 | 2 | 2 |
| `REJECTED_QUALITY` | 1 | 1 | 1 | 1 |
| `FAIL_JSON_DECODE` | 0 | 0 | 0 | 0 |
| `FAIL_LLM_SERVICE` | 0 | 0 | 0 | 0 |
| `FAIL_UNEXPECTED` | 0 | 0 | 0 | 0 |
| **Total Questions** | **30** | **30** | **30** | **30** |

#### Status Transition Matrix (Qwen)
| Source Status | Final Status | Count | Affected Question(s) | Reason |
| :--- | :--- | :---: | :--- | :--- |
| `PASS_QUALITY_VALIDATED` | `PASS_QUALITY_VALIDATED` | 27 | 27 questions | Compliant with schema & quality checks |
| `PASS_QUALITY_VALIDATED` | `FAIL_SCHEMA_VALIDATION` | 2 | Q119, Q127 | Extra key `E` in distractor_analysis (Q119); extra key `Explanation` (Q127) |
| `REJECTED_QUALITY` | `REJECTED_QUALITY` | 1 | Q112 | Ungrounded vocabulary `expansion` |
| **Total Accounted** | | **30** | | $\sum \text{transitions} == \operatorname{len}(\text{results}) == 30$ |

---

### B. Gemini 3.5 Flash Lite (`part5_batch_gemini-3.5-flash-lite_20261012_122158.json`)
- **Source File Path:** `reports/part5_batch_gemini-3.5-flash-lite_20261012_122158.json`
- **Source SHA-256:** `5fc1949d4dcf2667b3cc372cd2e95d5460b70ef9a3b86a878ea7363098b79e8f`
- **Revalidation Output File:** `reports/revalidation/revalidated_part5_batch_gemini-3.5-flash-lite_20261012_122158_20261012_135704.json`

| Metric / Status | Source Report Header | Direct Source Results Array | Recalculated Final Summary | Direct Revalidated Results Array |
| :--- | :---: | :---: | :---: | :---: |
| `PASS_QUALITY_VALIDATED` | 28 | 28 | 17 | 17 |
| `FAIL_SCHEMA_VALIDATION` | 1 | 1 | 12 | 12 |
| `FAIL_JSON_DECODE` | 1 | 1 | 1 | 1 |
| `REJECTED_QUALITY` | 0 | 0 | 0 | 0 |
| `FAIL_LLM_SERVICE` | 0 | 0 | 0 | 0 |
| `FAIL_UNEXPECTED` | 0 | 0 | 0 | 0 |
| **Total Questions** | **30** | **30** | **30** | **30** |

#### Status Transition Matrix (Gemini)
| Source Status | Final Status | Count | Affected Question(s) | Reason |
| :--- | :--- | :---: | :--- | :--- |
| `PASS_QUALITY_VALIDATED` | `PASS_QUALITY_VALIDATED` | 17 | 17 questions | Fully compliant with schema & quality checks |
| `PASS_QUALITY_VALIDATED` | `FAIL_SCHEMA_VALIDATION` | 11 | Q101, Q104, Q106, Q107, Q116, Q117, Q118, Q121, Q125, Q126, Q127 | Non-canonical POS tags (`noun phrase`, `verb phrase`, `prepositional phrase`) |
| `FAIL_SCHEMA_VALIDATION` | `FAIL_SCHEMA_VALIDATION` | 1 | Q120 | Missing distractor analysis key `D` in raw response |
| `FAIL_JSON_DECODE` | `FAIL_JSON_DECODE` | 1 | Q102 | Invalid JSON syntax from LLM output |
| **Total Accounted** | | **30** | | $\sum \text{transitions} == \operatorname{len}(\text{results}) == 30$ |

---

## 3. Production Database Integrity Verification

### A. Resolution and Filesystem Metadata
- **Configuration in `app/db/database.py`:**
  ```python
  DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./toeic_agent.db")
  ```
- **Project Root Directory:** `D:\project\Toeic_Agent`
- **Resolved Absolute Database Path:** `D:\project\Toeic_Agent\toeic_agent.db`
- **File Size:** `32,768` bytes (32 KB)

### B. Safe Read-Only Verification Protocol
The database was inspected using Python's standard `sqlite3` module with explicit read-only URI mode:
```python
conn = sqlite3.connect("file:D:/project/Toeic_Agent/toeic_agent.db?mode=ro", uri=True)
```
No write operations, migrations, SQLAlchemy `SessionLocal`, or DDL statements (`create_all`, `drop_all`) were executed against this file.

### C. Inspection Evidence & SHA-256 Invariant
- **SHA-256 Before Inspection:** `902caaec9b5739740e991a8a689238ff697162a0f03e204b39422a9373f848e2`
- **`sqlite_master` Table List:**
  - `[('table', 'question_enrichments'), ('table', 'questions')]`
- **Table Verification & Conditional Row Counts:**
  - Table `questions`: **PRESENT**, Row count = **30**
  - Table `question_enrichments`: **PRESENT**, Row count = **0**
  - Table `alembic_version`: **ABSENT** (does not exist in `sqlite_master`)
- **SHA-256 After Inspection & Entire Test Suite:** `902caaec9b5739740e991a8a689238ff697162a0f03e204b39422a9373f848e2`
- **Hash Match:** **IDENTICAL** (Production database was never modified).

---

## 4. Test Database Isolation Evidence

### A. Risk Identification
In `tests/test_question_enrichment_model.py`, `tests/test_import_questions.py`, and API test fixtures, tests execute:
```python
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
```
If `engine` were bound to `toeic_agent.db`, running test suites would drop production tables.

### B. Isolation Implementation & Enforcement
1. **Default Environment Setting (`tests/conftest.py`):**
   ```python
   os.environ.setdefault("DATABASE_URL", "sqlite:///./test_runner.db")
   ```
2. **Mandatory Session Fixture Assertion (`tests/conftest.py`):**
   Added an autouse session fixture `verify_test_db_isolation` that directly inspects `engine.url`:
   ```python
   @pytest.fixture(scope="session", autouse=True)
   def verify_test_db_isolation():
       from app.db.database import engine
       engine_url_str = str(engine.url)
       assert "test_runner.db" in engine_url_str or ":memory:" in engine_url_str, (
           f"CRITICAL SAFETY VIOLATION: Tests not isolated! Engine URL: {engine_url_str}"
       )
       assert "toeic_agent.db" not in engine_url_str, (
           f"CRITICAL SAFETY VIOLATION: Engine URL is bound to production DB: {engine_url_str}"
       )
   ```
3. **Empirical Proof:**
   All 302 tests ran with this fixture active. The production database SHA-256 was checked immediately following test completion and confirmed completely unchanged.

---

## 5. Gemini POS Taxonomy Compatibility Analysis

### A. Taxonomy Contract
In `app/schemas/enrichment.py`, the strict contract defines:
```python
VALID_PARTS_OF_SPEECH: Final[tuple[str, ...]] = (
    "noun", "verb", "adjective", "adverb", "preposition", "conjunction",
    "pronoun", "determiner", "auxiliary verb", "modal verb", "numeral",
    "proper noun", "phrase"
)
```

### B. Breakdown of Unapproved Labels in Gemini Raw Responses
Gemini generated 14 instances of multi-word phrasal categories across 11 questions instead of the approved umbrella label `phrase`:

| Label Generated | Frequency | Affected Questions & Target Lexical Items |
| :--- | :---: | :--- |
| `noun phrase` | 10 | **Q104** (`media organization`), **Q106** (`hiring manager`), **Q116** (`training program`, `manufacturing system`), **Q117** (`board of directors`), **Q118** (`finance director`), **Q121** (`lighting equipment`), **Q125** (`technical school`), **Q126** (`fixed price`), **Q127** (`chief analytics officer`) |
| `verb phrase` | 3 | **Q101** (`take place`), **Q107** (`leave for`), **Q118** (`move forward`) |
| `prepositional phrase` | 1 | **Q104** (`as a result of`) |
| **Total** | **14** | **11 Questions Total** |

### C. Strict Schema Rejection Rationale
Under Pydantic `extra="forbid"` and the `@field_validator("part_of_speech")`, any label not in `VALID_PARTS_OF_SPEECH` triggers `EnrichmentValidationError`. Because the validator enforces an exact match against the 13 canonical strings, these 11 items legitimately failed schema validation during offline revalidation.

### D. Policy Compliance & Recommendation
- **Action in Task 3.1:** No tags were added to `VALID_PARTS_OF_SPEECH`. No tags were coerced or normalized. No prompt changes were made.
- **Contract Recommendation for Future Tasks:**
  - *Option 1 (Prompt Alignment):* Add negative constraints and explicit few-shot examples in the enrichment prompt instructing the model to use the single canonical label `"phrase"` for all multi-word lexical units.
  - *Option 2 (Taxonomy Expansion):* Explicitly extend `VALID_PARTS_OF_SPEECH` to include `noun phrase`, `verb phrase`, and `prepositional phrase` if the pedagogical objective requires phrasal grammatical distinction.

---

## 6. Implementation Changes & Regression Test Results

### Changed Files
1. `app/services/report_revalidator.py`:
   - Enforced type checking: `item` must be a `dict`, and `status` must be a non-empty string. Malformed status data raises `ValueError` immediately rather than masking errors.
   - Enforced report structure validation: `report_data` must contain a `results` or `items` list.
   - Enforced invariant assertions: `sum(recalc_status_counts.values()) == total_questions == sum(transitions.values()) == sum(prev_status_counts.values())`.
2. `tests/test_report_revalidator.py`:
   - Added `test_revalidate_summary_counts_match_final_statuses_and_total_count`
   - Added `test_revalidate_transition_counts_sum_to_number_of_results`
   - Added `test_revalidate_mixed_statuses_remain_independent_across_batch`
   - Added `test_revalidate_malformed_or_missing_status_data_fails_clearly`
   - Added `test_revalidate_historical_gemini_report_if_present`
3. `tests/conftest.py`:
   - Added `verify_test_db_isolation` autouse fixture.

### Test Execution Summary
- **Focused Test Suite (145 tests):**
  - Command: `pytest tests/test_report_revalidator.py tests/test_enrichment_validator.py tests/test_enrichment_schema.py tests/test_part5_batch_script.py tests/test_gemini_batch_script.py`
  - Result: **145 passed**, 0 failed (1.24s).
- **Full Test Suite (302 tests):**
  - Command: `pytest tests/`
  - Result: **302 passed**, 0 failed (5.85s).

---

## 7. Artifact Integrity Sign-Off

- **Historical Benchmark Files:** Unmodified.
  - `reports/part5_batch_qwen2.5_3b_20261012_123315.json` (SHA-256: `fe964bdb26...`)
  - `reports/part5_batch_gemini-3.5-flash-lite_20261012_122158.json` (SHA-256: `5fc1949d4d...`)
- **New Timestamped Revalidation Artifacts:**
  - `reports/revalidation/revalidated_part5_batch_qwen2.5_3b_20261012_123315_20261012_135704.json`
  - `reports/revalidation/revalidated_part5_batch_gemini-3.5-flash-lite_20261012_122158_20261012_135704.json`
- **Zero LLM Calls Made:** Confirmed.
- **Production DB Untouched:** Confirmed (`toeic_agent.db` SHA-256: `902caaec9b...`).
