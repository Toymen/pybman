"""Discover verifiably downloadable structured publisher supplement files."""

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
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ELSEVIER_PII_RE = re.compile(r"(?:PII:|/pii/)(S[0-9A-Z]+)", re.IGNORECASE)
STRUCTURED_EXTENSIONS = ("xlsx", "xls", "csv", "zip", "sav", "dta", "json", "rdata")
STRUCTURED_MEMBER_RE = re.compile(
    r"\.(?:xlsx?|csv|tsv|sav|dta|json|rds|rdata|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "pybman-structured-supplement-discovery/1.0"
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def elsevier_pii(crossref_message: dict[str, Any]) -> str | None:
    values = [as_text(link.get("URL")) for link in crossref_message.get("link") or []] + [
        as_text((crossref_message.get("resource") or {}).get("primary", {}).get("URL"))
    ]
    for value in values:
        match = ELSEVIER_PII_RE.search(value)
        if match:
            return match.group(1).upper()
    return None


def structured_payload(extension: str, content: bytes) -> tuple[bool, str]:
    if len(content) < 100:
        return False, "response too small"
    if extension != "zip":
        return True, f"downloadable .{extension} structured supplement"
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = [name for name in archive.namelist() if STRUCTURED_MEMBER_RE.search(name)]
    except zipfile.BadZipFile:
        return False, "invalid ZIP response"
    if not members:
        return False, "ZIP contains no recognized structured data file"
    return True, f"ZIP contains {len(members)} structured data file(s)"


def probe_elsevier_supplements(
    session: requests.Session, pii: str, publication_title: str
) -> list[dict[str, Any]]:
    hits = []
    for sequence in range(1, 7):
        for extension in STRUCTURED_EXTENSIONS:
            url = f"https://ars.els-cdn.com/content/image/1-s2.0-{pii}-mmc{sequence}.{extension}"
            response = session.get(url, timeout=20)
            if response.status_code == 404:
                continue
            if not response.ok:
                continue
            valid, evidence = structured_payload(extension, response.content)
            if not valid:
                continue
            hits.append(
                {
                    "provider": "publisher-supplement",
                    "pid": url,
                    "pid_type": "url",
                    "title": f"Structured supplementary data for {publication_title}",
                    "publisher": "Elsevier supplementary content",
                    "relation": "structured-supplement-file",
                    "url": url,
                    "discovery_method": "verified-publisher-supplement",
                    "evidence": f"HTTP {response.status_code}; {evidence}",
                }
            )
    return hits


def process(row: dict[str, Any]) -> dict[str, Any]:
    item_id = as_text(row.get("PuRe-ID"))
    doi = as_text(row.get("DOI"))
    started = time.time()
    if not doi or not doi.casefold().startswith("10.1016/"):
        return {
            "PuRe-ID": item_id,
            "DOI": doi,
            "status": "not_applicable",
            "found": False,
            "doi_found": False,
            "title_found": False,
            "hits": [],
            "provider_summary": "publisher-supplement: not Elsevier",
            "provider_errors": "",
            "elapsed_s": 0,
        }
    session = make_session()
    try:
        response = session.get(f"https://api.crossref.org/works/{quote(doi, safe='')}", timeout=30)
        response.raise_for_status()
        pii = elsevier_pii(response.json().get("message") or {})
        hits = probe_elsevier_supplements(session, pii, as_text(row.get("Titel"))) if pii else []
        return {
            "PuRe-ID": item_id,
            "DOI": doi,
            "status": "checked_structured_supplements",
            "found": bool(hits),
            "doi_found": bool(hits),
            "title_found": False,
            "hits": hits,
            "provider_summary": f"publisher-supplement: {len(hits)}",
            "provider_errors": "" if pii else "Crossref exposed no Elsevier PII",
            "elapsed_s": round(time.time() - started, 2),
        }
    except Exception as exc:
        return {
            "PuRe-ID": item_id,
            "DOI": doi,
            "status": "error",
            "found": False,
            "doi_found": False,
            "title_found": False,
            "hits": [],
            "provider_summary": "publisher-supplement: error",
            "provider_errors": str(exc),
            "elapsed_s": round(time.time() - started, 2),
        }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_structured_supplements.py <publications.json> <results.json>")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    payload = json.loads(input_path.read_text(encoding="utf8"))
    rows = payload["publications"]["rows"]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(process, row): row for row in rows}
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 25 == 0 or index == len(rows):
                print(
                    f"{index}/{len(rows)}; found={sum(result['found'] for result in results)}",
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
