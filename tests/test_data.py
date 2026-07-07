from __future__ import annotations

from pybman import DataSet

from .conftest import make_record


def build_dataset() -> DataSet:
    records = [
        make_record(
            "item_1",
            title="First",
            genre="ARTICLE",
            sources=[
                {
                    "title": "Journal A",
                    "genre": "JOURNAL",
                    "publishingInfo": {"place": "Paris", "publisher": "Publisher B"},
                    "identifiers": [{"id": "1234-5678", "type": "ISSN"}],
                }
            ],
        ),
        make_record(
            "item_2",
            title="Second",
            genre="THESIS",
            creators=[
                {
                    "person": {"givenName": "Grace", "familyName": "Hopper"},
                    "role": "AUTHOR",
                    "type": "PERSON",
                },
                {
                    "organization": {"name": "Institute Two", "identifier": "ou_2"},
                    "role": "AUTHOR",
                    "type": "ORGANIZATION",
                },
            ],
            identifiers=[{"id": "http://example.org/x", "type": "URI"}],
            public_state="SUBMITTED",
            version_state="SUBMITTED",
        ),
        make_record(
            "item_3",
            title="Third",
            genre="ARTICLE",
            sources=[{"title": "Series S", "genre": "SERIES"}],
            files=[{"storage": "EXTERNAL_URL", "content": "http://example.org/f"}],
            languages=["deu", "eng"],
        ),
    ]
    # item_3: override date so it lands in another year
    records[2]["data"]["metadata"]["datePublishedInPrint"] = "2021-01-01"
    return DataSet("test", raw=records)


def test_len_iter_and_repr():
    ds = build_dataset()
    assert len(ds) == 3
    assert ds.num == 3
    assert [r["data"]["objectId"] for r in ds] == ["item_1", "item_2", "item_3"]
    assert "test" in repr(ds)


def test_from_data_dict():
    ds = DataSet("x", data={"numberOfRecords": 1, "records": [make_record()]})
    assert ds.num == 1


def test_empty_dataset():
    ds = DataSet("empty")
    assert ds.num == 0
    assert ds.persons == {}


def test_cone_persons_extracted_on_init():
    ds = build_dataset()
    assert ds.persons == {"persons100": "Ada Lovelace"}


def test_get_titles():
    ds = build_dataset()
    assert ds.get_titles() == {
        "First": ["item_1"],
        "Second": ["item_2"],
        "Third": ["item_3"],
    }


def test_get_genres_and_data():
    ds = build_dataset()
    assert ds.get_genres() == {"ARTICLE": ["item_1", "item_3"], "THESIS": ["item_2"]}
    data = ds.get_genre_data()
    assert [r["data"]["objectId"] for r in data["ARTICLE"]] == ["item_1", "item_3"]


def test_get_genre_relationships():
    ds = build_dataset()
    rel = ds.get_genre_relationships()
    assert rel["ARTICLE"]["JOURNAL"] == ["item_1"]
    assert rel["ARTICLE"]["SERIES"] == ["item_3"]
    assert rel["THESIS"]["NONE"] == ["item_2"]


def test_get_organizations():
    ds = build_dataset()
    orgs = ds.get_organizations()
    assert orgs["Institute One"] == ["item_1", "item_3"]
    assert orgs["Institute Two"] == ["item_2"]


def test_get_places_and_publishers_cover_sources():
    ds = build_dataset()
    places = ds.get_places()
    assert places["Berlin"] == ["item_1", "item_2", "item_3"]
    assert places["Paris"] == ["item_1"]
    publishers = ds.get_publishers()
    assert publishers["Publisher B"] == ["item_1"]


def test_get_contexts():
    ds = build_dataset()
    assert ds.get_contexts() == {"item_1": "ctx_1", "item_2": "ctx_1", "item_3": "ctx_1"}


def test_get_journals_and_series():
    ds = build_dataset()
    assert ds.get_journals() == {"Journal A": ["item_1"]}
    journals_data = ds.get_journals_data()
    assert journals_data["Journal A"][0]["data"]["objectId"] == "item_1"
    assert ds.get_series() == {"Series S": ["item_3"]}


def test_get_years():
    ds = build_dataset()
    years = ds.get_years()
    assert years["2020"] == ["item_1", "item_2"]
    assert years["2021"] == ["item_3"]
    assert ds.get_items_from_year("2021") == ["item_3"]
    assert ds.get_items_from_year("1999") == []


def test_get_languages_multi_and_single():
    ds = build_dataset()
    languages = ds.get_languages()
    assert languages["eng"] == ["item_1", "item_2"]
    assert languages["MULTI"] == [("item_3", ["deu", "eng"])]


def test_get_sources_identifiers():
    ds = build_dataset()
    assert ds.get_sources_identifiers() == {"ISSN": ["item_1"]}


def test_get_item():
    ds = build_dataset()
    assert ds.get_item("item_2")["data"]["objectId"] == "item_2"
    assert ds.get_item("item_404") == {}


def test_get_items_released_and_submitted():
    ds = build_dataset()
    released = ds.get_items_released()
    assert [r["data"]["objectId"] for r in released] == ["item_1", "item_3"]
    submitted = ds.get_items_submitted()
    assert list(submitted) == ["item_2_1"]


def test_get_items_with_source_genre_and_sources():
    ds = build_dataset()
    assert list(ds.get_items_with_source_genre("SERIES")) == ["item_3"]
    sources = ds.get_source_from_items_with_source_genre("JOURNAL")
    assert sources["item_1"]["title"] == "Journal A"


def test_get_items_with_external_url_and_uri():
    ds = build_dataset()
    assert list(ds.get_items_with_external_url()) == ["item_3"]
    assert list(ds.get_items_with_identifier_uri()) == ["item_2"]
