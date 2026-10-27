"""Port and domain exceptions for Large Language Model (LLM) services conforming to Clean Architecture."""

from typing import Protocol


class LLMService(Protocol):
    """Protocol for LLM service conforming to Clean Architecture.

    Decouples domain workflows and services from concrete cloud or local providers.
    """

    def generate(self, prompt: str) -> str:
        """Send prompt to LLM provider and return raw response string."""
        ...


class LLMServiceError(Exception):
    """Base domain exception for all LLM service failures."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LLMConnectionError(LLMServiceError):
    """Raised when connection to the LLM provider fails (e.g., DNS, socket, network error)."""

    pass


class LLMTimeoutError(LLMServiceError):
    """Raised when a request to the LLM provider times out."""

    pass


class LLMProviderError(LLMServiceError):
    """Raised when the LLM provider returns an API error or invalid response payload."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMAuthenticationError(LLMServiceError):
    """Raised when LLM API credentials (e.g. GEMINI_API_KEY) are missing or invalid."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
