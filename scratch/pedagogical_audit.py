import json
from pathlib import Path

def audit():
    p = Path("reports/part5_batch_gemini-3.5-flash-lite_20261012_175519.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    
    out_lines = []
    def log(msg=""):
        out_lines.append(str(msg))

    results = data.get("results", [])
    log(f"Total questions in report: {len(results)}")
    
    # 1. Quality warnings from validator
    log("\n--- 1. Quality Warnings ---")
    warn_counts = {}
    for r in results:
        qno = r.get("question_no")
        for w in r.get("quality_warnings", []):
            warn_counts[w] = warn_counts.get(w, 0) + 1
            log(f"  Q{qno}: {w}")
    if not warn_counts:
        log("  None! (0 quality warnings emitted by validator)")
        
    # 2. Grammar Topics
    log("\n--- 2. Grammar Topics ---")
    for r in results:
        qno = r.get("question_no")
        status = r.get("status")
        enr = r.get("enrichment")
        if enr:
            topic = enr.get("grammar_topic")
            pattern = enr.get("pattern")
            diff = enr.get("difficulty")
            log(f"Q{qno} [{diff}]: topic='{topic}' | pattern='{pattern}'")
        else:
            raw = r.get("raw_response", "")
            try:
                raw_obj = json.loads(raw)
                log(f"Q{qno} [{status}]: topic='{raw_obj.get('grammar_topic')}' (from raw)")
            except Exception:
                log(f"Q{qno} [{status}]: (no parsed enrichment)")

    # 3. Sample Explanations & Distractor Quality Check
    log("\n--- 3. Qualitative Pedagogical Check on Key Questions ---")
    key_qs = [101, 102, 104, 105, 106, 110, 114, 116, 118, 120, 125, 126, 130]
    for r in results:
        qno = r.get("question_no")
        if qno in key_qs:
            enr = r.get("enrichment")
            if not enr:
                try:
                    enr = json.loads(r.get("raw_response", ""))
                except Exception:
                    enr = {}
            log(f"\n==================== Q{qno} ====================")
            log(f"Question: {r.get('question_text')}")
            log(f"Options: A={r.get('option_a')} | B={r.get('option_b')} | C={r.get('option_c')} | D={r.get('option_d')}")
            log(f"Correct Answer: {r.get('correct_answer')}")
            log(f"Topic: {enr.get('grammar_topic')}")
            log(f"Structure: {enr.get('sentence_structure')}")
            log(f"Pattern: {enr.get('pattern')}")
            log(f"Explanation (VN): {enr.get('explanation')}")
            log("Distractors:")
            dist = enr.get("distractor_analysis", {})
            for k in ["A", "B", "C", "D"]:
                val = dist.get(k)
                log(f"  [{k}]: {val}")
            log("Vocabulary:")
            for v in enr.get("vocabulary", []):
                log(f"  * {v.get('word')}: {v.get('meaning')} ({v.get('part_of_speech')})")

    out_p = Path("scratch/pedagogical_audit_output.txt")
    out_p.write_text("\n".join(out_lines), encoding="utf-8")

if __name__ == "__main__":
    audit()
