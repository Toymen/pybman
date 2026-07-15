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
from .matching import has_surname_overlap, title_match_score, title_tokens
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://api.datacite.org"


class DataCiteProvider(Provider):
    name = "datacite"
    supports_doi = True
    supports_orcid = True
    supports_title = True

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

    def datasets_for_title(
        self,
        title: str,
        *,
        authors: tuple[str, ...] = (),
        year: int | None = None,
        limit: int = 100,
    ) -> ProviderResult:
        """Search dataset titles and retain only strongly verified matches.

        Data repositories commonly use titles such as ``Replication data for
        <publication title>`` without depositing the publication DOI.  The API
        query supplies recall; local title and creator checks supply precision.
        ``year`` is kept in the public signature for future ranking but is not a
        hard filter because replication packages can precede or follow papers.
        """
        del year
        title = " ".join(title.split())
        if not title:
            raise ValueError("publication title must not be empty")
        escaped_title = title.replace('"', '\\"')
        payload = self._get_json(
            f"{self._base_url}/dois",
            params={
                "query": f'titles.title:"{escaped_title}"',
                "resource-type-id": "dataset",
                "page[size]": limit,
                "sort": "relevance",
            },
        )
        hits: list[DatasetHit] = []
        for record in payload.get("data", []):
            attributes = record.get("attributes", {})
            titles = attributes.get("titles") or []
            candidate = str(titles[0].get("title") or "") if titles else ""
            score = title_match_score(title, candidate)
            creator_names = [
                str(creator.get("familyName") or creator.get("name") or "")
                for creator in attributes.get("creators") or []
            ]
            author_match = has_surname_overlap(authors, creator_names)
            enough_title_evidence = score >= 0.9 and len(title_tokens(title)) >= 4
            if not enough_title_evidence or (authors and not author_match):
                continue
            raw = dict(record)
            raw["_match"] = {"title_score": score, "author_overlap": author_match}
            hits.append(self._hit(raw, related_to=None, relation="verified-title-author-match"))
        return ProviderResult(provider=self.name, hits=hits, total=len(hits))

    def _search(self, query: str, *, limit: int, related_to: str | None = None) -> ProviderResult:
        payload = self._get_json(
            f"{self._base_url}/dois",
            params={"query": query, "resource-type-id": "dataset", "page[size]": limit},
        )
        hits = [self._hit(record, related_to) for record in payload.get("data", [])]
        total = payload.get("meta", {}).get("total")
        return ProviderResult(provider=self.name, hits=hits, total=total)

    def _hit(
        self,
        record: dict[str, Any],
        related_to: str | None,
        relation: str | None = None,
    ) -> DatasetHit:
        attributes = record.get("attributes", {})
        titles = attributes.get("titles") or []
        publisher = attributes.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("name")
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
