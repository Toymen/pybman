"""Propagate audited data links to strongly identified publication versions."""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import requests

PURE_ITEM_URL = "https://pure.mpg.de/rest/items/{item_id}"


def as_text(value: Any) -> str:
    return str(value or "").strip()


def normalized_tokens(value: Any) -> list[str]:
    normalized = (
        unicodedata.normalize("NFKD", as_text(value).replace("ß", "ss").replace("ẞ", "SS"))
        .encode("ascii", "ignore")
        .decode()
    )
    return re.findall(r"[a-z0-9]+", normalized.casefold())


def author_surnames(value: Any) -> set[str]:
    surnames = set()
    for author in as_text(value).split(";"):
        tokens = normalized_tokens(author.split(",", 1)[0])
        if tokens:
            surnames.add(tokens[-1])
    return surnames


def title_jaccard(left: Any, right: Any) -> float:
    left_tokens = set(normalized_tokens(left))
    right_tokens = set(normalized_tokens(right))
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def strong_version_match(
    candidate: dict[str, Any], source: dict[str, Any], duplicate: bool
) -> bool:
    candidate_authors = author_surnames(candidate.get("Autor:innen"))
    source_authors = author_surnames(source.get("Autor:innen"))
    if len(candidate_authors) < 2 or candidate_authors != source_authors:
        return False
    score = title_jaccard(candidate.get("Titel"), source.get("Titel"))
    candidate_prefix = normalized_tokens(candidate.get("Titel"))[:5]
    source_prefix = normalized_tokens(source.get("Titel"))[:5]
    return (duplicate and score >= 0.2) or (candidate_prefix == source_prefix and score >= 0.55)


def pure_duplicate_flag(item_id: str) -> tuple[bool, str]:
    try:
        response = requests.get(
            PURE_ITEM_URL.format(item_id=item_id),
            headers={"User-Agent": "pybman-publication-version-discovery/1.0"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        message = as_text(payload.get("message"))
        duplicate = payload.get("publicState") == "WITHDRAWN" and "dublette" in message.casefold()
        return duplicate, f"publicState={payload.get('publicState')}; message={message or '-'}"
    except Exception as exc:
        return False, f"PuRe lookup failed: {exc}"


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "Usage: discover_publication_versions.py "
            "<publications.json> <audited-research-data.json> <results.json>"
        )
        return 2
    publications_path, audited_path, output_path = map(Path, sys.argv[1:])
    rows = json.loads(publications_path.read_text(encoding="utf8"))["publications"]["rows"]
    audited = json.loads(audited_path.read_text(encoding="utf8"))["rows"]
    by_id = {as_text(row.get("PuRe-ID")): row for row in rows}
    positive = [row for row in audited if row.get("research_data") == "ja"]
    positive_ids = {as_text(row.get("pure_id")) for row in positive}
    results = []
    for candidate in rows:
        item_id = as_text(candidate.get("PuRe-ID"))
        hits: list[dict[str, Any]] = []
        evidence = ""
        if item_id not in positive_ids:
            same_author_sources = [
                source_audit
                for source_audit in positive
                if author_surnames(candidate.get("Autor:innen"))
                == author_surnames(
                    (by_id.get(as_text(source_audit.get("pure_id"))) or {}).get("Autor:innen")
                )
                and len(author_surnames(candidate.get("Autor:innen"))) >= 2
            ]
            direct_sources = [
                source_audit
                for source_audit in same_author_sources
                if strong_version_match(
                    candidate,
                    by_id.get(as_text(source_audit.get("pure_id"))) or {},
                    False,
                )
            ]
            duplicate = False
            pure_evidence = "PuRe duplicate lookup not required"
            candidate_sources = direct_sources
            if not candidate_sources and any(
                title_jaccard(
                    candidate.get("Titel"),
                    (by_id.get(as_text(source_audit.get("pure_id"))) or {}).get("Titel"),
                )
                >= 0.2
                for source_audit in same_author_sources
            ):
                duplicate, pure_evidence = pure_duplicate_flag(item_id)
                if duplicate:
                    candidate_sources = same_author_sources
            for source_audit in candidate_sources:
                source_id = as_text(source_audit.get("pure_id"))
                source = by_id.get(source_id) or {}
                if not strong_version_match(candidate, source, duplicate):
                    continue
                score = title_jaccard(candidate.get("Titel"), source.get("Titel"))
                evidence = (
                    f"same normalized author set; title Jaccard={score:.2f}; "
                    f"source PuRe-ID={source_id}; {pure_evidence}"
                )
                for link in source_audit.get("accepted_links") or []:
                    hits.append(
                        {
                            "provider": "publication-version",
                            "pid": as_text(link.get("canonical_url") or link.get("url")),
                            "pid_type": "url",
                            "title": as_text(link.get("dataset_title"))
                            or f"Research data for publication version {source_id}",
                            "publisher": as_text(link.get("provider") or link.get("source")),
                            "relation": "strongly-identified-publication-version",
                            "url": as_text(link.get("canonical_url") or link.get("url")),
                            "discovery_method": "audited-link-publication-version-propagation",
                            "evidence": evidence,
                        }
                    )
                break
        unique = {as_text(hit.get("url")).casefold(): hit for hit in hits if hit.get("url")}
        results.append(
            {
                "PuRe-ID": item_id,
                "DOI": as_text(candidate.get("DOI")).lstrip("/"),
                "status": "checked_publication_versions",
                "found": bool(unique),
                "doi_found": False,
                "title_found": bool(unique),
                "hits": list(unique.values()),
                "provider_summary": f"publication-version: {len(unique)}",
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
