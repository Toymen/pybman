"""DataCite REST API provider (https://api.datacite.org).

DataCite mints most research-data DOIs, which makes it the primary source
for both lookup directions:

* DOI → datasets: find dataset DOIs whose ``relatedIdentifiers`` point at
  the publication DOI.
* ORCID → datasets: find dataset DOIs whose creators carry the ORCID as a
  name identifier.

The API is anonymous and rate-limited by IP; see
https://support.datacite.org/docs/api-queries for the query syntax.
"""

from __future__ import annotations

from typing import Any

import requests

from ._client import Provider
from .identifiers import normalize_doi, normalize_orcid
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://api.datacite.org"


class DataCiteProvider(Provider):
    name = "datacite"
    supports_doi = True
    supports_orcid = True

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        session: requests.Session | None = None,
        timeout: float = 15.0,
        retries: int = 2,
    ) -> None:
        super().__init__(session=session, timeout=timeout, retries=retries)
        self._base_url = base_url.rstrip("/")

    def datasets_for_doi(self, doi: str, *, limit: int = 100) -> ProviderResult:
        doi = normalize_doi(doi)
        query = f'relatedIdentifiers.relatedIdentifier:"{doi}"'
        return self._search(query, limit=limit, related_to=doi)

    def datasets_for_orcid(self, orcid: str, *, limit: int = 100) -> ProviderResult:
        orcid = normalize_orcid(orcid)
        # Matches both bare iDs and https://orcid.org/... name identifiers.
        query = f"creators.nameIdentifiers.nameIdentifier:*{orcid}*"
        return self._search(query, limit=limit)

    def _search(self, query: str, *, limit: int, related_to: str | None = None) -> ProviderResult:
        payload = self._get_json(
            f"{self._base_url}/dois",
            params={"query": query, "resource-type-id": "dataset", "page[size]": limit},
        )
        hits = [self._hit(record, related_to) for record in payload.get("data", [])]
        total = payload.get("meta", {}).get("total")
        return ProviderResult(provider=self.name, hits=hits, total=total)

    def _hit(self, record: dict[str, Any], related_to: str | None) -> DatasetHit:
        attributes = record.get("attributes", {})
        titles = attributes.get("titles") or []
        publisher = attributes.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("name")
        relation = None
        if related_to is not None:
            for related in attributes.get("relatedIdentifiers") or []:
                identifier = str(related.get("relatedIdentifier", ""))
                if identifier.lower() == related_to:
                    relation = related.get("relationType")
                    break
        return DatasetHit(
            provider=self.name,
            pid=attributes.get("doi") or record.get("id", ""),
            pid_type="doi",
            title=titles[0].get("title") if titles else None,
            publisher=publisher,
            year=attributes.get("publicationYear"),
            relation=relation,
            url=attributes.get("url"),
            raw=record,
        )
