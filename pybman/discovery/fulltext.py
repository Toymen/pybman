"""High-precision extraction of research-data links from publication full text."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

_HEADING_RE = re.compile(
    r"(?im)^\s*(?:\d+(?:\.\d+)*\s+)?(?:"
    r"data(?:,? materials?,? and code| and code| and materials)? availability|"
    r"availability of data(?: and materials)?|data accessibility|accessibility of data|"
    r"open (?:practices|science) statement|research data availability|data sharing statement"
    r")\s*[:.]?\s*$"
)
_INLINE_HEADING_RE = re.compile(
    r"(?i)\b(?:data(?: and code)? availability|availability of data(?: and materials)?|"
    r"data accessibility|open practices statement|data sharing statement)\s*:\s*"
)
_NEXT_HEADING_RE = re.compile(
    r"(?m)^\s*(?:\d+(?:\.\d+)*\s+)?(?:acknowledg(?:e)?ments?|author contributions?|"
    r"competing interests?|conflict of interest|funding|references|supplementary materials?|"
    r"ethics statements?|declarations?)\s*[:.]?\s*$",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?\s*:\s*/\s*/[^\s<>\[\]{}\"']+", re.IGNORECASE)
_DOI_RE = re.compile(r"(?<![\w./])10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_FUTURE_OR_REQUEST_ONLY_RE = re.compile(
    r"\b(?:available (?:from the authors? )?(?:on|upon) (?:reasonable )?request|"
    r"will be (?:made )?available|not applicable|no data (?:were|was) generated|"
    r"data sharing is not applicable)\b",
    re.IGNORECASE,
)
_DATA_ASSERTION_RE = re.compile(
    r"\b(?:raw data|processed data|research data|data and code|data and materials|"
    r"data, materials and code|"
    r"dataset|data set|replication (?:data|package)|underlying data|analysis data)\b",
    re.IGNORECASE,
)
_DATA_ACTION_RE = re.compile(
    r"\b(?:available|deposited|archived|shared|hosted|accessible)\b",
    re.IGNORECASE,
)
_REPOSITORY_HOST_RE = re.compile(
    r"(?:^|\.)(?:osf\.io|zenodo\.org|figshare\.com|sagepub\.com|dryad\.org|"
    r"datadryad\.org|dataverse\.[^/]+|data\.mendeley\.com|openicpsr\.org|icpsr\.umich\.edu|"
    r"psycharchives\.org|edmond\.mpg\.de|researchdata\.[^/]+|b2find\.eudat\.eu|"
    r"gesis\.org|datorium\.gesis\.org|github\.com)$",
    re.IGNORECASE,
)
_DATASET_DOI_PREFIX_RE = re.compile(
    r"^10\.(?:17605|17617|23668|5281|5525|6084|7910|3886|4232|60600|7291|25584)/",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FullTextDataLink:
    """One repository link supported by an explicit full-text data statement."""

    url: str
    evidence: str
    heading: str


def _compact(value: str) -> str:
    return " ".join(html.unescape(value).replace("\u00ad", "").split())


def _clean_url(value: str) -> str:
    value = re.sub(r"\s+", "", html.unescape(value))
    value = value.rstrip(".,;:)]}")
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _repository_url(value: str, statement: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    host = parsed.netloc.lower().removeprefix("www.")
    if _REPOSITORY_HOST_RE.search(host):
        if host == "github.com":
            return bool(_DATA_ASSERTION_RE.search(statement))
        return True
    if host in {"doi.org", "dx.doi.org"}:
        return bool(_DATASET_DOI_PREFIX_RE.match(parsed.path.lstrip("/")))
    return False


def _annotation_supported(value: str, statement: str) -> bool:
    """Require the statement to name the repository behind an annotation."""
    host = urlsplit(value).netloc.lower()
    labels = {
        "osf.io": r"\b(?:OSF|Open Science Framework)\b",
        "zenodo.org": r"\bZenodo\b",
        "figshare.com": r"\bFigshare\b",
        "dryad.org": r"\bDryad\b",
        "datadryad.org": r"\bDryad\b",
        "data.mendeley.com": r"\bMendeley Data\b",
        "openicpsr.org": r"\bopenICPSR\b",
        "icpsr.umich.edu": r"\bICPSR\b",
        "doi.org": r"\b(?:DOI|OSF|Zenodo|Dataverse|Figshare|ICPSR|Edmond)\b",
    }
    for domain, pattern in labels.items():
        if host.endswith(domain):
            return bool(
                re.search(pattern, statement, re.IGNORECASE)
                or re.search(r"\b(?:repository|data archive)\b", statement, re.IGNORECASE)
            )
    return bool(re.search(r"\b(?:repository|data archive)\b", statement, re.IGNORECASE))


def explicit_data_statements(text: str, *, radius: int = 900) -> list[str]:
    """Find local sentences that explicitly say data are archived or available."""
    statements = []
    for match in _DATA_ASSERTION_RE.finditer(text):
        start = max(0, match.start() - 250)
        end = min(len(text), match.end() + radius)
        window = _compact(text[start:end])
        if not _DATA_ACTION_RE.search(window):
            continue
        if not (_URL_RE.search(window) or _DOI_RE.search(window)):
            continue
        if window not in statements:
            statements.append(window)
    return statements


def data_availability_sections(text: str, *, max_chars: int = 5000) -> list[tuple[str, str]]:
    """Return explicit data-availability sections from extracted article text."""
    sections: list[tuple[str, str]] = []
    matches = list(_HEADING_RE.finditer(text))
    matches.extend(
        match
        for match in _INLINE_HEADING_RE.finditer(text)
        if not any(existing.start() <= match.start() < existing.end() for existing in matches)
    )
    for match in sorted(matches, key=lambda item: item.start()):
        tail = text[match.end() : match.end() + max_chars]
        next_heading = _NEXT_HEADING_RE.search(tail)
        body = tail[: next_heading.start()] if next_heading else tail
        sections.append((_compact(match.group(0)), _compact(body)))
    return sections


def extract_fulltext_data_links(
    text: str, *, annotation_urls: tuple[str, ...] = ()
) -> list[FullTextDataLink]:
    """Extract only repository links backed by an explicit data statement.

    Annotation URLs are useful for PDFs where the visible text contains a
    label such as ``OSF`` but the actual target exists only in the link
    annotation. They are still constrained to known data repositories.
    """
    found: list[FullTextDataLink] = []
    seen: set[str] = set()
    sections = data_availability_sections(text)
    sections.extend(
        ("Explizite Datenverfügbarkeitsaussage", value)
        for value in explicit_data_statements(text)
    )
    for heading, statement in sections:
        urls = [_clean_url(match.group(0)) for match in _URL_RE.finditer(statement)]
        urls.extend(f"https://doi.org/{match.group(0)}" for match in _DOI_RE.finditer(statement))
        urls.extend(
            _clean_url(value)
            for value in annotation_urls
            if _annotation_supported(value, statement)
        )
        accepted = [url for url in urls if _repository_url(url, statement)]
        if not accepted and _FUTURE_OR_REQUEST_ONLY_RE.search(statement):
            continue
        for url in accepted:
            key = url.casefold()
            if key in seen:
                continue
            seen.add(key)
            found.append(
                FullTextDataLink(
                    url=url,
                    heading=heading,
                    evidence=statement[:1200],
                )
            )
    return found
