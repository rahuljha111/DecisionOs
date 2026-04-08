# 🎯 DecisionOS — AI That Simulates Before It Decides

A production-ready multi-agent AI decision engine that simulates scenarios before making actionable decisions. Unlike traditional chatbots, DecisionOS makes **ONE clear, decisive recommendation** per request, backed by data-driven analysis.

![DecisionOS Banner](https://img.shields.io/badge/DecisionOS-AI%20Decision%20Engine-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ⚡ Quick Start (Production)

**No setup needed! The app is live at:**
```
🌐 https://decisionos-837202638935.asia-south1.run.app
```

1. Open the URL in your browser
2. Enter tasks (e.g., "gym at 6pm", "interview at 7pm", "complete report")
3. Click **"Get Decision"**
4. View multi-agent analysis + Vertex AI ranking
5. Execute actions if desired

**No account required for demo!** (Optional OAuth for real calendar integration)

---

- [What is DecisionOS?](#-what-is-decisionos)
- [Key Features](#-key-features)
- [Architecture](#-architecture-overview)
- [Agent System](#-agent-system)
- [MCP Tools](#-mcp-tools)
- [Setup Instructions](#-setup-instructions)
- [Production Hardening](#-production-hardening)
- [How to Run](#-how-to-run)
- [Demo Example](#-demo-example)
- [API Reference](#-api-reference)
- [Tech Stack](#-tech-stack)
- [Future Improvements](#-future-improvements)

---

## 🤖 What is DecisionOS?

DecisionOS is a **multi-agent AI system** that helps you make better decisions by:

1. **Understanding** your situation (Planner Agent)
2. **Analyzing** priority and urgency (Task Agent)
3. **Checking** your real calendar for conflicts (Calendar Agent)
4. **Simulating** multiple scenarios with scores (Scenario Agent)
5. **Deciding** the best action with confidence (Decision Engine)
6. **Executing** actions via integrated tools (MCP Tools)

### Why is this different?

| Traditional Chatbot | DecisionOS |
|---------------------|------------|
| Gives suggestions | Makes decisions |
| Generic responses | Data-driven analysis |
| No real-world integration | Google Calendar + Database |
| Single-pass response | Multi-agent simulation |
| "You could try..." | "Skip the gym and focus on your exam" |

---

## ✨ Key Features

- **🧠 Multi-Agent Orchestration** - 5 specialized agents working together
- **🎲 Scenario Simulation** - Evaluates multiple options with scores
- **🧾 Scenario Recommendation Trace** - Shows all three scenario scores plus the recommendation and why it won
- **📅 Google Calendar Integration** - Real calendar data for conflict detection
- **⚡ Actionable Decisions** - Execute actions directly (cancel, reschedule events)
- **🔄 Real-time Streaming** - SSE-based live agent trace
- **💾 Decision History** - Learn from past decisions
- **🎯 Priority-based Conflict Resolution** - High priority tasks override low priority events

---

## 🏗 Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                       FRONTEND (HTML/JS)                              │
│            Multi-Agent Trace UI + Task Input                         │
│        https://decisionos-837202638935.asia-south1.run.app          │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ User submits: tasks + calendar context
┌──────────────────────────────────────────────────────────────────────┐
│                         FASTAPI BACKEND                               │
│           POST /api/prioritize_tasks (Primary Entry Point)            │
│              Running on: Google Cloud Run (asia-south1)               │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR (Backend)                              │
│     Coordinates multi-agent pipeline with Vertex AI decision          │
└──────────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   PLANNER AGENT  │ │   TASK AGENT     │ │  CALENDAR AGENT  │
│  (Analyze input) │ │ (Score urgency)  │ │ (Fetch Google    │
│                  │ │                  │ │  Calendar events)│
│ Extract task     │ │ Urgency: 0-10    │ │                  │
│ type & context   │ │ Importance: 0-10 │ │ MCP/DB fallback  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   SCENARIO SIMULATOR AGENT                            │
│            Generate 3 decision options with scores (0-100)            │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  DECISION ENGINE (Vertex AI)                          │
│        Gemini 2.5-Flash LLM: Rank tasks + return final decision       │
│   Returns: prioritized_tasks[], decision_text, reasoning              │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    MCP TOOLS (Execution Layer)                        │
│  POST /api/execute_action (Calendar: create, reschedule, cancel)     │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   PERSISTENT DATA LAYER                               │
│  PostgreSQL: Users, tokens, decisions, calendar events, tasks        │
│  Google Calendar API: Real-time calendar state                        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Agent System

The system uses a 5-step multi-agent pipeline that's **visible in the UI**:

### 1. 📋 Planner Agent
**Input:** Natural language task description  
**Output:** Structured task analysis (type, urgency keywords, constraints)

- Identifies task type (appointment, deadline, event, flexible activity)
- Extracts time windows and constraints
- Detects urgency keywords ("urgent", "asap", "deadline", "critical")
- Parses calendar event conflicts

### 2. 📊 Task Analyzer Agent  
**Input:** Structured task from Planner  
**Output:** Urgency score (0-10), Importance score (0-10)

- Calculates urgency: How soon must it be done?
- Calculates importance: What's the impact if skipped?
- Combined score influences final decision

### 3. 📅 Calendar Agent
**Input:** User ID, task details  
**Output:** Calendar events, conflicts, constraints

- Fetches real Google Calendar events (if authenticated)
- Falls back to PostgreSQL event database
- Detects time overlaps with 30-minute buffer
- Classifies events: fixed (appointments) vs flexible (tasks)

### 4. 🎲 Scenario Simulator Agent
**Input:** Tasks + calendar context  
**Output:** 3 decision scenarios with scores (0-100)

- Option 1: Recommended scenario (highest score)
- Option 2: Alternative scenario  
- Option 3: Rejected scenario (lowest score)
- Each scored based on priority conflicts and time constraints

### 5. 🧠 Decision Engine (Vertex AI)
**Input:** All task + scenario data  
**Output:** Final prioritized task list + reasoning

- Model: `google/gemini-2.5-flash` (Vertex AI, production)
- Selects highest-scoring scenario
- Generates strong, actionable language
- Returns in format: `{prioritized_tasks, decision, reason}`

---

## 🔧 MCP Tools

MCP (Model Context Protocol) Tools execute real-world calendar actions after decisions are made:

| Tool | Endpoint | Parameters | Purpose |
|------|----------|------------|---------|
| `create_event` | POST /api/execute_action | title, start_time, end_time, description | Create new calendar event |
| `reschedule_event` | POST /api/execute_action | event_id, new_start_time, new_end_time | Move event to different time |
| `cancel_event` | POST /api/execute_action | event_id | Delete/cancel event |
| `add_task` | POST /api/execute_action | title, description, priority, deadline | Add task to database |

**Implementation:**
- **Primary:** Google Calendar API (real-time when authenticated)
- **Fallback:** PostgreSQL database (local storage)
- **Sync:** Events synced between Google and DB on each request
- **Execution:** Called after user confirms decision + clicks action button

### Example Tool Execution

```bash
# Cancel a calendar event after decision
curl -X POST "https://decisionos-837202638935.asia-south1.run.app/api/execute_action" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001",
    "action_type": "cancel_event",
    "event_id": "google_event_abc123",
    "params": {}
  }'
```

---

## 🚀 Deployment

### Live Production Instance

**Application URL:** `https://decisionos-837202638935.asia-south1.run.app`

**Deployment Details:**
- Platform: Google Cloud Run
- Region: asia-south1  
- Timeout: 3600 seconds
- Revision: decisionos-00033-wmd
- Status: 100% traffic (production-ready)
- Auto-scaling: Enabled

**Make a Request to Production API:**

```bash
# Quick test
curl -X POST "https://decisionos-837202638935.asia-south1.run.app/api/health"

# Prioritize tasks (main endpoint)
curl -X POST "https://decisionos-837202638935.asia-south1.run.app/api/prioritize_tasks" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo","tasks":["task1","task2"]}'
```

### Deploy Locally or to Your Cloud

#### Local Deployment
```bash
# Requirements  
pip install -r requirements.txt

# Set environment variables
export VERTEX_AI_PROJECT=your-gcp-project
export VERTEX_AI_MODEL=google/gemini-2.5-flash
export GEMINI_API_KEY=your-api-key

# Start server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Access
open http://localhost:8000
```

#### Cloud Run Deployment
```bash
# Prerequisites: gcloud CLI, GCP project setup

# Deploy
gcloud run deploy decisionos \
  --source . \
  --region asia-south1 \
  --project your-project-id \
  --timeout 3600 \
  --set-env-vars VERTEX_AI_PROJECT=your-project-id,\
VERTEX_AI_MODEL=google/gemini-2.5-flash,\
VERTEX_AI_LOCATION=us-central1

# Verify
gcloud run services describe decisionos --region asia-south1

# View logs
gcloud run services logs read decisionos --region asia-south1 --limit 50
```

---

## ▶️ How to Run

### Live Production Deploy
Access the live instance:

```
🌐 Frontend: https://decisionos-837202638935.asia-south1.run.app
📌 API Base: https://decisionos-837202638935.asia-south1.run.app/api
```

The application is deployed on **Google Cloud Run** (asia-south1 region) with automatic scaling and 3600s timeout.

### Start the Backend Server Locally

```bash
# Development with auto-reload
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Production (local)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Access the Application

#### Local Testing
1. Open browser: `http://localhost:8000`
2. Enter your tasks in the text box
3. Click "Get Decision"
4. View the multi-agent trace (Planner → Task → Calendar → Scenario → Decision)
5. See Vertex AI prioritization result

#### Production Testing
1. Open: `https://decisionos-837202638935.asia-south1.run.app`
2. Same workflow as local (fully functional with live Google Calendar integration)

### Verify Calendar Integration (Local)

```bash
# Calendar status (OAuth check)
curl "http://127.0.0.1:8000/api/calendar/status?user_id=test_user"

# Calendar events for next 24 hours
curl "http://127.0.0.1:8000/api/calendar/events?user_id=test_user&hours=24"

# Health check
curl "http://127.0.0.1:8000/api/health"
```

---

## 🎮 Demo Example

### Scenario
A user has three items on their plate:
- **gym at 6:00 PM** - flexible, health activity
- **doctor appointment at 9:30 PM** - fixed-time, high priority
- **manager meeting at 10:30 PM** - fixed-time, work commitment
- **project report** - flexible deadline

### What Happens End-to-End

1. **Frontend** collects tasks and auto-injects calendar events
2. **POST /api/prioritize_tasks** is called with all items
3. **Backend Orchestrator** activates:
   - **Planner Agent** detects: doctor (critical), meeting (important), gym (flexible), report (important)
   - **Task Agent** scores: doctor health (10/10), meeting work (9/10), report work (8/10), gym (5/10)
   - **Calendar Agent** fetches real Google Calendar, finds doctor and meeting scheduled
   - **Scenario Agent** simulates 3 options with scores
4. **Vertex AI (Gemini 2.5-Flash)** selects final priority order
5. **Decision rendered** in UI with reasoning

### API Request (Direct)

```bash
curl -X POST "https://decisionos-837202638935.asia-south1.run.app/api/prioritize_tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_001",
    "tasks": [
        "gym at 6:00 PM",
        "doctor appointment at 9:30 PM",
        "manager meeting at 10:30 PM",
        "complete project report"
    ]
  }'
```

### AI Response

```json
{
    "prioritized_tasks": [
        "Attend doctor appointment at 9:30 PM",
        "Attend manager meeting at 10:30 PM",
        "complete project report",
        "gym at 6:00 PM"
    ],
    "decision": "Do Attend doctor appointment at 9:30 PM first, then Attend manager meeting at 10:30 PM.",
    "reason": "Fixed-time appointments are highest priority and must be attended at their scheduled times. The doctor appointment is earlier than the manager meeting. Gym is flexible and can be rescheduled if needed. Project report has a flexible deadline."
}
```

### Frontend Output Display

```
📊 Multi-Agent Trace:

▸ Planner: Identified 4 items (2 fixed appointments, 2 flexible)
  └─ Doctor appointment: CRITICAL (health)
  └─ Manager meeting: HIGH (commitment)
  └─ Project report: MEDIUM (work)
  └─ Gym: LOW (wellness)

▸ Task Analyzer: Scoring urgency and importance
  └─ Doctor: 97/100 (high priority + time constraint)  
  └─ Manager: 89/100 (work commitment + time constraint)
  └─ Report: 76/100 (work task + flexible)
  └─ Gym: 45/100 (wellness + flexible)

▸ Calendar Agent: Checking calendar conflicts
  └─ Found 2 calendar events (doctor, meeting)
  └─ No direct conflicts
  └─ All times confirmed

▸ Scenario Simulator: Evaluating options
  └─ Option 1: Do doctor, then meeting (Score: 96)
  └─ Option 2: Skip doctor (Score: 15) ❌ NOT RECOMMENDED
  └─ Option 3: Skip meeting (Score: 42) ❌ NOT RECOMMENDED

▸ Decision Engine (Vertex AI):
  ✅ RECOMMENDATION: Do Attend doctor appointment at 9:30 PM first, then Attend manager meeting at 10:30 PM.
  
  REASON: Fixed-time appointments are highest priority and must be attended at their scheduled times. The doctor appointment is earlier than the manager meeting. Gym is flexible and can be rescheduled if needed. Project report has a flexible deadline.
```

### Next Steps (Optional)

User can execute actions via the UI:
- **[❌ Cancel Gym]** - Remove from calendar
- **[⏰ Reschedule Gym]** - Move to tomorrow
- **[✅ Mark Completed]** - Complete report, then gym

---

## 📡 API Reference

### Production Endpoint

**Base URL (Production):**
```
https://decisionos-837202638935.asia-south1.run.app
```

**Base URL (Local Development):**
```
http://localhost:8000
```

### Primary Endpoints

| Method | Endpoint | Purpose | Response |
|--------|----------|---------|----------|
| **POST** | `/api/prioritize_tasks` | **Main Decision Endpoint** - Vertex AI prioritizes tasks with calendar context | `{prioritized_tasks: [], decision: string, reason: string}` |
| GET | `/api/health` | Service health check | `{status: "healthy", timestamp: ISO}` |
| GET | `/api/calendar/status?user_id=<id>` | Check OAuth status for user | `{authenticated: bool, has_credentials: bool}` |
| GET | `/api/calendar/events?user_id=<id>&hours=24` | Get upcoming calendar events | `{events: [{title, start_time, end_time}], fetched_at: ISO}` |
| GET | `/api/calendar/auth?user_id=<id>` | Initiate OAuth flow | Redirect to Google consent screen |
| GET | `/api/calendar/oauth/callback` | OAuth callback (auto-handled) | Session + token stored in database |

### Supporting Endpoints (Auxiliary)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/decide` | Legacy SSE streaming endpoint (use /prioritize_tasks instead) |
| POST | `/api/prioritize` | Build day plan from tasks + meetings (legacy) |
| POST | `/api/execute_action` | Execute calendar actions (create/reschedule/cancel event) |
| GET | `/api/decisions/{user_id}` | Get decision history for user |
| GET | `/api/decision/{decision_id}` | Get specific decision details |
| GET | `/api/events/{user_id}` | Get stored calendar events |
| POST | `/api/events/{user_id}` | Create new calendar event |
| GET | `/api/tasks/{user_id}` | Get task list |
| POST | `/api/tasks/{user_id}` | Create new task |
| GET | `/api/decisions/{user_id}/similar` | Find similar past decisions |

### Main Decision Endpoint - `/api/prioritize_tasks`

**Purpose:** Primary endpoint for Vertex AI task prioritization with calendar integration

**Request:**
```json
POST /api/prioritize_tasks
Content-Type: application/json

{
    "user_id": "user_001",
    "tasks": [
        "Complete project report",
        "Attend gym at 6 PM",
        "Interview at 7 PM"
    ]
}
```

**Response (Success):**
```json
{
    "prioritized_tasks": [
        "Interview at 7 PM",
        "Complete project report",
        "Attend gym at 6 PM"
    ],
    "decision": "Do Interview at 7 PM first, then Complete project report.",
    "reason": "Fixed-time appointment (Interview) is highest priority. Must attend at scheduled time. After interview, focus on project report. Gym is flexible and can be rescheduled."
}
```

**Response (No Calendar):**
```json
{
    "prioritized_tasks": [
        "Attend interview at 7 PM",
        "Complete project report",
        "Attend gym at 6 PM"
    ],
    "decision": "Attend interview and focus on project after.",
    "reason": "Fixed appointments take priority over flexible tasks."
}
```

### Execute Action Endpoint - `/api/execute_action`

**Purpose:** Execute calendar actions based on decision

**Request:**
```json
POST /api/execute_action
Content-Type: application/json

{
    "user_id": "user_001",
    "action_type": "cancel_event",
    "event_id": "event_12345",
    "params": {}
}
```

**Supported Actions:**
- `create_event` - Create new calendar event
- `reschedule_event` - Move event to different time
- `cancel_event` - Delete/cancel event
- `add_task` - Add task to database

**Response:**
```json
{
    "success": true,
    "action": "cancel_event",
    "message": "Event cancelled successfully",
    "event_id": "event_12345"
}
```

### Calendar Events Endpoint - `/api/calendar/events`

**Purpose:** Get upcoming calendar events for a user

**Request:**
```bash
GET /api/calendar/events?user_id=user_001&hours=24
```

**Parameters:**
- `user_id` (string): User identifier
- `hours` (integer, optional): Look-ahead window in hours (default: 24)

**Response:**
```json
{
    "events": [
        {
            "id": "event_123",
            "title": "Team Meeting",
            "start_time": "2026-04-08T14:00:00+00:00",
            "end_time": "2026-04-08T15:00:00+00:00",
            "description": "Weekly sync"
        },
        {
            "id": "event_456",
            "title": "Doctor Appointment",
            "start_time": "2026-04-08T21:30:00+00:00",
            "end_time": "2026-04-08T22:00:00+00:00",
            "description": "Annual checkup"
        }
    ],
    "user_id": "user_001",
    "fetched_at": "2026-04-08T12:00:00+00:00"
}
```

### Calendar Status Endpoint - `/api/calendar/status`

**Purpose:** Check if user has valid Google Calendar authentication

**Request:**
```bash
GET /api/calendar/status?user_id=user_001
```

**Response:**
```json
{
    "user_id": "user_001",
    "authenticated": true,
    "has_credentials": true,
    "oauth_flow_available": true,
    "next_step": "Ready to fetch events"
}
```

### Health Check Endpoint - `/api/health`

**Purpose:** Verify service is running and databases are accessible

**Request:**
```bash
GET /api/health
```

**Response:**
```json
{
    "status": "healthy",
    "timestamp": "2026-04-08T12:00:00Z",
    "services": {
        "api": "ok",
        "database": "ok",
        "vertex_ai": "ok"
    }
}
```

### Error Responses

All endpoints follow this error format:

```json
{
    "detail": "Error description",
    "status": 400,
    "error_code": "ERROR_CODE"
}
```

**Common Status Codes:**
- `200` - Success
- `400` - Bad request (missing/invalid parameters)
- `401` - Unauthorized (OAuth required)
- `404` - Resource not found
- `500` - Server error

---

## 🛠 Tech Stack

| Component | Technology | Version/Details |
|-----------|------------|-----------------|
| **Deployment** | Google Cloud Run | asia-south1 region, 3600s timeout |
| **Backend Framework** | FastAPI | 0.100+ |
| **LLM for Prioritization** | Vertex AI (Google Cloud) | `google/gemini-2.5-flash` |
| **LLM for Analysis** | Gemini API | `gemini-2.0-flash` |
| **Database** | PostgreSQL / SQLite | Production: PostgreSQL, Local: SQLite fallback |
| **ORM** | SQLAlchemy | 2.0+ |
| **Calendar Integration** | Google Calendar API | OAuth 2.0 PKCE flow, per-user tokens |
| **Frontend** | Vanilla JavaScript + CSS | No framework, lightweight |
| **Real-time** | Server-Sent Events (SSE) | For legacy `/api/decide` endpoint |
| **Authentication** | Google OAuth 2.0 | Web application flow for Cloud Run |
| **Async Runtime** | AsyncIO/Uvicorn | Production-grade async server |

### Environment Variables

**Required:**
```
VERTEX_AI_PROJECT=your-gcp-project-id
VERTEX_AI_MODEL=google/gemini-2.5-flash
VERTEX_AI_LOCATION=us-central1
GEMINI_API_KEY=your-gemini-api-key    # For legacy endpoints
```

**Optional:**
```
DATABASE_URL=postgresql://user:pwd@host:5432/decisionos
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
DECISIONOS_REQUIRE_AUTH=0
GOOGLE_CALENDAR_CLIENT_TYPE=web    # or "installed"
```

### Production Architecture

```
User Browser
     │
     ▼
Google Cloud Run (asia-south1)
  ├─ FastAPI App (decisionos-00033-wmd)
  ├─ Vertex AI Client (us-central1)
  ├─ PostgreSQL (Cloud SQL)
  └─ Google Calendar API
```

---

## 🔮 Future Improvements

- [ ] **Advanced Learning System** - Learn from user feedback
- [ ] **Multi-user Support** - Team decision making
- [ ] **More Integrations** - Slack, Todoist, Notion
- [ ] **Mobile App** - React Native client
- [ ] **Voice Input** - Speech-to-text integration
- [ ] **Decision Analytics** - Visualize decision patterns
- [ ] **Custom Agents** - User-defined agent workflows

---

## ✅ Production Validation

### Health Check
```bash
curl https://decisionos-837202638935.asia-south1.run.app/api/health
```

Expected response:
```json
{"status":"healthy","services":{"api":"ok","database":"ok","vertex_ai":"ok"}}
```

### Quick End-to-End Test
```bash
curl -X POST "https://decisionos-837202638935.asia-south1.run.app/api/prioritize_tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo",
    "tasks": ["gym", "doctor appointment at 9pm", "manager meeting at 10pm"]
  }' | python -m json.tool
```

### Local Regression Suite
```bash
python backend/tools/decision_regression_suite.py
```

This validates 15+ decision scenarios to ensure quality and specificity.

---

## 📊 Architecture Cleanup

**Removed/Deprecated:**
- ❌ `POST /api/decide` - Legacy SSE streaming (use `/api/prioritize_tasks`)
- ❌ `POST /api/prioritize` - Old day planner (use `/api/prioritize_tasks`)
- ❌ Local token.json storage - Now DB-based per-user tokens
- ❌ Installed OAuth flow - Now web-only for Cloud Run compatibility
- ❌ ai_engine/ (old directory) - Consolidated to ai-engine/

**Kept (Production Ready):**
- ✅ `POST /api/prioritize_tasks` - Main decision endpoint (Vertex AI backed)
- ✅ `GET/POST /api/calendar/*` - Calendar integration (OAuth, events, status)
- ✅ `POST /api/execute_action` - MCP tool execution
- ✅ Multi-agent trace UI - Real-time agent pipeline visualization
- ✅ PostgreSQL persistence - User tokens, events, decisions
- ✅ Google Cloud Run deployment - Production infrastructure

---

## 📁 Project Structure

```
DecisionOs/
├── README.md                        # This file
├── GOOGLE_CALENDAR_SETUP.md         # OAuth setup guide
├── LICENSE                          # MIT
├── requirements.txt                 # Python dependencies
├── Dockerfile                       # Container config for Cloud Run
│
├── backend/                         # FastAPI Backend
│   ├── main.py                      # App entry point
│   ├── routes.py                    # API endpoints (18 total)
│   ├── schemas.py                   # Pydantic request/response models
│   ├── db/
│   │   └── database.py              # SQLAlchemy models, PostgreSQL setup
│   └── tools/
│       ├── mcp_tools.py             # MCP tool implementations
│       ├── google_calendar.py       # OAuth flows, Calendar service
│       └── decision_regression_suite.py  # 15+ scenario tests
│
├── ai-engine/                       # Multi-Agent Orchestration
│   ├── orchestrator.py              # Main pipeline coordinator
│   ├── config/
│   │   └── defaults.py              # System defaults, priorities
│   ├── utils/
│   │   ├── helpers.py               # JSON parsing, utilities
│   │   └── time_resolver.py         # Time/date parsing
│   └── agents/
│       ├── planner_agent.py         # Task analysis agent
│       ├── task_agent.py            # Priority scoring agent
│       ├── calendar_agent.py        # Calendar constraint agent
│       ├── scenario_agent.py        # Scenario simulation agent
│       └── decision_engine.py       # Final Vertex AI decision agent
│
├── frontend/                        # Vanilla JS/CSS UI
│   ├── index.html                   # Main page
│   ├── app.js                       # Multi-agent trace UI logic
│   └── styles.css                   # Styling
│
├── credentials.example.json         # OAuth template (for reference)
├── credentials.json                 # Google OAuth credentials (not in git)
└── token.json                       # User tokens storage (not in git)
```

### Key Files by Purpose

**API & Routing:**
- `backend/main.py` - FastAPI app initialization, CORS setup
- `backend/routes.py` - All 18 endpoints (prioritize_tasks is main)

**Multi-Agent Logic:**
- `ai-engine/orchestrator.py` - Coordinates all agents
- `ai-engine/agents/*.py` - Individual agent implementations

**Database:**
- `backend/db/database.py` - User, Decision, CalendarEvent, Task models

**Calendar Integration:**
- `backend/tools/google_calendar.py` - OAuth and Calendar API
- `GOOGLE_CALENDAR_SETUP.md` - Setup instructions

**Frontend:**
- `frontend/app.js` - Single-page app with multi-agent trace rendering

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Powered by [Google Gemini](https://ai.google.dev/)
- Calendar integration via [Google Calendar API](https://developers.google.com/calendar)

---

**Made with ❤️ for the hackathon**
