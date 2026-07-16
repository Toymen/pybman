from unittest.mock import Mock

from tools.research_data_enrichment.discover_huggingface_arxiv_datasets import (
    arxiv_id_from_doi,
    discover_datasets,
)


def test_arxiv_id_from_doi_normalizes_leading_slash_and_case():
    assert arxiv_id_from_doi("/10.48550/arXiv.2503.01372") == "2503.01372"
    assert arxiv_id_from_doi("10.1016/example") is None


def test_discover_datasets_requires_exact_tag_and_real_data_files():
    session = Mock()
    search = Mock()
    search.json.return_value = [
        {
            "id": "author/SwissLawTranslations",
            "tags": ["arxiv:2503.01372", "format:parquet"],
        },
        {"id": "author/unrelated", "tags": ["arxiv:other"]},
    ]
    detail = Mock()
    detail.json.return_value = {
        "private": False,
        "gated": False,
        "disabled": False,
        "siblings": [
            {"rfilename": "README.md"},
            {"rfilename": "train.parquet"},
        ],
        "cardData": {"pretty_name": "Swiss Law Translations"},
    }
    session.get.side_effect = [search, detail]

    hits = discover_datasets(session, "2503.01372")

    assert len(hits) == 1
    assert hits[0]["provider"] == "huggingface-arxiv-dataset"
    assert "train.parquet" in hits[0]["evidence"]


def test_gated_dataset_is_rejected():
    session = Mock()
    search = Mock()
    search.json.return_value = [{"id": "author/private", "tags": ["arxiv:2503.01372"]}]
    detail = Mock()
    detail.json.return_value = {
        "private": False,
        "gated": True,
        "siblings": [{"rfilename": "data.parquet"}],
    }
    session.get.side_effect = [search, detail]

    assert discover_datasets(session, "2503.01372") == []
