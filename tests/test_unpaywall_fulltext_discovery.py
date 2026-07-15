from tools.research_data_enrichment.discover_from_unpaywall_fulltext import open_pdf_urls


def test_open_pdf_urls_are_unique_https_pdf_locations():
    work = {
        "best_oa_location": {"url_for_pdf": "https://repo.test/paper.pdf"},
        "oa_locations": [
            {"url_for_pdf": "https://repo.test/paper.pdf"},
            {"url_for_pdf": "http://insecure.test/paper.pdf"},
            {"url": "https://repo.test/landing", "url_for_pdf": None},
            {"url_for_pdf": "https://other.test/paper.pdf"},
        ],
    }

    assert open_pdf_urls(work) == [
        "https://repo.test/paper.pdf",
        "https://other.test/paper.pdf",
    ]
