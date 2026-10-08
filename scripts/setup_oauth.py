#!/usr/bin/env python3
"""
One-time interactive Google OAuth setup.

Run this ONCE from the project root before the first nightly sync:
    python scripts/setup_oauth.py

A browser window will open. Sign in with your Google account and grant
calendar access. When done, config/token.json is written and all subsequent
automated runs will use the stored refresh token.
"""
import sys
from pathlib import Path

# Allow running as a script from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

from src.calendar.auth import get_credentials, TOKEN_PATH, CREDENTIALS_PATH


def main() -> None:
    print("=== CanvasCalendar — Google OAuth Setup ===\n")

    if not CREDENTIALS_PATH.exists():
        print(f"ERROR: {CREDENTIALS_PATH} not found.\n")
        print("Steps to get it:")
        print("  1. Go to https://console.cloud.google.com")
        print("  2. Create a project → Enable 'Google Calendar API'")
        print("  3. APIs & Services → Credentials → Create OAuth client ID")
        print("     (Application type: Desktop app)")
        print("  4. Download JSON → rename to credentials.json → place in config/")
        sys.exit(1)

    if TOKEN_PATH.exists():
        print(f"token.json already exists at {TOKEN_PATH}.")
        answer = input("Re-run OAuth flow and overwrite it? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return
        TOKEN_PATH.unlink()

    print("Opening browser for Google OAuth...")
    print("(Sign in and click 'Allow' to grant calendar access)\n")
    creds = get_credentials()
    print(f"\nSuccess! Credentials saved to {TOKEN_PATH}")
    print("\nYou can now run the sync:")
    print("    python -m src.main")


if __name__ == "__main__":
    main()
