from __future__ import annotations

import dataclasses
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from pybman.discovery import (
    DataDiscovery,
    DatasetHit,
    DiscoveryReport,
    google_dataset_search_url,
    normalize_doi,
)

DISABLED_PROVIDERS = {
    provider.strip()
    for provider in os.environ.get("DISCOVERY_DISABLE_PROVIDERS", "").split(",")
    if provider.strip()
}


def as_text(value: Any) -> str:
    return str(value or "").strip()


def clean_doi(value: Any) -> str:
    doi = as_text(value)
    doi = doi.removeprefix("https://").removeprefix("http://")
    doi = doi.removeprefix("dx.doi.org/")
    doi = doi.removeprefix("doi.org/")
    doi = doi.lstrip("/")
    return normalize_doi(doi)


def publication_authors(value: Any) -> tuple[str, ...]:
    return tuple(author.strip() for author in as_text(value).split(";") if author.strip())


def publication_year(value: Any) -> int | None:
    date = as_text(value)
    return int(date[:4]) if date[:4].isdigit() else None


def serialized_hit(hit: DatasetHit, method: str) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in dataclasses.asdict(hit).items()
        if key != "raw" and value not in (None, "")
    }
    payload["discovery_method"] = method
    return payload


def merge_hits(
    *reports: tuple[str, DiscoveryReport | None], publication_doi: str = ""
) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for method, report in reports:
        if report is None:
            continue
        for hit in report.hits:
            if hit.pid_type == "doi" and hit.pid.casefold() == publication_doi.casefold():
                continue
            key = (hit.pid_type, hit.pid.casefold())
            candidate = serialized_hit(hit, method)
            existing = unique.get(key)
            if existing is None:
                unique[key] = candidate
            elif method not in as_text(existing.get("discovery_method")).split("+"):
                existing["discovery_method"] += f"+{method}"
    return list(unique.values())


def run_one(row: dict[str, Any]) -> dict[str, Any]:
    item_id = as_text(row.get("PuRe-ID"))
    doi_raw = as_text(row.get("DOI"))
    title = as_text(row.get("Titel"))
    started = time.time()
    discovery = DataDiscovery(timeout=12.0, retries=1)
    if DISABLED_PROVIDERS:
        discovery.providers = [
            provider for provider in discovery.providers if provider.name not in DISABLED_PROVIDERS
        ]
    doi = clean_doi(doi_raw) if doi_raw else ""
    doi_report = discovery.for_doi(doi, limit=20) if doi else None
    title_report = (
        discovery.for_title(
            title,
            authors=publication_authors(row.get("Autor:innen")),
            year=publication_year(row.get("Datum")),
            limit=20,
        )
        if title
        else None
    )
    reports = [report for report in (doi_report, title_report) if report is not None]
    errors = [
        f"{result.provider}: {result.error}"
        for report in reports
        for result in report.results
        if result.error
    ]
    hits = merge_hits(
        ("doi-relation", doi_report),
        ("verified-title-author", title_report),
        publication_doi=doi,
    )
    return {
        "PuRe-ID": item_id,
        "DOI": doi,
        "status": "checked_doi_and_title" if doi else "checked_title_only",
        "found": bool(hits),
        "doi_found": bool(doi_report and doi_report.found),
        "title_found": bool(title_report and title_report.found),
        "hits": hits,
        "provider_summary": " | ".join(
            f"{report.query_type}: {report.summary()}" for report in reports
        ),
        "provider_errors": " | ".join(errors),
        "google_dataset_search": google_dataset_search_url(doi or title),
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python run_discovery.py <publications.json> <results.json>", file=sys.stderr)
        return 2
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(input_path.read_text(encoding="utf8"))
    rows = payload["publications"]["rows"]

    max_workers = int(os.environ.get("DISCOVERY_WORKERS", "8"))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_one, row): row for row in rows}
        for idx, future in enumerate(as_completed(futures), start=1):
            row = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "PuRe-ID": as_text(row.get("PuRe-ID")),
                    "DOI": as_text(row.get("DOI")),
                    "status": "error",
                    "found": False,
                    "doi_found": False,
                    "title_found": False,
                    "hits": [],
                    "provider_summary": "",
                    "provider_errors": str(exc),
                    "google_dataset_search": google_dataset_search_url(
                        as_text(row.get("DOI") or row.get("Titel"))
                    ),
                    "elapsed_s": 0,
                }
            results.append(result)
            if idx % 20 == 0 or idx == len(rows):
                checked = sum(1 for result in results if result["status"].startswith("checked"))
                found = sum(1 for result in results if result["found"])
                print(
                    f"{idx}/{len(rows)} rows completed; checked={checked}; provider-found={found}",
                    flush=True,
                )

    by_id = {result["PuRe-ID"]: result for result in results}
    ordered = [by_id.get(as_text(row.get("PuRe-ID"))) for row in rows]
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_rows": len(rows),
        "doi_rows": sum(1 for row in rows if as_text(row.get("DOI"))),
        "title_rows": sum(1 for row in rows if as_text(row.get("Titel"))),
        "provider_found_rows": sum(1 for result in ordered if result and result["found"]),
        "title_found_rows": sum(1 for result in ordered if result and result["title_found"]),
        "results": ordered,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
