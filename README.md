# 🎯 DecisionOS — AI That Simulates Before It Decides

A production-ready multi-agent AI decision engine that simulates scenarios before making actionable decisions. Unlike traditional chatbots, DecisionOS makes **ONE clear, decisive recommendation** per request, backed by data-driven analysis.

![DecisionOS Banner](https://img.shields.io/badge/DecisionOS-AI%20Decision%20Engine-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 📋 Table of Contents

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
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                               │
│              "I have exam at 7pm and gym at 6pm"                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         FASTAPI                                  │
│                    POST /api/decide                              │
│                   (SSE Streaming)                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR                                │
│              Coordinates the agent pipeline                      │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   PLANNER     │   │    TASK       │   │   CALENDAR    │
│    AGENT      │   │    AGENT      │   │    AGENT      │
│  (LLM/Rules)  │   │  (Rule-based) │   │ (Rule-based)  │
│               │   │               │   │               │
│ Extract task  │   │ Score urgency │   │ Check Google  │
│ and context   │   │ & importance  │   │ Calendar      │
└───────────────┘   └───────────────┘   └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                    ┌───────────────┐
                    │   SCENARIO    │
                    │    AGENT      │
                    │    (Hybrid)   │
                    │               │
                    │ Simulate 3    │
                    │ options with  │
                    │ scores        │
                    └───────────────┘
                              │
                              ▼
                    ┌───────────────┐
                    │   DECISION    │
                    │    ENGINE     │
                    │   (LLM/Rules) │
                    │               │
                    │ Select best   │
                    │ option        │
                    └───────────────┘
                              │
                              ▼
                    ┌───────────────┐
                    │   MCP TOOLS   │
                    │               │
                    │ Execute:      │
                    │ - Cancel      │
                    │ - Reschedule  │
                    │ - Create      │
                    └───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DATABASE                                  │
│              PostgreSQL / SQLite + Google Calendar               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🤖 Agent System

### 1. 📋 Planner Agent
**Purpose:** Extract structured information from natural language input.

- Identifies task type (exam, deadline, meeting)
- Extracts time constraints
- Detects urgency keywords
- Falls back to rule-based parsing if LLM fails

### 2. 📊 Task Agent (Rule-based)
**Purpose:** Analyze task priority and urgency.

- Calculates urgency score (0-10)
- Calculates importance score (0-10)
- Determines overall priority
- Uses system defaults for duration estimates

### 3. 📅 Calendar Agent (Rule-based)
**Purpose:** Check calendar for conflicts.

- Fetches real events from Google Calendar
- Detects time overlaps with 30-minute buffer
- Classifies event priority (high/medium/low)
- Generates alternatives (attend, skip, reschedule)

### 4. 🎲 Scenario Agent (Hybrid)
**Purpose:** Simulate decision options with scores.

- Generates exactly 3 scenarios
- Scores each option (0-100)
- Applies hard penalties for priority conflicts
- Uses LLM for rich descriptions, rules for scoring

### 5. 🧠 Decision Engine (Hybrid)
**Purpose:** Synthesize final decision.

- Selects highest scoring option
- Generates strong, actionable language
- Validates against priority rules
- Returns executable actions

---

## 🔧 MCP Tools

MCP (Model Context Protocol) Tools execute real-world actions:

| Tool | Description | Parameters |
|------|-------------|------------|
| `create_event` | Create calendar event | title, start_time, end_time, description |
| `reschedule_event` | Move event to new time | event_id, new_start_time, new_end_time |
| `cancel_event` | Cancel/delete event | event_id |
| `add_task` | Add a task to database | title, description, priority, deadline |

**Integration:**
- Primary: Google Calendar API
- Fallback: PostgreSQL database
- Sync: Events are synced between both

---

## 🚀 Setup Instructions

## ✅ Production Hardening

The project now includes production-safe Google Calendar integration for Cloud Run and multi-user scenarios:

- Per-user OAuth token storage in database (instead of shared local token file)
- PKCE-safe OAuth callback handling across redirect round-trips
- Web OAuth client flow aligned for Cloud Run callback URLs
- Calendar event fetch endpoint honors requested time window (`hours`)
- Production smoke test script for health + calendar status + events response

Quick validation command:

```bash
.venv\Scripts\python.exe smoke_test_calendar_prod.py
```

Strict mode (requires authenticated test user):

```bash
set DECISIONOS_REQUIRE_AUTH=1
set DECISIONOS_USER_ID=your_user_id
.venv\Scripts\python.exe smoke_test_calendar_prod.py
```

## ✅ Production Regression Check

Run the decision regression suite (15 user scenarios + extra edge cases):

```bash
.venv\Scripts\python.exe backend/tools/decision_regression_suite.py
```

This validates that decisions are specific, actionable, and free from generic fallback phrasing.

### Prerequisites

- Python 3.10+
- PostgreSQL (recommended) or SQLite
- Google Cloud account (for Calendar integration)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/decisionos.git
cd decisionos
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Environment Variables

Create a `.env` file or set these variables:

```bash
# Required
export GEMINI_API_KEY="your-gemini-api-key"

# Database (PostgreSQL recommended)
export DATABASE_URL="postgresql://postgres:password@localhost:5432/decisionos"

# Or use SQLite (default)
# No config needed - uses decisionos.db
```

### 4. Google Calendar Setup (Optional but Recommended)

See [GOOGLE_CALENDAR_SETUP.md](GOOGLE_CALENDAR_SETUP.md) for detailed instructions.

**Quick Steps:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Google Calendar API
4. Create OAuth 2.0 credentials (Web application)
5. Download `credentials.json` to project root
6. Run the server and visit `/api/calendar/auth`
7. Authenticate in browser
8. `token.json` will be created automatically

### 5. Cloud Run Configuration (Production)

For Cloud Run, do not rely on local `credentials.json` inside the container image.

1. Create OAuth credentials as **Web application**
2. Add redirect URI:
    - `https://<your-cloud-run-url>/api/calendar/oauth/callback`
3. Set `GOOGLE_CREDENTIALS_JSON` environment variable on the Cloud Run service
4. Deploy and authenticate at least one test user through `/api/calendar/auth?user_id=<id>`

### 6. Initialize Database

The database is automatically initialized when you start the server.

---

## ▶️ How to Run

### Start the Backend Server

```bash
# Development
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Access the Application

1. Open browser: `http://localhost:8000`
2. Enter your situation in the text box
3. Click "Get Decision"
4. Watch the agent pipeline process
5. Review the decision and scenarios
6. Execute actions if desired

### Verify Calendar Integration

```bash
# Calendar status for a user
curl "http://127.0.0.1:8000/api/calendar/status?user_id=user_001"

# Calendar events for next 24 hours
curl "http://127.0.0.1:8000/api/calendar/events?user_id=user_001&hours=24"
```

---

## 🎮 Demo Example

### Input
```
I have exam at 7pm and gym at 6pm. What should I do?
```

### What Happens

1. **Planner** detects: exam (high priority), gym (low priority)
2. **Task Agent** scores: urgency 8/10, importance 10/10
3. **Calendar Agent** finds conflict: gym 6-7pm overlaps with exam prep
4. **Scenario Agent** simulates:
   - Skip gym: **90/100** ✨
   - Reschedule gym: 75/100
   - Attend gym: 14/100
5. **Decision Engine** chooses: Skip gym

### Output
```
🎯 Skip the gym and focus on your exam preparation

Confidence: 90%

Why this decision?
Skipping gym is recommended (score: 90/100). 
Urgency is high (8/10). Time conflict detected.
Focus on task to meet deadline.

Next Steps:
1. Cancel or decline gym
2. Start working on your task immediately
3. Complete before the deadline

[❌ Cancel Gym Event]  [📅 Reschedule Gym]
```

---

## 📡 API Reference

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/decide` | Make a decision (SSE stream) |
| POST | `/api/execute_action` | Execute an action |
| GET | `/api/decisions/{user_id}` | Get decision history |
| GET | `/api/calendar/events` | Get calendar events |
| GET | `/api/calendar/status` | Check calendar integration |
| GET | `/api/health` | Health check |
| POST | `/api/prioritize_tasks` | Prioritize a plain list of tasks |

### Decision Request

```json
POST /api/decide
{
    "user_id": "user_001",
    "message": "I have exam at 7pm and gym at 6pm"
}
```

### Execute Action

```json
POST /api/execute_action
{
    "user_id": "user_001",
    "action_type": "cancel_event",
    "event_id": "abc123",
    "params": {}
}
```

### Task Prioritization Demo

Use this endpoint when you want a simple Postman request that accepts only an array of tasks. Prioritization and decision text are generated by Gemini for each new input, so output can vary.

```json
POST /api/prioritize_tasks
{
    "tasks": [
        "Go to gym at 6 PM",
        "Attend interview at 7 PM",
        "Watch Netflix",
        "Prepare dinner"
    ]
}
```

Sample response:

```json
{
    "prioritized_tasks": [
        "Attend interview at 7 PM",
        "Prepare dinner",
        "Go to gym at 6 PM",
        "Watch Netflix"
    ],
    "decision": "Attend interview and skip gym",
    "reason": "Interview has highest priority and fixed time constraint"
}
```

---

## 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| Backend Framework | FastAPI |
| LLM Provider | Google Gemini (gemini-2.0-flash) |
| Database | PostgreSQL / SQLite |
| ORM | SQLAlchemy |
| Calendar | Google Calendar API |
| Streaming | Server-Sent Events (SSE) |
| Frontend | Vanilla JavaScript + CSS |

### Dependencies

```
fastapi>=0.100.0
uvicorn>=0.22.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
openai>=1.0.0
google-api-python-client>=2.100.0
google-auth>=2.22.0
google-auth-oauthlib>=1.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
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

## 📁 Project Structure

```
decisionos/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── routes.py            # API endpoints
│   ├── schemas.py           # Pydantic models
│   ├── db/
│   │   └── database.py      # Database models & setup
│   └── tools/
│       ├── mcp_tools.py     # MCP tool implementations
│       └── google_calendar.py # Google Calendar service
│
├── ai_engine/
│   ├── orchestrator.py      # Agent coordination
│   ├── config/
│   │   └── defaults.py      # System defaults & priorities
│   ├── utils/
│   │   ├── helpers.py       # JSON parsing, etc.
│   │   └── time_resolver.py # Time parsing
│   └── agents/
│       ├── planner_agent.py
│       ├── task_agent.py
│       ├── calendar_agent.py
│       ├── scenario_agent.py
│       └── decision_engine.py
│
├── frontend/
│   ├── index.html           # Main UI
│   ├── app.js               # Frontend logic
│   └── styles.css           # Styling
│
├── credentials.json         # Google OAuth (not in git)
├── token.json               # Google token (not in git)
├── requirements.txt         # Python dependencies
├── README.md                # This file
└── GOOGLE_CALENDAR_SETUP.md # Calendar setup guide
```

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
