"""Inspect public files in PuRe records that share the publication DOI."""

from __future__ import annotations

import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

import requests

from tools.research_data_enrichment.discover_from_openalex_fulltext import pdf_fulltext_hits

SEARCH_URL = "https://pure.mpg.de/rest/items/search"
BASE_URL = "https://pure.mpg.de"
DATA_FILE_RE = re.compile(
    r"\.(?:csv|tsv|xlsx?|sav|dta|rds|rdata|fst|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)
DOCUMENTATION_ONLY_RE = re.compile(
    r"(?:variable[_ -]?dict(?:ionary)?|data[_ -]?dict(?:ionary)?|codebook|readme)",
    re.IGNORECASE,
)
PUBLIC_DATA_CATEGORIES = {"research-data", "supplementary-material"}


def as_text(value: Any) -> str:
    return str(value or "").strip()


def get_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    **kwargs: Any,
) -> requests.Response:
    error: Exception | None = None
    for attempt in range(6):
        try:
            response = session.request(method, url, **kwargs)
            if response.status_code != 429:
                response.raise_for_status()
                return response
            error = requests.HTTPError(f"HTTP 429 for {url}")
        except requests.RequestException as exc:
            error = exc
        time.sleep(min(2 ** (attempt + 1), 30))
    raise RuntimeError(str(error or f"request failed: {url}"))


def search_records(session: requests.Session, doi: str) -> list[dict[str, Any]]:
    query = {
        "query": {"term": {"metadata.identifiers.id.keyword": {"value": doi}}},
        "size": 30,
        "from": 0,
    }
    response = get_with_retry(session, "POST", SEARCH_URL, json=query, timeout=45)
    return [record.get("data") or {} for record in response.json().get("records") or []]


def file_url(file: dict[str, Any]) -> str:
    content = as_text(file.get("content"))
    return content if content.startswith("http") else f"{BASE_URL}{content}"


def archive_data_members(content: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return [
                name
                for name in archive.namelist()
                if not name.startswith("__MACOSX/")
                and DATA_FILE_RE.search(name)
                and not DOCUMENTATION_ONLY_RE.search(Path(name).name)
            ]
    except zipfile.BadZipFile:
        return []


def inspect_public_file(
    session: requests.Session,
    row: dict[str, Any],
    record: dict[str, Any],
    file: dict[str, Any],
) -> list[dict[str, Any]]:
    name = as_text(file.get("name") or (file.get("metadata") or {}).get("title"))
    category = as_text((file.get("metadata") or {}).get("contentCategory")).casefold()
    mime_type = as_text(file.get("mimeType")).casefold()
    url = file_url(file)
    if not url or file.get("visibility") != "PUBLIC":
        return []
    if (
        category in PUBLIC_DATA_CATEGORIES
        and DATA_FILE_RE.search(name)
        and not DOCUMENTATION_ONLY_RE.search(name)
    ):
        return [
            {
                "provider": "pure-duplicate-file",
                "pid": as_text(file.get("pid") or url),
                "pid_type": "pure-file",
                "title": name,
                "publisher": "MPG.PuRe",
                "relation": "same-doi-public-research-data-file",
                "url": url,
                "discovery_method": "pure-same-doi-public-file-audit",
                "evidence": f"PuRe record {record.get('objectId')}; category={category}",
            }
        ]
    if name.casefold().endswith(".zip") or "zip" in mime_type:
        response = get_with_retry(session, "GET", url, timeout=90)
        data_files = archive_data_members(response.content)
        if not data_files:
            return []
        return [
            {
                "provider": "pure-duplicate-file",
                "pid": as_text(file.get("pid") or url),
                "pid_type": "pure-file",
                "title": name,
                "publisher": "MPG.PuRe",
                "relation": "same-doi-public-archive-with-data-files",
                "url": url,
                "discovery_method": "pure-same-doi-archive-file-audit",
                "evidence": (
                    f"PuRe record {record.get('objectId')}; archive contains "
                    f"{len(data_files)} data file(s): {', '.join(data_files[:8])}"
                ),
            }
        ]
    if mime_type == "application/pdf" or name.casefold().endswith(".pdf"):
        response = get_with_retry(session, "GET", url, timeout=90)
        if not response.content.startswith(b"%PDF") or len(response.content) > 35_000_000:
            return []
        hits = pdf_fulltext_hits(response.content, row, url)
        for hit in hits:
            hit["provider"] = "pure-duplicate-fulltext"
            hit["publisher"] = "MPG.PuRe same-DOI public full text"
            hit["discovery_method"] = "pure-same-doi-pdf-data-availability"
            hit["evidence"] = f"PuRe record {record.get('objectId')}; {hit['evidence']}"
        return hits
    return []


def process(row: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    doi = as_text(row.get("DOI")).lstrip("/")
    hits: list[dict[str, Any]] = []
    error = ""
    if doi:
        session = requests.Session()
        session.headers["User-Agent"] = "pybman-pure-duplicate-file-audit/1.0"
        try:
            for record in search_records(session, doi):
                if as_text(record.get("objectId")) == item_id:
                    continue
                for file in record.get("files") or []:
                    hits.extend(inspect_public_file(session, row, record, file))
        except Exception as exc:
            error = str(exc)
    unique = {as_text(hit.get("url")).casefold(): hit for hit in hits if hit.get("url")}
    return {
        "PuRe-ID": item_id,
        "DOI": doi,
        "status": "checked_pure_duplicates" if not error else "error",
        "found": bool(unique),
        "doi_found": bool(unique),
        "title_found": False,
        "hits": list(unique.values()),
        "provider_summary": f"pure-duplicate-files: {len(unique)}",
        "provider_errors": error,
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_pure_duplicate_files.py <publications.json> <results.json>")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    results = []
    for index, row in enumerate(rows, start=1):
        results.append(process(row))
        if index % 10 == 0 or index == len(rows):
            print(
                f"{index}/{len(rows)}; found={sum(result['found'] for result in results)}; "
                f"errors={sum(result['status'] == 'error' for result in results)}",
                flush=True,
            )
        time.sleep(0.75)
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
