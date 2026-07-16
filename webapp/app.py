"""Web UI over the synced publications: browse, filter, export to Excel,
trigger a refresh. Run with ``python -m webapp.app``."""

from __future__ import annotations

import io
import json
import logging
import threading
import time
from urllib.parse import urlencode

from flask import Flask, redirect, render_template, request, send_file, url_for
from openpyxl import Workbook

from pybman import Client
from webapp import store, sync
from webapp.config import Config

logger = logging.getLogger(__name__)

#: (column, display label) pairs, in table/export order.
COLUMNS = (
    ("object_id", "ID"),
    ("title", "Title"),
    ("genre", "Genre"),
    ("year", "Year"),
    ("creators", "Creators"),
    ("creator_cone_ids", "Creator CoNE IDs"),
    ("creator_cone_bindings", "Creator <-> CoNE"),
    ("local_tags", "Local Tags"),
    ("prime_tag", "Prime / Target Journal"),
    ("research_group_tags", "Group Tags"),
    ("research_data_flag", "Research Data?"),
    ("research_data_links", "Research Data Links"),
    ("research_data_details", "Research Data Evidence"),
    ("source_title", "Journal / Source"),
    ("publisher", "Publisher"),
    ("language", "Language"),
    ("doi", "DOI"),
    ("context_id", "Context"),
    ("public_state", "State"),
    ("date_modified", "Modified"),
)


def _filters_from_request() -> dict[str, str]:
    return {col: request.args.get(col, "") for col in store.FILTERABLE_COLUMNS}


def _cone_id_from_request() -> str:
    return request.args.get("cone_id", "").strip()


def _tag_from_request(name: str) -> str:
    return request.args.get(name, "").strip()


def _field_filters_from_request() -> list[tuple[str, str]]:
    paths = request.args.getlist("field_path")
    values = request.args.getlist("field_value")
    return [(path, value) for path, value in zip(paths, values, strict=False) if path and value]


def _columns_from_request() -> tuple[tuple[str, str], ...]:
    requested = request.args.getlist("columns")
    if not requested:
        return COLUMNS
    labels = dict(COLUMNS)
    selected = tuple((column, labels[column]) for column in requested if column in labels)
    return selected or COLUMNS


def _sort_from_request() -> tuple[str, str]:
    sort_by = request.args.get("sort", "date_modified")
    if sort_by not in store.SORTABLE_COLUMNS:
        sort_by = "date_modified"
    sort_dir = request.args.get("dir", "desc").lower()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    return sort_by, sort_dir


def _url_with_args(endpoint: str, **updates: object) -> str:
    args = request.args.to_dict(flat=False)
    for key, value in updates.items():
        if value is None:
            args.pop(key, None)
        elif isinstance(value, list):
            args[key] = [str(v) for v in value]
        else:
            args[key] = [str(value)]
    query = urlencode(args, doseq=True)
    url = url_for(endpoint)
    return f"{url}?{query}" if query else url


def _with_selected_option(options: list[str], selected: str) -> list[str]:
    if selected and selected not in options:
        return [selected, *options]
    return options


def _sort_url(column: str, current_sort: str, current_dir: str) -> str:
    next_dir = "desc" if column == current_sort and current_dir == "asc" else "asc"
    return _url_with_args("index", sort=column, dir=next_dir, page=1)


def sync_now(client: Client, cfg: Config, app: Flask) -> None:
    """Run one sync pass, tracking progress via ``app.config['SYNC_LOCK']``.

    Safe to call from any thread; a no-op while a sync is already running.
    """
    lock: threading.Lock = app.config["SYNC_LOCK"]
    if not lock.acquire(blocking=False):
        return
    app.config["SYNCING"] = True
    try:
        sync.run(
            client,
            cfg.query,
            cfg.db_path,
            dereference_authorities=cfg.dereference_authorities,
        )
    except Exception:
        logger.exception("sync failed")
    finally:
        app.config["SYNCING"] = False
        lock.release()


