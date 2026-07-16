"""Runtime configuration for the sync + web service, read from the environment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from pybman import queries


class ConfigError(ValueError):
    """Raised when an environment variable holds an invalid value."""


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
            try:
                query = json.loads(raw_query)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"SYNC_QUERY is not valid JSON: {exc}") from exc
        elif ctx_id:
            query = queries.by_context(ctx_id)
        elif ou_id:
            query = queries.by_organization(ou_id)
        else:
            query = queries.match_all()

        raw_port = os.environ.get("PORT", "8000")
        try:
            port = int(raw_port)
        except ValueError as exc:
            raise ConfigError(f"PORT must be an integer, got {raw_port!r}") from exc

        raw_interval = os.environ.get("REFRESH_INTERVAL_HOURS", "24")
        try:
            interval_hours = float(raw_interval)
        except ValueError as exc:
            raise ConfigError(
                f"REFRESH_INTERVAL_HOURS must be a number, got {raw_interval!r}"
            ) from exc

        return cls(
            base_url=os.environ.get("PUBMAN_BASE_URL"),
            db_path=os.environ.get("DB_PATH", "/data/pubman.db"),
            port=port,
            interval_hours=interval_hours,
            query=query,
            dereference_authorities=os.environ.get("DEREFERENCE_AUTHORITIES", "0").lower()
            in {"1", "true", "yes", "on"},
        )
