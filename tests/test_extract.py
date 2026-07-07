from __future__ import annotations

from pybman import extract

from .conftest import make_record


def test_basic_field_extraction():
    record = make_record("item_1", title="A Title", genre="ARTICLE")
    assert extract.idx_from_item(record) == "item_1"
    assert extract.ctx_idx_from_item(record) == "ctx_1"
    assert extract.title_from_item(record) == "A Title"
    assert extract.genre_from_item(record) == "ARTICLE"
    assert extract.languages_from_item(record) == ["eng"]


def test_creator_helpers():
    record = make_record()
    persons = extract.persons_from_item(record)
    assert len(persons) == 1
    creator = persons[0]
    assert extract.persons_name_from_creator(creator) == ("Ada", "Lovelace")
    assert extract.persons_id_from_creator(creator) == ("persons100", "CONE")
    assert extract.role_from_creator(creator) == "AUTHOR"
    affiliations = extract.persons_affiliation_from_creator(creator)
    assert affiliations[0][2] == "Institute One"


def test_person_without_identifier():
    record = make_record(
        creators=[
            {"person": {"givenName": "G", "familyName": "H"}, "role": "AUTHOR", "type": "PERSON"}
        ]
    )
    creator = extract.persons_from_item(record)[0]
    assert extract.persons_id_from_creator(creator) == ("", "")


def test_date_fallback_chain():
    record = make_record()
    del record["data"]["metadata"]["datePublishedInPrint"]
    record["data"]["metadata"]["dateAccepted"] = "2019-01-02"
    assert extract.date_from_item(record) == "2019-01-02"
    del record["data"]["metadata"]["dateAccepted"]
    assert extract.date_from_item(record) == ""


def test_pubinfo_extraction():
    record = make_record()
    assert extract.place_from_item(record) == "Berlin"
    assert extract.publisher_from_item(record) == "Publisher A"
    del record["data"]["metadata"]["publishingInfo"]
    assert extract.place_from_item(record) == ""


def test_identifiers_default_to_empty_pair():
    record = make_record()
    assert extract.identifiers_from_item(record) == [("", "")]
    record["data"]["metadata"]["identifiers"] = [{"id": "10.1/x", "type": "DOI"}]
    assert extract.identifiers_from_item(record) == [("DOI", "10.1/x")]


def test_source_helpers():
    record = make_record(
        sources=[
            {
                "title": "Journal A",
                "genre": "JOURNAL",
                "identifiers": [{"id": "1234-5678", "type": "ISSN"}],
                "creators": [
                    {
                        "person": {"givenName": "E", "familyName": "Editor"},
                        "role": "EDITOR",
                        "type": "PERSON",
                    }
                ],
            }
        ]
    )
    assert extract.sources_titles_from_item(record) == ["Journal A"]
    assert extract.sources_titles_genres_from_item(record) == [("Journal A", "JOURNAL")]
    assert extract.sources_identifiers_from_item(record) == [[("ISSN", "1234-5678")]]
    persons = extract.sources_persons_id_from_item(record)
    assert persons == [[("", "E", "Editor", "EDITOR", "")]]


def test_collection_helpers():
    records = [make_record("item_1", title="T1"), make_record("item_2", title="T2")]
    assert extract.titles_from_records(records) == ["T1", "T2"]
    records[0]["data"]["metadata"]["sources"] = [{"title": "S", "genre": "JOURNAL"}]
    assert extract.source_titles(records) == ["S"]
    assert extract.source_titles_genres(records) == [("S", "JOURNAL")]
