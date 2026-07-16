"""B2FIND provider (https://b2find.eudat.eu) — EUDAT's metadata catalogue.

B2FIND is a stock CKAN instance, so the standard CKAN action API applies
(``/api/3/action/package_search``). There are no dedicated DOI/ORCID query
fields; lookups are full-text phrase searches over the harvested metadata,
which works because DOIs and ORCID iDs are unusual enough strings.
"""

from __future__ import annotations

from typing import Any

import requests

from ._client import DiscoveryError, Provider, safe_get
from .identifiers import normalize_doi, normalize_orcid
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://b2find.eudat.eu"


class B2FindProvider(Provider):
    name = "b2find"
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
        return self._search(normalize_doi(doi), limit=limit)

    def datasets_for_orcid(self, orcid: str, *, limit: int = 100) -> ProviderResult:
        return self._search(normalize_orcid(orcid), limit=limit)

    def _search(self, term: str, *, limit: int) -> ProviderResult:
        payload = self._get_json(
            f"{self._base_url}/api/3/action/package_search",
            params={"q": f'"{term}"', "rows": limit},
        )
        if not payload.get("success"):
            message = safe_get(payload, "error", {}).get("message", "unknown error")
            raise DiscoveryError(f"{self.name}: CKAN reported failure: {message}")
        result = safe_get(payload, "result", {})
        hits = [self._hit(package) for package in result.get("results", [])]
        return ProviderResult(provider=self.name, hits=hits, total=result.get("count"))

    def _hit(self, package: dict[str, Any]) -> DatasetHit:
        name = package.get("name", "")
        pid, pid_type = name, "ckan"
        for extra in package.get("extras") or []:
            if str(extra.get("key", "")).lower() in ("doi", "pid") and extra.get("value"):
                doi = _try_doi(str(extra["value"]))
                if doi:
                    pid, pid_type = doi, "doi"
                    break
        if pid_type == "ckan":
            doi = _try_doi(str(package.get("url") or ""))
            if doi:
                pid, pid_type = doi, "doi"
        created = str(package.get("metadata_created") or "")
        organization = package.get("organization") or {}
        return DatasetHit(
            provider=self.name,
            pid=pid,
            pid_type=pid_type,
            title=package.get("title"),
            publisher=organization.get("title"),
            year=int(created[:4]) if created[:4].isdigit() else None,
            url=f"{self._base_url}/dataset/{name}" if name else None,
            raw=package,
        )


def _try_doi(value: str) -> str | None:
    try:
        return normalize_doi(value)
    except ValueError:
        return None
