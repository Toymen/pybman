"""Tests for the SQLite storage layer used by the sync + web service."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")

from webapp import store

from .conftest import make_record


def test_upsert_and_query_roundtrip(tmp_path):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    with store.connect(db_path) as conn:
        store.upsert_item(conn, make_record("item_1", title="Alpha", genre="ARTICLE"))
        store.upsert_item(conn, make_record("item_2", title="Beta", genre="BOOK"))

    with store.connect(db_path) as conn:
        rows, total = store.query_items(conn, {}, "")
        assert total == 2
        assert {r["object_id"] for r in rows} == {"item_1", "item_2"}

        rows, total = store.query_items(conn, {"genre": "BOOK"}, "")
        assert total == 1
        assert rows[0]["title"] == "Beta"

        rows, total = store.query_items(conn, {}, "alpha")
        assert total == 1
        assert rows[0]["object_id"] == "item_1"


def test_upsert_item_is_idempotent(tmp_path):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    with store.connect(db_path) as conn:
        store.upsert_item(conn, make_record("item_1", title="Old title"))
        store.upsert_item(conn, make_record("item_1", title="New title"))
        rows, total = store.query_items(conn, {}, "")
    assert total == 1
    assert rows[0]["title"] == "New title"


def test_nested_field_index_filters_any_scalar_value(tmp_path):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    with store.connect(db_path) as conn:
        store.upsert_item(
            conn,
            make_record(
                "item_1",
                title="Alpha",
                identifiers=[{"type": "DOI", "id": "10.1000/example"}],
            ),
        )
        store.upsert_item(conn, make_record("item_2", title="Beta", identifiers=[]))

    with store.connect(db_path) as conn:
        paths = store.field_paths(conn)
        assert "data.metadata.identifiers[].id" in paths

        rows, total = store.query_items(
            conn,
            {},
            field_filters=[("data.metadata.identifiers[].id", "10.1000")],
        )
        assert total == 1
        assert rows[0]["object_id"] == "item_1"


def test_creator_cone_ids_are_bound_to_creator_names(tmp_path):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    with store.connect(db_path) as conn:
        store.upsert_item(conn, make_record("item_1"))
        rows, total = store.query_items(conn, {}, "persons100")

    assert total == 1
    assert rows[0]["creator_cone_ids"] == "persons100"
    assert rows[0]["creator_cone_bindings"] == "Ada Lovelace (AUTHOR): persons100"


def test_filters_reject_unknown_columns(tmp_path):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    with store.connect(db_path) as conn:
        store.upsert_item(conn, make_record("item_1"))
        # an unknown column in filters is silently ignored, not used in SQL
        _rows, total = store.query_items(conn, {"object_id": "item_1"}, "")
    assert total == 1  # filter ignored, not an error
    with pytest.raises(ValueError):
        with store.connect(db_path) as conn:
            store.distinct_values(conn, "object_id")


def test_meta_roundtrip(tmp_path):
    db_path = str(tmp_path / "pubman.db")
    store.init_db(db_path)
    with store.connect(db_path) as conn:
        assert store.get_meta(conn, "last_synced_at", "never") == "never"
        store.set_meta(conn, "last_synced_at", "2026-01-01T00:00:00")
    with store.connect(db_path) as conn:
        assert store.get_meta(conn, "last_synced_at") == "2026-01-01T00:00:00"
