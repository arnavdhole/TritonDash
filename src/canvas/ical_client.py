"""
Canvas iCal feed client. Needs no API token.

Canvas exposes a secret .ics URL for every user's calendar that contains
all assignments, due dates, and calendar events. No API token required.

How to find your iCal URL:
  1. Log into Canvas → click "Calendar" in the left sidebar
  2. Scroll to the bottom-right and click the calendar feed icon
     (looks like a chain-link or signal icon, labeled "Calendar Feed")
  3. Copy the full URL — it looks like:
     https://canvas.youruniversity.edu/feeds/calendars/user_XXXXXXX.ics
  4. Paste it into .env as CANVAS_ICAL_URL (extra feeds use their own variable names)
"""

import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import requests
from icalendar import Calendar, Event  # type: ignore
from src.utils.models import CanvasEvent

logger = logging.getLogger(__name__)

# Canvas puts the course name in the DESCRIPTION field like:
#   "Course: MATH 101\nSection: ..."  or just as free text
_COURSE_RE = re.compile(r"(?:Course|Class)[:\s]+([^\n]+)", re.IGNORECASE)

# Canvas assignment URLs contain the course ID: /courses/12345/assignments/67890
_COURSE_ID_RE = re.compile(r"/courses/(\d+)/")


def _parse_dt(dt_val) -> tuple[Optional[datetime], Optional[str]]:
    """
    Convert an icalendar date/datetime value to (datetime_or_None, date_str).
    Returns (None, date_str) for all-day events (vDate, not vDatetime).
    """
    if dt_val is None:
        return None, None

    dt = dt_val.dt

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt, dt.date().isoformat()
    else:
        # all-day: dt is a date object
        return None, dt.isoformat()


def _extract_course_name(description: str, url: str) -> str:
    """Best-effort course name extraction from iCal description or URL."""
    if description:
        m = _COURSE_RE.search(description)
        if m:
            return m.group(1).strip()
    return "Canvas"


def _extract_course_id(url: str) -> Optional[int]:
    if url:
        m = _COURSE_ID_RE.search(url)
        if m:
            return int(m.group(1))
    return None


class FeedError(Exception):
    """A calendar feed could not be fetched or read. The message never contains the feed URL."""


def _safe_reason(exc: Exception) -> str:
    """Short reason for a failed request. requests' own messages include the secret feed URL."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        hint = " (the calendar link was probably regenerated)" if code in (401, 403, 404) else ""
        return f"HTTP {code}{hint}"
    if isinstance(exc, requests.Timeout):
        return "timed out"
    if isinstance(exc, requests.ConnectionError):
        return "could not connect"
    return type(exc).__name__


def fetch_ical_events(env_var: str = "CANVAS_ICAL_URL", raise_errors: bool = False) -> list[CanvasEvent]:
    """
    Download and parse a Canvas iCal feed whose URL is stored in `env_var`.
    Returns a list of CanvasEvents with source="ical". Failures return [] unless
    `raise_errors` is set, which raises FeedError so callers can tell them from an empty feed.
    """
    ical_url = os.environ.get(env_var, "").strip()
    if not ical_url:
        logger.warning(
            "%s not set — skipping iCal source. "
            "Find it in Canvas → Calendar → Calendar Feed icon.",
            env_var,
        )
        return []

    logger.info("Fetching Canvas iCal feed...")
    try:
        resp = requests.get(ical_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        reason = _safe_reason(exc)
        logger.error("Failed to fetch iCal feed (%s): %s", env_var, reason)
        if raise_errors:
            raise FeedError(reason) from None
        return []

    try:
        cal = Calendar.from_ical(resp.content)
    except Exception as exc:
        logger.error("Failed to parse iCal data (%s): %s", env_var, type(exc).__name__)
        if raise_errors:
            raise FeedError("the link did not return a calendar") from None
        return []

    events: list[CanvasEvent] = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("SUMMARY", "Untitled")).strip()
        description = str(component.get("DESCRIPTION", "")).strip()
        url = str(component.get("URL", "")).strip()

        # Prefer DTSTART; fall back to DUE
        dt_prop = component.get("DTSTART") or component.get("DUE")
        if dt_prop is None:
            continue

        due_datetime, due_date = _parse_dt(dt_prop)
        if due_date is None:
            continue

        course_name = _extract_course_name(description, url)
        course_id = _extract_course_id(url)

        # Use the UID from the iCal event as a stable external_id for dedup
        uid = str(component.get("UID", "")).strip()

        events.append(
            CanvasEvent(
                title=summary,
                due_datetime=due_datetime,
                due_date=due_date,
                course_id=course_id,
                course_name=course_name,
                source="ical",
                description=description[:500],
                html_url=url,
                external_id=uid if uid else None,
            )
        )

    logger.info("iCal feed: parsed %d events", len(events))
    return events
