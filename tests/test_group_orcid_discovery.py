from tools.research_data_enrichment.discover_by_group_orcid import group_leaders, tags


def test_tags_remove_admin_values_and_merge_transliteration_aliases():
    assert tags("gloeckner; DP; preprint; glöckner") == ("glöckner",)
    assert tags("gueth; güth; externDP") == ("güth",)


def test_group_leaders_use_most_frequent_author_per_research_group():
    rows = [
        {"Forschungsgruppen-Tags": "engel", "Autor:innen": "Christoph Engel; A Person"},
        {"Forschungsgruppen-Tags": "engel; DP", "Autor:innen": "Christoph Engel; B Person"},
        {"Forschungsgruppen-Tags": "sutter", "Autor:innen": "Matthias Sutter"},
    ]

    assert group_leaders(rows) == {"engel": "Christoph Engel", "sutter": "Matthias Sutter"}


def test_group_leader_prefers_author_whose_surname_matches_tag_on_frequency_tie():
    rows = [
        {"Forschungsgruppen-Tags": "schneider", "Autor:innen": "Matthias Sutter"},
        {"Forschungsgruppen-Tags": "schneider", "Autor:innen": "Sebastian O. Schneider"},
    ]

    assert group_leaders(rows) == {"schneider": "Sebastian O. Schneider"}
