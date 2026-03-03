/**
 * app.js – BalanceMate frontend logic.
 *
 * Responsibilities:
 *  - Timer that tracks current work / break session duration
 *  - Heartbeat & window-switch events sent to the backend
 *  - Polling for AI suggestions and dashboard data
 *  - Daily summary loader
 *  - Settings form persistence
 */

"use strict";

const API_BASE = "/api";
const USER_ID  = "default";

const HEARTBEAT_INTERVAL_MS   = 30_000;
const POLL_INTERVAL_MS        = 60_000;

// ── State ────────────────────────────────────────────────────────────────────
const state = {
  sessionType:     "work",   // "work" | "break"
  sessionStart:    Date.now(),
  windowSwitches:  0,
  lastActivity:    Date.now(),
  breakCount:      0,
  rhythmChart:     null,
  currentSuggestion: null,
};

// ── Utility ──────────────────────────────────────────────────────────────────

function formatTime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return [h, m, s].map(v => String(v).padStart(2, "0")).join(":");
}

function formatMinutes(minutes) {
  const m = Math.round(minutes || 0);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

// ── API Helpers ───────────────────────────────────────────────────────────────

async function apiPost(endpoint, body = {}) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ ...body, user_id: USER_ID }),
    });
    return res.ok ? await res.json() : null;
  } catch (err) {
    console.warn("POST", endpoint, err);
    return null;
  }
}

async function apiGet(endpoint, params = {}) {
  try {
    const url = new URL(`${window.location.origin}${API_BASE}${endpoint}`);
    url.searchParams.set("user_id", USER_ID);
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    const res = await fetch(url.toString());
    return res.ok ? await res.json() : null;
  } catch (err) {
    console.warn("GET", endpoint, err);
    return null;
  }
}

// ── Timer ─────────────────────────────────────────────────────────────────────

function updateTimer() {
  const elapsed = Math.floor((Date.now() - state.sessionStart) / 1000);
  document.getElementById("session-timer").textContent = formatTime(elapsed);
}

// ── Session Controls ──────────────────────────────────────────────────────────

function startBreak() {
  state.sessionType  = "break";
  state.sessionStart = Date.now();
  state.breakCount  += 1;
  logActivity("break_start");

  document.getElementById("session-badge").className   = "badge badge--break";
  document.getElementById("session-badge").textContent = "On Break";
  document.getElementById("timer-label").textContent   = "Break time – step away!";
  document.getElementById("btn-break").style.display   = "none";
  document.getElementById("btn-resume").style.display  = "";
  document.getElementById("stat-breaks").textContent   = state.breakCount;
  hideNotification();
}

function resumeWork() {
  state.sessionType    = "work";
  state.sessionStart   = Date.now();
  state.windowSwitches = 0;
  logActivity("break_end");

  document.getElementById("session-badge").className   = "badge badge--work";
  document.getElementById("session-badge").textContent = "Working";
  document.getElementById("timer-label").textContent   = "Deep focus in progress";
  document.getElementById("btn-break").style.display   = "";
  document.getElementById("btn-resume").style.display  = "none";
}

// ── Activity Logging ──────────────────────────────────────────────────────────

function logActivity(type, extra = {}) {
  const duration = Math.floor((Date.now() - state.lastActivity) / 1000);
  apiPost("/activity", {
    type,
    duration_seconds: duration,
    metadata: { session_type: state.sessionType, ...extra },
  });
  state.lastActivity = Date.now();
}

// ── Suggestions ───────────────────────────────────────────────────────────────

async function fetchSuggestions() {
  const data = await apiGet("/suggestions");
  if (!data || !data.suggestions || !data.suggestions.length) return;

  const suggestion = data.suggestions[0];
  state.currentSuggestion = suggestion;

  document.getElementById("suggestion-icon").textContent = suggestion.icon || "💡";
  document.getElementById("suggestion-text").textContent = suggestion.message || "";

  if (data.urgency === "high") {
    showNotification(suggestion.icon, suggestion.message);
  }
}

// ── Notification ──────────────────────────────────────────────────────────────

function showNotification(icon, message) {
  document.getElementById("notification-icon").textContent   = icon    || "💡";
  document.getElementById("notification-message").textContent = message || "";
  document.getElementById("break-notification").style.display = "flex";
}

function hideNotification() {
  document.getElementById("break-notification").style.display = "none";
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

async function refreshDashboard() {
  const data = await apiGet("/dashboard");
  if (!data) return;

  const today = data.today || {};
  document.getElementById("stat-work-time").textContent =
    formatMinutes(today.total_work_minutes || 0);
  document.getElementById("stat-switches").textContent =
    today.window_switches || 0;

  updateRhythmChart(data.hourly_breakdown || new Array(24).fill(0));
}

function initRhythmChart() {
  const ctx    = document.getElementById("rhythm-chart").getContext("2d");
  const labels = Array.from({ length: 24 }, (_, i) => `${i}:00`);

  state.rhythmChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label:            "Activity (seconds)",
        data:             new Array(24).fill(0),
        backgroundColor:  "rgba(79, 70, 229, .55)",
        borderColor:      "rgba(79, 70, 229, 1)",
        borderWidth:      1,
        borderRadius:     4,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: {
          beginAtZero: true,
          grid:  { color: "rgba(0,0,0,.05)" },
          ticks: { font: { size: 11 } },
        },
        x: {
          grid:  { display: false },
          ticks: { font: { size: 10 }, maxTicksLimit: 12 },
        },
      },
    },
  });
}

