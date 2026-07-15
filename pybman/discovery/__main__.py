"""Command line interface: ``python -m pybman.discovery <DOI|ORCID>``.

Exit codes follow grep semantics: 0 = datasets found, 1 = none found,
2 = invalid identifier.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .aggregator import DataDiscovery
from .google import google_dataset_search_url
from .identifiers import normalize_doi, normalize_orcid
from .models import DiscoveryReport


def _report(identifier: str, discovery: DataDiscovery, limit: int) -> DiscoveryReport | None:
    try:
        return discovery.for_doi(normalize_doi(identifier), limit=limit)
    except ValueError:
        pass
    try:
        return discovery.for_orcid(normalize_orcid(identifier), limit=limit)
    except ValueError:
        return None


def _print_text(report: DiscoveryReport) -> None:
    print(f"{report.query_type}: {report.query}")
    print(f"providers: {report.summary()}")
    hits = report.hits
    if not hits:
        print("no datasets found")
    for hit in hits:
        parts = [hit.provider, hit.pid]
        if hit.title:
            parts.append(hit.title)
        if hit.publisher:
            parts.append(f"({hit.publisher}{f', {hit.year}' if hit.year else ''})")
        if hit.relation:
            parts.append(f"[{hit.relation}]")
        print("  " + "  ".join(parts))
    print(f"manual check: {google_dataset_search_url(report.query)}")


def _print_json(report: DiscoveryReport) -> None:
    payload = {
        "query": report.query,
        "query_type": report.query_type,
        "found": report.found,
        "hits": [
            {k: v for k, v in dataclasses.asdict(hit).items() if k != "raw"} for hit in report.hits
        ],
        "results": [
            {
                "provider": r.provider,
                "total": r.total,
                "error": r.error,
                "hits": len(r.hits),
            }
            for r in report.results
        ],
        "google_dataset_search": google_dataset_search_url(report.query),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pybman.discovery",
        description="Check whether research datasets exist for a DOI or an ORCID iD.",
    )
    parser.add_argument("identifier", help="a publication DOI or a researcher ORCID iD")
    parser.add_argument("--json", action="store_true", help="machine-readable JSON output")
    parser.add_argument("--limit", type=int, default=100, help="max hits per provider")
    parser.add_argument("--crossref-mailto", help="contact email for the Crossref polite pool")
    parser.add_argument("--openaire-token", help="OpenAIRE access token (raises rate limits)")
    args = parser.parse_args(argv)

    discovery = DataDiscovery(
        crossref_mailto=args.crossref_mailto, openaire_token=args.openaire_token
    )
    report = _report(args.identifier, discovery, args.limit)
    if report is None:
        print(
            f"error: {args.identifier!r} is neither a valid DOI nor an ORCID iD",
            file=sys.stderr,
        )
        return 2
    if args.json:
        _print_json(report)
    else:
        _print_text(report)
    return 0 if report.found else 1


if __name__ == "__main__":
    sys.exit(main())
