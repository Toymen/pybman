"""Context (collection) endpoints (``/contexts``)."""

from __future__ import annotations

from typing import Any

from pybman._http import Transport
from pybman.models import SearchResult


class ContextsAPI:
    """Contexts — the collections publication items belong to."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def get(self, ctx_id: str) -> dict[str, Any]:
        """GET /contexts/{ctxId} — one context."""
        result: dict[str, Any] = self._transport.request_json("GET", f"/contexts/{ctx_id}")
        return result

    def all(self, *, size: int | None = None, from_: int | None = None) -> SearchResult:
        """GET /contexts — list contexts (fetches everything when size is None)."""
        if size is None:
            probe = self._transport.request_json("GET", "/contexts", params={"size": 1})
            size = int(probe.get("numberOfRecords", 0))
        payload = self._transport.request_json(
            "GET", "/contexts", params={"size": size, "from": from_}
        )
        return SearchResult.from_api(payload)

    def search(
        self,
        query: dict[str, Any],
        *,
        size: int | None = 10,
        from_: int | None = 0,
    ) -> SearchResult:
        """POST /contexts/search — Elasticsearch query over contexts."""
        body: dict[str, Any] = dict(query) if "query" in query else {"query": query}
        if size is not None:
            body.setdefault("size", size)
        if from_ is not None:
            body.setdefault("from", from_)
        payload = self._transport.request_json("POST", "/contexts/search", json=body)
        return SearchResult.from_api(payload)
