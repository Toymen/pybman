"""SQLite storage for synced publications, persons and organizations.

One file, no server to run — plenty for a read-mostly cache of a publication
repository refreshed at most a few times a day.

The raw JSON payloads are kept intact. In addition, every scalar JSON leaf is
indexed in ``item_fields``/``entity_fields`` as ``path -> value`` rows so the
web UI can filter nested metadata without knowing the PubMan schema upfront.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pybman import extract

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    object_id TEXT PRIMARY KEY,
    title TEXT,
    genre TEXT,
    year TEXT,
    context_id TEXT,
    public_state TEXT,
    version_state TEXT,
    language TEXT,
    doi TEXT,
    source_title TEXT,
    publisher TEXT,
    date_modified TEXT,
    creators TEXT,
    creator_cone_ids TEXT,
    creator_cone_bindings TEXT,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_genre ON items(genre);
CREATE INDEX IF NOT EXISTS idx_items_year ON items(year);
CREATE INDEX IF NOT EXISTS idx_items_context_id ON items(context_id);
CREATE INDEX IF NOT EXISTS idx_items_public_state ON items(public_state);
CREATE INDEX IF NOT EXISTS idx_items_version_state ON items(version_state);
CREATE INDEX IF NOT EXISTS idx_items_language ON items(language);
CREATE INDEX IF NOT EXISTS idx_items_publisher ON items(publisher);
CREATE INDEX IF NOT EXISTS idx_items_source_title ON items(source_title);
CREATE INDEX IF NOT EXISTS idx_items_date_modified ON items(date_modified);
CREATE TABLE IF NOT EXISTS item_fields (
    object_id TEXT NOT NULL,
    path TEXT NOT NULL,
    value TEXT NOT NULL,
    FOREIGN KEY(object_id) REFERENCES items(object_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_item_fields_path_value ON item_fields(path, value);
CREATE INDEX IF NOT EXISTS idx_item_fields_object_id ON item_fields(object_id);
CREATE TABLE IF NOT EXISTS item_creator_cones (
    object_id TEXT NOT NULL,
    creator_name TEXT NOT NULL,
    cone_id TEXT NOT NULL,
    role TEXT NOT NULL,
    FOREIGN KEY(object_id) REFERENCES items(object_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_item_creator_cones_cone_id ON item_creator_cones(cone_id);
CREATE INDEX IF NOT EXISTS idx_item_creator_cones_object_id ON item_creator_cones(object_id);
CREATE TABLE IF NOT EXISTS persons (
    cone_id TEXT PRIMARY KEY,
    name TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS organizations (
    ou_id TEXT PRIMARY KEY,
    name TEXT,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entity_fields (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    path TEXT NOT NULL,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entity_fields_type_path_value
    ON entity_fields(entity_type, path, value);
CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

#: Item columns a caller may filter/sort on (whitelist against SQL injection).
FILTERABLE_COLUMNS = (
    "genre",
    "year",
    "context_id",
    "public_state",
    "version_state",
    "language",
    "publisher",
    "source_title",
)

SUMMARY_COLUMNS = (
    "object_id",
    "title",
    "genre",
    "year",
    "creators",
    "creator_cone_ids",
    "creator_cone_bindings",
    "source_title",
    "publisher",
    "language",
    "doi",
    "context_id",
    "public_state",
    "date_modified",
)


@contextmanager
def connect(db_path: str) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _ensure_item_columns(conn)


def _ensure_item_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(items)").fetchall()}
    additions = {
        "creator_cone_ids": "TEXT",
        "creator_cone_bindings": "TEXT",
    }
    for column, definition in additions.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE items ADD COLUMN {column} {definition}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_items_creator_cone_ids ON items(creator_cone_ids)")


def _first(values: list[str]) -> str:
    return values[0] if values else ""


def _creator_names(metadata: dict[str, Any]) -> str:
    names = []
    for creator in metadata.get("creators") or []:
        person = creator.get("person")
        if person:
            name = f"{person.get('givenName', '')} {person.get('familyName', '')}".strip()
        else:
            name = creator.get("organization", {}).get("name", "")
        if name:
            names.append(name)
    return "; ".join(names)


def _creator_cone_data(metadata: dict[str, Any]) -> tuple[str, str]:
    entries = _creator_cone_entries(metadata)
    ids: list[str] = []
    bindings: list[str] = []
    for entry in entries:
        label = entry["creator_name"] or entry["cone_id"]
        if entry["role"]:
            label = f"{label} ({entry['role']})"
        ids.append(entry["cone_id"])
        bindings.append(f"{label}: {entry['cone_id']}")
    return "; ".join(dict.fromkeys(ids)), "; ".join(dict.fromkeys(bindings))


def _creator_cone_entries(metadata: dict[str, Any]) -> list[dict[str, str]]:
    entries = []
    for creator in metadata.get("creators") or []:
        person = creator.get("person") or {}
        identifier = person.get("identifier") or {}
        if identifier.get("type") != "CONE":
            continue
        cone_id = str(identifier.get("id") or "").rstrip("/").split("/")[-1]
        if not cone_id:
            continue
        name = f"{person.get('givenName', '')} {person.get('familyName', '')}".strip()
        role = creator.get("role", "")
        entries.append({"creator_name": name, "cone_id": cone_id, "role": role})
    return list({(e["creator_name"], e["cone_id"], e["role"]): e for e in entries}.values())


def _replace_creator_cones(
    conn: sqlite3.Connection, object_id: str, metadata: dict[str, Any]
) -> None:
    conn.execute("DELETE FROM item_creator_cones WHERE object_id = ?", (object_id,))
    rows = [
        (object_id, entry["creator_name"], entry["cone_id"], entry["role"])
        for entry in _creator_cone_entries(metadata)
    ]
    if rows:
        conn.executemany(
            """INSERT INTO item_creator_cones (object_id, creator_name, cone_id, role)
               VALUES (?, ?, ?, ?)""",
            rows,
        )


def _flatten_json(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(normalized.path, scalar_value)`` pairs for nested JSON.

    Lists use ``[]`` instead of numeric indexes, so a filter on
    ``data.metadata.creators[].person.familyName`` matches every creator slot.
    Empty containers are indexed too; that makes "field exists but is empty"
    visible in exports.
    """
    if isinstance(value, dict):
        if not value and path:
            yield path, ""
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _flatten_json(child, child_path)
    elif isinstance(value, list):
        if not value and path:
            yield path, ""
        for child in value:
            yield from _flatten_json(child, f"{path}[]")
    elif value is None:
        if path:
            yield path, ""
    elif path:
        yield path, str(value)


