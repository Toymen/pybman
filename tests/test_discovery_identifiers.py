"""Tests for identifier normalization used by the discovery package."""

from __future__ import annotations

import pytest

from pybman.discovery import normalize_doi, normalize_orcid

# -- DOI ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "10.5438/0012",
        "doi:10.5438/0012",
        "DOI:10.5438/0012",
        "https://doi.org/10.5438/0012",
        "http://dx.doi.org/10.5438/0012",
        "  10.5438/0012  ",
    ],
)
def test_normalize_doi_variants(raw):
    assert normalize_doi(raw) == "10.5438/0012"


def test_normalize_doi_lowercases():
    # DOIs are case-insensitive; normalize to lowercase for comparisons.
    assert normalize_doi("10.1594/PANGAEA.913496") == "10.1594/pangaea.913496"


@pytest.mark.parametrize("raw", ["", "not-a-doi", "11.1234/abc", "10./abc", "10.1234"])
def test_normalize_doi_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_doi(raw)


# -- ORCID iD -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "0000-0003-1419-2405",
        "https://orcid.org/0000-0003-1419-2405",
        "http://orcid.org/0000-0003-1419-2405",
        "orcid.org/0000-0003-1419-2405",
        " 0000-0003-1419-2405 ",
    ],
)
def test_normalize_orcid_variants(raw):
    assert normalize_orcid(raw) == "0000-0003-1419-2405"


def test_normalize_orcid_checksum_x_uppercased():
    assert normalize_orcid("0000-0002-1825-009x") == "0000-0002-1825-009X"


@pytest.mark.parametrize(
    "raw",
    ["", "0000-0003-1419", "0000-0003-1419-24055", "abcd-0003-1419-2405", "10.5438/0012"],
)
def test_normalize_orcid_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_orcid(raw)
