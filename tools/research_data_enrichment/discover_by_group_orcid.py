"""Find datasets through ORCIDs resolved from PuRe research-group leaders."""

from __future__ import annotations

import dataclasses
import json
import sys
import time
from collections import Counter, defaultdict
from contextlib import suppress
from pathlib import Path
from typing import Any

import requests

from pybman.discovery import DataCiteProvider, OrcidProvider, normalize_doi
from pybman.discovery.matching import normalize_text, title_match_score, title_tokens

ORCID_SEARCH_URL = "https://pub.orcid.org/v3.0/search/"
ADMIN_TAGS = {"dp", "externdp", "preprint"}
TAG_ALIASES = {
    "gloeckner": "glöckner",
    "glöckner": "glöckner",
    "gueth": "güth",
    "güth": "güth",
}


def as_text(value: Any) -> str:
    return str(value or "").strip()


def tags(value: Any) -> tuple[str, ...]:
    normalized = []
    for raw in as_text(value).split(";"):
        tag = raw.strip().casefold()
        if not tag or tag in ADMIN_TAGS:
            continue
        canonical = TAG_ALIASES.get(tag, tag)
        if canonical not in normalized:
            normalized.append(canonical)
    return tuple(normalized)


def authors(value: Any) -> tuple[str, ...]:
    return tuple(part.strip() for part in as_text(value).split(";") if part.strip())


def group_leaders(rows: list[dict[str, Any]]) -> dict[str, str]:
    frequencies: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        for tag in tags(row.get("Forschungsgruppen-Tags")):
            frequencies[tag].update(authors(row.get("Autor:innen")))
    leaders = {}
    for tag, counts in frequencies.items():
        surname_matches = [
            (name, count)
            for name, count in counts.items()
            if normalize_text(name).split()[-1:] == normalize_text(tag).split()[-1:]
        ]
        ranked = surname_matches or list(counts.items())
        leaders[tag] = max(ranked, key=lambda item: item[1])[0]
    return leaders


def person_parts(name: str) -> tuple[str, str]:
    parts = name.split()
    return " ".join(parts[:-1]), parts[-1]


def orcid_search(session: requests.Session, query: str) -> list[str]:
    response = session.get(
        ORCID_SEARCH_URL,
        params={"q": query},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return [
        as_text(result.get("orcid-identifier", {}).get("path"))
        for result in response.json().get("result") or []
        if as_text(result.get("orcid-identifier", {}).get("path"))
    ]


def publication_dois(rows: list[dict[str, Any]]) -> set[str]:
    result = set()
    for row in rows:
        with suppress(ValueError):
            result.add(normalize_doi(as_text(row.get("DOI"))))
    return result


def orcid_work_dois(session: requests.Session, orcid: str) -> set[str]:
    response = session.get(
        f"https://pub.orcid.org/v3.0/{orcid}/works",
        headers={"Accept": "application/vnd.orcid+json"},
        timeout=30,
    )
    response.raise_for_status()
    result = set()
    for group in response.json().get("group") or []:
        for external_id in (group.get("external-ids") or {}).get("external-id") or []:
            if as_text(external_id.get("external-id-type")).casefold() != "doi":
                continue
            with suppress(ValueError):
                result.add(normalize_doi(as_text(external_id.get("external-id-value"))))
    return result


def resolve_orcid(
    session: requests.Session, name: str, rows: list[dict[str, Any]]
) -> tuple[str | None, str]:
    given, family = person_parts(name)
    query = (
        f'family-name:"{family}" AND given-names:"{given}" '
        'AND affiliation-org-name:"Max Planck"'
    )
    matches = orcid_search(session, query)
    if len(matches) == 1:
        return matches[0], "unique exact-name and Max-Planck-affiliation match"
    fallback_query = f'family-name:"{family}" AND given-names:"{given.split()[0]}"'
    candidates = orcid_search(session, fallback_query)
    expected_dois = publication_dois(rows)
    verified = [
        orcid
        for orcid in candidates
        if expected_dois & orcid_work_dois(session, orcid)
    ]
    if len(verified) == 1:
        return verified[0], "exact-name ORCID verified by shared PuRe publication DOI"
    return None, (
        f"ORCID search unresolved: affiliation matches={len(matches)}, "
        f"name matches={len(candidates)}, DOI-verified={len(verified)}"
    )


def related_dois(raw: dict[str, Any]) -> set[str]:
    attributes = raw.get("attributes") or {}
    result: set[str] = set()
    for related in attributes.get("relatedIdentifiers") or []:
        if as_text(related.get("relatedIdentifierType")).casefold() != "doi":
            continue
        try:
            result.add(normalize_doi(as_text(related.get("relatedIdentifier"))))
        except ValueError:
            continue
    return result


def serialize_hit(hit: Any, relation: str, evidence: str) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in dataclasses.asdict(hit).items()
        if key != "raw" and value not in (None, "")
    }
    payload["relation"] = relation
    payload["discovery_method"] = "verified-group-leader-orcid"
    payload["orcid_evidence"] = evidence
    return payload


