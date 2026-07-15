import responses

from tools.research_data_enrichment.discover_elife_data import ARTICLE_URL, process


@responses.activate
def test_elife_structured_data_statement_yields_repository_link():
    responses.get(
        ARTICLE_URL.format(article_id="95823"),
        json={
            "dataSets": {
                "availability": [
                    {
                        "text": (
                            "The processed version of the dataset is publicly available at "
                            '<a href="https://github.com/example/study/tree/main/data">GitHub</a>.'
                        )
                    }
                ]
            }
        },
    )

    result = process(
        {
            "PuRe-ID": "item_1",
            "DOI": "10.7554/eLife.95823.4",
            "Titel": "A longitudinal study",
        }
    )

    assert result["found"] is True
    assert result["hits"][0]["url"] == "https://github.com/example/study/tree/main/data"


@responses.activate
def test_elife_request_only_statement_is_not_research_data_link():
    responses.get(
        ARTICLE_URL.format(article_id="42"),
        json={
            "dataSets": {
                "availability": [
                    {"text": "Raw data are available from the authors upon reasonable request."}
                ]
            }
        },
    )

    result = process({"PuRe-ID": "item_2", "DOI": "10.7554/eLife.42"})

    assert result["found"] is False
