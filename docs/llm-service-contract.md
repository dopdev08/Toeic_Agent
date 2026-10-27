# LLM Service Contract

## 1. Document Purpose & Scope

This document defines the **minimal architectural boundary** between the TOEIC Agent application and the underlying Large Language Model (LLM) provider.

- **Architecture:** Clean Architecture / Hexagonal Architecture (Ports and Adapters)
- **Port:** `LLMService` protocol (`app/services/llm_client.py`)
- **Adapter:** `GeminiClient` (`app/services/gemini_client.py`) using Google Gemini Cloud AI
- **Upstream References:**
  - [docs/ai-enrichment-contract.md](file:///d:/project/Toeic_Agent/docs/ai-enrichment-contract.md)
  - [docs/ai-enrichment-prompt.md](file:///d:/project/Toeic_Agent/docs/ai-enrichment-prompt.md)
  - [app/schemas/enrichment.py](file:///d:/project/Toeic_Agent/app/schemas/enrichment.py)

The objective is to establish a decoupled boundary so the application can invoke an LLM without binding business logic, validation rules, or persistence logic to provider-specific SDK communication.

---

## 2. Minimal Conceptual Interface

The LLM Service exposes a single, minimal abstraction:

```text
Input:  prompt (string)
Output: raw_response (string)
```

### Conceptual Signature:
```python
class LLMService(Protocol):
    def generate(self, prompt: str) -> str:
        ...
```

- **Input:** A fully formatted prompt string constructed by the application (incorporating system prompt, question context, and output instructions).
- **Output:** The exact, raw string payload returned by the LLM provider, untouched and unparsed.

---

## 3. Architecture & Pipeline Boundary

The LLM Service acts strictly as a transport and invocation bridge:

```text
Application Layer
    │
    ▼ (prompt: str)
LLM Service Boundary (LLMService Protocol)
    │
    ▼ (API invocation via google-genai SDK)
LLM Provider (Google Gemini Cloud API)
    │
    ▼ (Provider text response)
LLM Service Boundary
    │
    ▼ (raw_response: str)
Application Layer (Pydantic Validation & Persistence)
```

The LLM Service knows nothing about TOEIC, exam structures, JSON parsing, or database tables.

---

## 4. Core Responsibilities

The LLM Service is **strictly responsible** for:

1. **Receiving Prompt:** Accepting the rendered prompt string from the application caller.
2. **Provider Dispatch:** Forwarding the prompt to the configured LLM provider endpoint.
3. **Response Reception:** Receiving the textual response stream/payload from the provider.
4. **Returning Raw Output:** Delivering the raw response string directly back to the application layer.
5. **Secret Sanitization:** Ensuring API keys and credentials are never exposed in logs or exception messages.

---

## 5. Explicit Non-Responsibilities

To preserve strict separation of concerns, the LLM Service **must never**:

- **Parse JSON:** It does not call `json.loads()` or transform strings into dictionaries.
- **Perform Pydantic Validation:** Schema validation against `QuestionEnrichment` belongs solely to the application layer.
- **Access Database:** No queries, inserts, transactions, or sessions (`toeic_agent.db`).
- **Execute TOEIC Business Logic:** It has no concept of Parts 1–7, correct answers, grammar topics, or difficulty scoring.
- **Construct Prompts:** Prompts are built and rendered by the application or orchestration layer before invoking the service.
- **Implement Business Retry Logic:** Deciding when to re-prompt or fallback due to malformed output is an application/agent-level concern.

---

## 6. Error Boundary & Failure Modes

Domain exceptions are defined independently of provider SDKs in `app/services/llm_client.py`:

| Domain Exception | Description | HTTP Status Code Mapping |
|---|---|---|
| **`LLMAuthenticationError`** | API key is missing, expired, or rejected (e.g., HTTP 401/403). | HTTP 503 Service Unavailable |
| **`LLMConnectionError`** | Provider endpoint is unreachable or network connection drops. | HTTP 503 Service Unavailable |
| **`LLMTimeoutError`** | Provider takes longer than configured timeout threshold. | HTTP 504 Gateway Timeout |
| **`LLMProviderError`** | Provider returns HTTP error, quota error, or malformed response. | HTTP 502 Bad Gateway |

---

## 7. Design Principles

- **Clean Architecture Compliant:** The application layer depends on the `LLMService` protocol and domain exceptions, not on concrete Google GenAI classes.
- **Stateless:** The service does not store conversation history, previous requests, or cached responses.
- **Decoupled from Schema:** The service interface remains `generate(prompt: str) -> str` regardless of how `QuestionEnrichment` evolves.
- **Swappable Implementation:** The port allows drop-in mock implementations for testing or alternate cloud providers without altering domain code.
