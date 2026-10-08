import logging
import re
from bs4 import BeautifulSoup
from dateutil.parser import parse as dateparse, ParserError
from src.utils.models import CanvasEvent

logger = logging.getLogger(__name__)

# Matches spelled-out month names with an optional day ordinal and year
_DATE_RE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
    re.IGNORECASE,
)


def scrape_syllabus(course) -> list[CanvasEvent]:
    """
    Parse the Canvas HTML syllabus body for dates and event titles.
    Returns a list of CanvasEvents where source="syllabus_html".
    """
    html = getattr(course, "syllabus_body", None)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    events: list[CanvasEvent] = []
    seen: set[str] = set()

    for element in soup.find_all(["tr", "li", "p", "td"]):
        text = element.get_text(" ", strip=True)
        if not text or len(text) < 5:
            continue

        match = _DATE_RE.search(text)
        if not match:
            continue

        try:
            due = dateparse(match.group(), fuzzy=True, dayfirst=False)
        except (ParserError, OverflowError):
            continue

        due_date_str = due.date().isoformat()
        title = text[:100].strip()
        dedup_key = f"{course.id}:{title[:40]}:{due_date_str}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        events.append(
            CanvasEvent(
                title=title,
                due_datetime=None,
                due_date=due_date_str,
                course_id=course.id,
                course_name=course.name,
                source="syllabus_html",
                description=text[:500],
            )
        )

    logger.info(
        "Syllabus scrape for '%s': found %d date entries", course.name, len(events)
    )
    return events
