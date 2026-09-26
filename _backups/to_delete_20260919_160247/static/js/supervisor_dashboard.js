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
      loadDeliveryChangeNotifications();
      return;
    }

    renderTable(container, data);
    loadDeliveryChangeNotifications();
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
// ── Delivery Date Change Notifications ───────────────────────────────────────
async function loadDeliveryChangeNotifications() {
  const container = document.getElementById("od-dd-notif-container");
  if (!container) return;

  container.innerHTML = `<div class="od-loading"><span class="od-spinner"></span><span>Loading...</span></div>`;

  try {
    const res = await fetch("/api/notifications/delivery_changes");
    const data = await res.json();

    const records = Array.isArray(data.records)
      ? data.records
      : Array.isArray(data.data)
        ? data.data
        : Array.isArray(data.rows)
          ? data.rows
          : [];

    if (!data.success || !records.length) {
      container.innerHTML = `
        <div class="od-empty">
          <div class="od-empty-icon"><i class="fa fa-calendar-check-o"></i></div>
          <div class="od-empty-title">No delivery date changes</div>
          <div class="od-empty-sub">No changes in the last 30 days.</div>
        </div>`;
      return;
    }

    const levelBadge = (level) => {
      const normalized = String(level || "JC").toUpperCase();
      const colors = {
        SO: { bg: "#eff6ff", text: "#1a56db" },
        WO: { bg: "#f0fdf4", text: "#16a34a" },
        JC: { bg: "#fef9e7", text: "#d97706" },
      };
      const color = colors[normalized] || colors.JC;
      return `<span style="display:inline-flex; align-items:center; justify-content:center; min-width:28px; padding:3px 7px; border-radius:4px; background:${color.bg}; color:${color.text}; font-size:10px; font-weight:800;">${esc(normalized)}</span>`;
    };

    const changeTime = (value) => {
      const match = String(value || "").match(/\b\d{1,2}:\d{2}\s*[AP]M\b/i);
      return match ? match[0].toUpperCase() : (value || "—");
    };

    const groups = [];
    const groupMap = new Map();
    records.forEach((record) => {
      const key = record.job_card_no || "—";
      if (!groupMap.has(key)) {
        const group = {
          jobCardNo: key,
          itemName: record.item_name || "—",
          changes: [],
        };
        groupMap.set(key, group);
        groups.push(group);
      }
      groupMap.get(key).changes.push(record);
    });

    const groupMarkup = groups.map((group, index) => {
      const changes = group.changes.map((r) => `
        <div class="od-dd-change-row" style="display:flex; align-items:flex-start; gap:10px; padding:9px 14px 9px 42px; border-top:1px solid var(--border); color:var(--text);">
          <div style="padding-top:1px;">${levelBadge(r.change_level)}</div>
          <div style="min-width:0; flex:1; display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:13px; line-height:1.45;">
            <span style="font-weight:700; color:var(--text);">${esc(r.so_no || "—")} / ${esc(r.work_order_no || "—")}</span>
            <span style="color:var(--muted);">·</span>
            <span style="color:#ef4444; text-decoration:line-through; font-weight:700;">${esc(r.old_delivery_date || "—")}</span>
            <span style="color:var(--muted);">→</span>
            <span style="color:#16a34a; font-weight:800;">${esc(r.new_delivery_date || "—")}</span>
            <span style="color:var(--muted);">·</span>
            <span style="font-weight:700;">${esc(r.changed_by || "—")}</span>
            <span style="color:var(--muted);">·</span>
            <span style="font-style:italic;">${esc(r.reason || "—")}</span>
            <span style="color:var(--muted);">·</span>
            <span style="color:var(--muted); font-size:12px;">${esc(changeTime(r.changed_at))}</span>
          </div>
        </div>`).join("");

      return `
        <div class="od-dd-group" style="border-top:${index === 0 ? "0" : "1px solid var(--border)"};">
          <button type="button" class="od-dd-group-toggle" data-group-index="${index}"
                  style="width:100%; border:0; background:var(--card-bg, #fff); padding:13px 16px; display:flex; align-items:center; gap:10px; cursor:pointer; text-align:left;">
            <i class="fa fa-chevron-down od-dd-chevron" style="width:14px; color:var(--muted); transition:transform 0.15s;"></i>
            <i class="fa fa-archive" style="color:var(--accent);"></i>
            <span style="font-weight:800; color:var(--header-bg); white-space:nowrap;">JC: ${esc(group.jobCardNo)}</span>
            <span style="color:var(--muted);">—</span>
            <span style="min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--text); font-weight:600;">${esc(group.itemName)}</span>
            <span style="margin-left:auto; background:#f8fafc; border:1px solid var(--border); color:var(--muted); border-radius:999px; padding:2px 8px; font-size:11px; font-weight:800;">${group.changes.length}</span>
          </button>
          <div class="od-dd-group-body" data-group-body="${index}" style="background:#ffffff;">
            ${changes}
          </div>
        </div>`;
    }).join("");

    container.innerHTML = `
      <div class="od-notif-wrap">
        <div class="od-notif-header">
          <span class="od-notif-header-title">
            <i class="fa fa-calendar" style="color:#f59e0b;"></i>
            Delivery Date Changes
          </span>
          <span class="od-notif-count" style="background:#f59e0b;">${data.count ?? records.length}</span>
        </div>
        <div class="od-dd-tree" style="font-size:13px;">${groupMarkup}</div>
      </div>`;

    container.querySelectorAll(".od-dd-group-toggle").forEach((button) => {
      button.addEventListener("click", () => {
        const index = button.getAttribute("data-group-index");
        const body = container.querySelector(`[data-group-body="${index}"]`);
        const icon = button.querySelector(".od-dd-chevron");
        const collapsed = body.style.display === "none";
        body.style.display = collapsed ? "block" : "none";
        icon.style.transform = collapsed ? "rotate(0deg)" : "rotate(-90deg)";
      });
    });
  } catch (e) {
    container.innerHTML = `<div class="od-error"><i class="fa fa-exclamation-triangle"></i> Failed to load.</div>`;
  }
}
