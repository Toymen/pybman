from __future__ import annotations

import json

from pybman import LocalData, utils

from .conftest import make_record


def test_clean_string():
    assert utils.clean_string("  a\nb\r  c  ") == "a b c"


def test_json_roundtrip(tmp_path):
    path = str(tmp_path / "data.json")
    utils.write_json(path, {"a": [1, 2]})
    assert utils.read_json(path) == {"a": [1, 2]}


def test_write_csv_and_read_with_header(tmp_path):
    path = str(tmp_path / "table.csv")
    utils.write_csv(path, [["id", "name"], ["1", 'quo"ted']])
    table = utils.read_csv_with_header(path)
    assert table["id"] == ["1"]
    assert table["name"] == ['quo"ted']


def test_url_exists(responses):
    responses.head("https://ok.example.org/x", status=200)
    responses.head("https://gone.example.org/x", status=404)
    assert utils.url_exists("https://ok.example.org/x")
    assert not utils.url_exists("https://gone.example.org/x")


def test_url_exists_falls_back_to_get_on_405(responses):
    responses.head("https://nohead.example.org/x", status=405)
    responses.get("https://nohead.example.org/x", status=200)
    assert utils.url_exists("https://nohead.example.org/x")


def test_url_exists_handles_connection_errors(responses):
    # nothing registered: responses raises ConnectionError
    assert not utils.url_exists("https://unreachable.example.org/x")


def test_local_data_create_and_roundtrip(tmp_path):
    base = tmp_path / "data"
    local = LocalData(str(base), create=True)
    assert base.is_dir()
    assert (base / "ous").is_dir()

    record = make_record("item_1")
    payload = {"numberOfRecords": 1, "records": [record]}
    path = local.store_data("ctx_1", payload)
    assert path.startswith(str(base))

    # re-scan directory
    local = LocalData(str(base))
    found = local.find_data_path("ctx_1")
    assert found == [path]
    datasets = local.get_data("ctx_1")
    assert datasets[0].num == 1
    assert datasets[0].idx.startswith("ctx_1--")


def test_local_data_missing_dir(tmp_path):
    local = LocalData(str(tmp_path / "nope"))
    assert not local.data_exists
    assert local.find_data_path("x") == []
    assert local.get_data("x") == []


def test_generate_data_path_joins_correctly(tmp_path):
    local = LocalData(str(tmp_path), create=True)
    path = local.generate_data_path("ctx_9")
    assert path.startswith(str(tmp_path))
    assert "/ctx_9--" in path
    assert json.dumps({}) is not None  # keep json import used
