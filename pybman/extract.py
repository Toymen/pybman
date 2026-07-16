"""Field extraction helpers for PubMan item records.

All functions operate on plain record dicts as returned by the search
endpoints (``{"data": {...}}`` envelopes) and degrade gracefully — missing
fields yield empty strings/lists rather than raising.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

Record = dict[str, Any]


def value_from_level(field: str, level: dict[str, Any]) -> Any:
    """Value of *field* in *level*, or ``""`` when absent."""
    return level.get(field, "")


def list_from_level(field: str, level: dict[str, Any]) -> list[Any]:
    """List value of *field* in *level*, or ``[]`` when absent."""
    return level.get(field, [])


def field_in_level(field: str, level: dict[str, Any]) -> bool:
    """Whether *field* exists in *level*."""
    return field in level


def iter_fields(field: str, level: dict[str, Any]) -> Iterator[Any]:
    """Iterate over the entries of *field* in *level* (empty when absent)."""
    yield from level.get(field) or []


def data(item: Record) -> dict[str, Any]:
    """The ``data`` part of an item record."""
    return item["data"]


def metadata(item: Record) -> dict[str, Any]:
    """The metadata of an item record."""
    return data(item)["metadata"]


def idx_from_item(item: Record) -> str:
    """Object id of an item."""
    return data(item)["objectId"]


def ctx_from_item(item: Record) -> dict[str, Any]:
    """Context of an item."""
    return data(item)["context"]


def ctx_idx_from_item(item: Record) -> str:
    """Context id of an item."""
    return ctx_from_item(item)["objectId"]


def title_from_item(item: Record) -> str:
    """Title of an item."""
    return metadata(item)["title"]


def genre_from_item(item: Record) -> str:
    """Genre of an item."""
    return metadata(item)["genre"]


def creators_from_item(item: Record) -> list[dict[str, Any]]:
    """Creators of an item."""
    return metadata(item)["creators"]


def field_from_creator(field: str, creator: dict[str, Any]) -> Any:
    """Field of a creator entry."""
    return value_from_level(field, creator)


def persons_from_item(item: Record) -> list[dict[str, Any]]:
    """Creators of an item that are persons."""
    return [creator for creator in creators_from_item(item) if creator.get("person")]


def persons_name_from_creator(creator: dict[str, Any]) -> tuple[str, str]:
    """``(given name, family name)`` of a person creator."""
    return (
        value_from_level("givenName", creator["person"]),
        value_from_level("familyName", creator["person"]),
    )


def persons_identifier_from_creator(creator: dict[str, Any]) -> Any:
    """Identifier entry of a person creator."""
    return value_from_level("identifier", creator["person"])


def persons_id_from_creator(creator: dict[str, Any]) -> tuple[str, str]:
    """``(id, id type)`` of a person creator."""
    pers_id = persons_identifier_from_creator(creator) or {}
    return (
        value_from_level("id", pers_id).split("/")[-1],
        value_from_level("type", pers_id),
    )


def persons_organizations_from_creator(creator: dict[str, Any]) -> list[dict[str, Any]]:
    """Organizations of a person creator."""
    return list_from_level("organizations", creator["person"])


def persons_affiliation_from_creator(
    creator: dict[str, Any],
) -> list[tuple[Any, Any, Any, Any]]:
    """``(identifier, identifierPath, name, address)`` per organization."""
    return [
        (
            value_from_level("identifier", organization),
            value_from_level("identifierPath", organization),
            value_from_level("name", organization),
            value_from_level("address", organization),
        )
        for organization in persons_organizations_from_creator(creator)
    ]


def role_from_creator(creator: dict[str, Any]) -> str:
    """Role of a creator (e.g. ``AUTHOR``)."""
    return value_from_level("role", creator)


def field_from_metadata(field: str, item: Record, value: bool = True) -> Any:
    """Field from the metadata of an item (``""``/``[]`` when absent)."""
    if value:
        return value_from_level(field, metadata(item))
    return list_from_level(field, metadata(item))


def languages_from_item(item: Record) -> list[str]:
    """Languages of an item."""
    return field_from_metadata("languages", item, value=False)


def identifiers_from_item(item: Record) -> list[tuple[str, str]]:
    """``(type, id)`` pairs of the item's identifiers (``[]`` when absent)."""
    return [
        (value_from_level("type", idx), value_from_level("id", idx))
        for idx in iter_fields("identifiers", metadata(item))
    ]


