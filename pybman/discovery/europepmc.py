"""Europe PMC full-text data-availability discovery."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import defusedxml.ElementTree as DefusedET
from defusedxml.common import DefusedXmlException

from ._client import Provider
from .identifiers import normalize_doi
from .models import DatasetHit, ProviderResult

DEFAULT_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
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
    "github.com",
)


class EuropePmcProvider(Provider):
    """Extract explicit repository links from OA data-availability sections."""

    name = "europepmc"
    supports_doi = True
    default_base_url = DEFAULT_BASE_URL

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
        root = DefusedET.fromstring(xml)
    except (ET.ParseError, DefusedXmlException):
        return []
    links: list[str] = []
    elements_by_id = {
        element_id: element
        for element in root.iter()
        if (element_id := str(element.attrib.get("id") or ""))
    }
    for section in root.iter("sec"):
        if not _is_data_availability_section(section):
            continue
        statement = " ".join("".join(section.itertext()).split())
        statement_lower = statement.casefold()
        current_availability = any(
            phrase in statement_lower
            for phrase in (
                "are available",
                "are openly available",
                "are publicly available",
                "is available",
                "is openly available",
                "is publicly available",
                "have been deposited",
                "can be accessed",
                "provide all data",
                "all data and workflow",
            )
        )
        future_release = re.search(
            r"will be (?:made |openly |publicly )?available", statement_lower
        )
        if future_release and not current_availability:
            continue
        referenced_elements = [
            elements_by_id[reference_id]
            for element in section.iter()
            for reference_id in str(element.attrib.get("rid") or "").split()
            if reference_id in elements_by_id
        ]
        candidates = [
            str(value)
            for container in (section, *referenced_elements)
            for element in container.iter()
            for key, value in element.attrib.items()
            if key.endswith("href")
        ]
        for candidate in candidates:
            cleaned = candidate.rstrip(".,;:")
            if _matches_data_host(cleaned):
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


def _matches_data_host(url: str) -> bool:
    """True if ``url``'s host is (or is a subdomain of) a known data host.

    Matches against the URL's netloc rather than the whole URL string, so a
    lookalike like ``https://fakegithub.com.evil.example/x`` (matched only
    on path/query in the old substring-over-full-URL check) can no longer
    spoof ``github.com``. Full domains (containing a dot, e.g. ``osf.io``)
    require an exact host or subdomain match; bare keywords (``dataverse``,
    ``dryad``) that stand for a family of installations keep a substring
    match, but scoped to the host label only, not the full URL.
    """
    netloc = urlsplit(url if "//" in url else f"//{url}").netloc.casefold()
    host = netloc.rpartition("@")[2].partition(":")[0]
    if not host:
        return False
    for data_host in DATA_HOSTS:
        if "." in data_host:
            if host == data_host or host.endswith(f".{data_host}"):
                return True
        elif data_host in host:
            return True
    return False


def _is_data_availability_section(section: ET.Element) -> bool:
    section_type = str(section.attrib.get("sec-type") or "").casefold()
    if "data-availability" in section_type:
        return True
    title = section.find("title")
    title_text = " ".join(title.itertext()).casefold() if title is not None else ""
    return "data availability" in title_text or "availability of data" in title_text
