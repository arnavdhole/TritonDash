import logging
from datetime import datetime, timezone
from canvasapi import Canvas
from src.utils.models import CanvasEvent

logger = logging.getLogger(__name__)


def _parse_canvas_datetime(dt_str: str) -> datetime:
    cleaned = dt_str.rstrip("Z")
    if "+" not in cleaned and cleaned.count("-") <= 2:
        cleaned += "+00:00"
    return datetime.fromisoformat(cleaned).astimezone(timezone.utc)


def fetch_todos(canvas: Canvas) -> list[CanvasEvent]:
    """
    Fetch user-level todo items from Canvas. These overlap with assignments
    but may include quiz-type entries missing from get_assignments().
    Deduplication in the sync layer handles any overlap.
    """
    events: list[CanvasEvent] = []

    try:
        for todo in canvas.get_todo_items():
            if getattr(todo, "type", None) != "submitting":
                continue

            assignment = getattr(todo, "assignment", None)
            if not assignment:
                continue

            # canvasapi returns assignment as a dict-like object
            if isinstance(assignment, dict):
                due_at = assignment.get("due_at")
                name = assignment.get("name", "Untitled")
                a_id = assignment.get("id")
                html_url = assignment.get("html_url", "")
            else:
                due_at = getattr(assignment, "due_at", None)
                name = getattr(assignment, "name", "Untitled")
                a_id = getattr(assignment, "id", None)
                html_url = getattr(assignment, "html_url", "")

            if not due_at:
                continue

            try:
                due = _parse_canvas_datetime(due_at)
            except (ValueError, AttributeError) as exc:
                logger.warning("Could not parse todo due_at '%s': %s", due_at, exc)
                continue

            course_id = getattr(todo, "course_id", None)
            events.append(
                CanvasEvent(
                    title=name,
                    due_datetime=due,
                    due_date=due.date().isoformat(),
                    course_id=course_id,
                    course_name=f"Course {course_id}" if course_id else "Unknown",
                    source="todo",
                    html_url=html_url,
                    assignment_id=a_id,
                )
            )
    except Exception as exc:
        logger.error("Error fetching todos: %s", exc)

    return events
