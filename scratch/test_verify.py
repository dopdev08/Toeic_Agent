import json
from app.services.enrichment_response_parser import parse_and_validate_enrichment
from app.services.enrichment_validator import EnrichmentValidator
from scripts.test_gemini_batch import QuestionInput

with open("reports/part5_batch_gemini-3.5-flash-lite_20261012_175519.json", "r", encoding="utf-8") as f:
    data = json.load(f)

validator = EnrichmentValidator()

for r in data["results"]:
    q_no = r["question_no"]
    if q_no in (116, 118, 120):
        raw = r["raw_response"]
        enrichment = parse_and_validate_enrichment(raw, sanitize=True)
        q_input = QuestionInput(r)
        val_res = validator.validate(q_input, enrichment)
        print(f"Q{q_no}: is_valid={val_res.is_valid}, status={val_res.status}, warnings={val_res.warnings}")
