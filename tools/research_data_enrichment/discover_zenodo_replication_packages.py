"""Discover Zenodo replication packages by inspecting their actual files."""

from __future__ import annotations

import io
import json
import re
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

from pybman.discovery.matching import normalize_text, title_tokens

SEARCH_URL = "https://zenodo.org/api/records"
ELIGIBLE_GENRES = {"ARTICLE", "PAPER", "CONFERENCE_PAPER"}
DATA_FILE_RE = re.compile(
    r"\.(?:csv|tsv|xlsx?|sav|dta|rds|rdata|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)
MAX_ARCHIVE_BYTES = 50_000_000


def get_with_retry(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 30,
) -> requests.Response:
    for attempt in range(5):
        response = session.get(url, params=params, timeout=timeout)
        if response.status_code != 429:
            response.raise_for_status()
            return response
        delay = float(response.headers.get("Retry-After") or 2 ** (attempt + 1))
        time.sleep(min(delay, 30))
    response.raise_for_status()
    return response


def as_text(value: Any) -> str:
    return str(value or "").strip()


def surnames(values: list[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        raw_name = as_text(value)
        comma_ordered = "," in raw_name
        name = normalize_text(raw_name)
        if not name:
            continue
        result.add(name.split()[0] if comma_ordered else name.split()[-1])
    return result


def strong_record_match(row: dict[str, Any], record: dict[str, Any]) -> bool:
    metadata = record.get("metadata") or {}
    publication_tokens = set(title_tokens(as_text(row.get("Titel"))))
    record_tokens = set(title_tokens(as_text(metadata.get("title"))))
    coverage = (
        len(publication_tokens & record_tokens) / len(publication_tokens)
        if publication_tokens
        else 0
    )
    publication_authors = surnames(as_text(row.get("Autor:innen")).split(";"))
    record_authors = surnames(
        [as_text(creator.get("name")) for creator in metadata.get("creators") or []]
    )
    return len(publication_tokens) >= 4 and coverage >= 0.75 and bool(
        publication_authors & record_authors
    )


def archive_data_members(content: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return [name for name in archive.namelist() if DATA_FILE_RE.search(name)]
    except zipfile.BadZipFile:
        return []


def record_data_files(session: requests.Session, record: dict[str, Any]) -> list[str]:
    data_files: list[str] = []
    for file in record.get("files") or []:
        name = as_text(file.get("key"))
        if DATA_FILE_RE.search(name):
            data_files.append(name)
            continue
        if not name.casefold().endswith(".zip") or int(file.get("size") or 0) > MAX_ARCHIVE_BYTES:
            continue
        url = as_text((file.get("links") or {}).get("self"))
        if not url:
            continue
        response = get_with_retry(session, url, timeout=60)
        data_files.extend(f"{name}:{member}" for member in archive_data_members(response.content))
    return data_files


def search_phrase(title: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9]+", title)[:18])


def process(row: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    title = as_text(row.get("Titel"))
    hits: list[dict[str, Any]] = []
    error = ""
    if as_text(row.get("Genre")) in ELIGIBLE_GENRES and len(title_tokens(title)) >= 4:
        session = requests.Session()
        session.headers["User-Agent"] = "pybman-zenodo-replication-discovery/1.0"
        try:
            response = get_with_retry(
                session,
                SEARCH_URL,
                params={"q": f'metadata.title:"{search_phrase(title)}"', "size": 10},
                timeout=30,
            )
            for record in (response.json().get("hits") or {}).get("hits") or []:
                if not strong_record_match(row, record):
                    continue
                data_files = record_data_files(session, record)
                if not data_files:
                    continue
                metadata = record.get("metadata") or {}
                doi = as_text(record.get("doi") or metadata.get("doi"))
                if not doi:
                    continue
                hits.append(
                    {
                        "provider": "zenodo-replication",
                        "pid": doi,
                        "pid_type": "doi",
                        "title": as_text(metadata.get("title")),
                        "publisher": "Zenodo",
                        "relation": "verified-title-author-and-data-files",
                        "url": f"https://doi.org/{doi}",
                        "discovery_method": "zenodo-title-author-archive-audit",
                        "evidence": (
                            "Strong publication-title and author match; Zenodo files contain "
                            f"{len(data_files)} structured data file(s): "
                            f"{', '.join(data_files[:8])}"
                        ),
                    }
                )
        except Exception as exc:
            error = str(exc)
    return {
        "PuRe-ID": item_id,
        "DOI": as_text(row.get("DOI")),
        "status": "checked_zenodo_replication" if not error else "error",
        "found": bool(hits),
        "doi_found": False,
        "title_found": bool(hits),
        "hits": hits,
        "provider_summary": f"zenodo-replication: {len(hits)}",
        "provider_errors": error,
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_zenodo_replication_packages.py <publications.json> <results.json>")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(process, row): row for row in rows}
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 20 == 0 or index == len(rows):
                print(
                    f"{index}/{len(rows)}; found={sum(result['found'] for result in results)}; "
                    f"errors={sum(result['status'] == 'error' for result in results)}",
                    flush=True,
                )
    by_id = {result["PuRe-ID"]: result for result in results}
    ordered = [by_id[as_text(row.get("PuRe-ID"))] for row in rows]
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_rows": len(rows),
        "provider_found_rows": sum(result["found"] for result in ordered),
        "results": ordered,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
