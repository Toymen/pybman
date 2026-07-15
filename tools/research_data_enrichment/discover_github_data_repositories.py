"""Discover publication-linked GitHub repositories that contain real data files."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

from pybman.discovery.matching import normalize_text, title_tokens

GITHUB_API = "https://api.github.com"
ELIGIBLE_GENRES = {"ARTICLE", "PAPER", "CONFERENCE_PAPER"}
DATA_PATH_RE = re.compile(
    r"\.(?:csv|tsv|xlsx?|sav|dta|rds|rdata|parquet|feather|mat|h5|hdf5|sqlite)$",
    re.IGNORECASE,
)
JSON_DATA_PATH_RE = re.compile(
    r"(?:^|/)(?:data|dataset|datasets|results?|responses?|observations?|survey|experiment|"
    r"benchmark|corpus|splits?)(?:/|[-_]).*\.json$",
    re.IGNORECASE,
)


def as_text(value: Any) -> str:
    return str(value or "").strip()


def data_paths(tree: list[dict[str, Any]]) -> list[str]:
    return [
        as_text(item.get("path"))
        for item in tree
        if as_text(item.get("type")) == "blob"
        and (
            DATA_PATH_RE.search(as_text(item.get("path")))
            or JSON_DATA_PATH_RE.search(as_text(item.get("path")))
        )
    ]


def exact_title_in_readme(title: str, readme: str) -> bool:
    normalized_title = normalize_text(title)
    primary_context = readme[:6000]
    return len(title_tokens(title)) >= 4 and normalized_title in normalize_text(primary_context)


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "pybman-github-data-discovery/1.0",
            }
        )

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.session.get(f"{GITHUB_API}/{path.lstrip('/')}", params=params, timeout=30)
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset = int(response.headers.get("X-RateLimit-Reset", "0"))
            time.sleep(max(1, reset - int(time.time()) + 2))
            response = self.session.get(
                f"{GITHUB_API}/{path.lstrip('/')}", params=params, timeout=30
            )
        response.raise_for_status()
        return response.json()


def repository_hit(
    client: GitHubClient, full_name: str, title: str
) -> dict[str, Any] | None:
    repository = client.get(f"repos/{full_name}")
    default_branch = as_text(repository.get("default_branch"))
    tree = client.get(f"repos/{full_name}/git/trees/{default_branch}", recursive="1")
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
    if not exact_title_in_readme(title, readme):
        return None
    url = as_text(repository.get("html_url"))
    return {
        "provider": "github-data",
        "pid": full_name,
        "pid_type": "github-repository",
        "title": f"Data repository for {title}",
        "publisher": "GitHub",
        "relation": "verified-readme-title-and-data-files",
        "url": url,
        "discovery_method": "github-exact-title-and-tree-audit",
        "evidence": (
            f"README contains exact normalized publication title; repository tree contains "
            f"{len(paths)} structured data file(s): {', '.join(paths[:8])}"
        ),
    }


def process(client: GitHubClient, row: dict[str, Any]) -> list[dict[str, Any]]:
    title = as_text(row.get("Titel"))
    if as_text(row.get("Genre")) not in ELIGIBLE_GENRES or len(title_tokens(title)) < 4:
        return []
    query_title = title[:180].replace('"', "")
    payload = client.get("search/code", q=f'"{query_title}" filename:README', per_page="20")
    repositories = []
    for item in payload.get("items") or []:
        full_name = as_text((item.get("repository") or {}).get("full_name"))
        if full_name and full_name not in repositories:
            repositories.append(full_name)
    hits = []
    for full_name in repositories:
        try:
            hit = repository_hit(client, full_name, title)
        except requests.RequestException:
            continue
        if hit:
            hits.append(hit)
    return hits


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_github_data_repositories.py <publications.json> <results.json>")
        return 2
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    payload = json.loads(input_path.read_text(encoding="utf8"))
    rows = payload["publications"]["rows"]
    client = GitHubClient(token)
    results = []
    for index, row in enumerate(rows, start=1):
        started = time.time()
        try:
            hits = process(client, row)
            error = ""
            status = "checked_github"
        except Exception as exc:
            hits = []
            error = str(exc)
            status = "error"
        results.append(
            {
                "PuRe-ID": as_text(row.get("PuRe-ID")),
                "DOI": as_text(row.get("DOI")),
                "status": status,
                "found": bool(hits),
                "doi_found": False,
                "title_found": bool(hits),
                "hits": hits,
                "provider_summary": f"github-data: {len(hits)}",
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
