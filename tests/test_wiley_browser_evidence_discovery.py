from unittest.mock import Mock

from tools.research_data_enrichment.discover_wiley_browser_evidence import (
    osf_data_files,
    osf_identity,
    validated_hits,
)


def test_osf_identity_requires_complete_view_token():
    assert osf_identity("https://osf.io/yef3k/?view_only=" + "a" * 32) == (
        "yef3k",
        "a" * 32,
    )
    assert osf_identity("https://osf.io/yef3k/?view_only=short") is None


def test_osf_data_files_recurses_and_excludes_documentation():
    session = Mock()
    root = Mock()
    root.json.return_value = {
        "data": [
            {
                "attributes": {"name": "Data", "kind": "folder"},
                "relationships": {
                    "files": {"links": {"related": {"href": "https://api.test/folder"}}}
                },
            },
            {"attributes": {"name": "codebook.xlsx", "kind": "file"}},
        ],
        "links": {},
    }
    folder = Mock()
    folder.json.return_value = {
        "data": [{"attributes": {"name": "raw.csv", "kind": "file"}}],
        "links": {},
    }
    session.get.side_effect = [root, folder]

    assert osf_data_files(session, "https://osf.io/yef3k/?view_only=" + "b" * 32) == [
        "raw.csv"
    ]


def test_request_only_statement_is_not_accepted():
    observation = {
        "data_availability_statement": "Data are available upon request.",
        "links": ["https://osf.io/yef3k/"],
    }
    assert validated_hits(observation) == []
