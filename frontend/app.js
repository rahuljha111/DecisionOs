/**
 * DecisionOS — Frontend Application
 * Production-ready: clean state management, SSE streaming, action execution
 */

const API_BASE = "/api";

// ─── State ────────────────────────────────────────────────────────────────────
let isProcessing = false;
let currentDecision = null;
let pendingAction = null;
let availableActions = [];

// Calendar & To-Do state
let calendarConnected = false;
let todayMeetings = [];
let todoItems = [];
let nextTodoId = 1;
let calendarRefreshTimer = null;

const pill = document.getElementById("statusPill");

// target the text span specifically
const statusText = pill.querySelector(".status-text");
statusText.textContent = "Waiting for input";

// ─── Google Calendar Integration ──────────────────────────────────────────────

/**
 * Initiates Google Calendar OAuth flow.
 * Uses backend OAuth endpoint and fetches real events.
 */
async function connectGoogleCalendar() {
  const btn = document.getElementById("connectCalBtn");
  const label = document.getElementById("connectCalBtnLabel");

  if (calendarConnected) {
    // Disconnect
    calendarConnected = false;
    todayMeetings = [];
    btn.classList.remove("connected");
    label.textContent = "Connect Google Calendar";
    renderMeetings();
    return;
  }

  // Show loading state on button
  label.textContent = "Connecting…";
  btn.disabled = true;

  try {
    const userId = document.getElementById("userId").value.trim() || "user_001";
    const checkRes = await fetch(
      `${API_BASE}/calendar/auth_url?user_id=${encodeURIComponent(userId)}`,
    ).catch(() => null);

    if (checkRes && checkRes.ok) {
      const { auth_url } = await checkRes.json();
      const target = auth_url || `${API_BASE}/calendar/auth?user_id=${encodeURIComponent(userId)}`;

      // Open OAuth popup
        const popup = window.open(target, "gcal_oauth", "width=500,height=620");

      // Poll for popup close & then fetch events
      const pollTimer = setInterval(async () => {
        if (!popup || popup.closed) {
          clearInterval(pollTimer);
          await fetchCalendarEvents();
        }
      }, 500);
    } else {
      showToast("Calendar auth endpoint not available. Start backend server first.", "error");
    }
  } catch (err) {
    showToast("Google Calendar connection failed. Check credentials and token setup.", "error");
  } finally {
    if (!calendarConnected) {
      label.textContent = "Connect Google Calendar";
    }
    btn.disabled = false;
  }
}

/**
 * Fetch real calendar events from backend after OAuth completes.
 */
async function fetchCalendarEvents() {
  const btn = document.getElementById("connectCalBtn");
  const label = document.getElementById("connectCalBtnLabel");

  try {
    const userId = document.getElementById("userId").value.trim() || "user_001";
    const res = await fetch(
      `${API_BASE}/calendar/events?user_id=${encodeURIComponent(userId)}`,
    );

    if (!res.ok) throw new Error("Failed to fetch events");

    const data = await res.json();
    todayMeetings = (data.events || []).map((e) => ({
      time: e.start_time || e.time || "",
      title: e.title || e.summary || "Event",
    }));

    setCalendarConnected();
  } catch (err) {
    showToast("Unable to fetch calendar events from backend.", "error");
  }
}

function startCalendarAutoRefresh() {
  stopCalendarAutoRefresh();
  calendarRefreshTimer = setInterval(() => {
    if (calendarConnected) {
      fetchCalendarEvents();
    }
  }, 60000);
}

function stopCalendarAutoRefresh() {
  if (calendarRefreshTimer) {
    clearInterval(calendarRefreshTimer);
    calendarRefreshTimer = null;
  }
}

/**
 */

function setCalendarConnected() {
  calendarConnected = true;

  const btn = document.getElementById("connectCalBtn");
  const label = document.getElementById("connectCalBtnLabel");

  btn.classList.add("connected");
  label.textContent = "✓ Calendar Connected";

  renderMeetings();
  startCalendarAutoRefresh();
}

