const state = {
  messages: [],
  selectedMessageId: null,
  loadingMessageId: null,
  expandedToolCalls: {},
};

const messageList       = document.getElementById("messageList");
const questionInput     = document.getElementById("questionInput");
const sendButton        = document.getElementById("sendButton");
const statusPill        = document.getElementById("statusPill");
const statusText        = document.getElementById("statusText");
const detailsEmpty      = document.getElementById("detailsEmpty");
const detailsContent    = document.getElementById("detailsContent");
const confidenceValue   = document.getElementById("confidenceValue");
const confidenceBarFill = document.getElementById("confidenceBarFill");
const traceIdButton     = document.getElementById("traceIdButton");
const failureBadge      = document.getElementById("failureBadge");
const detailTimestamp   = document.getElementById("detailTimestamp");
const toolTimeline      = document.getElementById("toolTimeline");
const toolCallCount     = document.getElementById("toolCallCount");
const historyButton     = document.getElementById("historyButton");
const clearChatButton   = document.getElementById("clearChatButton");
const closeHistoryButton = document.getElementById("closeHistoryButton");
const historyDrawer     = document.getElementById("historyDrawer");
const drawerBackdrop    = document.getElementById("drawerBackdrop");
const historyList       = document.getElementById("historyList");
const suggestionRow     = document.getElementById("suggestionRow");
const hintSummary       = document.getElementById("hintSummary");
const charCount         = document.getElementById("charCount");
const chatColumnEl      = document.getElementById("chatColumn");
const detailsColumnEl   = document.getElementById("detailsColumn");
const sendLabel         = sendButton.querySelector(".send-label");

const starterMessage = {
  role: "agent",
  content:
    "Start with a stock question, a schema-routing question, or anything that needs tool-backed analysis. Click any reply to inspect the evidence on the right.",
  result: {
    answer: "",
    confidence: 0.92,
    trace_id: "ready",
    tool_calls: [],
    failure_count: 0,
  },
};

marked.setOptions({ breaks: true, gfm: true });

// ==========================================
// Utilities
// ==========================================

function createId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function getSelectedHints() {
  return Array.from(document.querySelectorAll('#hintGroup input[type="checkbox"]:checked')).map(
    (input) => input.value,
  );
}

function formatTimestamp(value) {
  if (!value) return "Just now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function autoResizeTextarea() {
  questionInput.style.height = "auto";
  questionInput.style.height = `${Math.min(questionInput.scrollHeight, 180)}px`;
}

function updateComposerMeta() {
  charCount.textContent = `${questionInput.value.length} / 4096`;
  const hints = getSelectedHints();
  hintSummary.innerHTML = "";
  const labels = hints.length ? hints : ["no db hints"];
  labels.forEach((hint) => {
    const pill = document.createElement("span");
    pill.className = "hint-pill";
    pill.textContent = hint;
    hintSummary.appendChild(pill);
  });
}

function shouldStickToBottom() {
  const threshold = 96;
  return messageList.scrollHeight - messageList.scrollTop - messageList.clientHeight < threshold;
}

function scrollToLatest(force = false) {
  if (force || shouldStickToBottom()) {
    messageList.scrollTop = messageList.scrollHeight;
  }
}

function shouldCollapseMessage(message) {
  if (!message || message.role !== "agent" || message.loading) return false;
  const content = message.content || "";
  return content.length > 420 || (content.match(/\n/g) || []).length > 8;
}

function confidenceColor(confidence) {
  if (confidence > 0.8) return "var(--green)";
  if (confidence > 0.5) return "var(--yellow)";
  return "var(--red)";
}

// ==========================================
// Mobile Panel Switching
// ==========================================

const mobileTabs = document.querySelectorAll(".mobile-tab");

function setMobilePanel(panel) {
  mobileTabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.panel === panel));
  chatColumnEl.classList.toggle("mobile-active", panel === "chat");
  detailsColumnEl.classList.toggle("mobile-active", panel === "details");
}

mobileTabs.forEach((tab) => tab.addEventListener("click", () => setMobilePanel(tab.dataset.panel)));

// ==========================================
// Message Rendering
// ==========================================

