"""Fetch every publication matching a query, plus the persons/organizations
it references, into the local SQLite store."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from pybman import Client, extract
from pybman.exceptions import PubManError
from webapp import store

logger = logging.getLogger(__name__)
PAGE_SIZE = 1000
COMMIT_EVERY = 5000
FIELD_LOOKUP_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_item_fields_path_value ON item_fields(path, value)"
)


def _dereference(
    conn: Any, record: dict[str, Any], client: Client, seen_persons: set[str], seen_orgs: set[str]
) -> None:
    for creator in extract.persons_from_item(record):
        person_id, id_type = extract.persons_id_from_creator(creator)
        if id_type == "CONE" and person_id and person_id not in seen_persons:
            seen_persons.add(person_id)
            try:
                store.upsert_person(conn, person_id, client.cone.person(person_id))
            except PubManError:
                logger.warning("could not fetch person %s", person_id, exc_info=True)

        for identifier, _path, name, address in extract.persons_affiliation_from_creator(creator):
            org_id = identifier
            if not org_id or org_id in seen_orgs:
                continue
            seen_orgs.add(org_id)
            try:
                store.upsert_organization(conn, org_id, client.ous.get(org_id))
            except PubManError:
                logger.debug("falling back to embedded data for organization %s", org_id)
                store.upsert_organization(conn, org_id, {"name": name, "address": address})


def run(
    client: Client, query: dict[str, Any], db_path: str, *, dereference_authorities: bool = False
) -> int:
    """Fetch every record matching *query*, store it, and dereference the
    persons/organizations it references. Returns the number of items stored.

    If fewer records were retrieved than the server reports for the same
    query (a dropped page mid-scroll), one full retry pass is made so the
    store ends up complete rather than silently partial.
    """
    seen_persons: set[str] = set()
    seen_orgs: set[str] = set()
    started = time.time()
    count = 0
    with store.connect(db_path) as conn:
        expected = client.items.count(query)
        store.set_meta(conn, "expected_item_count", str(expected))
        store.set_meta(conn, "sync_started_at", datetime.now(timezone.utc).isoformat())
        conn.execute("DROP INDEX IF EXISTS idx_item_fields_path_value")
        conn.commit()

        try:
            for record in client.items.search_iter(query, page_size=PAGE_SIZE):
                store.upsert_item(conn, record)
                if dereference_authorities:
                    _dereference(conn, record, client, seen_persons, seen_orgs)
                count += 1
                if count % COMMIT_EVERY == 0:
                    store.set_meta(conn, "sync_progress_count", str(count))
                    conn.commit()
                    logger.info("sync progress: %d of %d items", count, expected)

            if count < expected:
                logger.warning(
                    "sync stored %d of %d reported records, retrying once", count, expected
                )
                for record in client.items.search_iter(query, page_size=PAGE_SIZE):
                    store.upsert_item(conn, record)
                    if dereference_authorities:
                        _dereference(conn, record, client, seen_persons, seen_orgs)
                count = store.item_count(conn)
                if count < expected:
                    logger.warning("still missing records after retry: %d of %d", count, expected)

            store.set_meta(conn, "last_synced_at", datetime.now(timezone.utc).isoformat())
            store.set_meta(conn, "item_count", str(count))
            store.set_meta(conn, "sync_progress_count", str(count))
        finally:
            logger.info("rebuilding item field lookup index")
            conn.execute(FIELD_LOOKUP_INDEX)
            count = store.item_count(conn)

    logger.info("sync finished: %d items in %.1fs", count, time.time() - started)
    return count
