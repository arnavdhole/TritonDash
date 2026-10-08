#!/usr/bin/env python3
"""
CanvasCalendar — main sync entrypoint.
Collects events from all sources and syncs them to Google Calendar.

Usage:
    python -m src.main
"""
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env before anything reads os.environ
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from src.utils.logger import setup_logging
from src.utils.models import CanvasEvent, SyncResult
from src.canvas.ical_client import fetch_ical_events
from src.canvas.client import get_canvas_client, get_active_courses
from src.canvas.assignments import fetch_assignments
from src.canvas.todos import fetch_todos
from src.canvas.syllabus_scraper import scrape_syllabus
from src.parsers.pdf_parser import extract_text_from_pdf
from src.parsers.ai_extractor import extract_events_from_text
from src.parsers.manual_parser import load_manual_events
from src.calendar.client import get_calendar_service
from src.calendar.sync import sync_all_events
from src.dashboard_export import export_dashboard_tasks

logger = logging.getLogger(__name__)

PROCESSED_PDFS_PATH = Path("data/processed_pdfs.json")
SYLLABI_PDF_DIR = Path("data/syllabi_pdf")
MANUAL_ENTRIES_PATH = Path("data/manual_entries.yaml")


# ---------------------------------------------------------------------------
# PDF syllabus processing
# ---------------------------------------------------------------------------

def _load_processed_pdfs() -> dict:
    if PROCESSED_PDFS_PATH.exists():
        return json.loads(PROCESSED_PDFS_PATH.read_text())
    return {"processed": {}}


def _save_processed_pdfs(state: dict) -> None:
    PROCESSED_PDFS_PATH.write_text(json.dumps(state, indent=2, default=str))


def _process_pdf_syllabi(processed_state: dict) -> list[CanvasEvent]:
    events: list[CanvasEvent] = []

    for pdf_path in sorted(SYLLABI_PDF_DIR.glob("*.pdf")):
        sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        name = pdf_path.name

        if processed_state["processed"].get(name, {}).get("sha256") == sha256:
            logger.info("Skipping already-processed PDF: %s", name)
            continue

        # Derive course name from filename stem (before first _ or -)
        stem = pdf_path.stem
        course_hint = stem.replace("-", "_").split("_")[0].replace("-", " ").strip()

        # Allow sidecar YAML to override course name
        sidecar = pdf_path.with_suffix(".yaml")
        if sidecar.exists():
            import yaml as _yaml
            meta = _yaml.safe_load(sidecar.read_text()) or {}
            course_hint = meta.get("course_name", course_hint)

        logger.info("Processing PDF: %s (course hint: '%s')", name, course_hint)
        try:
            text = extract_text_from_pdf(str(pdf_path))
            if not text.strip():
                logger.warning("PDF '%s' appears to have no extractable text", name)
                continue

            new_events = extract_events_from_text(text, course_hint)

            # Tag external_id for deduplication: sha256 prefix + title
            for ev in new_events:
                ev.external_id = f"{sha256[:12]}:{ev.title[:40]}"

            events.extend(new_events)

            processed_state["processed"][name] = {
                "sha256": sha256,
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "events_extracted": len(new_events),
                "course_name": course_hint,
            }
        except Exception as exc:
            logger.error("Failed to process PDF '%s': %s", name, exc)

    return events


# ---------------------------------------------------------------------------
# Event collection — all sources
# ---------------------------------------------------------------------------

def collect_all_events() -> list[CanvasEvent]:
    all_events: list[CanvasEvent] = []

    has_api_token = bool(os.environ.get("CANVAS_API_TOKEN", "").strip())
    has_ical_url = bool(os.environ.get("CANVAS_ICAL_URL", "").strip())

    # ── Source 1a: Canvas iCal feed (works without an API token) ──
    if has_ical_url:
        try:
            ical_events = fetch_ical_events()
            logger.info("iCal events: %d", len(ical_events))
            all_events.extend(ical_events)
        except Exception as exc:
            logger.error("iCal fetch error: %s", exc)
    elif not has_api_token:
        logger.warning(
            "Neither CANVAS_API_TOKEN nor CANVAS_ICAL_URL is set. "
            "Canvas assignments will not be synced.\n"
            "  → To use iCal (recommended): set CANVAS_ICAL_URL in .env\n"
            "    (Canvas → Calendar → Calendar Feed icon → copy URL)\n"
            "  → To use the API: set CANVAS_API_TOKEN in .env"
        )

    # ── Source 1b: Canvas REST API (assignments + todos + HTML syllabus) ──
    #    Only used if CANVAS_API_TOKEN is set (may be disabled by your institution)
    if has_api_token:
        try:
            canvas = get_canvas_client()
            courses = get_active_courses(canvas)
            logger.info("Found %d active Canvas courses", len(courses))

            for course in courses:
                logger.info("Processing course: %s (id=%s)", course.name, course.id)

                try:
                    assignments = fetch_assignments(course)
                    logger.info("  assignments: %d", len(assignments))
                    all_events.extend(assignments)
                except Exception as exc:
                    logger.error("Assignment fetch error for '%s': %s", course.name, exc)

                try:
                    syllabus_events = scrape_syllabus(course)
                    logger.info("  syllabus HTML entries: %d", len(syllabus_events))
                    all_events.extend(syllabus_events)
                except Exception as exc:
                    logger.error("Syllabus scrape error for '%s': %s", course.name, exc)

            try:
                todo_events = fetch_todos(canvas)
                logger.info("Todos: %d", len(todo_events))
                all_events.extend(todo_events)
            except Exception as exc:
                logger.error("Todos fetch error: %s", exc)

        except Exception as exc:
            logger.error("Canvas API client error: %s", exc)

    # ── Source 3: PDF syllabi ──
    processed_state = _load_processed_pdfs()
    pdf_events = _process_pdf_syllabi(processed_state)
    all_events.extend(pdf_events)
    _save_processed_pdfs(processed_state)

    # ── Source 4: Manual entries ──
    if MANUAL_ENTRIES_PATH.exists():
        try:
            manual_events = load_manual_events(str(MANUAL_ENTRIES_PATH))
            logger.info("Manual entries: %d", len(manual_events))
            all_events.extend(manual_events)
        except Exception as exc:
            logger.error("Manual entries error: %s", exc)

    logger.info("Total events collected: %d", len(all_events))
    return all_events


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()
    logger.info("=== CanvasCalendar sync started ===")

    # Independent of Google Calendar, so a failure below never blocks the dashboard.
    try:
        export_dashboard_tasks()
    except Exception:
        logger.exception("Dashboard export failed")

    events = collect_all_events()

    if not events:
        logger.warning("No events collected — nothing to sync.")
        return

    service = get_calendar_service()
    result: SyncResult = sync_all_events(service, events)

    logger.info(
        "Sync complete — Created: %d | Updated: %d | Skipped: %d | Errors: %d",
        result.created,
        result.updated,
        result.skipped,
        len(result.errors),
    )
    for err in result.errors:
        logger.error("  %s", err)

    if result.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
