from unittest.mock import Mock, patch

from tools.research_data_enrichment.discover_degruyter_browser_evidence import (
    osf_node_from_publisher_link,
    validated_hits,
)


def test_osf_node_from_publisher_doi_link():
    assert (
        osf_node_from_publisher_link("https://doi.org/10.17605/OSF.IO/JZ6WP")
        == "jz6wp"
    )


@patch(
    "tools.research_data_enrichment.discover_degruyter_browser_evidence.osf_project_evidence"
)
def test_validated_hit_requires_matching_author_and_data_file(project_evidence):
    project_evidence.return_value = (
        "Supplementary materials",
        {"luckner", "winter"},
        ["data.csv"],
    )
    observation = {
        "data_availability_statement": (
            "Experimental data and code is available here: "
            "https://doi.org/10.17605/OSF.IO/JZ6WP"
        ),
        "links": ["https://doi.org/10.17605/OSF.IO/JZ6WP"],
    }
    publication = {"Autor:innen": "Katharina Luckner; Fabian Winter"}

    hits = validated_hits(observation, publication, Mock())

    assert len(hits) == 1
    assert hits[0]["provider"] == "degruyter-browser-data-availability"
    assert "data.csv" in hits[0]["evidence"]


@patch(
    "tools.research_data_enrichment.discover_degruyter_browser_evidence.osf_project_evidence"
)
def test_request_only_statement_is_rejected(project_evidence):
    observation = {
        "data_availability_statement": "Data are available upon request.",
        "links": ["https://doi.org/10.17605/OSF.IO/JZ6WP"],
    }
    assert validated_hits(observation, {"Autor:innen": "Fabian Winter"}, Mock()) == []
    project_evidence.assert_not_called()