async function checkCalendarStatus() {
  try {
    const userId = document.getElementById("userId").value.trim() || "user_001";
    const res = await fetch(`${API_BASE}/calendar/status?user_id=${encodeURIComponent(userId)}`);
    if (!res.ok) return;

    const status = await res.json();
    if (status.authenticated) {
      await fetchCalendarEvents();
    }
  } catch (_err) {
    // Ignore status probe errors; manual connect button remains available.
  }
}

// ─── Render Events ────────────────────────────────────────────────────────────
function renderMeetings() {
  const list = document.getElementById("meetingsList");

  if (!calendarConnected || todayMeetings.length === 0) {
    list.innerHTML = `
            <div class="cal-empty-state">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="3" y="4" width="18" height="18" rx="2"/>
                    <path d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
                <p>Connect Google Calendar to see your events</p>
            </div>`;
    return;
  }

  list.innerHTML = todayMeetings
    .map(
      (m) => `
        <div class="meeting-item">
            <div class="meeting-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
            </div>
            <span class="meeting-time">${escapeHtml(m.time)}</span>
            <span class="meeting-title">${escapeHtml(m.title)}</span>
        </div>
    `,
    )
    .join("");
}

// ─── To-Do List ───────────────────────────────────────────────────────────────
function renderTodos() {
  const list = document.getElementById("todoList");

  if (todoItems.length === 0) {
    list.innerHTML = `<p style="font-size:12.5px;color:var(--gray-400);padding:12px 10px;">No tasks yet. Add one below!</p>`;
    return;
  }

  list.innerHTML = todoItems
    .map(
      (item) => `
        <div class="todo-item ${item.done ? "done" : ""}" id="todo-${item.id}">
            <input type="checkbox" ${item.done ? "checked" : ""}
                onchange="toggleTodo(${item.id})" />
            <span class="todo-item-label">${escapeHtml(item.text)}</span>
            <button class="todo-item-delete" onclick="deleteTodo(${item.id})" title="Remove task">✕</button>
        </div>
    `,
    )
    .join("");
}

function addTask() {
  const input = document.getElementById("newTaskInput");
  const text = input.value.trim();
  if (!text) return;

  todoItems.push({ id: nextTodoId++, text, done: false });
  input.value = "";
  renderTodos();
}

function toggleTodo(id) {
  const item = todoItems.find((t) => t.id === id);
  if (item) {
    item.done = !item.done;
    renderTodos();
  }
}

function deleteTodo(id) {
  todoItems = todoItems.filter((t) => t.id !== id);
  renderTodos();
}

// ─── AI Prioritize My Day ─────────────────────────────────────────────────────

/**
 * Calls the backend (or Claude API) to produce an AI-prioritized schedule
 * that interleaves to-do tasks with today's meetings.
 */
