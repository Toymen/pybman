"""Validate aggregated discovery hits against authoritative source metadata."""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

TRUSTED_EVIDENCE_PROVIDERS = {
    "datacite",
    "b2find",
    "osf",
    "europepmc",
    "pure-file",
    "pure-fulltext",
    "publisher-supplement",
    "aea",
    "github-data",
    "openalex-fulltext",
    "harvard-dataverse",
    "github-doi-data",
    "zenodo-replication",
    "informs-replication",
    "elife-data-availability",
    "pure-duplicate-file",
    "pure-duplicate-fulltext",
    "unpaywall-fulltext",
    "wiley-browser-data-availability",
    "publication-version",
    "cambridge-osf-data",
    "degruyter-browser-data-availability",
    "huggingface-arxiv-dataset",
    "osf-exact-title-data",
}
DATACITE_URL = "https://api.datacite.org/dois/{doi}"


def as_text(value: Any) -> str:
    return str(value or "").strip()


def datacite_resource_type(doi: str) -> tuple[str | None, str]:
    try:
        response = requests.get(
            DATACITE_URL.format(doi=quote(doi, safe="")),
            timeout=15,
            headers={"User-Agent": "pybman-research-data-validation/1.0"},
        )
    except requests.RequestException as exc:
        return None, f"DataCite request failed: {exc}"
    if response.status_code == 404:
        return None, "DOI has no DataCite dataset metadata record"
    if not response.ok:
        return None, f"DataCite returned HTTP {response.status_code}"
    try:
        attributes = response.json()["data"]["attributes"]
    except (KeyError, TypeError, ValueError):
        return None, "DataCite returned invalid metadata"
    resource_type = as_text((attributes.get("types") or {}).get("resourceTypeGeneral"))
    return resource_type or None, f"DataCite resourceTypeGeneral={resource_type or 'missing'}"


def validate_hit(
    hit: dict[str, Any], type_cache: dict[str, tuple[str | None, str]]
) -> tuple[bool, str]:
    provider = as_text(hit.get("provider"))
    if provider in TRUSTED_EVIDENCE_PROVIDERS:
        return True, f"trusted {provider} dataset evidence"
    if as_text(hit.get("pid_type")) != "doi":
        return False, "aggregator hit has no verifiable dataset DOI"
    doi = as_text(hit.get("pid")).casefold()
    resource_type, evidence = type_cache.get(doi, (None, "DataCite validation missing"))
    return resource_type == "Dataset", evidence


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: validate_discovery_results.py <input.json> <output.json>",
            file=sys.stderr,
        )
        return 2
    input_path, output_path = map(Path, sys.argv[1:])
    payload = json.loads(input_path.read_text(encoding="utf8"))
    dois = sorted(
        {
            as_text(hit.get("pid")).casefold()
            for row in payload.get("results") or []
            for hit in row.get("hits") or []
            if as_text(hit.get("provider")) not in TRUSTED_EVIDENCE_PROVIDERS
            and as_text(hit.get("pid_type")) == "doi"
            and as_text(hit.get("pid"))
        }
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        validated = pool.map(datacite_resource_type, dois)
    type_cache = dict(zip(dois, validated, strict=True))

    accepted_total = 0
    rejected_total = 0
    for row in payload.get("results") or []:
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for hit in row.get("hits") or []:
            valid, evidence = validate_hit(hit, type_cache)
            audited = dict(hit)
            audited["source_validation"] = evidence
            if valid:
                accepted.append(audited)
            else:
                rejected.append(audited)
        row["hits"] = accepted
        row["rejected_hits"] = rejected
        row["found"] = bool(accepted)
        row["validation_summary"] = (
            f"accepted={len(accepted)}; rejected_non_dataset={len(rejected)}"
        )
        accepted_total += len(accepted)
        rejected_total += len(rejected)

    payload["source_validation"] = {
        "rule": (
            "DataCite/B2FIND/OSF/Europe PMC direct evidence accepted; other DOI hits "
            "require DataCite resourceTypeGeneral=Dataset"
        ),
        "accepted_hits": accepted_total,
        "rejected_non_dataset_hits": rejected_total,
        "datacite_dois_checked": len(dois),
    }
    payload["provider_found_rows"] = sum(
        bool(row.get("found")) for row in payload.get("results") or []
    )
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
