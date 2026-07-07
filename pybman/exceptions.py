"""Exception hierarchy for pybman.

Every error raised by the library derives from :class:`PubManError`, so
callers can catch a single type. HTTP-level failures are mapped onto more
specific subclasses carrying the response for inspection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "BadRequestError",
    "NotFoundError",
    "PubManError",
    "PubManHTTPError",
    "ServerError",
]


class PubManError(Exception):
    """Base class for all pybman errors."""


class PubManHTTPError(PubManError):
    """An HTTP request to the PubMan API failed.

    Attributes:
        status_code: HTTP status code of the failed response.
        response: The full :class:`requests.Response`, if available.
    """

    def __init__(self, message: str, response: requests.Response | None = None) -> None:
        super().__init__(message)
        self.response = response
        self.status_code: int | None = response.status_code if response is not None else None


class BadRequestError(PubManHTTPError):
    """The request was rejected as invalid (HTTP 400)."""


class AuthenticationError(PubManHTTPError):
    """Authentication failed or is required (HTTP 401, or login failure)."""


class AuthorizationError(PubManHTTPError):
    """The authenticated user lacks permission for the operation (HTTP 403)."""


class NotFoundError(PubManHTTPError):
    """The requested resource does not exist (HTTP 404)."""


class ServerError(PubManHTTPError):
    """The PubMan service reported an internal error (HTTP 5xx)."""


def error_for_response(response: requests.Response) -> PubManHTTPError:
    """Build the matching exception for a non-2xx *response*."""
    status = response.status_code
    detail = _extract_detail(response)
    message = f"{response.request.method} {response.url} failed with HTTP {status}"
    if detail:
        message = f"{message}: {detail}"
    cls: type[PubManHTTPError]
    if status == 400:
        cls = BadRequestError
    elif status == 401:
        cls = AuthenticationError
    elif status == 403:
        cls = AuthorizationError
    elif status == 404:
        cls = NotFoundError
    elif status >= 500:
        cls = ServerError
    else:
        cls = PubManHTTPError
    return cls(message, response=response)


def _extract_detail(response: requests.Response) -> str:
    """Pull a short human-readable error detail out of an error response."""
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:500]
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
    return ""
