"""HTTP transport for the PubMan REST API.

Wraps a :class:`requests.Session` with base-URL handling, sensible timeouts,
bounded retries for idempotent requests, token authentication and mapping of
HTTP errors onto :mod:`pybman.exceptions`.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pybman import __about__
from pybman.exceptions import AuthenticationError, PubManHTTPError, error_for_response
from pybman.models import UserAccount

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://pure.mpg.de"

#: Statuses worth an automatic retry (only ever applied to GET/HEAD).
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class Transport:
    """A configured HTTP session against one PubMan instance.

    Args:
        base_url: Root of the PubMan instance (default ``https://pure.mpg.de``).
            The REST API lives under ``{base_url}/rest``, the CoNE authority
            service under ``{base_url}/cone``.
        credentials: Optional ``(username, password)`` used for lazy login
            when an authenticated endpoint is called.
        token: A pre-existing authorization token (e.g. from a previous
            login; tokens are valid for 24 hours).
        timeout: Default per-request timeout in seconds.
        retries: Number of automatic retries for idempotent (GET/HEAD)
            requests on connection errors and transient server errors.
        session: Bring-your-own :class:`requests.Session` (proxies, extra
            CA bundles, ...). Retry adapters are still mounted onto it.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        credentials: tuple[str, str] | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rest_url = f"{self.base_url}/rest"
        self.cone_url = f"{self.base_url}/cone"
        self.timeout = timeout
        self.token = token
        self._credentials = credentials

        self._session = session or requests.Session()
        retry = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            status_forcelist=_RETRY_STATUSES,
            allowed_methods=frozenset({"GET", "HEAD"}),
            backoff_factor=0.5,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.setdefault("User-Agent", f"pybman/{__about__.__version__}")
        self._session.headers.setdefault("Accept", "application/json")

    # -- authentication ------------------------------------------------

    @property
    def has_credentials(self) -> bool:
        return self._credentials is not None

    @property
    def is_authenticated(self) -> bool:
        return self.token is not None

    def login(self, username: str | None = None, password: str | None = None) -> str:
        """POST /login — obtain an authorization token (valid 24 hours)."""
        if username is not None and password is not None:
            self._credentials = (username, password)
        if self._credentials is None:
            raise AuthenticationError("no credentials available for login")
        user, secret = self._credentials
        response = self._session.post(
            f"{self.rest_url}/login",
            data=f"{user}:{secret}".encode(),
            headers={"Content-Type": "text/plain"},
            timeout=self.timeout,
        )
        token = response.headers.get("Token")
        if not response.ok or not token:
            raise AuthenticationError(
                f"login failed with HTTP {response.status_code}", response=response
            )
        self.token = token
        logger.debug("logged in to %s as %s", self.base_url, user)
        return token

    def logout(self) -> None:
        """GET /logout — invalidate the current token. Never raises."""
        if not self.token:
            return
        try:
            self.request("GET", "/logout", authenticated=True)
        except Exception:
            logger.debug("logout request failed", exc_info=True)
        finally:
            self.token = None

    def whoami(self) -> UserAccount:
        """GET /login/who — the account behind the current token."""
        payload = self.request_json("GET", "/login/who", authenticated=True)
        return UserAccount.from_api(payload)

    def _ensure_token(self) -> str:
        if self.token is None:
            self.login()
        if self.token is None:
            # login() either raises or sets self.token; this is defensive
            # against a future bug in that contract, not a normal path.
            raise AuthenticationError("login succeeded but no token was set")
        return self.token

    # -- generic requests ------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: bytes | str | None = None,
        headers: dict[str, str] | None = None,
        authenticated: bool = False,
        stream: bool = False,
        timeout: float | None = None,
    ) -> requests.Response:
        """Send a request to the REST API and return the raw response.

        ``path`` is joined to the REST root unless it is already absolute.
        When ``authenticated`` is true, a token is required (a lazy login is
        performed if credentials are available). Otherwise a token is still
        sent when present — anonymous and authenticated callers legitimately
        see different data on several read endpoints.

        Raises a subclass of :class:`~pybman.exceptions.PubManHTTPError`
        for non-2xx responses. If an authenticated request bounces with 401
        and credentials are on hand, one re-login and retry is attempted
        (tokens expire after 24 hours).
        """
        url = path if path.startswith(("http://", "https://")) else self.rest_url + path
        request_headers = dict(headers or {})
        if authenticated:
            request_headers["Authorization"] = self._ensure_token()
        elif self.token:
            request_headers["Authorization"] = self.token

        clean_params = {k: v for k, v in (params or {}).items() if v is not None} or None
        effective_timeout = timeout if timeout is not None else self.timeout

        def _send() -> requests.Response:
            return self._session.request(
                method,
                url,
                params=clean_params,
                json=json,
                data=data,
                headers=request_headers,
                stream=stream,
                timeout=effective_timeout,
            )

        response = _send()
        if response.status_code == 401 and self.token and self.has_credentials:
            logger.debug("token rejected, re-authenticating once")
            self.token = None
            request_headers["Authorization"] = self._ensure_token()
            response = _send()

        if not response.ok:
            raise error_for_response(response)
        return response

    def request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Like :meth:`request`, but parse and return the JSON body."""
        response = self.request(method, path, **kwargs)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            # a 2xx response with a non-JSON body (e.g. an HTML error page
            # from a misbehaving reverse proxy) shouldn't surface as a raw
            # json.JSONDecodeError outside the library's exception hierarchy
            raise PubManHTTPError(
                f"{method} {response.url} returned a non-JSON body", response=response
            ) from exc

    def close(self) -> None:
        self._session.close()
