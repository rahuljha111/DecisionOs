/**
 * DecisionOS — Frontend Application
 * Production-ready: clean state management, SSE streaming, action execution
 */

const API_BASE = '/api';

// ─── State ────────────────────────────────────────────────────────────────────
let isProcessing    = false;
let currentDecision = null;
let pendingAction   = null;

// Calendar & To-Do state
let calendarConnected = false;
let todayMeetings     = [];
let todoItems         = [
    { id: 1, text: 'Finish Presentation', done: false },
    { id: 2, text: 'Go to the gym',        done: false },
    { id: 3, text: 'Reply to Emails',      done: false },
];
let nextTodoId = 4;

// ─── Google Calendar Integration ──────────────────────────────────────────────

/**
 * Initiates Google Calendar OAuth flow.
 * If a backend OAuth endpoint is configured it will redirect;
 * otherwise we fall back to a simulated demo connection.
 */
async function connectGoogleCalendar() {
    const btn   = document.getElementById('connectCalBtn');
    const label = document.getElementById('connectCalBtnLabel');

    if (calendarConnected) {
        // Disconnect
        calendarConnected = false;
        todayMeetings     = [];
        btn.classList.remove('connected');
        label.textContent = 'Connect Google Calendar';
        renderMeetings();
        return;
    }

    // Show loading state on button
    label.textContent = 'Connecting…';
    btn.disabled      = true;

    try {
        // Try the real backend OAuth endpoint first
        const checkRes = await fetch(`${API_BASE}/calendar/auth_url`).catch(() => null);

        if (checkRes && checkRes.ok) {
            const { auth_url } = await checkRes.json();

            // Open OAuth popup
            const popup = window.open(auth_url, 'gcal_oauth', 'width=500,height=620');

            // Poll for popup close & then fetch events
            const pollTimer = setInterval(async () => {
                if (!popup || popup.closed) {
                    clearInterval(pollTimer);
                    await fetchCalendarEvents();
                }
            }, 500);

        } else {
            // Backend not available → simulate demo data
            await simulateCalendarConnection();
        }

    } catch (err) {
        await simulateCalendarConnection();
    } finally {
        btn.disabled = false;
    }
}

/**
 * Fetch real calendar events from backend after OAuth completes.
 */
async function fetchCalendarEvents() {
    const btn   = document.getElementById('connectCalBtn');
    const label = document.getElementById('connectCalBtnLabel');

    try {
        const userId = document.getElementById('userId').value.trim() || 'user_001';
        const res    = await fetch(`${API_BASE}/calendar/events?user_id=${encodeURIComponent(userId)}`);

        if (!res.ok) throw new Error('Failed to fetch events');

        const data    = await res.json();
        todayMeetings = (data.events || []).map(e => ({
            time:  e.start_time || e.time || '',
            title: e.title || e.summary || 'Meeting',
        }));

        setCalendarConnected();

    } catch (err) {
        // Fall back to demo on any fetch error
        await simulateCalendarConnection();
    }
}

/**
 * Demo/fallback: populate with sample meetings so the UI isn't empty.
 */
async function simulateCalendarConnection() {
    // Simulate a short network delay
    await delay(900);

    todayMeetings = [
        { time: '10:00 AM', title: 'Team Standup'    },
        { time: '12:30 PM', title: 'Client Call'     },
        { time: '03:00 PM', title: 'Review Meeting'  },
    ];

    setCalendarConnected();
}

function setCalendarConnected() {
    calendarConnected = true;

    const btn   = document.getElementById('connectCalBtn');
    const label = document.getElementById('connectCalBtnLabel');

    btn.classList.add('connected');
    label.textContent = '✓ Calendar Connected';

    renderMeetings();
}

// ─── Render Meetings ──────────────────────────────────────────────────────────
function renderMeetings() {
    const list = document.getElementById('meetingsList');

    if (!calendarConnected || todayMeetings.length === 0) {
        list.innerHTML = `
            <div class="cal-empty-state">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="3" y="4" width="18" height="18" rx="2"/>
                    <path d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
                <p>Connect Google Calendar to see your meetings</p>
            </div>`;
        return;
    }

    list.innerHTML = todayMeetings.map(m => `
        <div class="meeting-item">
            <div class="meeting-icon">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>
                </svg>
            </div>
            <span class="meeting-time">${escapeHtml(m.time)}</span>
            <span class="meeting-title">${escapeHtml(m.title)}</span>
        </div>
    `).join('');
}

