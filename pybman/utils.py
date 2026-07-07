"""Small file and string utilities used across pybman."""

from __future__ import annotations

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


def read_plain_clean(path: str) -> list[str]:
    """Read a text file into a list of lines (without newlines)."""
    with open(path, encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def read_csv_with_header(path: str) -> dict[str, list[str]]:
    """Read a simple quoted CSV file into a column-name → values mapping."""
    lines = read_plain_clean(path)
    if not lines:
        return {}
    columns = [name.replace('"', "") for name in lines[0].split(",")]
    values: dict[str, list[str]] = {name: [] for name in columns}
    for row in lines[1:]:
        for i, v in enumerate(row.split(",", 1)):
            values[columns[i]].append(v.replace('"', ""))
    return values


def write_csv(path: str, results: list[list[str]]) -> None:
    """Write rows of strings as a quoted CSV file."""
    logger.debug("write csv to file %s", path)
    with open(path, "w", encoding="utf-8") as f:
        for row in results:
            cleaned = [clean_string(r.replace('"', "'")) for r in row]
            f.write('"' + '","'.join(cleaned) + '"\n')


def write_list(path: str, results: list[str] | list[list[str]]) -> None:
    """Write a list of strings (or of string lists) to a text file."""
    logger.debug("write list to file %s", path)
    if not results:
        return
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(results[0], str):
            f.write("\n".join(results))
        else:
            for res in results:
                f.write('"' + '"\n"'.join(res) + '"\n')


def add_value(d: dict[str, list[Any]], dkey: str = "", dvalue: Any = "") -> None:
    """Append *dvalue* to the list at *dkey*, creating it when missing."""
    d.setdefault(dkey, []).append(dvalue)


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
