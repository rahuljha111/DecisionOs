/**
 * DecisionOS — Frontend Application
 * Production-ready: clean state management, SSE streaming, action execution
 */

const API_BASE = "/api";

// ─── State ────────────────────────────────────────────────────────────────────
let isProcessing = false;
let currentDecision = null;
let pendingAction = null;

const pill = document.getElementById("statusPill");

// target the text span specifically
const statusText = pill.querySelector(".status-text");
statusText.textContent = "Waiting for input";

// ─── Submit ───────────────────────────────────────────────────────────────────
async function submitDecision() {
  const messageInput = document.getElementById("messageInput");
  const userIdInput = document.getElementById("userId");

  const message = messageInput.value.trim();
  const userId = userIdInput.value.trim() || "user_001";

  if (!message) {
    showError("Please enter a decision request.");
    return;
  }

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

    // Process SSE stream
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
      return `${data.options?.length || 0} options simulated`;
    case "decision_engine":
      return "Decision made";
    default:
      return "";
  }
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

  let html = '<div class="scenarios-grid">';

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
            <div class="decision-action">
                <span class="action-icon">🎯</span>
                <span class="action-text">${decisionText}</span>
            </div>

            ${conflictBadge}

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
              decision.reasoning
                ? `
            <div class="decision-reasoning">
                <h4>Why this decision?</h4>
                <p>${decision.reasoning}</p>
            </div>`
                : ""
            }

            ${
              decision.next_steps?.length
                ? `
            <div class="decision-steps">
                <h4>Next steps</h4>
                <ol>
                    ${decision.next_steps.map((s) => `<li>${s}</li>`).join("")}
                </ol>
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

  if (allActions.length === 0) {
    section.style.display = "none";
    return;
  }

  container.innerHTML = allActions
    .map((act) => {
      const icon = act.icon || getActionIcon(act.type);
      const label = act.label || formatOptionName(act.type);
      const eid = act.event_id || act.eventId || "";
      const etitle = act.event_title || "";

      return `
            <button class="action-btn"
                onclick="executeAction('${act.type}', '${eid}', '${etitle}')">
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

// ─── Execute Action ───────────────────────────────────────────────────────────
function executeAction(actionType, eventId, eventTitle) {
  pendingAction = { actionType, eventId, eventTitle };

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

  const { actionType, eventId } = pendingAction;
  closeModal();

  try {
    const userId = document.getElementById("userId").value.trim() || "user_001";

    const response = await fetch(`${API_BASE}/execute_action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        action_type: actionType,
        event_id: eventId,
        params: {},
      }),
    });

    const result = await response.json();

    if (result.success) {
      showSuccess(result.message || "Action executed successfully!");
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

  const btn = document.getElementById("submitBtn");
  const btnText = btn.querySelector(".btn-text");
  const btnLoad = btn.querySelector(".btn-loading");

  btn.disabled = processing;
  btnText.style.display = processing ? "none" : "inline-flex";
  btnLoad.style.display = processing ? "inline-flex" : "none";

  if (pill) {
    pill.classList.toggle("processing", processing);
    pill.querySelector("span:last-child").textContent = processing
      ? "Processing"
      : "Ready";
  }
}

// ─── Keyboard Shortcut ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("messageInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitDecision();
    }
  });

  // Close modal on overlay click
  document.getElementById("confirmModal").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
});
