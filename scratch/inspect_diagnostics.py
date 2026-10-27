import json
from pathlib import Path

# Inspect Qwen report
qwen_file = list(Path("reports/pos_consistency").glob("pos_consistency_revalidated_part5_batch_qwen*.json"))[-1]
with open(qwen_file, encoding="utf-8") as f:
    qwen_diag = json.load(f)

print(f"=== QWEN DIAGNOSTIC INSPECTION ({qwen_file.name}) ===")
mismatches = [d for d in qwen_diag["diagnostics"] if d["checker_outcome"] == "POS_CONTEXT_MISMATCH"]
print(f"Mismatches ({len(mismatches)}):")
for m in mismatches:
    print(f"  Q{m['question_no']} word='{m['vocabulary_word']}' expected={m['expected_pos']} spacy={m['spacy_pos']}/{m['spacy_tag']} dep={m['spacy_dep']} rule='{m['mapping_rule']}'")

target_qs = [102, 104, 106, 110, 114, 125, 126, 130]
print("\nTarget Questions in Qwen:")
for d in qwen_diag["diagnostics"]:
    if d["question_no"] in target_qs:
        print(f"  Q{d['question_no']}: word='{d['vocabulary_word']}', expected={d['expected_pos']}, outcome={d['checker_outcome']}, spacy={d['spacy_pos']}/{d['spacy_tag']}, mode={d['match_mode']}, rat='{d.get('mapping_rationale')}'")

# Inspect Gemini report
gem_file = list(Path("reports/pos_consistency").glob("pos_consistency_revalidated_part5_batch_gemini*.json"))[-1]
with open(gem_file, encoding="utf-8") as f:
    gem_diag = json.load(f)

print(f"\n=== GEMINI DIAGNOSTIC INSPECTION ({gem_file.name}) ===")
target_qs = [102, 104, 106, 110, 114, 125, 126, 130]
for d in gem_diag["diagnostics"]:
    if d["question_no"] in target_qs:
        print(f"  Q{d['question_no']}: word='{d['vocabulary_word']}', expected={d['expected_pos']}, outcome={d['checker_outcome']}, spacy={d.get('spacy_pos')}/{d.get('spacy_tag')}, mode={d['match_mode']}, rat='{d.get('mapping_rationale')}'")

# Inspect Adjudication CSVs
print("\n=== ADJUDICATION CSV CHECKS ===")
csv_files = list(Path("reports/pos_consistency").glob("*.csv"))
for cf in csv_files:
    print(f"{cf.name}:")
    with open(cf, encoding="utf-8-sig") as f:
        lines = f.readlines()
    print(f"  Total lines: {len(lines)}")
    if len(lines) > 1:
        print(f"  First data row: {lines[1].strip()[:100]}...")
