from tools.research_data_enrichment.discover_github_data_repositories import (
    data_paths,
    exact_title_in_readme,
)


def test_data_paths_exclude_code_and_documentation():
    tree = [
        {"type": "blob", "path": "analysis.py"},
        {"type": "blob", "path": "README.md"},
        {"type": "blob", "path": "package.json"},
        {"type": "blob", "path": "tsconfig.json"},
        {"type": "blob", "path": "data/raw.csv"},
        {"type": "blob", "path": "data/splits/train.json"},
        {"type": "blob", "path": "results/model.rds"},
    ]

    assert data_paths(tree) == [
        "data/raw.csv",
        "data/splits/train.json",
        "results/model.rds",
    ]


def test_readme_requires_exact_normalized_publication_title():
    title = "A Field Experiment: Evidence & Results"
    readme = "Replication package for A Field Experiment - Evidence & Results."

    assert exact_title_in_readme(title, readme) is True
    assert exact_title_in_readme(title, "A different field experiment") is False


def test_readme_rejects_title_only_in_late_reference_list():
    title = "A Field Experiment: Evidence & Results"
    readme = "Primary project documentation.\n" + ("context\n" * 1000) + title

    assert exact_title_in_readme(title, readme) is False
