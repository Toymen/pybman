"""Discover repository links in eLife's structured data-availability metadata."""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

from pybman.discovery.fulltext import extract_fulltext_data_links

ARTICLE_URL = "https://api.elifesciences.org/articles/{article_id}"
ELIFE_DOI_RE = re.compile(r"^10\.7554/elife\.(\d+)(?:\.\d+)?$", re.IGNORECASE)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def data_availability_hits(payload: dict[str, Any], row: dict[str, Any]) -> list[dict[str, Any]]:
    statements = [
        as_text(block.get("text"))
        for block in (payload.get("dataSets") or {}).get("availability") or []
        if as_text(block.get("text"))
    ]
    text = "\nData availability:\n" + "\n".join(statements)
    links = [
        link
        for link in extract_fulltext_data_links(text)
        if urlsplit(link.url).netloc.casefold() != "github.com"
        or len([part for part in urlsplit(link.url).path.split("/") if part]) >= 2
    ]
    return [
        {
            "provider": "elife-data-availability",
            "pid": link.url,
            "pid_type": "url",
            "title": f"eLife data availability for {as_text(row.get('Titel'))}",
            "publisher": "eLife",
            "relation": "structured-publisher-data-availability",
            "url": link.url,
            "discovery_method": "elife-api-data-availability",
            "evidence": link.evidence,
        }
        for link in links
    ]


def process(row: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    doi = as_text(row.get("DOI")).lstrip("/")
    hits: list[dict[str, Any]] = []
    error = ""
    match = ELIFE_DOI_RE.match(doi)
    if match:
        try:
            response = requests.get(
                ARTICLE_URL.format(article_id=match.group(1)),
                headers={"User-Agent": "pybman-elife-data-discovery/1.0"},
                timeout=30,
            )
            response.raise_for_status()
            hits = data_availability_hits(response.json(), row)
        except Exception as exc:
            error = str(exc)
    return {
        "PuRe-ID": item_id,
        "DOI": doi,
        "status": "checked_elife_data" if not error else "error",
        "found": bool(hits),
        "doi_found": bool(hits),
        "title_found": False,
        "hits": hits,
        "provider_summary": f"elife-data-availability: {len(hits)}",
        "provider_errors": error,
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_elife_data.py <publications.json> <results.json>")
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
