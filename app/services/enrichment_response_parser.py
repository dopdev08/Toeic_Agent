import json
import re
from typing import Any
from pydantic import ValidationError

from app.schemas.enrichment import VALID_PARTS_OF_SPEECH, QuestionEnrichment


class EnrichmentParseError(Exception):
    """Base exception for enrichment response parsing and validation failures."""

    def __init__(self, message: str, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.raw_response = raw_response


class EnrichmentJSONDecodeError(EnrichmentParseError):
    """Raised when the LLM response is not valid JSON."""

    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        json_error: json.JSONDecodeError | None = None,
    ) -> None:
        super().__init__(message, raw_response=raw_response)
        self.json_error = json_error


class EnrichmentValidationError(EnrichmentParseError):
    """Raised when the parsed JSON does not satisfy the QuestionEnrichment schema."""

    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        raw_data: Any = None,
        validation_error: ValidationError | None = None,
    ) -> None:
        super().__init__(message, raw_response=raw_response)
        self.raw_data = raw_data
        self.validation_error = validation_error

    @property
    def errors(self) -> list[dict[str, Any]]:
        """Return structured Pydantic error details if available."""
        if self.validation_error is not None:
            return self.validation_error.errors()
        return []


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
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] in ("}", "]"):
                    # Trailing comma before closing brace/bracket: omit it
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

    # 1. Strip markdown code fences (e.g. ```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    elif not cleaned.startswith("{"):
        # If no fence and does not start with '{', check for conversational intro ending in newline
        intro_match = re.search(r"^[\w\s,.:!?-]+\n\s*(\{[\s\S]*\})\s*$", cleaned)
        if intro_match:
            cleaned = intro_match.group(1).strip()

    # 2. If it starts with '{' and ends with '}', clean trailing commas and invalid escapes
    if cleaned.startswith("{") and cleaned.endswith("}"):
        cleaned = remove_trailing_commas(cleaned)
        cleaned = re.sub(r"\\'", "'", cleaned)

    return cleaned


def normalize_enrichment_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Dynamically align dictionary structure to QuestionEnrichment contract without hardcoding.

    1. Distractor keys and structure invariant:
       - If any top-level QuestionEnrichment schema key (e.g. 'difficulty') was accidentally placed
         inside 'distractor_analysis' and is missing from the root object, dynamically move it
         to the root level.
       - If distractor_analysis contains exactly 4 entries, where exactly 3 are valid letters
         among {"A", "B", "C", "D"}, and exactly 1 key is an unrecognized identifier (e.g. choice text),
         dynamically remap the unrecognized key to the remaining missing letter.
         Extra keys beyond 4 (e.g. extra "E" or "Explanation") are intentionally preserved so that
         strict schema validation continues to catch them.

    2. Vocabulary keys invariant:
       - If 'part_of_speech' is missing from a vocabulary item, but the item contains a key matching
         one of the 16 canonical VALID_PARTS_OF_SPEECH (e.g. 'noun': 'training'), remap it to
         'part_of_speech': <matching_pos> and drop the misplaced key.
       - If 'part_of_speech' is already present, drop redundant metadata keys whose value matches
         the part of speech (e.g. 'name': 'noun').
    """
    if not isinstance(data, dict):
        return data

    # 1. Distractor analysis dynamic alignment
    dist_analysis = data.get("distractor_analysis")
    if isinstance(dist_analysis, dict):
        # 1a. Relocate any top-level schema key accidentally nested inside distractor_analysis
        top_level_keys = {
            "grammar_topic",
            "sentence_structure",
            "pattern",
            "vocabulary",
            "explanation",
            "difficulty",
        }
        for k in top_level_keys:
            if k in dist_analysis and k not in data:
                data[k] = dist_analysis.pop(k)

        # 1b. Remap single choice-text key if exactly 3 valid keys present
        valid_keys = {"A", "B", "C", "D"}
        current_keys = set(dist_analysis.keys())
        present_valid = current_keys.intersection(valid_keys)
        invalid_keys = current_keys - valid_keys
        if len(present_valid) == 3 and len(invalid_keys) == 1:
            missing_key = (valid_keys - present_valid).pop()
            wrong_key = invalid_keys.pop()
            val = dist_analysis.pop(wrong_key)
            dist_analysis[missing_key] = val

    # 2. Vocabulary items dynamic alignment
    vocab_list = data.get("vocabulary")
    if isinstance(vocab_list, list):
        for item in vocab_list:
            if not isinstance(item, dict):
                continue
            if "part_of_speech" not in item:
                matching_pos = [
                    k
                    for k in item.keys()
                    if k in VALID_PARTS_OF_SPEECH and k not in ("word", "meaning")
                ]
                if len(matching_pos) == 1:
                    pos_key = matching_pos[0]
                    item["part_of_speech"] = pos_key
                    item.pop(pos_key)
            if "part_of_speech" in item:
                for red_k in ("name", "tag", "type"):
                    if red_k in item and item[red_k] == item["part_of_speech"]:
                        item.pop(red_k)

    return data


def parse_and_validate_enrichment(raw_response: str, sanitize: bool = True) -> QuestionEnrichment:
    """Parse raw LLM response string and validate against QuestionEnrichment schema.

    - Accepts raw_response: str.
    - sanitize: bool = True. When True, sanitizes markdown codeblocks, trailing commas, and invalid escapes.
    - Fast path: tries strict json.loads directly.
    - Resilient path (when sanitize=True): on decode failure, applies sanitization and retries.
    - Preserves underlying causes: json_error and validation_error.
    - Rejects non-dict JSON (e.g. lists, primitives).
    - Validates strictly against existing QuestionEnrichment Pydantic schema.
    - Raises EnrichmentJSONDecodeError on invalid JSON syntax with cause chained.
    - Raises EnrichmentValidationError on schema validation failure with cause chained.
    - Returns validated QuestionEnrichment instance.
    """
    if not isinstance(raw_response, str) or not raw_response.strip():
        raise EnrichmentJSONDecodeError(
            "Raw LLM response is empty or not a string",
            raw_response=raw_response if isinstance(raw_response, str) else None,
        )

    data = None
    first_exc: json.JSONDecodeError | None = None
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        first_exc = exc

    if data is None and sanitize:
        try:
            sanitized = sanitize_json_text(raw_response)
            data = json.loads(sanitized, strict=False)
        except json.JSONDecodeError as exc:
            raise EnrichmentJSONDecodeError(
                f"Failed to decode JSON from LLM response: {exc}",
                raw_response=raw_response,
                json_error=first_exc or exc,
            ) from (first_exc or exc)
    elif data is None and not sanitize:
        raise EnrichmentJSONDecodeError(
            f"Failed to decode JSON from LLM response: {first_exc}",
            raw_response=raw_response,
            json_error=first_exc,
        ) from first_exc

    if not isinstance(data, dict):
        raise EnrichmentValidationError(
            f"Expected JSON object (dict), but received {type(data).__name__}",
            raw_response=raw_response,
            raw_data=data,
        )

    if sanitize:
        data = normalize_enrichment_dict(data)

    try:
        return QuestionEnrichment.model_validate(data)
    except ValidationError as exc:
        raise EnrichmentValidationError(
            f"LLM response failed QuestionEnrichment validation: {exc}",
            raw_response=raw_response,
            raw_data=data,
            validation_error=exc,
        ) from exc
