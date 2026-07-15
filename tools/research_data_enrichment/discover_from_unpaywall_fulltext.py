"""Discover explicit research-data links in Unpaywall-indexed open PDF full text."""

from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from tools.research_data_enrichment.discover_from_openalex_fulltext import (
    MAX_PDF_BYTES,
    pdf_fulltext_hits,
)

UNPAYWALL_WORK = "https://api.unpaywall.org/v2/{doi}"


def as_text(value: Any) -> str:
    return str(value or "").strip()


def open_pdf_urls(work: dict[str, Any]) -> list[str]:
    """Return unique HTTPS PDF URLs from Unpaywall's open-access locations."""
    urls: list[str] = []
    candidates = [work.get("best_oa_location") or {}, *(work.get("oa_locations") or [])]
    for location in candidates:
        url = as_text(location.get("url_for_pdf"))
        if url.startswith("https://") and url not in urls:
            urls.append(url)
    return urls


def process(row: dict[str, Any], email: str) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    doi = as_text(row.get("DOI")).lstrip("/")
    hits: list[dict[str, Any]] = []
    errors: list[str] = []
    if doi:
        session = requests.Session()
        session.headers["User-Agent"] = f"pybman-unpaywall-fulltext-discovery/1.0 mailto:{email}"
        try:
            response = session.get(
                UNPAYWALL_WORK.format(doi=quote(doi, safe="")),
                params={"email": email},
                timeout=30,
            )
            if response.status_code == 404:
                work = {}
            else:
                response.raise_for_status()
                work = response.json()
            for pdf_url in open_pdf_urls(work)[:3]:
                try:
                    pdf = session.get(pdf_url, timeout=60)
                    pdf.raise_for_status()
                    content = pdf.content
                    if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF"):
                        continue
                    for hit in pdf_fulltext_hits(content, row, pdf_url):
                        hit["provider"] = "unpaywall-fulltext"
                        hit["publisher"] = "Open-access full text indexed by Unpaywall"
                        hit["discovery_method"] = "unpaywall-oa-pdf-data-availability"
                        hits.append(hit)
                except Exception as exc:
                    errors.append(f"{pdf_url}: {exc}")
        except Exception as exc:
            errors.append(str(exc))
    unique = {as_text(hit.get("url")).casefold(): hit for hit in hits}
    return {
        "PuRe-ID": item_id,
        "DOI": doi,
        "status": "checked_unpaywall_fulltext" if not errors else "checked_with_errors",
        "found": bool(unique),
        "doi_found": False,
        "title_found": False,
        "hits": list(unique.values()),
        "provider_summary": f"unpaywall-fulltext: {len(unique)}",
        "provider_errors": " | ".join(errors),
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_from_unpaywall_fulltext.py <publications.json> <results.json>")
        return 2
    email = as_text(os.environ.get("UNPAYWALL_EMAIL"))
    if not email or "@" not in email:
        print("Set UNPAYWALL_EMAIL to the contact address required by the Unpaywall API.")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(process, row, email): row for row in rows}
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