function renderMessages() {
  const stickToBottom = shouldStickToBottom();
  messageList.innerHTML = "";

  state.messages.forEach((message, index) => {
    const prev = index > 0 ? state.messages[index - 1] : null;
    const isFirstInGroup = !prev || prev.role !== message.role;

    const wrapper = document.createElement("article");
    wrapper.className = `message ${message.role}`;
    if (isFirstInGroup) wrapper.classList.add("first-in-group");
    if (message.id === state.selectedMessageId) wrapper.classList.add("selected");

    if (message.role === "agent" && !message.loading) {
      wrapper.tabIndex = 0;
      wrapper.addEventListener("click", () => selectMessage(message.id));
      wrapper.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectMessage(message.id);
        }
      });
    }

    if (isFirstInGroup) {
      const meta = document.createElement("div");
      meta.className = "message-meta";
      meta.textContent = `${message.role === "user" ? "You" : "OracleForge"} · ${formatTimestamp(message.timestamp)}`;
      wrapper.appendChild(meta);
    }

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    const body = document.createElement("div");
    body.className = "message-body";

    if (message.loading) {
      body.innerHTML = `
        <div class="loading">
          <div class="typing-dots" aria-label="Thinking">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
          </div>
          <span>Thinking through the query plan</span>
        </div>`;
    } else if (message.role === "agent") {
      body.innerHTML = DOMPurify.sanitize(marked.parse(message.content || ""));
    } else {
      body.textContent = message.content;
    }

    if (!message.loading && shouldCollapseMessage(message) && !message.expanded) {
      body.classList.add("collapsed");
    }
    bubble.appendChild(body);
    wrapper.appendChild(bubble);

    if (message.role === "agent" && !message.loading) {
      const actions = document.createElement("div");
      actions.className = "message-actions";

      const inspectBtn = document.createElement("button");
      inspectBtn.className = "message-action";
      inspectBtn.type = "button";
      inspectBtn.textContent = "Inspect";
      inspectBtn.addEventListener("click", (e) => { e.stopPropagation(); selectMessage(message.id); });

      const copyBtn = document.createElement("button");
      copyBtn.className = "message-action";
      copyBtn.type = "button";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(message.content || "");
          copyBtn.textContent = "Copied ✓";
          setTimeout(() => { copyBtn.textContent = "Copy"; }, 1400);
        } catch {
          copyBtn.textContent = "Failed";
          setTimeout(() => { copyBtn.textContent = "Copy"; }, 1400);
        }
      });

      actions.append(inspectBtn, copyBtn);

      if (shouldCollapseMessage(message)) {
        const toggleBtn = document.createElement("button");
        toggleBtn.className = "message-action";
        toggleBtn.type = "button";
        toggleBtn.textContent = message.expanded ? "Show less" : "Show more";
        toggleBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          toggleMessageExpanded(message.id);
        });
        actions.appendChild(toggleBtn);
      }

      wrapper.appendChild(actions);
    }

    messageList.appendChild(wrapper);
  });

  document.querySelectorAll("pre code").forEach((block) => hljs.highlightElement(block));
  suggestionRow.style.display = state.messages.length > 1 ? "none" : "flex";
  scrollToLatest(!stickToBottom);
  renderDetails();
}

function selectMessage(messageId) {
  state.selectedMessageId = messageId;
  if (window.innerWidth <= 768) {
    setMobilePanel("details");
  }
  renderMessages();
}

function toggleMessageExpanded(messageId) {
  const message = state.messages.find((m) => m.id === messageId);
  if (!message) return;
  message.expanded = !message.expanded;
  renderMessages();
}

function getSelectedMessage() {
  return state.messages.find((m) => m.id === state.selectedMessageId) || null;
}

// ==========================================
// Details Panel
// ==========================================