#: Deprecated misspelled alias, kept for backward compatibility.
identifers_from_item = identifiers_from_item


def pubinfo_from_item(item: Record) -> Any:
    """Publishing info of an item."""
    return field_from_metadata("publishingInfo", item)


def field_from_pubinfo(field: str, item: Record) -> Any:
    """Field from the publishing info of an item."""
    pubinfo = pubinfo_from_item(item)
    if field_in_level(field, pubinfo):
        return pubinfo[field]
    return ""


def place_from_item(item: Record) -> str:
    """Publishing place of an item."""
    return field_from_pubinfo("place", item)


def publisher_from_item(item: Record) -> str:
    """Publisher of an item."""
    return field_from_pubinfo("publisher", item)


def date_pubprint_from_item(item: Record) -> str:
    """Print publication date of an item."""
    return field_from_metadata("datePublishedInPrint", item)


def date_pubonline_from_item(item: Record) -> str:
    """Online publication date of an item."""
    return field_from_metadata("datePublishedOnline", item)


def date_modified_from_item(item: Record) -> str:
    """Modification date of an item."""
    return field_from_metadata("dateModified", item)


def date_accepted_from_item(item: Record) -> str:
    """Acceptance date of an item."""
    return field_from_metadata("dateAccepted", item)


def date_submitted_from_item(item: Record) -> str:
    """Submission date of an item."""
    return field_from_metadata("dateSubmitted", item)


def date_created_from_item(item: Record) -> str:
    """Creation date of an item."""
    return field_from_metadata("dateCreated", item)


def date_from_item(item: Record) -> str:
    """Best available date of an item (print, online, modified, ...)."""
    return (
        date_pubprint_from_item(item)
        or date_pubonline_from_item(item)
        or date_modified_from_item(item)
        or date_accepted_from_item(item)
        or date_submitted_from_item(item)
        or date_created_from_item(item)
        or ""
    )


def sources(item: Record) -> Iterator[dict[str, Any]]:
    """Iterate over the sources of an item."""
    yield from metadata(item).get("sources") or []


def sources_titles_from_item(item: Record) -> list[str]:
    """Source titles of an item."""
    return [value_from_level("title", source) for source in sources(item)]


def sources_titles_genres_from_item(item: Record) -> list[tuple[str, str]]:
    """``(title, genre)`` pairs of the item's sources."""
    return [
        (value_from_level("title", source), value_from_level("genre", source))
        for source in sources(item)
    ]


def creators_from_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Creators of a source."""
    return list_from_level("creators", source)


def sources_persons_from_item(item: Record) -> list[list[dict[str, Any]]]:
    """Person creators per source of an item."""
    return [
        [creator for creator in creators_from_source(source) if field_in_level("person", creator)]
        for source in sources(item)
    ]


def sources_persons_id_from_item(
    item: Record,
) -> list[list[tuple[str, str, str, str, str]]]:
    """``(id, given name, family name, role, id type)`` per source person."""
    result = []
    for source in sources_persons_from_item(item):
        entries = []
        for person in source:
            pers_name = persons_name_from_creator(person)
            pers_id, pers_id_type = persons_id_from_creator(person)
            entries.append(
                (pers_id, pers_name[0], pers_name[1], role_from_creator(person), pers_id_type)
            )
        result.append(entries)
    return result


def sources_identifiers_from_item(item: Record) -> list[list[tuple[str, str]]]:
    """``(type, id)`` pairs per source of an item (``[]`` per source without any)."""
    return [
        [
            (value_from_level("type", idx), value_from_level("id", idx))
            for idx in iter_fields("identifiers", source)
        ]
        for source in sources(item)
    ]


def items(records: list[Record]) -> Iterator[Record]:
    """Iterate over records."""
    yield from records


def titles_from_records(records: list[Record]) -> list[str]:
    """Titles of all records."""
    return [title_from_item(item) for item in records]


def source_titles(collection: list[Record]) -> list[str]:
    """Non-empty source titles of all records."""
    return [
        source_title
        for item in collection
        for source_title in sources_titles_from_item(item)
        if source_title
    ]


def source_titles_genres(collection: list[Record]) -> list[tuple[str, str]]:
    """``(title, genre)`` pairs of all records' sources."""
    return [
        source_title_genre
        for item in collection
        for source_title_genre in sources_titles_genres_from_item(item)
    ]
