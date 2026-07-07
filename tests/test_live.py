"""Optional tests against the real MPG.PuRe service.

Skipped unless ``PYBMAN_LIVE_TESTS=1`` is set. They are anonymous and
read-only; no credentials are required or used.

Run with::

    PYBMAN_LIVE_TESTS=1 pytest -m live
"""

from __future__ import annotations

import os

import pytest

from pybman import Client, queries

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("PYBMAN_LIVE_TESTS") != "1",
        reason="live tests disabled (set PYBMAN_LIVE_TESTS=1 to enable)",
    ),
]


@pytest.fixture(scope="module")
def live_client():
    with Client() as client:
        yield client


def test_service_is_reachable(live_client):
    result = live_client.items.search(queries.match_all(), size=1)
    assert result.number_of_records > 0
    assert len(result.records) == 1


def test_search_by_context_and_get_item(live_client):
    result = live_client.items.search(queries.match_all(), size=1)
    record = result.records[0]
    item_id = record["data"]["objectId"]
    item = live_client.items.get(item_id)
    assert item["objectId"] == item_id


def test_scrolling(live_client):
    records = live_client.items.search_all(queries.match_all(), page_size=5, max_records=12)
    assert len(records) == 12


def test_ous_toplevel(live_client):
    toplevel = live_client.ous.toplevel()
    assert isinstance(toplevel, list)
    assert toplevel


def test_export_bibtex(live_client):
    result = live_client.items.search(queries.match_all(), size=1)
    item_id = result.records[0]["data"]["objectId"]
    bibtex = live_client.items.export(item_id, format="BibTex")
    assert b"@" in bibtex


def test_feed_recent(live_client):
    feed = live_client.feeds.recent()
    assert "<" in feed  # some XML came back


def test_cone_language(live_client):
    lang = live_client.cone.language("deu")
    assert lang
