from __future__ import annotations

import copy
from typing import Any

import pytest
import responses as responses_lib

from pybman import Client

BASE = "https://pure.example.org"
REST = f"{BASE}/rest"
CONE = f"{BASE}/cone"


@pytest.fixture
def responses():
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def client() -> Client:
    """Anonymous client against the fake instance (retries off for speed)."""
    return Client(BASE, retries=0)


@pytest.fixture
def auth_client(responses) -> Client:
    """Client with credentials; login endpoint is mocked to return a token."""
    responses.post(f"{REST}/login", json={}, headers={"Token": "test-token-123"})
    return Client(BASE, username="alice", password="wonder", retries=0)


def make_record(
    item_id: str = "item_1",
    *,
    title: str = "A Title",
    genre: str = "ARTICLE",
    ctx_id: str = "ctx_1",
    creators: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    files: list[dict[str, Any]] | None = None,
    public_state: str = "RELEASED",
    version_state: str = "RELEASED",
    **metadata: Any,
) -> dict[str, Any]:
    """A realistic PubMan search record for tests."""
    if creators is None:
        creators = [
            {
                "person": {
                    "givenName": "Ada",
                    "familyName": "Lovelace",
                    "organizations": [
                        {"identifier": "ou_1", "name": "Institute One", "identifierPath": [""]}
                    ],
                    "identifier": {"id": "/persons/resource/persons100", "type": "CONE"},
                },
                "role": "AUTHOR",
                "type": "PERSON",
            }
        ]
    md: dict[str, Any] = {
        "title": title,
        "genre": genre,
        "creators": creators,
        "datePublishedInPrint": "2020-05-01",
        "languages": ["eng"],
        "publishingInfo": {"place": "Berlin", "publisher": "Publisher A"},
    }
    if sources is not None:
        md["sources"] = sources
    md.update(metadata)
    data: dict[str, Any] = {
        "objectId": item_id,
        "versionNumber": 1,
        "lastModificationDate": "2020-06-01T10:00:00.000+0000",
        "publicState": public_state,
        "versionState": version_state,
        "context": {"objectId": ctx_id},
        "metadata": md,
    }
    if files is not None:
        data["files"] = files
    return {
        "schema": "test",
        "packing": "test",
        "persistenceId": f"{item_id}_1",
        "data": data,
    }


def search_response(
    records: list[dict[str, Any]],
    *,
    total: int | None = None,
    scroll_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "numberOfRecords": total if total is not None else len(records),
        "records": copy.deepcopy(records),
    }
    if scroll_id is not None:
        body["scrollId"] = scroll_id
    return body
