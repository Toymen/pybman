"""AEA article-page provider for authoritative Data and Code links."""

from __future__ import annotations

import html
import re

from ._client import Provider
from .identifiers import normalize_doi
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://www.aeaweb.org/articles"
_DATA_DOI_RE = re.compile(
    r'href=["\'](https?://(?:dx\.)?doi\.org/(10\.3886/[^"\']+))["\']',
    re.IGNORECASE,
)


class AeaDataProvider(Provider):
    """Read publisher-maintained ICPSR Data and Code links from AEA pages."""

    name = "aea"
    supports_doi = True
    default_base_url = DEFAULT_BASE_URL

    def datasets_for_doi(self, doi: str, *, limit: int = 100) -> ProviderResult:
        doi = normalize_doi(doi)
        if not doi.startswith("10.1257/"):
            return ProviderResult(provider=self.name, hits=[], total=0)
        page = self._get_text(self._base_url, params={"id": doi}) or ""
        hits = []
        seen = set()
        for match in _DATA_DOI_RE.finditer(html.unescape(page)):
            dataset_doi = normalize_doi(match.group(2))
            if dataset_doi in seen:
                continue
            seen.add(dataset_doi)
            hits.append(
                DatasetHit(
                    provider=self.name,
                    pid=dataset_doi,
                    pid_type="doi",
                    publisher="AEA Data and Code / ICPSR",
                    relation="publisher-data-and-code-link",
                    url=f"https://doi.org/{dataset_doi}",
                    raw={"publication_doi": doi, "publisher_page": self._base_url},
                )
            )
            if len(hits) >= limit:
                break
        return ProviderResult(provider=self.name, hits=hits, total=len(hits))
