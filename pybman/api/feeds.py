"""Atom feed endpoints (``/feed``). All return feed XML as text."""

from __future__ import annotations

from pybman._http import Transport


class FeedsAPI:
    """Atom feeds of recently released items."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def _get(self, path: str, **params: str) -> str:
        response = self._transport.request(
            "GET", path, params=dict(params), headers={"Accept": "application/atom+xml, */*"}
        )
        return response.text

    def recent(self) -> str:
        """GET /feed/recent — recently released items."""
        return self._get("/feed/recent")

    def open_access(self) -> str:
        """GET /feed/oa — recently released open-access items."""
        return self._get("/feed/oa")

    def organization(self, ou_id: str) -> str:
        """GET /feed/organization/{ouId} — recent releases of one organization."""
        return self._get(f"/feed/organization/{ou_id}")

    def search(self, q: str) -> str:
        """GET /feed/search — a search result as a feed."""
        return self._get("/feed/search", q=q)