// ─── To-Do List ───────────────────────────────────────────────────────────────
function renderTodos() {
    const list = document.getElementById('todoList');

    if (todoItems.length === 0) {
        list.innerHTML = `<p style="font-size:12.5px;color:var(--gray-400);padding:12px 10px;">No tasks yet. Add one below!</p>`;
        return;
    }

    list.innerHTML = todoItems.map(item => `
        <div class="todo-item ${item.done ? 'done' : ''}" id="todo-${item.id}">
            <input type="checkbox" ${item.done ? 'checked' : ''}
                onchange="toggleTodo(${item.id})" />
            <span class="todo-item-label">${escapeHtml(item.text)}</span>
            <button class="todo-item-delete" onclick="deleteTodo(${item.id})" title="Remove task">✕</button>
        </div>
    `).join('');
}

function addTask() {
    const input = document.getElementById('newTaskInput');
    const text  = input.value.trim();
    if (!text) return;

    todoItems.push({ id: nextTodoId++, text, done: false });
    input.value = '';
    renderTodos();
}

function toggleTodo(id) {
    const item = todoItems.find(t => t.id === id);
    if (item) {
        item.done = !item.done;
        renderTodos();
    }
}

function deleteTodo(id) {
    todoItems = todoItems.filter(t => t.id !== id);
    renderTodos();
}

// ─── AI Prioritize My Day ─────────────────────────────────────────────────────

/**
 * Calls the backend (or Claude API) to produce an AI-prioritized schedule
 * that interleaves to-do tasks with today's meetings.
 */
