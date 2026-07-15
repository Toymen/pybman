"""Merge audited discovery snapshots without losing successful provider hits."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def as_text(value: Any) -> str:
    return str(value or "").strip()


def hit_key(hit: dict[str, Any]) -> tuple[str, str]:
    return as_text(hit.get("pid_type")), as_text(hit.get("pid")).casefold()


def merge_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latest = dict(rows[-1])
    hits: dict[tuple[str, str], dict[str, Any]] = {}
    summaries: list[str] = []
    errors: list[str] = []
    for row in rows:
        summary = as_text(row.get("provider_summary"))
        if summary and summary not in summaries:
            summaries.append(summary)
        error = as_text(row.get("provider_errors"))
        if error and error not in errors:
            errors.append(error)
        for hit in row.get("hits") or []:
            key = hit_key(hit)
            if not key[1]:
                continue
            candidate = dict(hit)
            existing = hits.get(key)
            if existing is None:
                hits[key] = candidate
                continue
            methods = {
                method
                for value in (
                    existing.get("discovery_method"),
                    candidate.get("discovery_method"),
                )
                for method in as_text(value).split("+")
                if method
            }
            existing["discovery_method"] = "+".join(sorted(methods))
    latest["hits"] = list(hits.values())
    latest["found"] = bool(hits)
    latest["doi_found"] = any(bool(row.get("doi_found")) for row in rows)
    latest["title_found"] = any(bool(row.get("title_found")) for row in rows)
    latest["provider_summary"] = " || ".join(summaries)
    latest["provider_errors"] = " | ".join(errors)
    return latest


def main() -> int:
    if len(sys.argv) < 4:
        print(
            "Usage: merge_discovery_results.py <input1.json> <input2.json> "
            "[inputN.json ...] <output.json>",
            file=sys.stderr,
        )
        return 2
    input_paths = [Path(value) for value in sys.argv[1:-1]]
    output_path = Path(sys.argv[-1])
    payloads = [json.loads(path.read_text(encoding="utf8")) for path in input_paths]
    by_file = [
        {as_text(row.get("PuRe-ID")): row for row in payload.get("results") or []}
        for payload in payloads
    ]
    item_ids = list(by_file[-1])
    results = [
        merge_rows([mapping[item_id] for mapping in by_file if item_id in mapping])
        for item_id in item_ids
    ]
    output = dict(payloads[-1])
    output["merged_from"] = [str(path) for path in input_paths]
    output["provider_found_rows"] = sum(bool(row.get("found")) for row in results)
    output["title_found_rows"] = sum(bool(row.get("title_found")) for row in results)
    output["results"] = results
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
