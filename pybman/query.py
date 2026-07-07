"""Deprecated query template classes.

This module preserves the classic pybman query classes as thin wrappers
around :mod:`pybman.queries`. New code should call those builder functions
directly.
"""

from __future__ import annotations

import warnings
from typing import Any

from pybman import queries

Query = dict[str, Any]


def _deprecated(name: str) -> None:
    warnings.warn(
        f"pybman.query.{name} is deprecated, use the builder functions in pybman.queries instead",
        DeprecationWarning,
        stacklevel=3,
    )


class AllQuery:
    def __init__(self) -> None:
        _deprecated("AllQuery")

    def get_files_query(self) -> Query:
        return {"query": queries.with_files(), "size": "5000", "from": "0"}

    def get_locators_query(self) -> Query:
        return {"query": queries.with_locators(), "size": "5000", "from": "0"}


class ContextQuery:
    def __init__(self) -> None:
        _deprecated("ContextQuery")

    def get_item_query(self, ctx_id: str) -> Query:
        return {"query": queries.by_context(ctx_id), "size": "50", "from": "0"}

    def get_released_item_query(self, ctx_id: str) -> Query:
        return {
            "query": queries.by_context(ctx_id, released_only=True),
            "size": "500",
            "from": "0",
        }


class OrgUnitQuery:
    def __init__(self) -> None:
        _deprecated("OrgUnitQuery")

    def get_item_query(self, ou_id: str) -> Query:
        return {"query": queries.by_organization(ou_id), "size": "50", "from": "0"}

    def get_item_released_query(self, ou_id: str) -> Query:
        return {
            "query": queries.by_organization(ou_id, released_only=True),
            "size": "500",
            "from": "0",
        }

    # the classic API was inconsistent about this method name
    get_released_item_query = get_item_released_query


class PersQuery:
    def __init__(self) -> None:
        _deprecated("PersQuery")

    def get_item_query(self, cone_id: str) -> Query:
        return {"query": queries.by_person(cone_id), "size": "50", "from": "0"}

    def get_item_released_query(self, cone_id: str) -> Query:
        return {
            "query": queries.by_person(cone_id, released_only=True),
            "size": "500",
            "from": "0",
        }

    get_released_item_query = get_item_released_query


class LangQuery:
    def __init__(self) -> None:
        _deprecated("LangQuery")

    def get_item_query(self, lang_id: str) -> Query:
        return {"query": queries.by_language(lang_id), "size": "50", "from": "0"}

    def get_released_item_query(self, lang_id: str) -> Query:
        return {
            "query": queries.by_language(lang_id, released_only=True),
            "size": "500",
            "from": "0",
        }


class JournalQuery:
    def __init__(self) -> None:
        _deprecated("JournalQuery")

    def get_item_query(self, jour_name: str) -> Query:
        return {"query": queries.by_journal(jour_name), "size": "50", "from": "0"}

    def get_released_item_query(self, jour_name: str) -> Query:
        return {
            "query": queries.by_journal(jour_name, released_only=True),
            "size": "500",
            "from": "0",
        }
