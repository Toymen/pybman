"""Discover public Hugging Face datasets linked by an exact arXiv tag."""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ARXIV_DOI_RE = re.compile(r"^10\.48550/arxiv\.([0-9]{4}\.[0-9]{4,5})$", re.I)
DATA_FILE_RE = re.compile(
    r"\.(?:parquet|arrow|csv|tsv|jsonl|ndjson|json|sqlite|h5|hdf5)$", re.I
)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def arxiv_id_from_doi(doi: str) -> str | None:
    match = ARXIV_DOI_RE.fullmatch(as_text(doi).lstrip("/"))
    return match.group(1) if match else None


def discover_datasets(
    session: requests.Session, arxiv_id: str
) -> list[dict[str, Any]]:
    tag = f"arxiv:{arxiv_id}"
    response = session.get(
        "https://huggingface.co/api/datasets", params={"filter": tag}, timeout=30
    )
    response.raise_for_status()
    hits = []
    for candidate in response.json():
        repo_id = as_text(candidate.get("id"))
        tags = {as_text(item).casefold() for item in candidate.get("tags") or []}
        if not repo_id or tag.casefold() not in tags:
            continue
        detail_response = session.get(
            f"https://huggingface.co/api/datasets/{quote(repo_id, safe='/')}",
            timeout=30,
        )
        detail_response.raise_for_status()
        detail = detail_response.json()
        if detail.get("private") or detail.get("gated") or detail.get("disabled"):
            continue
        data_files = sorted(
            {
                as_text(record.get("rfilename"))
                for record in detail.get("siblings") or []
                if DATA_FILE_RE.search(as_text(record.get("rfilename")))
            }
        )
        if not data_files:
            continue
        card = detail.get("cardData") or {}
        title = as_text(card.get("pretty_name")) or repo_id.rsplit("/", 1)[-1]
        hits.append(
            {
                "provider": "huggingface-arxiv-dataset",
                "pid": repo_id,
                "pid_type": "huggingface-dataset",
                "title": title,
                "publisher": "Hugging Face Datasets",
                "relation": "exact-arxiv-tag-with-verified-data-files",
                "url": f"https://huggingface.co/datasets/{repo_id}",
                "discovery_method": "huggingface-exact-arxiv-tag-api-audit",
                "evidence": (
                    f"Public, ungated Hugging Face dataset has exact tag {tag} and "
                    f"contains {len(data_files)} structured data file(s): "
                    f"{', '.join(data_files[:12])}"
                ),
            }
        )
    return hits


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: discover_huggingface_arxiv_datasets.py "
            "<publications.json> <results.json>"
        )
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    session = requests.Session()
    session.headers["User-Agent"] = "pybman-huggingface-dataset-discovery/1.0"
    results = []
    for row in rows:
        item_id = as_text(row.get("PuRe-ID"))
        doi = as_text(row.get("DOI")).lstrip("/")
        arxiv_id = arxiv_id_from_doi(doi)
        started = time.time()
        hits: list[dict[str, Any]] = []
        error = ""
        if arxiv_id:
            try:
                hits = discover_datasets(session, arxiv_id)
            except (TypeError, ValueError, requests.RequestException) as exc:
                error = str(exc)
        results.append(
            {
                "PuRe-ID": item_id,
                "DOI": doi,
                "status": "checked_huggingface_arxiv" if arxiv_id else "not_applicable",
                "found": bool(hits),
                "doi_found": bool(hits),
                "title_found": False,
                "hits": hits,
                "provider_summary": f"huggingface-arxiv-dataset: {len(hits)}",
                "provider_errors": error,
                "elapsed_s": round(time.time() - started, 2),
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
