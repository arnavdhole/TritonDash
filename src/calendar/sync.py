import logging
import os
import time
from typing import Any, Optional

from googleapiclient.errors import HttpError

from src.calendar.event_builder import build_gcal_event
from src.utils.dedup import make_sync_id
from src.utils.models import CanvasEvent, SyncResult

logger = logging.getLogger(__name__)


def _get_calendar_id() -> str:
    return os.environ.get("GOOGLE_CALENDAR_ID", "primary")


def _find_existing_event(service, sync_id: str) -> Optional[dict[str, Any]]:
    """Search GCal for an event tagged with this sync_id private property."""
    result = service.events().list(
        calendarId=_get_calendar_id(),
        privateExtendedProperty=f"canvas_sync_id={sync_id}",
        showDeleted=False,
        maxResults=1,
    ).execute()
    items = result.get("items", [])
    return items[0] if items else None


def _needs_update(existing: dict, new: dict) -> bool:
    """Return True if any key field changed, warranting an API update call."""
    for field in ("summary", "description", "start", "end", "colorId"):
        if existing.get(field) != new.get(field):
            return True
    return False


def _sync_one(service, canvas_event: CanvasEvent, result: SyncResult) -> None:
    sync_id = make_sync_id(canvas_event)
    gcal_event = build_gcal_event(canvas_event)
    calendar_id = _get_calendar_id()

    for attempt in range(4):
        try:
            existing = _find_existing_event(service, sync_id)
            if existing:
                if _needs_update(existing, gcal_event):
                    service.events().update(
                        calendarId=calendar_id,
                        eventId=existing["id"],
                        body=gcal_event,
                    ).execute()
                    result.updated += 1
                else:
                    result.skipped += 1
            else:
                service.events().insert(
                    calendarId=calendar_id,
                    body=gcal_event,
                ).execute()
                result.created += 1
            return

        except HttpError as exc:
            if exc.resp.status == 429 and attempt < 3:
                wait = 2 ** attempt
                logger.warning("Rate limited — retrying in %ds", wait)
                time.sleep(wait)
            else:
                result.errors.append(
                    f"HttpError {exc.resp.status} for '{canvas_event.title}': {exc}"
                )
                return
        except Exception as exc:
            result.errors.append(f"Unexpected error for '{canvas_event.title}': {exc}")
            return


def sync_all_events(service, events: list[CanvasEvent]) -> SyncResult:
    result = SyncResult()
    for event in events:
        _sync_one(service, event, result)
    return result
