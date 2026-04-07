/**
 * DecisionOS — Frontend Logic
 *
 * BACKEND_URL is set to empty string so requests go to the same origin.
 * When running the frontend separately (e.g. file://) change BACKEND_URL
 * to your Cloud Run service URL, e.g.:
 *   const BACKEND_URL = "https://decisionos-xxxx-uc.a.run.app";
 */
const BACKEND_URL = window.__BACKEND_URL__ || "";

// Read user_id from URL params (set after OAuth) or use default
const params = new URLSearchParams(window.location.search);
const USER_ID = params.get("user_id") || "test_user";

// ─────────────────────────────────────────────
// GOOGLE CALENDAR CONNECT
// ─────────────────────────────────────────────

function connectCalendar() {
  const url = `${BACKEND_URL}/auth/google?user_id=${encodeURIComponent(USER_ID)}`;
  window.location.href = url;
}

// Show success message if redirected back after OAuth
if (params.get("auth") === "success") {
  const btn = document.getElementById("calendarBtn");
  if (btn) {
    btn.textContent = "✅ Google Calendar Connected";
    btn.style.background = "#22c55e";
    btn.disabled = true;
  }
}

// ─────────────────────────────────────────────
// LOGGING
// ─────────────────────────────────────────────

function log(message, type = "info") {
  const logs = document.getElementById("logs");
  const div = document.createElement("div");
  div.className = `log log-${type}`;
  div.innerText = message;
  logs.appendChild(div);
  logs.scrollTop = logs.scrollHeight;
}

function clearUI() {
  document.getElementById("logs").innerHTML = "";
  document.getElementById("final").innerHTML = "";
}

// ─────────────────────────────────────────────
// FINAL DECISION RENDER
// ─────────────────────────────────────────────

function showFinal(decision, summary) {
  const final = document.getElementById("final");

  const confidenceColor =
    decision.confidence >= 80 ? "#22c55e" :
    decision.confidence >= 60 ? "#f59e0b" : "#ef4444";

  const stepsHtml = (decision.next_steps || [])
    .map(s => `<li>${s}</li>`)
    .join("");

  const alternativesHtml = (decision.alternatives || [])
    .map(a => `<li>${a.action} <span class="score">(score: ${a.score})</span></li>`)
    .join("");

  final.innerHTML = `
    <div class="decision-card">
      <h2>🎯 Final Decision</h2>

      <div class="decision-main">
        <div class="decision-action">${decision.decision_text || decision.action}</div>
        <div class="confidence-bar">
          <span>Confidence</span>
          <div class="bar-track">
            <div class="bar-fill" style="width:${decision.confidence}%;background:${confidenceColor}"></div>
          </div>
          <span>${decision.confidence}%</span>
        </div>
      </div>

      <p class="reasoning"><strong>Reasoning:</strong> ${decision.reasoning || "—"}</p>

      ${stepsHtml ? `<div class="next-steps"><h3>📋 Next Steps</h3><ul>${stepsHtml}</ul></div>` : ""}

      ${alternativesHtml ? `<div class="alternatives"><h3>🔄 Alternatives Considered</h3><ul>${alternativesHtml}</ul></div>` : ""}

      ${summary ? `
        <div class="summary-grid">
          <div class="summary-item">
            <span class="label">Urgency</span>
            <span class="value">${summary.urgency}/10</span>
          </div>
          <div class="summary-item">
            <span class="label">Importance</span>
            <span class="value">${summary.importance}/10</span>
          </div>
          <div class="summary-item">
            <span class="label">Priority</span>
            <span class="value">${summary.task_priority}/10</span>
          </div>
          <div class="summary-item">
            <span class="label">Conflict</span>
            <span class="value">${summary.has_conflict ? "⚠️ Yes" : "✅ No"}</span>
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

// ─────────────────────────────────────────────
// MAIN: START DECISION PIPELINE
// ─────────────────────────────────────────────

function startDecision() {
  const input = document.getElementById("input").value.trim();
  if (!input) {
    alert("Please describe your decision situation.");
    return;
  }

  clearUI();
  document.getElementById("runBtn").disabled = true;

  const url = `${BACKEND_URL}/stream_decision?message=${encodeURIComponent(input)}&user_id=${encodeURIComponent(USER_ID)}`;
  const eventSource = new EventSource(url);

  // ── SSE LISTENERS ──

  eventSource.addEventListener("agent_start", (e) => {
    const data = JSON.parse(e.data);
    log(`🟡 ${data.agent} — ${data.message || "running..."}`, "running");
  });

  eventSource.addEventListener("agent_complete", (e) => {
    const data = JSON.parse(e.data);
    log(`🟢 ${data.agent} — complete`, "complete");
  });

  eventSource.addEventListener("processing", (e) => {
    const data = JSON.parse(e.data);
    log(`⚙️  ${data.message}`, "processing");
  });

  eventSource.addEventListener("processing_complete", (e) => {
    const data = JSON.parse(e.data);
    log(`✅  ${data.step} — done`, "done");
  });

  eventSource.addEventListener("mcp_start", (e) => {
    const data = JSON.parse(e.data);
    log(`⚡ Executing calendar actions: ${(data.actions || []).join(", ")}`, "mcp");
  });

  eventSource.addEventListener("mcp_action", (e) => {
    const data = JSON.parse(e.data);
    const ok = data.result?.success ? "✅" : "❌";
    log(`  ${ok} ${data.tool}`, "mcp");
  });

  eventSource.addEventListener("mcp_complete", (e) => {
    log("⚡ Calendar actions complete", "mcp");
  });

  eventSource.addEventListener("complete", (e) => {
    const data = JSON.parse(e.data);
    log("🎯 Decision pipeline complete", "complete");
    showFinal(data.decision, data.summary);
    eventSource.close();
    document.getElementById("runBtn").disabled = false;
  });

  eventSource.addEventListener("error", (e) => {
    try {
      const data = JSON.parse(e.data);
      log(`❌ Error at [${data.stage}]: ${data.error}`, "error");
    } catch {
      log("❌ Connection error — check backend is running", "error");
    }
    eventSource.close();
    document.getElementById("runBtn").disabled = false;
  });

  // Fallback: native onerror (fires if EventSource can't connect at all)
  eventSource.onerror = () => {
    log("❌ Could not connect to backend", "error");
    eventSource.close();
    document.getElementById("runBtn").disabled = false;
  };
}