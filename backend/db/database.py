"""
Database layer for DecisionOS.
Uses SQLAlchemy with PostgreSQL (Cloud SQL) or SQLite fallback for local dev.

Tables:
  - users           : registered users
  - decisions       : decision pipeline records
  - events          : calendar events fallback store
  - user_tokens     : stored Google OAuth2 tokens
"""

import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Text,
    Float, DateTime, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import text as sql_text
from datetime import datetime
from typing import Generator

# ─────────────────────────────────────────────
# ENGINE SETUP
# ─────────────────────────────────────────────

def _build_database_url() -> str:
    """
    Build DB URL from environment variables.
    Priority:
      1. DATABASE_URL (full connection string — set this in Cloud Run secrets)
      2. SQLite local file (for development only)
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        # Cloud SQL via Unix socket uses postgresql+pg8000 driver
        # Example: postgresql+pg8000://user:pass@/dbname?unix_sock=/cloudsql/...
        return url
    # Local development fallback
    return "sqlite:///./decisionos.db"


DATABASE_URL = _build_database_url()

# connect_args only needed for SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,      # detect stale connections
    pool_recycle=300,        # recycle connections every 5 min (Cloud SQL)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id          = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), unique=True, index=True, nullable=False)
    email       = Column(String(255), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)


class Decision(Base):
    __tablename__ = "decisions"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=False)
    input_message    = Column(Text,    nullable=False)
    extracted_data   = Column(Text,    nullable=True)   # JSON
    task_analysis    = Column(Text,    nullable=True)   # JSON
    calendar_result  = Column(Text,    nullable=True)   # JSON
    scenarios        = Column(Text,    nullable=True)   # JSON
    final_decision   = Column(Text,    nullable=True)   # JSON
    action_taken     = Column(String(100), nullable=True)
    confidence_score = Column(Float,   nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)


class Event(Base):
    """
    Local calendar event storage — used when Google Calendar is unavailable.
    """
    __tablename__ = "events"

    id             = Column(Integer, primary_key=True, index=True)
    event_id       = Column(String(255), unique=True, nullable=False)
    user_id        = Column(String(255), nullable=False, index=True)
    title          = Column(String(500), nullable=False)
    start_time     = Column(DateTime, nullable=False)
    end_time       = Column(DateTime, nullable=False)
    duration_hours = Column(Float,    nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)


class UserToken(Base):
    """
    Stores Google OAuth2 tokens per user.
    token_json is a JSON string: {token, refresh_token, ...}
    """
    __tablename__ = "user_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(String(255), unique=True, nullable=False, index=True)
    token_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─────────────────────────────────────────────
# INITIALIZATION
# ─────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they don't exist. Call once at startup."""
    Base.metadata.create_all(bind=engine)


# ─────────────────────────────────────────────
# DEPENDENCY: FastAPI session generator
# ─────────────────────────────────────────────

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request.
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────

def get_or_create_user(db: Session, external_id: str) -> User:
    """
    Fetch existing user by external_id, or create one.

    Args:
        db: Active SQLAlchemy session
        external_id: String identifier from the frontend (e.g. 'test_user')

    Returns:
        User ORM object
    """
    user = db.query(User).filter(User.external_id == external_id).first()
    if not user:
        user = User(external_id=external_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user