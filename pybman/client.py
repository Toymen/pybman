"""High-level client for MPG.PuRe / PubMan."""

from __future__ import annotations

import json
import logging
import os
import warnings
from types import TracebackType
from typing import Any

import requests

from pybman import queries
from pybman._http import DEFAULT_BASE_URL, Transport
from pybman.api import ConeAPI, ContextsAPI, FeedsAPI, ItemsAPI, OrgUnitsAPI, StagingAPI
from pybman.data import DataSet
from pybman.models import Item, UserAccount

logger = logging.getLogger(__name__)

#: Environment variables consulted when no explicit credentials are given.
ENV_USERNAME = "PUBMAN_USERNAME"
ENV_PASSWORD = "PUBMAN_PASSWORD"
ENV_TOKEN = "PUBMAN_TOKEN"
ENV_BASE_URL = "PUBMAN_BASE_URL"


def _read_credentials_file(path: str | os.PathLike[str]) -> tuple[str, str]:
    """Read credentials from a JSON file.

    Two layouts are accepted::

        {"username": "...", "password": "..."}
        {"user-pass": "username:password"}      # legacy pybman format
    """
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if "username" in data and "password" in data:
        return str(data["username"]), str(data["password"])
    if "user-pass" in data:
        user, _, secret = str(data["user-pass"]).partition(":")
        if user and secret:
            return user, secret
    raise ValueError(
        f"{os.fspath(path)!r} does not contain credentials in a supported layout "
        '(expected {"username": ..., "password": ...} or {"user-pass": "user:pass"})'
    )


class Client:
    """Entry point for talking to a PubMan instance.

    The API is exposed through resource groups::

        client = Client()                         # anonymous, read-only
        client.items.get("item_3015660")
        client.items.search(queries.by_context("ctx_924547"))
        client.ous.toplevel()
        client.contexts.get("ctx_924547")
        client.feeds.recent()
        client.cone.person("persons32341")

    Write operations need credentials. Provide them explicitly, via the
    ``PUBMAN_USERNAME`` / ``PUBMAN_PASSWORD`` environment variables, or via a
    JSON credentials file — login then happens automatically on the first
    call that needs it::

        with Client(username="...", password="...") as client:
            client.items.update(item_id, item)
            client.items.release(item_id, item["lastModificationDate"], "fixed typo")

    Args:
        base_url: Root URL of the PubMan instance. Defaults to
            ``https://pure.mpg.de`` (overridable via ``PUBMAN_BASE_URL``).
        username: Login name for authenticated operations.
        password: Password matching *username*.
        token: Existing authorization token (skips login; valid 24 h).
        credentials_file: Path to a JSON file holding credentials.
        secret: Deprecated alias for ``credentials_file``.
        timeout: Per-request timeout in seconds.
        retries: Automatic retries for idempotent requests.
        session: Optional pre-configured :class:`requests.Session`.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        credentials_file: str | os.PathLike[str] | None = None,
        secret: str | os.PathLike[str] | None = None,
        timeout: float = 30.0,
        retries: int = 3,
        session: requests.Session | None = None,
    ) -> None:
        if secret:
            warnings.warn(
                "the 'secret' argument is deprecated, use 'credentials_file' "
                "(or username/password, or PUBMAN_USERNAME/PUBMAN_PASSWORD)",
                DeprecationWarning,
                stacklevel=2,
            )
            credentials_file = credentials_file or secret

        credentials: tuple[str, str] | None = None
        if username is not None and password is not None:
            credentials = (username, password)
        elif credentials_file:
            credentials = _read_credentials_file(credentials_file)
        elif os.environ.get(ENV_USERNAME) and os.environ.get(ENV_PASSWORD):
            credentials = (os.environ[ENV_USERNAME], os.environ[ENV_PASSWORD])

        if token is None:
            token = os.environ.get(ENV_TOKEN) or None
        if base_url is None:
            base_url = os.environ.get(ENV_BASE_URL) or DEFAULT_BASE_URL

        self.transport = Transport(
            base_url,
            credentials=credentials,
            token=token,
            timeout=timeout,
            retries=retries,
            session=session,
        )

        self.items = ItemsAPI(self.transport)
        self.ous = OrgUnitsAPI(self.transport)
        self.contexts = ContextsAPI(self.transport)
        self.feeds = FeedsAPI(self.transport)
        self.staging = StagingAPI(self.transport)
        self.cone = ConeAPI(self.transport)

    # -- session handling --------------------------------------------------

    @property
    def base_url(self) -> str:
        return self.transport.base_url

    @property
    def is_authenticated(self) -> bool:
        """Whether the client currently holds an authorization token."""
        return self.transport.is_authenticated

    def login(self, username: str | None = None, password: str | None = None) -> str:
        """Authenticate and return the authorization token (valid 24 h)."""
        return self.transport.login(username, password)

    def logout(self) -> None:
        """Invalidate the current token (best effort, never raises)."""
        self.transport.logout()

    def whoami(self) -> UserAccount:
        """Account information of the logged-in user (``GET /login/who``)."""
        return self.transport.whoami()

    def close(self) -> None:
        """Log out (if logged in) and release HTTP resources."""
        self.logout()
        self.transport.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        auth = "authenticated" if self.is_authenticated else "anonymous"
        return f"<pybman.Client {self.base_url} ({auth})>"

    # -- convenience -----------------------------------------------------

    def update_and_release(self, item_id: str, item: Item, comment: str | None = None) -> Item:
        """Update an item and release the new version in one step.

        Returns the released item. Requires authentication and, for the
        release step, appropriate (moderator) rights in the item's context.
        """
        updated = self.items.update(item_id, item)
        return self.items.release(item_id, updated["lastModificationDate"], comment)

    # -- legacy convenience API (pybman <= 2019.x) ----------------------------

    def get_data(
        self,
        ctx_id: str | None = None,
        ou_id: str | None = None,
        pers_id: str | None = None,
        lang_id: str | None = None,
        jour_name: str | None = None,
        misc_query: dict[str, Any] | None = None,
        *,
        released_only: bool = False,
        max_records: int | None = None,
    ) -> DataSet:
        """Fetch all items for a context, OU, person, language or journal.

        Exactly one selector must be given. Scrolls through the full result
        set (bounded by ``max_records`` if provided) and wraps it in a
        :class:`~pybman.data.DataSet`, mirroring the classic pybman API.
        """
        selectors: list[tuple[str, dict[str, Any]]] = []
        if ctx_id:
            selectors.append((ctx_id, queries.by_context(ctx_id, released_only=released_only)))
        if ou_id:
            selectors.append((ou_id, queries.by_organization(ou_id, released_only=released_only)))
        if pers_id:
            selectors.append((pers_id, queries.by_person(pers_id, released_only=released_only)))
        if lang_id:
            selectors.append((lang_id, queries.by_language(lang_id, released_only=released_only)))
        if jour_name:
            selectors.append(
                (jour_name, queries.by_journal(jour_name, released_only=released_only))
            )
        if misc_query:
            selectors.append(("query_data", misc_query))
        if len(selectors) != 1:
            raise ValueError(
                "pass exactly one of ctx_id, ou_id, pers_id, lang_id, jour_name or misc_query"
            )
        data_id, query = selectors[0]
        records = self.items.search_all(query, max_records=max_records)
        return DataSet(data_id, raw=records)

    def update_data(self, idx: str, item_data: Item, comment: str | None = None) -> Item:
        """Deprecated alias for :meth:`update_and_release`."""
        warnings.warn(
            "Client.update_data() is deprecated, use Client.update_and_release()",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.update_and_release(idx, item_data, comment)
