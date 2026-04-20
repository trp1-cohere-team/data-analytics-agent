const state = {
  messages: [],
  selectedMessageId: null,
  loadingMessageId: null,
  dashboard: {
    health: null,
    summary: null,
  },
};

const messageList = document.getElementById("messageList");
const questionInput = document.getElementById("questionInput");
const sendButton = document.getElementById("sendButton");
const statusPill = document.getElementById("statusPill");
const statusText = document.getElementById("statusText");
const historyButton = document.getElementById("historyButton");
const clearChatButton = document.getElementById("clearChatButton");
const closeHistoryButton = document.getElementById("closeHistoryButton");
const historyDrawer = document.getElementById("historyDrawer");
const drawerBackdrop = document.getElementById("drawerBackdrop");
const historyList = document.getElementById("historyList");
const suggestionRow = document.getElementById("suggestionRow");
const hintSummary = document.getElementById("hintSummary");
const charCount = document.getElementById("charCount");
const sendLabel = sendButton.querySelector(".send-label");
const runtimeMode = document.getElementById("runtimeMode");
const runtimeTools = document.getElementById("runtimeTools");
const evidenceConfidence = document.getElementById("evidenceConfidence");
const evidenceTimestamp = document.getElementById("evidenceTimestamp");
const evidenceToolCalls = document.getElementById("evidenceToolCalls");
const toolTimelineList = document.getElementById("toolTimelineList");
const correctionList = document.getElementById("correctionList");
const evalPass = document.getElementById("evalPass");
const evalEntries = document.getElementById("evalEntries");
const evalProbes = document.getElementById("evalProbes");

const starterMessage = {
  role: "agent",
  content:
    "Start with a stock question, a schema-routing question, or anything that needs tool-backed analysis.",
  result: {
    answer: "",
    confidence: 0.92,
    trace_id: "ready",
    tool_calls: [],
    failure_count: 0,
  },
};

marked.setOptions({ breaks: true, gfm: true });

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

function buildEvidence(message) {
  const result = message?.result || {};
  const rawConfidence = Number(result.confidence);
  const confidence = Number.isFinite(rawConfidence)
    ? `${Math.round(Math.max(0, Math.min(rawConfidence, 1)) * 100)}%`
    : "ready";
  const timestamp = formatTimestamp(message.timestamp);
  const toolCalls = Array.isArray(result.tool_calls) ? result.tool_calls : [];
  return {
    confidence,
    timestamp,
    toolCallCount: toolCalls.length,
  };
}

function inferDbType(toolName) {
  const normalized = String(toolName || "").toLowerCase();
  if (normalized.includes("mongo")) return "mongodb";
  if (normalized.includes("duck")) return "duckdb";
  if (normalized.includes("sqlite")) return "sqlite";
  if (normalized.includes("postgres")) return "postgresql";
  return "unknown";
}

function getCurrentAgentMessage() {
  if (state.selectedMessageId) {
    const selected = state.messages.find((msg) => msg.id === state.selectedMessageId && msg.role === "agent");
    if (selected && !selected.loading) return selected;
  }
  for (let i = state.messages.length - 1; i >= 0; i -= 1) {
    const msg = state.messages[i];
    if (msg.role === "agent" && !msg.loading) return msg;
  }
  return null;
}

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

      const copyBtn = document.createElement("button");
      copyBtn.className = "message-action";
      copyBtn.type = "button";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(message.content || "");
          copyBtn.textContent = "Copied ✓";
          setTimeout(() => {
            copyBtn.textContent = "Copy";
          }, 1400);
        } catch {
          copyBtn.textContent = "Failed";
          setTimeout(() => {
            copyBtn.textContent = "Copy";
          }, 1400);
        }
      });

      actions.append(copyBtn);

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
      wrapper.addEventListener("click", () => {
        state.selectedMessageId = message.id;
        renderMessages();
      });
    }

    messageList.appendChild(wrapper);
  });

  document.querySelectorAll("pre code").forEach((block) => hljs.highlightElement(block));
  suggestionRow.style.display = state.messages.length > 1 ? "none" : "flex";
  scrollToLatest(!stickToBottom);
  renderDashboard();
}

function toggleMessageExpanded(messageId) {
  const message = state.messages.find((m) => m.id === messageId);
  if (!message) return;
  message.expanded = !message.expanded;
  renderMessages();
}

