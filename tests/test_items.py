from __future__ import annotations

import io
import json

import pytest

from .conftest import REST, make_record, search_response


def test_get_item(responses, client):
    responses.get(f"{REST}/items/item_1", json={"objectId": "item_1"})
    assert client.items.get("item_1") == {"objectId": "item_1"}


def test_history(responses, client):
    responses.get(f"{REST}/items/item_1/history", json=[{"event": "CREATE"}])
    assert client.items.history("item_1") == [{"event": "CREATE"}]


def test_search_wraps_bare_query(responses, client):
    responses.post(f"{REST}/items/search", json=search_response([make_record()]))
    result = client.items.search({"term": {"context.objectId": {"value": "ctx_1"}}}, size=25)
    assert result.number_of_records == 1
    assert len(result) == 1
    body = json.loads(responses.calls[0].request.body)
    assert body["query"] == {"term": {"context.objectId": {"value": "ctx_1"}}}
    assert body["size"] == 25
    assert body["from"] == 0


def test_search_accepts_full_body(responses, client):
    responses.post(f"{REST}/items/search", json=search_response([]))
    client.items.search({"query": {"match_all": {}}, "size": 7, "sort": [{"x": "ASC"}]})
    body = json.loads(responses.calls[0].request.body)
    assert body["size"] == 7  # body's own size wins over the default
    assert body["sort"] == [{"x": "ASC"}]


def test_search_scroll_param(responses, client):
    responses.post(f"{REST}/items/search", json=search_response([], scroll_id="sc-1"))
    result = client.items.search({"match_all": {}}, scroll=True)
    assert result.scroll_id == "sc-1"
    assert "scroll=true" in responses.calls[0].request.url


def test_search_iter_follows_scroll(responses, client):
    records = [make_record(f"item_{i}") for i in range(5)]
    responses.post(
        f"{REST}/items/search", json=search_response(records[:2], total=5, scroll_id="sc-1")
    )
    responses.get(
        f"{REST}/items/search/scroll", json=search_response(records[2:4], total=5, scroll_id="sc-2")
    )
    responses.get(
        f"{REST}/items/search/scroll", json=search_response(records[4:], total=5, scroll_id="sc-3")
    )
    collected = list(client.items.search_iter({"match_all": {}}, page_size=2))
    assert [r["data"]["objectId"] for r in collected] == [f"item_{i}" for i in range(5)]
    # stops once numberOfRecords is reached: exactly one search + two scrolls
    assert len(responses.calls) == 3
    assert "scrollId=sc-1" in responses.calls[1].request.url
    assert "scrollId=sc-2" in responses.calls[2].request.url


def test_search_iter_respects_max_records(responses, client):
    records = [make_record(f"item_{i}") for i in range(3)]
    responses.post(
        f"{REST}/items/search", json=search_response(records, total=10, scroll_id="sc-1")
    )
    collected = list(client.items.search_iter({"match_all": {}}, page_size=3, max_records=2))
    assert len(collected) == 2
    assert len(responses.calls) == 1


def test_search_iter_stops_on_empty_page(responses, client):
    responses.post(
        f"{REST}/items/search",
        json=search_response([make_record()], total=99, scroll_id="sc-1"),
    )
    responses.get(f"{REST}/items/search/scroll", json=search_response([], total=99))
    assert len(list(client.items.search_iter({"match_all": {}}))) == 1


def test_search_iter_validates_page_size(client):
    with pytest.raises(ValueError):
        next(client.items.search_iter({"match_all": {}}, page_size=0))
    with pytest.raises(ValueError):
        next(client.items.search_iter({"match_all": {}}, page_size=5001))


def test_count(responses, client):
    responses.post(f"{REST}/items/search", json=search_response([], total=42))
    assert client.items.count({"match_all": {}}) == 42
    body = json.loads(responses.calls[0].request.body)
    assert body["size"] == 0