def _replace_fields(
    conn: sqlite3.Connection, table: str, key_columns: dict[str, str], payload: dict[str, Any]
) -> None:
    where = " AND ".join(f"{column} = ?" for column in key_columns)
    conn.execute(f"DELETE FROM {table} WHERE {where}", tuple(key_columns.values()))
    rows = [
        (*key_columns.values(), path, scalar)
        for path, scalar in dict.fromkeys(_flatten_json(payload))
    ]
    if not rows:
        return
    columns = [*key_columns.keys(), "path", "value"]
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        rows,
    )


def upsert_item(conn: sqlite3.Connection, record: dict[str, Any]) -> None:
    """Store one search-result record, extracting flat columns for filtering."""
    item = record["data"]
    metadata = item.get("metadata", {})
    doi = next((i["id"] for i in metadata.get("identifiers") or [] if i.get("type") == "DOI"), "")
    object_id = item.get("objectId", "")
    creator_cone_ids, creator_cone_bindings = _creator_cone_data(metadata)
    conn.execute(
        """INSERT INTO items (object_id, title, genre, year, context_id, public_state,
                               version_state, language, doi, source_title, publisher,
                               date_modified, creators, creator_cone_ids,
                               creator_cone_bindings, data)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(object_id) DO UPDATE SET
               title=excluded.title, genre=excluded.genre, year=excluded.year,
               context_id=excluded.context_id, public_state=excluded.public_state,
               version_state=excluded.version_state, language=excluded.language,
               doi=excluded.doi, source_title=excluded.source_title,
               publisher=excluded.publisher, date_modified=excluded.date_modified,
               creators=excluded.creators, creator_cone_ids=excluded.creator_cone_ids,
               creator_cone_bindings=excluded.creator_cone_bindings,
               data=excluded.data""",
        (
            object_id,
            metadata.get("title", ""),
            metadata.get("genre", ""),
            extract.date_from_item(record)[:4],
            item.get("context", {}).get("objectId", ""),
            item.get("publicState", ""),
            item.get("versionState", ""),
            _first(metadata.get("languages") or []),
            doi,
            _first([s["title"] for s in metadata.get("sources") or [] if s.get("title")]),
            metadata.get("publishingInfo", {}).get("publisher", ""),
            metadata.get("dateModified", ""),
            _creator_names(metadata),
            creator_cone_ids,
            creator_cone_bindings,
            json.dumps(record),
        ),
    )
    _replace_fields(conn, "item_fields", {"object_id": object_id}, record)
    _replace_creator_cones(conn, object_id, metadata)


