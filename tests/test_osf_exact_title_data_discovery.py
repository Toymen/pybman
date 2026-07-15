from unittest.mock import Mock, patch

from tools.research_data_enrichment.discover_osf_exact_title_data import (
    discover_row,
    matching_nodes,
)


def osf_record(title="Legal interpretation as coordination"):
    return {
        "id": "3yexq",
        "attributes": {"title": title},
        "embeds": {
            "contributors": {
                "data": [
                    {
                        "embeds": {
                            "users": {
                                "data": {
                                    "attributes": {
                                        "full_name": "Piotr Bystranowski"
                                    }
                                }
                            }
                        }
                    }
                ]
            }
        },
    }


def test_matching_nodes_requires_title_and_contributor():
    row = {
        "Titel": "Legal interpretation as coordination",
        "Autor:innen": "Piotr Bystranowski; Kevin Tobia",
    }
    assert matching_nodes(row, {"data": [osf_record()]})[0]["id"] == "3yexq"
    row["Autor:innen"] = "Unrelated Author"
    assert matching_nodes(row, {"data": [osf_record()]}) == []


@patch(
    "tools.research_data_enrichment.discover_osf_exact_title_data.osf_project_evidence"
)
def test_discover_row_requires_verified_data_files(project_evidence):
    project_evidence.return_value = (
        "Legal interpretation as coordination",
        {"bystranowski", "tobia"},
        ["main_study_long.csv", "pretest.csv"],
    )
    response = Mock()
    response.json.return_value = {"data": [osf_record()]}
    session = Mock()
    session.get.return_value = response
    row = {
        "Titel": "Legal interpretation as coordination",
        "Autor:innen": "Piotr Bystranowski; Kevin Tobia",
    }

    hits = discover_row(row, session)

    assert len(hits) == 1
    assert hits[0]["provider"] == "osf-exact-title-data"
    assert "main_study_long.csv" in hits[0]["evidence"]


@patch(
    "tools.research_data_enrichment.discover_osf_exact_title_data.osf_project_evidence"
)
def test_discover_row_rejects_fileless_project(project_evidence):
    project_evidence.return_value = (
        "Legal interpretation as coordination",
        {"bystranowski"},
        [],
    )
    response = Mock()
    response.json.return_value = {"data": [osf_record()]}
    session = Mock()
    session.get.return_value = response
    row = {
        "Titel": "Legal interpretation as coordination",
        "Autor:innen": "Piotr Bystranowski; Kevin Tobia",
    }
    assert discover_row(row, session) == []
