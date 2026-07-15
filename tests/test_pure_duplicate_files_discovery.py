import responses

from tools.research_data_enrichment.discover_pure_duplicate_files import SEARCH_URL, process


@responses.activate
def test_same_doi_public_research_data_file_is_accepted():
    responses.post(
        SEARCH_URL,
        json={
            "records": [
                {"data": {"objectId": "item_original", "files": []}},
                {
                    "data": {
                        "objectId": "item_duplicate",
                        "files": [
                            {
                                "objectId": "file_1",
                                "name": "observations.csv",
                                "visibility": "PUBLIC",
                                "content": "/rest/items/item_duplicate/component/file_1/content",
                                "mimeType": "text/csv",
                                "metadata": {"contentCategory": "research-data"},
                            }
                        ],
                    }
                },
            ]
        },
    )

    result = process(
        {
            "PuRe-ID": "item_original",
            "DOI": "10.1000/example",
            "Titel": "Publication title",
        }
    )

    assert result["found"] is True
    assert result["hits"][0]["provider"] == "pure-duplicate-file"
    assert result["hits"][0]["url"].endswith("/file_1/content")


@responses.activate
def test_same_doi_public_dictionary_file_is_rejected():
    responses.post(
        SEARCH_URL,
        json={
            "records": [
                {
                    "data": {
                        "objectId": "item_duplicate",
                        "files": [
                            {
                                "name": "data dictionary.csv",
                                "visibility": "PUBLIC",
                                "content": "/file.csv",
                                "metadata": {"contentCategory": "research-data"},
                            }
                        ],
                    }
                }
            ]
        },
    )

    result = process({"PuRe-ID": "item_original", "DOI": "10.1000/example"})

    assert result["found"] is False
