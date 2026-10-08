import logging
import re
from datetime import datetime, timezone
from src.utils.models import CanvasEvent

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return _HTML_TAG_RE.sub("", html).strip()


def _parse_canvas_datetime(dt_str: str) -> datetime:
    """Parse Canvas ISO 8601 datetime string (may end with Z) to UTC datetime."""
    cleaned = dt_str.rstrip("Z")
    if "+" not in cleaned and cleaned.count("-") <= 2:
        cleaned += "+00:00"
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def fetch_assignments(course) -> list[CanvasEvent]:
    """Fetch upcoming and overdue assignments for a Canvas course."""
    events: list[CanvasEvent] = []
    seen_ids: set[int] = set()

    for bucket in ("upcoming", "overdue"):
        try:
            for a in course.get_assignments(bucket=bucket, order_by="due_at"):
                if not getattr(a, "due_at", None):
                    continue
                if a.id in seen_ids:
                    continue
                seen_ids.add(a.id)

                try:
                    due = _parse_canvas_datetime(a.due_at)
                except (ValueError, AttributeError) as exc:
                    logger.warning(
                        "Could not parse due_at '%s' for assignment %s: %s",
                        a.due_at,
                        a.id,
                        exc,
                    )
                    continue

                events.append(
                    CanvasEvent(
                        title=a.name,
                        due_datetime=due,
                        due_date=due.date().isoformat(),
                        course_id=course.id,
                        course_name=course.name,
                        source="assignment",
                        description=_strip_html(getattr(a, "description", "") or ""),
                        html_url=getattr(a, "html_url", ""),
                        points_possible=getattr(a, "points_possible", None),
                        submission_types=list(
                            getattr(a, "submission_types", []) or []
                        ),
                        assignment_id=a.id,
                    )
                )
        except Exception as exc:
            logger.error(
                "Error fetching '%s' assignments for course %s: %s",
                bucket,
                course.name,
                exc,
            )

    return events