def backfill_creator_cone_columns(conn: sqlite3.Connection, *, batch_size: int = 5000) -> int:
    _ensure_item_columns(conn)
    rows = conn.execute(
        """SELECT object_id, data FROM items
           WHERE creator_cone_ids IS NULL OR creator_cone_bindings IS NULL"""
    ).fetchmany(batch_size)
    total = 0
    while rows:
        updates = []
        for row in rows:
            record = json.loads(row["data"])
            metadata = record.get("data", {}).get("metadata", {})
            creator_cone_ids, creator_cone_bindings = _creator_cone_data(metadata)
            updates.append((creator_cone_ids, creator_cone_bindings, row["object_id"]))
            _replace_creator_cones(conn, row["object_id"], metadata)
        conn.executemany(
            """UPDATE items
               SET creator_cone_ids = ?, creator_cone_bindings = ?
               WHERE object_id = ?""",
            updates,
        )
        total += len(rows)
        conn.commit()
        rows = conn.execute(
            """SELECT object_id, data FROM items
               WHERE creator_cone_ids IS NULL OR creator_cone_bindings IS NULL"""
        ).fetchmany(batch_size)
    return total


def rebuild_creator_cones(conn: sqlite3.Connection, *, batch_size: int = 5000) -> int:
    conn.execute("DELETE FROM item_creator_cones")
    offset = 0
    total = 0
    while True:
        rows = conn.execute(
            "SELECT object_id, data FROM items ORDER BY object_id LIMIT ? OFFSET ?",
            (batch_size, offset),
        ).fetchall()
        if not rows:
            return total
        for row in rows:
            record = json.loads(row["data"])
            metadata = record.get("data", {}).get("metadata", {})
            _replace_creator_cones(conn, row["object_id"], metadata)
        total += len(rows)
        offset += len(rows)
        conn.commit()


def _payload_dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {"value": payload}


def upsert_person(conn: sqlite3.Connection, cone_id: str, payload: Any) -> None:
    payload = _payload_dict(payload)
    name = (
        payload.get("value")
        or f"{payload.get('givenName', '')} {payload.get('familyName', '')}".strip()
        or cone_id
    )
    conn.execute(
        "INSERT INTO persons (cone_id, name, data) VALUES (?, ?, ?) "
        "ON CONFLICT(cone_id) DO UPDATE SET name=excluded.name, data=excluded.data",
        (cone_id, name, json.dumps(payload)),
    )
    _replace_fields(
        conn, "entity_fields", {"entity_type": "person", "entity_id": cone_id}, payload
    )


