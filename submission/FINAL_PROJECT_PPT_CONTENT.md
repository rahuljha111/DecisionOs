# Slide 1: Title

DecisionOS: Real-World Decision Engine

- Team/Owner: Rahul Jha
- Hackathon Submission 2026
- Tagline: AI That Simulates Before It Decides

# Slide 2: Problem Statement

People struggle to pick the right action under time pressure when events and tasks conflict.

- Generic assistants suggest too many options
- No strict prioritization in real scenarios
- Poor conflict resolution leads to missed exams/deadlines

# Slide 3: Solution Overview

DecisionOS makes one decisive action recommendation based on strict real-world hierarchy.

- Inputs: Calendar events + to-do tasks
- Output: One clear decision with reason, consequence, next steps
- Goal: Maximize real-world outcome, not convenience

# Slide 4: Core Priority Logic

Strict hierarchy used by engine:

1. Exams/Deadlines/Interviews (non-negotiable)
2. High-impact work (submission, urgent bug, career-critical)
3. Meetings
4. Routine items (gym, reading, social media)

Lower-priority conflicts are skipped/rescheduled first.

# Slide 5: Architecture

- Frontend: Vanilla JS dashboard
- Backend: FastAPI
- Agents:
  - Planner (deterministic parsing)
  - Task analyzer
  - Calendar conflict detector
  - Scenario simulator
  - Decision engine
- Tooling: Google Calendar integration + DB persistence

# Slide 6: Production Hardening Done

- Deterministic output mode by default
- Real action verbs only (attend/skip/cancel/reschedule/start/stop)
- Consistency enforcement across Decision/Reason/Consequence/Next Steps
- Generic fallback language removed
- Secrets excluded from git

# Slide 7: Results

Regression Suite Results:

- Total scenarios tested: 20
- Passed: 20
- Failed: 0

Includes required demo scenarios and edge cases.

# Slide 8: Demo Walkthrough

Demo flow shown:

- Input conflict: exam + gym + meeting
- Engine output: attend exam, skip lower-priority conflicts
- Output sections:
  - Decision
  - Reason
  - Consequence
  - Next Steps

# Slide 9: Deployment

Cloud Run hosted backend + frontend static serving.

- Public endpoint: PENDING (paste deployed URL)
- GitHub repo: https://github.com/rahuljha111/DecisionOs

# Slide 10: Future Improvements

- Dynamic quantitative scoring
- User preference learning
- Multi-day optimization
- Better time estimation
- Automatic calendar conflict resolution
