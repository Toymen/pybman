"""Discover data repositories whose README explicitly identifies a publication DOI."""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

from pybman.discovery.matching import normalize_text, title_tokens
from tools.research_data_enrichment.discover_github_data_repositories import (
    ELIGIBLE_GENRES,
    GitHubClient,
    as_text,
    data_paths,
)

DATA_CONTEXT_WORDS = {
    "data",
    "dataset",
    "replication",
    "reproducibility",
    "benchmark",
    "corpus",
}


def author_surnames(value: str) -> set[str]:
    return {
        normalize_text(name).split()[-1]
        for name in value.split(";")
        if normalize_text(name).split()
    }


def publication_context_in_readme(row: dict[str, Any], readme: str) -> bool:
    doi = as_text(row.get("DOI")).casefold().lstrip("/")
    normalized = normalize_text(readme[:12_000])
    if not doi or doi not in readme[:12_000].casefold():
        return False
    publication_authors = author_surnames(as_text(row.get("Autor:innen")))
    author_overlap = {surname for surname in publication_authors if surname in normalized}
    context = DATA_CONTEXT_WORDS & set(normalized.split())
    publication_title = set(title_tokens(as_text(row.get("Titel"))))
    title_coverage = (
        len(publication_title & set(normalized.split())) / len(publication_title)
        if publication_title
        else 0
    )
    required_authors = 1 if len(publication_authors) <= 2 else 2
    return bool(context) and len(author_overlap) >= required_authors and title_coverage >= 0.6


def repository_hit(
    client: GitHubClient, full_name: str, row: dict[str, Any]
) -> dict[str, Any] | None:
    repository = client.get(f"repos/{full_name}")
    branch = as_text(repository.get("default_branch"))
    tree = client.get(f"repos/{full_name}/git/trees/{branch}", recursive="1")
    paths = data_paths(tree.get("tree") or [])
    if not paths:
        return None
    readme_payload = client.get(f"repos/{full_name}/readme")
    try:
        readme = base64.b64decode(as_text(readme_payload.get("content"))).decode(
            "utf8", errors="replace"
        )
    except ValueError:
        return None
    if not publication_context_in_readme(row, readme):
        return None
    url = as_text(repository.get("html_url"))
    return {
        "provider": "github-doi-data",
        "pid": full_name,
        "pid_type": "github-repository",
        "title": f"Data repository for {as_text(row.get('Titel'))}",
        "publisher": "GitHub",
        "relation": "verified-readme-doi-author-and-data-files",
        "url": url,
        "discovery_method": "github-doi-author-context-tree-audit",
        "evidence": (
            "README contains publication DOI, data/replication context, title and author "
            f"evidence; repository tree contains {len(paths)} structured data file(s): "
            f"{', '.join(paths[:8])}"
        ),
    }


def process(client: GitHubClient, row: dict[str, Any]) -> list[dict[str, Any]]:
    doi = as_text(row.get("DOI")).lstrip("/")
    if as_text(row.get("Genre")) not in ELIGIBLE_GENRES or not doi:
        return []
    payload = client.get("search/code", q=f'"{doi}" filename:README', per_page="20")
    repositories: list[str] = []
    for item in payload.get("items") or []:
        full_name = as_text((item.get("repository") or {}).get("full_name"))
        if full_name and full_name not in repositories:
            repositories.append(full_name)
    hits = []
    for full_name in repositories:
        try:
            hit = repository_hit(client, full_name, row)
        except requests.RequestException:
            continue
        if hit:
            hits.append(hit)
    return hits


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_github_doi_repositories.py <publications.json> <results.json>")
        return 2
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(input_path.read_text(encoding="utf8"))["publications"]["rows"]
    client = GitHubClient(token)
    results = []
    for index, row in enumerate(rows, start=1):
        started = time.time()
        try:
            hits = process(client, row)
            error = ""
        except Exception as exc:
            hits = []
            error = str(exc)
        results.append(
            {
                "PuRe-ID": as_text(row.get("PuRe-ID")),
                "DOI": as_text(row.get("DOI")),
                "status": "checked_github_doi" if not error else "error",
                "found": bool(hits),
                "doi_found": bool(hits),
                "title_found": False,
                "hits": hits,
                "provider_summary": f"github-doi-data: {len(hits)}",
                "provider_errors": error,
                "elapsed_s": round(time.time() - started, 2),
            }
        )
        if index % 20 == 0 or index == len(rows):
            print(
                f"{index}/{len(rows)}; found={sum(result['found'] for result in results)}; "
                f"errors={sum(result['status'] == 'error' for result in results)}",
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
