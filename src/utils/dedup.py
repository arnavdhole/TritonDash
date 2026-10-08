import hashlib
from src.utils.models import CanvasEvent

APP_TAG = "canvas_cal_sync_v1"


def make_sync_id(event: CanvasEvent) -> str:
    """
    Produces a stable, deterministic dedup ID stored as a GCal private
    extended property so the syncer can find existing events without
    maintaining a local database.

    Key strategy by source:
      assignment/todo  → course_id + assignment_id  (most stable)
      syllabus_html    → course_id + title[:40] + due_date
      syllabus_pdf     → external_id (set to "sha256prefix:title" by pdf processor)
      manual           → external_id from YAML (user-controlled)
    """
    if event.source in ("assignment", "todo") and event.assignment_id is not None:
        raw = f"assignment:{event.course_id}:{event.assignment_id}"
    elif event.source == "ical" and event.external_id:
        # iCal UIDs are globally unique and stable — ideal dedup key
        raw = f"ical:{event.external_id}"
    elif event.source == "manual" and event.external_id:
        raw = f"manual:{event.external_id}"
    elif event.source == "syllabus_pdf" and event.external_id:
        raw = f"pdf:{event.external_id}"
    else:
        raw = f"{event.source}:{event.course_id}:{event.title[:40]}:{event.due_date}"

    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{APP_TAG}:{digest}"