function renderDetails() {
  const selected = getSelectedMessage();
  if (!selected || selected.role !== "agent" || selected.loading || !selected.result) {
    detailsEmpty.classList.remove("hidden");
    detailsContent.classList.add("hidden");
    return;
  }

  detailsEmpty.classList.add("hidden");
  detailsContent.classList.remove("hidden");

  const confidence = Number(selected.result.confidence || 0);
  const pct = Math.round(confidence * 100);
  confidenceValue.textContent = `${pct}%`;
  confidenceBarFill.style.width  = `${Math.max(0, Math.min(confidence, 1)) * 100}%`;
  confidenceBarFill.style.background = confidenceColor(confidence);

  traceIdButton.textContent = selected.result.trace_id || "No trace";
  failureBadge.textContent  = String(selected.result.failure_count ?? 0);
  detailTimestamp.textContent = formatTimestamp(selected.timestamp);

  const toolCalls = Array.isArray(selected.result.tool_calls) ? selected.result.tool_calls : [];
  toolCallCount.textContent = String(toolCalls.length);
  toolTimeline.innerHTML = "";

  if (!toolCalls.length) {
    const emptyCard = document.createElement("div");
    emptyCard.className = "tool-card";
    emptyCard.style.cssText = "padding:12px 13px; color:var(--muted); font-size:0.84rem;";
    emptyCard.textContent = "No tool calls were recorded for this response.";
    toolTimeline.appendChild(emptyCard);
    return;
  }

  toolCalls.forEach((call, index) => {
    const card = document.createElement("div");
    const callKey = `${selected.id}-${index}`;
    const expanded = state.expandedToolCalls[callKey] ?? index === 0;

    card.className = `tool-card ${call.success ? "success-card" : "failed-card"}`;
    if (expanded) card.classList.add("expanded");

    const params  = call.params || {};
    const sql     = typeof params.sql === "string" ? params.sql : JSON.stringify(params, null, 2);
    const summary = sql.split("\n")[0].slice(0, 120);
    const statusClass = call.success ? "tool-status success" : "tool-status";
    const statusLabel = call.success ? "Success" : "Failed";

    card.innerHTML = `
      <button class="tool-trigger" type="button" aria-expanded="${expanded}">
        <div class="tool-trigger-main">
          <div class="tool-title">${escapeHtml(call.tool_name || `Tool ${index + 1}`)}</div>
          <div class="${statusClass}">${statusLabel}</div>
          <div class="tool-summary">${escapeHtml(summary || "{}")}</div>
        </div>
        <div class="tool-trigger-side">
          <span class="message-meta">#${index + 1}</span>
          <span class="tool-chevron">▸</span>
        </div>
      </button>
      ${expanded ? `
      <div class="tool-details">
        <span class="tool-params-label">Parameters</span>
        <pre><code class="language-sql">${escapeHtml(sql || "{}")}</code></pre>
      </div>` : ""}
    `;

    card.querySelector(".tool-trigger").addEventListener("click", () => {
      state.expandedToolCalls[callKey] = !expanded;
      renderDetails();
    });

    toolTimeline.appendChild(card);
  });

  toolTimeline.querySelectorAll("pre code").forEach((block) => hljs.highlightElement(block));
}

// ==========================================
// State Management
// ==========================================

function addMessage(message) {
  state.messages.push(message);
  renderMessages();
}

function updateMessage(messageId, updates) {
  const message = state.messages.find((m) => m.id === messageId);
  if (!message) return;
  Object.assign(message, updates);
  renderMessages();
}

function resetChat() {
  state.messages = [{
    id: createId("agent"),
    timestamp: new Date().toISOString(),
    expanded: false,
    ...starterMessage,
  }];
  state.selectedMessageId = state.messages[0].id;
  renderMessages();
  questionInput.value = "";
  autoResizeTextarea();
  updateComposerMeta();
  questionInput.focus();
}

// ==========================================
// API: Send Message
// ==========================================

async function sendMessage(prefillQuestion = null) {
  const question = (prefillQuestion ?? questionInput.value).trim();
  if (!question || state.loadingMessageId) return;

  const dbHints         = getSelectedHints();
  const timestamp       = new Date().toISOString();
  const userMessageId   = createId("user");
  const loadingMessageId = createId("agent");

  addMessage({ id: userMessageId, role: "user", content: question, timestamp });
  addMessage({ id: loadingMessageId, role: "agent", content: "", timestamp, loading: true, expanded: false });

  state.loadingMessageId  = loadingMessageId;
  state.selectedMessageId = loadingMessageId;
  sendButton.disabled = true;
  if (sendLabel) sendLabel.textContent = "Sending…";
  questionInput.value = "";
  autoResizeTextarea();
  updateComposerMeta();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, db_hints: dbHints }),
    });

    if (!response.ok) throw new Error(`Request failed with status ${response.status}`);

    const result = await response.json();
    updateMessage(loadingMessageId, {
      content: result.answer || "No answer returned.",
      loading: false,
      result,
      timestamp: new Date().toISOString(),
      expanded: false,
    });
    state.selectedMessageId = loadingMessageId;
    renderMessages();
    loadHistory();
  } catch (error) {
    updateMessage(loadingMessageId, {
      content: `I hit an API error.\n\n\`\`\`\n${error.message}\n\`\`\``,
      loading: false,
      result: { answer: "", confidence: 0, trace_id: "", tool_calls: [], failure_count: 1 },
      timestamp: new Date().toISOString(),
      expanded: false,
    });
    state.selectedMessageId = loadingMessageId;
    renderMessages();
  } finally {
    state.loadingMessageId = null;
    sendButton.disabled = false;
    if (sendLabel) sendLabel.textContent = "Send";
    questionInput.focus();
    checkHealth();
  }
}

