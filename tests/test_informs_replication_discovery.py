import io
import zipfile

import responses

from tools.research_data_enrichment.discover_informs_replication import (
    DOWNLOAD_URL,
    LANDING_URL,
    archive_data_members,
    process,
)


def zipped(*files: tuple[str, bytes]) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        for name, content in files:
            archive.writestr(name, content)
    return target.getvalue()


def test_archive_data_members_rejects_dictionary_only_and_finds_data():
    content = zipped(
        ("variable dictionary.xlsx", b"docs"),
        ("__MACOSX/data/._observations.dta", b"metadata"),
        ("data/observations.dta", b"research data"),
    )

    assert archive_data_members(content) == ["data/observations.dta"]


@responses.activate
def test_process_accepts_official_doi_archive_with_research_data():
    responses.get(
        LANDING_URL,
        body='<input type="hidden" name="token" value="abc123" />',
    )
    responses.post(
        DOWNLOAD_URL,
        body=zipped(("replication/rawdata.csv", b"a,b\n1,2\n")),
        content_type="binary/octet-stream",
    )

    result = process(
        {
            "PuRe-ID": "item_1",
            "DOI": "10.1287/mnsc.2022.00990",
            "Titel": "A publication",
        }
    )

    assert result["found"] is True
    assert result["hits"][0]["provider"] == "informs-replication"
    assert result["hits"][0]["url"].endswith("doi=mnsc.2022.00990")


@responses.activate
def test_process_rejects_code_and_dictionary_only_archive():
    responses.get(
        LANDING_URL,
        body='<input type="hidden" name="token" value="abc123" />',
    )
    responses.post(
        DOWNLOAD_URL,
        body=zipped(("analysis.do", b"code"), ("data dictionary.csv", b"metadata")),
    )

    result = process({"PuRe-ID": "item_2", "DOI": "10.1287/mnsc.2024.05507"})

    assert result["found"] is False
