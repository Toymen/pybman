"""Small file and string utilities used across pybman."""

from __future__ import annotations

import csv
import json
import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)


def clean_string(string: str) -> str:
    """Strip and collapse whitespace/newlines in *string*."""
    string = string.strip()
    string = string.replace("\n", " ").replace("\r", " ")
    return re.sub(" +", " ", string)


def read_json(path: str) -> Any:
    """Read a JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data: Any) -> str:
    """Write *data* as pretty-printed JSON to *path*."""
    logger.debug("write to %s", path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return path


def read_csv_with_header(path: str) -> dict[str, list[str]]:
    """Read a quoted CSV file into a column-name → values mapping."""
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        values: dict[str, list[str]] = {name: [] for name in columns}
        for row in reader:
            for name in columns:
                values[name].append(row[name])
        return values


def write_csv(path: str, results: list[list[str]]) -> None:
    """Write rows of strings as a quoted CSV file."""
    logger.debug("write csv to file %s", path)
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, quoting=csv.QUOTE_ALL).writerows(results)


def url_exists(url: str, *, timeout: float = 15.0) -> bool:
    """Whether *url* is reachable (HEAD, falling back to GET)."""
    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code in (405, 403):
            response = requests.get(url, timeout=timeout, stream=True, allow_redirects=True)
            response.close()
        return response.status_code < 400
    except requests.RequestException as exc:
        logger.debug("url check failed for %s: %s", url, exc)
        return False
