import os
from unittest.mock import MagicMock
import pytest

from app.services.gemini_client import (
    GeminiAPIKeyError,
    GeminiClient,
    sanitize_secret,
)
from app.services.llm_client import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMServiceError,
    LLMTimeoutError,
)


def test_gemini_client_missing_key_raises_auth_error(monkeypatch):
    """Missing GEMINI_API_KEY raises GeminiAPIKeyError subclassing LLMAuthenticationError."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.services.gemini_client._load_env_key", lambda: None)

    with pytest.raises(GeminiAPIKeyError) as exc_info:
        GeminiClient(api_key=None)

    assert "GEMINI_API_KEY environment variable is not set" in str(exc_info.value)
    assert issubclass(GeminiAPIKeyError, LLMAuthenticationError)
    assert issubclass(LLMAuthenticationError, LLMServiceError)


def test_gemini_client_init_with_custom_params():
    """Client initializes with explicit api_key, model, and timeout."""
    mock_sdk_client = MagicMock()
    client = GeminiClient(
        api_key="test-api-key-12345",
        model="gemini-3.5-flash-lite",
        timeout=45.0,
        client=mock_sdk_client,
    )

    assert client.api_key == "test-api-key-12345"
    assert client.model == "gemini-3.5-flash-lite"
    assert client.timeout == 45.0
    assert client.client is mock_sdk_client


def test_gemini_client_successful_generate():
    """Successful generate_content call returns text string and tracks metadata."""
    mock_sdk_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '{"grammar_topic": "Subject-Verb Agreement"}'
    mock_response.usage_metadata.prompt_token_count = 120
    mock_response.usage_metadata.candidates_token_count = 85
    mock_response.usage_metadata.total_token_count = 205
    mock_sdk_client.models.generate_content.return_value = mock_response

    client = GeminiClient(
        api_key="test-key",
        model="gemini-3.5-flash-lite",
        client=mock_sdk_client,
    )

    result = client.generate("Analyze this question")

    mock_sdk_client.models.generate_content.assert_called_once_with(
        model="gemini-3.5-flash-lite",
        contents="Analyze this question",
    )
    assert result == '{"grammar_topic": "Subject-Verb Agreement"}'
    assert client.last_raw_response == result
    assert client.last_usage == {
        "prompt_tokens": 120,
        "candidates_tokens": 85,
        "total_tokens": 205,
    }


def test_gemini_client_connection_error_mapping():
    """Network connection failure maps to LLMConnectionError."""
    mock_sdk_client = MagicMock()
    mock_sdk_client.models.generate_content.side_effect = ConnectionError("Failed to establish a new connection")

    client = GeminiClient(
        api_key="test-key",
        client=mock_sdk_client,
    )

    with pytest.raises(LLMConnectionError) as exc_info:
        client.generate("Test prompt")

    assert "Failed to connect to Gemini API" in str(exc_info.value)
    assert issubclass(LLMConnectionError, LLMServiceError)


def test_gemini_client_timeout_error_mapping():
    """Timeout exception maps to LLMTimeoutError."""
    mock_sdk_client = MagicMock()
    mock_sdk_client.models.generate_content.side_effect = TimeoutError("The read operation timed out")

    client = GeminiClient(
        api_key="test-key",
        timeout=30.0,
        client=mock_sdk_client,
    )

    with pytest.raises(LLMTimeoutError) as exc_info:
        client.generate("Test prompt")

    assert "Request to Gemini timed out after 30.0s" in str(exc_info.value)
    assert issubclass(LLMTimeoutError, LLMServiceError)


def test_gemini_client_auth_error_mapping():
    """HTTP 401 or API_KEY_INVALID maps to LLMAuthenticationError."""
    mock_sdk_client = MagicMock()
    mock_error = Exception("API_KEY_INVALID: The provided API key is expired or invalid")
    mock_error.code = 401
    mock_sdk_client.models.generate_content.side_effect = mock_error

    client = GeminiClient(
        api_key="test-key",
        client=mock_sdk_client,
    )

    with pytest.raises(LLMAuthenticationError) as exc_info:
        client.generate("Test prompt")

    assert "Gemini API authentication failed" in str(exc_info.value)


def test_gemini_client_provider_error_mapping():
    """HTTP 500 or generic API error maps to LLMProviderError."""
    mock_sdk_client = MagicMock()
    mock_error = Exception("Internal server error from Gemini backend")
    mock_error.code = 500
    mock_sdk_client.models.generate_content.side_effect = mock_error

    client = GeminiClient(
        api_key="test-key",
        client=mock_sdk_client,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        client.generate("Test prompt")

    assert "Gemini API returned error" in str(exc_info.value)
    assert exc_info.value.status_code == 500


def test_gemini_client_missing_text_raises_provider_error():
    """Response payload missing text attribute raises LLMProviderError."""
    mock_sdk_client = MagicMock()
    mock_response = MagicMock(spec=[])  # no 'text' attribute
    mock_sdk_client.models.generate_content.return_value = mock_response

    client = GeminiClient(
        api_key="test-key",
        client=mock_sdk_client,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        client.generate("Test prompt")

    assert "Invalid response payload from Gemini" in str(exc_info.value)


def test_sanitize_secret_masks_api_key():
    """sanitize_secret masks secret value and common Google API key patterns."""
    raw = "Failed with key AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6 and secret-key-xyz"
    masked = sanitize_secret(raw, secret="secret-key-xyz")

    assert "secret-key-xyz" not in masked
    assert "AIzaSy" not in masked
    assert "[REDACTED_API_KEY]" in masked
