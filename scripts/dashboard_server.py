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
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.dashboard_export import EXTENSION_SOURCES, export_dashboard_tasks  # noqa: E402
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
logger = logging.getLogger("dashboard_server")
_lock = threading.Lock()


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

    def do_POST(self):
        if not self._origin_allowed():
            self._send_json(403, {"ok": False, "error": "Forbidden"})
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
                count = export_dashboard_tasks()
            except Exception as exc:
                logger.exception("Refresh failed")
                self._send_json(500, {"ok": False, "error": str(exc)})
                return
        self._send_json(200, {"ok": True, "count": count})

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
