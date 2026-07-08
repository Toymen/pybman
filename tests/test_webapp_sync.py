"""Tests for the fetch-everything-into-SQLite sync engine."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")

from webapp import store, sync

from .conftest import CONE, REST, make_record, search_response


def test_run_stores_items_and_dereferences_person_and_org(tmp_path, responses, client):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    record = make_record("item_1", title="A Title")

    responses.post(f"{REST}/items/search", json=search_response([record]))  # count()
    responses.post(f"{REST}/items/search", json=search_response([record]))
    responses.get(
        f"{CONE}/persons/resource/persons100",
        json={"givenName": "Ada", "familyName": "Lovelace"},
    )
    responses.get(f"{REST}/ous/ou_1", json={"objectId": "ou_1", "name": "Institute One"})

    count = sync.run(client, {"match_all": {}}, db_path, dereference_authorities=True)

    assert count == 1
    with store.connect(db_path) as conn:
        rows, total = store.query_items(conn, {}, "")
        assert total == 1
        assert rows[0]["object_id"] == "item_1"
        assert store.get_meta(conn, "item_count") == "1"
        assert store.get_meta(conn, "last_synced_at") is not None

        person = conn.execute("SELECT * FROM persons WHERE cone_id = 'persons100'").fetchone()
        assert person["name"] == "Ada Lovelace"

        org = conn.execute("SELECT * FROM organizations WHERE ou_id = 'ou_1'").fetchone()
        assert org["name"] == "Institute One"


def test_run_retries_once_when_records_are_missing(tmp_path, responses, client):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    record = make_record("item_1", creators=[])  # no creators: skip person/org dereference

    # first scroll pass "drops" the record (empty page), count says 1 is expected,
    # so a full retry pass should pick it up.
    responses.post(f"{REST}/items/search", json=search_response([record], total=1))  # count()
    responses.post(f"{REST}/items/search", json=search_response([]))
    responses.post(f"{REST}/items/search", json=search_response([record]))  # retry pass

    count = sync.run(client, {"match_all": {}}, db_path)

    assert count == 1
    with store.connect(db_path) as conn:
        assert store.item_count(conn) == 1
