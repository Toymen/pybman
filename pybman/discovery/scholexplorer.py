"""ScholeXplorer / Scholix provider (https://api.scholexplorer.openaire.eu).

ScholeXplorer serves Scholix links — the publication↔dataset link graph fed
by Crossref, DataCite and OpenAIRE. It is purpose-built for exactly this
question: "which datasets are linked to publication DOI X?". It has no
notion of authors, so ORCID lookups are unsupported.

Both link directions are queried (publication as ``sourcePid`` and as
``targetPid``) because links are not guaranteed to be materialized both
ways; results are merged and deduplicated.
"""

from __future__ import annotations

from typing import Any

import requests

from ._client import Provider
from .identifiers import normalize_doi
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://api.scholexplorer.openaire.eu/v3"
_MAX_PAGES = 50


def _get(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """First present key wins — the Scholix payload mixes key casings."""
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


class ScholexplorerProvider(Provider):
    name = "scholexplorer"
    supports_doi = True
    supports_orcid = False

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
        hits: list[DatasetHit] = []
        seen: set[str] = set()
        total = 0
        for direction, entity_key in (("sourcePid", "target"), ("targetPid", "source")):
            page = 0
            while True:
                payload = self._get_json(
                    f"{self._base_url}/Links", params={direction: doi, "page": page}
                )
                if page == 0:
                    total += int(payload.get("totalLinks") or 0)
                for link in payload.get("result", []):
                    hit = self._hit(link, entity_key)
                    if hit is not None and hit.pid.lower() not in seen:
                        seen.add(hit.pid.lower())
                        hits.append(hit)
                    if len(hits) >= limit:
                        break
                if len(hits) >= limit:
                    break
                page += 1
                total_pages = min(int(payload.get("totalPages") or 1), _MAX_PAGES)
                if page >= total_pages:
                    break
            if len(hits) >= limit:
                break
        return ProviderResult(provider=self.name, hits=hits, total=total)

    def _hit(self, link: dict[str, Any], entity_key: str) -> DatasetHit | None:
        entity = _get(link, entity_key, entity_key.capitalize(), default={}) or {}
        if str(_get(entity, "Type", "type", default="")).lower() != "dataset":
            return None
        pid = None
        for identifier in _get(entity, "Identifier", "identifier", default=[]) or []:
            scheme = str(_get(identifier, "IDScheme", "idScheme", "schema", default=""))
            if scheme.lower() == "doi":
                pid = _get(identifier, "ID", "id")
                break
        if not pid:
            return None
        relationship = _get(link, "RelationshipType", "relationshipType", default={}) or {}
        publishers = _get(entity, "Publisher", "publisher", default=[]) or []
        publisher = _get(publishers[0], "name", "Name") if publishers else None
        date = str(_get(entity, "PublicationDate", "publicationDate", default="") or "")
        return DatasetHit(
            provider=self.name,
            pid=pid,
            pid_type="doi",
            title=_get(entity, "Title", "title"),
            publisher=publisher,
            year=int(date[:4]) if date[:4].isdigit() else None,
            relation=_get(relationship, "Name", "name"),
            url=f"https://doi.org/{pid}",
            raw=link,
        )
