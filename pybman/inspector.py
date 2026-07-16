"""Batch inspection and cleanup of PubMan records.

The :class:`Inspector` walks a list of records, detects (and optionally
fixes) common metadata problems, and pushes fixes back to the repository via
an authenticated :class:`pybman.client.Client`.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from pybman import utils

if TYPE_CHECKING:
    from pybman.client import Client

logger = logging.getLogger(__name__)

Record = dict[str, Any]

#: Matches "[et al.]" style omission markers in publisher/place values.
_ET_AL = re.compile(r"\s?\[et\.? ?al\.?\s?\]|\s?\[u\.?\s?a\.?\]|\s?\[etc\.?\]")


class Inspector:
    """Check and clean records, writing fixes back through *client*."""

    def __init__(self, client: Client, records: list[Record]) -> None:
        self.client = client
        self.records = records

    # -- checks -----------------------------------------------------------

    def check_publication_titles(self, clean: bool = False) -> dict[str, Record]:
        """Records whose title has surplus whitespace or control characters."""
        updates: dict[str, Record] = {}
        for record in self.records:
            metadata = record["data"]["metadata"]
            title = metadata["title"]
            if title != utils.clean_string(title):
                if clean:
                    metadata["title"] = utils.clean_string(title)
                updates[record["data"]["objectId"]] = record
        return updates

    def check_source_titles(self, clean: bool = False) -> dict[str, Record]:
        """Records with unclean source titles."""
        updates: dict[str, Record] = {}
        for record in self.records:
            for source in record["data"]["metadata"].get("sources") or []:
                if source["title"] != utils.clean_string(source["title"]):
                    if clean:
                        source["title"] = utils.clean_string(source["title"])
                    updates[record["data"]["objectId"]] = record
        return updates

    def _check_pubinfo_field(self, field: str, transform: Any, clean: bool) -> dict[str, Record]:
        updates: dict[str, Record] = {}
        for record in self.records:
            metadata = record["data"]["metadata"]
            levels = [metadata, *(metadata.get("sources") or [])]
            for level in levels:
                pubinfo = level.get("publishingInfo")
                if not pubinfo or field not in pubinfo:
                    continue
                value = pubinfo[field]
                if value != transform(value):
                    if clean:
                        pubinfo[field] = transform(value)
                    updates[record["data"]["objectId"]] = record
        return updates

    def check_publishers(self, clean: bool = False) -> dict[str, Record]:
        """Records with unclean publisher values (item or source level)."""
        return self._check_pubinfo_field("publisher", utils.clean_string, clean)

    def check_publishers_omission(self, clean: bool = False) -> dict[str, Record]:
        """Records whose publisher carries an "[et al.]" marker."""
        return self._check_pubinfo_field("publisher", lambda v: _ET_AL.sub("", v), clean)

    def check_publishing_places(self, clean: bool = False) -> dict[str, Record]:
        """Records with unclean publishing places (item or source level)."""
        return self._check_pubinfo_field("place", utils.clean_string, clean)

    def check_publishing_places_omission(self, clean: bool = False) -> dict[str, Record]:
        """Records whose publishing place carries an "[et al.]" marker."""
        return self._check_pubinfo_field("place", lambda v: _ET_AL.sub("", v), clean)

    def check_publication_uri(self) -> dict[str, str]:
        """Record ids mapped to unreachable URI identifiers."""
        updates: dict[str, str] = {}
        for record in self.records:
            for idx in record["data"]["metadata"].get("identifiers") or []:
                if idx.get("type") == "URI" and not utils.url_exists(idx["id"]):
                    updates[record["data"]["objectId"]] = idx["id"]
        return updates

    def check_publication_url(self) -> dict[str, str]:
        """Record ids mapped to unreachable external file URLs."""
        updates: dict[str, str] = {}
        for record in self.records:
            for f in record["data"].get("files") or []:
                if f.get("storage") == "EXTERNAL_URL" and not utils.url_exists(f["content"]):
                    updates[record["data"]["objectId"]] = f["content"]
        return updates

    # -- transformations --------------------------------------------------

    def change_genre(self, new_genre: str, old_genre: str) -> dict[str, Record]:
        """Change the genre of matching records (in memory)."""
        updates: dict[str, Record] = {}
        for record in self.records:
            if record["data"]["metadata"]["genre"] == old_genre:
                record["data"]["metadata"]["genre"] = new_genre
                updates[record["data"]["objectId"]] = record
            else:
                logger.debug("skipping item %s", record["data"]["objectId"])
        return updates

    def change_source_genre(self, new_genre: str, old_genre: str) -> dict[str, Record]:
        """Change the source genre of matching records (in memory)."""
        updates: dict[str, Record] = {}
        for record in self.records:
            for source in record["data"]["metadata"].get("sources") or []:
                if source["genre"] == old_genre:
                    source["genre"] = new_genre
                    updates[record["data"]["objectId"]] = record
                    break
            else:
                logger.debug("skipping item %s", record["data"]["objectId"])
        return updates

    def change_pers_name(
        self,
        old_family_name: str | None = None,
        new_family_name: str | None = None,
        old_given_name: str | None = None,
        new_given_name: str | None = None,
    ) -> dict[str, Record]:
        """Rename a person across records (in memory)."""
        updates: dict[str, Record] = {}
        if old_family_name and new_family_name:
            field, old, new = "familyName", old_family_name, new_family_name
        elif old_given_name and new_given_name:
            field, old, new = "givenName", old_given_name, new_given_name
        else:
            raise ValueError("pass either old and new family name or old and new given name")
        for record in self.records:
            for creator in record["data"]["metadata"].get("creators") or []:
                if creator.get("type") == "PERSON" and creator["person"].get(field) == old:
                    creator["person"][field] = new
                    updates[record["data"]["objectId"]] = record
        return updates

    # -- write-back operations ------------------------------------------------

    def _push(self, updates: dict[str, Record], comment: str) -> int:
        """Push each update, continuing past individual failures.

        A single item failing to update (transient server error, stale
        ``lastModificationDate`` from a concurrent edit) used to abort the
        whole batch, silently discarding whichever updates hadn't been
        pushed yet with no record of which ones. Failures are now logged
        with the offending item id and the batch continues; the return
        value is the count that actually succeeded.
        """
        total = 0
        failed: list[str] = []
        for item_id, record in updates.items():
            try:
                self.client.update_and_release(item_id, record["data"], comment)
            except Exception:
                logger.exception("failed to push update for %s", item_id)
                failed.append(item_id)
                continue
            total += 1
        if failed:
            logger.warning("%d of %d updates failed to push: %s", len(failed), len(updates), failed)
        return total

    def update_genre(self, new_genre: str, old_genre: str) -> int:
        """Change genres and push the updates to the repository."""
        updates = self.change_genre(new_genre, old_genre)
        total = self._push(
            updates, f"auto-update: change genre of item from {old_genre} to {new_genre}"
        )
        logger.info("updated genre of %d items", total)
        return total

    def update_source_genre(self, new_genre: str, old_genre: str) -> int:
        """Change source genres and push the updates to the repository."""
        updates = self.change_source_genre(new_genre, old_genre)
        total = self._push(
            updates,
            f"auto-update: change source genre of item from {old_genre} to {new_genre}",
        )
        logger.info("updated source genre of %d items", total)
        return total

    def clean_titles(self) -> int:
        """Strip publication titles and push the updates."""
        updates = self.check_publication_titles(clean=True)
        total = self._push(updates, "auto-update: publication title stripped")
        logger.info("updated %d publication titles", total)
        return total

    def clean_source_titles(self) -> int:
        """Strip source titles and push the updates."""
        updates = self.check_source_titles(clean=True)
        total = self._push(updates, "auto-update: source title stripped")
        logger.info("updated %d source titles", total)
        return total

    def clean_publishers(self) -> int:
        """Clean publisher values and push the updates."""
        updates = self.check_publishers(clean=True)
        total = self._push(updates, "auto-update: remove control characters from publisher value")
        logger.info("updated %d publishers", total)
        return total

    def clean_publishing_places(self) -> int:
        """Clean publishing place values and push the updates."""
        updates = self.check_publishing_places(clean=True)
        total = self._push(
            updates, "auto-update: remove control characters from publishing place value"
        )
        logger.info("updated %d publishing places", total)
        return total
