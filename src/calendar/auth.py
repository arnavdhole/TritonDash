import os
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TOKEN_PATH = Path("config/token.json")
CREDENTIALS_PATH = Path("config/credentials.json")


def get_credentials() -> Credentials:
    """
    Load credentials from token.json (refresh if expired).
    On first run (no token.json), launches the browser OAuth flow.
    For automated nightly runs, token.json must already exist with a
    valid refresh token — run scripts/setup_oauth.py once to create it.
    """
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Google OAuth credentials not found at {CREDENTIALS_PATH}.\n"
                    "Download credentials.json from Google Cloud Console → "
                    "APIs & Services → Credentials."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return creds
