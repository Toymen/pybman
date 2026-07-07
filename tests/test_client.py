from __future__ import annotations

import json

import pytest

from pybman import Client, DataSet
from pybman.client import ENV_PASSWORD, ENV_USERNAME

from .conftest import BASE, REST, make_record, search_response


def test_default_base_url():
    client = Client()
    assert client.base_url == "https://pure.mpg.de"


def test_repr_hides_credentials():
    client = Client(BASE, username="alice", password="hunter2")
    assert "hunter2" not in repr(client)
    assert "anonymous" in repr(client)


def test_credentials_from_env(monkeypatch, responses):
    monkeypatch.setenv(ENV_USERNAME, "envuser")
    monkeypatch.setenv(ENV_PASSWORD, "envpass")
    responses.post(f"{REST}/login", json={}, headers={"Token": "tok-env"})
    client = Client(BASE, retries=0)
    assert client.login() == "tok-env"
    assert responses.calls[0].request.body == b"envuser:envpass"


def test_credentials_file_modern_layout(tmp_path):
    path = tmp_path / "creds.json"
    path.write_text(json.dumps({"username": "u", "password": "p"}))
    client = Client(BASE, credentials_file=path)
    assert client.transport.has_credentials


def test_credentials_file_legacy_layout(tmp_path):
    path = tmp_path / "secret.json"
    path.write_text(json.dumps({"user-pass": "u:p"}))
    client = Client(BASE, credentials_file=path)
    assert client.transport.has_credentials


def test_credentials_file_invalid_layout(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"user-pass": "no-separator"}))
    with pytest.raises(ValueError):
        Client(BASE, credentials_file=path)


def test_secret_argument_is_deprecated(tmp_path):
    path = tmp_path / "secret.json"
    path.write_text(json.dumps({"user-pass": "u:p"}))
    with pytest.warns(DeprecationWarning, match="secret"):
        client = Client(BASE, secret=str(path))
    assert client.transport.has_credentials


def test_context_manager_logs_out(responses, auth_client):
    responses.get(f"{REST}/logout", json={})
    with auth_client as client:
        client.login()
        assert client.is_authenticated
    assert not auth_client.is_authenticated
    assert responses.calls[-1].request.url == f"{REST}/logout"


def test_get_data_scrolls_and_returns_dataset(responses, client):
    records = [make_record("item_1"), make_record("item_2")]
    responses.post(f"{REST}/items/search", json=search_response(records, total=2))
    dataset = client.get_data(ctx_id="ctx_1")
    assert isinstance(dataset, DataSet)
    assert dataset.idx == "ctx_1"
    assert dataset.num == 2
    body = json.loads(responses.calls[0].request.body)
    assert body["query"] == {"term": {"context.objectId": {"value": "ctx_1"}}}


def test_get_data_misc_query(responses, client):
    responses.post(f"{REST}/items/search", json=search_response([]))
    dataset = client.get_data(misc_query={"match_all": {}})
    assert dataset.idx == "query_data"


def test_get_data_requires_exactly_one_selector(client):
    with pytest.raises(ValueError):
        client.get_data()
    with pytest.raises(ValueError):
        client.get_data(ctx_id="ctx_1", ou_id="ou_1")


def test_update_and_release(responses, auth_client):
    responses.put(
        f"{REST}/items/item_1",
        json={"objectId": "item_1", "lastModificationDate": "2021-01-01T00:00:00.000+0000"},
    )
    responses.put(f"{REST}/items/item_1/release", json={"objectId": "item_1"})
    released = auth_client.update_and_release("item_1", {"metadata": {}}, "cleanup")
    assert released["objectId"] == "item_1"
    release_body = json.loads(responses.calls[-1].request.body)
    assert release_body == {
        "lastModificationDate": "2021-01-01T00:00:00.000+0000",
        "comment": "cleanup",
    }


def test_update_data_is_deprecated_alias(responses, auth_client):
    responses.put(
        f"{REST}/items/item_1",
        json={"objectId": "item_1", "lastModificationDate": "2021-01-01T00:00:00.000+0000"},
    )
    responses.put(f"{REST}/items/item_1/release", json={"objectId": "item_1"})
    with pytest.warns(DeprecationWarning, match="update_and_release"):
        auth_client.update_data("item_1", {"metadata": {}}, "cleanup")
