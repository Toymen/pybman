from __future__ import annotations

import pytest

from pybman import queries


def test_by_context():
    assert queries.by_context("ctx_1") == {"term": {"context.objectId": {"value": "ctx_1"}}}


def test_by_context_released_only():
    query = queries.by_context("ctx_1", released_only=True)
    must = query["bool"]["must"]
    assert {"term": {"publicState": {"value": "RELEASED"}}} in must
    assert {"term": {"versionState": {"value": "RELEASED"}}} in must
    assert {"term": {"context.objectId": {"value": "ctx_1"}}} in must


def test_by_organization_matches_person_and_org_creators():
    query = queries.by_organization("ou_1")
    should = query["bool"]["should"]
    fields = [next(iter(clause["term"])) for clause in should]
    assert "metadata.creators.person.organizations.identifierPath" in fields
    assert "metadata.creators.organization.identifierPath" in fields


@pytest.mark.parametrize(
    "cone_id",
    ["persons100", "/persons/resource/persons100", "https://x/persons/resource/persons100"],
)
def test_by_person_normalizes_ids(cone_id):
    query = queries.by_person(cone_id)
    assert query == {
        "term": {
            "metadata.creators.person.identifier.id": {"value": "/persons/resource/persons100"}
        }
    }


def test_by_language():
    assert queries.by_language("deu") == {"term": {"metadata.languages": {"value": "deu"}}}


def test_by_journal_matches_title_and_alternatives():
    query = queries.by_journal("Nature")
    should = query["bool"]["should"]
    assert {"match_phrase": {"metadata.sources.title": {"query": "Nature"}}} in should
    assert {
        "match_phrase": {"metadata.sources.alternativeTitles.value": {"query": "Nature"}}
    } in should


def test_by_genre():
    assert queries.by_genre("ARTICLE") == {"term": {"metadata.genre": {"value": "ARTICLE"}}}


@pytest.mark.parametrize(
    "doi", ["10.1000/xyz", "https://doi.org/10.1000/xyz", "http://doi.org/10.1000/xyz"]
)
def test_by_identifier_strips_doi_prefixes(doi):
    query = queries.by_identifier(doi)
    keyword_term = query["bool"]["should"][0]["term"]
    assert keyword_term["metadata.identifiers.id.keyword"]["value"] == "10.1000/xyz"


def test_with_files_defaults_to_released_fulltexts():
    query = queries.with_files()
    must = query["bool"]["must"]
    nested = must[2]["nested"]
    assert nested["path"] == "files"
    storage = nested["query"]["bool"]["must"][0]
    assert storage == {"term": {"files.storage": {"value": "INTERNAL_MANAGED"}}}
    categories = [
        clause["match"]["files.metadata.contentCategory"]["query"]
        for clause in nested["query"]["bool"]["must"][1]["bool"]["should"]
    ]
    assert categories == ["post-print", "pre-print", "any-fulltext", "publisher-version"]


def test_with_locators_uses_external_url_storage():
    query = queries.with_locators()
    nested = query["bool"]["must"][2]["nested"]
    assert nested["query"]["bool"]["must"][0] == {
        "term": {"files.storage": {"value": "EXTERNAL_URL"}}
    }


def test_builders_return_fresh_objects():
    first = queries.by_context("ctx_1", released_only=True)
    second = queries.by_context("ctx_2", released_only=True)
    assert first["bool"]["must"][2]["term"]["context.objectId"]["value"] == "ctx_1"
    assert second["bool"]["must"][2]["term"]["context.objectId"]["value"] == "ctx_2"


def test_legacy_query_module_wraps_builders():
    import pybman.query as legacy

    with pytest.warns(DeprecationWarning):
        ctx = legacy.ContextQuery()
    body = ctx.get_item_query("ctx_9")
    assert body["query"] == queries.by_context("ctx_9")
    assert body["size"] == "50"

    with pytest.warns(DeprecationWarning):
        ou = legacy.OrgUnitQuery()
    assert ou.get_item_released_query("ou_1") == ou.get_released_item_query("ou_1")
