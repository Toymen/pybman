"""Tests for the ous, contexts, feeds, staging and cone resource APIs."""

from __future__ import annotations

import io
import json

import pytest

from .conftest import CONE, REST, search_response

# -- organizational units ---------------------------------------------------


def test_ous_get(responses, client):
    responses.get(f"{REST}/ous/ou_1", json={"objectId": "ou_1"})
    assert client.ous.get("ou_1") == {"objectId": "ou_1"}


def test_ous_all_probes_total_first(responses, client):
    responses.get(f"{REST}/ous", json=search_response([], total=3))
    responses.get(
        f"{REST}/ous", json=search_response([{"data": {}}, {"data": {}}, {"data": {}}], total=3)
    )
    result = client.ous.all()
    assert result.number_of_records == 3
    assert "size=1" in responses.calls[0].request.url
    assert "size=3" in responses.calls[1].request.url


def test_ous_toplevel_and_children(responses, client):
    responses.get(f"{REST}/ous/toplevel", json=[{"objectId": "ou_root"}])
    responses.get(f"{REST}/ous/ou_root/children", json=[{"objectId": "ou_child"}])
    assert client.ous.toplevel()[0]["objectId"] == "ou_root"
    assert client.ous.children("ou_root")[0]["objectId"] == "ou_child"


def test_ous_search(responses, client):
    responses.post(f"{REST}/ous/search", json=search_response([], total=7))
    result = client.ous.search({"match": {"metadata.name": "Institute"}}, size=5)
    assert result.number_of_records == 7
    body = json.loads(responses.calls[0].request.body)
    assert body["query"] == {"match": {"metadata.name": "Institute"}}
    assert body["size"] == 5


# -- contexts ---------------------------------------------------------------


def test_contexts_get(responses, client):
    responses.get(f"{REST}/contexts/ctx_1", json={"objectId": "ctx_1"})
    assert client.contexts.get("ctx_1") == {"objectId": "ctx_1"}


def test_contexts_all(responses, client):
    responses.get(f"{REST}/contexts", json=search_response([], total=2))
    responses.get(f"{REST}/contexts", json=search_response([{"data": {}}, {"data": {}}], total=2))
    assert client.contexts.all().number_of_records == 2


def test_contexts_search(responses, client):
    responses.post(f"{REST}/contexts/search", json=search_response([]))
    client.contexts.search({"match_all": {}})
    assert json.loads(responses.calls[0].request.body)["query"] == {"match_all": {}}


# -- feeds --------------------------------------------------------------------


def test_feeds_return_text(responses, client):
    responses.get(f"{REST}/feed/recent", body="<feed>recent</feed>")
    responses.get(f"{REST}/feed/oa", body="<feed>oa</feed>")
    responses.get(f"{REST}/feed/organization/ou_1", body="<feed>ou</feed>")
    responses.get(f"{REST}/feed/search", body="<feed>found</feed>")
    assert "recent" in client.feeds.recent()
    assert "oa" in client.feeds.open_access()
    assert "ou" in client.feeds.organization("ou_1")
    assert "found" in client.feeds.search("title:test")
    assert "q=title%3Atest" in responses.calls[3].request.url


# -- staging -------------------------------------------------------------------


def test_staging_upload_bytes(responses, auth_client):
    responses.post(f"{REST}/staging/file.pdf", body='"12345"', status=201)
    staged_id = auth_client.staging.upload(b"%PDF-1.4", filename="file.pdf")
    assert staged_id == "12345"
    request = responses.calls[-1].request
    assert request.headers["Content-Type"] == "application/octet-stream"
    assert request.headers["Authorization"] == "test-token-123"
    assert request.body == b"%PDF-1.4"


def test_staging_upload_path(responses, auth_client, tmp_path):
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"pdf-data")
    responses.post(f"{REST}/staging/paper.pdf", body="staged-1", status=201)
    assert auth_client.staging.upload(path) == "staged-1"


def test_staging_upload_fileobj(responses, auth_client):
    responses.post(f"{REST}/staging/data.bin", body="staged-2", status=201)
    assert auth_client.staging.upload(io.BytesIO(b"xyz"), filename="data.bin") == "staged-2"


def test_staging_upload_bytes_requires_filename(auth_client):
    with pytest.raises(ValueError):
        auth_client.staging.upload(b"data")


# -- cone ---------------------------------------------------------------------


def test_cone_persons(responses, client):
    responses.get(
        f"{CONE}/persons/all",
        json=[{"id": f"{CONE}/persons/resource/persons100", "value": "Lovelace, Ada"}],
    )
    persons = client.cone.persons()
    assert persons[0]["value"] == "Lovelace, Ada"
    assert "format=json" in responses.calls[0].request.url


def test_cone_person_accepts_full_urls(responses, client):
    responses.get(f"{CONE}/persons/resource/persons100", json={"id": "persons100"})
    client.cone.person(f"{CONE}/persons/resource/persons100")
    assert responses.calls[0].request.url.startswith(f"{CONE}/persons/resource/persons100?")


def test_cone_query_with_limit(responses, client):
    responses.get(f"{CONE}/persons/query", json=[{"id": "x", "value": "Lovelace"}])
    result = client.cone.query_persons("Lovelace", limit=5)
    assert result[0]["value"] == "Lovelace"
    url = responses.calls[0].request.url
    assert "q=Lovelace" in url and "n=5" in url


def test_cone_languages(responses, client):
    responses.get(f"{CONE}/iso639-3/resource/deu", json={"id": "deu"})
    assert client.cone.language("deu") == {"id": "deu"}
