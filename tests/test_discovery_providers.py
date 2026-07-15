"""Tests for the individual research-data discovery providers.

All HTTP is mocked with ``responses``; the request contracts mirror the real
APIs (see docs/RESEARCH_DATA_DISCOVERY.md for verified example calls).
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from pybman.discovery import (
    B2FindProvider,
    CrossrefProvider,
    DataCiteProvider,
    DiscoveryError,
    OpenAIREProvider,
    OrcidProvider,
    ScholexplorerProvider,
    google_dataset_search_url,
)

DOI = "10.1038/s41586-020-2649-2"
ORCID = "0000-0003-1419-2405"


def _query(responses, call=0) -> dict[str, list[str]]:
    return parse_qs(urlparse(responses.calls[call].request.url).query)


# -- DataCite -----------------------------------------------------------------


def datacite_response(*dois: str, total: int | None = None):
    return {
        "data": [
            {
                "id": doi,
                "type": "dois",
                "attributes": {
                    "doi": doi,
                    "titles": [{"title": f"Dataset {doi}"}],
                    "publisher": "Zenodo",
                    "publicationYear": 2020,
                    "url": f"https://example.org/{doi}",
                    "relatedIdentifiers": [
                        {
                            "relationType": "IsSupplementTo",
                            "relatedIdentifier": DOI,
                            "relatedIdentifierType": "DOI",
                        }
                    ],
                },
            }
            for doi in dois
        ],
        "meta": {"total": total if total is not None else len(dois)},
    }


def test_datacite_datasets_for_doi(responses):
    responses.get("https://api.datacite.org/dois", json=datacite_response("10.5281/zenodo.1"))
    provider = DataCiteProvider()
    result = provider.datasets_for_doi(DOI)

    query = _query(responses)
    assert query["query"] == [f'relatedIdentifiers.relatedIdentifier:"{DOI}"']
    assert query["resource-type-id"] == ["dataset"]
    assert result.provider == "datacite"
    assert result.total == 1
    (hit,) = result.hits
    assert hit.pid == "10.5281/zenodo.1"
    assert hit.pid_type == "doi"
    assert hit.title == "Dataset 10.5281/zenodo.1"
    assert hit.publisher == "Zenodo"
    assert hit.year == 2020
    assert hit.relation == "IsSupplementTo"
    assert hit.url == "https://example.org/10.5281/zenodo.1"


def test_datacite_datasets_for_orcid(responses):
    responses.get("https://api.datacite.org/dois", json=datacite_response("10.5281/zenodo.2"))
    result = DataCiteProvider().datasets_for_orcid(ORCID)

    query = _query(responses)
    assert query["query"] == [f"creators.nameIdentifiers.nameIdentifier:*{ORCID}*"]
    assert query["resource-type-id"] == ["dataset"]
    assert result.hits[0].pid == "10.5281/zenodo.2"
    # relation only applies to DOI-based lookups
    assert result.hits[0].relation is None


def test_datacite_publisher_may_be_object(responses):
    body = datacite_response("10.5281/zenodo.3")
    body["data"][0]["attributes"]["publisher"] = {"name": "PANGAEA"}
    responses.get("https://api.datacite.org/dois", json=body)
    result = DataCiteProvider().datasets_for_doi(DOI)
    assert result.hits[0].publisher == "PANGAEA"


def test_datacite_page_size_and_base_url(responses):
    responses.get("https://datacite.test/dois", json=datacite_response())
    DataCiteProvider(base_url="https://datacite.test").datasets_for_doi(DOI, limit=7)
    assert _query(responses)["page[size]"] == ["7"]


def test_datacite_datasets_for_title_requires_title_and_author_match(responses):
    body = datacite_response("10.5281/zenodo.44", "10.5281/zenodo.45")
    body["data"][0]["attributes"].update(
        {
            "titles": [{"title": "Replication data for Conflict and Democratic Preferences"}],
            "creators": [{"familyName": "Tähtinen", "name": "Tähtinen, Tuuli"}],
        }
    )
    body["data"][1]["attributes"].update(
        {
            "titles": [{"title": "Conflict and democratic preferences in classrooms"}],
            "creators": [{"familyName": "Someone", "name": "Someone, Else"}],
        }
    )
    responses.get("https://api.datacite.org/dois", json=body)

    result = DataCiteProvider().datasets_for_title(
        "Conflict and democratic preferences",
        authors=("Nicole Stoelinga", "Tuuli Tähtinen"),
        year=2026,
    )

    query = _query(responses)
    assert query["query"] == ['titles.title:"Conflict and democratic preferences"']
    assert query["sort"] == ["relevance"]
    assert [hit.pid for hit in result.hits] == ["10.5281/zenodo.44"]
    assert result.hits[0].relation == "verified-title-author-match"


def test_datacite_datasets_for_title_rejects_weak_title_match(responses):
    body = datacite_response("10.5281/zenodo.46")
    body["data"][0]["attributes"].update(
        {
            "titles": [{"title": "Preferences in democratic systems"}],
            "creators": [{"familyName": "Tähtinen"}],
        }
    )
    responses.get("https://api.datacite.org/dois", json=body)
    result = DataCiteProvider().datasets_for_title(
        "Conflict and democratic preferences", authors=("Tuuli Tähtinen",)
    )
    assert result.hits == []


def test_datacite_http_error_raises_discovery_error(responses):
    responses.get("https://api.datacite.org/dois", json={"errors": []}, status=500)
    with pytest.raises(DiscoveryError):
        DataCiteProvider(retries=0).datasets_for_doi(DOI)


# -- OpenAIRE Graph API ---------------------------------------------------------


def openaire_response(*titles: str, total: int | None = None):
    return {
        "header": {"numFound": total if total is not None else len(titles), "pageSize": 100},
        "results": [
            {
                "id": f"openaire____::{i}",
                "mainTitle": title,
                "type": "dataset",
                "publisher": "B2SHARE",
                "publicationDate": "2021-03-01",
                "pids": [{"scheme": "doi", "value": f"10.23728/fake.{i}"}],
            }
            for i, title in enumerate(titles)
        ],
    }


def test_openaire_datasets_for_orcid(responses):
    responses.get(
        "https://api.openaire.eu/graph/v1/researchProducts",
        json=openaire_response("EUDAT dataset"),
    )
    result = OpenAIREProvider().datasets_for_orcid(ORCID)

    query = _query(responses)
    assert query["authorOrcid"] == [ORCID]
    assert query["type"] == ["dataset"]
    assert result.provider == "openaire"
    assert result.total == 1
    (hit,) = result.hits
    assert hit.pid == "10.23728/fake.0"
    assert hit.title == "EUDAT dataset"
    assert hit.publisher == "B2SHARE"
    assert hit.year == 2021


def test_openaire_dataset_lookup_by_doi(responses):
    # A "pid" lookup answers: is this DOI itself a registered dataset?
    responses.get(
        "https://api.openaire.eu/graph/v1/researchProducts",
        json=openaire_response("The dataset itself"),
    )
    result = OpenAIREProvider().datasets_for_doi(DOI)
    query = _query(responses)
    assert query["pid"] == [DOI]
    assert query["type"] == ["dataset"]
    assert result.hits[0].title == "The dataset itself"


def test_openaire_access_token_header(responses):
    responses.get("https://api.openaire.eu/graph/v1/researchProducts", json=openaire_response())
    OpenAIREProvider(access_token="sekrit").datasets_for_orcid(ORCID)
    assert responses.calls[0].request.headers["Authorization"] == "Bearer sekrit"


def test_openaire_result_without_doi_pid_keeps_openaire_id(responses):
    body = openaire_response("No DOI here")
    body["results"][0]["pids"] = []
    responses.get("https://api.openaire.eu/graph/v1/researchProducts", json=body)
    result = OpenAIREProvider().datasets_for_orcid(ORCID)
    assert result.hits[0].pid == "openaire____::0"
    assert result.hits[0].pid_type == "openaire"


# -- ORCID ---------------------------------------------------------------------


def orcid_works_response():
    return {
        "group": [
            {
                "external-ids": {
                    "external-id": [
                        {
                            "external-id-type": "doi",
                            "external-id-value": "10.5281/zenodo.42",
                            "external-id-url": {"value": "https://doi.org/10.5281/zenodo.42"},
                        }
                    ]
                },
                "work-summary": [
                    {
                        "title": {"title": {"value": "Dataset from ORCID"}},
                        "type": "data-set",
                        "journal-title": {"value": "Zenodo"},
                        "publication-date": {"year": {"value": "2023"}},
                    }
                ],
            },
            {
                "external-ids": {
                    "external-id": [
                        {
                            "external-id-type": "doi",
                            "external-id-value": "10.1038/article",
                        }
                    ]
                },
                "work-summary": [
                    {"title": {"title": {"value": "Article"}}, "type": "journal-article"}
                ],
            },
        ]
    }


def test_orcid_datasets_for_orcid_reads_public_works(responses):
    responses.get(f"https://pub.orcid.org/v3.0/{ORCID}/works", json=orcid_works_response())
    result = OrcidProvider().datasets_for_orcid(f"https://orcid.org/{ORCID}")

    assert responses.calls[0].request.headers["Accept"] == "application/vnd.orcid+json"
    assert result.provider == "orcid"
    assert result.total == 1
    (hit,) = result.hits
    assert hit.pid == "10.5281/zenodo.42"
    assert hit.pid_type == "doi"
    assert hit.title == "Dataset from ORCID"
    assert hit.publisher == "Zenodo"
    assert hit.year == 2023
    assert hit.url == "https://doi.org/10.5281/zenodo.42"


def test_orcid_works_without_doi_fall_back_to_put_code(responses):
    body = {
        "group": [
            {
                "external-ids": {"external-id": []},
                "work-summary": [
                    {
                        "put-code": 123,
                        "title": {"title": {"value": "Public metadata-only dataset"}},
                        "type": "data-set",
                    }
                ],
            }
        ]
    }
    responses.get(f"https://pub.orcid.org/v3.0/{ORCID}/works", json=body)
    result = OrcidProvider().datasets_for_orcid(ORCID)
    assert result.hits[0].pid == f"{ORCID}/work/123"
    assert result.hits[0].pid_type == "orcid-work"
    assert result.hits[0].url == f"https://orcid.org/{ORCID}/work/123"


def test_orcid_checks_all_summaries_in_a_work_group(responses):
    body = {
        "group": [
            {
                "external-ids": {
                    "external-id": [
                        {"external-id-type": "doi", "external-id-value": "10.5281/zenodo.99"}
                    ]
                },
                "work-summary": [
                    {"title": {"title": {"value": "Article view"}}, "type": "journal-article"},
                    {"title": {"title": {"value": "Dataset view"}}, "type": "data-set"},
                ],
            }
        ]
    }
    responses.get(f"https://pub.orcid.org/v3.0/{ORCID}/works", json=body)
    result = OrcidProvider().datasets_for_orcid(ORCID)
    assert len(result.hits) == 1
    assert result.hits[0].pid == "10.5281/zenodo.99"
    assert result.hits[0].title == "Dataset view"


def test_orcid_does_not_support_doi():
    assert OrcidProvider().supports_doi is False


# -- ScholeXplorer (Scholix) ----------------------------------------------------


def scholix_link(target_id: str, *, target_type: str = "dataset", relation: str = "References"):
    return {
        "RelationshipType": {"Name": relation},
        "source": {
            "Identifier": [{"ID": DOI, "IDScheme": "doi"}],
            "Type": "publication",
        },
        "target": {
            "Identifier": [{"ID": target_id, "IDScheme": "doi"}],
            "Title": f"Dataset {target_id}",
            "Type": target_type,
            "PublicationDate": "2020-06-15",
            "Publisher": [{"name": "PANGAEA"}],
        },
    }


def scholix_response(*links, total_pages: int = 1):
    return {
        "currentPage": 0,
        "totalLinks": len(links),
        "totalPages": total_pages,
        "result": list(links),
    }


def test_scholexplorer_datasets_for_doi_filters_targets(responses):
    responses.get(
        "https://api.scholexplorer.openaire.eu/v3/Links",
        json=scholix_response(
            scholix_link("10.1594/pangaea.1"),
            scholix_link("10.9999/software.1", target_type="software"),
        ),
    )
    # reverse direction: dataset -> publication links
    responses.get(
        "https://api.scholexplorer.openaire.eu/v3/Links",
        json=scholix_response(),
    )
    result = ScholexplorerProvider().datasets_for_doi(DOI)

    assert _query(responses, 0)["sourcePid"] == [DOI]
    assert _query(responses, 1)["targetPid"] == [DOI]
    assert result.provider == "scholexplorer"
    (hit,) = result.hits
    assert hit.pid == "10.1594/pangaea.1"
    assert hit.title == "Dataset 10.1594/pangaea.1"
    assert hit.publisher == "PANGAEA"
    assert hit.year == 2020
    assert hit.relation == "References"


def test_scholexplorer_reverse_links_report_dataset_sources(responses):
    responses.get("https://api.scholexplorer.openaire.eu/v3/Links", json=scholix_response())
    reverse = {
        "RelationshipType": {"Name": "IsSupplementTo"},
        "source": {
            "Identifier": [{"ID": "10.1594/pangaea.2", "IDScheme": "doi"}],
            "Title": "Supplementary data",
            "Type": "dataset",
            "PublicationDate": "2019",
            "Publisher": [{"name": "PANGAEA"}],
        },
        "target": {"Identifier": [{"ID": DOI, "IDScheme": "doi"}], "Type": "publication"},
    }
    responses.get("https://api.scholexplorer.openaire.eu/v3/Links", json=scholix_response(reverse))
    result = ScholexplorerProvider().datasets_for_doi(DOI)
    (hit,) = result.hits
    assert hit.pid == "10.1594/pangaea.2"
    assert hit.relation == "IsSupplementTo"
    assert hit.year == 2019


def test_scholexplorer_deduplicates_both_directions(responses):
    responses.get(
        "https://api.scholexplorer.openaire.eu/v3/Links",
        json=scholix_response(scholix_link("10.1594/PANGAEA.1")),
    )
    reverse = scholix_link("10.1594/pangaea.1")
    reverse["source"], reverse["target"] = reverse["target"], reverse["source"]
    responses.get("https://api.scholexplorer.openaire.eu/v3/Links", json=scholix_response(reverse))
    result = ScholexplorerProvider().datasets_for_doi(DOI)
    assert len(result.hits) == 1


def test_scholexplorer_paginates_and_stops_at_limit(responses):
    responses.get(
        "https://api.scholexplorer.openaire.eu/v3/Links",
        json=scholix_response(scholix_link("10.1594/pangaea.10"), total_pages=2),
    )
    responses.get(
        "https://api.scholexplorer.openaire.eu/v3/Links",
        json=scholix_response(scholix_link("10.1594/pangaea.11"), total_pages=2),
    )
    result = ScholexplorerProvider().datasets_for_doi(DOI, limit=2)
    assert [hit.pid for hit in result.hits] == ["10.1594/pangaea.10", "10.1594/pangaea.11"]
    assert _query(responses, 0)["page"] == ["0"]
    assert _query(responses, 1)["page"] == ["1"]
    # limit reached in source direction; reverse direction should not be fetched
    assert len(responses.calls) == 2


def test_scholexplorer_does_not_support_orcid():
    provider = ScholexplorerProvider()
    assert provider.supports_orcid is False
    with pytest.raises(NotImplementedError):
        provider.datasets_for_orcid(ORCID)


# -- B2FIND (CKAN) --------------------------------------------------------------


def ckan_response(*names: str, count: int | None = None):
    return {
        "success": True,
        "result": {
            "count": count if count is not None else len(names),
            "results": [
                {
                    "name": name,
                    "title": f"Dataset {name}",
                    "url": f"https://doi.org/10.23728/{name}",
                    "metadata_created": "2022-05-01T12:00:00",
                    "organization": {"title": "PANGAEA"},
                    "extras": [{"key": "DOI", "value": f"10.23728/{name}"}],
                }
                for name in names
            ],
        },
    }


def test_b2find_datasets_for_doi(responses):
    responses.get("https://b2find.eudat.eu/api/3/action/package_search", json=ckan_response("abc"))
    result = B2FindProvider().datasets_for_doi(DOI)

    query = _query(responses)
    assert query["q"] == [f'"{DOI}"']
    assert result.provider == "b2find"
    (hit,) = result.hits
    assert hit.pid == "10.23728/abc"
    assert hit.title == "Dataset abc"
    assert hit.publisher == "PANGAEA"
    assert hit.year == 2022
    assert hit.url == "https://b2find.eudat.eu/dataset/abc"


def test_b2find_datasets_for_orcid(responses):
    responses.get("https://b2find.eudat.eu/api/3/action/package_search", json=ckan_response("xyz"))
    result = B2FindProvider().datasets_for_orcid(ORCID)
    assert _query(responses)["q"] == [f'"{ORCID}"']
    assert result.hits[0].pid == "10.23728/xyz"


def test_b2find_ckan_error_flag_raises(responses):
    responses.get(
        "https://b2find.eudat.eu/api/3/action/package_search",
        json={"success": False, "error": {"message": "boom"}},
    )
    with pytest.raises(DiscoveryError):
        B2FindProvider().datasets_for_doi(DOI)


def test_b2find_hit_without_doi_falls_back_to_name(responses):
    body = ckan_response("plain")
    body["result"]["results"][0]["extras"] = []
    body["result"]["results"][0]["url"] = ""
    responses.get("https://b2find.eudat.eu/api/3/action/package_search", json=body)
    result = B2FindProvider().datasets_for_doi(DOI)
    assert result.hits[0].pid == "plain"
    assert result.hits[0].pid_type == "ckan"


# -- Crossref -------------------------------------------------------------------


def crossref_response(relations: dict):
    return {"status": "ok", "message": {"DOI": DOI, "relation": relations}}


def test_crossref_supplement_relations_reported(responses):
    responses.get(
        f"https://api.crossref.org/works/{DOI}",
        json=crossref_response(
            {
                "is-supplemented-by": [
                    {"id-type": "doi", "id": "10.5061/dryad.abc", "asserted-by": "subject"}
                ],
                "has-preprint": [{"id-type": "doi", "id": "10.1101/xyz"}],
            }
        ),
    )
    result = CrossrefProvider().datasets_for_doi(DOI)
    assert result.provider == "crossref"
    (hit,) = result.hits
    assert hit.pid == "10.5061/dryad.abc"
    assert hit.relation == "is-supplemented-by"
    assert hit.url == "https://doi.org/10.5061/dryad.abc"


def test_crossref_unknown_doi_yields_empty_result(responses):
    # DataCite-registered DOIs 404 on Crossref; that is "no information", not an error.
    responses.get(f"https://api.crossref.org/works/{DOI}", status=404)
    result = CrossrefProvider().datasets_for_doi(DOI)
    assert result.hits == []
    assert result.error is None


def test_crossref_does_not_support_orcid():
    assert CrossrefProvider().supports_orcid is False


def test_crossref_mailto_forwarded(responses):
    responses.get(f"https://api.crossref.org/works/{DOI}", json=crossref_response({}))
    CrossrefProvider(mailto="me@example.org").datasets_for_doi(DOI)
    assert _query(responses)["mailto"] == ["me@example.org"]


def test_crossref_respects_limit_across_relation_types(responses):
    responses.get(
        f"https://api.crossref.org/works/{DOI}",
        json=crossref_response(
            {
                "has-supplement": [{"id-type": "doi", "id": "10.5061/dryad.1"}],
                "is-supplemented-by": [{"id-type": "doi", "id": "10.5061/dryad.2"}],
            }
        ),
    )
    result = CrossrefProvider().datasets_for_doi(DOI, limit=1)
    assert len(result.hits) == 1


# -- Google Dataset Search (no API) ----------------------------------------------


def test_google_dataset_search_url():
    url = google_dataset_search_url(DOI)
    assert url == (
        "https://datasetsearch.research.google.com/search?query=10.1038%2Fs41586-020-2649-2"
    )
