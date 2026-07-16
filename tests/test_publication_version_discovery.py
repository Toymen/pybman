from tools.research_data_enrichment.discover_publication_versions import (
    author_surnames,
    strong_version_match,
    title_jaccard,
)


def test_author_surnames_normalize_diacritics():
    assert author_surnames("Max Großmann; Christoph Engel") == {"grossmann", "engel"}


def test_matching_version_requires_same_authors_and_title_prefix():
    candidate = {
        "Titel": "Integrating machine behavior into human subject experiments: A toolkit",
        "Autor:innen": "Christoph Engel; Max Großmann; Axel Ockenfels",
    }
    source = {
        "Titel": (
            "Integrating machine behavior into human subject experiments: A toolkit and application"
        ),
        "Autor:innen": "Christoph Engel; Max Grossmann; Axel Ockenfels",
    }
    assert title_jaccard(candidate["Titel"], source["Titel"]) > 0.55
    assert strong_version_match(candidate, source, duplicate=False)


def test_duplicate_flag_still_requires_substantial_title_overlap():
    candidate = {
        "Titel": "Deliberately ignoring inequality to avoid rejecting unfair offers",
        "Autor:innen": "Christoph Engel; Dorothee Mischkowski; Konstantin Offer; Zoe Rahwan",
    }
    source = {
        "Titel": (
            "Deliberately ignoring unfairness: Responses to uncertain inequality "
            "in the ultimatum game"
        ),
        "Autor:innen": "Konstantin Offer; Dorothee Mischkowski; Zoe Rahwan; Christoph Engel",
    }
    assert strong_version_match(candidate, source, duplicate=True)
    unrelated = {**source, "Titel": "Entirely unrelated study"}
    assert not strong_version_match(candidate, unrelated, True)
