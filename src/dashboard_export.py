#!/usr/bin/env python3
"""
Exports Canvas assignments to dashboard/canvas_tasks.js for the school dashboard.

The dashboard loads that file with a <script> tag (so it works when opened
straight from disk) and merges the tasks into its own localStorage data.

Usage:
    python -m src.dashboard_export
"""
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=ROOT / ".env")

from src.canvas.ical_client import fetch_ical_events
from src.utils.logger import setup_logging

logger = logging.getLogger(__name__)

CONFIG_PATH = ROOT / "config" / "dashboard.yaml"
EXAMPLE_CONFIG_PATH = ROOT / "config" / "dashboard.example.yaml"
OUTPUT_PATH = ROOT / "dashboard" / "canvas_tasks.js"
# Deadlines the Chrome extension scrapes and posts to the local server, one file per site.
EXTENSION_SOURCES = {
    "prairielearn": ROOT / "data" / "prairielearn_tasks.json",
    "gradescope": ROOT / "data" / "gradescope_tasks.json",
}

# "Assignment: Group Report #1 [CAT125_FA26_005]"
_PREFIX_RE = re.compile(r"^(Assignment|Quiz|Discussion):\s*", re.IGNORECASE)
_BRACKET_RE = re.compile(r"\s*\[([^\]]+)\]\s*$")
# "CAT125_FA26_005" -> ("CAT", "125")
_CODE_RE = re.compile(r"^([A-Za-z]+)\s*(\d+[A-Za-z]?)")


def _load_config() -> dict:
    config = {
        "timezone": "America/Los_Angeles",
        "days_behind": 7,
        "include_calendar_events": False,
        "course_tags": {},
        "sources": [{"env": "CANVAS_ICAL_URL"}],
        "ensure_tags": [],
        "title_strip": [],
        "max_title_length": 200,
    }
    # config/dashboard.yaml is personal and untracked; the example is the fallback.
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    if path.exists():
        config.update(yaml.safe_load(path.read_text()) or {})
    config["course_tags"] = config["course_tags"] or {}
    return config


def _clean_title(title: str, config: dict) -> str:
    for pattern in config["title_strip"]:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" -")
    limit = int(config["max_title_length"])
    if len(title) > limit:
        title = title[: limit - 3].rstrip(" -,") + "..."
    return title


def _split_summary(summary: str) -> tuple[str, str]:
    """Returns (clean title, course key like 'CAT125_FA26_005')."""
    course_key = ""
    m = _BRACKET_RE.search(summary)
    if m:
        course_key = m.group(1)
        summary = summary[: m.start()]
    title = _PREFIX_RE.sub("", summary).strip()
    return title, course_key


def _tag_for(course_key: str, overrides: dict) -> str:
    if course_key in overrides:
        return overrides[course_key]
    m = _CODE_RE.match(course_key)
    if not m:
        return overrides.get("default", "Canvas")
    code = f"{m.group(1).upper()}{m.group(2).upper()}"
    if code in overrides:
        return overrides[code]
    return f"{m.group(1).upper()} {m.group(2).upper()}"


def build_tasks(events, config: dict, source: dict) -> list[dict]:
    tz = ZoneInfo(config["timezone"])
    cutoff = (datetime.now(tz) - timedelta(days=int(config["days_behind"]))).date().isoformat()
    tasks = []
    fixed_tag = source.get("tag")
    id_prefix = source.get("id_prefix", "")

    for ev in events:
        uid = ev.external_id or ""
        is_assignment = uid.startswith("event-assignment-")
        if not is_assignment and not config["include_calendar_events"]:
            continue

        # Timed events arrive in UTC; convert so a late-night deadline keeps its local date.
        if ev.due_datetime is not None:
            due = ev.due_datetime.astimezone(tz).date().isoformat()
        else:
            due = ev.due_date
        if not due or due < cutoff:
            continue

        title, course_key = _split_summary(ev.title)
        title = _clean_title(title, config)
        tasks.append(
            {
                "canvasId": id_prefix + (uid or f"{ev.title}|{due}"),
                "name": title,
                "tag": fixed_tag or _tag_for(course_key, config["course_tags"]),
                "date": due,
                "url": ev.html_url,
            }
        )

    return tasks


def build_extension_tasks(config: dict) -> list[dict]:
    """Tasks the Chrome extension posted to the local server (see extension/)."""
    tz = ZoneInfo(config["timezone"])
    cutoff = (datetime.now(tz) - timedelta(days=int(config["days_behind"]))).date().isoformat()
    tasks = []
    for site, path in EXTENSION_SOURCES.items():
        if not path.exists():
            continue
        for item in json.loads(path.read_text()).get("items", []):
            if item["date"] < cutoff:
                continue
            tasks.append(
                {
                    "canvasId": site + ":" + item["id"],
                    "name": _clean_title(item["name"], config),
                    "tag": _tag_for(item.get("course", ""), config["course_tags"]),
                    "date": item["date"],
                    "url": item.get("url", ""),
                }
            )
    return tasks


def export_dashboard_tasks() -> int:
    """Fetch the Canvas feed and write the dashboard file. Returns task count."""
    config = _load_config()
    tasks = []
    fetched_any = False
    for source in config["sources"]:
        events = fetch_ical_events(source["env"])
        if events:
            fetched_any = True
            tasks.extend(build_tasks(events, config, source))

    extension_tasks = build_extension_tasks(config)
    tasks.extend(extension_tasks)

    if not fetched_any and not extension_tasks:
        # Keep the previous file rather than wiping it after a failed fetch.
        logger.warning("No events fetched; leaving %s unchanged.", OUTPUT_PATH.name)
        return 0

    tasks.sort(key=lambda t: (t["date"], t["name"]))
    payload = {
        "generated": datetime.now(ZoneInfo(config["timezone"])).isoformat(timespec="seconds"),
        "tags": config["ensure_tags"],
        "tasks": tasks,
    }
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text("window.CANVAS_TASKS = " + json.dumps(payload, indent=2) + ";\n")
    logger.info("Wrote %d Canvas tasks to %s", len(tasks), OUTPUT_PATH)
    return len(tasks)


if __name__ == "__main__":
    setup_logging()
    export_dashboard_tasks()
