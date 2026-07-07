# Migrating from pybman ≤ 2019.10 to 2026.x

The 2026 release modernizes pybman for the current PubMan REST API and
current Python. The high-level API is preserved where practical; the
low-level plumbing was rebuilt.

## What keeps working

- `from pybman import Client, DataSet, Inspector, LocalData` and
  `from pybman import extract, utils`.
- `Client(secret="path/to/secret.json")` — still accepted (with a
  `DeprecationWarning`); the legacy `{"user-pass": "user:pass"}` file layout
  is still understood. Prefer `credentials_file=`, `username=`/`password=`,
  or the `PUBMAN_USERNAME`/`PUBMAN_PASSWORD` environment variables.
- `Client.get_data(ctx_id=..., ou_id=..., pers_id=..., lang_id=...,
  jour_name=..., misc_query=...)` returns a `DataSet` as before.
- `Client.update_data(idx, data, comment)` — deprecated alias of
  `Client.update_and_release(...)`.
- All `DataSet` grouping/selection methods, the `extract` helpers, the
  `Inspector` checks/cleanups and `LocalData`.
- The query template classes in `pybman.query` (deprecated wrappers around
  the new `pybman.queries` builder functions).

## What changed

| Old | New |
| --- | --- |
| `pybman.rest.ItemRestController` | `client.items` (`get`, `search`, `search_iter`, `scroll`, `create`, `update`, `delete`, `submit`, `release`, `withdraw`, `revise`, `export`, `component_metadata`, `component_content`, `download_component`) |
| `ItemRestController.search_items(query)` + `.records` | `client.items.search_all(query)` (or `search`/`search_iter`) |
| `ItemRestController.count_items(query)` | `client.items.count(query)` |
| `pybman.rest.OrgUnitRestController` | `client.ous` (`get`, `all`, `toplevel`, `firstlevel`, `children`, `all_children`, `parents`, `id_path`, `search`) |
| `pybman.rest.ContextRestController` | `client.contexts` (`get`, `all`, `search`) |
| `pybman.rest.FeedRestController` (stubs) | `client.feeds` (`recent`, `open_access`, `organization`, `search`) — implemented |
| `pybman.rest.PersonConeController` etc. | `client.cone` (`persons`, `person`, `query_persons`, `journals`, `languages`, ...) |
| — (no upload support) | `client.staging.upload(...)` |
| `utils.get_request` / `post_request` / `put_request` | removed — use `client.transport.request(...)` for endpoints pybman does not wrap |
| `utils.check_url`, `utils.url_exists2`, `utils.resolve_path` | removed (`utils.url_exists` remains) |
| static JSON query templates (`pybman/static/elastic/*.json`) | `pybman.queries` builder functions |
| `conf/secret.json` in the repository | removed — never store credentials in a repository |

## Behavioural changes

- **Errors raise exceptions.** Failed requests raise subclasses of
  `pybman.PubManError` (`NotFoundError`, `AuthenticationError`,
  `AuthorizationError`, `BadRequestError`, `ServerError`) instead of
  printing a message and returning `{}` / `None`.
- **Nothing prints to stdout.** Diagnostics go to the `pybman.*` loggers.
- **Login is lazy.** `Client(...)` no longer logs in during construction;
  the first authenticated call does. `client.login()` forces it. The old
  `atexit` logout hook is gone — use the client as a context manager
  (`with Client(...) as client:`) or call `client.logout()` / `close()`.
- **Release without password.** Item release no longer re-sends your
  password; the current API only needs `lastModificationDate` and an
  optional comment.
- **`Client.get_data` raises `ValueError`** when not exactly one selector
  is passed (it used to print and return `None`).
- **`Inspector` methods raise on bad arguments** instead of printing, and
  push updates through `Client.update_and_release`.
- **Python ≥ 3.10 and `requests` ≥ 2.28** are required; the `tqdm`
  dependency (progress bars) was dropped.

## Version scheme

Versions continue the calendar scheme (`2026.7.0`), so upgrades sort
correctly after `2019.10.1`.
