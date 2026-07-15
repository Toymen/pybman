"""Live tests against the real discovery APIs.

Disabled by default; enable with ``PYBMAN_LIVE_TESTS=1``. These need outbound
network access and tolerate service hiccups by design (the aggregator turns
provider failures into ``ProviderResult.error``).

The fixture DOI 10.1038/s41586-020-2649-2 is the NumPy paper, which has
well-known dataset links; the ORCID belongs to a researcher with published
datasets on DataCite.
"""

from __future__ import annotations

import os

import pytest

from pybman.discovery import DataDiscovery

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("PYBMAN_LIVE_TESTS") != "1",
        reason="live tests disabled (set PYBMAN_LIVE_TESTS=1 to enable)",
    ),
]

DOI = "10.1038/s41586-020-2649-2"
ORCID = "0000-0003-1419-2405"


def test_live_doi_lookup_runs_all_providers():
    report = DataDiscovery(crossref_mailto="pybman-tests@example.org").for_doi(DOI)
    assert {r.provider for r in report.results} == {
        "datacite",
        "openaire",
        "scholexplorer",
        "b2find",
        "crossref",
    }
    # At least one provider must be reachable and answer without error.
    assert any(r.ok for r in report.results), report.summary()


def test_live_orcid_lookup_runs_orcid_capable_providers():
    report = DataDiscovery().for_orcid(ORCID)
    assert {r.provider for r in report.results} == {"datacite", "openaire", "b2find", "orcid"}
    assert any(r.ok for r in report.results), report.summary()