def upsert_organization(conn: sqlite3.Connection, ou_id: str, payload: Any) -> None:
    payload = _payload_dict(payload)
    name = payload.get("name") or payload.get("value") or ou_id
    conn.execute(
        "INSERT INTO organizations (ou_id, name, data) VALUES (?, ?, ?) "
        "ON CONFLICT(ou_id) DO UPDATE SET name=excluded.name, data=excluded.data",
        (ou_id, name, json.dumps(payload)),
    )
    _replace_fields(
        conn, "entity_fields", {"entity_type": "organization", "entity_id": ou_id}, payload
    )


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def item_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM items").fetchone()
    return int(row["n"])


def distinct_values(conn: sqlite3.Connection, column: str, *, limit: int = 200) -> list[str]:
    if column not in FILTERABLE_COLUMNS:
        raise ValueError(f"not a filterable column: {column!r}")
    rows = conn.execute(
        f"""SELECT DISTINCT {column} AS v FROM items
            WHERE {column} != ''
            ORDER BY {column}
            LIMIT ?""",
        (limit,),
    ).fetchall()
    return [row["v"] for row in rows]


def field_paths(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT path FROM item_fields ORDER BY path").fetchall()
    return [row["path"] for row in rows]


def field_values(conn: sqlite3.Connection, path: str, *, limit: int = 500) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT value FROM item_fields
           WHERE path = ? AND value != ''
           ORDER BY value LIMIT ?""",
        (path, limit),
    ).fetchall()
    return [row["value"] for row in rows]


def export_field_matrix(
    conn: sqlite3.Connection, object_ids: list[str], paths: list[str]
) -> dict[str, dict[str, str]]:
    if not object_ids or not paths:
        return {}
    id_placeholders = ", ".join("?" for _ in object_ids)
    path_placeholders = ", ".join("?" for _ in paths)
    rows = conn.execute(
        f"""SELECT object_id, path, GROUP_CONCAT(DISTINCT value) AS value
            FROM item_fields
            WHERE object_id IN ({id_placeholders}) AND path IN ({path_placeholders})
            GROUP BY object_id, path""",
        [*object_ids, *paths],
    ).fetchall()
    matrix: dict[str, dict[str, str]] = {object_id: {} for object_id in object_ids}
    for row in rows:
        matrix[row["object_id"]][row["path"]] = row["value"] or ""
    return matrix


def query_items(
    conn: sqlite3.Connection,
    filters: dict[str, str],
    q: str = "",
    *,
    field_filters: list[tuple[str, str]] | None = None,
    cone_id: str = "",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[sqlite3.Row], int]:
    """Items matching *filters* (exact match on whitelisted columns) and *q*
    (substring search over title/creators/source_title). Returns (rows, total)."""
    where = []
    params: list[Any] = []
    for column, value in filters.items():
        if value and column in FILTERABLE_COLUMNS:
            where.append(f"{column} = ?")
            params.append(value)
    if cone_id:
        where.append(
            """object_id IN (
                   SELECT c.object_id FROM item_creator_cones c
                   WHERE c.cone_id = ? OR c.cone_id LIKE ?
               )"""
        )
        params.extend([cone_id, f"%{cone_id}%"])
    for path, value in field_filters or []:
        if not path or not value:
            continue
        where.append(
            """object_id IN (
                   SELECT f.object_id FROM item_fields f
                   WHERE f.path = ? AND f.value LIKE ?
               )"""
        )
        params.extend([path, f"%{value}%"])
    if q:
        where.append(
            """(title LIKE ? OR creators LIKE ? OR creator_cone_ids LIKE ?
                OR creator_cone_bindings LIKE ? OR source_title LIKE ?
                OR EXISTS (
                    SELECT 1 FROM item_fields f
                    WHERE f.object_id = items.object_id AND f.value LIKE ?
                ))"""
        )
        like = f"%{q}%"
        params.extend([like, like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) AS n FROM items {where_sql}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT * FROM items {where_sql} ORDER BY date_modified DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return rows, int(total)
