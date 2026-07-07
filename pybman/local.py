"""Storage and retrieval of PubMan data in a local directory tree."""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

from pybman import utils
from pybman.data import DataSet

logger = logging.getLogger(__name__)

_DATA_SUFFIXES = (".txt", ".json", ".csv")


class LocalData:
    """A local directory holding downloaded PubMan data files."""

    def __init__(
        self,
        base_dir: str = "./data/",
        ous_dir: str = "ous",
        ctx_dir: str = "ctx",
        pers_dir: str = "pers",
        create: bool = False,
    ) -> None:
        self.data_dir = os.path.realpath(base_dir)
        self.ou_dir = os.path.join(self.data_dir, ous_dir)
        self.ctx_dir = os.path.join(self.data_dir, ctx_dir)
        self.pers_dir = os.path.join(self.data_dir, pers_dir)

        self.data_exists = os.path.exists(self.data_dir)
        self.ou_exists = os.path.exists(self.ou_dir)
        self.ctx_exists = os.path.exists(self.ctx_dir)
        self.pers_exists = os.path.exists(self.pers_dir)

        if create:
            for directory in (self.data_dir, self.ou_dir, self.ctx_dir, self.pers_dir):
                os.makedirs(directory, exist_ok=True)

        self.data_paths: list[str] = []
        if self.data_exists:
            for root, _dirs, files in os.walk(self.data_dir):
                for name in files:
                    if name.endswith(_DATA_SUFFIXES):
                        self.data_paths.append(os.path.join(root, name))
            self.data_paths.sort()
            for p in self.data_paths[:25]:
                logger.debug("local publication data: %s", p)

    def find_data_path(self, pattern: str) -> list[str]:
        """Paths of local data files whose path contains *pattern*."""
        found = [p for p in self.data_paths if pattern in p]
        if not found:
            logger.info("could not find path containing %s", pattern)
        return found

    def get_data(self, pattern: str) -> list[DataSet]:
        """Load matching local JSON data files as :class:`DataSet` objects."""
        data_sets = []
        for path in self.find_data_path(pattern):
            json_data = utils.read_json(path)
            data_idx = os.path.basename(path).split(".")[0]
            data_sets.append(DataSet(data_idx, data=json_data))
        return data_sets

    def store_data(self, idx: str, dict_data: dict[str, Any]) -> str:
        """Write *dict_data* to a dated JSON file named after *idx*."""
        path = self.generate_data_path(idx)
        logger.info("store local data of %s at %s", idx, path)
        utils.write_json(path, dict_data)
        return path

    def generate_data_path(self, data_id: str) -> str:
        """The dated file path used to store data for *data_id*."""
        return os.path.join(self.data_dir, f"{data_id}--{date.today().isoformat()}.json")
