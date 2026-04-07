"""
Google Calendar MCP Integration for DecisionOS.

Provides OAuth 2.0 authentication and calendar operations.
Primary calendar source with PostgreSQL as fallback.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

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
        
    def authenticate(self) -> bool:
        """
        Authenticate with Google Calendar API.
        
        Returns:
            True if authentication successful, False otherwise
        """
        if not GOOGLE_API_AVAILABLE:
            self.error_message = "Google API libraries not installed"
            return False
            
        if not CREDENTIALS_FILE.exists():
            self.error_message = f"credentials.json not found at {CREDENTIALS_FILE}"
            logger.warning(self.error_message)
            return False
        
        creds = None
        
        # Load existing token
        if TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
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
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(CREDENTIALS_FILE), SCOPES
                    )
                    # This will open a browser for OAuth consent
                    creds = flow.run_local_server(port=0)
                    logger.info("Google Calendar OAuth completed")
                except Exception as e:
                    self.error_message = f"OAuth flow failed: {e}"
                    logger.error(self.error_message)
                    return False
            
            # Save token for future use
            try:
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"Token saved to {TOKEN_FILE}")
            except Exception as e:
                logger.warning(f"Failed to save token: {e}")
        
        # Build service
        try:
            self.service = build('calendar', 'v3', credentials=creds)
            self.authenticated = True
            logger.info("Google Calendar service initialized")
            return True
        except Exception as e:
            self.error_message = f"Failed to build service: {e}"
            logger.error(self.error_message)
            return False
    
    def get_events(
        self,
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
        if not self.authenticated:
            if not self.authenticate():
                return []
        
        if time_min is None:
            time_min = datetime.utcnow()
        if time_max is None:
            time_max = time_min + timedelta(hours=24)
        
        try:
            events_result = self.service.events().list(
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
        if not self.authenticated:
            if not self.authenticate():
                return None
        
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
            event = self.service.events().insert(
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
        if not self.authenticated:
            if not self.authenticate():
                return None
        
        try:
            # Get current event
            event = self.service.events().get(
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
            
            updated_event = self.service.events().update(
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
        if not self.authenticated:
            if not self.authenticate():
                return False
        
        try:
            self.service.events().delete(
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
    return GOOGLE_API_AVAILABLE and CREDENTIALS_FILE.exists()
