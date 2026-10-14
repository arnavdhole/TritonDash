#!/usr/bin/env python3
"""
Local helper for the school dashboard's Refresh button.

Serves dashboard/ at http://127.0.0.1:8765 and runs the Canvas export when the
page POSTs to /refresh. It listens on localhost only and never returns task
data, just a count. The dashboard reloads canvas_tasks.js from disk afterwards.

Usage:
    python scripts/dashboard_server.py
"""
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dashboard_export import EXTENSION_SOURCES, export_dashboard_report  # noqa: E402
from src.utils.logger import setup_logging  # noqa: E402

HOST, PORT = "127.0.0.1", 8765
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGIN_PREFIXES = (
    f"http://127.0.0.1:{PORT}",
    f"http://localhost:{PORT}",
    "chrome-extension://",
    "moz-extension://",
)
MAX_BODY = 1_000_000
MAX_BACKUP_BODY = 5_000_000
BACKUP_DIR = ROOT / "data" / "backups"
BACKUP_KEEP_DAYS = 30
BACKUP_HISTORY_KEEP = 10
BACKUP_KEYS = ("tasks", "categories", "aliases", "dismissed", "seeded")
logger = logging.getLogger("dashboard_server")
_lock = threading.Lock()


def _latest_backup() -> dict | None:
    path = BACKUP_DIR / "latest.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _would_lose_data(latest: dict | None, incoming: list) -> bool:
    """A browser with cleared storage must not replace a real backup with a near-empty one."""
    old = len(latest.get("tasks", [])) if latest else 0
    if old == 0:
        return False
    if not incoming:
        return True
    return old >= 10 and len(incoming) < 0.6 * old


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _task_keys(backup: dict | None) -> set:
    # Canvas tasks keep a stable canvasId, while other tasks only have the id their browser made.
    return {t.get("canvasId") or t.get("id") for t in (backup or {}).get("tasks", [])}


def _keep_history_if_tasks_vanish(latest: dict | None, incoming: list) -> None:
    """Before replacing a backup, keep a copy when five or more of its tasks are missing from the new one."""
    if not latest:
        return
    lost = _task_keys(latest) - _task_keys({"tasks": incoming})
    if len(lost) < 5:
        return
    history = BACKUP_DIR / "history"
    history.mkdir(parents=True, exist_ok=True)
    _write_json(history / f"before-{datetime.now():%Y%m%d-%H%M%S}.json", latest)
    for old in sorted(history.glob("before-*.json"))[:-BACKUP_HISTORY_KEEP]:
        old.unlink()


def _prune_backups() -> None:
    cutoff = datetime.now() - timedelta(days=BACKUP_KEEP_DAYS)
    for path in BACKUP_DIR.glob("tasks-*.json"):
        if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            path.unlink()


class Handler(SimpleHTTPRequestHandler):
    def _origin_allowed(self) -> bool:
        """Blocks other websites from posting to the helper, and DNS rebinding."""
        if self.headers.get("Host", "") not in ALLOWED_HOSTS:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.startswith(ALLOWED_ORIGIN_PREFIXES)

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        if not self._origin_allowed():
            self._send_json(403, {"ok": False, "error": "Forbidden"})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _save_items(self, site: str) -> None:
        """Stores deadlines posted by the Chrome extension for the next export."""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send_json(400, {"ok": False, "error": "Bad body size"})
            return
        try:
            body = json.loads(self.rfile.read(length))
            items = [
                {k: str(i[k]) for k in ("id", "course", "name", "date", "url") if k in i}
                for i in body["items"]
                if isinstance(i, dict) and i.get("id") and i.get("name") and i.get("date")
            ]
        except (ValueError, KeyError, TypeError):
            self._send_json(400, {"ok": False, "error": "Bad JSON"})
            return
        path = EXTENSION_SOURCES[site]
        path.parent.mkdir(exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"items": items}, indent=2))
        os.replace(tmp, path)
        logger.info("Stored %d %s items", len(items), site)
        self._send_json(200, {"ok": True, "count": len(items)})

    def _save_backup(self) -> None:
        """Keeps the dashboard's tasks on disk, since the browser's own storage can be cleared."""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BACKUP_BODY:
            self._send_json(400, {"ok": False, "error": "Bad body size"})
            return
        try:
            body = json.loads(self.rfile.read(length))
            tasks = body["tasks"]
            if not isinstance(tasks, list) or not all(isinstance(t, dict) for t in tasks):
                raise ValueError
            if not isinstance(body["categories"], dict):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            self._send_json(400, {"ok": False, "error": "Bad JSON"})
            return

        with _lock:
            latest = _latest_backup()
            if _would_lose_data(latest, tasks):
                logger.warning("Refused backup with %d tasks over one with %d", len(tasks), len(latest["tasks"]))
                self._send_json(409, {
                    "ok": False,
                    "error": "this browser has far fewer tasks than the last backup, so the backup was kept. "
                             "Use Restore from backup if data was lost",
                })
                return
            snapshot = {k: body[k] for k in BACKUP_KEYS if k in body}
            snapshot["saved"] = datetime.now().isoformat(timespec="seconds")
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            _keep_history_if_tasks_vanish(latest, tasks)
            _write_json(BACKUP_DIR / "latest.json", snapshot)
            _write_json(BACKUP_DIR / f"tasks-{datetime.now():%Y-%m-%d}.json", snapshot)
            _prune_backups()
        self._send_json(200, {"ok": True, "count": len(tasks), "saved": snapshot["saved"]})

    def do_GET(self):
        if self.path.split("?")[0] == "/backup/latest":
            if not self._origin_allowed():
                self._send_json(403, {"ok": False, "error": "Forbidden"})
                return
            latest = _latest_backup()
            if latest is None:
                self._send_json(404, {"ok": False, "error": "No backup yet"})
            else:
                self._send_json(200, {"ok": True, **latest})
            return
        super().do_GET()

    def do_POST(self):
        if not self._origin_allowed():
            self._send_json(403, {"ok": False, "error": "Forbidden"})
            return
        if self.path == "/backup":
            self._save_backup()
            return
        site = self.path.lstrip("/")
        if site in EXTENSION_SOURCES:
            self._save_items(site)
            return
        if self.path != "/refresh":
            self._send_json(404, {"ok": False, "error": "Not found"})
            return
        with _lock:
            try:
                report = export_dashboard_report()
            except Exception as exc:
                logger.exception("Refresh failed")
                self._send_json(500, {"ok": False, "error": str(exc)})
                return
        self._send_json(200, {"ok": True, **report})

    def end_headers(self):
        # The dashboard must always see the freshest canvas_tasks.js.
        if self.command == "GET":
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    setup_logging()
    handler = partial(Handler, directory=str(ROOT / "dashboard"))
    server = ThreadingHTTPServer((HOST, PORT), handler)
    logger.info("Dashboard server on http://%s:%d", HOST, PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()
