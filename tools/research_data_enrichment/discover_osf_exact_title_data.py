"""Discover exact-title OSF projects and verify their research-data files."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pybman.discovery.matching import title_match_score, title_tokens
from pybman.discovery.osf import _contributor_names
from tools.research_data_enrichment.discover_cambridge_osf_data import (
    osf_project_evidence,
    publication_surnames,
)

OSF_NODES_URL = "https://api.osf.io/v2/nodes/"
ELIGIBLE_GENRES = {"ARTICLE", "PAPER", "CONFERENCE_PAPER"}


def as_text(value: Any) -> str:
    return str(value or "").strip()


def retrying_session() -> requests.Session:
    retry = Retry(
        total=7,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "pybman-osf-exact-title-data/1.0"
    return session


def matching_nodes(
    row: dict[str, Any], payload: dict[str, Any]
) -> list[dict[str, Any]]:
    title = as_text(row.get("Titel"))
    author_surnames = publication_surnames(as_text(row.get("Autor:innen")))
    matches = []
    for record in payload.get("data") or []:
        attributes = record.get("attributes") or {}
        candidate_title = as_text(attributes.get("title"))
        contributor_surnames = publication_surnames(
            ";".join(_contributor_names(record))
        )
        if (
            len(title_tokens(title)) >= 4
            and title_match_score(title, candidate_title) >= 0.9
            and author_surnames & contributor_surnames
        ):
            matches.append(record)
    return matches


def discover_row(
    row: dict[str, Any], session: requests.Session
) -> list[dict[str, Any]]:
    title = as_text(row.get("Titel"))
    response = session.get(
        OSF_NODES_URL,
        params={
            "filter[title]": title,
            "filter[public]": "true",
            "page[size]": 50,
            "embed": "contributors",
        },
        timeout=30,
    )
    response.raise_for_status()
    publication_authors = publication_surnames(as_text(row.get("Autor:innen")))
    hits = []
    for record in matching_nodes(row, response.json()):
        node_id = as_text(record.get("id")).casefold()
        if not node_id:
            continue
        try:
            project_title, contributor_surnames, data_files = osf_project_evidence(
                session, f"https://osf.io/{node_id}/"
            )
        except (KeyError, TypeError, ValueError, requests.RequestException):
            continue
        matching_authors = sorted(publication_authors & contributor_surnames)
        if not matching_authors or not data_files:
            continue
        hits.append(
            {
                "provider": "osf-exact-title-data",
                "pid": node_id,
                "pid_type": "osf",
                "title": project_title,
                "publisher": "Open Science Framework",
                "relation": "verified-title-author-and-data-files",
                "url": f"https://osf.io/{node_id}/",
                "discovery_method": "osf-exact-title-contributor-file-api-audit",
                "evidence": (
                    "Strong publication-title match; matching publication contributor(s): "
                    f"{', '.join(matching_authors)}; OSF contains {len(data_files)} "
                    f"research-data file(s): {', '.join(data_files[:12])}"
                ),
            }
        )
    return hits


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: discover_osf_exact_title_data.py <publications.json> <results.json>"
        )
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    session = retrying_session()
    delay = float(os.environ.get("OSF_DISCOVERY_DELAY_SECONDS", "0.7"))
    results = []
    for index, row in enumerate(rows, start=1):
        item_id = as_text(row.get("PuRe-ID"))
        applicable = (
            as_text(row.get("Genre")) in ELIGIBLE_GENRES
            and len(title_tokens(as_text(row.get("Titel")))) >= 4
        )
        started = time.time()
        hits: list[dict[str, Any]] = []
        error = ""
        if applicable:
            try:
                hits = discover_row(row, session)
            except requests.RequestException as exc:
                error = str(exc)
            time.sleep(delay)
        results.append(
            {
                "PuRe-ID": item_id,
                "DOI": as_text(row.get("DOI")).lstrip("/"),
                "status": "checked_osf_exact_title" if applicable else "not_applicable",
                "found": bool(hits),
                "doi_found": False,
                "title_found": bool(hits),
                "hits": hits,
                "provider_summary": f"osf-exact-title-data: {len(hits)}",
                "provider_errors": error,
                "elapsed_s": round(time.time() - started, 2),
            }
        )
        if index % 40 == 0 or index == len(rows):
            print(
                f"{index}/{len(rows)}; found={sum(item['found'] for item in results)}; "
                f"errors={sum(bool(item['provider_errors']) for item in results)}",
                flush=True,
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
