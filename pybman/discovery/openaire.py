"""OpenAIRE Graph API provider (https://api.openaire.eu/graph/v1).

OpenAIRE aggregates research products (publications, datasets, software)
from thousands of European repositories and links them to authors, projects
and each other.

* ORCID → datasets: ``researchProducts?authorOrcid=...&type=dataset`` —
  OpenAIRE's author linking makes this the strongest ORCID source.
* DOI → datasets: a ``pid`` lookup answers whether the DOI *itself* is a
  registered dataset. Publication→dataset *links* are served by the sibling
  ScholeXplorer service (see :mod:`pybman.discovery.scholexplorer`).

Anonymous access is rate-limited; a registered access token raises the
limits and is sent as a Bearer header when configured.
"""

from __future__ import annotations

from typing import Any

import requests

from ._client import Provider, safe_get
from .identifiers import normalize_doi, normalize_orcid
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://api.openaire.eu/graph/v1"


class OpenAIREProvider(Provider):
    name = "openaire"
    supports_doi = True
    supports_orcid = True

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        access_token: str | None = None,
        session: requests.Session | None = None,
        timeout: float = 15.0,
        retries: int = 2,
    ) -> None:
        super().__init__(session=session, timeout=timeout, retries=retries)
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token

    def datasets_for_doi(self, doi: str, *, limit: int = 100) -> ProviderResult:
        return self._search({"pid": normalize_doi(doi)}, limit=limit)

    def datasets_for_orcid(self, orcid: str, *, limit: int = 100) -> ProviderResult:
        return self._search({"authorOrcid": normalize_orcid(orcid)}, limit=limit)

    def _search(self, params: dict[str, Any], *, limit: int) -> ProviderResult:
        headers = None
        if self._access_token:
            headers = {"Authorization": f"Bearer {self._access_token}"}
        payload = self._get_json(
            f"{self._base_url}/researchProducts",
            params={**params, "type": "dataset", "pageSize": limit},
            headers=headers,
        )
        hits = [self._hit(record) for record in payload.get("results", []) if record.get("id")]
        total = safe_get(payload, "header", {}).get("numFound")
        if isinstance(total, str) and total.isdigit():
            total = int(total)
        return ProviderResult(provider=self.name, hits=hits, total=total)

    def _hit(self, record: dict[str, Any]) -> DatasetHit:
        pid, pid_type, url = record.get("id", ""), "openaire", None
        for candidate in record.get("pids") or []:
            if str(candidate.get("scheme", "")).lower() == "doi":
                pid, pid_type = candidate.get("value", ""), "doi"
                url = f"https://doi.org/{pid}"
                break
        date = record.get("publicationDate") or ""
        year = int(date[:4]) if date[:4].isdigit() else None
        return DatasetHit(
            provider=self.name,
            pid=pid,
            pid_type=pid_type,
            title=record.get("mainTitle"),
            publisher=record.get("publisher"),
            year=year,
            url=url,
            raw=record,
        )
