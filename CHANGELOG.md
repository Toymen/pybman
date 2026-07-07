# Changelog

## 2026.7.0 (unreleased)

Modernization release. See [MIGRATION.md](MIGRATION.md) for upgrade notes.

### Added

- Resource-oriented client API: `client.items`, `client.ous`,
  `client.contexts`, `client.feeds`, `client.staging`, `client.cone`.
- Full item lifecycle: `create`, `update`, `delete`, `submit`, `release`,
  `withdraw`, `revise` (per the current REST API's `TaskParamVO` body).
- Item and search-result export (`BibTex`, `EndNote`, `Marc_Xml`, `pdf`,
  `docx`, citation styles, ...).
- File handling: staging upload (`client.staging.upload`), component
  metadata, content retrieval and streaming download.
- Transparent scroll pagination: `items.search_iter` / `search_all` /
  `count`.
- Implemented Atom feeds (`recent`, `oa`, `organization`, `search`) —
  previously stubs.
- Extended organizational-unit coverage: `firstlevel`, `all_children`,
  `parents`, `id_path`, `search`; context search.
- `pybman.queries`: programmatic Elasticsearch query builders (including
  `by_identifier` for DOI lookups and released-only filters).
- Typed exceptions (`pybman.exceptions`) mapped from HTTP status codes.
- `SearchResult` / `UserAccount` models and controlled-vocabulary enums
  from the live OpenAPI specification; `py.typed` marker.
- Credentials via environment variables (`PUBMAN_USERNAME`,
  `PUBMAN_PASSWORD`, `PUBMAN_TOKEN`, `PUBMAN_BASE_URL`) and modern
  credentials files; context-manager sessions with automatic logout;
  automatic re-login when the 24 h token expires.
- Request timeouts and bounded retries for idempotent requests.
- Unit test suite (mocked HTTP) and optional live tests
  (`PYBMAN_LIVE_TESTS=1 pytest -m live`).
- CI (GitHub Actions): ruff, mypy, pytest on Python 3.10–3.14, package
  build.
- PEP 621 packaging (`pyproject.toml`), ruff + mypy (strict)
  configuration.

### Changed

- Requires Python ≥ 3.10 and `requests` ≥ 2.28; `tqdm` dropped.
- Errors raise exceptions instead of printing; diagnostics use `logging`.
- Login is lazy; the `atexit` logout hook was removed.
- Item release no longer re-transmits the account password.
- `Client.update_data` is a deprecated alias of
  `Client.update_and_release`.
- `pybman.query` classes are deprecated wrappers around `pybman.queries`.

### Removed

- `pybman.rest` controllers (replaced by the resource APIs).
- HTTP helpers and dead code in `pybman.utils`; `pkg_resources` usage.
- Static Elasticsearch JSON templates (replaced by `pybman.queries`).
- The tracked `conf/secret.json` credentials placeholder.

### Fixed

- `extract.field_from_pubinfo` returned `None` instead of `""`.
- `LocalData.generate_data_path` produced broken paths (missing
  separator).
- Scroll pagination no longer recurses (no recursion-limit crashes on
  large result sets) and follows changing scroll ids.

## 2019.10.1

Last upstream release (https://github.com/herreio/pybman).
