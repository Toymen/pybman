"""Builders for common Elasticsearch queries over PubMan items.

All functions return a bare Elasticsearch query dict, ready to be passed to
:meth:`pybman.api.items.ItemsAPI.search` (or wrapped into a request body with
``size``/``from``/``sort`` by the caller).

These replace the static JSON query templates shipped with earlier pybman
releases; the produced queries are semantically equivalent.
"""

from __future__ import annotations

from typing import Any

Query = dict[str, Any]

#: Prefix of person entries in the CoNE authority, as stored in item metadata.
CONE_PERSON_PREFIX = "/persons/resource/"


def term(field: str, value: str) -> Query:
    """Exact ``term`` match on *field*."""
    return {"term": {field: {"value": value}}}


def match_phrase(field: str, value: str) -> Query:
    """``match_phrase`` on *field*."""
    return {"match_phrase": {field: {"query": value}}}


def released() -> Query:
    """Items whose public and version state are both ``RELEASED``."""
    return {
        "bool": {
            "must": [
                term("publicState", "RELEASED"),
                term("versionState", "RELEASED"),
            ]
        }
    }


def _with_released(query: Query, released_only: bool) -> Query:
    if not released_only:
        return query
    combined = released()
    combined["bool"]["must"].append(query)
    return combined


def by_context(ctx_id: str, *, released_only: bool = False) -> Query:
    """Items belonging to the context (collection) *ctx_id*."""
    return _with_released(term("context.objectId", ctx_id), released_only)


def by_organization(ou_id: str, *, released_only: bool = False) -> Query:
    """Items created by persons or organizations affiliated with *ou_id*."""
    query: Query = {
        "bool": {
            "should": [
                term("metadata.creators.person.organizations.identifierPath", ou_id),
                term("metadata.creators.organization.identifierPath", ou_id),
            ]
        }
    }
    return _with_released(query, released_only)


def by_person(cone_id: str, *, released_only: bool = False) -> Query:
    """Items created by the person with CoNE id *cone_id*.

    Accepts a bare id (``persons32341``) or a full CoNE path/URL.
    """
    bare_id = cone_id.rstrip("/").split("/")[-1]
    query = term("metadata.creators.person.identifier.id", CONE_PERSON_PREFIX + bare_id)
    return _with_released(query, released_only)


def by_language(lang_id: str, *, released_only: bool = False) -> Query:
    """Items published in language *lang_id* (ISO 639-3, e.g. ``deu``)."""
    return _with_released({"term": {"metadata.languages": {"value": lang_id}}}, released_only)


def by_journal(journal_name: str, *, released_only: bool = False) -> Query:
    """Items published in the journal named *journal_name* (or an alternative title)."""
    query: Query = {
        "bool": {
            "should": [
                match_phrase("metadata.sources.title", journal_name),
                match_phrase("metadata.sources.alternativeTitles.value", journal_name),
            ]
        }
    }
    return _with_released(query, released_only)


def by_genre(genre: str, *, released_only: bool = False) -> Query:
    """Items of publication type *genre* (e.g. ``ARTICLE``)."""
    return _with_released(term("metadata.genre", genre), released_only)


def by_identifier(identifier: str, *, released_only: bool = False) -> Query:
    """Items carrying *identifier* (e.g. a DOI, bare or as doi.org URL)."""
    value = identifier.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/"):
        value = value.removeprefix(prefix)
    query: Query = {
        "bool": {
            "should": [
                {"term": {"metadata.identifiers.id.keyword": {"value": value}}},
                match_phrase("metadata.identifiers.id", value),
            ],
            "minimum_should_match": 1,
        }
    }
    return _with_released(query, released_only)


def with_files(
    *,
    storage: str = "INTERNAL_MANAGED",
    content_categories: tuple[str, ...] = (
        "post-print",
        "pre-print",
        "any-fulltext",
        "publisher-version",
    ),
    released_only: bool = True,
) -> Query:
    """Items with attached full-text files of the given content categories."""
    query: Query = {
        "nested": {
            "path": "files",
            "query": {
                "bool": {
                    "must": [
                        term("files.storage", storage),
                        {
                            "bool": {
                                "should": [
                                    {"match": {"files.metadata.contentCategory": {"query": c}}}
                                    for c in content_categories
                                ]
                            }
                        },
                    ]
                }
            },
        }
    }
    return _with_released(query, released_only)


def with_locators(*, released_only: bool = True) -> Query:
    """Items with external full-text links (locators)."""
    return with_files(storage="EXTERNAL_URL", released_only=released_only)


def match_all() -> Query:
    """Every visible item."""
    return {"match_all": {}}
