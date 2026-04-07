"""
Google Calendar MCP Integration for DecisionOS.

Provides OAuth 2.0 authentication and calendar operations.
Primary calendar source with PostgreSQL as fallback.
"""

import os
import json
import base64
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from backend.db.database import get_or_create_user, GoogleCalendarToken

logger = logging.getLogger(__name__)

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    logger.warning("Google Calendar API libraries not installed. Using DB fallback only.")


# OAuth 2.0 scopes - full calendar access
SCOPES = ['https://www.googleapis.com/auth/calendar']

# File paths for credentials
PROJECT_ROOT = Path(__file__).parent.parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"


def _running_in_cloud() -> bool:
    return bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_JOB"))


def _token_file_path() -> Path:
    # In Cloud Run, writable filesystem is ephemeral. Use /tmp.
    if _running_in_cloud():
        return Path("/tmp/token.json")
    return TOKEN_FILE


def _load_client_config() -> Optional[Dict[str, Any]]:
    """Load OAuth client config from env var or credentials file."""
    env_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if env_json:
        try:
            if env_json.startswith("{"):
                return json.loads(env_json)
            decoded = base64.b64decode(env_json).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            logger.exception("Failed to parse GOOGLE_CREDENTIALS_JSON")

    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load credentials.json")

    return None