// ==========================================
// API: Health & History
// ==========================================

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("unhealthy");
    await response.json();
    statusPill.classList.add("healthy");
    statusPill.classList.remove("unhealthy");
    statusText.textContent = "API healthy";
  } catch {
    statusPill.classList.add("unhealthy");
    statusPill.classList.remove("healthy");
    statusText.textContent = "API unavailable";
  }
}

async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    if (!response.ok) throw new Error("history unavailable");
    const payload  = await response.json();
    const sessions = Array.isArray(payload.sessions) ? payload.sessions : [];
    historyList.innerHTML = "";

    if (!sessions.length) {
      const empty = document.createElement("div");
      empty.className = "history-item";
      empty.style.cssText = "color:var(--muted); font-size:0.84rem; cursor:default;";
      empty.textContent = "No sessions recorded yet.";
      historyList.appendChild(empty);
      return;
    }

    sessions.forEach((session) => {
      const pct       = Math.round((session.confidence || 0) * 100);
      const confClass = pct > 80 ? "high" : pct > 50 ? "medium" : "low";
      const item      = document.createElement("article");
      item.className  = "history-item";
      item.innerHTML  = `
        <div class="history-top">
          <strong>${escapeHtml(session.question || "Untitled session")}</strong>
          <span class="history-confidence ${confClass}">${pct}%</span>
        </div>
        <p>${escapeHtml(session.answer || "No answer preview available.")}</p>
        <p class="message-meta">${formatTimestamp(session.timestamp)}</p>
      `;
      item.addEventListener("click", () => {
        questionInput.value = session.question || "";
        autoResizeTextarea();
        updateComposerMeta();
        closeHistory();
        questionInput.focus();
      });
      historyList.appendChild(item);
    });
  } catch {
    historyList.innerHTML = '<div class="history-item" style="color:var(--muted);font-size:0.84rem;cursor:default;">Unable to load history right now.</div>';
  }
}

function openHistory() {
  historyDrawer.classList.add("open");
  drawerBackdrop.classList.add("open");
  historyDrawer.setAttribute("aria-hidden", "false");
}

function closeHistory() {
  historyDrawer.classList.remove("open");
  drawerBackdrop.classList.remove("open");
  historyDrawer.setAttribute("aria-hidden", "true");
}

// ==========================================
// Event Listeners
// ==========================================

traceIdButton.addEventListener("click", async () => {
  const value = traceIdButton.textContent.trim();
  if (!value || value === "No trace") return;
  try {
    await navigator.clipboard.writeText(value);
    traceIdButton.textContent = "Copied ✓";
    setTimeout(() => {
      const sel = getSelectedMessage();
      traceIdButton.textContent = sel?.result?.trace_id || "No trace";
    }, 1400);
  } catch {
    // Clipboard access denied silently.
  }
});

questionInput.addEventListener("input", () => {
  autoResizeTextarea();
  updateComposerMeta();
});

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});

document.querySelectorAll('#hintGroup input[type="checkbox"]').forEach((input) => {
  input.addEventListener("change", updateComposerMeta);
});

sendButton.addEventListener("click", () => sendMessage());
clearChatButton.addEventListener("click", resetChat);
historyButton.addEventListener("click", openHistory);
closeHistoryButton.addEventListener("click", closeHistory);
drawerBackdrop.addEventListener("click", closeHistory);

suggestionRow.addEventListener("click", (event) => {
  const button = event.target.closest(".suggestion-chip");
  if (!button) return;
  sendMessage(button.textContent.trim());
});

// ==========================================
// Init
// ==========================================

setMobilePanel("chat");
resetChat();
autoResizeTextarea();
updateComposerMeta();
checkHealth();
loadHistory();
setInterval(checkHealth, 30000);
