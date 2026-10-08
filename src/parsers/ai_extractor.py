import json
import logging
import os
import re
from datetime import datetime

import anthropic

from src.utils.models import CanvasEvent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a structured data extractor. Given raw syllabus text, extract all
deadlines, due dates, exams, quizzes, and assignments.

Return ONLY a valid JSON array (no prose, no markdown code fences) where each
element has exactly these fields:
{
  "title": "short event title",
  "due_date": "YYYY-MM-DD",
  "due_time": "HH:MM" or null,
  "description": "brief context from the syllabus (1-2 sentences)",
  "event_type": "assignment|exam|quiz|reading|project|other"
}

Rules:
- If a year is not given, assume the current academic year.
- Omit vague entries with no actionable date.
- Output an empty array [] if nothing is found.
- Do not include any text outside the JSON array.\
"""


def extract_events_from_text(text: str, course_name: str) -> list[CanvasEvent]:
    """
    Use Claude to extract structured events from raw syllabus text.
    Returns a list of CanvasEvents with source="syllabus_pdf".
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set in .env")

    client = anthropic.Anthropic(api_key=api_key)
    truncated = text[:15_000]

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Course: {course_name}\n\n---\n\n{truncated}",
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Attempt direct parse; fall back to extracting the JSON array if the
    # model wrapped it in prose
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            logger.warning("AI extractor returned no parseable JSON for '%s'", course_name)
            return []
        try:
            items = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("AI extractor JSON parse failed for '%s'", course_name)
            return []

    events: list[CanvasEvent] = []
    for item in items:
        due_str = item.get("due_date")
        if not due_str:
            continue
        try:
            due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Skipping bad date '%s' from AI extractor", due_str)
            continue

        due_dt = None
        if item.get("due_time"):
            try:
                t = datetime.strptime(item["due_time"], "%H:%M").time()
                due_dt = datetime.combine(due_date, t)
            except ValueError:
                pass

        events.append(
            CanvasEvent(
                title=item.get("title", "Untitled"),
                due_datetime=due_dt,
                due_date=due_str,
                course_id=None,
                course_name=course_name,
                source="syllabus_pdf",
                description=item.get("description", ""),
            )
        )

    logger.info(
        "AI extractor found %d events for course '%s'", len(events), course_name
    )
    return events
