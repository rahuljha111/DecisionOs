"""
Database configuration and models for DecisionOS.
PostgreSQL database with real MCP integration.
"""

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# PostgreSQL Database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./decisionos.db"
)

# Create engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """User model for tracking decision history."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    decisions = relationship("Decision", back_populates="user")
    events = relationship("CalendarEvent", back_populates="user")
    tasks = relationship("Task", back_populates="user")
    google_token = relationship("GoogleCalendarToken", back_populates="user", uselist=False)


class Decision(Base):
    """Decision records for audit and history."""
    __tablename__ = "decisions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    input_message = Column(Text, nullable=False)
    extracted_data = Column(Text)  # JSON string of planner output
    task_analysis = Column(Text)   # JSON string of task agent output
    calendar_result = Column(Text) # JSON string of calendar agent output
    scenarios = Column(Text)       # JSON string of scenario agent output
    final_decision = Column(Text)  # JSON string of decision engine output
    action_taken = Column(String(100))
    confidence_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="decisions")


class CalendarEvent(Base):
    """Calendar events managed by MCP tools."""
    __tablename__ = "calendar_events"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(String(100), unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(50), default="scheduled")  # scheduled, cancelled, rescheduled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="events")


class Task(Base):
    """Tasks managed by MCP tools."""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(String(100), unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    priority = Column(Integer, default=5)  # 1-10 scale
    urgency_score = Column(Float)
    importance_score = Column(Float)
    estimated_duration = Column(Float)  # hours
    deadline = Column(DateTime)
    status = Column(String(50), default="pending")  # pending, in_progress, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="tasks")


class GoogleCalendarToken(Base):
    """Per-user Google OAuth token storage."""
    __tablename__ = "google_calendar_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    token_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="google_token")


def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_or_create_user(db, user_id: str) -> User:
    """Get existing user or create new one."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        user = User(user_id=user_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
