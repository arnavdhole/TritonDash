import json
import threading
from http.server import ThreadingHTTPServer
from urllib import error, request

import pytest

from scripts import dashboard_server as server


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "EXTENSION_SOURCES", {"gradescope": tmp_path / "gs.json", "prairielearn": tmp_path / "pl.json"})
    monkeypatch.setattr(server, "BACKUP_DIR", tmp_path / "backups")
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


# ---------------------------------------------------------------------------
# Task backups
# ---------------------------------------------------------------------------

def get(url, headers=None):
    try:
        with request.urlopen(request.Request(url, headers=headers or {})) as res:
            return res.status, json.loads(res.read())
    except error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def tasks(n):
    return [{"id": str(i), "name": "t%d" % i, "tag": "CSE 100", "date": "2026-10-20", "done": i % 2 == 0} for i in range(n)]


def backup(n, **extra):
    return {"tasks": tasks(n), "categories": {"class": ["CSE 100"], "extra": []}, **extra}


def test_backup_round_trip_keeps_done_state_and_dismissed(base):
    url, tmp = base
    assert get(url + "/backup/latest")[0] == 404
    status, body = post(url + "/backup", backup(12, dismissed=["event-assignment-9"], aliases={"A": "B"}))
    assert (status, body["ok"], body["count"]) == (200, True, 12)
    status, latest = get(url + "/backup/latest")
    assert status == 200 and len(latest["tasks"]) == 12
    assert latest["dismissed"] == ["event-assignment-9"] and latest["aliases"] == {"A": "B"}
    assert latest["tasks"][0]["done"] is True
    assert len(list((tmp / "backups").glob("tasks-*.json"))) == 1


def test_empty_browser_cannot_replace_a_real_backup(base):
    url, _ = base
    post(url + "/backup", backup(12))
    status, body = post(url + "/backup", backup(0))
    assert status == 409 and "Restore from backup" in body["error"]
    assert len(get(url + "/backup/latest")[1]["tasks"]) == 12


def test_canvas_only_browser_cannot_replace_a_larger_backup(base):
    url, _ = base
    post(url + "/backup", backup(40))
    assert post(url + "/backup", backup(15))[0] == 409          # far fewer: refused
    assert post(url + "/backup", backup(30))[0] == 200          # normal pruning: accepted
    assert len(get(url + "/backup/latest")[1]["tasks"]) == 30


def test_small_backups_can_grow_and_shrink_freely(base):
    url, _ = base
    assert post(url + "/backup", backup(3))[0] == 200
    assert post(url + "/backup", backup(1))[0] == 200


def test_backup_rejects_bad_data_and_foreign_sites(base):
    url, _ = base
    assert post(url + "/backup", {"tasks": "nope", "categories": {}})[0] == 400
    assert post(url + "/backup", {"tasks": [], "categories": []})[0] == 400
    assert post(url + "/backup", backup(2), {"Origin": "https://evil.example"})[0] == 403
    assert get(url + "/backup/latest", {"Origin": "https://evil.example"})[0] == 403
    assert get(url + "/backup/latest", {"Host": "evil.example"})[0] == 403


def test_replaced_backup_is_kept_in_history_when_tasks_vanish(base):
    url, tmp = base
    post(url + "/backup", backup(40))
    assert not (tmp / "backups" / "history").exists()
    # A browser that only holds some of the tasks: accepted, but the old backup is preserved.
    assert post(url + "/backup", {"tasks": tasks(40)[:30] + [{"id": "new", "name": "x"}], "categories": {}})[0] == 200
    kept = list((tmp / "backups" / "history").glob("before-*.json"))
    assert len(kept) == 1 and len(json.loads(kept[0].read_text())["tasks"]) == 40


def test_ordinary_edits_do_not_fill_history(base):
    url, tmp = base
    post(url + "/backup", backup(40))
    post(url + "/backup", backup(40))
    post(url + "/backup", backup(38))   # two removed: not worth a copy
    assert not (tmp / "backups" / "history").exists()
