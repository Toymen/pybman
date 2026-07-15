from unittest.mock import Mock

from tools.research_data_enrichment.discover_cambridge_osf_data import (
    discover_row,
    extract_osf_links,
    publication_surnames,
)


def response(payload=None, *, text="", url=""):
    result = Mock()
    result.json.return_value = payload
    result.text = text
    result.url = url
    return result


def test_extract_osf_links_decodes_and_deduplicates_view_token():
    token = "a" * 32
    page = (
        f'<a href="https://osf.io/abc12/?view_only={token}&amp;x=1">data</a>'
        f" https://osf.io/abc12/?view_only={token}&amp;x=1"
    )
    assert extract_osf_links(page) == [
        f"https://osf.io/abc12/?view_only={token}&x=1"
    ]


def test_publication_surnames_handles_diacritics():
    assert publication_surnames("Jenna Neufeld; Jérôme Olsen") == {
        "neufeld",
        "olsen",
    }


def test_discover_row_requires_author_overlap_and_data_file():
    session = Mock()
    page = response(
        text='<a href="https://osf.io/aq7zd/">data</a>',
        url="https://www.cambridge.org/core/article/example",
    )
    node = response({"data": {"attributes": {"title": "Safety compliance data"}}})
    contributors = response(
        {
            "data": [
                {
                    "embeds": {
                        "users": {"data": {"attributes": {"full_name": "Jerome Olsen"}}}
                    }
                }
            ]
        }
    )
    files = response(
        {
            "data": [{"attributes": {"name": "Safety_data.sav", "kind": "file"}}],
            "links": {},
        }
    )
    session.get.side_effect = [page, node, contributors, files]
    row = {
        "DOI": "10.1017/bpp.2022.42",
        "Titel": "Safety compliance",
        "Autor:innen": "Jerome Olsen; Jenna Neufeld",
    }

    hits = discover_row(row, session)

    assert len(hits) == 1
    assert hits[0]["provider"] == "cambridge-osf-data"
    assert "Safety_data.sav" in hits[0]["evidence"]


def test_discover_row_rejects_nonmatching_repository_contributors():
    session = Mock()
    page = response(
        text='<a href="https://osf.io/aq7zd/">citation</a>',
        url="https://www.cambridge.org/core/article/example",
    )
    node = response({"data": {"attributes": {"title": "Unrelated data"}}})
    contributors = response(
        {
            "data": [
                {
                    "embeds": {
                        "users": {"data": {"attributes": {"full_name": "Other Author"}}}
                    }
                }
            ]
        }
    )
    files = response(
        {
            "data": [{"attributes": {"name": "data.csv", "kind": "file"}}],
            "links": {},
        }
    )
    session.get.side_effect = [page, node, contributors, files]
    row = {
        "DOI": "10.1017/bpp.2022.42",
        "Titel": "Safety compliance",
        "Autor:innen": "Jerome Olsen",
    }

    assert discover_row(row, session) == []


def test_view_only_project_retries_public_contributors_when_anonymous():
    token = "a" * 32
    session = Mock()
    page = response(
        text=f'<a href="https://osf.io/adeh5/?view_only={token}">data</a>',
        url="https://www.cambridge.org/core/article/example",
    )
    node = response({"data": {"attributes": {"title": "Replication data"}}})
    anonymous_contributors = response({"data": [], "meta": {"anonymous": True}})
    public_contributors = response(
        {
            "data": [
                {
                    "embeds": {
                        "users": {"data": {"attributes": {"full_name": "Christoph Engel"}}}
                    }
                }
            ]
        }
    )
    public_contributors.ok = True
    files = response(
        {
            "data": [{"attributes": {"name": "experiment.csv", "kind": "file"}}],
            "links": {},
        }
    )
    session.get.side_effect = [page, node, anonymous_contributors, public_contributors, files]
    row = {
        "DOI": "10.1017/jdm.2025.10005",
        "Titel": "Sabotaging competitors",
        "Autor:innen": "Christoph Engel; Dan Simon",
    }

    assert len(discover_row(row, session)) == 1
