"""ORCID Public API provider (https://pub.orcid.org).

ORCID is useful for ORCID -> datasets lookups because researcher records can
contain public works whose type is ``data-set``. Unlike DataCite and OpenAIRE,
this source reflects what is present on the ORCID record itself, so coverage
depends on public record completeness.
"""

from __future__ import annotations

from typing import Any

import requests

from ._client import Provider
from .identifiers import normalize_doi, normalize_orcid
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://pub.orcid.org/v3.0"
JSON_ACCEPT = "application/vnd.orcid+json"
DATASET_TYPES = frozenset({"data-set", "dataset"})


class OrcidProvider(Provider):
    name = "orcid"
    supports_doi = False
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

    def datasets_for_orcid(self, orcid: str, *, limit: int = 100) -> ProviderResult:
        orcid = normalize_orcid(orcid)
        payload = self._get_json(
            f"{self._base_url}/{orcid}/works",
            headers={"Accept": JSON_ACCEPT},
            none_on_404=True,
        )
        if payload is None:
            return ProviderResult(provider=self.name, hits=[], total=0)
        hits = list(self._hits(payload, orcid))[:limit]
        return ProviderResult(provider=self.name, hits=hits, total=len(hits))

    def _hits(self, payload: dict[str, Any], orcid: str) -> list[DatasetHit]:
        hits: list[DatasetHit] = []
        seen: set[tuple[str, str]] = set()
        for group in payload.get("group") or []:
            summaries = group.get("work-summary") or []
            if not summaries:
                continue
            for summary in summaries:
                if str(summary.get("type", "")).lower() not in DATASET_TYPES:
                    continue
                hit = self._hit(group, summary, orcid)
                if hit is not None and (hit.pid_type, hit.pid.lower()) not in seen:
                    seen.add((hit.pid_type, hit.pid.lower()))
                    hits.append(hit)
        return hits

    def _hit(
        self, group: dict[str, Any], summary: dict[str, Any], orcid: str
    ) -> DatasetHit | None:
        doi, doi_url = _doi_from_group(group)
        if doi:
            pid, pid_type, url = doi, "doi", doi_url or f"https://doi.org/{doi}"
        else:
            put_code = summary.get("put-code")
            if put_code is None:
                return None
            pid, pid_type = f"{orcid}/work/{put_code}", "orcid-work"
            url = f"https://orcid.org/{orcid}/work/{put_code}"
        return DatasetHit(
            provider=self.name,
            pid=pid,
            pid_type=pid_type,
            title=_nested_value(summary, "title", "title", "value"),
            publisher=_nested_value(summary, "journal-title", "value"),
            year=_publication_year(summary),
            url=url,
            raw=summary,
        )


def _doi_from_group(group: dict[str, Any]) -> tuple[str | None, str | None]:
    for external_id in (group.get("external-ids") or {}).get("external-id") or []:
        if str(external_id.get("external-id-type", "")).lower() != "doi":
            continue
        try:
            doi = normalize_doi(str(external_id.get("external-id-value", "")))
        except ValueError:
            continue
        return doi, _nested_value(external_id, "external-id-url", "value")
    return None, None


def _nested_value(mapping: dict[str, Any], *keys: str) -> str | None:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return str(value) if value is not None else None


def _publication_year(summary: dict[str, Any]) -> int | None:
    year = _nested_value(summary, "publication-date", "year", "value")
    return int(year) if year and year.isdigit() else None