async function prioritizeMyDay() {
  const btn = document.querySelector(".btn-prioritize");
  const planSection = document.getElementById("aiPlanSection");
  const planList = document.getElementById("aiPlanList");

  const pendingTasks = todoItems.filter((t) => !t.done).map((t) => t.text);

  if (pendingTasks.length === 0) {
    planList.innerHTML = `<div class="ai-plan-loading"><span>⚠️</span> Add at least one task to prioritize.</div>`;
    planSection.style.display = "block";
    return;
  }

  // Show loading
  btn.disabled = true;
  btn.textContent = "Prioritizing…";
  planSection.style.display = "block";
  planList.innerHTML = `
        <div class="ai-plan-loading">
            <span class="ai-plan-spinner"></span>
            AI is building your schedule…
        </div>`;

  try {
    // Try real backend endpoint first
    const userId = document.getElementById("userId").value.trim() || "user_001";

    const res = await fetch(`${API_BASE}/prioritize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        tasks: pendingTasks,
        meetings: todayMeetings,
      }),
    }).catch(() => null);

    if (res && res.ok) {
      const data = await res.json();
      renderAiPlan(data.plan || []);
    } else {
      // Fallback: build a smart demo plan locally
      const demoPlan = buildDemoPlan(pendingTasks, todayMeetings);
      renderAiPlan(demoPlan);
    }
  } catch (err) {
    const demoPlan = buildDemoPlan(pendingTasks, todayMeetings);
    renderAiPlan(demoPlan);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
            </svg>
            Prioritize My Day`;
  }
}

/**
 * Render a plan array:  [{ task, start, end, note }]
 */
function renderAiPlan(plan) {
  const planList = document.getElementById("aiPlanList");

  if (!plan.length) {
    planList.innerHTML = `<div class="ai-plan-loading">No plan could be generated.</div>`;
    return;
  }

  planList.innerHTML = plan
    .map(
      (item, i) => `
        <div class="ai-plan-item">
            <span class="ai-plan-num">${i + 1}.</span>
            <span class="ai-plan-task">${escapeHtml(item.task)}</span>
            <span class="ai-plan-time">${escapeHtml(item.start)} – ${escapeHtml(item.end)}</span>
            <span class="ai-plan-note">"${escapeHtml(item.note)}"</span>
        </div>
    `,
    )
    .join("");
}

/**
 * Local fallback plan builder — slots tasks into gaps between meetings.
 */
function buildDemoPlan(tasks, meetings) {
  // Parse meeting times to find free windows
  const notes = [
    "Focus work, ideal time slot",
    "Quick task after meeting",
    "Evening is great for this",
    "Good momentum window",
    "Batch with similar tasks",
  ];

  // Build simple schedule starting after last known meeting or from 9 AM
  const slots = generateFreeSlots(meetings);

  return tasks.map((task, i) => {
    const slot = slots[i] || { start: "06:00 PM", end: "07:00 PM" };
    return {
      task,
      start: slot.start,
      end: slot.end,
      note: notes[i % notes.length],
    };
  });
}

/**
 * Produce a list of 90-minute free slots that don't overlap known meetings.
 */
function generateFreeSlots(meetings) {
  // Convert meeting times (e.g. "10:00 AM") to minutes since midnight
  const busyMinutes = meetings.map((m) => parseTime(m.time)).filter(Boolean);

  const slots = [];
  let cursor = parseTime("09:00 AM"); // start searching from 9 AM
  const endDay = parseTime("08:00 PM");
  const slotLen = 90; // minutes per task slot

  while (cursor + slotLen <= endDay && slots.length < 8) {
    // Check if this window overlaps any meeting (assume each meeting = 60 min)
    const overlaps = busyMinutes.some(
      (m) => cursor < m + 60 && cursor + slotLen > m,
    );

    if (!overlaps) {
      slots.push({
        start: formatMinutes(cursor),
        end: formatMinutes(cursor + slotLen),
      });
      cursor += slotLen + 15; // 15-min buffer
    } else {
      cursor += 15; // step forward and try again
    }
  }

  return slots;
}

function parseTime(timeStr) {
  if (!timeStr) return null;
  const match = timeStr.match(/(\d+):(\d+)\s*(AM|PM)/i);
  if (!match) return null;
  let h = parseInt(match[1], 10);
  const m = parseInt(match[2], 10);
  const p = match[3].toUpperCase();
  if (p === "PM" && h !== 12) h += 12;
  if (p === "AM" && h === 12) h = 0;
  return h * 60 + m;
}

function formatMinutes(total) {
  const h = Math.floor(total / 60);
  const m = total % 60;
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h > 12 ? h - 12 : h === 0 ? 12 : h;
  return `${h12}:${String(m).padStart(2, "0")} ${ampm}`;
}

// ─── Utility ──────────────────────────────────────────────────────────────────
function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function generateUserId() {
  const rand = Math.random().toString(36).slice(2, 10);
  return `user_${rand}`;
}

function initUserId() {
  const userIdInput = document.getElementById("userId");
  if (!userIdInput) return;

  const saved = localStorage.getItem("decisionos_user_id");
  const current = userIdInput.value.trim();

  if (saved) {
    userIdInput.value = saved;
  } else if (!current || current === "user_001") {
    const generated = generateUserId();
    userIdInput.value = generated;
    localStorage.setItem("decisionos_user_id", generated);
  } else {
    localStorage.setItem("decisionos_user_id", current);
  }

  userIdInput.addEventListener("change", () => {
    const normalized = userIdInput.value.trim() || generateUserId();
    userIdInput.value = normalized;
    localStorage.setItem("decisionos_user_id", normalized);
    checkCalendarStatus();
  });
}

// ─── Submit ───────────────────────────────────────────────────────────────────
async function submitDecision() {
  const userIdInput = document.getElementById("userId");
  const userId = userIdInput.value.trim() || "user_001";

  // Get pending tasks from to-do list
  const pendingTasks = todoItems.filter((t) => !t.done).map((t) => t.text);

  console.log("pendingTasks", pendingTasks);

  // Check if there are any tasks
  if (pendingTasks.length === 0) {
    showToast("Please create To Do list", "warning");
    return;
  }

  // Build message from tasks and current calendar context
  const taskList = pendingTasks
    .map((task, i) => `${i + 1}. ${task}`)
    .join(", ");

  const meetingList = todayMeetings.length
    ? todayMeetings
        .map((meeting, i) => `${i + 1}. ${meeting.title} at ${meeting.time}`)
        .join(", ")
    : "No calendar events found";

  console.log("taskList", taskList);

  const message = `I have the following tasks to prioritize today: ${taskList}. My calendar events are: ${meetingList}. Use this calendar context to identify conflicts, prioritize tasks, and suggest rescheduling when needed.`;

  console.log("message", message);

  if (isProcessing) return;

  resetUI();
  setProcessing(true);

  try {
    const response = await fetch(`${API_BASE}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, message }),
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      let currentEvent = null;
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.substring(7);
        } else if (line.startsWith("data: ") && currentEvent) {
          try {
            const data = JSON.parse(line.substring(6));
            handleEvent(currentEvent, data);
          } catch (_) {
            /* skip malformed JSON */
          }
          currentEvent = null;
        }
      }
    }
  } catch (error) {
    showError(`Connection error: ${error.message}`);
  } finally {
    setProcessing(false);
  }
}

// ─── SSE Event Router ─────────────────────────────────────────────────────────
function handleEvent(eventType, data) {
  const traceContainer = document.getElementById("traceContainer");

  switch (eventType) {
    case "agent_start":
      addTraceItem(traceContainer, {
        type: "agent",
        status: "running",
        agent: data.agent,
        message: data.message,
      });
      break;

    case "agent_complete":
      updateTraceItem(data.agent, "complete", data.data);
      if (data.agent === "scenario") displayScenarios(data.data);
      break;

    case "processing":
      addTraceItem(traceContainer, {
        type: "processing",
        status: "running",
        step: data.step,
        message: data.message,
      });
      break;

    case "processing_complete":
      updateProcessingItem(data.step, "complete");
      break;

    case "complete":
      currentDecision = data;
      displayFinalDecision(data);
      break;

    case "error":
      showError(data.error);
      break;
  }
}

// ─── Trace Helpers ────────────────────────────────────────────────────────────
function addTraceItem(container, config) {
  const placeholder = container.querySelector(".empty-state");
  if (placeholder) placeholder.remove();

  const item = document.createElement("div");
  item.className = `trace-item trace-${config.status}`;
  item.id = config.agent
    ? `trace-${config.agent}`
    : `trace-${config.step || config.type}`;

  const icon = getStatusIcon(config.status);
  const label = config.agent
    ? formatAgentName(config.agent)
    : config.step || config.type;

  item.innerHTML = `
        <span class="trace-icon">${icon}</span>
        <span class="trace-label">${label}</span>
        <span class="trace-message">${config.message || ""}</span>
    `;

  container.appendChild(item);
  container.scrollTop = container.scrollHeight;
}

function updateTraceItem(agent, status, data) {
  const item = document.getElementById(`trace-${agent}`);
  if (!item) return;
  item.className = `trace-item trace-${status}`;
  const iconEl = item.querySelector(".trace-icon");
  if (iconEl) iconEl.textContent = getStatusIcon(status);
  const msgEl = item.querySelector(".trace-message");
  if (msgEl && data) msgEl.textContent = summarizeData(agent, data);
}

function updateProcessingItem(step, status) {
  const item = document.getElementById(`trace-${step}`);
  if (!item) return;
  item.className = `trace-item trace-${status}`;
  const iconEl = item.querySelector(".trace-icon");
  if (iconEl) iconEl.textContent = getStatusIcon(status);
}

// ─── Formatting ───────────────────────────────────────────────────────────────
function getStatusIcon(status) {
  return { running: "⏳", complete: "✅", error: "❌" }[status] || "•";
}

function formatAgentName(agent) {
  return (
    {
      planner: "📋 Planner",
      task: "📊 Task Analyzer",
      calendar: "📅 Calendar",
      scenario: "🎲 Simulator",
      decision_engine: "🧠 Decision Engine",
    }[agent] || agent
  );
}

function summarizeData(agent, data) {
  switch (agent) {
    case "planner":
      return data.task_type
        ? `Detected: ${data.task_type}`
        : "Extracted task info";
    case "task":
      return `Priority: ${data.priority}/10`;
    case "calendar":
      return data.has_conflict ? "⚠️ Conflict detected" : "✓ No conflicts";
    case "scenario":
      return formatScenarioSummary(data.options || []);
    case "decision_engine":
      return "Decision made";
    default:
      return "";
  }
}

function formatScenarioScore(option) {
  const score = Number(option?.score);
  return Number.isFinite(score) ? Math.round(score) : 0;
}

function formatScenarioSummary(options) {
  if (!options.length) return "0 options simulated";

  const scoreSummary = options
    .slice(0, 3)
    .map((opt) => `${formatOptionName(opt.action)} ${formatScenarioScore(opt)}/100`)
    .join(" · ");

  return `${options.length} options simulated (${scoreSummary})`;
}

function formatScenarioRationale(opt) {
  const score = formatScenarioScore(opt);
  const urgency = Number(opt?.urgency_factor ?? 0);
  const taskPriority = String(opt?.task_priority || "unknown").toLowerCase();
  const eventPriority = String(opt?.event_priority || "unknown").toLowerCase();

  if (taskPriority === "high" && eventPriority === "low") {
    if (String(opt?.action || "").includes("skip")) {
      return `High-priority task beats the low-priority event, so this gets a strong score (${score}/100).`;
    }
    if (String(opt?.action || "").includes("attend")) {
      return `This keeps the low-priority event, so it is penalized against the high-priority task (${score}/100).`;
    }
  }

  if (taskPriority === "low" && eventPriority === "high") {
    if (String(opt?.action || "").includes("attend")) {
      return `The higher-priority event should win here, so this choice is favored (${score}/100).`;
    }
    if (String(opt?.action || "").includes("skip")) {
      return `Skipping a high-priority event is discouraged, so this score stays low (${score}/100).`;
    }
  }

  if (urgency >= 7 && String(opt?.action || "").includes("skip")) {
    return `Urgency is high, so skipping gets rewarded as a focus-first move (${score}/100).`;
  }

  if (urgency >= 7 && String(opt?.action || "").includes("attend")) {
    return `High urgency makes attending less attractive, so the score is reduced (${score}/100).`;
  }

  if (String(opt?.action || "").includes("reschedule")) {
    return `Rescheduling is the compromise option, so it lands in the middle (${score}/100).`;
  }

  return `Score ${score}/100 based on urgency ${urgency}/10 and the current conflict context.`;
}

function formatOptionName(action) {
  if (!action) return "Unknown";
  return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─── Scenarios ────────────────────────────────────────────────────────────────
function displayScenarios(data) {
  if (!data?.options?.length) return;

  const section = document.getElementById("scenariosSection");
  const container = document.getElementById("scenariosContainer");
  const sorted = [...data.options].sort(
    (a, b) => (b.score || 0) - (a.score || 0),
  );
  const scoreSummary = sorted
    .slice(0, 3)
    .map((opt) => `${formatOptionName(opt.action)}: ${formatScenarioScore(opt)}/100`)
    .join(" · ");

  let html = "";

  if (scoreSummary) {
    html += `
        <div class="scenario-score-summary">
            <strong>Scores:</strong> ${scoreSummary}
        </div>
    `;
  }

  if (data.recommendation) {
    const recommendedOption = sorted.find((opt) => opt.action === data.recommendation);
    html += `
        <div class="scenario-recommendation">
            <strong>Scenario recommendation:</strong> ${formatOptionName(data.recommendation)}
            ${recommendedOption?.description ? `<div class="scenario-recommendation-note">${escapeHtml(recommendedOption.description)}</div>` : ""}
        </div>
    `;
  }

  html += '<div class="scenarios-grid">';

  sorted.forEach((opt, index) => {
    const isRecommended = index === 0;
    const scoreClass =
      opt.score >= 70 ? "high" : opt.score >= 40 ? "medium" : "low";

    html += `
            <div class="scenario-card ${isRecommended ? "recommended" : ""}">
                ${isRecommended ? '<span class="recommended-badge">✨ Recommended</span>' : ""}
                <h4>${formatOptionName(opt.action)}</h4>
                <div class="scenario-score score-${scoreClass}">
                    <span class="score-value">${Math.round(opt.score)}</span>
                    <span class="score-label">/ 100</span>
                </div>
                <p class="scenario-rationale">
                  <strong>Why this score:</strong> ${formatScenarioRationale(opt)}
                </p>
                <p class="scenario-outcome">
                    <strong>Outcome:</strong> ${opt.description || "No description"}
                </p>
                <p class="scenario-risk">
                    <strong>Risk:</strong> ${opt.risks?.join(", ") || "None identified"}
                </p>
            </div>
        `;
  });

  html += "</div>";
  container.innerHTML = html;
  section.style.display = "block";
}

// ─── Final Decision ───────────────────────────────────────────────────────────
function displayFinalDecision(data) {
  const container = document.getElementById("decisionContainer");
  const decision = data.decision;

  if (!decision) {
    container.innerHTML =
      '<div class="error"><span class="error-icon">❌</span><span class="error-message">No decision generated.</span></div>';
    return;
  }

  const confidenceClass =
    decision.confidence >= 0.8
      ? "high"
      : decision.confidence >= 0.6
        ? "medium"
        : "low";

  const decisionText =
    decision.decision_text || formatOptionName(decision.action);
  const reasonText = decision.reasoning || "No reason provided.";
  const consequenceText =
    decision.consequence ||
    "If you ignore this decision, the highest-impact risk will remain unresolved.";

  let conflictBadge = "";
  if (decision.conflict_type && decision.conflict_type !== "none") {
    const label =
      decision.conflict_type === "priority_conflict"
        ? "⚡ Priority conflict"
        : "⏰ Time conflict";
    conflictBadge = `<span class="conflict-badge">${label}</span>`;
  }

  container.innerHTML = `
        <div class="decision-result">
        <div class="decision-section">
          <div class="decision-section-label">[Decision]</div>
          <div class="decision-action">
            <span class="action-icon">🎯</span>
            <span class="action-text">${decisionText}</span>
          </div>
            </div>
            ${conflictBadge}
        <div class="decision-section">
          <div class="decision-section-label">[Reason]</div>
          <div class="decision-reasoning">
            <p>${reasonText}</p>
                </div>
        </div>
        <div class="decision-section">
          <div class="decision-section-label">[Consequence]</div>
          <div class="decision-consequence">
            <p>${consequenceText}</p>
                </div>
            </div>
        <div class="decision-confidence confidence-${confidenceClass}">
          <div class="confidence-row">
            <span class="confidence-label">Confidence</span>
            <span class="confidence-value">${Math.round(decision.confidence * 100)}%</span>
          </div>
          <div class="confidence-bar">
            <div class="confidence-fill" style="width: ${decision.confidence * 100}%"></div>
          </div>
        </div>
            ${
              decision.next_steps?.length
                ? `
            <div class="decision-steps">
                <h4>Next steps</h4>
                <ol>${decision.next_steps.map((s) => `<li>${s}</li>`).join("")}</ol>
            </div>`
                : ""
            }
        </div>
    `;

  displayActionButtons(decision);
}

// ─── Action Buttons ───────────────────────────────────────────────────────────
function displayActionButtons(decision) {
  const section = document.getElementById("actionsSection");
  const container = document.getElementById("actionsContainer");

  const actions = decision.executable_actions || [];
  const inferredActions = [];
  const action = decision.action?.toLowerCase() || "";
  const eventId = decision.event_id;

  if (action.includes("skip") || action.includes("cancel")) {
    inferredActions.push({
      type: "cancel_event",
      label: "Skip / Cancel event",
      icon: "❌",
      eventId,
    });
  } else if (action.includes("reschedule")) {
    inferredActions.push({
      type: "reschedule_event",
      label: "Reschedule event",
      icon: "📅",
      eventId,
    });
  }

  const allActions = [...actions, ...inferredActions];
  availableActions = allActions;

  if (allActions.length === 0) {
    section.style.display = "none";
    return;
  }

  container.innerHTML = allActions
    .map((act, index) => {
      const icon = act.icon || getActionIcon(act.type);
      const label = act.label || formatOptionName(act.type);
      const eid = act.event_id || act.eventId || "";
      const etitle = act.event_title || "";

      return `
            <button class="action-btn"
                onclick="executeActionByIndex(${index})">
                <span class="action-btn-icon">${icon}</span>
                <span class="action-btn-label">${label}</span>
                ${etitle ? `<span class="action-btn-detail">${etitle}</span>` : ""}
            </button>
        `;
    })
    .join("");

  section.style.display = "block";
}

function getActionIcon(type) {
  return (
    {
      cancel_event: "❌",
      reschedule_event: "📅",
      create_event: "➕",
      add_task: "📝",
    }[type] || "⚡"
  );
}

function executeActionByIndex(index) {
  const action = availableActions[index];
  if (!action) {
    showError("Unable to execute action: missing action payload.");
    return;
  }

  const actionType = action.type || action.action || "";
  const eventId = action.event_id || action.eventId || "";
  const eventTitle = action.event_title || action.eventTitle || "";

  executeAction(actionType, eventId, eventTitle, action);
}

// ─── Execute Action ───────────────────────────────────────────────────────────
function executeAction(actionType, eventId, eventTitle, actionData = null) {
  pendingAction = { actionType, eventId, eventTitle, actionData };

  const modal = document.getElementById("confirmModal");
  const message = document.getElementById("confirmMessage");

  let text = formatOptionName(actionType);
  if (eventTitle) text += ` "${eventTitle}"`;

  message.textContent = `Are you sure you want to ${text}?`;
  modal.style.display = "flex";
}

function closeModal() {
  document.getElementById("confirmModal").style.display = "none";
  pendingAction = null;
}

async function confirmAction() {
  if (!pendingAction) {
    closeModal();
    return;
  }

  const { actionType, eventId, actionData } = pendingAction;
  closeModal();

  try {
    const userId = document.getElementById("userId").value.trim() || "user_001";

    const params = {
      ...(actionData?.params || {}),
    };

    if (actionData?.suggested_time && !params.new_start_time) {
      params.suggested_time = actionData.suggested_time;
    }

    if (actionType === "reschedule_event") {
      const nextTask = todoItems.find((task) => !task.done);
      if (nextTask && !params.create_focus_event_title) {
        params.create_focus_event_title = `Focus: ${nextTask.text}`;
      }
    }

    const response = await fetch(`${API_BASE}/execute_action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        action_type: actionType,
        event_id: eventId,
        params,
      }),
    });

    const result = await response.json();

    if (result.success) {
      const focusMessage = result.focus_event?.created
        ? ` Focus block created: ${result.focus_event.title}`
        : "";
      showSuccess((result.message || "Action executed successfully!") + focusMessage);
      if (calendarConnected) {
        await fetchCalendarEvents();
      }
    } else {
      showError(result.message || "Action failed.");
    }
  } catch (error) {
    showError(`Error executing action: ${error.message}`);
  }

  pendingAction = null;
}

