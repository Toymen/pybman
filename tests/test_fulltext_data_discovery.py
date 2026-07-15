from pybman.discovery.fulltext import data_availability_sections, extract_fulltext_data_links


def test_extracts_repository_link_from_explicit_data_availability_section():
    text = """Results
    The treatment increased cooperation.
    Data availability
    The raw data and analysis scripts are available at https://osf.io/abc12/.
    References
    Unrelated citation https://doi.org/10.1016/example.
    """

    links = extract_fulltext_data_links(text)

    assert [link.url for link in links] == ["https://osf.io/abc12/"]
    assert links[0].heading.lower() == "data availability"


def test_rejects_request_only_and_future_data_statements():
    text = """Data availability
    Data will be made available upon reasonable request.
    References
    """

    assert extract_fulltext_data_links(text) == []


def test_accepts_pdf_annotation_url_only_on_data_availability_page():
    text = """Availability of data and materials
    The dataset and code are archived in the project repository.
    Funding
    None.
    """

    links = extract_fulltext_data_links(text, annotation_urls=("https://zenodo.org/records/123",))

    assert [link.url for link in links] == ["https://zenodo.org/records/123"]


def test_rejects_article_doi_and_unrelated_web_links():
    text = """Data availability
    Supplementary discussion is at https://doi.org/10.1016/j.test.2026.1 and
    https://example.org/material. Data are available on request.
    References
    """

    assert extract_fulltext_data_links(text) == []


def test_sections_stop_at_next_article_heading():
    text = """Open Practices Statement
    Raw data are at https://osf.io/xyz89/.
    Acknowledgements
    A repository mentioned later is https://zenodo.org/records/999.
    """

    sections = data_availability_sections(text)
    links = extract_fulltext_data_links(text)

    assert len(sections) == 1
    assert "mentioned later" not in sections[0][1]
    assert [link.url for link in links] == ["https://osf.io/xyz89/"]


def test_inline_data_availability_heading_is_supported():
    text = (
        "Results. Data availability: The raw data are deposited at "
        "https://zenodo.org/records/456. Acknowledgements\nNone."
    )

    assert [link.url for link in extract_fulltext_data_links(text)] == [
        "https://zenodo.org/records/456"
    ]


def test_explicit_data_sentence_outside_named_section_is_supported():
    text = (
        "The study was preregistered, and data, materials and code are available at "
        "https://doi.org/10.17605/OSF.IO/RGAWF. The experiment then followed."
    )

    assert [link.url for link in extract_fulltext_data_links(text)] == [
        "https://doi.org/10.17605/OSF.IO/RGAWF"
    ]


def test_unrelated_pdf_annotation_is_not_attached_to_request_only_statement():
    text = "Data availability\nData will be made available on request."

    assert extract_fulltext_data_links(
        text, annotation_urls=("https://doi.org/10.5281/zenodo.999",)
    ) == []