function renderDashboard() {
  const selected = getCurrentAgentMessage();
  const calls = Array.isArray(selected?.result?.tool_calls) ? selected.result.tool_calls : [];
  const failureCount = Number(selected?.result?.failure_count || 0);

  if (!selected) {
    evidenceConfidence.textContent = "ready";
    evidenceTimestamp.textContent = "--";
    evidenceToolCalls.textContent = "0";
  } else {
    const evidence = buildEvidence(selected);
    evidenceConfidence.textContent = evidence.confidence;
    evidenceTimestamp.textContent = evidence.timestamp;
    evidenceToolCalls.textContent = String(evidence.toolCallCount);
  }

  toolTimelineList.innerHTML = "";
  if (!calls.length) {
    toolTimelineList.innerHTML = '<li class="insight-item muted">No tool calls were recorded for this response.</li>';
  } else {
    calls.forEach((call, idx) => {
      const toolName = call.tool_name || call.tool || "unknown_tool";
      const dbType = inferDbType(toolName);
      const status = call.success === false ? "failed" : "ok";
      const retry = Number(call.retry || 0);
      const li = document.createElement("li");
      li.className = "insight-item";
      li.innerHTML = `
        <div class="insight-top">
          <strong>${idx + 1}. ${escapeHtml(toolName)}</strong>
          <span class="insight-badge ${status}">${status}</span>
        </div>
        <div class="insight-meta">${escapeHtml(dbType)}${retry > 0 ? ` · retry ${retry}` : ""}</div>
      `;
      toolTimelineList.appendChild(li);
    });
  }

  const failedCalls = calls.filter((c) => c.success === false).length;
  const retriedCalls = calls.filter((c) => Number(c.retry || 0) > 0).length;
  correctionList.innerHTML = "";
  if (!failureCount && !failedCalls && !retriedCalls) {
    correctionList.innerHTML = '<li class="insight-item muted">No corrections observed in the selected response.</li>';
  } else {
    const rows = [
      `failure_count returned by agent: ${failureCount}`,
      `failed tool calls in trace: ${failedCalls}`,
      `retry-tagged tool calls: ${retriedCalls}`,
    ];
    rows.forEach((row) => {
      const li = document.createElement("li");
      li.className = "insight-item";
      li.textContent = row;
      correctionList.appendChild(li);
    });
  }

  const health = state.dashboard.health || {};
  const summary = state.dashboard.summary || {};
  runtimeMode.textContent = health.offline_mode ? "offline" : "online";
  runtimeTools.textContent = String((health.available_db_tools || []).length || 0);
  if (!summary.eval) {
    evalPass.textContent = "--";
    evalEntries.textContent = "--";
    evalProbes.textContent = "--";
  } else {
    const passRate = Number(summary.eval.pass_at_1 || 0);
    evalPass.textContent = `${Math.round(passRate * 10000) / 100}%`;
    evalEntries.textContent = String(summary.eval.total_entries || 0);
    evalProbes.textContent = `${summary.probes?.total_probes || 0} probes · ${summary.probes?.categories || 0} categories`;
  }
}

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

async function sendMessage(prefillQuestion = null) {
  const question = (prefillQuestion ?? questionInput.value).trim();
  if (!question || state.loadingMessageId) return;

  const dbHints = getSelectedHints();
  const timestamp = new Date().toISOString();
  const userMessageId = createId("user");
  const loadingMessageId = createId("agent");

  addMessage({ id: userMessageId, role: "user", content: question, timestamp });
  addMessage({ id: loadingMessageId, role: "agent", content: "", timestamp, loading: true, expanded: false });

  state.loadingMessageId = loadingMessageId;
  state.selectedMessageId = loadingMessageId;
  sendButton.disabled = true;
  if (sendLabel) sendLabel.textContent = "Sending...";
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
    loadDashboardSummary();
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

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("unhealthy");
    const payload = await response.json();
    state.dashboard.health = payload;
    statusPill.classList.add("healthy");
    statusPill.classList.remove("unhealthy");
    statusText.textContent = "API healthy";
    renderDashboard();
  } catch {
    statusPill.classList.add("unhealthy");
    statusPill.classList.remove("healthy");
    statusText.textContent = "API unavailable";
    state.dashboard.health = { status: "unavailable", available_db_tools: [], offline_mode: null };
    renderDashboard();
  }
}

async function loadDashboardSummary() {
  try {
    const response = await fetch("/api/dashboard_summary");
    if (!response.ok) throw new Error("summary unavailable");
    state.dashboard.summary = await response.json();
  } catch {
    state.dashboard.summary = null;
  }
  renderDashboard();
}

async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    if (!response.ok) throw new Error("history unavailable");
    const payload = await response.json();
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
      const pct = Math.round((session.confidence || 0) * 100);
      const confClass = pct > 80 ? "high" : pct > 50 ? "medium" : "low";
      const item = document.createElement("article");
      item.className = "history-item";
      item.innerHTML = `
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

resetChat();
autoResizeTextarea();
updateComposerMeta();
checkHealth();
loadHistory();
loadDashboardSummary();
setInterval(checkHealth, 30000);
setInterval(loadDashboardSummary, 45000);
