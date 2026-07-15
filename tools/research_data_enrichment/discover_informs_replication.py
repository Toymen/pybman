"""Discover and inspect official Management Science replication archives."""

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

LANDING_URL = "https://services.informs.org/dataset/mnsc/download.php"
DOWNLOAD_URL = "https://services.informs.org/dataset/action/download_process.php"
DATA_FILE_RE = re.compile(
    r"\.(?:csv|tsv|xlsx?|sav|dta|rds|rdata|fst|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)
DOCUMENTATION_ONLY_RE = re.compile(
    r"(?:variable[_ -]?dict(?:ionary)?|data[_ -]?dict(?:ionary)?|codebook|readme)",
    re.IGNORECASE,
)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def archive_data_members(content: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return [
                name
                for name in archive.namelist()
                if not name.startswith("__MACOSX/")
                and DATA_FILE_RE.search(name)
                and not DOCUMENTATION_ONLY_RE.search(Path(name).name)
            ]
    except zipfile.BadZipFile:
        return []


def fetch_archive(session: requests.Session, suffix: str) -> bytes:
    landing = session.get(LANDING_URL, params={"doi": suffix}, timeout=30)
    landing.raise_for_status()
    token = re.search(r'name="token" value="([^"]+)"', landing.text)
    if not token:
        return b""
    response = session.post(
        DOWNLOAD_URL,
        data={
            "doi": suffix,
            "token": token.group(1),
            "ack": "1",
            "email": "research-data-audit@example.com",
        },
        timeout=90,
    )
    response.raise_for_status()
    return response.content


def process(row: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    item_id = as_text(row.get("PuRe-ID"))
    doi = as_text(row.get("DOI")).lstrip("/")
    hits: list[dict[str, Any]] = []
    error = ""
    if doi.casefold().startswith("10.1287/mnsc."):
        suffix = doi.split("/", 1)[1]
        session = requests.Session()
        session.headers["User-Agent"] = "pybman-informs-replication-audit/1.0"
        try:
            data_files = archive_data_members(fetch_archive(session, suffix))
            if data_files:
                hits.append(
                    {
                        "provider": "informs-replication",
                        "pid": suffix,
                        "pid_type": "publisher-replication-package",
                        "title": f"Management Science replication files for {doi}",
                        "publisher": "INFORMS",
                        "relation": "publisher-doi-replication-package-with-data-files",
                        "url": f"{LANDING_URL}?doi={suffix}",
                        "discovery_method": "informs-doi-archive-file-audit",
                        "evidence": (
                            f"Official DOI-specific archive contains {len(data_files)} "
                            f"research-data file(s): {', '.join(data_files[:8])}"
                        ),
                    }
                )
        except Exception as exc:
            error = str(exc)
    return {
        "PuRe-ID": item_id,
        "DOI": doi,
        "status": "checked_informs_replication" if not error else "error",
        "found": bool(hits),
        "doi_found": bool(hits),
        "title_found": False,
        "hits": hits,
        "provider_summary": f"informs-replication: {len(hits)}",
        "provider_errors": error,
        "elapsed_s": round(time.time() - started, 2),
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_informs_replication.py <publications.json> <results.json>")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
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
