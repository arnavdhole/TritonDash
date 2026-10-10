from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CanvasEvent:
    """
    One deadline read from a Canvas calendar feed.
    """
    title: str
    due_datetime: Optional[datetime]        # None → all-day event on due_date
    due_date: Optional[str]                 # ISO date string "YYYY-MM-DD"
    course_id: Optional[int]               # Canvas course ID (None for manual/PDF)
    course_name: str
    source: str
    description: str = ""
    html_url: str = ""
    points_possible: Optional[float] = None
    submission_types: list = field(default_factory=list)
    assignment_id: Optional[int] = None    # Canvas assignment ID; used for dedup
    external_id: Optional[str] = None      # Stable ID for manual/PDF entries
