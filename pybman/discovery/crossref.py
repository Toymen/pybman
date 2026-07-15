"""Crossref REST API provider (https://api.crossref.org).

Crossref registers most *publication* DOIs. Its work records can carry
explicit relations to datasets (``is-supplemented-by``), asserted by the
publisher — high precision, but coverage depends on publishers depositing
the links. ORCID→dataset lookups are not meaningful here because Crossref
hosts publications, not datasets.

A ``mailto`` puts requests into Crossref's "polite pool" with better
service; a 404 simply means the DOI is not Crossref-registered (e.g. a
DataCite DOI) and is treated as "no information", not an error.
"""

from __future__ import annotations

from collections.abc import Iterable

import requests

from ._client import Provider
from .identifiers import normalize_doi
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://api.crossref.org"

#: Relation types that (per the Crossref/DataCite vocabulary) indicate
#: supplementary research data attached to a publication.
DATASET_RELATIONS = frozenset({"is-supplemented-by", "has-supplement"})


class CrossrefProvider(Provider):
    name = "crossref"
    supports_doi = True
    supports_orcid = False

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        mailto: str | None = None,
        relations: Iterable[str] = DATASET_RELATIONS,
        session: requests.Session | None = None,
        timeout: float = 15.0,
        retries: int = 2,
    ) -> None:
        super().__init__(session=session, timeout=timeout, retries=retries)
        self._base_url = base_url.rstrip("/")
        self._mailto = mailto
        self._relations = frozenset(relations)

    def datasets_for_doi(self, doi: str, *, limit: int = 100) -> ProviderResult:
        doi = normalize_doi(doi)
        params = {"mailto": self._mailto} if self._mailto else None
        payload = self._get_json(f"{self._base_url}/works/{doi}", params=params, none_on_404=True)
        if payload is None:
            return ProviderResult(provider=self.name, hits=[], total=0)
        relation = payload.get("message", {}).get("relation", {}) or {}
        hits: list[DatasetHit] = []
        for relation_name in sorted(self._relations & relation.keys()):
            for entry in relation[relation_name]:
                if str(entry.get("id-type", "")).lower() != "doi":
                    continue
                pid = normalize_doi(str(entry["id"]))
                hits.append(
                    DatasetHit(
                        provider=self.name,
                        pid=pid,
                        pid_type="doi",
                        relation=relation_name,
                        url=f"https://doi.org/{pid}",
                        raw=entry,
                    )
                )
                if len(hits) >= limit:
                    break
        return ProviderResult(provider=self.name, hits=hits, total=len(hits))