// ─── Toast / Feedback ─────────────────────────────────────────────────────────
function showSuccess(message) {
  const container = document.getElementById("actionsContainer");
  container.innerHTML = `
        <div class="success-message">
            <span>✅</span>
            <span>${message}</span>
        </div>
    `;
}

function showError(message) {
  const container = document.getElementById("decisionContainer");
  container.innerHTML = `
        <div class="error">
            <span class="error-icon">⚠️</span>
            <span class="error-message">${message}</span>
        </div>
    `;
}

function showToast(message, type = "warning") {
  // Create a toast container if it doesn't exist
  let toastContainer = document.getElementById("toastContainer");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toastContainer";
    toastContainer.style.cssText = `
      position: fixed;
      top: 20px;
      right: 20px;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-width: 400px;
    `;
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement("div");
  const bgColor = type === "warning" ? "#fef3c7" : "#fee2e2";
  const borderColor = type === "warning" ? "#fcd34d" : "#fca5a5";
  const textColor = type === "warning" ? "#92400e" : "#991b1b";
  const icon = type === "warning" ? "⚠️" : "❌";

  toast.style.cssText = `
    background: ${bgColor};
    border: 1px solid ${borderColor};
    border-radius: 8px;
    padding: 16px;
    color: ${textColor};
    display: flex;
    align-items: center;
    gap: 12px;
    font-weight: 500;
    font-size: 14px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    animation: slideInRight 0.3s ease-out;
  `;

  toast.innerHTML = `
    <span style="font-size: 18px; flex-shrink: 0;">${icon}</span>
    <span>${message}</span>
  `;

  toastContainer.appendChild(toast);

  // Auto-remove after 4 seconds
  setTimeout(() => {
    toast.style.animation = "slideOutRight 0.3s ease-out";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ─── UI State ─────────────────────────────────────────────────────────────────
function resetUI() {
  document.getElementById("decisionContainer").innerHTML = `
        <div class="empty-state">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
            </svg>
            <p>Processing your request…</p>
        </div>
    `;
  document.getElementById("traceContainer").innerHTML = "";
  document.getElementById("scenariosSection").style.display = "none";
  document.getElementById("actionsSection").style.display = "none";
  currentDecision = null;
}

function setProcessing(processing) {
  isProcessing = processing;

  const btn = document.querySelector(".btn-prioritize");
  const pill = document.getElementById("statusPill");

  if (btn) {
    btn.disabled = processing;
    btn.innerHTML = processing
      ? "Processing…"
      : `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
        </svg>
        Prioritize My Day`;
  }

  if (pill) {
    pill.classList.toggle("processing", processing);
    pill.querySelector("span:last-child").textContent = processing
      ? "Processing"
      : "Ready";
  }
}

// ─── Keyboard Shortcuts & Init ────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Enter in new-task input
  document.getElementById("newTaskInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addTask();
    }
  });

  // Close modal on overlay click
  document.getElementById("confirmModal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });

  window.addEventListener("message", (event) => {
    const data = event.data || {};
    if (data.type === "google-calendar-auth" && data.success) {
      fetchCalendarEvents();
    }
  });

  initUserId();

  // Render initial to-do list
  renderTodos();
  renderMeetings();
  checkCalendarStatus();

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && calendarConnected) {
      fetchCalendarEvents();
    }
  });
});
