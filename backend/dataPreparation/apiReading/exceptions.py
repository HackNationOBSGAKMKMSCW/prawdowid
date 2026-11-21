"""Typed, source-aware errors raised by API clients."""


class ApiReadingError(Exception):
    """Base error for failures while fetching data from an API."""

    def __init__(
        self,
        source: str,
        message: str,
        *,
        status_code: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.source = source
        self.status_code = status_code
        self.cause = cause
        super().__init__(f"{source}: {message}")


class ApiConnectionError(ApiReadingError):
    """A connection or other transport error prevented an API request."""


class ApiTimeoutError(ApiReadingError):
    """An API request exceeded its configured timeout."""


class ApiHttpError(ApiReadingError):
    """An API returned an unsuccessful HTTP status."""


class ApiRateLimitError(ApiHttpError):
    """An API rate-limited the caller."""

    def __init__(
        self,
        source: str,
        message: str,
        *,
        retry_after: float | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(source, message, status_code=429, cause=cause)


class ApiAuthError(ApiHttpError):
    """The API rejected the supplied authentication."""


class ApiResponseError(ApiReadingError):
    """An API response could not be decoded or normalized."""


class InvalidFiltersError(ApiReadingError, ValueError):
    """Caller-provided filters are invalid; no request was made."""


class NoSourcesAvailableError(ApiReadingError, ValueError):
    """No registered API can serve any requested category."""
