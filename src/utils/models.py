from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CanvasEvent:
    """
    Unified event model. All ingestion sources produce this before syncing to GCal.

    source values: "assignment" | "todo" | "syllabus_html" | "syllabus_pdf" | "manual"
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


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)