def create_app(client: Client, cfg: Config) -> Flask:
    app = Flask(__name__)
    app.config["SYNCING"] = False
    app.config["SYNC_LOCK"] = threading.Lock()

    @app.get("/")
    def index():
        filters = _filters_from_request()
        cone_id = _cone_id_from_request()
        local_tag = _tag_from_request("local_tag")
        group_tag = _tag_from_request("group_tag")
        field_filters = _field_filters_from_request()
        visible_columns = _columns_from_request()
        sort_by, sort_dir = _sort_from_request()
        q = request.args.get("q", "")
        try:
            page = max(int(request.args.get("page", 1) or 1), 1)
        except ValueError:
            page = 1
        page_size = 50
        with store.connect(cfg.db_path) as conn:
            rows, total = store.query_items(
                conn,
                filters,
                q,
                field_filters=field_filters,
                cone_id=cone_id,
                local_tag=local_tag,
                group_tag=group_tag,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=page_size,
                offset=(page - 1) * page_size,
            )
            options = {col: store.distinct_values(conn, col) for col in store.FILTERABLE_COLUMNS}
            local_tag_options = _with_selected_option(store.local_tag_values(conn), local_tag)
            group_tag_options = _with_selected_option(
                store.local_tag_values(conn, include_prime=False), group_tag
            )
            field_paths = store.field_paths(conn)
            last_synced = store.get_meta(conn, "last_synced_at", "never")
            item_count = store.item_count(conn)
            field_count = int(
                conn.execute("SELECT COUNT(DISTINCT path) AS n FROM item_fields").fetchone()["n"]
            )

        return render_template(
            "index.html",
            rows=rows,
            columns=visible_columns,
            all_columns=COLUMNS,
            selected_column_ids={column for column, _label in visible_columns},
            filters=filters,
            cone_id=cone_id,
            local_tag=local_tag,
            group_tag=group_tag,
            local_tag_options=local_tag_options,
            group_tag_options=group_tag_options,
            field_filters=field_filters,
            field_paths=field_paths,
            q=q,
            options=options,
            total=total,
            item_count=item_count,
            field_count=field_count,
            page=page,
            page_size=page_size,
            pages=max((total + page_size - 1) // page_size, 1),
            page_url=lambda target: _url_with_args("index", page=target),
            sort_url=lambda column: _sort_url(column, sort_by, sort_dir),
            sort_by=sort_by,
            sort_dir=sort_dir,
            export_url=_url_with_args("export_xlsx", page=None),
            last_synced=last_synced,
            syncing=app.config["SYNCING"],
        )

    @app.get("/export.xlsx")
    def export_xlsx():
        filters = _filters_from_request()
        cone_id = _cone_id_from_request()
        local_tag = _tag_from_request("local_tag")
        group_tag = _tag_from_request("group_tag")
        field_filters = _field_filters_from_request()
        sort_by, sort_dir = _sort_from_request()
        q = request.args.get("q", "")
        with store.connect(cfg.db_path) as conn:
            rows, _total = store.query_items(
                conn,
                filters,
                q,
                field_filters=field_filters,
                cone_id=cone_id,
                local_tag=local_tag,
                group_tag=group_tag,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=50_000,
                offset=0,
            )
            paths = store.field_paths(conn)
            object_ids = [row["object_id"] for row in rows]
            field_matrix = store.export_field_matrix(conn, object_ids, paths)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "publications"
        sheet.append([label for _col, label in COLUMNS] + paths + ["raw_json"])
        for row in rows:
            raw_json = json.dumps(json.loads(row["data"]), ensure_ascii=False)
            sheet.append(
                [row[col] for col, _label in COLUMNS]
                + [field_matrix.get(row["object_id"], {}).get(path, "") for path in paths]
                + [raw_json]
            )

        buf = io.BytesIO()
        workbook.save(buf)
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name="publications.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.post("/refresh")
    def refresh():
        threading.Thread(target=sync_now, args=(client, cfg, app), daemon=True).start()
        return redirect(url_for("index"))

    @app.get("/status")
    def status():
        with store.connect(cfg.db_path) as conn:
            last_synced = store.get_meta(conn, "last_synced_at", "never")
            expected = store.get_meta(conn, "expected_item_count", "unknown")
            progress = store.get_meta(conn, "sync_progress_count", "0")
            count = store.item_count(conn)
        return {
            "last_synced_at": last_synced,
            "expected_item_count": expected,
            "sync_progress_count": progress,
            "item_count": count,
            "syncing": app.config["SYNCING"],
        }

    return app


def _sync_loop(client: Client, cfg: Config, app: Flask) -> None:
    """Sync immediately on startup, then every ``interval_hours``."""
    while True:
        sync_now(client, cfg, app)
        time.sleep(cfg.interval_hours * 3600)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cfg = Config.from_env()
    client = Client(base_url=cfg.base_url)
    store.init_db(cfg.db_path)

    app = create_app(client, cfg)
    # Fetch immediately in the background so the site is usable right away
    # (showing "no data yet" until the first pass commits) instead of
    # blocking the port on a potentially long initial fetch.
    threading.Thread(target=_sync_loop, args=(client, cfg, app), daemon=True).start()
    app.run(host="0.0.0.0", port=cfg.port, threaded=True)


if __name__ == "__main__":
    main()
