"""Tests for the DataDiscovery aggregator and its report model."""

from __future__ import annotations

from pybman.discovery import (
    DataDiscovery,
    DatasetHit,
    DiscoveryError,
    DiscoveryReport,
    ProviderResult,
)

DOI = "10.1038/s41586-020-2649-2"
ORCID = "0000-0003-1419-2405"


class FakeProvider:
    """Deterministic provider double."""

    def __init__(
        self,
        name: str,
        hits: list[DatasetHit] | None = None,
        *,
        supports_doi: bool = True,
        supports_orcid: bool = True,
        supports_title: bool = False,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.supports_doi = supports_doi
        self.supports_orcid = supports_orcid
        self.supports_title = supports_title
        self._hits = hits or []
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def _result(self) -> ProviderResult:
        if self._error is not None:
            raise self._error
        return ProviderResult(provider=self.name, hits=list(self._hits), total=len(self._hits))

    def datasets_for_doi(self, doi: str, *, limit: int = 100) -> ProviderResult:
        self.calls.append(("doi", doi))
        return self._result()

    def datasets_for_orcid(self, orcid: str, *, limit: int = 100) -> ProviderResult:
        self.calls.append(("orcid", orcid))
        return self._result()

    def datasets_for_title(self, title, *, authors=(), year=None, limit=100):
        self.calls.append(("title", title))
        self.title_context = (authors, year, limit)
        return self._result()


def hit(provider: str, pid: str, **kwargs) -> DatasetHit:
    return DatasetHit(provider=provider, pid=pid, **kwargs)


def test_for_doi_queries_all_doi_capable_providers():
    a = FakeProvider("a", [hit("a", "10.1/x")])
    b = FakeProvider("b", supports_doi=False)
    report = DataDiscovery(providers=[a, b]).for_doi(f"https://doi.org/{DOI}")

    assert isinstance(report, DiscoveryReport)
    assert report.query == DOI.lower()
    assert report.query_type == "doi"
    # normalized DOI is passed through, non-DOI provider skipped
    assert a.calls == [("doi", DOI.lower())]
    assert b.calls == []
    assert [r.provider for r in report.results] == ["a"]


def test_for_orcid_queries_orcid_capable_providers():
    a = FakeProvider("a", supports_orcid=False)
    b = FakeProvider("b", [hit("b", "10.2/y")])
    report = DataDiscovery(providers=[a, b]).for_orcid(f"https://orcid.org/{ORCID}")
    assert report.query == ORCID
    assert report.query_type == "orcid"
    assert b.calls == [("orcid", ORCID)]
    assert a.calls == []


def test_provider_failure_is_captured_not_raised():
    ok = FakeProvider("ok", [hit("ok", "10.1/x")])
    boom = FakeProvider("boom", error=DiscoveryError("service down"))
    report = DataDiscovery(providers=[ok, boom]).for_doi(DOI)

    by_name = {r.provider: r for r in report.results}
    assert by_name["ok"].ok
    assert not by_name["boom"].ok
    assert "service down" in by_name["boom"].error
    assert report.found  # the ok provider still counts


def test_for_title_queries_capable_providers_with_context():
    title_provider = FakeProvider("titles", [hit("titles", "10.1/data")], supports_title=True)
    doi_only = FakeProvider("doi-only")
    report = DataDiscovery(providers=[title_provider, doi_only]).for_title(
        "  A   publication title ", authors=["Ada Lovelace"], year=2025, limit=7
    )

    assert report.query == "A publication title"
    assert report.query_type == "title"
    assert report.found is True
    assert title_provider.calls == [("title", "A publication title")]
    assert title_provider.title_context == (("Ada Lovelace",), 2025, 7)
    assert doi_only.calls == []


def test_report_hits_deduplicate_across_providers():
    a = FakeProvider("a", [hit("a", "10.1594/PANGAEA.1"), hit("a", "10.1/other")])
    b = FakeProvider("b", [hit("b", "10.1594/pangaea.1")])
    report = DataDiscovery(providers=[a, b]).for_doi(DOI)

    assert len(report.hits) == 2
    assert {h.pid.lower() for h in report.hits} == {"10.1594/pangaea.1", "10.1/other"}
    assert report.found is True


def test_report_not_found_when_empty():
    report = DataDiscovery(providers=[FakeProvider("a")]).for_doi(DOI)
    assert report.hits == []
    assert report.found is False


def test_report_summary_lists_providers():
    a = FakeProvider("a", [hit("a", "10.1/x")])
    boom = FakeProvider("boom", error=DiscoveryError("nope"))
    report = DataDiscovery(providers=[a, boom]).for_doi(DOI)
    summary = report.summary()
    assert "a: 1" in summary
    assert "boom: error" in summary


def test_default_providers_cover_expected_services():
    names = {p.name for p in DataDiscovery().providers}
    assert names == {"datacite", "openaire", "scholexplorer", "b2find", "crossref", "orcid"}


def test_limit_is_forwarded():
    class Recorder(FakeProvider):
        def datasets_for_doi(self, doi, *, limit=100):
            self.calls.append(("limit", str(limit)))
            return self._result()

    rec = Recorder("rec")
    DataDiscovery(providers=[rec]).for_doi(DOI, limit=5)
    assert rec.calls == [("limit", "5")]
