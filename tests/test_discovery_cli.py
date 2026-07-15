"""Tests for the ``python -m pybman.discovery`` command line interface."""

from __future__ import annotations

import json

import pytest

from pybman.discovery.__main__ import main

DOI = "10.1038/s41586-020-2649-2"
ORCID = "0000-0003-1419-2405"


@pytest.fixture
def one_dataset(responses):
    """Mock every default provider; only DataCite returns a dataset."""
    responses.get(
        "https://api.datacite.org/dois",
        json={
            "data": [
                {
                    "id": "10.5281/zenodo.1",
                    "attributes": {
                        "doi": "10.5281/zenodo.1",
                        "titles": [{"title": "A dataset"}],
                        "publisher": "Zenodo",
                        "publicationYear": 2020,
                    },
                }
            ],
            "meta": {"total": 1},
        },
    )
    responses.get(
        "https://api.openaire.eu/graph/v1/researchProducts",
        json={"header": {"numFound": 0}, "results": []},
    )
    responses.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        json={"resultList": {"result": []}},
    )
    responses.get(
        "https://api.scholexplorer.openaire.eu/v3/Links",
        json={"totalLinks": 0, "totalPages": 0, "result": []},
    )
    responses.get(
        "https://b2find.eudat.eu/api/3/action/package_search",
        json={"success": True, "result": {"count": 0, "results": []}},
    )
    responses.get(f"https://api.crossref.org/works/{DOI}", status=404)


def test_cli_doi_found_prints_hits_and_exits_zero(one_dataset, capsys):
    assert main([DOI]) == 0
    out = capsys.readouterr().out
    assert "10.5281/zenodo.1" in out
    assert "datacite" in out


def test_cli_orcid_detected_automatically(responses, capsys):
    responses.get("https://api.datacite.org/dois", json={"data": [], "meta": {"total": 0}})
    responses.get(
        "https://api.openaire.eu/graph/v1/researchProducts",
        json={"header": {"numFound": 0}, "results": []},
    )
    responses.get(
        "https://b2find.eudat.eu/api/3/action/package_search",
        json={"success": True, "result": {"count": 0, "results": []}},
    )
    responses.get(f"https://pub.orcid.org/v3.0/{ORCID}/works", json={"group": []})
    exit_code = main([ORCID])
    # exit code 1 signals "no datasets found" (grep-style semantics)
    assert exit_code == 1
    assert "no datasets found" in capsys.readouterr().out


def test_cli_json_output(one_dataset, capsys):
    assert main(["--json", DOI]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == DOI
    assert payload["query_type"] == "doi"
    assert payload["found"] is True
    assert payload["hits"][0]["pid"] == "10.5281/zenodo.1"
    assert {r["provider"] for r in payload["results"]} == {
        "datacite",
        "europepmc",
        "openaire",
        "scholexplorer",
        "b2find",
        "crossref",
    }


def test_cli_invalid_identifier_exits_two(capsys):
    assert main(["not-an-identifier"]) == 2
    assert "neither a valid DOI nor an ORCID" in capsys.readouterr().err
