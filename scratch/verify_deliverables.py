import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')
import json
import sqlite3
from app.schemas.enrichment import QuestionEnrichment, VALID_PARTS_OF_SPEECH
from app.services.enrichment_validator import EnrichmentValidator

candidate_path = 'reports/gold_set_review/part5_gold_set_candidate_2026-10-12.json'

print('=== 1. Parse Candidate JSON with json.loads ===')
with open(candidate_path, 'r', encoding='utf-8') as f:
    candidate_data = json.load(f)
print('Successfully parsed JSON.')
print('Dataset Name:', candidate_data.get('dataset_name'))
print('Review Status:', candidate_data.get('review_status'))

print('\n=== 2. Check Question Numbers & Count ===')
items = candidate_data.get('items', [])
q_nos = [item['question_no'] for item in items]
expected_nos = [101, 102, 104, 105, 108, 110, 112, 114, 119, 124, 127, 130]

print(f'Total items: {len(items)}')
print(f'Unique question numbers count: {len(set(q_nos))}')
print(f'Question numbers: {q_nos}')
assert len(items) == 12, f'Expected 12 items, got {len(items)}'
assert len(set(q_nos)) == 12, 'Duplicate question numbers found'
assert q_nos == expected_nos, f'Question numbers mismatch: {q_nos} vs {expected_nos}'
print('Question numbers check: PASSED (Exact match).')

print('\n=== 3. Read Database Snapshot for Verification (Read-Only) ===')
conn = sqlite3.connect('file:toeic_agent.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
db_rows = conn.cursor().execute('SELECT * FROM questions ORDER BY question_no').fetchall()
print(f'Total questions in DB: {len(db_rows)}')
assert len(db_rows) == 30, f'Expected 30 questions in DB, got {len(db_rows)}'
db_map = {r['question_no']: dict(r) for r in db_rows}

print('\n=== 4. Validate Schema, Distractor Keys, POS Taxonomy & Grounding ===')
validator = EnrichmentValidator()
schema_passed = 0
distractor_passed = 0
pos_passed = 0
grounding_passed = 0

for item in items:
    q_no = item['question_no']
    print(f'\n--- Item Q{q_no} ---')
    db_item = db_map[q_no]
    
    # Check source data fidelity
    assert item['question_text'] == db_item['question_text'], f'Q{q_no} question_text mismatch'
    assert item['options']['A'] == db_item['option_a'], f'Q{q_no} option_a mismatch'
    assert item['options']['B'] == db_item['option_b'], f'Q{q_no} option_b mismatch'
    assert item['options']['C'] == db_item['option_c'], f'Q{q_no} option_c mismatch'
    assert item['options']['D'] == db_item['option_d'], f'Q{q_no} option_d mismatch'
    assert item['correct_answer'] == db_item['correct_answer'], f'Q{q_no} correct_answer mismatch'
    assert item['review_status'] == 'DRAFT_NEEDS_HUMAN_REVIEW', f'Q{q_no} review_status must be DRAFT_NEEDS_HUMAN_REVIEW'
    
    # 3. Schema validation
    enr_payload = item['enrichment']
    qe = QuestionEnrichment(**enr_payload)
    schema_passed += 1
    
    # 4. Check distractor keys
    dist_keys = sorted(list(enr_payload['distractor_analysis'].keys()))
    assert dist_keys == ['A', 'B', 'C', 'D'], f'Q{q_no} distractor keys invalid: {dist_keys}'
    distractor_passed += 1
    
    # 4. Check POS labels
    for v in qe.vocabulary:
        pos = v.part_of_speech
        assert pos in VALID_PARTS_OF_SPEECH, f'Q{q_no} invalid POS: {pos}'
    pos_passed += 1
    
    # 5. Check grounding
    val_res = validator.validate(db_item, qe)
    if val_res.is_valid:
        grounding_passed += 1
        print(f'  Validation: PASSED (status={val_res.status.value})')
    else:
        print(f'  Validation: FAILED (errors={val_res.errors})')
        raise AssertionError(f'Q{q_no} failed validator: {val_res.errors}')
        
    # Check vocab items detail
    for v in qe.vocabulary:
        print(f'    Vocab: "{v.word}" ({v.part_of_speech}) -> "{v.meaning}"')

print(f'\nSummary: Schema Passed: {schema_passed}/12, Distractors Passed: {distractor_passed}/12, POS Passed: {pos_passed}/12, Grounding/Validator Passed: {grounding_passed}/12')

print('\n=== 5. Final DB Check (Read-Only Safety) ===')
c = conn.cursor()
c.execute('SELECT count(*) FROM questions')
count_after = c.fetchone()[0]
assert count_after == 30, f'DB count altered! {count_after} != 30'
print(f'Final DB count: {count_after} (UNCHANGED).')
