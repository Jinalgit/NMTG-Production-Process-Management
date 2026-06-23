/* ── Supervisor Dashboard JS — NMTG JMS ─────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  setDate();
  loadDashboard();
});

/* ── Live date in welcome bar ────────────────────────────────────────────── */
function setDate() {
  const el = document.getElementById("od-date");
  if (!el) return;
  const now = new Date();
  const opts = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
  el.textContent = now.toLocaleDateString("en-IN", opts);
}

/* ── Dashboard summary + overdue processes ───────────────────────────────── */
async function loadDashboard() {
  const container = document.getElementById("od-notif-container");
  const refreshBtn = document.getElementById("od-refresh-btn");

  if (refreshBtn) refreshBtn.classList.add("spinning");
  setStatsLoading();

  container.innerHTML = `
    <div class="od-loading">
      <span class="od-spinner"></span>
      <span>Loading dashboard…</span>
    </div>`;

  try {
    const res = await fetch("/api/supervisor/dashboard-summary");

    if (!res.ok) {
      throw new Error(`Server returned ${res.status}`);
    }

    const result = await res.json();

    if (!result.success) {
      setStatsEmpty();
      showError(container, result.error || "Failed to load dashboard.");
      return;
    }

    renderStats(result.summary || {});

    const data = result.overdue_processes || [];
    bindOverdueStatClicks(data);
    if (data.length === 0) {
      showEmpty(container);
      return;
    }

    renderTable(container, data);

  } catch (err) {
    setStatsEmpty();
    showError(container, "Could not connect to server. Please try again.");
    console.error("[SD] Dashboard fetch error:", err);
  } finally {
    if (refreshBtn) refreshBtn.classList.remove("spinning");
  }
}

/* ── Summary stat cards ──────────────────────────────────────────────────── */
function renderStats(summary) {
  setStat("stat-total-overdue", summary.total_overdue);
  setStat("stat-critical-overdue", summary.critical_overdue);
  setStat("stat-avg-delay", summary.avg_delay_days);
  setStat("stat-max-delay", summary.max_delay_days);
}

function setStat(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = (val ?? 0);
}

function setStatsLoading() {
  ["stat-total-overdue", "stat-critical-overdue", "stat-avg-delay", "stat-max-delay"]
    .forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = "…"; });
}

function setStatsEmpty() {
  ["stat-total-overdue", "stat-critical-overdue", "stat-avg-delay", "stat-max-delay"]
    .forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = "—"; });
}

function bindOverdueStatClicks(data) {
  const bind = (id, item) => {
    const card = document.getElementById(id)?.closest(".od-stat-card");
    if (!card) return;
    if (!item?.job_card_no) {
      card.classList.remove("od-clickable-stat");
      card.removeAttribute("title");
      card.onclick = null;
      return;
    }
    card.classList.add("od-clickable-stat");
    card.title = "Click to view overdue process in Traceability";
    card.onclick = () => openTraceability(item.job_card_no);
  };

  bind("stat-total-overdue", data[0]);
  bind("stat-critical-overdue", data.find(item => ((item.actual_days || 0) - (item.lead_days || 0)) > 7));
}

/* ── Render table ────────────────────────────────────────────────────────── */
function renderTable(container, data) {
  const rows = data.map((item) => {
    const overdueDays = (item.actual_days || 0) - (item.lead_days || 0);
    const overdueLabel = overdueDays > 0
      ? `+${overdueDays}d overdue`
      : `${Math.abs(overdueDays)}d over limit`;

    return `
      <tr class="od-clickable-row"
          onclick="openTraceability('${escAttr(item.job_card_no)}')"
          title="Click to view overdue process in Traceability">
        <td class="od-td-jc">${esc(item.job_card_no) || "—"}</td>
        <td>${esc(item.model) || "—"}</td>
        <td class="od-td-process">${esc(item.process_name) || "—"}</td>
        <td style="text-align:center;">${item.lead_days ?? "—"}</td>
        <td style="text-align:center;">${item.actual_days ?? "—"}</td>
        <td>
          <span class="od-overdue-badge">
            <i class="fa fa-exclamation-circle"></i>
            ${overdueLabel}
          </span>
        </td>
      </tr>`;
  }).join("");

  container.innerHTML = `
    <div class="od-notif-wrap">
      <div class="od-notif-header">
        <span class="od-notif-header-title">
          <i class="fa fa-clock-o"></i>
          Overdue Processes
        </span>
        <span class="od-notif-count">${data.length}</span>
      </div>
      <div class="od-table-scroll">
        <table class="od-table">
          <thead>
            <tr>
              <th>Job Card No.</th>
              <th>Model</th>
              <th>Process</th>
              <th style="text-align:center;">Lead Days</th>
              <th style="text-align:center;">Actual Days</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
function showEmpty(container) {
  container.innerHTML = `
    <div class="od-empty">
      <div class="od-empty-icon"><i class="fa fa-check-circle"></i></div>
      <div class="od-empty-title">All processes are on time</div>
      <div class="od-empty-sub">No lead time violations found right now.</div>
    </div>`;
}

/* ── Error state ─────────────────────────────────────────────────────────── */
function showError(container, msg) {
  container.innerHTML = `
    <div class="od-error">
      <i class="fa fa-exclamation-triangle"></i>
      <span>${esc(msg)}</span>
    </div>`;
}

/* ── XSS-safe escape ─────────────────────────────────────────────────────── */
function esc(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escAttr(str) {
  return esc(str).replace(/'/g, "&#39;");
}
