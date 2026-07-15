"""Fan-out aggregator: query every capable provider, tolerate failures."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol, runtime_checkable

import requests

from ._client import make_session
from .b2find import B2FindProvider
from .crossref import CrossrefProvider
from .datacite import DataCiteProvider
from .identifiers import normalize_doi, normalize_orcid
from .models import DiscoveryReport, ProviderResult
from .openaire import OpenAIREProvider
from .orcid import OrcidProvider
from .scholexplorer import ScholexplorerProvider


@runtime_checkable
class SupportsDiscovery(Protocol):
    """Structural interface every provider (or test double) satisfies."""

    name: str
    supports_doi: bool
    supports_orcid: bool
    supports_title: bool

    def datasets_for_doi(self, doi: str, *, limit: int = 100) -> ProviderResult: ...

    def datasets_for_orcid(self, orcid: str, *, limit: int = 100) -> ProviderResult: ...

    def datasets_for_title(
        self,
        title: str,
        *,
        authors: tuple[str, ...] = (),
        year: int | None = None,
        limit: int = 100,
    ) -> ProviderResult: ...


class DataDiscovery:
    """Answer "do research data exist for this DOI / ORCID?" across providers.

    Example:
        >>> from pybman.discovery import DataDiscovery
        >>> report = DataDiscovery().for_doi("10.1038/s41586-020-2649-2")
        >>> report.found
        True
        >>> [hit.pid for hit in report.hits]  # doctest: +SKIP

    One provider failing (rate limit, outage) never fails the lookup; the
    failure is recorded on that provider's :class:`ProviderResult`.
    """

    def __init__(
        self,
        providers: Sequence[SupportsDiscovery] | None = None,
        *,
        timeout: float = 15.0,
        retries: int = 2,
        openaire_token: str | None = None,
        crossref_mailto: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if providers is None:
            shared = session if session is not None else make_session(retries)
            common: dict[str, Any] = {"session": shared, "timeout": timeout}
            providers = [
                DataCiteProvider(**common),
                OpenAIREProvider(access_token=openaire_token, **common),
                ScholexplorerProvider(**common),
                B2FindProvider(**common),
                CrossrefProvider(mailto=crossref_mailto, **common),
                OrcidProvider(**common),
            ]
        self.providers: list[SupportsDiscovery] = list(providers)

    def for_doi(self, doi: str, *, limit: int = 100) -> DiscoveryReport:
        """Query all DOI-capable providers for datasets related to ``doi``."""
        query = normalize_doi(doi)
        results = [
            self._run(provider, provider.datasets_for_doi, query, limit)
            for provider in self.providers
            if getattr(provider, "supports_doi", False)
        ]
        return DiscoveryReport(query=query, query_type="doi", results=results)

    def for_orcid(self, orcid: str, *, limit: int = 100) -> DiscoveryReport:
        """Query all ORCID-capable providers for datasets by ``orcid``."""
        query = normalize_orcid(orcid)
        results = [
            self._run(provider, provider.datasets_for_orcid, query, limit)
            for provider in self.providers
            if getattr(provider, "supports_orcid", False)
        ]
        return DiscoveryReport(query=query, query_type="orcid", results=results)

    def for_title(
        self,
        title: str,
        *,
        authors: Sequence[str] = (),
        year: int | None = None,
        limit: int = 100,
    ) -> DiscoveryReport:
        """Find datasets by publication title with provider-side evidence checks.

        This fallback is useful for publications without a DOI and for dataset
        records that name the publication but omit a formal DOI relation.
        Providers must validate candidates before returning them.
        """
        query = " ".join(title.split())
        if not query:
            raise ValueError("publication title must not be empty")
        author_tuple = tuple(author.strip() for author in authors if author.strip())
        results = [
            self._run(
                provider,
                provider.datasets_for_title,
                query,
                limit,
                authors=author_tuple,
                year=year,
            )
            for provider in self.providers
            if getattr(provider, "supports_title", False)
        ]
        return DiscoveryReport(query=query, query_type="title", results=results)

    @staticmethod
    def _run(
        provider: SupportsDiscovery,
        lookup: Callable[..., ProviderResult],
        query: str,
        limit: int,
        **kwargs: Any,
    ) -> ProviderResult:
        try:
            return lookup(query, limit=limit, **kwargs)
        except Exception as exc:  # one provider must not sink the rest
            return ProviderResult(provider=provider.name, hits=[], error=str(exc))
