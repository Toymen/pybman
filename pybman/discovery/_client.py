"""Minimal HTTP plumbing shared by the discovery providers.

Deliberately independent from :mod:`pybman._http`: that transport is tied to
one PubMan instance (login, ``/rest`` base URL); discovery talks to several
unrelated public APIs and only ever needs anonymous JSON GETs.
"""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pybman import __about__

from .models import ProviderResult

_RETRY_STATUSES = (429, 500, 502, 503, 504)
USER_AGENT = f"pybman-discovery/{__about__.__version__} (https://github.com/Toymen/pybman)"


def safe_get(mapping: Any, key: str, default: dict[str, Any]) -> dict[str, Any]:
    """``mapping.get(key, default)`` that also coalesces an explicit ``null``.

    A plain ``dict.get(key, default)`` only falls back to ``default`` when
    ``key`` is absent; if the API returns ``{"key": null}`` (a legal JSON
    value), ``.get`` happily returns ``None`` and the next ``.get(...)`` on
    it raises ``AttributeError``. Several providers hit exactly this when an
    upstream API includes an empty envelope field instead of omitting it.
    """
    value = mapping.get(key) if isinstance(mapping, dict) else None
    return value if isinstance(value, dict) else default


class DiscoveryError(Exception):
    """A discovery provider request failed (network, HTTP or bad payload)."""


def year_from_date_str(date: str | None) -> int | None:
    """Extract a leading 4-digit year from a date-ish string, or ``None``.

    Handles ``"2021"``, ``"2021-05-01"``, ``"2021-05-01T00:00:00Z"`` and
    similar ISO-ish prefixes uniformly, which several providers otherwise
    reimplement with ``date[:4].isdigit()``.
    """
    prefix = (date or "")[:4]
    return int(prefix) if prefix.isdigit() else None


def make_session(retries: int = 2) -> requests.Session:
    """A session with a polite User-Agent and bounded GET retries."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    retry = Retry(
        total=retries,
        backoff_factor=0.5,
        status_forcelist=_RETRY_STATUSES,
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class Provider:
    """Base class for discovery providers.

    Subclasses set :attr:`name`, the ``supports_*`` capability flags and
    override the lookups they support.
    """

    name: str = "provider"
    supports_doi: bool = False
    supports_orcid: bool = False
    supports_title: bool = False

    #: Overridden by subclasses; used when ``base_url`` isn't passed in.
    default_base_url: str = ""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        session: requests.Session | None = None,
        timeout: float = 15.0,
        retries: int = 2,
    ) -> None:
        self._session = session if session is not None else make_session(retries)
        self._timeout = timeout
        self._base_url = (base_url if base_url is not None else self.default_base_url).rstrip("/")

    def datasets_for_doi(self, doi: str, *, limit: int = 100) -> ProviderResult:
        """Datasets related to the publication identified by ``doi``."""
        raise NotImplementedError(f"{self.name} does not support DOI lookups")

    def datasets_for_orcid(self, orcid: str, *, limit: int = 100) -> ProviderResult:
        """Datasets created by the researcher identified by ``orcid``."""
        raise NotImplementedError(f"{self.name} does not support ORCID lookups")

    def datasets_for_title(
        self,
        title: str,
        *,
        authors: tuple[str, ...] = (),
        year: int | None = None,
        limit: int = 100,
    ) -> ProviderResult:
        """Datasets whose metadata can be verified against a publication title."""
        raise NotImplementedError(f"{self.name} does not support title lookups")

    # -- shared plumbing ---------------------------------------------------

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        none_on_404: bool = False,
    ) -> Any:
        """GET ``url`` and decode JSON, mapping failures to DiscoveryError."""
        try:
            response = self._session.get(url, params=params, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise DiscoveryError(f"{self.name}: GET {url} failed: {exc}") from exc
        if none_on_404 and response.status_code == 404:
            return None
        if not response.ok:
            raise DiscoveryError(
                f"{self.name}: GET {response.url} returned HTTP {response.status_code}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise DiscoveryError(f"{self.name}: GET {response.url} returned invalid JSON") from exc

    def _get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        none_on_404: bool = False,
    ) -> str | None:
        """GET text content with the same failure semantics as :meth:`_get_json`."""
        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
        except requests.RequestException as exc:
            raise DiscoveryError(f"{self.name}: GET {url} failed: {exc}") from exc
        if none_on_404 and response.status_code == 404:
            return None
        if not response.ok:
            raise DiscoveryError(
                f"{self.name}: GET {response.url} returned HTTP {response.status_code}"
            )
        return response.text
