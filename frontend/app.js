/**
 * DecisionOS Frontend Application
 * Clean, human-readable UI with action execution
 */

// API Base URL
const API_BASE = '/api';

// State
let isProcessing = false;
let currentDecision = null;
let pendingAction = null;

/**
 * Submit decision request
 */
async function submitDecision() {
    const messageInput = document.getElementById('messageInput');
    const userIdInput = document.getElementById('userId');
    
    const message = messageInput.value.trim();
    const userId = userIdInput.value.trim() || 'user_001';
    
    if (!message) {
        showError('Please enter a decision request');
        return;
    }
    
    if (isProcessing) {
        return;
    }
    
    // Reset UI
    resetUI();
    setProcessing(true);
    
    // Connect to SSE endpoint
    try {
        const response = await fetch(`${API_BASE}/decide`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_id: userId,
                message: message
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        // Process SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            
            // Process complete events
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
                    } catch (e) {
                        // Skip invalid JSON
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

/**
 * Handle SSE event
 */
function handleEvent(eventType, data) {
    const traceContainer = document.getElementById('traceContainer');
    
    switch (eventType) {
        case 'agent_start':
            addTraceItem(traceContainer, {
                type: 'agent',
                status: 'running',
                agent: data.agent,
                message: data.message
            });
            break;
            
        case 'agent_complete':
            updateTraceItem(data.agent, 'complete', data.data);
            if (data.agent === 'scenario') {
                displayScenarios(data.data);
            }
            break;
            
        case 'processing':
            addTraceItem(traceContainer, {
                type: 'processing',
                status: 'running',
                step: data.step,
                message: data.message
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

/**
 * Add trace item to container
 */
function addTraceItem(container, config) {
    // Remove placeholder if exists
    const placeholder = container.querySelector('.trace-placeholder');
    if (placeholder) {
        placeholder.remove();
    }
    
    const item = document.createElement('div');
    item.className = `trace-item trace-${config.status}`;
    item.id = config.agent ? `trace-${config.agent}` : `trace-${config.step || config.type}`;
    
    const icon = getStatusIcon(config.status);
    const label = config.agent ? formatAgentName(config.agent) : (config.step || config.type);
    
    item.innerHTML = `
        <span class="trace-icon">${icon}</span>
        <span class="trace-label">${label}</span>
        <span class="trace-message">${config.message || ''}</span>
    `;
    
    container.appendChild(item);
    container.scrollTop = container.scrollHeight;
}

/**
 * Update existing trace item
 */
function updateTraceItem(agent, status, data) {
    const item = document.getElementById(`trace-${agent}`);
    if (item) {
        item.className = `trace-item trace-${status}`;
        const icon = item.querySelector('.trace-icon');
        if (icon) {
            icon.textContent = getStatusIcon(status);
        }
        
        const message = item.querySelector('.trace-message');
        if (message && data) {
            message.textContent = summarizeData(agent, data);
        }
    }
}

/**
 * Update processing item
 */
function updateProcessingItem(step, status) {
    const item = document.getElementById(`trace-${step}`);
    if (item) {
        item.className = `trace-item trace-${status}`;
        const icon = item.querySelector('.trace-icon');
        if (icon) {
            icon.textContent = getStatusIcon(status);
        }
    }
}

/**
 * Get status icon
 */
function getStatusIcon(status) {
    const icons = {
        'running': '⏳',
        'complete': '✅',
        'error': '❌'
    };
    return icons[status] || '•';
}

/**
 * Format agent name for display
 */
function formatAgentName(agent) {
    const names = {
        'planner': '📋 Planner',
        'task': '📊 Task Analyzer',
        'calendar': '📅 Calendar',
        'scenario': '🎲 Simulator',
        'decision_engine': '🧠 Decision Engine'
    };
    return names[agent] || agent;
}

/**
 * Summarize agent data for trace display
 */
function summarizeData(agent, data) {
    switch (agent) {
        case 'planner':
            return data.task_type ? `Detected: ${data.task_type}` : 'Extracted task info';
        case 'task':
            return `Priority: ${data.priority}/10`;
        case 'calendar':
            return data.has_conflict ? `⚠️ Conflict detected` : '✓ No conflicts';
        case 'scenario':
            return `${data.options?.length || 0} options simulated`;
        case 'decision_engine':
            return `Decision made`;
        default:
            return '';
    }
}

/**
 * Display scenarios in human-friendly format
 */
function displayScenarios(data) {
    if (!data || !data.options || data.options.length === 0) {
        return;
    }
    
    const section = document.getElementById('scenariosSection');
    const container = document.getElementById('scenariosContainer');
    
    // Sort by score descending
    const sortedOptions = [...data.options].sort((a, b) => (b.score || 0) - (a.score || 0));
    
    let html = '<div class="scenarios-grid">';
    
    sortedOptions.forEach((opt, index) => {
        const isRecommended = index === 0;
        const scoreClass = opt.score >= 70 ? 'high' : opt.score >= 40 ? 'medium' : 'low';
        
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

/**
 * Format option name for display
 */
function formatOptionName(action) {
    if (!action) return 'Unknown';
    return action
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase());
}

/**
 * Display final decision
 */
function displayFinalDecision(data) {
    const container = document.getElementById('decisionContainer');
    const decision = data.decision;
    const summary = data.summary;
    
    if (!decision) {
        container.innerHTML = '<div class="error">No decision generated</div>';
        return;
    }
    
    const confidenceClass = decision.confidence >= 0.8 ? 'high' : 
                           decision.confidence >= 0.6 ? 'medium' : 'low';
    
    // Use decision_text if available, otherwise format action
    const decisionText = decision.decision_text || formatOptionName(decision.action);
    
    // Determine conflict badge
    let conflictBadge = '';
    if (decision.conflict_type && decision.conflict_type !== 'none') {
        const conflictLabel = decision.conflict_type === 'priority_conflict' ? 
            '⚡ Priority Conflict' : '⏰ Time Conflict';
        conflictBadge = `<span class="conflict-badge">${conflictLabel}</span>`;
    }
    
    container.innerHTML = `
        <div class="decision-result">
            <div class="decision-action">
                <span class="action-icon">🎯</span>
                <span class="action-text">${decisionText}</span>
            </div>
            
            ${conflictBadge}
            
            <div class="decision-confidence confidence-${confidenceClass}">
                <span class="confidence-label">Confidence:</span>
                <span class="confidence-value">${Math.round(decision.confidence * 100)}%</span>
                <div class="confidence-bar">
                    <div class="confidence-fill" style="width: ${decision.confidence * 100}%"></div>
                </div>
            </div>
            
            <div class="decision-reasoning">
                <h4>Why this decision?</h4>
                <p>${decision.reasoning}</p>
            </div>
            
            ${decision.next_steps?.length ? `
            <div class="decision-steps">
                <h4>Next Steps</h4>
                <ol>
                    ${decision.next_steps.map(step => `<li>${step}</li>`).join('')}
                </ol>
            </div>
            ` : ''}
        </div>
    `;
    
    // Display action buttons if available
    displayActionButtons(decision);
}

/**
 * Display executable action buttons
 */
function displayActionButtons(decision) {
    const section = document.getElementById('actionsSection');
    const container = document.getElementById('actionsContainer');
    
    // Get actions from decision
    const actions = decision.executable_actions || [];
    
    // Also infer actions from the decision action
    const inferredActions = [];
    const action = decision.action?.toLowerCase() || '';
    const eventId = decision.event_id;
    
    if (action.includes('skip') || action.includes('cancel')) {
        inferredActions.push({
            type: 'cancel_event',
            label: 'Skip/Cancel Event',
            icon: '❌',
            eventId: eventId
        });
    } else if (action.includes('reschedule')) {
        inferredActions.push({
            type: 'reschedule_event',
            label: 'Reschedule Event',
            icon: '📅',
            eventId: eventId
        });
    }
    
    // Combine explicit and inferred actions
    const allActions = [...actions, ...inferredActions];
    
    if (allActions.length === 0) {
        section.style.display = 'none';
        return;
    }
    
    let html = '';
    allActions.forEach(act => {
        const icon = act.icon || getActionIcon(act.type);
        const label = act.label || formatOptionName(act.type);
        
        html += `
            <button class="action-btn" onclick="executeAction('${act.type}', '${act.event_id || act.eventId || ''}', '${act.event_title || ''}')">
                <span class="action-btn-icon">${icon}</span>
                <span class="action-btn-label">${label}</span>
                ${act.event_title ? `<span class="action-btn-detail">${act.event_title}</span>` : ''}
            </button>
        `;
    });
    
    container.innerHTML = html;
    section.style.display = 'block';
}

/**
 * Get icon for action type
 */
function getActionIcon(type) {
    const icons = {
        'cancel_event': '❌',
        'reschedule_event': '📅',
        'create_event': '➕',
        'add_task': '📝'
    };
    return icons[type] || '⚡';
}

/**
 * Execute an action (shows confirmation first)
 */
function executeAction(actionType, eventId, eventTitle) {
    pendingAction = { actionType, eventId, eventTitle };
    
    const modal = document.getElementById('confirmModal');
    const message = document.getElementById('confirmMessage');
    
    let actionText = formatOptionName(actionType);
    if (eventTitle) {
        actionText += ` "${eventTitle}"`;
    }
    
    message.textContent = `Are you sure you want to ${actionText}?`;
    modal.style.display = 'flex';
}

/**
 * Close confirmation modal
 */
function closeModal() {
    const modal = document.getElementById('confirmModal');
    modal.style.display = 'none';
    pendingAction = null;
}

/**
 * Confirm and execute the pending action
 */
async function confirmAction() {
    if (!pendingAction) {
        closeModal();
        return;
    }
    
    const { actionType, eventId, eventTitle } = pendingAction;
    closeModal();
    
    try {
        const userId = document.getElementById('userId').value.trim() || 'user_001';
        
        const response = await fetch(`${API_BASE}/execute_action`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_id: userId,
                action_type: actionType,
                event_id: eventId,
                params: {}
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showSuccess(result.message || 'Action executed successfully!');
        } else {
            showError(result.message || 'Action failed');
        }
        
    } catch (error) {
        showError(`Error executing action: ${error.message}`);
    }
    
    pendingAction = null;
}

/**
 * Show success message
 */
function showSuccess(message) {
    const container = document.getElementById('actionsContainer');
    container.innerHTML = `
        <div class="success-message">
            <span class="success-icon">✅</span>
            <span>${message}</span>
        </div>
    `;
}

/**
 * Show error message
 */
function showError(message) {
    const container = document.getElementById('decisionContainer');
    container.innerHTML = `
        <div class="error">
            <span class="error-icon">❌</span>
            <span class="error-message">${message}</span>
        </div>
    `;
}

/**
 * Reset UI state
 */
function resetUI() {
    document.getElementById('decisionContainer').innerHTML = `
        <div class="decision-placeholder">
            Processing your request...
        </div>
    `;
    document.getElementById('traceContainer').innerHTML = '';
    document.getElementById('scenariosSection').style.display = 'none';
    document.getElementById('actionsSection').style.display = 'none';
    currentDecision = null;
}

/**
 * Set processing state
 */
function setProcessing(processing) {
    isProcessing = processing;
    const submitBtn = document.getElementById('submitBtn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoading = submitBtn.querySelector('.btn-loading');
    
    if (processing) {
        submitBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoading.style.display = 'inline';
    } else {
        submitBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

// Handle Enter key in textarea
document.addEventListener('DOMContentLoaded', function() {
    const messageInput = document.getElementById('messageInput');
    messageInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitDecision();
        }
    });
});
