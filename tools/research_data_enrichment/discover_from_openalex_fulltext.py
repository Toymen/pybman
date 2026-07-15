"""Discover explicit research-data links in OpenAlex-indexed open PDF full text."""

from __future__ import annotations

import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from pybman.discovery.fulltext import data_availability_sections, extract_fulltext_data_links

OPENALEX_WORK = "https://api.openalex.org/works/https://doi.org/{doi}"
MAX_PDF_BYTES = 35_000_000


def as_text(value: Any) -> str:
    return str(value or "").strip()


def open_pdf_urls(work: dict[str, Any]) -> list[str]:
    """Return unique PDF URLs from locations explicitly marked open access."""
    urls: list[str] = []
    candidates = [work.get("best_oa_location") or {}, *(work.get("locations") or [])]
    for location in candidates:
        url = as_text(location.get("pdf_url"))
        if location.get("is_oa") is True and url.startswith("https://") and url not in urls:
            urls.append(url)
    return urls


def pdf_annotations(reader: Any, page_indexes: set[int]) -> tuple[str, ...]:
    urls: list[str] = []
    for page_index in page_indexes:
        for reference in reader.pages[page_index].get("/Annots") or []:
            try:
                annotation = reference.get_object()
                uri = (annotation.get("/A") or {}).get("/URI")
            except Exception:
                continue
            if uri and as_text(uri) not in urls:
                urls.append(as_text(uri))
    return tuple(urls)


def pdf_fulltext_hits(content: bytes, row: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - actionable CLI dependency check
        raise RuntimeError("Install the research extra: pip install 'pybman[research]'") from exc
    reader = PdfReader(io.BytesIO(content))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    relevant_pages = {
        index for index, page_text in enumerate(page_texts) if data_availability_sections(page_text)
    }
    if not relevant_pages:
        return []
    annotation_urls = pdf_annotations(reader, relevant_pages)
    links = extract_fulltext_data_links("\n".join(page_texts), annotation_urls=annotation_urls)
    for page_index in relevant_pages:
        links.extend(
            extract_fulltext_data_links(
                page_texts[page_index],
                annotation_urls=pdf_annotations(reader, {page_index}),
            )
        )
    unique = {link.url.casefold(): link for link in links}
    return [
        {
            "provider": "openalex-fulltext",
            "pid": link.url,
            "pid_type": "url",
            "title": f"Data availability link for {as_text(row.get('Titel'))}",
            "publisher": "Open-access full text indexed by OpenAlex",
            "relation": "data-availability-statement",
            "url": link.url,
            "discovery_method": "openalex-oa-pdf-data-availability",
            "evidence": f"{link.heading}: {link.evidence}; PDF: {source_url}",
        }
        for link in unique.values()
    ]


def process(row: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    doi = as_text(row.get("DOI"))
    hits: list[dict[str, Any]] = []
    errors: list[str] = []
    if doi:
        session = requests.Session()
        session.headers["User-Agent"] = "pybman-openalex-fulltext-discovery/1.0"
        try:
            response = session.get(OPENALEX_WORK.format(doi=quote(doi, safe="")), timeout=30)
            if response.status_code == 404:
                work = {}
            else:
                response.raise_for_status()
                work = response.json()
            for pdf_url in open_pdf_urls(work)[:2]:
                try:
                    pdf = session.get(pdf_url, timeout=60)
                    pdf.raise_for_status()
                    content = pdf.content
                    if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF"):
                        continue
                    hits.extend(pdf_fulltext_hits(content, row, pdf_url))
                except Exception as exc:
                    errors.append(f"{pdf_url}: {exc}")
        except Exception as exc:
            errors.append(str(exc))
    unique = {as_text(hit.get("url")).casefold(): hit for hit in hits}
    return {
        "PuRe-ID": item_id,
        "DOI": doi,
        "status": "checked_openalex_fulltext" if not errors else "checked_with_errors",
        "found": bool(unique),
        "doi_found": False,
        "title_found": False,
        "hits": list(unique.values()),
        "provider_summary": f"openalex-fulltext: {len(unique)}",
        "provider_errors": " | ".join(errors),
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_from_openalex_fulltext.py <publications.json> <results.json>")
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
                    f"errors={sum(bool(result['provider_errors']) for result in results)}",
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
