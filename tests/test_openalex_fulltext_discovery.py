from tools.research_data_enrichment.discover_from_openalex_fulltext import open_pdf_urls


def test_open_pdf_urls_require_explicit_open_access_and_https():
    work = {
        "best_oa_location": {"is_oa": True, "pdf_url": "https://repo.test/paper.pdf"},
        "locations": [
            {"is_oa": True, "pdf_url": "https://repo.test/paper.pdf"},
            {"is_oa": False, "pdf_url": "https://closed.test/paper.pdf"},
            {"is_oa": True, "pdf_url": "http://insecure.test/paper.pdf"},
            {"is_oa": True, "pdf_url": "https://other.test/paper.pdf"},
        ],
    }

    assert open_pdf_urls(work) == [
        "https://repo.test/paper.pdf",
        "https://other.test/paper.pdf",
    ]
