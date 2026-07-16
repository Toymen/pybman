"""Shared Elasticsearch request-body building for the ``/search`` endpoints."""

from __future__ import annotations

from typing import Any


def search_body(
    query: dict[str, Any],
    *,
    size: int | None,
    from_: int | None,
    sort: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Wrap a bare query into a request body, or pass a full body through.

    A complete request body (``{"query": ..., "size": ..., ...}``) is
    detected by the presence of a top-level ``"query"`` key — bare
    Elasticsearch queries never have one (their top-level key is the query
    type, e.g. ``"bool"``/``"match"``). ``size``/``from``/``sort`` are only
    applied if not already set on a passed-through full body.
    """
    if "query" in query:
        body = dict(query)
    else:
        body = {"query": query}
    if size is not None:
        body.setdefault("size", size)
    if from_ is not None:
        body.setdefault("from", from_)
    if sort is not None:
        body.setdefault("sort", sort)
    return body
