"""Discover Cambridge-linked OSF projects that contain research-data files."""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests

DATA_FILE_RE = re.compile(
    r"\.(?:csv|tsv|xlsx?|sav|dta|rds|rdata|fst|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)
DOCUMENTATION_ONLY_RE = re.compile(
    r"(?:variable[_ -]?dict(?:ionary)?|data[_ -]?dict(?:ionary)?|codebook|readme)",
    re.IGNORECASE,
)
OSF_URL_RE = re.compile(
    r"https?://(?:www\.)?osf\.io/[a-z0-9]{5}(?:/[a-z0-9_./-]*)?(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def normalized_surname(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", folded.casefold())


def publication_surnames(value: str) -> set[str]:
    surnames = set()
    for author in value.split(";"):
        words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'-]+", author)
        if words:
            surnames.add(normalized_surname(words[-1]))
    return surnames - {""}


def osf_identity(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    if parsed.netloc.casefold().removeprefix("www.") != "osf.io":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    token = (parse_qs(parsed.query).get("view_only") or [""])[0]
    if not parts or not re.fullmatch(r"[a-z0-9]{5}", parts[0], re.I):
        return None
    if token and not re.fullmatch(r"[a-f0-9]{32}", token, re.I):
        return None
    return parts[0].casefold(), token


def extract_osf_links(page_html: str) -> list[str]:
    links = []
    for match in OSF_URL_RE.findall(html.unescape(page_html)):
        cleaned = match.rstrip(".,;:)]}")
        if osf_identity(cleaned):
            links.append(cleaned)
    return list(dict.fromkeys(links))


def osf_project_evidence(
    session: requests.Session, url: str
) -> tuple[str, set[str], list[str]]:
    identity = osf_identity(url)
    if not identity:
        return "", set(), []
    node_id, token = identity
    params: dict[str, Any] = {"page[size]": 100}
    if token:
        params["view_only"] = token

    node_response = session.get(
        f"https://api.osf.io/v2/nodes/{node_id}/", params=params, timeout=30
    )
    node_response.raise_for_status()
    title = as_text(node_response.json()["data"]["attributes"].get("title"))

    contributors_url = f"https://api.osf.io/v2/nodes/{node_id}/contributors/"
    contributor_payloads = []
    contributors_response = session.get(
        contributors_url, params=params, timeout=30
    )
    contributors_response.raise_for_status()
    contributor_payloads.append(contributors_response.json())
    if token and contributor_payloads[0].get("meta", {}).get("anonymous"):
        public_response = session.get(
            contributors_url, params={"page[size]": 100}, timeout=30
        )
        if public_response.ok:
            contributor_payloads.append(public_response.json())

    contributor_surnames = set()
    for payload in contributor_payloads:
        for record in payload.get("data") or []:
            attributes = (
                ((record.get("embeds") or {}).get("users") or {}).get("data") or {}
            ).get("attributes") or {}
            words = re.findall(
                r"[A-Za-zÀ-ÖØ-öø-ÿ'-]+", as_text(attributes.get("full_name"))
            )
            if words:
                contributor_surnames.add(normalized_surname(words[-1]))

    queue = [f"https://api.osf.io/v2/nodes/{node_id}/files/osfstorage/"]
    data_files: list[str] = []
    while queue:
        endpoint = queue.pop(0)
        response = session.get(endpoint, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for record in payload.get("data") or []:
            attributes = record.get("attributes") or {}
            name = as_text(attributes.get("name"))
            if attributes.get("kind") == "folder":
                related = (
                    (((record.get("relationships") or {}).get("files") or {}).get("links") or {})
                    .get("related", {})
                    .get("href")
                )
                if related:
                    queue.append(as_text(related))
            elif DATA_FILE_RE.search(name) and not DOCUMENTATION_ONLY_RE.search(name):
                data_files.append(name)
        next_url = ((payload.get("links") or {}).get("next") or {}).get("href")
        if next_url:
            queue.append(as_text(next_url))
    return title, contributor_surnames - {""}, sorted(set(data_files))


def discover_row(row: dict[str, Any], session: requests.Session) -> list[dict[str, Any]]:
    doi = as_text(row.get("DOI")).lstrip("/")
    if not doi.casefold().startswith("10.1017/"):
        return []
    publisher_response = session.get(
        f"https://doi.org/{doi}",
        headers={"Accept": "text/html,application/xhtml+xml"},
        timeout=30,
    )
    publisher_response.raise_for_status()
    if not urlsplit(publisher_response.url).netloc.casefold().endswith("cambridge.org"):
        return []

    publication_authors = publication_surnames(as_text(row.get("Autor:innen")))
    hits = []
    for url in extract_osf_links(publisher_response.text):
        try:
            project_title, contributor_surnames, data_files = osf_project_evidence(
                session, url
            )
        except (KeyError, TypeError, ValueError, requests.RequestException):
            continue
        matching_authors = sorted(publication_authors & contributor_surnames)
        if not matching_authors or not data_files:
            continue
        node_id, _ = osf_identity(url) or ("", "")
        hits.append(
            {
                "provider": "cambridge-osf-data",
                "pid": node_id,
                "pid_type": "osf",
                "title": project_title,
                "publisher": "Cambridge Core / Open Science Framework",
                "relation": "publisher-linked-osf-with-author-overlap-and-data-files",
                "url": url,
                "discovery_method": "cambridge-doi-page-plus-osf-file-api-audit",
                "evidence": (
                    f"Official Cambridge DOI page links this OSF project; matching "
                    f"publication contributor(s): {', '.join(matching_authors)}; OSF "
                    f"contains {len(data_files)} research-data file(s): "
                    f"{', '.join(data_files[:12])}"
                ),
            }
        )
    return hits


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: discover_cambridge_osf_data.py <publications.json> <results.json>"
        )
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    session = requests.Session()
    session.headers["User-Agent"] = "pybman-cambridge-osf-discovery/1.0"
    results = []
    for row in rows:
        item_id = as_text(row.get("PuRe-ID"))
        applicable = as_text(row.get("DOI")).lstrip("/").casefold().startswith("10.1017/")
        started = time.time()
        hits: list[dict[str, Any]] = []
        error = ""
        if applicable:
            try:
                hits = discover_row(row, session)
            except requests.RequestException as exc:
                error = str(exc)
        results.append(
            {
                "PuRe-ID": item_id,
                "DOI": as_text(row.get("DOI")).lstrip("/"),
                "status": "checked_cambridge_osf" if applicable else "not_applicable",
                "found": bool(hits),
                "doi_found": bool(hits),
                "title_found": False,
                "hits": hits,
                "provider_summary": f"cambridge-osf-data: {len(hits)}",
                "provider_errors": error,
                "elapsed_s": round(time.time() - started, 2),
            }
        )
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_rows": len(rows),
        "provider_found_rows": sum(result["found"] for result in results),
        "results": results,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
