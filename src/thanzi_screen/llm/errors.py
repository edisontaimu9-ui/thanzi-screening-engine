"""Error types for the local LLM client.

Every message is a fixed string. Nothing here ever carries a prompt, a reply, a header or a URL, so an error that is
logged or returned over HTTP cannot leak what was sent to the model.
"""
from __future__ import annotations


class LLMError(Exception):
    """Base class. `code` is stable and safe to return to callers. `retryable` says if a retry could help."""
    code = "llm_error"
    retryable = False
    default_message = "The language model request failed."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class LLMConfigError(LLMError, ValueError):
    code = "llm_config"
    default_message = "The language model configuration is not valid."


class LLMBadRequestError(LLMError):
    """Rejected by this client before anything was sent (for example, a prompt that is too long)."""
    code = "llm_bad_request"
    default_message = "The request was rejected before it was sent to the model."


class LLMConnectionError(LLMError):
    code = "llm_unreachable"
    retryable = True
    default_message = "The model server could not be reached."


class LLMTimeoutError(LLMError):
    """Not retried: a retry doubles the load on hardware that is already slow."""
    code = "llm_timeout"
    default_message = "The model server did not answer in time."


class LLMBusyError(LLMError):
    """All inference slots are in use and the queue wait ran out."""
    code = "llm_busy"
    default_message = "The model is busy. Try again shortly."


class LLMAuthError(LLMError):
    code = "llm_auth"
    default_message = "The model server refused the credentials."


class LLMModelNotFoundError(LLMError):
    code = "llm_model_not_found"
    default_message = "The model or the endpoint was not found on the server."


class LLMServerError(LLMError):
    """The server answered with an error status. Only 429, 502, 503 and 504 are worth a retry (500 is usually
    out-of-memory on small machines, and retrying it only makes things worse)."""
    code = "llm_server_error"
    default_message = "The model server returned an error."

    def __init__(self, status_code: int, message: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = status_code in (429, 502, 503, 504)


class LLMRejectedError(LLMError):
    """The server answered 4xx for the request itself (other than auth, not-found and rate limit)."""
    code = "llm_rejected"
    default_message = "The model server rejected the request."

    def __init__(self, status_code: int, message: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMResponseError(LLMError):
    """The reply was malformed, unexpected or larger than the configured limit."""
    code = "llm_bad_response"
    default_message = "The model server sent a reply that could not be used."
