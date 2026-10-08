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
