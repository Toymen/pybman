"""Europe PMC full-text data-availability discovery."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import requests

from ._client import Provider
from .identifiers import normalize_doi
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
URL_RE = re.compile(r"https?://[^\s<>\]\[)]+", re.IGNORECASE)
DATA_HOSTS = (
    "osf.io",
    "doi.org",
    "zenodo.org",
    "figshare.com",
    "dataverse",
    "dryad",
    "edmond.mpg.de",
    "pangaea.de",
    "icpsr.org",
    "openicpsr.org",
    "data.mendeley.com",
    "psycharchives.org",
)


class EuropePmcProvider(Provider):
    """Extract explicit repository links from OA data-availability sections."""

    name = "europepmc"
    supports_doi = True

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
        payload = self._get_json(
            f"{self._base_url}/search",
            params={
                "query": f'DOI:"{doi}"',
                "format": "json",
                "resultType": "core",
                "pageSize": 5,
            },
        )
        hits: list[DatasetHit] = []
        seen: set[str] = set()
        for article in (payload.get("resultList") or {}).get("result") or []:
            pmcid = str(article.get("pmcid") or "")
            if not pmcid:
                continue
            xml = self._get_text(f"{self._base_url}/{pmcid}/fullTextXML", none_on_404=True)
            if not xml:
                continue
            for hit in _data_links(xml, doi, pmcid):
                if hit.url and hit.url.casefold() not in seen:
                    seen.add(hit.url.casefold())
                    hits.append(hit)
                    if len(hits) >= limit:
                        return ProviderResult(provider=self.name, hits=hits, total=len(hits))
        return ProviderResult(provider=self.name, hits=hits, total=len(hits))


def _data_links(xml: str, publication_doi: str, pmcid: str) -> list[DatasetHit]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    links: list[str] = []
    for section in root.iter("sec"):
        if not _is_data_availability_section(section):
            continue
        statement = " ".join("".join(section.itertext()).split())
        statement_lower = statement.casefold()
        current_availability = any(
            phrase in statement_lower
            for phrase in (
                "are available",
                "is available",
                "have been deposited",
                "can be accessed",
            )
        )
        if "will be available" in statement_lower and not current_availability:
            continue
        candidates = [
            str(value)
            for element in section.iter()
            for key, value in element.attrib.items()
            if key.endswith("href")
        ]
        candidates.extend(URL_RE.findall(statement))
        for candidate in candidates:
            cleaned = candidate.rstrip(".,;:")
            if any(host in cleaned.casefold() for host in DATA_HOSTS):
                links.append(cleaned)
    hits: list[DatasetHit] = []
    for url in dict.fromkeys(links):
        pid, pid_type = url, "url"
        if "doi.org/" in url.casefold():
            try:
                pid = normalize_doi(url)
                pid_type = "doi"
            except ValueError:
                pass
        hits.append(
            DatasetHit(
                provider="europepmc",
                pid=pid,
                pid_type=pid_type,
                title=f"Data availability link for {publication_doi}",
                publisher="Europe PMC full text",
                relation="data-availability-statement",
                url=url,
                raw={"pmcid": pmcid},
            )
        )
    return hits


def _is_data_availability_section(section: ET.Element) -> bool:
    section_type = str(section.attrib.get("sec-type") or "").casefold()
    if "data-availability" in section_type:
        return True
    title = section.find("title")
    title_text = " ".join(title.itertext()).casefold() if title is not None else ""
    return "data availability" in title_text or "availability of data" in title_text
