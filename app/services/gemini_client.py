"""Google Gemini cloud LLM client conforming to Clean Architecture LLMService protocol."""

import os
from pathlib import Path
import re
from typing import Any

from app.services.llm_client import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMService,
    LLMServiceError,
    LLMTimeoutError,
)

try:
    from google import genai
    from google.genai import errors as genai_errors
except ImportError:
    genai = None  # type: ignore
    genai_errors = None  # type: ignore


class GeminiAPIKeyError(LLMAuthenticationError):
    """Raised when GEMINI_API_KEY environment variable is not provided or empty."""

    pass


def sanitize_secret(text: str | None, secret: str | None = None) -> str:
    """Mask sensitive API keys or credential patterns from logs and exception messages."""
    if not text:
        return ""
    masked = str(text)
    if secret:
        s = secret.strip().strip('"').strip("'")
        if s:
            masked = masked.replace(s, "[REDACTED_API_KEY]")
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        env_k = env_key.strip().strip('"').strip("'")
        if env_k:
            masked = masked.replace(env_k, "[REDACTED_API_KEY]")
    masked = re.sub(r"AIza[0-9A-Za-z_\-]+", "[REDACTED_API_KEY]", masked)
    masked = re.sub(
        r"((?:api[_-]?)?key=)[^&\s'\"]+",
        r"\1[REDACTED_API_KEY]",
        masked,
        flags=re.IGNORECASE,
    )
    return masked


def _load_env_key() -> str | None:
    """Load GEMINI_API_KEY from environment or .env file in project root."""
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()

    # Search current directory and parent directory for .env
    for candidate in [Path(".env"), Path(__file__).resolve().parent.parent.parent / ".env"]:
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY=") and not os.getenv("GEMINI_API_KEY"):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                os.environ["GEMINI_API_KEY"] = val
                                return val
            except Exception:
                pass
    return None


class GeminiClient:
    """Production client for Google Gemini Cloud LLM conforming to LLMService protocol."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: Any = None,
    ) -> None:
        self.api_key = api_key or _load_env_key()
        if not self.api_key or not self.api_key.strip():
            raise GeminiAPIKeyError(
                "GEMINI_API_KEY environment variable is not set. "
                "Please set GEMINI_API_KEY in your environment, pass api_key, or place GEMINI_API_KEY in a .env file."
            )

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        env_timeout = os.getenv("GEMINI_TIMEOUT")
        self.timeout = (
            timeout
            if timeout is not None
            else (float(env_timeout) if env_timeout else 120.0)
        )
        self.last_raw_response: str | None = None
        self.last_usage: dict[str, int | None] = {}

        if client is not None:
            self.client = client
        else:
            if genai is None:
                raise ImportError(
                    "The 'google-genai' package is required. Install it using 'pip install google-genai'."
                )
            self.client = genai.Client(api_key=self.api_key.strip())

    def generate(self, prompt: str) -> str:
        """Send prompt to Google Gemini API and return raw textual response."""
        self.last_raw_response = None
        self.last_usage = {}

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
        except (LLMServiceError, GeminiAPIKeyError):
            raise
        except Exception as exc:
            sanitized_msg = sanitize_secret(str(exc), self.api_key)
            exc_type = type(exc).__name__

            # Check for timeout errors
            if "Timeout" in exc_type or "timed out" in sanitized_msg.lower():
                raise LLMTimeoutError(
                    f"Request to Gemini timed out after {self.timeout}s: {sanitized_msg}"
                ) from exc

            # Check for connection / network errors
            if "Connect" in exc_type or "connection" in sanitized_msg.lower() or "network" in sanitized_msg.lower():
                raise LLMConnectionError(
                    f"Failed to connect to Gemini API: {sanitized_msg}"
                ) from exc

            # Check for authentication / authorization errors
            status_code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
            if (
                status_code in (401, 403)
                or "API_KEY_INVALID" in sanitized_msg
                or "PERMISSION_DENIED" in sanitized_msg
                or "UNAUTHENTICATED" in sanitized_msg
            ):
                raise LLMAuthenticationError(
                    f"Gemini API authentication failed: {sanitized_msg}",
                    status_code=status_code,
                ) from exc

            # Generic provider error
            raise LLMProviderError(
                f"Gemini API returned error: {sanitized_msg}",
                status_code=status_code,
            ) from exc

        raw_output = getattr(response, "text", None)
        if raw_output is None:
            raise LLMProviderError(
                f"Invalid response payload from Gemini: missing 'text' attribute in response {response}"
            )

        self.last_raw_response = str(raw_output)

        usage_meta = getattr(response, "usage_metadata", None)
        if usage_meta is not None:
            self.last_usage = {
                "prompt_tokens": getattr(usage_meta, "prompt_token_count", None),
                "candidates_tokens": getattr(usage_meta, "candidates_token_count", None),
                "total_tokens": getattr(usage_meta, "total_token_count", None),
            }

        return self.last_raw_response
