"""Validate browser-observed Wiley data statements against repository APIs."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import requests

DATA_FILE_RE = re.compile(
    r"\.(?:csv|tsv|xlsx?|sav|dta|rds|rdata|fst|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)
DOCUMENTATION_ONLY_RE = re.compile(
    r"(?:variable[_ -]?dict(?:ionary)?|data[_ -]?dict(?:ionary)?|codebook|readme)",
    re.IGNORECASE,
)
REQUEST_ONLY_RE = re.compile(r"\b(?:upon|on) (?:reasonable )?request\b", re.IGNORECASE)
NO_DATA_RE = re.compile(
    r"\bno data (?:has|have|was|were) (?:been )?(?:collected|generated)\b", re.I
)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def osf_identity(url: str) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    if parsed.netloc.casefold().removeprefix("www.") != "osf.io":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    token = (parse_qs(parsed.query).get("view_only") or [""])[0]
    if not parts or not re.fullmatch(r"[a-z0-9]{5}", parts[0], re.I):
        return None
    if token and not re.fullmatch(r"[a-f0-9]{32}", token, re.I):
        return None
    return parts[0], token


def osf_data_files(session: requests.Session, url: str) -> list[str]:
    identity = osf_identity(url)
    if not identity:
        return []
    node_id, token = identity
    params = {"page[size]": 100}
    if token:
        params["view_only"] = token
    queue = [f"https://api.osf.io/v2/nodes/{node_id}/files/osfstorage/"]
    data_files: list[str] = []
    while queue:
        endpoint = queue.pop(0)
        response = session.get(endpoint, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        for record in payload.get("data") or []:
            attributes = record.get("attributes") or {}
            name = as_text(attributes.get("name"))
            if attributes.get("kind") == "folder":
                related = (
                    (((record.get("relationships") or {}).get("files") or {}).get("links") or {})
                    .get("related", {})
                    .get("href")
                )
                if related:
                    queue.append(as_text(related))
            elif DATA_FILE_RE.search(name) and not DOCUMENTATION_ONLY_RE.search(name):
                data_files.append(name)
        next_url = ((payload.get("links") or {}).get("next") or {}).get("href")
        if next_url:
            queue.append(as_text(next_url))
    return sorted(set(data_files))


def validated_hits(observation: dict[str, Any]) -> list[dict[str, Any]]:
    statement = as_text(observation.get("data_availability_statement"))
    if REQUEST_ONLY_RE.search(statement) or NO_DATA_RE.search(statement):
        return []
    session = requests.Session()
    session.headers["User-Agent"] = "pybman-wiley-browser-evidence/1.0"
    hits = []
    for url in observation.get("links") or []:
        try:
            data_files = osf_data_files(session, as_text(url))
        except requests.RequestException:
            continue
        if not data_files:
            continue
        node_id, _ = osf_identity(as_text(url)) or ("", "")
        hits.append(
            {
                "provider": "wiley-browser-data-availability",
                "pid": node_id,
                "pid_type": "osf",
                "title": f"Wiley-linked OSF research data ({node_id})",
                "publisher": "Wiley Online Library / Open Science Framework",
                "relation": "publisher-data-availability-statement-with-verified-data-files",
                "url": as_text(url),
                "discovery_method": "browser-observation-plus-osf-file-api-audit",
                "evidence": (
                    f"{statement} OSF contains {len(data_files)} research-data file(s): "
                    f"{', '.join(data_files[:10])}"
                ),
            }
        )
    return hits


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "Usage: discover_wiley_browser_evidence.py "
            "<publications.json> <browser-observations.json> <results.json>"
        )
        return 2
    publications_path, observations_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(publications_path.read_text(encoding="utf8"))["publications"]["rows"]
    observations = json.loads(observations_path.read_text(encoding="utf8"))["observations"]
    by_id = {as_text(item.get("PuRe-ID")): item for item in observations}
    results = []
    for row in rows:
        item_id = as_text(row.get("PuRe-ID"))
        observation = by_id.get(item_id)
        hits = validated_hits(observation) if observation else []
        results.append(
            {
                "PuRe-ID": item_id,
                "DOI": as_text(row.get("DOI")).lstrip("/"),
                "status": "checked_wiley_browser_evidence" if observation else "not_applicable",
                "found": bool(hits),
                "doi_found": bool(hits),
                "title_found": False,
                "hits": hits,
                "provider_summary": f"wiley-browser-data-availability: {len(hits)}",
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
