from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pybman import Inspector

from .conftest import make_record


def make_inspector(records):
    client = MagicMock()
    client.update_and_release.return_value = {"objectId": "x"}
    return Inspector(client, records), client


def test_check_publication_titles_detects_and_cleans():
    records = [make_record("item_1", title="  Padded Title \n"), make_record("item_2")]
    inspector, _ = make_inspector(records)
    found = inspector.check_publication_titles()
    assert list(found) == ["item_1"]
    # not cleaned yet
    assert records[0]["data"]["metadata"]["title"] == "  Padded Title \n"
    inspector.check_publication_titles(clean=True)
    assert records[0]["data"]["metadata"]["title"] == "Padded Title"


def test_check_source_titles():
    records = [make_record("item_1", sources=[{"title": " J ", "genre": "JOURNAL"}])]
    inspector, _ = make_inspector(records)
    assert list(inspector.check_source_titles(clean=True)) == ["item_1"]
    assert records[0]["data"]["metadata"]["sources"][0]["title"] == "J"


def test_check_publishers_covers_item_and_source_level():
    records = [
        make_record(
            "item_1",
            sources=[
                {
                    "title": "J",
                    "genre": "JOURNAL",
                    "publishingInfo": {"publisher": "Bad  Publisher"},
                }
            ],
        ),
    ]
    records[0]["data"]["metadata"]["publishingInfo"]["publisher"] = "OK Publisher"
    inspector, _ = make_inspector(records)
    assert list(inspector.check_publishers(clean=True)) == ["item_1"]
    source = records[0]["data"]["metadata"]["sources"][0]
    assert source["publishingInfo"]["publisher"] == "Bad Publisher"


def test_check_publishers_omission_strips_et_al():
    records = [make_record("item_1")]
    records[0]["data"]["metadata"]["publishingInfo"]["publisher"] = "Springer [u.a.]"
    inspector, _ = make_inspector(records)
    assert list(inspector.check_publishers_omission(clean=True)) == ["item_1"]
    assert records[0]["data"]["metadata"]["publishingInfo"]["publisher"] == "Springer"


def test_change_genre():
    records = [make_record("item_1", genre="ARTICLE"), make_record("item_2", genre="THESIS")]
    inspector, _ = make_inspector(records)
    updates = inspector.change_genre("PAPER", "ARTICLE")
    assert list(updates) == ["item_1"]
    assert records[0]["data"]["metadata"]["genre"] == "PAPER"
    assert records[1]["data"]["metadata"]["genre"] == "THESIS"


def test_change_source_genre():
    records = [make_record("item_1", sources=[{"title": "J", "genre": "JOURNAL"}])]
    inspector, _ = make_inspector(records)
    updates = inspector.change_source_genre("SERIES", "JOURNAL")
    assert list(updates) == ["item_1"]
    assert records[0]["data"]["metadata"]["sources"][0]["genre"] == "SERIES"


def test_change_pers_name_requires_pair():
    inspector, _ = make_inspector([make_record()])
    with pytest.raises(ValueError):
        inspector.change_pers_name(old_family_name="Lovelace")


def test_change_pers_name_family():
    records = [make_record("item_1")]
    inspector, _ = make_inspector(records)
    updates = inspector.change_pers_name(old_family_name="Lovelace", new_family_name="Byron")
    assert list(updates) == ["item_1"]
    creator = records[0]["data"]["metadata"]["creators"][0]
    assert creator["person"]["familyName"] == "Byron"


def test_clean_titles_pushes_updates_through_client():
    records = [make_record("item_1", title=" X "), make_record("item_2")]
    inspector, client = make_inspector(records)
    total = inspector.clean_titles()
    assert total == 1
    client.update_and_release.assert_called_once()
    args = client.update_and_release.call_args.args
    assert args[0] == "item_1"
    assert args[2] == "auto-update: publication title stripped"


def test_update_genre_pushes_all_matches():
    records = [make_record("item_1", genre="ARTICLE"), make_record("item_2", genre="ARTICLE")]
    inspector, client = make_inspector(records)
    assert inspector.update_genre("PAPER", "ARTICLE") == 2
    assert client.update_and_release.call_count == 2
