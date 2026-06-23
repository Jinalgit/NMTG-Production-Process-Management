/* ── Admin Dashboard JS — NMTG JMS ──────────────────────────────────────── */

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

const STAT_IDS = [
  "stat-total-job-cards",
  "stat-active-job-cards",
  "stat-completed-job-cards",
  "stat-critical-overdue",
];

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
    const res = await fetch("/api/admin/dashboard-summary");

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
    console.error("[AD] Dashboard fetch error:", err);
  } finally {
    if (refreshBtn) refreshBtn.classList.remove("spinning");
  }
}

/* ── Summary stat cards ──────────────────────────────────────────────────── */
function renderStats(summary) {
  setStat("stat-total-job-cards", summary.total_job_cards);
  setStat("stat-active-job-cards", summary.active_job_cards);
  setStat("stat-completed-job-cards", summary.completed_job_cards);
  setStat("stat-critical-overdue", summary.critical_overdue);
}

function setStat(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = (val ?? 0);
}

function setStatsLoading() {
  STAT_IDS.forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = "…"; });
}

function setStatsEmpty() {
  STAT_IDS.forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = "—"; });
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

/* ── Stat card drill-down modal ──────────────────────────────────────────── */
async function openStatModal(type) {
  const res  = await fetch(`/api/dashboard/stat-detail?type=${type}`);
  const data = await res.json();
  if (!data.success) return;

  const titles = {
    total:     "All Job Cards",
    active:    "Active Job Cards",
    completed: "Completed Job Cards",
    critical:  "Critical Overdue Job Cards",
  };

  document.getElementById("stat-modal-title").textContent = titles[type] || type;
  document.getElementById("stat-modal-head").innerHTML = `
    <tr style="background:#1e3a5f;color:#fff;">
      <th style="padding:8px 12px;text-align:left;">JC No</th>
      <th style="padding:8px 12px;text-align:left;">Item Name</th>
      <th style="padding:8px 12px;text-align:left;">WIP Stage</th>
      <th style="padding:8px 12px;text-align:left;">Delivery</th>
      <th style="padding:8px 12px;text-align:left;">Status</th>
    </tr>`;
  document.getElementById("stat-modal-body").innerHTML = data.records.map(r => `
    <tr style="border-bottom:1px solid #e5e7eb;">
      <td style="padding:8px 12px;font-weight:700;">${esc(r.job_card_no)}</td>
      <td style="padding:8px 12px;">${esc(r.item_name)}</td>
      <td style="padding:8px 12px;">${esc(r.wip_status)}</td>
      <td style="padding:8px 12px;">${esc(r.delivery_date || "—")}</td>
      <td style="padding:8px 12px;">${esc(r.final_status)}</td>
    </tr>`).join("");

  const modal = document.getElementById("stat-modal");
  modal.style.display = "flex";
}

function closeStatModal() {
  document.getElementById("stat-modal").style.display = "none";
}
