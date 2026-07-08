"""Runtime configuration for the sync + web service, read from the environment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from pybman import queries


@dataclass
class Config:
    base_url: str | None
    db_path: str
    port: int
    interval_hours: float
    query: dict[str, Any]
    dereference_authorities: bool

    @classmethod
    def from_env(cls) -> Config:
        raw_query = os.environ.get("SYNC_QUERY")
        ctx_id = os.environ.get("SYNC_CONTEXT_ID")
        ou_id = os.environ.get("SYNC_OU_ID")
        if raw_query:
            query = json.loads(raw_query)
        elif ctx_id:
            query = queries.by_context(ctx_id)
        elif ou_id:
            query = queries.by_organization(ou_id)
        else:
            query = queries.match_all()
        return cls(
            base_url=os.environ.get("PUBMAN_BASE_URL"),
            db_path=os.environ.get("DB_PATH", "/data/pubman.db"),
            port=int(os.environ.get("PORT", "8000")),
            interval_hours=float(os.environ.get("REFRESH_INTERVAL_HOURS", "24")),
            query=query,
            dereference_authorities=os.environ.get("DEREFERENCE_AUTHORITIES", "0").lower()
            in {"1", "true", "yes", "on"},
        )
