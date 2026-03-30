# DecisionOS Frontend

Frontend UI for **DecisionOS** — an AI-powered system that helps users make optimal decisions by analyzing tasks, deadlines, and constraints.

---

## Overview

DecisionOS goes beyond task management.

It:

- Understands user problems
- Detects conflicts (deadlines, meetings, priorities)
- Simulates multiple outcomes
- Recommends the best possible decision

This project contains the **React + Vite frontend UI** for interacting with the system.

---

## Tech Stack

- React (Vite)
- TypeScript
- Tailwind CSS
- shadcn/ui
- Axios

---

## Installation & Setup

### 1. Clone the repository

```bash
cd frontend
```

---

### 2. Install dependencies

```bash
npm install
```

---

### 3. Run development server

```bash
npm run dev
```

App will run on:

```
http://localhost:5173
```

---

### 4. Build for production

```bash
npm run build
```

---

## Features Implemented

### 1. User Input Form

- Input for task/problem
- Deadline selection
- Constraints (meetings, time limits)

---

### 2. Simulation View

- Displays multiple decision options (e.g., Option A / Option B)
- Shows:
  - Risk levels
  - Expected outcomes
  - Success probability

---

### 3. Decision Recommendation

- Highlights the best decision
- Displays reasoning behind the recommendation

---

### 4. Task & Conflict Visualization

- Timeline / list-based view
- Highlights conflicts between tasks and deadlines

---

### 5. AI Processing State

- Loading indicators
- Messages like:
  - “Analyzing your situation…”
  - “Simulating outcomes…”

---

### 6. UI Layout

- Sidebar navigation
- Header section
- Dashboard-style layout
- Built using modern shadcn/ui components

---

### 7. API Integration Structure

- Axios setup ready
- Service layer created for backend integration

---

## Project Structure

```bash
src/
├── components/
├── pages/
├── services/
├── hooks/
├── utils/
├── App.tsx
└── main.tsx
```

---

## UI Design

- Modern SaaS-style interface
- Clean and minimal layout
- Rounded cards and soft shadows
- Focused on clarity for decision-making

---

## Note

> This is not just a task manager UI — it is a **decision intelligence interface**.