function updateRhythmChart(hourlyData) {
  if (!state.rhythmChart) return;
  state.rhythmChart.data.datasets[0].data = hourlyData;
  state.rhythmChart.update("none");
}

// ── Summary ───────────────────────────────────────────────────────────────────

async function loadSummary(date = null) {
  const params = date ? { date } : {};
  const data   = await apiGet("/summary", params);
  const container = document.getElementById("summary-content");

  if (!data || !data.stats || Object.keys(data.stats).length === 0) {
    container.innerHTML =
      `<p class="loading">${(data && data.message) || "No data for this day."}</p>`;
    return;
  }

  const s     = data.stats;
  const score = s.focus_score || 0;
  const scoreColor =
    score >= 70 ? "var(--success)" :
    score >= 50 ? "var(--warning)" : "var(--danger)";

  container.innerHTML = `
    <p class="summary-message">${data.message || ""}</p>
    <div class="summary-stats">
      <div class="summary-stat">
        <div class="summary-stat__value">${formatMinutes(s.total_work_minutes || 0)}</div>
        <div class="summary-stat__label">Focus Time</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat__value">${s.break_count || 0}</div>
        <div class="summary-stat__label">Breaks Taken</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat__value">${s.window_switches || 0}</div>
        <div class="summary-stat__label">Context Switches</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat__value" style="color:${scoreColor}">${score}</div>
        <div class="summary-stat__label">Focus Score</div>
        <div class="focus-score-bar">
          <div class="focus-score-fill"
               style="width:${score}%; background:${scoreColor}"></div>
        </div>
      </div>
    </div>
    <ul class="summary-insights">
      ${(data.insights || []).map(i => `<li>${i}</li>`).join("")}
    </ul>
  `;
}

// ── Settings ──────────────────────────────────────────────────────────────────

async function loadSettings() {
  const data = await apiGet("/settings");
  if (!data) return;
  const form = document.getElementById("settings-form");
  Object.entries(data).forEach(([key, value]) => {
    const el = form.elements[key];
    if (el) el.value = value;
  });
}

async function saveSettings(e) {
  e.preventDefault();
  const form = e.target;
  const body = {};
  [...form.elements].forEach(el => {
    if (!el.name) return;
    body[el.name] = el.type === "number" ? Number(el.value) : el.value;
  });
  const result = await apiPost("/settings", body);
  if (result) {
    const indicator = document.getElementById("settings-saved");
    indicator.style.display = "";
    setTimeout(() => { indicator.style.display = "none"; }, 2500);
  }
}

// ── Tab Navigation ────────────────────────────────────────────────────────────

function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("tab--active"));
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`tab-${name}`).classList.add("tab--active");
  document.querySelector(`[data-tab="${name}"]`).classList.add("active");

  if (name === "summary") loadSummary();
  if (name === "settings") loadSettings();
}

// ── Visibility / Window-Switch Tracking ──────────────────────────────────────

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    logActivity("focus_lost");
  } else {
    state.windowSwitches += 1;
    logActivity("window_switch", { switches: state.windowSwitches });
    const el = document.getElementById("stat-switches");
    el.textContent = parseInt(el.textContent || "0", 10) + 1;
  }
});

// ── Initialisation ────────────────────────────────────────────────────────────

async function init() {
  initRhythmChart();

  // Set today's date in the summary date picker
  document.getElementById("summary-date").value =
    new Date().toISOString().split("T")[0];

  // Log session start and load initial data
  logActivity("session_start");
  await Promise.all([fetchSuggestions(), refreshDashboard()]);

  // Recurring tasks
  setInterval(updateTimer,       1000);   // clock tick
  setInterval(() => logActivity("heartbeat"), HEARTBEAT_INTERVAL_MS);
  setInterval(async () => {                // suggestions + dashboard
    await fetchSuggestions();
    await refreshDashboard();
  }, POLL_INTERVAL_MS);

  // ── Event listeners ──────────────────────────────────────────────────────

  document.getElementById("btn-break").addEventListener("click", startBreak);
  document.getElementById("btn-resume").addEventListener("click", resumeWork);

  document.getElementById("btn-accept-suggestion").addEventListener("click", () => {
    if (state.currentSuggestion) {
      apiPost("/suggestions/respond", {
        suggestion_type: state.currentSuggestion.type,
        accepted: true,
      });
      if (["short_break", "long_break"].includes(state.currentSuggestion.type)) {
        startBreak();
      }
    }
    hideNotification();
  });

  document.getElementById("btn-dismiss-suggestion").addEventListener("click", () => {
    if (state.currentSuggestion) {
      apiPost("/suggestions/respond", {
        suggestion_type: state.currentSuggestion.type,
        accepted: false,
      });
    }
    hideNotification();
  });

  document.getElementById("notification-close")
    .addEventListener("click", hideNotification);

  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  document.getElementById("settings-form")
    .addEventListener("submit", saveSettings);

  document.getElementById("summary-date").addEventListener("change", e => {
    loadSummary(e.target.value);
  });
}

document.addEventListener("DOMContentLoaded", init);
