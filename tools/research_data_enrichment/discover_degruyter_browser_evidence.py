"""Validate browser-observed De Gruyter data statements against OSF APIs."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

from tools.research_data_enrichment.discover_cambridge_osf_data import (
    osf_project_evidence,
    publication_surnames,
)

OSF_DOI_RE = re.compile(r"10\.17605/osf\.io/([a-z0-9]{5})", re.IGNORECASE)
REQUEST_ONLY_RE = re.compile(r"\b(?:upon|on) (?:reasonable )?request\b", re.I)
FUTURE_RELEASE_RE = re.compile(r"\b(?:will|shall) be (?:made )?available\b", re.I)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def osf_node_from_publisher_link(url: str) -> str | None:
    match = OSF_DOI_RE.search(url)
    return match.group(1).casefold() if match else None


def validated_hits(
    observation: dict[str, Any], publication: dict[str, Any], session: requests.Session
) -> list[dict[str, Any]]:
    statement = as_text(observation.get("data_availability_statement"))
    if REQUEST_ONLY_RE.search(statement) or FUTURE_RELEASE_RE.search(statement):
        return []
    publication_authors = publication_surnames(
        as_text(publication.get("Autor:innen"))
    )
    hits = []
    for publisher_link in observation.get("links") or []:
        node_id = osf_node_from_publisher_link(as_text(publisher_link))
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
                "provider": "degruyter-browser-data-availability",
                "pid": node_id,
                "pid_type": "osf",
                "title": project_title,
                "publisher": "De Gruyter Brill / Open Science Framework",
                "relation": "publisher-data-availability-with-author-overlap-and-data-files",
                "url": as_text(publisher_link),
                "discovery_method": "browser-observation-plus-osf-file-api-audit",
                "evidence": (
                    f"{statement} Matching publication contributor(s): "
                    f"{', '.join(matching_authors)}. OSF contains {len(data_files)} "
                    f"research-data file(s): {', '.join(data_files[:12])}"
                ),
            }
        )
    return hits


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "Usage: discover_degruyter_browser_evidence.py "
            "<publications.json> <browser-observations.json> <results.json>"
        )
        return 2
    publications_path, observations_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(publications_path.read_text(encoding="utf8"))["publications"][
        "rows"
    ]
    observations = json.loads(observations_path.read_text(encoding="utf8"))[
        "observations"
    ]
    by_id = {as_text(item.get("PuRe-ID")): item for item in observations}
    session = requests.Session()
    session.headers["User-Agent"] = "pybman-degruyter-browser-evidence/1.0"
    results = []
    for row in rows:
        item_id = as_text(row.get("PuRe-ID"))
        observation = by_id.get(item_id)
        hits = validated_hits(observation, row, session) if observation else []
        results.append(
            {
                "PuRe-ID": item_id,
                "DOI": as_text(row.get("DOI")).lstrip("/"),
                "status": (
                    "checked_degruyter_browser_evidence"
                    if observation
                    else "not_applicable"
                ),
                "found": bool(hits),
                "doi_found": bool(hits),
                "title_found": False,
                "hits": hits,
                "provider_summary": (
                    f"degruyter-browser-data-availability: {len(hits)}"
                ),
                "provider_errors": "",
                "elapsed_s": 0,
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
