from tools.research_data_enrichment.discover_github_doi_repositories import (
    publication_context_in_readme,
)

ROW = {
    "DOI": "10.1234/example.1",
    "Titel": "A field experiment on cooperation and trust",
    "Autor:innen": "Alex Example; Beate Sample; Chris Researcher",
}


def test_publication_context_requires_doi_data_title_and_authors():
    readme = """
    # A field experiment on cooperation and trust
    Replication data for Alex Example, Beate Sample, and Chris Researcher.
    DOI: 10.1234/example.1
    """

    assert publication_context_in_readme(ROW, readme) is True
    no_data_context = readme.replace("Replication data", "Article")
    assert publication_context_in_readme(ROW, no_data_context) is False
    assert publication_context_in_readme(ROW, readme.replace("10.1234/example.1", "")) is False


def test_publication_context_rejects_citation_without_author_overlap():
    readme = """
    Dataset for an unrelated project by Other Person.
    Reference: A field experiment on cooperation and trust. DOI: 10.1234/example.1
    """

    assert publication_context_in_readme(ROW, readme) is False
