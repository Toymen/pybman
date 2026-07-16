"""Items / publications endpoints (``/items``)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import IO, Any, BinaryIO

from pybman._http import Transport
from pybman.api._search import search_body as _search_body
from pybman.models import Item, Record, SearchResult

#: Hard server-side cap on ``size`` for one search request.
MAX_PAGE_SIZE = 5000

#: Default page size used by the scrolling helpers.
DEFAULT_PAGE_SIZE = 100


class ItemsAPI:
    """Publication items: retrieval, search, lifecycle and files."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    # -- retrieval -------------------------------------------------------

    def get(self, item_id: str) -> Item:
        """GET /items/{itemId} — one publication item (``ItemVersionVO``)."""
        result: Item = self._transport.request_json("GET", f"/items/{item_id}")
        return result

    def history(self, item_id: str) -> list[dict[str, Any]]:
        """GET /items/{itemId}/history — version history of an item."""
        result: list[dict[str, Any]] = self._transport.request_json(
            "GET", f"/items/{item_id}/history"
        )
        return result

    # -- search ----------------------------------------------------------

    def search(
        self,
        query: dict[str, Any],
        *,
        size: int | None = 10,
        from_: int | None = 0,
        sort: list[dict[str, Any]] | None = None,
        scroll: bool = False,
    ) -> SearchResult:
        """POST /items/search — run an Elasticsearch query over items.

        ``query`` is either a bare Elasticsearch query (e.g. produced by
        :mod:`pybman.queries`) or a complete request body containing its own
        ``query``/``size``/``from``/``sort`` keys. The server caps ``size``
        at 5000; pass ``scroll=True`` and use :meth:`scroll` (or simply
        :meth:`search_iter`) to page through larger result sets.

        Anonymous searches only see released, public items; searching with a
        logged-in client can additionally return pending/submitted versions.
        """
        body = _search_body(query, size=size, from_=from_, sort=sort)
        payload = self._transport.request_json(
            "POST", "/items/search", params={"scroll": "true" if scroll else None}, json=body
        )
        return SearchResult.from_api(payload)

    def scroll(self, scroll_id: str) -> SearchResult:
        """GET /items/search/scroll — fetch the next page of a scrolled search."""
        payload = self._transport.request_json(
            "GET", "/items/search/scroll", params={"scrollId": scroll_id}
        )
        return SearchResult.from_api(payload)

    def search_iter(
        self,
        query: dict[str, Any],
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_records: int | None = None,
        sort: list[dict[str, Any]] | None = None,
    ) -> Iterator[Record]:
        """Iterate over all records matching *query*, scrolling as needed.

        Yields records lazily; stop iterating early to stop requesting.
        ``max_records`` bounds the total number of yielded records.
        """
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
        yielded = 0
        result = self.search(query, size=page_size, from_=0, sort=sort, scroll=True)
        while True:
            for record in result.records:
                if max_records is not None and yielded >= max_records:
                    return
                yield record
                yielded += 1
            if not result.records or not result.scroll_id:
                return
            if yielded >= result.number_of_records:
                return
            result = self.scroll(result.scroll_id)

    def search_all(
        self,
        query: dict[str, Any],
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_records: int | None = None,
        sort: list[dict[str, Any]] | None = None,
    ) -> list[Record]:
        """Collect all records matching *query* into a list (see search_iter)."""
        return list(
            self.search_iter(query, page_size=page_size, max_records=max_records, sort=sort)
        )

    def count(self, query: dict[str, Any]) -> int:
        """Number of records matching *query* (fetches no record data)."""
        return self.search(query, size=0, from_=0).number_of_records

    # -- export ----------------------------------------------------------

    def export(
        self,
        item_id: str,
        *,
        format: str = "json",
        citation: str | None = None,
        csl_cone_id: str | None = None,
    ) -> bytes:
        """GET /items/{itemId}/export — item in an export format.

        ``format`` is one of :class:`pybman.models.ExportFormat` (e.g.
        ``"BibTex"``, ``"EndNote"``, ``"Marc_Xml"``, ``"pdf"``, ``"docx"``).
        Citation-oriented formats additionally require ``citation`` (e.g.
        ``"APA"``); ``citation="CSL"`` also needs ``csl_cone_id``.
        """
        response = self._transport.request(
            "GET",
            f"/items/{item_id}/export",
            params={"format": format, "citation": citation, "cslConeId": csl_cone_id},
        )
        return response.content

    def export_search(
        self,
        query: dict[str, Any],
        *,
        format: str = "json",
        citation: str | None = None,
        csl_cone_id: str | None = None,
        size: int | None = None,
        from_: int | None = None,
        sort: list[dict[str, Any]] | None = None,
    ) -> bytes:
        """POST /items/search with a non-JSON ``format`` — bulk export."""
        body = _search_body(query, size=size, from_=from_, sort=sort)
        response = self._transport.request(
            "POST",
            "/items/search",
            params={"format": format, "citation": citation, "cslConeId": csl_cone_id},
            json=body,
        )
        return response.content

    # -- write operations --------------------------------------------------

    def create(self, item: Item) -> Item:
        """POST /items — create a new item (status ``PENDING``).

        The item dict must include ``context.objectId`` and ``metadata``.
        Requires authentication.
        """
        result: Item = self._transport.request_json("POST", "/items", json=item, authenticated=True)
        return result

    def update(self, item_id: str, item: Item) -> Item:
        """PUT /items/{itemId} — update an item, creating a new version.

        Fetch the current item first and modify it; the server validates
        ``lastModificationDate`` for optimistic locking. Requires
        authentication.
        """
        result: Item = self._transport.request_json(
            "PUT", f"/items/{item_id}", json=item, authenticated=True
        )
        return result

    def delete(self, item_id: str, last_modification_date: str) -> None:
        """DELETE /items/{itemId} — erase an item (only while ``PENDING``)."""
        self._transport.request(
            "DELETE",
            f"/items/{item_id}",
            json={"lastModificationDate": last_modification_date},
            authenticated=True,
        )

    # -- lifecycle ---------------------------------------------------------

    def _task(
        self, action: str, item_id: str, last_modification_date: str, comment: str | None
    ) -> Item:
        body: dict[str, Any] = {"lastModificationDate": last_modification_date}
        if comment is not None:
            body["comment"] = comment
        result: Item = self._transport.request_json(
            "PUT", f"/items/{item_id}/{action}", json=body, authenticated=True
        )
        return result

    def submit(self, item_id: str, last_modification_date: str, comment: str | None = None) -> Item:
        """PUT /items/{itemId}/submit — set status to ``SUBMITTED``.

        Only possible in contexts with the standard workflow.
        """
        return self._task("submit", item_id, last_modification_date, comment)

    def release(
        self, item_id: str, last_modification_date: str, comment: str | None = None
    ) -> Item:
        """PUT /items/{itemId}/release — release a pending/submitted item.

        Once released, an item can no longer be deleted, only withdrawn.
        """
        return self._task("release", item_id, last_modification_date, comment)

    def withdraw(self, item_id: str, last_modification_date: str, comment: str) -> Item:
        """PUT /items/{itemId}/withdraw — discard a released item.

        Cannot be undone; a comment is mandatory.
        """
        return self._task("withdraw", item_id, last_modification_date, comment)

    def revise(self, item_id: str, last_modification_date: str, comment: str | None = None) -> Item:
        """PUT /items/{itemId}/revise — send a submitted item back to ``PENDING``."""
        return self._task("revise", item_id, last_modification_date, comment)

    # -- components (files) -------------------------------------------------

    def component_metadata(self, item_id: str, component_id: str) -> dict[str, Any]:
        """GET /items/{itemId}/component/{componentId}/metadata — file metadata."""
        result: dict[str, Any] = self._transport.request_json(
            "GET", f"/items/{item_id}/component/{component_id}/metadata"
        )
        return result

    def component_content(self, item_id: str, component_id: str) -> bytes:
        """GET /items/{itemId}/component/{componentId}/content — file bytes."""
        response = self._transport.request(
            "GET", f"/items/{item_id}/component/{component_id}/content"
        )
        return response.content

    def download_component(
        self,
        item_id: str,
        component_id: str,
        target: str | os.PathLike[str] | IO[bytes] | BinaryIO,
        *,
        chunk_size: int = 64 * 1024,
    ) -> int:
        """Stream a file component to *target* (path or binary file object).

        Returns the number of bytes written.
        """
        response = self._transport.request(
            "GET",
            f"/items/{item_id}/component/{component_id}/content",
            params={"download": "true"},
            stream=True,
        )
        written = 0
        if isinstance(target, (str, os.PathLike)):
            with open(target, "wb") as fh:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    fh.write(chunk)
                    written += len(chunk)
        else:
            for chunk in response.iter_content(chunk_size=chunk_size):
                target.write(chunk)
                written += len(chunk)
        return written
