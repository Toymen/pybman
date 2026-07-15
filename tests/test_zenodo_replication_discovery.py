import io
import zipfile

from tools.research_data_enrichment.discover_zenodo_replication_packages import (
    archive_data_members,
    strong_record_match,
)


def test_strong_record_match_requires_title_and_author():
    row = {
        "Titel": "School choice with consent: An experiment",
        "Autor:innen": "Claudia Cerrone; Yoan Hermstrüwer; Onur Kesten",
    }
    record = {
        "metadata": {
            "title": 'Replication package for: "School Choice with Consent: An Experiment"',
            "creators": [{"name": "Cerrone, Claudia"}],
        }
    }

    assert strong_record_match(row, record) is True
    assert strong_record_match(row, {"metadata": {**record["metadata"], "creators": []}}) is False


def test_archive_data_members_rejects_code_only_zip():
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("analysis.py", "print('x')")
        archive.writestr("data/raw.dta", "data")

    assert archive_data_members(content.getvalue()) == ["data/raw.dta"]

    code_only = io.BytesIO()
    with zipfile.ZipFile(code_only, "w") as archive:
        archive.writestr("analysis.py", "print('x')")
    assert archive_data_members(code_only.getvalue()) == []
