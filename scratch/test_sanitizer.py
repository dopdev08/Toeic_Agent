import json
import re
from pathlib import Path

def remove_trailing_commas(text: str) -> str:
    """Remove trailing commas before closing braces/brackets outside string literals."""
    result = []
    in_string = False
    escape = False
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            i += 1
        else:
            if char == '"':
                in_string = True
                result.append(char)
                i += 1
            elif char == ",":
                # Look ahead past whitespace to see if next token is } or ]
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] in ("}", "]"):
                    # Omit this comma
                    i += 1
                else:
                    result.append(char)
                    i += 1
            else:
                result.append(char)
                i += 1
    return "".join(result)


def sanitize_json_text(text: str) -> str:
    """Sanitize raw LLM response by extracting JSON and cleaning syntax artifacts."""
    if not isinstance(text, str):
        return ""
    
    cleaned = text.strip()
    if not cleaned:
        return ""

    # 1. Extract markdown code fence if present
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # 2. Extract outermost JSON object if surrounding commentary exists
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace : last_brace + 1].strip()

    # 3. Remove trailing commas before } or ]
    cleaned = remove_trailing_commas(cleaned)

    # 4. Clean invalid JS-style escapes like \' -> '
    cleaned = re.sub(r"\\'", "'", cleaned)

    return cleaned


def test_sanitizer():
    # 1. Test Q102
    p = Path("reports/part5_batch_gemini-3.5-flash-lite_20261012_122158.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    q102_raw = None
    for item in data.get("results", []):
        if item.get("question_no") == 102:
            q102_raw = item.get("raw_response")
            break
    assert q102_raw is not None
    
    # Raw fails json.loads
    try:
        json.loads(q102_raw)
        print("Raw surprisingly passed?!")
    except json.JSONDecodeError as e:
        print("Raw correctly failed with:", e)

    # Sanitized passes json.loads!
    sanitized = sanitize_json_text(q102_raw)
    parsed = json.loads(sanitized)
    print("Sanitized Q102 parsed successfully! Keys:", list(parsed.keys()))
    print("Distractor keys:", list(parsed["distractor_analysis"].keys()))

    # 2. Test Markdown code fences with commentary
    fenced = """Here is your JSON response:
```json
{
  "key": "value, with comma",
  "nested": {
    "sub": "ok",
  },
}
```
Hope that helps!"""
    clean_fenced = sanitize_json_text(fenced)
    parsed_fenced = json.loads(clean_fenced)
    assert parsed_fenced["key"] == "value, with comma"
    assert parsed_fenced["nested"]["sub"] == "ok"
    print("Fenced test passed!")

    # 3. Test array trailing commas and strings with braces
    complex_text = '{"items": [1, 2, 3, ], "text": "a string with } and ] and , inside"}'
    clean_complex = sanitize_json_text(complex_text)
    parsed_complex = json.loads(clean_complex)
    assert parsed_complex["items"] == [1, 2, 3]
    assert parsed_complex["text"] == "a string with } and ] and , inside"
    print("Complex test passed!")

if __name__ == "__main__":
    test_sanitizer()
