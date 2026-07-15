"""Discover publication-linked datasets directly in Harvard Dataverse."""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import requests

from pybman.discovery.matching import normalize_text, title_tokens

SEARCH_URL = "https://dataverse.harvard.edu/api/search"
ELIGIBLE_GENRES = {"ARTICLE", "PAPER", "CONFERENCE_PAPER"}


def as_text(value: Any) -> str:
    return str(value or "").strip()


def publication_surnames(value: str) -> set[str]:
    return {
        normalize_text(name).split()[-1]
        for name in value.split(";")
        if normalize_text(name).split()
    }


def dataverse_surnames(authors: list[Any]) -> set[str]:
    surnames: set[str] = set()
    for author in authors:
        name = normalize_text(author)
        if not name:
            continue
        surname = name.split(",", 1)[0].split()[0]
        if surname:
            surnames.add(surname)
    return surnames


def strong_dataset_match(row: dict[str, Any], item: dict[str, Any]) -> bool:
    publication_tokens = set(title_tokens(as_text(row.get("Titel"))))
    dataset_tokens = set(title_tokens(as_text(item.get("name"))))
    title_coverage = (
        len(publication_tokens & dataset_tokens) / len(publication_tokens)
        if publication_tokens
        else 0
    )
    author_overlap = publication_surnames(as_text(row.get("Autor:innen"))) & dataverse_surnames(
        item.get("authors") or []
    )
    return (
        len(publication_tokens) >= 4
        and title_coverage >= 0.75
        and bool(author_overlap)
        and int(item.get("fileCount") or 0) > 0
        and "Published" in (item.get("publicationStatuses") or [])
        and as_text(item.get("global_id")).casefold().startswith("doi:")
    )


def search_phrase(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title)
    return " ".join(words[:18])


def process(row: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    title = as_text(row.get("Titel"))
    hits: list[dict[str, Any]] = []
    error = ""
    if as_text(row.get("Genre")) in ELIGIBLE_GENRES and len(title_tokens(title)) >= 4:
        try:
            response = requests.get(
                SEARCH_URL,
                params={"q": f'title:"{search_phrase(title)}"', "type": "dataset", "per_page": 20},
                timeout=30,
                headers={"User-Agent": "pybman-harvard-dataverse-discovery/1.0"},
            )
            response.raise_for_status()
            for item in (response.json().get("data") or {}).get("items") or []:
                if not strong_dataset_match(row, item):
                    continue
                global_id = as_text(item.get("global_id"))[4:]
                hits.append(
                    {
                        "provider": "harvard-dataverse",
                        "pid": global_id,
                        "pid_type": "doi",
                        "title": as_text(item.get("name")),
                        "publisher": as_text(item.get("publisher")) or "Harvard Dataverse",
                        "relation": "verified-title-author-files-match",
                        "url": as_text(item.get("url")),
                        "discovery_method": "harvard-dataverse-title-author-file-audit",
                        "evidence": (
                            "Published Harvard Dataverse record with strong publication-title and "
                            f"author match; fileCount={int(item.get('fileCount') or 0)}"
                        ),
                    }
                )
        except Exception as exc:
            error = str(exc)
    return {
        "PuRe-ID": item_id,
        "DOI": as_text(row.get("DOI")),
        "status": "checked_harvard_dataverse" if not error else "error",
        "found": bool(hits),
        "doi_found": False,
        "title_found": bool(hits),
        "hits": hits,
        "provider_summary": f"harvard-dataverse: {len(hits)}",
        "provider_errors": error,
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_harvard_dataverse.py <publications.json> <results.json>")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(process, row): row for row in rows}
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 25 == 0 or index == len(rows):
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
