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
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=ROOT / ".env")

from src.canvas.ical_client import FeedError, fetch_ical_events
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


EXTENSION_LABELS = {"prairielearn": "PrairieLearn", "gradescope": "Gradescope"}


def _extension_status(config: dict, extension_tasks: list[dict]) -> list[dict]:
    """One entry per extension site, based on what the helper has stored so far."""
    entries = []
    for site, path in EXTENSION_SOURCES.items():
        entry = {"label": EXTENSION_LABELS.get(site, site), "kind": "extension", "site": site}
        if path.exists():
            kept = sum(1 for t in extension_tasks if t["canvasId"].startswith(site + ":"))
            updated = datetime.fromtimestamp(path.stat().st_mtime, ZoneInfo(config["timezone"]))
            entry.update(ok=True, count=kept, updated=updated.isoformat(timespec="seconds"))
        else:
            entry.update(ok=False, count=0, error="has never synced")
        entries.append(entry)
    return entries


def export_dashboard_report() -> dict:
    """
    Fetch every Canvas feed and write the dashboard file.
    Returns {"count": int, "sources": [...]} where each source says whether it worked,
    so the dashboard can report a broken feed instead of looking like an empty one.
    """
    config = _load_config()
    tasks = []
    sources = []
    any_feed_ok = False

    for source in config["sources"]:
        entry = {
            "label": source.get("label") or source.get("tag") or "Canvas",
            "kind": "calendar",
            "ok": False,
            "count": 0,
        }
        sources.append(entry)
        if not os.environ.get(source["env"], "").strip():
            entry["error"] = source["env"] + " is not set in .env"
            continue
        try:
            events = fetch_ical_events(source["env"], raise_errors=True)
        except FeedError as exc:
            entry["error"] = str(exc)
            continue
        built = build_tasks(events, config, source)
        tasks.extend(built)
        entry.update(ok=True, count=len(built))
        any_feed_ok = True

    extension_tasks = build_extension_tasks(config)
    tasks.extend(extension_tasks)
    sources.extend(_extension_status(config, extension_tasks))

    if not any_feed_ok and not extension_tasks:
        # Keep the previous file rather than wiping it after a failed fetch.
        logger.warning("No source worked; leaving %s unchanged.", OUTPUT_PATH.name)
        return {"count": 0, "sources": sources}

    tasks.sort(key=lambda t: (t["date"], t["name"]))
    payload = {
        "generated": datetime.now(ZoneInfo(config["timezone"])).isoformat(timespec="seconds"),
        "tags": config["ensure_tags"],
        "tasks": tasks,
    }
    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text("window.CANVAS_TASKS = " + json.dumps(payload, indent=2) + ";\n")
    logger.info("Wrote %d Canvas tasks to %s", len(tasks), OUTPUT_PATH)
    return {"count": len(tasks), "sources": sources}


def export_dashboard_tasks() -> int:
    """Fetch the Canvas feeds and write the dashboard file. Returns task count."""
    return export_dashboard_report()["count"]


if __name__ == "__main__":
    setup_logging()
    export_dashboard_tasks()
