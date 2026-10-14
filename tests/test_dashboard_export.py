from datetime import datetime, timedelta, timezone

import pytest

from src.dashboard_export import _clean_title, _split_summary, _tag_for, build_tasks
from src.utils.models import CanvasEvent

CONFIG = {
    "timezone": "America/Los_Angeles",
    "days_behind": 7,
    "include_calendar_events": False,
    "course_tags": {},
    "title_strip": [],
    "max_title_length": 70,
}


def event(uid="event-assignment-1", title="Assignment: HW 1 [CSE100_FA26_001]", due_date=None, due_datetime=None):
    due_date = due_date or (datetime.now() + timedelta(days=3)).date().isoformat()
    return CanvasEvent(
        title=title, due_datetime=due_datetime, due_date=due_date, course_id=1,
        course_name="Canvas", source="ical", external_id=uid, html_url="https://canvas.ucsd.edu/x",
    )


@pytest.mark.parametrize("key,expected", [
    ("CSE100_FA26_001", "CSE 100"),
    ("MATH18_FA26_A00", "MATH 18"),
    ("CSE 103", "CSE 103"),
    ("math20c", "MATH 20C"),
    ("", "Canvas"),
])
def test_tag_from_course_key(key, expected):
    assert _tag_for(key, {}) == expected


def test_tag_override_wins():
    assert _tag_for("CSE100_FA26_001", {"CSE100": "Data Structures"}) == "Data Structures"


def test_split_summary_removes_prefix_and_course():
    assert _split_summary("Assignment: Group Report #1 [CAT125_FA26_005]") == ("Group Report #1", "CAT125_FA26_005")
    assert _split_summary("Quiz: Week 2 [MATH18_FA26_A00]") == ("Week 2", "MATH18_FA26_A00")
    assert _split_summary("Plain title") == ("Plain title", "")


def test_clean_title_strips_and_truncates():
    config = {**CONFIG, "title_strip": [r"^Fall\s+\d{4}\s*-\s*"], "max_title_length": 20}
    assert _clean_title("Fall 2026-Short", config) == "Short"
    out = _clean_title("A very long assignment title indeed", config)
    assert len(out) <= 20 and out.endswith("...")


def test_build_tasks_only_assignments_by_default():
    events = [event(), event(uid="event-calendar-event-9", title="Lecture [CSE100_FA26_001]")]
    tasks = build_tasks(events, CONFIG, {})
    assert [t["name"] for t in tasks] == ["HW 1"]
    assert tasks[0]["tag"] == "CSE 100"


def test_build_tasks_includes_calendar_events_when_enabled():
    events = [event(uid="event-calendar-event-9", title="Lecture [CSE100_FA26_001]")]
    assert len(build_tasks(events, {**CONFIG, "include_calendar_events": True}, {})) == 1


def test_build_tasks_drops_old_items():
    old = (datetime.now() - timedelta(days=30)).date().isoformat()
    assert build_tasks([event(due_date=old)], CONFIG, {}) == []


def test_late_night_deadline_keeps_pacific_date():
    # 11:59 PM Pacific on Oct 12 is 06:59 UTC on Oct 13.
    due = datetime(2099, 10, 13, 6, 59, tzinfo=timezone.utc)
    tasks = build_tasks([event(due_date="2099-10-13", due_datetime=due)], CONFIG, {})
    assert tasks[0]["date"] == "2099-10-12"


def test_source_tag_and_id_prefix():
    tasks = build_tasks([event()], CONFIG, {"tag": "Community College", "id_prefix": "cc:"})
    assert tasks[0]["tag"] == "Community College"
    assert tasks[0]["canvasId"] == "cc:event-assignment-1"


# ---------------------------------------------------------------------------
# Refresh report: every source says whether it worked
# ---------------------------------------------------------------------------

import json

import requests

from src import dashboard_export as export
from src.canvas.ical_client import FeedError, fetch_ical_events


@pytest.fixture()
def report_env(tmp_path, monkeypatch):
    config = {
        "timezone": "America/Los_Angeles", "days_behind": 7, "include_calendar_events": False,
        "course_tags": {}, "ensure_tags": [], "title_strip": [], "max_title_length": 200,
        "sources": [
            {"env": "FEED_A", "label": "School A"},
            {"env": "FEED_B", "tag": "School B", "id_prefix": "b:"},
        ],
    }
    monkeypatch.setattr(export, "_load_config", lambda: config)
    monkeypatch.setattr(export, "OUTPUT_PATH", tmp_path / "canvas_tasks.js")
    monkeypatch.setattr(export, "EXTENSION_SOURCES", {"prairielearn": tmp_path / "pl.json", "gradescope": tmp_path / "gs.json"})
    monkeypatch.setenv("FEED_A", "https://secret.example/feed-a.ics")
    monkeypatch.setenv("FEED_B", "https://secret.example/feed-b.ics")
    return tmp_path


def by_label(report):
    return {s["label"]: s for s in report["sources"]}


def test_report_flags_failed_feed_and_unset_url(report_env, monkeypatch):
    monkeypatch.delenv("FEED_B")
    monkeypatch.setattr(export, "fetch_ical_events", lambda env, raise_errors=False: (_ for _ in ()).throw(FeedError("HTTP 404")))
    sources = by_label(export.export_dashboard_report())
    assert sources["School A"]["ok"] is False and sources["School A"]["error"] == "HTTP 404"
    assert sources["School B"]["ok"] is False and "FEED_B is not set" in sources["School B"]["error"]


def test_empty_feed_is_ok_not_an_error(report_env, monkeypatch):
    monkeypatch.setattr(export, "fetch_ical_events", lambda env, raise_errors=False: [])
    sources = by_label(export.export_dashboard_report())
    assert sources["School A"]["ok"] is True and sources["School A"]["count"] == 0


def test_failed_everything_keeps_previous_file(report_env, monkeypatch):
    (report_env / "canvas_tasks.js").write_text("old")
    monkeypatch.setattr(export, "fetch_ical_events", lambda env, raise_errors=False: (_ for _ in ()).throw(FeedError("timed out")))
    assert export.export_dashboard_report()["count"] == 0
    assert (report_env / "canvas_tasks.js").read_text() == "old"


def test_extension_sources_report_last_sync(report_env, monkeypatch):
    monkeypatch.setattr(export, "fetch_ical_events", lambda env, raise_errors=False: [])
    (report_env / "pl.json").write_text(json.dumps({"items": [
        {"id": "1:HW1", "course": "CSE 103", "name": "HW1", "date": "2999-01-01", "url": "u"}]}))
    sources = by_label(export.export_dashboard_report())
    assert sources["PrairieLearn"]["ok"] and sources["PrairieLearn"]["count"] == 1 and sources["PrairieLearn"]["updated"]
    assert sources["Gradescope"]["ok"] is False and sources["Gradescope"]["error"] == "has never synced"


def test_feed_errors_never_contain_the_secret_url(monkeypatch):
    monkeypatch.setenv("FEED_A", "https://secret.example/feed-a.ics")

    def boom(url, timeout):
        resp = requests.Response()
        resp.status_code = 404
        resp.url = url
        raise requests.HTTPError("404 Client Error: Not Found for url: " + url, response=resp)

    monkeypatch.setattr(requests, "get", boom)
    with pytest.raises(FeedError) as exc:
        fetch_ical_events("FEED_A", raise_errors=True)
    assert "secret.example" not in str(exc.value) and "404" in str(exc.value)
    assert fetch_ical_events("FEED_A") == []  # default stays quiet for the nightly job
