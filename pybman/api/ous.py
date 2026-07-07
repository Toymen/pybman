"""Organizational unit endpoints (``/ous``)."""

from __future__ import annotations

from typing import Any

from pybman._http import Transport
from pybman.models import SearchResult


class OrgUnitsAPI:
    """Organizational units (institutes, departments, groups)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def get(self, ou_id: str) -> dict[str, Any]:
        """GET /ous/{ouId} — one organizational unit."""
        result: dict[str, Any] = self._transport.request_json("GET", f"/ous/{ou_id}")
        return result

    def all(self, *, size: int | None = None, from_: int | None = None) -> SearchResult:
        """GET /ous — list organizational units.

        Without ``size`` the full list is fetched (two requests: one to
        learn the total, one to retrieve everything).
        """
        if size is None:
            probe = self._transport.request_json("GET", "/ous", params={"size": 1})
            size = int(probe.get("numberOfRecords", 0))
        payload = self._transport.request_json("GET", "/ous", params={"size": size, "from": from_})
        return SearchResult.from_api(payload)

    def toplevel(self) -> list[dict[str, Any]]:
        """GET /ous/toplevel — root organizational units."""
        result: list[dict[str, Any]] = self._transport.request_json("GET", "/ous/toplevel")
        return result

    def firstlevel(self) -> list[dict[str, Any]]:
        """GET /ous/firstlevel — first-level organizational units."""
        result: list[dict[str, Any]] = self._transport.request_json("GET", "/ous/firstlevel")
        return result

    def children(self, ou_id: str) -> list[dict[str, Any]]:
        """GET /ous/{ouId}/children — direct child units."""
        result: list[dict[str, Any]] = self._transport.request_json("GET", f"/ous/{ou_id}/children")
        return result

    def all_children(self, ou_id: str) -> list[dict[str, Any]]:
        """POST /ous/allchildren/{ouId} — all transitive child units."""
        result: list[dict[str, Any]] = self._transport.request_json(
            "POST", f"/ous/allchildren/{ou_id}"
        )
        return result

    def parents(self, ou_id: str) -> list[dict[str, Any]]:
        """GET /ous/{ouId}/parents — parent units up to the root."""
        result: list[dict[str, Any]] = self._transport.request_json("GET", f"/ous/{ou_id}/parents")
        return result

    def id_path(self, ou_id: str) -> list[str]:
        """GET /ous/{ouId}/idPath — ids from the unit up to the root."""
        result: list[str] = self._transport.request_json("GET", f"/ous/{ou_id}/idPath")
        return result

    def search(
        self,
        query: dict[str, Any],
        *,
        size: int | None = 10,
        from_: int | None = 0,
    ) -> SearchResult:
        """POST /ous/search — Elasticsearch query over organizational units."""
        body: dict[str, Any] = dict(query) if "query" in query else {"query": query}
        if size is not None:
            body.setdefault("size", size)
        if from_ is not None:
            body.setdefault("from", from_)
        payload = self._transport.request_json("POST", "/ous/search", json=body)
        return SearchResult.from_api(payload)
