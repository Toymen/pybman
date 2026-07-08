# pybman

[![CI](https://github.com/Toymen/pybman/actions/workflows/ci.yml/badge.svg)](https://github.com/Toymen/pybman/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](COPYING)

Python client for [MPG.PuRe](https://pure.mpg.de), the publication repository
of the Max Planck Society, via the
[PubMan REST API](https://pure.mpg.de/rest/swagger-ui/index.html).

- **Read** publication items, collections (contexts), organizational units,
  feeds and the CoNE authority vocabularies — anonymously.
- **Search** with the full Elasticsearch query DSL, with transparent
  scrolling for large result sets.
- **Write** (create, update, submit, release, withdraw, delete items and
  upload files) with a PuRe account.
- Typed, tested, and based on a single small dependency (`requests`).

## Installation

```bash
pip install pybman
```

Requires Python ≥ 3.10.

## Quick start

```python
from pybman import Client
from pybman import queries

client = Client()  # anonymous, read-only, against https://pure.mpg.de

# one publication item
item = client.items.get("item_3015660")
print(item["metadata"]["title"])

# search: builders for common queries ...
result = client.items.search(queries.by_context("ctx_924547"), size=10)
print(result.number_of_records)

# ... or any raw Elasticsearch query
result = client.items.search(
    {"match": {"metadata.title": "photonic crystal"}},
    size=5,
    sort=[{"metadata.datePublishedInPrint": {"order": "desc"}}],
)
for record in result:
    print(record["data"]["metadata"]["title"])
```

### Scrolling through large result sets

One search request returns at most 5000 items. `search_iter` /
`search_all` page through everything via the scroll API:

```python
for record in client.items.search_iter(queries.by_organization("ou_907574")):
    ...  # lazily fetched, 100 records per request

records = client.items.search_all(queries.by_journal("Nature"), max_records=500)
count = client.items.count(queries.by_language("deu"))
```

### Exports, files, feeds, organizational units

```python
bibtex = client.items.export("item_3015660", format="BibTex")
apa = client.items.export("item_3015660", format="html_plain", citation="APA")

meta = client.items.component_metadata("item_3015660", "file_3015661")
client.items.download_component("item_3015660", "file_3015661", "paper.pdf")

roots = client.ous.toplevel()
children = client.ous.children("ou_907574")
collection = client.contexts.get("ctx_924547")
atom = client.feeds.recent()
```

### CoNE authority service (persons, journals, languages)

```python
person = client.cone.person("persons32341")
hits = client.cone.query_persons("Lovelace", limit=5)
languages = client.cone.languages()
```

## Authentication and write operations

Write operations require a PuRe account. Credentials can come from
arguments, the environment (`PUBMAN_USERNAME` / `PUBMAN_PASSWORD`), or a JSON
file (`{"username": ..., "password": ...}`; the legacy
`{"user-pass": "user:pass"}` layout is still accepted). Login happens
lazily on the first call that needs it; tokens are valid for 24 hours and
are refreshed automatically once when they expire mid-session.

**Never commit credentials.** Prefer environment variables, or keep the
credentials file outside the repository.

```python
from pybman import Client

with Client(username="...", password="...") as client:   # logs out on exit
    me = client.whoami()
    print(me.login_name, me.roles)

    # update an item: fetch, modify, put, release
    item = client.items.get("item_3015660")
    item["metadata"]["title"] = item["metadata"]["title"].strip()
    updated = client.items.update("item_3015660", item)
    client.items.release("item_3015660", updated["lastModificationDate"],
                         "remove whitespace")

    # or in one step
    client.update_and_release("item_3015660", item, "remove whitespace")
```

Creating an item with an attached file:

```python
staged_id = client.staging.upload("paper.pdf")  # must be staged first
item = client.items.create({
    "context": {"objectId": "ctx_924547"},
    "metadata": {"title": "A new paper", "genre": "ARTICLE",
                 "creators": [...]},
    "files": [{
        "visibility": "PUBLIC",
        "storage": "INTERNAL_MANAGED",
        "content": staged_id,
        "metadata": {"title": "paper.pdf", "contentCategory": "publisher-version"},
    }],
})
client.items.submit(item["objectId"], item["lastModificationDate"], "please review")
```

Other instances of PubMan (e.g. the QA system) work via
`Client("https://qa.pure.mpdl.mpg.de")` or the `PUBMAN_BASE_URL`
environment variable.

## Error handling

All HTTP failures raise typed exceptions from `pybman.exceptions`, each
carrying the `requests` response:

```python
from pybman import Client, NotFoundError, AuthenticationError, PubManError

client = Client()
try:
    client.items.get("item_does_not_exist")
except NotFoundError:
    ...
except PubManError as exc:   # base class of everything pybman raises
    print(exc)
```

## Working with result sets

The classic `DataSet` / `extract` / `Inspector` helpers for analysing and
cleaning record collections are still available:

```python
from pybman import Client, Inspector

client = Client()
dataset = client.get_data(ctx_id="ctx_924547")   # scrolls everything
genres = dataset.get_genres()
years = dataset.get_years()

# batch cleanup (requires an authenticated client)
inspector = Inspector(client, dataset.get_items_released())
inspector.clean_titles()
```

## Sync + web service (Docker)

`webapp/` is a small companion app built on top of the client: it fetches
every publication matching a query (default: everything), stores the raw JSON
plus a flattened index of every nested scalar value in a local SQLite
database, and serves a filterable table with Excel export. It refreshes every
24 hours (configurable) or on demand via a "Refresh now" button; the first
fetch runs immediately on startup. CoNE person and organizational-unit
dereferencing is optional because an unrestricted PubMan sync is very large.

```bash
docker compose up --build
```

Then open <http://localhost:8000>. Data persists in the `pubman-data`
volume. Configuration is via environment variables (see
`docker-compose.yml`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `PUBMAN_BASE_URL` | `https://pure.mpg.de` | PubMan instance to sync from |
| `SYNC_CONTEXT_ID` / `SYNC_OU_ID` / `SYNC_QUERY` | unset (= every item) | narrow the sync scope |
| `REFRESH_INTERVAL_HOURS` | `24` | time between automatic refreshes |
| `DEREFERENCE_AUTHORITIES` | `0` | also fetch full CoNE person / OU authority records |
| `DB_PATH` | `/data/pubman.db` | SQLite file location |

Without Docker: `pip install -e ".[web]"` then `python -m webapp.app`.

## Development

```bash
git clone https://github.com/Toymen/pybman.git
cd pybman
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

pytest                      # unit tests (offline, mocked HTTP)
PYBMAN_LIVE_TESTS=1 pytest -m live   # optional read-only tests against pure.mpg.de
ruff check . && ruff format --check .
mypy
```

## Migration from pybman ≤ 2019.x

See [MIGRATION.md](MIGRATION.md). The high-level `Client`, `DataSet`,
`Inspector`, `LocalData` and `extract` APIs are preserved; the low-level
`pybman.rest` controllers were replaced by `client.items`, `client.ous`,
`client.contexts`, `client.feeds`, `client.staging` and `client.cone`.

## Links

- PubMan REST API documentation: <https://colab.mpdl.mpg.de/mediawiki/PubMan_REST_API_Documentation>
- Swagger UI / OpenAPI spec: <https://pure.mpg.de/rest/swagger-ui/index.html>
- Upstream project: <https://github.com/herreio/pybman>

## License

GPL-3.0-or-later, see [COPYING](COPYING). Originally written by
Donatus Herre.
