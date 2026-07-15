import io
import zipfile

from tools.research_data_enrichment.discover_structured_supplements import (
    elsevier_pii,
    structured_payload,
)


def test_extracts_elsevier_pii_from_crossref_text_mining_link():
    message = {
        "link": [
            {
                "URL": "https://api.elsevier.com/content/article/PII:S0167268126001940"
            }
        ]
    }

    assert elsevier_pii(message) == "S0167268126001940"


def test_zip_must_contain_structured_data_member():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("README.pdf", b"documentation")
        archive.writestr("raw/data.csv", b"a,b\n1,2")

    valid, evidence = structured_payload("zip", buffer.getvalue())

    assert valid is True
    assert "1 structured data file" in evidence


def test_pdf_like_zip_is_not_research_data():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("appendix.pdf", b"documentation")

    assert structured_payload("zip", buffer.getvalue())[0] is False
