"""Open Science Framework title-based research-data discovery."""

from __future__ import annotations

from typing import Any

from ._client import DiscoveryError, Provider
from .matching import has_surname_overlap, title_match_score, title_tokens
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://api.osf.io/v2"


class OsfProvider(Provider):
    """Find public OSF projects and registrations by title and contributors."""

    name = "osf"
    supports_title = True
    default_base_url = DEFAULT_BASE_URL

    def datasets_for_title(
        self,
        title: str,
        *,
        authors: tuple[str, ...] = (),
        year: int | None = None,
        limit: int = 100,
    ) -> ProviderResult:
        del year
        title = " ".join(title.split())
        if not title:
            raise ValueError("publication title must not be empty")
        hits: list[DatasetHit] = []
        seen: set[str] = set()
        for collection in ("nodes", "registrations"):
            payload = self._get_json(
                f"{self._base_url}/{collection}/",
                params={
                    "filter[title]": title,
                    "filter[public]": "true",
                    "page[size]": min(limit, 100),
                    "embed": "contributors",
                },
            )
            if "errors" in payload:
                errors = payload.get("errors") or [{}]
                detail = str(errors[0].get("detail") or errors[0] or "unknown error")
                raise DiscoveryError(f"{self.name}: API reported failure: {detail}")
            for record in payload.get("data", []):
                hit = self._verified_hit(record, title, authors, collection)
                if hit is not None and hit.pid not in seen:
                    seen.add(hit.pid)
                    hits.append(hit)
                    if len(hits) >= limit:
                        return ProviderResult(provider=self.name, hits=hits, total=len(hits))
        return ProviderResult(provider=self.name, hits=hits, total=len(hits))

    def _verified_hit(
        self,
        record: dict[str, Any],
        publication_title: str,
        publication_authors: tuple[str, ...],
        collection: str,
    ) -> DatasetHit | None:
        attributes = record.get("attributes") or {}
        title = str(attributes.get("title") or "")
        contributors = _contributor_names(record)
        score = title_match_score(publication_title, title)
        if (
            score < 0.9
            or len(title_tokens(publication_title)) < 4
            or not has_surname_overlap(publication_authors, contributors)
        ):
            return None
        identifier = str(record.get("id") or "")
        url = str((record.get("links") or {}).get("html") or f"https://osf.io/{identifier}/")
        raw = dict(record)
        raw["_match"] = {
            "title_score": score,
            "author_overlap": True,
            "collection": collection,
        }
        return DatasetHit(
            provider=self.name,
            pid=identifier,
            pid_type="osf",
            title=title,
            publisher="Open Science Framework",
            relation="verified-title-author-match",
            url=url,
            raw=raw,
        )


def _contributor_names(record: dict[str, Any]) -> list[str]:
    embedded = (record.get("embeds") or {}).get("contributors") or {}
    names: list[str] = []
    for contributor in embedded.get("data") or []:
        user = ((contributor.get("embeds") or {}).get("users") or {}).get("data") or {}
        attributes = user.get("attributes") or {}
        name = attributes.get("full_name") or attributes.get("bibliographic_name")
        if name:
            names.append(str(name))
    return names