class GoogleCalendarService:
    """
    Google Calendar service with OAuth 2.0 authentication.
    
    Authentication flow:
    1. Check for existing token.json
    2. If valid, use it
    3. If expired, refresh it
    4. If no token, start OAuth flow (opens browser)
    """
    
    def __init__(self):
        self.service = None
        self.authenticated = False
        self.error_message = None
        self._services_by_user: Dict[str, Any] = {}
        
    def _load_token_from_db(self, db: Session, user_id: str) -> Optional[str]:
        try:
            user = get_or_create_user(db, user_id)
            token_row = db.query(GoogleCalendarToken).filter(GoogleCalendarToken.user_id == user.id).first()
            return token_row.token_json if token_row else None
        except OperationalError:
            db.rollback()
            logger.warning("google_calendar_tokens table not available yet")
            return None

    def _save_token_to_db(self, db: Session, user_id: str, token_json: str) -> None:
        try:
            user = get_or_create_user(db, user_id)
            token_row = db.query(GoogleCalendarToken).filter(GoogleCalendarToken.user_id == user.id).first()
            if token_row:
                token_row.token_json = token_json
                token_row.updated_at = datetime.utcnow()
            else:
                token_row = GoogleCalendarToken(user_id=user.id, token_json=token_json)
                db.add(token_row)
            db.commit()
        except OperationalError:
            db.rollback()
            raise

    def authenticate(self, user_id: str = "system", db: Optional[Session] = None, interactive: bool = True) -> bool:
        """
        Authenticate with Google Calendar API.
        
        Returns:
            True if authentication successful, False otherwise
        """
        if not GOOGLE_API_AVAILABLE:
            self.error_message = "Google API libraries not installed"
            return False
            
        client_config = _load_client_config()
        if not client_config:
            self.error_message = (
                f"Google OAuth credentials not found. Provide credentials.json at {CREDENTIALS_FILE} "
                "or set GOOGLE_CREDENTIALS_JSON environment variable."
            )
            logger.warning(self.error_message)
            return False
        
        creds = None
        token_file = _token_file_path()
        
        # Load existing token
        if db is not None:
            token_json = self._load_token_from_db(db, user_id)
            if token_json:
                try:
                    creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
                except Exception as e:
                    logger.warning(f"Failed to load DB token for user {user_id}: {e}")
        elif token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load token: {e}")
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Google Calendar token refreshed")
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}")
                    creds = None
            
            if not creds:
                if not interactive:
                    self.error_message = "No token found. Connect Google Calendar via /api/calendar/auth"
                    return False
                if _running_in_cloud():
                    self.error_message = (
                        "Interactive desktop OAuth is not supported in Cloud Run. "
                        "Use /api/calendar/auth to start web OAuth flow."
                    )
                    return False
                try:
                    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                    # This will open a browser for OAuth consent
                    creds = flow.run_local_server(port=0)
                    logger.info("Google Calendar OAuth completed")
                except Exception as e:
                    self.error_message = f"OAuth flow failed: {e}"
                    logger.error(self.error_message)
                    return False
            
            # Save token for future use
            try:
                if db is not None:
                    self._save_token_to_db(db, user_id, creds.to_json())
                    logger.info(f"Token saved in DB for user {user_id}")
                else:
                    with open(token_file, 'w', encoding="utf-8") as token:
                        token.write(creds.to_json())
                    logger.info(f"Token saved to {token_file}")
            except Exception as e:
                logger.warning(f"Failed to save token: {e}")
        
        # Build service
        try:
            service = build('calendar', 'v3', credentials=creds)
            self.service = service
            self._services_by_user[user_id] = service
            self.authenticated = True
            logger.info("Google Calendar service initialized")
            return True
        except Exception as e:
            self.error_message = f"Failed to build service: {e}"
            logger.error(self.error_message)
            return False

    def get_auth_url(self, redirect_uri: str, user_id: str) -> Optional[str]:
        """Generate web OAuth URL for browser-based authentication."""
        if not GOOGLE_API_AVAILABLE:
            self.error_message = "Google API libraries not installed"
            return None

        client_config = _load_client_config()
        if not client_config:
            self.error_message = "Missing OAuth client config"
            return None

        try:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES, redirect_uri=redirect_uri)
            auth_url, _state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                state=user_id,
            )
            return auth_url
        except Exception as e:
            self.error_message = f"Failed to build auth URL: {e}"
            return None

    def complete_web_oauth(self, code: str, redirect_uri: str, user_id: str, db: Optional[Session] = None) -> bool:
        """Exchange auth code for token and initialize service."""
        if not GOOGLE_API_AVAILABLE:
            self.error_message = "Google API libraries not installed"
            return False

        client_config = _load_client_config()
        if not client_config:
            self.error_message = "Missing OAuth client config"
            return False

        try:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES, redirect_uri=redirect_uri)
            flow.fetch_token(code=code)
            creds = flow.credentials

            if db is not None:
                self._save_token_to_db(db, user_id, creds.to_json())
            else:
                token_file = _token_file_path()
                token_file.write_text(creds.to_json(), encoding="utf-8")

            service = build('calendar', 'v3', credentials=creds)
            self.service = service
            self._services_by_user[user_id] = service
            self.authenticated = True
            self.error_message = None
            return True
        except Exception as e:
            self.error_message = f"OAuth callback failed: {e}"
            logger.exception(self.error_message)
            return False
    
    def get_events(
        self,
        user_id: str = "system",
        db: Optional[Session] = None,
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 50,
        calendar_id: str = 'primary'
    ) -> List[Dict[str, Any]]:
        """
        Fetch events from Google Calendar.
        
        Args:
            time_min: Start of time window (default: now)
            time_max: End of time window (default: 24 hours from now)
            max_results: Maximum number of events to return
            calendar_id: Calendar ID (default: primary)
            
        Returns:
            List of event dictionaries
        """
        service = self._services_by_user.get(user_id)
        if service is None:
            if not self.authenticate(user_id=user_id, db=db):
                return []
            service = self._services_by_user.get(user_id, self.service)
        
        if time_min is None:
            time_min = datetime.now()
        if time_max is None:
            time_max = time_min + timedelta(hours=24)
        
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat() + 'Z' if time_min.tzinfo is None else time_min.isoformat(),
                timeMax=time_max.isoformat() + 'Z' if time_max.tzinfo is None else time_max.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            return [self._parse_google_event(e) for e in events]
            
        except HttpError as e:
            logger.error(f"Google Calendar API error: {e}")
            self.error_message = str(e)
            return []
        except Exception as e:
            logger.error(f"Error fetching events: {e}")
            self.error_message = str(e)
            return []
    
    def create_event(
        self,
        user_id: str,
        db: Optional[Session],
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        calendar_id: str = 'primary'
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new event in Google Calendar.
        
        Args:
            title: Event title/summary
            start_time: Event start datetime
            end_time: Event end datetime
            description: Optional event description
            calendar_id: Calendar ID (default: primary)
            
        Returns:
            Created event dict or None if failed
        """
        service = self._services_by_user.get(user_id)
        if service is None:
            if not self.authenticate(user_id=user_id, db=db):
                return None
            service = self._services_by_user.get(user_id, self.service)
        
        event_body = {
            'summary': title,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'UTC' if start_time.tzinfo is None else str(start_time.tzinfo),
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'UTC' if end_time.tzinfo is None else str(end_time.tzinfo),
            },
        }
        
        if description:
            event_body['description'] = description
        
        try:
            event = service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()
            
            logger.info(f"Created Google Calendar event: {event.get('id')}")
            return self._parse_google_event(event)
            
        except HttpError as e:
            logger.error(f"Failed to create event: {e}")
            self.error_message = str(e)
            return None
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            self.error_message = str(e)
            return None
    
    def update_event(
        self,
        user_id: str,
        db: Optional[Session],
        event_id: str,
        new_start_time: Optional[datetime] = None,
        new_end_time: Optional[datetime] = None,
        new_title: Optional[str] = None,
        calendar_id: str = 'primary'
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing Google Calendar event.
        
        Args:
            event_id: Google Calendar event ID
            new_start_time: New start time (optional)
            new_end_time: New end time (optional)
            new_title: New title (optional)
            calendar_id: Calendar ID
            
        Returns:
            Updated event dict or None if failed
        """
        service = self._services_by_user.get(user_id)
        if service is None:
            if not self.authenticate(user_id=user_id, db=db):
                return None
            service = self._services_by_user.get(user_id, self.service)
        
        try:
            # Get current event
            event = service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Update fields
            if new_title:
                event['summary'] = new_title
            
            if new_start_time:
                event['start'] = {
                    'dateTime': new_start_time.isoformat(),
                    'timeZone': 'UTC' if new_start_time.tzinfo is None else str(new_start_time.tzinfo),
                }
            
            if new_end_time:
                event['end'] = {
                    'dateTime': new_end_time.isoformat(),
                    'timeZone': 'UTC' if new_end_time.tzinfo is None else str(new_end_time.tzinfo),
                }
            
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            logger.info(f"Updated Google Calendar event: {event_id}")
            return self._parse_google_event(updated_event)
            
        except HttpError as e:
            logger.error(f"Failed to update event: {e}")
            self.error_message = str(e)
            return None
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            self.error_message = str(e)
            return None
    
    def delete_event(
        self,
        user_id: str,
        db: Optional[Session],
        event_id: str,
        calendar_id: str = 'primary'
    ) -> bool:
        """
        Delete (cancel) a Google Calendar event.
        
        Args:
            event_id: Google Calendar event ID
            calendar_id: Calendar ID
            
        Returns:
            True if deleted successfully, False otherwise
        """
        service = self._services_by_user.get(user_id)
        if service is None:
            if not self.authenticate(user_id=user_id, db=db):
                return False
            service = self._services_by_user.get(user_id, self.service)
        
        try:
            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            logger.info(f"Deleted Google Calendar event: {event_id}")
            return True
            
        except HttpError as e:
            logger.error(f"Failed to delete event: {e}")
            self.error_message = str(e)
            return False
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            self.error_message = str(e)
            return False
    
    def _parse_google_event(self, google_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Google Calendar event into standard format.
        
        Args:
            google_event: Raw Google Calendar event
            
        Returns:
            Standardized event dictionary
        """
        # Handle all-day events vs timed events
        start = google_event.get('start', {})
        end = google_event.get('end', {})
        
        start_time = self._parse_google_datetime(start)
        end_time = self._parse_google_datetime(end)
        
        # Calculate duration
        duration_hours = 0.0
        if start_time and end_time:
            duration_hours = (end_time - start_time).total_seconds() / 3600
        
        return {
            "event_id": google_event.get('id'),
            "google_id": google_event.get('id'),  # Keep original Google ID
            "title": google_event.get('summary', 'Untitled Event'),
            "description": google_event.get('description'),
            "start_time": start_time,
            "end_time": end_time,
            "duration_hours": round(duration_hours, 2),
            "status": google_event.get('status', 'confirmed'),
            "source": "google_calendar",
            "html_link": google_event.get('htmlLink'),
            "all_day": 'date' in start and 'dateTime' not in start
        }
    
    def _parse_google_datetime(self, dt_dict: Dict[str, str]) -> Optional[datetime]:
        """
        Parse Google Calendar datetime format.
        
        Handles both:
        - dateTime: "2024-01-15T10:00:00-05:00"
        - date: "2024-01-15" (all-day events)
        """
        if 'dateTime' in dt_dict:
            dt_str = dt_dict['dateTime']
            # Handle timezone offset
            try:
                # Try parsing with timezone
                if '+' in dt_str or dt_str.endswith('Z'):
                    dt_str = dt_str.replace('Z', '+00:00')
                    return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                return datetime.fromisoformat(dt_str)
            except ValueError:
                # Fallback: strip timezone and parse
                dt_str = dt_str.split('+')[0].split('-')[0] if 'T' in dt_str else dt_str
                try:
                    return datetime.fromisoformat(dt_str[:19])  # Trim to YYYY-MM-DDTHH:MM:SS
                except:
                    return None
        elif 'date' in dt_dict:
            # All-day event
            try:
                return datetime.strptime(dt_dict['date'], '%Y-%m-%d')
            except ValueError:
                return None
        return None


# Singleton instance
_google_calendar_service: Optional[GoogleCalendarService] = None


def get_google_calendar_service() -> GoogleCalendarService:
    """Get or create singleton Google Calendar service."""
    global _google_calendar_service
    if _google_calendar_service is None:
        _google_calendar_service = GoogleCalendarService()
    return _google_calendar_service


def is_google_calendar_available() -> bool:
    """Check if Google Calendar integration is available."""
    return GOOGLE_API_AVAILABLE and (_load_client_config() is not None)
