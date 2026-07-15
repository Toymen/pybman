"""Result models shared by all discovery providers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DatasetHit:
    """One dataset found by a provider.

    Attributes:
        provider: Name of the provider that produced the hit (``"datacite"``,
            ``"openaire"``, ...).
        pid: Persistent identifier of the dataset, usually a DOI.
        pid_type: Scheme of ``pid`` (``"doi"``, ``"openaire"``, ``"ckan"``).
        title: Dataset title, if the provider exposes one.
        publisher: Publishing repository (Zenodo, PANGAEA, ...).
        year: Publication year.
        relation: Relation of the dataset to the queried work, if the lookup
            was DOI-based and the provider reports it (e.g. ``IsSupplementTo``).
        url: Landing page or resolver URL.
        raw: The provider's raw record for downstream inspection. Excluded
            from equality so hits from identical metadata compare equal.
    """

    provider: str
    pid: str
    pid_type: str = "doi"
    title: str | None = None
    publisher: str | None = None
    year: int | None = None
    relation: str | None = None
    url: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass
class ProviderResult:
    """Outcome of querying a single provider.

    ``error`` is set (and ``hits`` empty) when the provider failed; the
    aggregator never lets one broken service break the whole lookup.
    """

    provider: str
    hits: list[DatasetHit] = field(default_factory=list)
    total: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class DiscoveryReport:
    """Aggregated answer to "are there research data for this DOI/ORCID?"."""

    query: str
    query_type: str  # "doi" or "orcid"
    results: list[ProviderResult] = field(default_factory=list)

    @property
    def hits(self) -> list[DatasetHit]:
        """All hits across providers, deduplicated by identifier."""
        seen: set[tuple[str, str]] = set()
        unique: list[DatasetHit] = []
        for result in self.results:
            for hit in result.hits:
                key = (hit.pid_type, hit.pid.lower())
                if key not in seen:
                    seen.add(key)
                    unique.append(hit)
        return unique

    @property
    def found(self) -> bool:
        """True if at least one provider reported a dataset."""
        return any(result.hits for result in self.results)

    def summary(self) -> str:
        """One-line, human-readable per-provider tally."""
        parts = [
            f"{r.provider}: {len(r.hits)}" if r.ok else f"{r.provider}: error ({r.error})"
            for r in self.results
        ]
        return "; ".join(parts)