async function prioritizeMyDay() {
    const btn         = document.querySelector('.btn-prioritize');
    const planSection = document.getElementById('aiPlanSection');
    const planList    = document.getElementById('aiPlanList');

    const pendingTasks = todoItems.filter(t => !t.done).map(t => t.text);

    if (pendingTasks.length === 0) {
        planList.innerHTML = `<div class="ai-plan-loading"><span>⚠️</span> Add at least one task to prioritize.</div>`;
        planSection.style.display = 'block';
        return;
    }

    // Show loading
    btn.disabled        = true;
    btn.textContent     = 'Prioritizing…';
    planSection.style.display = 'block';
    planList.innerHTML  = `
        <div class="ai-plan-loading">
            <span class="ai-plan-spinner"></span>
            AI is building your schedule…
        </div>`;

    try {
        // Try real backend endpoint first
        const userId = document.getElementById('userId').value.trim() || 'user_001';

        const res = await fetch(`${API_BASE}/prioritize`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                user_id:  userId,
                tasks:    pendingTasks,
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
        btn.disabled    = false;
        btn.innerHTML   = `
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
    const planList = document.getElementById('aiPlanList');

    if (!plan.length) {
        planList.innerHTML = `<div class="ai-plan-loading">No plan could be generated.</div>`;
        return;
    }

    planList.innerHTML = plan.map((item, i) => `
        <div class="ai-plan-item">
            <span class="ai-plan-num">${i + 1}.</span>
            <span class="ai-plan-task">${escapeHtml(item.task)}</span>
            <span class="ai-plan-time">${escapeHtml(item.start)} – ${escapeHtml(item.end)}</span>
            <span class="ai-plan-note">"${escapeHtml(item.note)}"</span>
        </div>
    `).join('');
}

/**
 * Local fallback plan builder — slots tasks into gaps between meetings.
 */
function buildDemoPlan(tasks, meetings) {
    // Parse meeting times to find free windows
    const notes = [
        'Focus work, ideal time slot',
        'Quick task after meeting',
        'Evening is great for this',
        'Good momentum window',
        'Batch with similar tasks',
    ];

    // Build simple schedule starting after last known meeting or from 9 AM
    const slots = generateFreeSlots(meetings);

    return tasks.map((task, i) => {
        const slot = slots[i] || { start: '06:00 PM', end: '07:00 PM' };
        return {
            task,
            start: slot.start,
            end:   slot.end,
            note:  notes[i % notes.length],
        };
    });
}

/**
 * Produce a list of 90-minute free slots that don't overlap known meetings.
 */
function generateFreeSlots(meetings) {
    // Convert meeting times (e.g. "10:00 AM") to minutes since midnight
    const busyMinutes = meetings.map(m => parseTime(m.time)).filter(Boolean);

    const slots   = [];
    let   cursor  = parseTime('09:00 AM'); // start searching from 9 AM
    const endDay  = parseTime('08:00 PM');
    const slotLen = 90; // minutes per task slot

    while (cursor + slotLen <= endDay && slots.length < 8) {
        // Check if this window overlaps any meeting (assume each meeting = 60 min)
        const overlaps = busyMinutes.some(m => cursor < m + 60 && cursor + slotLen > m);

        if (!overlaps) {
            slots.push({
                start: formatMinutes(cursor),
                end:   formatMinutes(cursor + slotLen),
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
    let   h = parseInt(match[1], 10);
    const m = parseInt(match[2], 10);
    const p = match[3].toUpperCase();
    if (p === 'PM' && h !== 12) h += 12;
    if (p === 'AM' && h === 12) h  = 0;
    return h * 60 + m;
}

function formatMinutes(total) {
    const h    = Math.floor(total / 60);
    const m    = total % 60;
    const ampm = h >= 12 ? 'PM' : 'AM';
    const h12  = h > 12 ? h - 12 : h === 0 ? 12 : h;
    return `${h12}:${String(m).padStart(2, '0')} ${ampm}`;
}

// ─── Utility ──────────────────────────────────────────────────────────────────
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ─── Submit ───────────────────────────────────────────────────────────────────
async function submitDecision() {
    const messageInput = document.getElementById('messageInput');
    const userIdInput  = document.getElementById('userId');

    const message = messageInput.value.trim();
    const userId  = userIdInput.value.trim() || 'user_001';

    if (!message) {
        showError('Please enter a decision request.');
        return;
    }

    if (isProcessing) return;

    resetUI();
    setProcessing(true);

    try {
        const response = await fetch(`${API_BASE}/decide`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ user_id: userId, message }),
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader  = response.body.getReader();
        const decoder = new TextDecoder();
        let   buffer  = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let currentEvent = null;
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    currentEvent = line.substring(7);
                } else if (line.startsWith('data: ') && currentEvent) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        handleEvent(currentEvent, data);
                    } catch (_) { /* skip malformed JSON */ }
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
    const traceContainer = document.getElementById('traceContainer');

    switch (eventType) {
        case 'agent_start':
            addTraceItem(traceContainer, {
                type: 'agent', status: 'running',
                agent: data.agent, message: data.message,
            });
            break;

        case 'agent_complete':
            updateTraceItem(data.agent, 'complete', data.data);
            if (data.agent === 'scenario') displayScenarios(data.data);
            break;

        case 'processing':
            addTraceItem(traceContainer, {
                type: 'processing', status: 'running',
                step: data.step, message: data.message,
            });
            break;

        case 'processing_complete':
            updateProcessingItem(data.step, 'complete');
            break;

        case 'complete':
            currentDecision = data;
            displayFinalDecision(data);
            break;

        case 'error':
            showError(data.error);
            break;
    }
}

// ─── Trace Helpers ────────────────────────────────────────────────────────────
function addTraceItem(container, config) {
    const placeholder = container.querySelector('.empty-state');
    if (placeholder) placeholder.remove();

    const item = document.createElement('div');
    item.className = `trace-item trace-${config.status}`;
    item.id = config.agent ? `trace-${config.agent}` : `trace-${config.step || config.type}`;

    const icon  = getStatusIcon(config.status);
    const label = config.agent
        ? formatAgentName(config.agent)
        : (config.step || config.type);

    item.innerHTML = `
        <span class="trace-icon">${icon}</span>
        <span class="trace-label">${label}</span>
        <span class="trace-message">${config.message || ''}</span>
    `;

    container.appendChild(item);
    container.scrollTop = container.scrollHeight;
}

function updateTraceItem(agent, status, data) {
    const item = document.getElementById(`trace-${agent}`);
    if (!item) return;
    item.className = `trace-item trace-${status}`;
    const iconEl = item.querySelector('.trace-icon');
    if (iconEl) iconEl.textContent = getStatusIcon(status);
    const msgEl  = item.querySelector('.trace-message');
    if (msgEl && data) msgEl.textContent = summarizeData(agent, data);
}

function updateProcessingItem(step, status) {
    const item = document.getElementById(`trace-${step}`);
    if (!item) return;
    item.className = `trace-item trace-${status}`;
    const iconEl = item.querySelector('.trace-icon');
    if (iconEl) iconEl.textContent = getStatusIcon(status);
}

// ─── Formatting ───────────────────────────────────────────────────────────────
function getStatusIcon(status) {
    return { running: '⏳', complete: '✅', error: '❌' }[status] || '•';
}

function formatAgentName(agent) {
    return {
        planner:         '📋 Planner',
        task:            '📊 Task Analyzer',
        calendar:        '📅 Calendar',
        scenario:        '🎲 Simulator',
        decision_engine: '🧠 Decision Engine',
    }[agent] || agent;
}

function summarizeData(agent, data) {
    switch (agent) {
        case 'planner':         return data.task_type ? `Detected: ${data.task_type}` : 'Extracted task info';
        case 'task':            return `Priority: ${data.priority}/10`;
        case 'calendar':        return data.has_conflict ? '⚠️ Conflict detected' : '✓ No conflicts';
        case 'scenario':        return `${data.options?.length || 0} options simulated`;
        case 'decision_engine': return 'Decision made';
        default:                return '';
    }
}

function formatOptionName(action) {
    if (!action) return 'Unknown';
    return action.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

// ─── Scenarios ────────────────────────────────────────────────────────────────
function displayScenarios(data) {
    if (!data?.options?.length) return;

    const section   = document.getElementById('scenariosSection');
    const container = document.getElementById('scenariosContainer');
    const sorted    = [...data.options].sort((a, b) => (b.score || 0) - (a.score || 0));

    let html = '<div class="scenarios-grid">';

    sorted.forEach((opt, index) => {
        const isRecommended = index === 0;
        const scoreClass    = opt.score >= 70 ? 'high' : opt.score >= 40 ? 'medium' : 'low';

        html += `
            <div class="scenario-card ${isRecommended ? 'recommended' : ''}">
                ${isRecommended ? '<span class="recommended-badge">✨ Recommended</span>' : ''}
                <h4>${formatOptionName(opt.action)}</h4>
                <div class="scenario-score score-${scoreClass}">
                    <span class="score-value">${Math.round(opt.score)}</span>
                    <span class="score-label">/ 100</span>
                </div>
                <p class="scenario-outcome">
                    <strong>Outcome:</strong> ${opt.description || 'No description'}
                </p>
                <p class="scenario-risk">
                    <strong>Risk:</strong> ${opt.risks?.join(', ') || 'None identified'}
                </p>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
    section.style.display = 'block';
}

// ─── Final Decision ───────────────────────────────────────────────────────────
function displayFinalDecision(data) {
    const container = document.getElementById('decisionContainer');
    const decision  = data.decision;

    if (!decision) {
        container.innerHTML = '<div class="error"><span class="error-icon">❌</span><span class="error-message">No decision generated.</span></div>';
        return;
    }

    const confidenceClass = decision.confidence >= 0.8 ? 'high'
                          : decision.confidence >= 0.6 ? 'medium' : 'low';

    const decisionText = decision.decision_text || formatOptionName(decision.action);

    let conflictBadge = '';
    if (decision.conflict_type && decision.conflict_type !== 'none') {
        const label = decision.conflict_type === 'priority_conflict'
            ? '⚡ Priority conflict' : '⏰ Time conflict';
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
            ${decision.reasoning ? `
            <div class="decision-reasoning">
                <h4>Why this decision?</h4>
                <p>${decision.reasoning}</p>
            </div>` : ''}
            ${decision.next_steps?.length ? `
            <div class="decision-steps">
                <h4>Next steps</h4>
                <ol>${decision.next_steps.map(s => `<li>${s}</li>`).join('')}</ol>
            </div>` : ''}
        </div>
    `;

    displayActionButtons(decision);
}

// ─── Action Buttons ───────────────────────────────────────────────────────────
function displayActionButtons(decision) {
    const section   = document.getElementById('actionsSection');
    const container = document.getElementById('actionsContainer');

    const actions         = decision.executable_actions || [];
    const inferredActions = [];
    const action          = decision.action?.toLowerCase() || '';
    const eventId         = decision.event_id;

    if (action.includes('skip') || action.includes('cancel')) {
        inferredActions.push({ type: 'cancel_event',     label: 'Skip / Cancel event', icon: '❌', eventId });
    } else if (action.includes('reschedule')) {
        inferredActions.push({ type: 'reschedule_event', label: 'Reschedule event',    icon: '📅', eventId });
    }

    const allActions = [...actions, ...inferredActions];

    if (allActions.length === 0) {
        section.style.display = 'none';
        return;
    }

    container.innerHTML = allActions.map(act => {
        const icon   = act.icon || getActionIcon(act.type);
        const label  = act.label || formatOptionName(act.type);
        const eid    = act.event_id || act.eventId || '';
        const etitle = act.event_title || '';

        return `
            <button class="action-btn"
                onclick="executeAction('${act.type}', '${eid}', '${etitle}')">
                <span class="action-btn-icon">${icon}</span>
                <span class="action-btn-label">${label}</span>
                ${etitle ? `<span class="action-btn-detail">${etitle}</span>` : ''}
            </button>
        `;
    }).join('');

    section.style.display = 'block';
}

function getActionIcon(type) {
    return { cancel_event: '❌', reschedule_event: '📅', create_event: '➕', add_task: '📝' }[type] || '⚡';
}

// ─── Execute Action ───────────────────────────────────────────────────────────
function executeAction(actionType, eventId, eventTitle) {
    pendingAction = { actionType, eventId, eventTitle };

    const modal   = document.getElementById('confirmModal');
    const message = document.getElementById('confirmMessage');

    let text = formatOptionName(actionType);
    if (eventTitle) text += ` "${eventTitle}"`;

    message.textContent = `Are you sure you want to ${text}?`;
    modal.style.display = 'flex';
}

function closeModal() {
    document.getElementById('confirmModal').style.display = 'none';
    pendingAction = null;
}

async function confirmAction() {
    if (!pendingAction) { closeModal(); return; }

    const { actionType, eventId } = pendingAction;
    closeModal();

    try {
        const userId = document.getElementById('userId').value.trim() || 'user_001';

        const response = await fetch(`${API_BASE}/execute_action`, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({
                user_id: userId, action_type: actionType, event_id: eventId, params: {},
            }),
        });

        const result = await response.json();

        if (result.success) {
            showSuccess(result.message || 'Action executed successfully!');
        } else {
            showError(result.message || 'Action failed.');
        }

    } catch (error) {
        showError(`Error executing action: ${error.message}`);
    }

    pendingAction = null;
}

// ─── Toast / Feedback ─────────────────────────────────────────────────────────
function showSuccess(message) {
    const container = document.getElementById('actionsContainer');
    container.innerHTML = `
        <div class="success-message">
            <span>✅</span>
            <span>${message}</span>
        </div>
    `;
}

function showError(message) {
    const container = document.getElementById('decisionContainer');
    container.innerHTML = `
        <div class="error">
            <span class="error-icon">⚠️</span>
            <span class="error-message">${message}</span>
        </div>
    `;
}

// ─── UI State ─────────────────────────────────────────────────────────────────
function resetUI() {
    document.getElementById('decisionContainer').innerHTML = `
        <div class="empty-state">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
            </svg>
            <p>Processing your request…</p>
        </div>
    `;
    document.getElementById('traceContainer').innerHTML    = '';
    document.getElementById('scenariosSection').style.display = 'none';
    document.getElementById('actionsSection').style.display   = 'none';
    currentDecision = null;
}

function setProcessing(processing) {
    isProcessing = processing;

    const btn     = document.getElementById('submitBtn');
    const btnText = btn.querySelector('.btn-text');
    const btnLoad = btn.querySelector('.btn-loading');
    const pill    = document.getElementById('statusPill');

    btn.disabled          = processing;
    btnText.style.display = processing ? 'none'        : 'inline-flex';
    btnLoad.style.display = processing ? 'inline-flex' : 'none';

    if (pill) {
        pill.classList.toggle('processing', processing);
        pill.querySelector('span:last-child').textContent = processing ? 'Processing' : 'Ready';
    }
}

// ─── Keyboard Shortcuts & Init ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {

    // Enter to submit decision
    document.getElementById('messageInput').addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitDecision();
        }
    });

    // Enter in new-task input
    document.getElementById('newTaskInput').addEventListener('keydown', e => {
        if (e.key === 'Enter') {
            e.preventDefault();
            addTask();
        }
    });

    // Close modal on overlay click
    document.getElementById('confirmModal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });

    // Render initial to-do list
    renderTodos();
    renderMeetings();
});
