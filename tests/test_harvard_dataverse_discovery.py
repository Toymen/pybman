from tools.research_data_enrichment.discover_harvard_dataverse import strong_dataset_match

ROW = {
    "Titel": "A field experiment on reputation and selection effects",
    "Autor:innen": "Alex Example; Matthias Sutter",
}


def test_strong_dataset_match_requires_title_author_files_and_publication():
    item = {
        "name": "Replication Data for: A field experiment on reputation and selection effects",
        "authors": ["Sutter, Matthias"],
        "fileCount": 3,
        "publicationStatuses": ["Published"],
        "global_id": "doi:10.7910/DVN/ABC123",
    }

    assert strong_dataset_match(ROW, item) is True
    assert strong_dataset_match(ROW, {**item, "fileCount": 0}) is False
    assert strong_dataset_match(ROW, {**item, "authors": ["Other, Person"]}) is False
    assert strong_dataset_match(ROW, {**item, "publicationStatuses": ["Draft"]}) is False


def test_strong_dataset_match_rejects_weak_title_overlap():
    item = {
        "name": "Unrelated field experiment",
        "authors": ["Sutter, Matthias"],
        "fileCount": 1,
        "publicationStatuses": ["Published"],
        "global_id": "doi:10.7910/DVN/ABC123",
    }

    assert strong_dataset_match(ROW, item) is False
