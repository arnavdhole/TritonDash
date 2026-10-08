import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from src.utils.dedup import make_sync_id
from src.utils.models import CanvasEvent

_color_map: dict[int, str] = {}
_default_color: str = "7"
_colors_loaded = False


def _load_color_map() -> None:
    global _color_map, _default_color, _colors_loaded
    if _colors_loaded:
        return
    config_path = Path("config/course_colors.yaml")
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}
        _color_map = {int(k): str(v) for k, v in data.get("course_colors", {}).items()}
        _default_color = str(data.get("default_color", 7))
    _colors_loaded = True


def build_gcal_event(event: CanvasEvent) -> dict[str, Any]:
    """Convert a CanvasEvent into a Google Calendar API event dict."""
    _load_color_map()

    sync_id = make_sync_id(event)
    timezone = os.environ.get("TIMEZONE", "America/New_York")
    color_id = _color_map.get(event.course_id or -1, _default_color)

    # Build description
    parts = [f"Course: {event.course_name}"]
    if event.points_possible is not None:
        parts.append(f"Points: {event.points_possible}")
    if event.submission_types:
        parts.append(f"Submit via: {', '.join(event.submission_types)}")
    if event.html_url:
        parts.append(f"Canvas: {event.html_url}")
    if event.description:
        parts.append("")
        parts.append(event.description[:500])
    parts.append(f"\n[CanvasCalendar | source={event.source} | id={sync_id}]")
    description = "\n".join(parts)

    # Build start/end
    if event.due_datetime:
        # 15-minute block ending at the deadline
        end_dt = event.due_datetime
        start_dt = end_dt - timedelta(minutes=15)
        start = {"dateTime": start_dt.isoformat(), "timeZone": timezone}
        end = {"dateTime": end_dt.isoformat(), "timeZone": timezone}
    else:
        start = {"date": event.due_date}
        end = {"date": event.due_date}

    return {
        "summary": f"[{event.course_name}] {event.title}",
        "description": description,
        "start": start,
        "end": end,
        "colorId": color_id,
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 1440},  # 24 hours
                {"method": "popup", "minutes": 60},    # 1 hour
            ],
        },
        "extendedProperties": {
            "private": {
                "canvas_sync_id": sync_id,
                "canvas_source": event.source,
                "canvas_course_id": str(event.course_id or ""),
            }
        },
    }
