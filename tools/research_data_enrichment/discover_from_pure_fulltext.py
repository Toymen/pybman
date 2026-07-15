"""Discover research-data links in public PDF files attached to PuRe records."""

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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pybman.discovery.fulltext import data_availability_sections, extract_fulltext_data_links

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - actionable CLI dependency check
    raise SystemExit("Install the research extra: pip install 'pybman[research]'") from exc

PURE_BASE = "https://pure.mpg.de"
DATA_FILE_RE = re.compile(
    r"\.(?:csv|tsv|sav|dta|rds|rdata|xlsx?|json|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)
ARCHIVE_FILE_RE = re.compile(r"\.zip$", re.IGNORECASE)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "pybman-pure-fulltext-discovery/1.0"
    retry = Retry(
        total=3,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def public_file_url(file_record: dict[str, Any]) -> str:
    content = as_text(file_record.get("content"))
    return content if content.startswith("http") else f"{PURE_BASE}{content}"


def pdf_annotations(reader: PdfReader, page_indexes: set[int]) -> tuple[str, ...]:
    urls: list[str] = []
    for page_index in page_indexes:
        page = reader.pages[page_index]
        for reference in page.get("/Annots") or []:
            try:
                annotation = reference.get_object()
                action = annotation.get("/A") or {}
                uri = action.get("/URI")
            except Exception:
                continue
            if uri and as_text(uri) not in urls:
                urls.append(as_text(uri))
    return tuple(urls)


def pdf_hits(
    session: requests.Session, item: dict[str, Any], row: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hits: list[dict[str, Any]] = []
    statements: list[dict[str, Any]] = []
    for file_record in item.get("files") or []:
        if as_text(file_record.get("visibility")) != "PUBLIC":
            continue
        metadata = file_record.get("metadata") or {}
        category = as_text(metadata.get("contentCategory"))
        name = as_text(file_record.get("name") or metadata.get("title"))
        url = public_file_url(file_record)
        is_internal = as_text(file_record.get("storage")) == "INTERNAL_MANAGED"
        data_file_evidence = ""
        if is_internal and DATA_FILE_RE.search(name):
            data_file_evidence = f"public structured PuRe attachment: {name}"
        elif (
            is_internal
            and ARCHIVE_FILE_RE.search(name)
            and int(file_record.get("size") or 0) <= 50_000_000
        ):
            archive_response = session.get(url, timeout=60)
            archive_response.raise_for_status()
            try:
                with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
                    data_members = [
                        member for member in archive.namelist() if DATA_FILE_RE.search(member)
                    ]
            except zipfile.BadZipFile:
                data_members = []
            if data_members:
                data_file_evidence = (
                    "public PuRe ZIP attachment contains "
                    f"{len(data_members)} structured data file(s)"
                )
        if (
            category == "research-data"
            or data_file_evidence
        ):
            hits.append(
                {
                    "provider": "pure-file",
                    "pid": as_text(file_record.get("pid") or file_record.get("objectId") or url),
                    "pid_type": "url",
                    "title": name or f"Research data for {as_text(row.get('Titel'))}",
                    "publisher": "MPG.PuRe",
                    "relation": "curated-research-data-file",
                    "url": url,
                    "discovery_method": "pure-file-metadata",
                    "evidence": data_file_evidence or "PuRe contentCategory=research-data",
                }
            )
        if (
            as_text(file_record.get("storage")) != "INTERNAL_MANAGED"
            or as_text(file_record.get("mimeType")) != "application/pdf"
            or int(file_record.get("size") or 0) > 35_000_000
        ):
            continue
        response = session.get(url, timeout=60)
        response.raise_for_status()
        reader = PdfReader(io.BytesIO(response.content))
        page_texts = [page.extract_text() or "" for page in reader.pages]
        relevant_pages = {
            index
            for index, page_text in enumerate(page_texts)
            if data_availability_sections(page_text)
        }
        if not relevant_pages:
            continue
        annotation_urls = pdf_annotations(reader, relevant_pages)
        full_text = "\n".join(page_texts)
        sections = data_availability_sections(full_text)
        statements.extend(
            {
                "file": name,
                "heading": heading,
                "statement": statement[:1800],
                "annotation_urls": list(annotation_urls),
            }
            for heading, statement in sections
        )
        links = extract_fulltext_data_links(full_text, annotation_urls=annotation_urls)
        for page_index, page_text in enumerate(page_texts):
            page_annotations = pdf_annotations(reader, {page_index})
            links.extend(
                extract_fulltext_data_links(page_text, annotation_urls=page_annotations)
            )
        for link in links:
            hits.append(
                {
                    "provider": "pure-fulltext",
                    "pid": link.url,
                    "pid_type": "url",
                    "title": f"Data availability link for {as_text(row.get('Titel'))}",
                    "publisher": "MPG.PuRe full text",
                    "relation": "data-availability-statement",
                    "url": link.url,
                    "discovery_method": "pure-pdf-data-availability",
                    "evidence": f"{link.heading}: {link.evidence}",
                }
            )
    unique: dict[str, dict[str, Any]] = {}
    for hit in hits:
        unique.setdefault(as_text(hit.get("url")).casefold(), hit)
    return list(unique.values()), statements


def process(row: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    session = make_session()
    try:
        response = session.get(f"{PURE_BASE}/rest/items/{item_id}", timeout=30)
        response.raise_for_status()
        item = response.json()
        hits, statements = pdf_hits(session, item, row)
        return {
            "PuRe-ID": item_id,
            "DOI": as_text(row.get("DOI")),
            "status": "checked_pure_fulltext",
            "found": bool(hits),
            "doi_found": False,
            "title_found": False,
            "hits": hits,
            "data_statements": statements,
            "provider_summary": f"pure-fulltext: {len(hits)}",
            "provider_errors": "",
            "elapsed_s": round(time.time() - started, 2),
        }
    except Exception as exc:
        return {
            "PuRe-ID": item_id,
            "DOI": as_text(row.get("DOI")),
            "status": "error",
            "found": False,
            "doi_found": False,
            "title_found": False,
            "hits": [],
            "data_statements": [],
            "provider_summary": "pure-fulltext: error",
            "provider_errors": str(exc),
            "elapsed_s": round(time.time() - started, 2),
        }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_from_pure_fulltext.py <publications.json> <results.json>")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    payload = json.loads(input_path.read_text(encoding="utf8"))
    rows = payload["publications"]["rows"]
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
