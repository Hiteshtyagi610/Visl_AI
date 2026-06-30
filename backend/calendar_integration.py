"""
Google Calendar Integration — real OAuth2 flow + automatic Google Meet
link generation, as explicitly required by the assignment ("Real Google
Calendar integration is required").

Flow:
  1. Recruiter visits /api/google/auth-url, logs into Google, grants access
  2. Google redirects to /api/google/oauth2callback?code=...
  3. We exchange the code for tokens and store them (DB, for simplicity)
  4. schedule_interview_for_candidate() then creates real Calendar events
     with conferenceData set to auto-generate a Meet link, and invites
     the candidate as an attendee (they get a real Google Calendar invite).

Requires a Google Cloud project with the Calendar API enabled and OAuth
2.0 Client ID credentials (Web application type). See setup steps provided
separately — this code assumes:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI env vars
"""

import os
import json
import uuid
from datetime import datetime, timedelta

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request as GoogleRequest

from db import get_conn

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/google/oauth2callback")

CLIENT_CONFIG = {
    "web": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [REDIRECT_URI],
    }
}


def get_auth_url() -> str:
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return auth_url


def handle_oauth_callback(code: str):
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=code)
    creds = flow.credentials

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    conn = get_conn()
    conn.execute("DELETE FROM google_tokens")
    conn.execute("INSERT INTO google_tokens (token_json) VALUES (?)", (json.dumps(token_data),))
    conn.commit()
    conn.close()


def _get_credentials() -> Credentials | None:
    conn = get_conn()
    row = conn.execute("SELECT token_json FROM google_tokens ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return None

    data = json.loads(row[0])
    creds = Credentials(
        token=data["token"],
        refresh_token=data["refresh_token"],
        token_uri=data["token_uri"],
        client_id=data["client_id"],
        client_secret=data["client_secret"],
        scopes=data["scopes"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleRequest())
    return creds


def schedule_interview_for_candidate(s_no: int, name: str, email: str, slot_offset: int = 0, start_hour: int = 11) -> dict:
    """Creates a real Calendar event with an auto-generated Meet link,
    starting tomorrow at start_hour, each candidate offset by 30 minutes."""
    creds = _get_credentials()
    if creds is None:
        return {"s_no": s_no, "status": "failed", "reason": "Google account not connected"}

    service = build("calendar", "v3", credentials=creds)

    start_time = (datetime.utcnow() + timedelta(days=1)).replace(
        hour=start_hour, minute=0, second=0, microsecond=0
    ) + timedelta(minutes=30 * slot_offset)
    end_time = start_time + timedelta(minutes=30)

    event_body = {
        "summary": f"Interview: {name} — Visl AI Labs",
        "description": "Automatically scheduled interview based on AI screening results.",
        "start": {"dateTime": start_time.isoformat() + "Z"},
        "end": {"dateTime": end_time.isoformat() + "Z"},
        "attendees": [{"email": email}],
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    try:
        event = service.events().insert(
            calendarId="primary", body=event_body, conferenceDataVersion=1, sendUpdates="all"
        ).execute()

        meet_link = event.get("hangoutLink", "")
        conn = get_conn()
        conn.execute(
            "INSERT INTO interviews (s_no, name, email, meet_link, event_id, scheduled_time) VALUES (?, ?, ?, ?, ?, ?)",
            (s_no, name, email, meet_link, event.get("id"), start_time.isoformat()),
        )
        conn.commit()
        conn.close()

        return {"s_no": s_no, "status": "scheduled", "meet_link": meet_link, "time": start_time.isoformat()}
    except Exception as e:
        return {"s_no": s_no, "status": "failed", "reason": str(e)}
