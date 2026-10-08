import logging
from datetime import datetime
from pathlib import Path

import yaml

from src.utils.models import CanvasEvent

logger = logging.getLogger(__name__)


def load_manual_events(yaml_path: str) -> list[CanvasEvent]:
    """Load and parse manual_entries.yaml into CanvasEvents."""
    path = Path(yaml_path)
    if not path.exists():
        return []

    data = yaml.safe_load(path.read_text()) or {}
    events: list[CanvasEvent] = []

    for item in data.get("events", []):
        entry_id = item.get("id")
        if not entry_id:
            logger.warning("Skipping manual entry missing required 'id' field: %s", item)
            continue

        due_date_str = item.get("due_date")
        if not due_date_str:
            logger.warning("Skipping manual entry '%s': missing due_date", entry_id)
            continue

        try:
            due_date = datetime.strptime(str(due_date_str), "%Y-%m-%d").date()
        except ValueError:
            logger.warning(
                "Skipping manual entry '%s': invalid due_date '%s'",
                entry_id,
                due_date_str,
            )
            continue

        due_dt = None
        due_time_str = item.get("due_time")
        if due_time_str:
            try:
                t = datetime.strptime(str(due_time_str), "%H:%M").time()
                due_dt = datetime.combine(due_date, t)
            except ValueError:
                logger.warning(
                    "Could not parse due_time '%s' for entry '%s'",
                    due_time_str,
                    entry_id,
                )

        events.append(
            CanvasEvent(
                title=item.get("title", "Untitled"),
                due_datetime=due_dt,
                due_date=str(due_date_str),
                course_id=None,
                course_name=item.get("course_name", "Manual"),
                source="manual",
                description=item.get("description", ""),
                external_id=str(entry_id),
            )
        )

    logger.info("Loaded %d manual events from %s", len(events), yaml_path)
    return events