def match_hits(
    rows: list[dict[str, Any]], hits: list[Any], orcid: str, leader: str
) -> dict[str, list[dict[str, Any]]]:
    matched: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        publication_doi = ""
        with suppress(ValueError):
            publication_doi = normalize_doi(as_text(row.get("DOI")))
        publication_title = as_text(row.get("Titel"))
        for hit in hits:
            exact_doi = bool(publication_doi and publication_doi in related_dois(dict(hit.raw)))
            score = title_match_score(publication_title, as_text(hit.title))
            exact_title = score >= 0.9 and len(title_tokens(publication_title)) >= 4
            if not exact_doi and not exact_title:
                continue
            relation = "verified-orcid-doi-relation" if exact_doi else "verified-orcid-title-match"
            evidence = (
                f"ORCID {orcid} uniquely resolved for group leader {leader}; "
                f"publication match={'DOI relation' if exact_doi else f'title score {score:.2f}'}"
            )
            matched[as_text(row.get("PuRe-ID"))].append(serialize_hit(hit, relation, evidence))
    return matched


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: discover_by_group_orcid.py <publications.json> <results.json>")
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    payload = json.loads(input_path.read_text(encoding="utf8"))
    rows = payload["publications"]["rows"]
    leaders = group_leaders(rows)
    rows_by_group = {
        tag: [row for row in rows if tag in tags(row.get("Forschungsgruppen-Tags"))]
        for tag in leaders
    }
    session = requests.Session()
    session.headers["User-Agent"] = "pybman-group-orcid-discovery/1.0"
    all_matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    resolution: dict[str, dict[str, Any]] = {}
    for tag, leader in sorted(leaders.items()):
        try:
            orcid, evidence = resolve_orcid(session, leader, rows_by_group[tag])
            resolution[tag] = {"leader": leader, "orcid": orcid, "evidence": evidence}
            if not orcid:
                continue
            providers = [
                DataCiteProvider(session=session, timeout=30, retries=3),
                OrcidProvider(session=session, timeout=30, retries=3),
            ]
            hits = []
            for provider in providers:
                result = provider.datasets_for_orcid(orcid, limit=100)
                hits.extend(result.hits)
            matches = match_hits(rows_by_group[tag], hits, orcid, leader)
            for item_id, item_hits in matches.items():
                existing = {as_text(hit.get("url")).casefold() for hit in all_matches[item_id]}
                for hit in item_hits:
                    if as_text(hit.get("url")).casefold() not in existing:
                        all_matches[item_id].append(hit)
                        existing.add(as_text(hit.get("url")).casefold())
            print(f"{tag}: ORCID={orcid}; datasets={len(hits)}; matched={len(matches)}", flush=True)
        except Exception as exc:
            resolution[tag] = {"leader": leader, "orcid": None, "evidence": str(exc)}
            print(f"{tag}: error: {exc}", flush=True)
    results = []
    for row in rows:
        item_id = as_text(row.get("PuRe-ID"))
        item_hits = all_matches.get(item_id, [])
        results.append(
            {
                "PuRe-ID": item_id,
                "DOI": as_text(row.get("DOI")),
                "status": "checked_group_orcid",
                "found": bool(item_hits),
                "doi_found": False,
                "title_found": bool(item_hits),
                "hits": item_hits,
                "provider_summary": f"group-orcid: {len(item_hits)}",
                "provider_errors": "",
                "elapsed_s": 0,
            }
        )
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_rows": len(rows),
        "provider_found_rows": sum(result["found"] for result in results),
        "orcid_resolution": resolution,
        "results": results,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
