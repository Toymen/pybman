"""In-memory collections of PubMan records with grouping/extraction helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from pybman import extract

logger = logging.getLogger(__name__)

Record = dict[str, Any]

#: Metadata date fields in order of preference for determining the year.
_DATE_FIELDS = (
    "datePublishedInPrint",
    "datePublishedOnline",
    "dateModified",
    "dateAccepted",
    "dateSubmitted",
    "dateCreated",
)


class DataSet:
    """A set of PubMan item records (as returned by the search endpoints).

    Construct from raw record lists (``raw=[...]``) or from a search
    response body (``data={"records": [...], ...}``).
    """

    def __init__(
        self,
        data_id: str,
        data: dict[str, Any] | None = None,
        raw: list[Record] | None = None,
    ) -> None:
        self.idx = data_id
        if raw is not None:
            self.records: list[Record] = raw
        elif data is not None:
            self.records = data.get("records") or []
        else:
            self.records = []
        self.collection: dict[str, Any] = {
            "numberOfRecords": len(self.records),
            "records": self.records,
        }
        self.num = len(self.records)
        self.persons = self.get_cone_persons()

    def __len__(self) -> int:
        return self.num

    def __iter__(self) -> Any:
        return iter(self.records)

    def __repr__(self) -> str:
        return f"<pybman.DataSet {self.idx!r} ({self.num} records)>"

    # -- generic grouping helpers ------------------------------------------

    def _group(
        self,
        keys_for_record: Callable[[Record], Iterable[str]],
        value_for_record: Callable[[Record], Any],
    ) -> dict[str, list[Any]]:
        groups: dict[str, list[Any]] = {}
        for record in self.records:
            for key in keys_for_record(record):
                groups.setdefault(key, []).append(value_for_record(record))
        return groups

    # -- creators / persons ---------------------------------------------------

    def get_creators(self) -> list[dict[str, Any]]:
        """All creator entries across records."""
        creators: list[dict[str, Any]] = []
        for record in self.records:
            creators.extend(record["data"]["metadata"].get("creators") or [])
        return creators

    def get_creators_from_records(self) -> list[list[dict[str, Any]]]:
        """The creators list of each record that has one."""
        return [
            record["data"]["metadata"]["creators"]
            for record in self.records
            if "creators" in record["data"]["metadata"]
        ]

    def get_creators_data(self) -> dict[str, list[Record]]:
        """Persons' CoNE ids mapped to their records."""
        creators: dict[str, list[Record]] = {}
        for record in self.records:
            found = False
            for creator in record["data"]["metadata"].get("creators") or []:
                person = creator.get("person")
                if person is None:
                    continue
                found = True
                identifier = person.get("identifier")
                if identifier and "id" in identifier:
                    idx = identifier["id"].split("/")[-1]
                    creators.setdefault(idx, []).append(record)
            if not found:
                logger.debug("no person found for %s", record["data"]["objectId"])
        return creators

    def get_cone_persons(self) -> dict[str, str]:
        """Persons' CoNE ids mapped to their names."""
        persons: dict[str, str] = {}
        for creator in self.get_creators():
            if creator.get("type") != "PERSON":
                continue
            person = creator.get("person") or {}
            identifier = person.get("identifier")
            if not identifier or identifier.get("type") != "CONE":
                continue
            cone_id = identifier["id"].split("/")[-1]
            if cone_id in persons:
                continue
            name_parts = [person.get("givenName", ""), person.get("familyName", "")]
            name = " ".join(part for part in name_parts if part)
            if not name:
                logger.debug("no name found for %s", cone_id)
            persons[cone_id] = name
        return persons

    def get_organizations(self) -> dict[str, list[str]]:
        """Creator organizations mapped to record ids."""
        organizations: dict[str, list[str]] = {}
        for record in self.records:
            metadata = record["data"]["metadata"]
            if "creators" not in metadata:
                logger.debug("%s has no creator", record["data"]["objectId"])
                continue
            for creator in metadata["creators"]:
                if creator.get("type") == "PERSON":
                    for organization in creator["person"].get("organizations") or []:
                        organizations.setdefault(organization["name"], []).append(
                            record["data"]["objectId"]
                        )
                elif creator.get("type") == "ORGANIZATION":
                    organizations.setdefault(creator["organization"]["name"], []).append(
                        record["data"]["objectId"]
                    )
                else:
                    logger.debug("unknown creator type %s", creator.get("type"))
        return organizations

    # -- titles ---------------------------------------------------------------

    def get_titles(self) -> dict[str, list[str]]:
        """Titles mapped to record ids (records without a title are skipped)."""
        return self._group(
            lambda r: [title] if (title := r["data"]["metadata"].get("title")) else [],
            lambda r: r["data"]["objectId"],
        )

    def get_titles_from_source(self) -> dict[str, list[str]]:
        """Source titles mapped to record ids."""
        return self._group(
            lambda r: [s["title"] for s in r["data"]["metadata"].get("sources") or []],
            lambda r: r["data"]["objectId"],
        )

    get_sources_titles = get_titles_from_source

    # -- genres -----------------------------------------------------------------

    def get_genres(self) -> dict[str, list[str]]:
        """Genres mapped to record ids (records without a genre are skipped)."""
        return self._group(
            lambda r: [genre] if (genre := r["data"]["metadata"].get("genre")) else [],
            lambda r: r["data"]["objectId"],
        )

    def get_genre_data(self) -> dict[str, list[Record]]:
        """Genres mapped to records (records without a genre are skipped)."""
        return self._group(
            lambda r: [genre] if (genre := r["data"]["metadata"].get("genre")) else [], lambda r: r
        )

    def get_genre_relationships(self) -> dict[str, dict[str, list[str]]]:
        """Genres mapped to source genres mapped to record ids."""
        genres: dict[str, dict[str, list[str]]] = {}
        for record in self.records:
            genre = record["data"]["metadata"].get("genre")
            if genre is None:
                logger.debug("no genre found for %s", record["data"].get("objectId"))
                continue
            by_source = genres.setdefault(genre, {})
            sources = record["data"]["metadata"].get("sources")
            if sources:
                for source in sources:
                    by_source.setdefault(source["genre"], []).append(record["data"]["objectId"])
            else:
                by_source.setdefault("NONE", []).append(record["data"]["objectId"])
        return genres

    def get_source_genres(self) -> dict[str, list[str]]:
        """Source genres mapped to record ids."""
        return self._group(
            lambda r: [s["genre"] for s in r["data"]["metadata"].get("sources") or []],
            lambda r: r["data"]["objectId"],
        )

    def get_source_genres_data(self) -> dict[str, list[Record]]:
        """Source genres mapped to records."""
        return self._group(
            lambda r: [s["genre"] for s in r["data"]["metadata"].get("sources") or []],
            lambda r: r,
        )

    # -- publishing info ----------------------------------------------------------

    @staticmethod
    def _pubinfo_values(record: Record, field: str) -> list[str]:
        values = []
        metadata = record["data"]["metadata"]
        if field in metadata.get("publishingInfo", {}):
            values.append(metadata["publishingInfo"][field])
        for source in metadata.get("sources") or []:
            if field in source.get("publishingInfo", {}):
                values.append(source["publishingInfo"][field])
        return values

    def get_places(self) -> dict[str, list[str]]:
        """Publication places mapped to record ids."""
        return self._group(
            lambda r: self._pubinfo_values(r, "place"),
            lambda r: r["data"]["objectId"],
        )

    def get_publishers(self) -> dict[str, list[str]]:
        """Publishers mapped to record ids."""
        return self._group(
            lambda r: self._pubinfo_values(r, "publisher"),
            lambda r: r["data"]["objectId"],
        )

    # -- contexts ------------------------------------------------------------------

    def get_contexts(self) -> dict[str, str]:
        """Record ids mapped to their context id."""
        return {
            record["data"]["objectId"]: record["data"]["context"]["objectId"]
            for record in self.records
        }

    # -- journals / series ------------------------------------------------------------

    def get_journals(self) -> dict[str, list[str]]:
        """Journal titles mapped to record ids (source genre JOURNAL)."""
        journals: dict[str, list[str]] = {}
        for item_id, source in self.get_source_from_items_with_source_genre("JOURNAL").items():
            journals.setdefault(source["title"], []).append(item_id)
        return journals

    def get_journals_data(self) -> dict[str, list[Record]]:
        """Journal titles mapped to records (source genre JOURNAL)."""
        journals: dict[str, list[Record]] = {}
        for item_id, source in self.get_source_from_items_with_source_genre("JOURNAL").items():
            journals.setdefault(source["title"], []).append(self.get_item(item_id))
        return journals

    def get_series(self) -> dict[str, list[str]]:
        """Series titles mapped to record ids (source genre SERIES)."""
        series: dict[str, list[str]] = {}
        for item_id, source in self.get_source_from_items_with_source_genre("SERIES").items():
            series.setdefault(source["title"], []).append(item_id)
        return series

    # -- dates ---------------------------------------------------------------------------

    @staticmethod
    def _year(record: Record) -> str | None:
        metadata = record["data"]["metadata"]
        for field in _DATE_FIELDS:
            if field in metadata:
                return str(metadata[field]).split("-")[0]
        logger.debug("no publication date found for %s", record["data"]["objectId"])
        return None

    def get_years(self) -> dict[str, list[str]]:
        """Publication years mapped to record ids."""
        return self._group(
            lambda r: [y] if (y := self._year(r)) else [],
            lambda r: r["data"]["objectId"],
        )

    def get_years_data(self) -> dict[str, list[Record]]:
        """Publication years mapped to records."""
        return self._group(lambda r: [y] if (y := self._year(r)) else [], lambda r: r)

    def get_items_from_year(self, year: str) -> list[str]:
        """Record ids with the given publication year."""
        return self.get_years().get(year, [])

    def get_items_from_year_data(self, year: str) -> list[Record]:
        """Records with the given publication year."""
        return self.get_years_data().get(year, [])

    # -- languages -----------------------------------------------------------------------

    @staticmethod
    def _language(record: Record) -> str:
        if "languages" not in extract.metadata(record):
            return "NONE"
        langs = extract.languages_from_item(record)
        if len(langs) == 1:
            return langs[0]
        return "MULTI"

    def get_languages(self) -> dict[str, list[Any]]:
        """Languages mapped to record ids.

        Records without language data are grouped under ``"NONE"``; records
        with several languages under ``"MULTI"`` as ``(id, languages)``.
        """
        languages: dict[str, list[Any]] = {}
        for record in self.records:
            lang = self._language(record)
            item_idx = extract.idx_from_item(record)
            if lang == "MULTI":
                languages.setdefault(lang, []).append(
                    (item_idx, extract.languages_from_item(record))
                )
            else:
                languages.setdefault(lang, []).append(item_idx)
        return languages

    def get_languages_data(self) -> dict[str, list[Record]]:
        """Languages mapped to records (``NONE``/``MULTI`` as in get_languages)."""
        return self._group(lambda r: [self._language(r)], lambda r: r)

    # -- identifiers -------------------------------------------------------------------------

    def get_sources_identifiers(self) -> dict[str, list[str]]:
        """Source identifier types mapped to record ids."""
        return self._group(
            lambda r: [
                identifier["type"]
                for source in r["data"]["metadata"].get("sources") or []
                for identifier in source.get("identifiers") or []
            ],
            lambda r: r["data"]["objectId"],
        )

    # -- item selection --------------------------------------------------------------------------

    def get_item(self, item_id: str) -> Record:
        """The record with the given id (empty dict when absent)."""
        for record in self.records:
            if record["data"]["objectId"] == item_id:
                return record
        return {}

    def get_items_with_genre(self, genre: str) -> dict[str, Record]:
        """Record ids mapped to records with the given genre."""
        return {
            record["data"]["objectId"]: record
            for record in self.records
            if record["data"]["metadata"].get("genre") == genre
        }

    def get_items_released(self) -> list[Record]:
        """Records whose public and version state are RELEASED."""
        return [
            record
            for record in self.records
            if record["data"].get("publicState") == "RELEASED"
            and record["data"].get("versionState") == "RELEASED"
        ]

    def get_items_submitted(self) -> dict[str, Any]:
        """Persistence ids mapped to item data with state SUBMITTED."""
        return {
            record["persistenceId"]: record["data"]
            for record in self.records
            if record["data"].get("publicState") == "SUBMITTED"
            and record["data"].get("versionState") == "SUBMITTED"
        }

    def get_items_with_external_url(self) -> dict[str, Record]:
        """Record ids mapped to records with EXTERNAL_URL file entries."""
        return {
            record["data"]["objectId"]: record
            for record in self.records
            if any(f.get("storage") == "EXTERNAL_URL" for f in record["data"].get("files") or [])
        }

    def get_items_with_identifier_uri(self) -> dict[str, Record]:
        """Record ids mapped to records carrying a URI identifier."""
        return {
            record["data"]["objectId"]: record
            for record in self.records
            if any(
                identifier.get("type") == "URI"
                for identifier in record["data"]["metadata"].get("identifiers") or []
            )
        }

    def get_items_with_source_genre(self, source_genre: str) -> dict[str, Record]:
        """Record ids mapped to records with the given source genre."""
        return {
            record["data"]["objectId"]: record
            for record in self.records
            if any(
                source.get("genre") == source_genre
                for source in record["data"]["metadata"].get("sources") or []
            )
        }

    def get_source_from_items_with_source_genre(self, source_genre: str) -> dict[str, Any]:
        """Record ids mapped to the (last) source entry of the given genre."""
        records: dict[str, Any] = {}
        for record in self.records:
            for source in record["data"]["metadata"].get("sources") or []:
                if source.get("genre") == source_genre:
                    records[record["data"]["objectId"]] = source
        return records
