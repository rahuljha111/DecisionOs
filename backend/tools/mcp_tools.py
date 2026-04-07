"""
MCP Tools for DecisionOS.
Primary: Google Calendar API (via stored OAuth tokens in DB).
Fallback: Events stored in local database table.

All calendar reads go through get_events_in_range().
All calendar writes go through execute_action().
"""

import os
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text as sql_text


# ─────────────────────────────────────────────
# GOOGLE CALENDAR IMPORT (optional — graceful fallback)
# ─────────────────────────────────────────────

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


class MCPTools:
    """
    Provides calendar read/write operations.
    Tries Google Calendar first; falls back to database events table.
    """

    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user_id = user_id

    # ─────────────────────────────────────────
    # PUBLIC: GET EVENTS IN TIME RANGE
    # ─────────────────────────────────────────

    def get_events_in_range(
        self,
        start: datetime,
        end: datetime
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Fetch calendar events between start and end.

        Returns:
            (events_list, source_string)
            source_string is 'google_calendar' or 'database'
        """
        # Try Google Calendar first
        if GOOGLE_AVAILABLE:
            creds = self._load_google_credentials()
            if creds:
                try:
                    events = self._fetch_google_calendar_events(creds, start, end)
                    return events, "google_calendar"
                except Exception as e:
                    print(f"[MCPTools] Google Calendar error: {e} — falling back to DB")

        # Fallback: local DB events table
        events = self._fetch_db_events(start, end)
        return events, "database"

    # ─────────────────────────────────────────
    # PUBLIC: EXECUTE CALENDAR ACTION
    # ─────────────────────────────────────────

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a calendar mutation action.

        Supported tools:
          - calendar_reschedule
          - calendar_cancel

        Args:
            action: dict with 'tool', 'event_id', optional 'suggested_time'

        Returns:
            Result dict with success flag and details
        """
        tool = action.get("tool", "")

        if tool == "calendar_reschedule":
            return self._reschedule_event(
                event_id=action.get("event_id"),
                new_time=action.get("suggested_time")
            )

        if tool == "calendar_cancel":
            return self._cancel_event(event_id=action.get("event_id"))

        return {"success": False, "error": f"Unknown tool: {tool}"}

    # ─────────────────────────────────────────
    # GOOGLE CALENDAR HELPERS
    # ─────────────────────────────────────────

    def _load_google_credentials(self) -> Optional["Credentials"]:
        """
        Load stored OAuth2 credentials for this user from the database.
        Expected table: user_tokens (user_id, token_json)
        """
        if not GOOGLE_AVAILABLE or self.db is None:
            return None

        try:
            row = self.db.execute(
                sql_text("SELECT token_json FROM user_tokens WHERE user_id = :uid LIMIT 1"),
                {"uid": self.user_id}
            ).fetchone()

            if not row:
                return None

            token_data = json.loads(row[0])
            creds = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.environ.get("GOOGLE_CLIENT_ID"),
                client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
                scopes=["https://www.googleapis.com/auth/calendar"]
            )
            return creds

        except Exception as e:
            print(f"[MCPTools] Failed to load credentials: {e}")
            return None

    def _fetch_google_calendar_events(
        self,
        creds: "Credentials",
        start: datetime,
        end: datetime
    ) -> List[Dict[str, Any]]:
        """Fetch events from Google Calendar API."""
        service = build("calendar", "v3", credentials=creds)

        # Convert to RFC3339 UTC strings
        time_min = _to_rfc3339(start)
        time_max = _to_rfc3339(end)

        result = service.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50
        ).execute()

        raw_events = result.get("items", [])
        return [_parse_google_event(e) for e in raw_events]

    def _reschedule_event(
        self,
        event_id: Optional[str],
        new_time: Optional[str]
    ) -> Dict[str, Any]:
        """Reschedule a Google Calendar event to new_time."""
        if not event_id or not new_time:
            return {"success": False, "error": "Missing event_id or new_time"}

        if GOOGLE_AVAILABLE:
            creds = self._load_google_credentials()
            if creds:
                try:
                    service = build("calendar", "v3", credentials=creds)
                    event = service.events().get(
                        calendarId="primary", eventId=event_id
                    ).execute()

                    # Parse new start time
                    new_start = datetime.fromisoformat(new_time.replace("Z", "+00:00"))
                    duration_ms = 3600000  # default 1h

                    old_start = event.get("start", {})
                    old_end = event.get("end", {})
                    if old_start.get("dateTime") and old_end.get("dateTime"):
                        s = datetime.fromisoformat(old_start["dateTime"])
                        e = datetime.fromisoformat(old_end["dateTime"])
                        duration_ms = int((e - s).total_seconds() * 1000)

                    new_end = new_start + timedelta(milliseconds=duration_ms)

                    event["start"] = {"dateTime": new_start.isoformat(), "timeZone": "UTC"}
                    event["end"] = {"dateTime": new_end.isoformat(), "timeZone": "UTC"}

                    updated = service.events().update(
                        calendarId="primary", eventId=event_id, body=event
                    ).execute()

                    return {
                        "success": True,
                        "event_id": event_id,
                        "new_start": new_start.isoformat(),
                        "source": "google_calendar"
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}

        # DB fallback
        return self._db_reschedule(event_id, new_time)

    def _cancel_event(self, event_id: Optional[str]) -> Dict[str, Any]:
        """Cancel / delete a Google Calendar event."""
        if not event_id:
            return {"success": False, "error": "Missing event_id"}

        if GOOGLE_AVAILABLE:
            creds = self._load_google_credentials()
            if creds:
                try:
                    service = build("calendar", "v3", credentials=creds)
                    service.events().delete(
                        calendarId="primary", eventId=event_id
                    ).execute()
                    return {"success": True, "event_id": event_id, "source": "google_calendar"}
                except Exception as e:
                    return {"success": False, "error": str(e)}

        return self._db_cancel(event_id)

    # ─────────────────────────────────────────
    # DATABASE FALLBACK HELPERS
    # ─────────────────────────────────────────

    def _fetch_db_events(
        self,
        start: datetime,
        end: datetime
    ) -> List[Dict[str, Any]]:
        """
        Fetch events from local `events` table as fallback.
        Table schema expected:
            event_id TEXT, user_id TEXT, title TEXT,
            start_time TIMESTAMP, end_time TIMESTAMP,
            duration_hours REAL
        """
        if self.db is None:
            return []

        try:
            rows = self.db.execute(
                sql_text("""
                    SELECT event_id, title, start_time, end_time, duration_hours
                    FROM events
                    WHERE user_id = :uid
                      AND start_time < :end
                      AND end_time   > :start
                    ORDER BY start_time
                """),
                {"uid": self.user_id, "start": start, "end": end}
            ).fetchall()

            return [
                {
                    "event_id": r[0],
                    "title": r[1],
                    "start_time": r[2],
                    "end_time": r[3],
                    "duration_hours": r[4] or 1.0,
                    "source": "database"
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[MCPTools] DB events fetch error: {e}")
            return []

    def _db_reschedule(self, event_id: str, new_time: str) -> Dict[str, Any]:
        """Reschedule event in local DB."""
        if self.db is None:
            return {"success": False, "error": "No DB connection"}
        try:
            new_start = datetime.fromisoformat(new_time)
            self.db.execute(
                sql_text("""
                    UPDATE events
                    SET start_time = :start,
                        end_time   = start_time + (end_time - start_time)
                    WHERE event_id = :eid
                """),
                {"start": new_start, "eid": event_id}
            )
            self.db.commit()
            return {"success": True, "event_id": event_id, "source": "database"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _db_cancel(self, event_id: str) -> Dict[str, Any]:
        """Delete event from local DB."""
        if self.db is None:
            return {"success": False, "error": "No DB connection"}
        try:
            self.db.execute(
                sql_text("DELETE FROM events WHERE event_id = :eid"),
                {"eid": event_id}
            )
            self.db.commit()
            return {"success": True, "event_id": event_id, "source": "database"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# PRIVATE UTILITIES
# ─────────────────────────────────────────────

def _to_rfc3339(dt: datetime) -> str:
    """Convert datetime to RFC3339 UTC string for Google Calendar API."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_google_event(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw Google Calendar event dict into our internal format."""
    start_raw = raw.get("start", {})
    end_raw = raw.get("end", {})

    start_str = start_raw.get("dateTime") or start_raw.get("date")
    end_str = end_raw.get("dateTime") or end_raw.get("date")

    start_dt = _parse_dt(start_str)
    end_dt = _parse_dt(end_str)

    duration_hours = 1.0
    if start_dt and end_dt:
        duration_hours = (end_dt - start_dt).total_seconds() / 3600

    return {
        "event_id": raw.get("id"),
        "title": raw.get("summary", "Untitled"),
        "start_time": start_dt,
        "end_time": end_dt,
        "duration_hours": round(duration_hours, 2),
        "location": raw.get("location"),
        "description": raw.get("description"),
        "source": "google_calendar"
    }


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string (with or without timezone) to naive UTC datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None