"""
MCP-style tools for DecisionOS.
These tools execute actions - they contain NO decision intelligence.
REAL database integration for calendar and task management.
Google Calendar as PRIMARY source, PostgreSQL as FALLBACK.
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging

from sqlalchemy.orm import Session

from backend.db.database import CalendarEvent, Task, get_or_create_user
from backend.tools.google_calendar import (
    get_google_calendar_service,
    is_google_calendar_available,
    GoogleCalendarService
)

logger = logging.getLogger(__name__)


class MCPTools:
    """
    MCP-style tools for calendar and task management.
    
    Google Calendar is PRIMARY source.
    PostgreSQL database is FALLBACK.
    
    All tools write to both Google Calendar and DB for sync.
    Tools execute only - no intelligence or decision-making.
    """
    
    def __init__(self, db: Session, user_id: str):
        self.db = db
        self.user = get_or_create_user(db, user_id)
        self.google_calendar = get_google_calendar_service() if is_google_calendar_available() else None
        self._google_authenticated = False
        
    def _ensure_google_auth(self) -> bool:
        """Ensure Google Calendar is authenticated."""
        if not self.google_calendar:
            return False
        if not self._google_authenticated:
            self._google_authenticated = self.google_calendar.authenticate(
                user_id=self.user.user_id,
                db=self.db,
                interactive=False,
            )
        return self._google_authenticated
    
    def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new calendar event.
        Creates in Google Calendar first, then syncs to DB.
        
        Args:
            title: Event title
            start_time: Event start datetime
            end_time: Event end datetime
            description: Optional event description
            
        Returns:
            Dictionary with event details and status
        """
        google_event = None
        google_id = None
        source = "database"
        
        # Try Google Calendar first
        if self._ensure_google_auth():
            google_event = self.google_calendar.create_event(
                user_id=self.user.user_id,
                db=self.db,
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=description
            )
            if google_event:
                google_id = google_event.get("google_id")
                source = "google_calendar"
                logger.info(f"Created event in Google Calendar: {google_id}")
        
        # Create in database (always for sync)
        event_id = google_id or f"evt_{uuid.uuid4().hex[:12]}"
        
        event = CalendarEvent(
            user_id=self.user.id,
            event_id=event_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            status="scheduled"
        )
        
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        
        return {
            "success": True,
            "action": "create_event",
            "event_id": event_id,
            "google_id": google_id,
            "title": title,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "source": source,
            "message": f"Created event '{title}' from {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')}"
        }
    
    def reschedule_event(
        self,
        event_id: str,
        new_start_time: datetime,
        new_end_time: datetime
    ) -> Dict[str, Any]:
        """
        Reschedule an existing calendar event.
        Updates Google Calendar first, then syncs to DB.
        
        Args:
            event_id: ID of the event to reschedule
            new_start_time: New start datetime
            new_end_time: New end datetime
            
        Returns:
            Dictionary with rescheduling result
        """
        source = "database"
        google_updated = False
        
        # Try Google Calendar first
        if self._ensure_google_auth():
            result = self.google_calendar.update_event(
                user_id=self.user.user_id,
                db=self.db,
                event_id=event_id,
                new_start_time=new_start_time,
                new_end_time=new_end_time
            )
            if result:
                google_updated = True
                source = "google_calendar"
                logger.info(f"Updated event in Google Calendar: {event_id}")
        
        # Update in database
        event = self.db.query(CalendarEvent).filter(
            CalendarEvent.event_id == event_id,
            CalendarEvent.user_id == self.user.id
        ).first()
        
        if not event and not google_updated:
            return {
                "success": False,
                "action": "reschedule_event",
                "event_id": event_id,
                "message": f"Event '{event_id}' not found"
            }
        
        if event:
            old_start = event.start_time
            event.start_time = new_start_time
            event.end_time = new_end_time
            event.status = "rescheduled"
            event.updated_at = datetime.now()
            self.db.commit()
        else:
            old_start = new_start_time  # Can't determine original time
        
        return {
            "success": True,
            "action": "reschedule_event",
            "event_id": event_id,
            "title": event.title if event else "Unknown",
            "old_time": old_start.isoformat(),
            "new_start_time": new_start_time.isoformat(),
            "new_end_time": new_end_time.isoformat(),
            "source": source,
            "google_updated": google_updated,
            "message": f"Rescheduled event to {new_start_time.strftime('%H:%M')}"
        }
    
    def cancel_event(self, event_id: str) -> Dict[str, Any]:
        """
        Cancel a calendar event.
        Deletes from Google Calendar, marks cancelled in DB.
        
        Args:
            event_id: ID of the event to cancel
            
        Returns:
            Dictionary with cancellation result
        """
        source = "database"
        google_deleted = False
        
        # Try Google Calendar first
        if self._ensure_google_auth():
            if self.google_calendar.delete_event(user_id=self.user.user_id, db=self.db, event_id=event_id):
                google_deleted = True
                source = "google_calendar"
                logger.info(f"Deleted event from Google Calendar: {event_id}")
        
        # Update in database (mark as cancelled, don't delete)
        event = self.db.query(CalendarEvent).filter(
            CalendarEvent.event_id == event_id,
            CalendarEvent.user_id == self.user.id
        ).first()
        
        if not event and not google_deleted:
            return {
                "success": False,
                "action": "cancel_event",
                "event_id": event_id,
                "message": f"Event '{event_id}' not found"
            }
        
        event_title = "Unknown"
        if event:
            event_title = event.title
            event.status = "cancelled"
            event.updated_at = datetime.now()
            self.db.commit()
        
        return {
            "success": True,
            "action": "cancel_event",
            "event_id": event_id,
            "title": event_title,
            "source": source,
            "google_deleted": google_deleted,
            "message": f"Cancelled event '{event_title}'"
        }
    
    def add_task(
        self,
        title: str,
        description: Optional[str] = None,
        priority: int = 5,
        deadline: Optional[datetime] = None,
        estimated_duration: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Add a new task.
        
        Args:
            title: Task title
            description: Optional task description
            priority: Priority level 1-10
            deadline: Optional deadline datetime
            estimated_duration: Estimated hours to complete
            
        Returns:
            Dictionary with task details
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        
        task = Task(
            user_id=self.user.id,
            task_id=task_id,
            title=title,
            description=description,
            priority=priority,
            deadline=deadline,
            estimated_duration=estimated_duration,
            status="pending"
        )
        
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        
        return {
            "success": True,
            "action": "add_task",
            "task_id": task_id,
            "title": title,
            "priority": priority,
            "deadline": deadline.isoformat() if deadline else None,
            "message": f"Added task '{title}' with priority {priority}"
        }
    
    def get_upcoming_events(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get upcoming events within the specified time window.
        
        Args:
            hours: Number of hours to look ahead
            
        Returns:
            Dictionary with list of upcoming events
        """
        now = datetime.now()
        end_window = now + timedelta(hours=hours)
        
        events = self.db.query(CalendarEvent).filter(
            CalendarEvent.user_id == self.user.id,
            CalendarEvent.start_time >= now,
            CalendarEvent.start_time <= end_window,
            CalendarEvent.status != "cancelled"
        ).order_by(CalendarEvent.start_time).all()
        
        event_list = [
            {
                "event_id": e.event_id,
                "title": e.title,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "status": e.status
            }
            for e in events
        ]
        
        return {
            "success": True,
            "action": "get_upcoming_events",
            "events": event_list,
            "count": len(event_list),
            "message": f"Found {len(event_list)} upcoming events in the next {hours} hours"
        }
    
    def get_events_in_range(
        self, 
        start_time: datetime, 
        end_time: datetime
    ) -> tuple:
        """
        Get all active events within a specific time range.
        Uses Google Calendar as PRIMARY source, DB as FALLBACK.
        
        Args:
            start_time: Start of range
            end_time: End of range
            
        Returns:
            Tuple of (List of event dictionaries, source string)
        """
        source = "database"
        events = []
        
        # Try Google Calendar first
        if self._ensure_google_auth():
            google_events = self.google_calendar.get_events(
                user_id=self.user.user_id,
                db=self.db,
                time_min=start_time,
                time_max=end_time
            )
            if google_events:
                source = "google_calendar"
                events = google_events
                logger.info(f"Fetched {len(events)} events from Google Calendar")
                
                # Sync to database for backup
                self._sync_google_events_to_db(google_events)
        
        # Fallback to database if Google Calendar failed or no events
        if not events:
            logger.info("Using database fallback for events")
            db_events = self.db.query(CalendarEvent).filter(
                CalendarEvent.user_id == self.user.id,
                CalendarEvent.status.in_(["scheduled", "rescheduled"]),
                CalendarEvent.start_time < end_time,
                CalendarEvent.end_time > start_time
            ).order_by(CalendarEvent.start_time).all()
            
            events = [
                {
                    "event_id": e.event_id,
                    "title": e.title,
                    "start_time": e.start_time,
                    "end_time": e.end_time,
                    "duration_hours": (e.end_time - e.start_time).total_seconds() / 3600,
                    "status": e.status,
                    "source": "database"
                }
                for e in db_events
            ]
            source = "database"
        
        return events, source
    
    def _sync_google_events_to_db(self, google_events: List[Dict[str, Any]]) -> None:
        """
        Sync Google Calendar events to local database for backup.
        
        Args:
            google_events: List of events from Google Calendar
        """
        for g_event in google_events:
            event_id = g_event.get("event_id") or g_event.get("google_id")
            if not event_id:
                continue
            
            # Check if event exists
            existing = self.db.query(CalendarEvent).filter(
                CalendarEvent.event_id == event_id,
                CalendarEvent.user_id == self.user.id
            ).first()
            
            start_time = g_event.get("start_time")
            end_time = g_event.get("end_time")
            
            if existing:
                # Update existing event
                existing.title = g_event.get("title", existing.title)
                if start_time:
                    existing.start_time = start_time
                if end_time:
                    existing.end_time = end_time
                existing.status = "scheduled" if g_event.get("status") == "confirmed" else g_event.get("status", existing.status)
                existing.updated_at = datetime.now()
            else:
                # Create new event
                if start_time and end_time:
                    new_event = CalendarEvent(
                        user_id=self.user.id,
                        event_id=event_id,
                        title=g_event.get("title", "Google Event"),
                        description=g_event.get("description"),
                        start_time=start_time,
                        end_time=end_time,
                        status="scheduled"
                    )
                    self.db.add(new_event)
        
        try:
            self.db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync events to DB: {e}")
            self.db.rollback()
    
    def get_all_active_events(self) -> List[Dict[str, Any]]:
        """
        Get all active (non-cancelled) events for the user.
        Used for debugging and full calendar view.
        
        Returns:
            List of all active events
        """
        events = self.db.query(CalendarEvent).filter(
            CalendarEvent.user_id == self.user.id,
            CalendarEvent.status != "cancelled"
        ).order_by(CalendarEvent.start_time).all()
        
        return [
            {
                "event_id": e.event_id,
                "title": e.title,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "duration_hours": (e.end_time - e.start_time).total_seconds() / 3600,
                "status": e.status
            }
            for e in events
        ]
    
    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an MCP action based on action dictionary.
        
        Args:
            action: Dictionary with 'tool' and 'params' keys
            
        Returns:
            Result of the tool execution
        """
        tool_name = action.get("tool", "")
        params = action.get("params", {})
        
        tool_map = {
            "create_event": self.create_event,
            "reschedule_event": self.reschedule_event,
            "cancel_event": self.cancel_event,
            "add_task": self.add_task,
            "get_upcoming_events": self.get_upcoming_events
        }
        
        if tool_name not in tool_map:
            return {
                "success": False,
                "action": tool_name,
                "message": f"Unknown tool: {tool_name}"
            }
        
        # Convert datetime strings to datetime objects
        for key in ["start_time", "end_time", "new_start_time", "new_end_time", "deadline"]:
            if key in params and isinstance(params[key], str):
                try:
                    params[key] = datetime.fromisoformat(params[key].replace("Z", "+00:00"))
                except ValueError:
                    pass
        
        try:
            return tool_map[tool_name](**params)
        except Exception as e:
            return {
                "success": False,
                "action": tool_name,
                "message": f"Error executing {tool_name}: {str(e)}"
            }