def test_export_item(responses, client):
    responses.get(f"{REST}/items/item_1/export", body=b"@article{...}")
    out = client.items.export("item_1", format="BibTex")
    assert out == b"@article{...}"
    assert "format=BibTex" in responses.calls[0].request.url


def test_export_search_passes_citation_params(responses, client):
    responses.post(f"{REST}/items/search", body=b"<pdf>")
    client.items.export_search({"match_all": {}}, format="pdf", citation="APA", size=100)
    url = responses.calls[0].request.url
    assert "format=pdf" in url and "citation=APA" in url


def test_create_requires_auth_and_posts_item(responses, auth_client):
    responses.post(f"{REST}/items", json={"objectId": "item_new"})
    item = {"context": {"objectId": "ctx_1"}, "metadata": {"title": "T", "genre": "ARTICLE"}}
    created = auth_client.items.create(item)
    assert created["objectId"] == "item_new"
    create_call = responses.calls[-1].request
    assert create_call.headers["Authorization"] == "test-token-123"
    assert json.loads(create_call.body)["metadata"]["title"] == "T"


def test_update_puts_item(responses, auth_client):
    responses.put(f"{REST}/items/item_1", json={"objectId": "item_1", "versionNumber": 2})
    updated = auth_client.items.update("item_1", {"metadata": {}})
    assert updated["versionNumber"] == 2


def test_delete_sends_last_modification_date(responses, auth_client):
    responses.delete(f"{REST}/items/item_1", json={})
    auth_client.items.delete("item_1", "2020-06-01T10:00:00.000+0000")
    body = json.loads(responses.calls[-1].request.body)
    assert body == {"lastModificationDate": "2020-06-01T10:00:00.000+0000"}


@pytest.mark.parametrize("action", ["submit", "release", "revise"])
def test_lifecycle_actions_put_task_param(responses, auth_client, action):
    responses.put(f"{REST}/items/item_1/{action}", json={"objectId": "item_1"})
    method = getattr(auth_client.items, action)
    method("item_1", "2020-06-01T10:00:00.000+0000", "note")
    body = json.loads(responses.calls[-1].request.body)
    assert body == {
        "lastModificationDate": "2020-06-01T10:00:00.000+0000",
        "comment": "note",
    }


def test_lifecycle_comment_omitted_when_none(responses, auth_client):
    responses.put(f"{REST}/items/item_1/release", json={})
    auth_client.items.release("item_1", "2020-06-01T10:00:00.000+0000")
    body = json.loads(responses.calls[-1].request.body)
    assert "comment" not in body


def test_withdraw_requires_comment(responses, auth_client):
    responses.put(f"{REST}/items/item_1/withdraw", json={})
    auth_client.items.withdraw("item_1", "2020-06-01T10:00:00.000+0000", "duplicate")
    body = json.loads(responses.calls[-1].request.body)
    assert body["comment"] == "duplicate"


def test_component_metadata(responses, client):
    responses.get(f"{REST}/items/item_1/component/file_1/metadata", json={"title": "f.pdf"})
    assert client.items.component_metadata("item_1", "file_1") == {"title": "f.pdf"}


def test_component_content(responses, client):
    responses.get(f"{REST}/items/item_1/component/file_1/content", body=b"%PDF-1.4")
    assert client.items.component_content("item_1", "file_1") == b"%PDF-1.4"


def test_download_component_to_path(responses, client, tmp_path):
    responses.get(f"{REST}/items/item_1/component/file_1/content", body=b"data-bytes")
    target = tmp_path / "file.pdf"
    written = client.items.download_component("item_1", "file_1", target)
    assert written == 10
    assert target.read_bytes() == b"data-bytes"


def test_download_component_to_fileobj(responses, client):
    responses.get(f"{REST}/items/item_1/component/file_1/content", body=b"stream")
    buffer = io.BytesIO()
    client.items.download_component("item_1", "file_1", buffer)
    assert buffer.getvalue() == b"stream"
