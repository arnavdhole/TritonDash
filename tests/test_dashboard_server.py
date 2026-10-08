import json
import threading
from http.server import ThreadingHTTPServer
from urllib import error, request

import pytest

from scripts import dashboard_server as server


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "EXTENSION_SOURCES", {"gradescope": tmp_path / "gs.json", "prairielearn": tmp_path / "pl.json"})
    monkeypatch.setattr(server, "PORT", 0)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_address[1]
    monkeypatch.setattr(server, "ALLOWED_HOSTS", {f"127.0.0.1:{port}"})
    monkeypatch.setattr(server, "ALLOWED_ORIGIN_PREFIXES", (f"http://127.0.0.1:{port}", "chrome-extension://", "moz-extension://"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}", tmp_path
    httpd.shutdown()


def post(url, body, headers=None):
    req = request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with request.urlopen(req) as res:
            return res.status, json.loads(res.read())
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


ITEM = {"id": "1:2", "course": "CSE 100", "name": "PA1", "date": "2026-10-15", "url": "u"}


def test_extension_post_is_stored(base):
    url, tmp = base
    status, body = post(url + "/gradescope", {"items": [ITEM, {"id": "bad"}]}, {"Origin": "chrome-extension://abc"})
    assert (status, body["count"]) == (200, 1)
    assert json.loads((tmp / "gs.json").read_text())["items"][0]["name"] == "PA1"


def test_foreign_website_origin_is_rejected(base):
    url, tmp = base
    status, _ = post(url + "/gradescope", {"items": [ITEM]}, {"Origin": "https://evil.example"})
    assert status == 403 and not (tmp / "gs.json").exists()


def test_unexpected_host_header_is_rejected(base):
    url, _ = base
    status, _ = post(url + "/gradescope", {"items": [ITEM]}, {"Host": "evil.example"})
    assert status == 403


def test_bad_json_and_unknown_path(base):
    url, _ = base
    req = request.Request(url + "/gradescope", data=b"nope", method="POST")
    with pytest.raises(error.HTTPError) as exc:
        request.urlopen(req)
    assert exc.value.code == 400
    assert post(url + "/bogus", {})[0] == 404
