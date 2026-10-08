from googleapiclient.discovery import build
from src.calendar.auth import get_credentials


def get_calendar_service():
    """Build and return an authorized Google Calendar API service."""
    creds = get_credentials()
    return build("calendar", "v3", credentials=creds)
