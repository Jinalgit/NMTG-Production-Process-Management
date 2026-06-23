// ── State ─────────────────────────────────────────────────────────────────────
let activeTab = "jc";
let currentPage = 1;
let totalRows = 0;
let perPage = 50;
let sortCol = "";
let sortOrder = "desc";
let searchTimer = null;
let allData = [];
let filterOpen = false;
let wipOptions = [];
let statusOptions = [];

// ── Tab config ────────────────────────────────────────────────────────────────
const TAB = {
  jc: {
    api: "/api/data/job_cards",
    label: "PPC",
    cols: [
      { key: "job_card_no", label: "JC No" },
      { key: "so_no", label: "SO No" },
      { key: "item_name", label: "Item Name" },
      { key: "material", label: "Material" },
      { key: "so_qty", label: "SO Qty" },
      { key: "actual_qty", label: "Actual Qty" },
      { key: "wip_status", label: "WIP Status" },
      { key: "wip_stage_days", label: "Days in Stage" },
      { key: "total_days", label: "Total Days" },
      { key: "remaining_days", label: "Remaining Days" },
      { key: "days_overdue", label: "Days Overdue" },
      { key: "final_status", label: "Status" },
      { key: "delivery_date", label: "Delivery Date" },
      { key: "so_date", label: "SO Date" },
      { key: "remarks", label: "Remarks" },
    ],
  },
  qc: {
    api: "/api/data/quality_checks",
    label: "Traceability",
    cols: [
      { key: "job_card_no", label: "JC No" },
      { key: "checked_at", label: "Checked At" },
      { key: "item_name", label: "Item Name" },
      { key: "actual_qty", label: "Actual Qty" },
      { key: "completed_process", label: "Process" },
      { key: "quality_result", label: "Result" },
      { key: "supervisor", label: "Supervisor" },
    ],
  },
};

// ── Switch tab ────────────────────────────────────────────────────────────────
function switchTab(tab) {
  activeTab = tab;
  currentPage = 1;
  sortCol = "";
  sortOrder = "desc";
  filterOpen = false;

  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("tab-" + tab).classList.add("active");

  const isReport = tab === "pr";
  const isPlan = tab === "ps";
  document.getElementById("table-view").style.display = (!isReport && !isPlan) ? "block" : "none";
  document.getElementById("pr-view").style.display = isReport ? "block" : "none";
  document.getElementById("ps-view").style.display = isPlan ? "block" : "none";

  // Hide filter panel on tab switch
  const panel = document.getElementById("filter-panel");
  panel.style.display = "none";
  document.getElementById("btn-filter-toggle").classList.remove("active");

  document.getElementById("global-search").value = "";
  document.getElementById("pr-search").value = "";

  if (isReport) loadProcessReport();
  else if (isPlan) loadPlanningSheet();
  else loadData();
}

// ── Filter toggle ─────────────────────────────────────────────────────────────
function toggleFilters() {
  filterOpen = !filterOpen;
  const panel = document.getElementById("filter-panel");
  const btn = document.getElementById("btn-filter-toggle");
  panel.style.display = filterOpen ? "block" : "none";
  btn.classList.toggle("active", filterOpen);
  if (filterOpen && activeTab === "jc") buildFilterPanel();
}

function buildFilterPanel() {
  const content = document.getElementById("filter-panel-content");
  if (content.innerHTML) return; // already built

  let html = "";
  if (wipOptions.length) {
    html += `<div class="filter-group">
      <label>WIP Status</label>
      <select data-param="wip" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All WIP Stages</option>
        ${wipOptions.map(w => `<option value="${w}">${w}</option>`).join("")}
      </select>
    </div>`;
  }
  if (statusOptions.length) {
    html += `<div class="filter-group">
      <label>Final Status</label>
      <select data-param="status" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All Statuses</option>
        ${statusOptions.map(s => `<option value="${s}">${s}</option>`).join("")}
      </select>
    </div>`;
  }
  html += `
    <div class="filter-group">
      <label>SO Date From</label>
      <input type="date" data-param="date_from" onchange="currentPage=1;loadData();updateFilterBadge()" />
    </div>
    <div class="filter-group">
      <label>SO Date To</label>
      <input type="date" data-param="date_to" onchange="currentPage=1;loadData();updateFilterBadge()" />
    </div>`;

  content.innerHTML = html;
}

function updateFilterBadge() {
  let count = 0;
  document.querySelectorAll("#filter-panel-content select").forEach(s => { if (s.value) count++; });
  document.querySelectorAll("#filter-panel-content input[type='date']").forEach(i => { if (i.value) count++; });
  const badge = document.getElementById("filter-count-badge");
  badge.textContent = count;
  badge.style.display = count > 0 ? "inline-block" : "none";
}

function clearAllFilters() {
  document.querySelectorAll("#filter-panel-content select").forEach(s => s.value = "");
  document.querySelectorAll("#filter-panel-content input[type='date']").forEach(i => i.value = "");
  updateFilterBadge();
  currentPage = 1;
  loadData();
}

// ── Search ────────────────────────────────────────────────────────────────────
function debounceSearch() {
  const val = document.getElementById(activeTab === "pr" ? "pr-search" : "global-search").value;
  document.getElementById("btn-clear-search").style.display = val ? "block" : "none";
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage = 1;
    if (activeTab === "pr") loadProcessReport();
    else if (activeTab === "ps") loadPlanningSheet();
    else loadData();
  }, 350);
}

function clearSearch() {
  document.getElementById("global-search").value = "";
  document.getElementById("btn-clear-search").style.display = "none";
  currentPage = 1;
  loadData();
}

// ── Build query params ────────────────────────────────────────────────────────
function buildParams() {
  const search = document.getElementById("global-search").value.trim();
  const p = new URLSearchParams({ search, page: currentPage, per_page: perPage, sort: sortCol, order: sortOrder });
  document.querySelectorAll("#filter-panel-content select").forEach(sel => { if (sel.value) p.set(sel.dataset.param, sel.value); });
  document.querySelectorAll("#filter-panel-content input[type='date']").forEach(inp => { if (inp.value) p.set(inp.dataset.param, inp.value); });
  return p.toString();
}

// ── Load data ─────────────────────────────────────────────────────────────────
async function loadData() {
  document.getElementById("table-body").innerHTML =
    `<tr><td colspan="20" style="text-align:center;padding:40px;color:var(--muted)">Loading...</td></tr>`;
  try {
    const cfg = TAB[activeTab];
    const res = await fetch(`${cfg.api}?${buildParams()}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error, "error"); return; }

    allData = data.data;
    totalRows = data.total || data.data.length;

    renderHead(cfg.cols);
    renderBody(cfg.cols, data.data);
    renderPagination();
    renderRowCount();

    // Store filter options on first load
    if (activeTab === "jc" && data.wip_options && !wipOptions.length) {
      wipOptions = data.wip_options;
      statusOptions = data.status_options || [];
    }

  } catch (e) { showToast("Server error", "error"); }
}

// ── Render head ───────────────────────────────────────────────────────────────
function renderHead(cols) {
  const arrows = (key) => {
    if (sortCol !== key) return `<span class="sort-ind"><i class="fa fa-sort" aria-hidden="true"></i></span>`;
    return sortOrder === "asc"
      ? `<span class="sort-ind"><i class="fa fa-sort-asc" aria-hidden="true"></i></span>`
      : `<span class="sort-ind"><i class="fa fa-sort-desc" aria-hidden="true"></i></span>`;
  };
  document.getElementById("table-head").innerHTML =
    `<tr>${cols.map(c => `<th onclick="setSort('${c.key}')">${c.label}${arrows(c.key)}</th>`).join("")}</tr>`;
}

// ── Render body ───────────────────────────────────────────────────────────────
function renderBody(cols, rows) {
  const tbody = document.getElementById("table-body");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="${cols.length}" style="text-align:center;padding:48px;color:var(--muted)">No records found</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(row => {
    const cells = cols.map(c => {
      let v = row[c.key] ?? (c.key === "wip_stage_days" ? 0 : "");
      if (c.key === "quality_result") {
        v = v === "OK" ? `<span class="badge-ok">OK</span>`
          : v === "NOT OK" ? `<span class="badge-notok">Not OK</span>` : v;
      }
      if (c.key === "days_overdue" && v > 0) {
        v = `<span class="badge-overdue">${v}d overdue</span>`;
      }
      if (c.key === "wip_status" && v) {
        const s = String(v).toLowerCase();
        const cls = s === "store" || s === "complete" || s === "completed" ? "badge-ok"
          : s === "pending" ? "badge-pending" : "badge-wip";
        v = `<span class="${cls}">${v}</span>`;
      }
      if (c.key === "final_status" && v) {
        const cls = String(v).toLowerCase() === "completed" ? "badge-ok" : "badge-pending";
        v = `<span class="${cls}">${v}</span>`;
      }
      return `<td title="${String(row[c.key] ?? '')}">${v}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
}

// ── Sort ──────────────────────────────────────────────────────────────────────
function setSort(col) {
  if (sortCol === col) sortOrder = sortOrder === "asc" ? "desc" : "asc";
  else { sortCol = col; sortOrder = "asc"; }
  currentPage = 1;
  loadData();
}

// ── Pagination ────────────────────────────────────────────────────────────────
function renderPagination() {
  const totalPages = Math.ceil(totalRows / perPage);
  const bar = document.getElementById("pagination-bar");
  if (totalPages <= 1) { bar.innerHTML = ""; return; }
  let html = `<button onclick="goPage(${currentPage - 1})" ${currentPage === 1 ? "disabled" : ""}><i class="fa fa-chevron-left" aria-hidden="true"></i> Prev</button>`;
  const start = Math.max(1, currentPage - 2);
  const end = Math.min(totalPages, currentPage + 2);
  if (start > 1) html += `<button onclick="goPage(1)">1</button>${start > 2 ? '<span>…</span>' : ""}`;
  for (let i = start; i <= end; i++)
    html += `<button onclick="goPage(${i})" class="${i === currentPage ? 'active' : ''}">${i}</button>`;
  if (end < totalPages) html += `${end < totalPages - 1 ? '<span>…</span>' : ""}<button onclick="goPage(${totalPages})">${totalPages}</button>`;
  html += `<button onclick="goPage(${currentPage + 1})" ${currentPage === totalPages ? "disabled" : ""}>Next <i class="fa fa-chevron-right" aria-hidden="true"></i></button>`;
  bar.innerHTML = html;
}

function goPage(p) {
  const totalPages = Math.ceil(totalRows / perPage);
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  loadData();
}

function renderRowCount() {
  const start = (currentPage - 1) * perPage + 1;
  const end = Math.min(currentPage * perPage, totalRows);
  document.getElementById("row-count").textContent =
    totalRows ? `Showing ${start}–${end} of ${totalRows} records` : "No records";
}

// ── Process Report ────────────────────────────────────────────────────────────
async function loadProcessReport() {
  document.getElementById("pr-cards").innerHTML =
    `<div style="text-align:center;padding:40px;color:var(--muted)">Loading...</div>`;
  try {
    const search = document.getElementById("pr-search").value.trim();
    const res = await fetch(`/api/data/process_report?search=${encodeURIComponent(search)}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error, "error"); return; }
    renderPRCards(data.data);
    document.getElementById("pr-row-count").textContent = `${data.data.length} job card(s)`;
  } catch (e) { showToast("Server error", "error"); }
}

function renderPRCards(items) {
  const container = document.getElementById("pr-cards");
  if (!items.length) { container.innerHTML = `<div class="pr-empty">No records found</div>`; return; }
  container.innerHTML = items.map(jc => {
    const procs = jc.processes.map(p => {
      const cls = { "On Time": "proc-ontime", "Delayed": "proc-delayed", "In Progress": "proc-inprogress", "Pending": "proc-pending" }[p.status] || "proc-pending";
      const actualDisplay = p.status === "In Progress" && p.in_time
        ? `${Math.max(0, Math.floor((Date.now() - new Date(p.in_time)) / 86400000))}d so far`
        : (p.actual_days != null ? `${p.actual_days}d` : "—");
      return `<div class="proc-col ${cls}">
        <div class="proc-name" title="${p.process_name}">${p.process_name}</div>
        <div class="proc-lead">Lead: ${p.lead_days ?? "—"}d</div>
        <div class="proc-actual">${actualDisplay}</div>
        <div class="proc-date">${p.in_time || ""}</div>
        <div class="proc-badge">${p.status}</div>
      </div>`;
    }).join("");
    const rem = jc.remaining_days ?? 0;
    const remStyle = rem <= 0 ? "background:#f0fdf4;border:1px solid #86efac;color:#16a34a;" : "background:#fffbeb;border:1px solid #fde68a;color:#92400e;";
    return `<div class="jc-card">
      <div class="jc-card-header">
        <div class="jc-hrow">
          <span><span class="jc-hl">JC</span><a class="jc-link" onclick="goToPage3('${jc.job_card_no}')">${jc.job_card_no}</a></span>
          <span><span class="jc-hl">SO</span>${jc.so_no || "—"}</span>
          <span><span class="jc-hl">Status</span>${jc.final_status || "—"}</span>
          ${jc.delivery_date ? `<span><span class="jc-hl">Delivery</span>${jc.delivery_date}</span>` : ""}
        </div>
        <div class="jc-hrow">
          <span class="jc-item-name">${jc.item_name}</span>
          <span><span class="jc-hl">WIP</span>${jc.wip_status || "—"}</span>
          <span style="${remStyle};padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700;">Remaining: ${rem}d</span>
        </div>
      </div>
      <div class="jc-card-body"><div class="proc-grid">${procs}</div></div>
    </div>`;
  }).join("");
}

function goToPage3(jcNo) {
  window.location.href = `/page3?jc=${encodeURIComponent(jcNo)}`;
}

// ── Export (no CSV) ───────────────────────────────────────────────────────────
function getExportData() {
  const cols = TAB[activeTab]?.cols || [];
  return {
    headers: cols.map(c => c.label),
    rows: allData.map(r => cols.map(c => r[c.key] ?? ""))
  };
}

function exportExcel() {
  const { headers, rows } = getExportData();
  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Data");
  XLSX.writeFile(wb, "export.xlsx");
}

function exportPDF() {
  const { headers, rows } = getExportData();
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ orientation: "landscape" });
  doc.autoTable({ head: [headers], body: rows, styles: { fontSize: 8 }, headStyles: { fillColor: [30, 58, 95] } });
  doc.save("export.pdf");
}

function exportPRExcel() {
  const wb = XLSX.utils.book_new();
  const aoa = [["JC No", "SO No", "Item Name", "WIP Status", "Process", "Lead Days", "Actual Days", "Status"]];
  document.querySelectorAll(".jc-card").forEach(card => {
    const jcNo = card.querySelector(".jc-link")?.textContent || "";
    const item = card.querySelector(".jc-item-name")?.textContent || "";
    card.querySelectorAll(".proc-col").forEach(col => {
      aoa.push([jcNo, "", item, "",
        col.querySelector(".proc-name")?.textContent || "",
        col.querySelector(".proc-lead")?.textContent.replace("Lead:", "").trim() || "",
        col.querySelector(".proc-actual")?.textContent || "",
        col.querySelector(".proc-badge")?.textContent || ""]);
    });
  });
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), "Process Report");
  XLSX.writeFile(wb, "process_report.xlsx");
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadData();
// ── Planning Sheet ────────────────────────────────────────────────────────────
let psData = [];

async function loadPlanningSheet() {
  document.getElementById("ps-body").innerHTML =
    `<tr><td colspan="25" style="text-align:center;padding:40px;color:var(--muted)">Loading...</td></tr>`;

  try {
    const search = document.getElementById("ps-search").value.trim();
    const wip = document.getElementById("ps-wip-filter").value;
    const res = await fetch(`/api/data/planning_sheet?search=${encodeURIComponent(search)}&wip=${encodeURIComponent(wip)}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error, "error"); return; }

    psData = data.data;
    renderPSTable(data.data);

    // Populate WIP filter
    const sel = document.getElementById("ps-wip-filter");
    if (sel.options.length <= 1 && data.wip_options?.length) {
      data.wip_options.forEach(w => {
        const opt = document.createElement("option");
        opt.value = w; opt.textContent = w;
        sel.appendChild(opt);
      });
    }
    document.getElementById("ps-row-count").textContent = `${data.data.length} record(s)`;
  } catch (e) { showToast("Server error", "error"); }
}

function renderPSTable(rows) {
  const COLS = [
    { key: "job_card_no", label: "JC No" },
    { key: "item_name", label: "Item Name" },
    { key: "wip_status", label: "Current Stage" },
    { key: "live_stage_days", label: "Days in Stage" },
    { key: "next_process", label: "Next Stage" },
    { key: "pend_days", label: "Pend Days" },
    { key: "delivery_date", label: "Delivery Date" },
  ];

  // Header
  document.getElementById("ps-head").innerHTML =
    `<tr>${COLS.map(c => `<th>${c.label}</th>`).join("")}</tr>`;

  const tbody = document.getElementById("ps-body");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="${COLS.length}" style="text-align:center;padding:48px;color:var(--muted)">No records found</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(row => {
    const cells = COLS.map(c => {
      let v = row[c.key] ?? "";

      // WIP status badge
      if (c.key === "wip_status" && v) {
        const s = String(v).toLowerCase();
        const cls = s === "store" || s === "completed" ? "badge-ok"
          : s === "pending" ? "badge-pending" : "badge-wip";
        v = `<span class="${cls}">${v}</span>`;
      }

      // Days in stage — colored by urgency
      if (c.key === "live_stage_days") {
        const days = parseInt(v) || 0;
        const color = days > 10 ? "#dc2626" : days > 5 ? "#d97706" : "#16a34a";
        const bg = days > 10 ? "#fef2f2" : days > 5 ? "#fffbeb" : "#f0fdf4";
        const border = days > 10 ? "#fca5a5" : days > 5 ? "#fde68a" : "#86efac";
        v = `<span style="font-weight:700;color:${color};background:${bg};border:1px solid ${border};padding:2px 10px;border-radius:20px;">${days}d</span>`;
      }

      // Next stage badge
      if (c.key === "next_process") {
        if (!v || v === "") v = `<span style="color:var(--muted);font-size:12px">—</span>`;
        else v = `<span style="background:#eff6ff;border:1px solid #bfdbfe;color:#1a56db;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700;">${v}</span>`;
      }

      // Pend days — colored
      if (c.key === "pend_days") {
        if (v === null || v === "") { v = "—"; }
        else {
          const days = parseInt(v);
          const color = days < 0 ? "#dc2626" : days <= 7 ? "#d97706" : "#16a34a";
          const bg = days < 0 ? "#fef2f2" : days <= 7 ? "#fffbeb" : "#f0fdf4";
          const border = days < 0 ? "#fca5a5" : days <= 7 ? "#fde68a" : "#86efac";
          const label = days < 0 ? `${Math.abs(days)}d overdue` : `${days}d left`;
          v = `<span style="font-weight:700;color:${color};background:${bg};border:1px solid ${border};padding:2px 10px;border-radius:20px;">${label}</span>`;
        }
      }

      return `<td title="${String(row[c.key] ?? '')}">${v}</td>`;
    }).join("");
    return `<tr>${cells}</tr>`;
  }).join("");
}

function clearPSSearch() {
  document.getElementById("ps-search").value = "";
  document.getElementById("ps-clear-search").style.display = "none";
  loadPlanningSheet();
}

function exportPSExcel() {
  if (!psData.length) { showToast("No data to export", "error"); return; }
  const headers = ["JC No", "SO No", "Item Name", "WIP Status", "Live Stage Days", "Remarks",
    "Next Process", "Drg Days", "RM Days", "Cut Days", "Forg Days", "Norm Days", "RT Days",
    "HRC Days", "CNC Days", "Conv Days", "Other O/S", "QC Days", "Store", "Assembly",
    "Total Days", "Pend Days", "Final Delivery Date"];
  const keys = ["job_card_no", "so_no", "item_name", "wip_status", "live_stage_days", "remarks",
    "next_process", "drg_days", "rm_days", "cut_days", "forg_days", "norm_days", "rt_days",
    "hrc_days", "cnc_days", "conv_days", "other_days", "qc_days", "store_days", "assembly_days",
    "total_days", "pend_days", "delivery_date"];
  const aoa = [headers, ...psData.map(r => keys.map(k => r[k] ?? ""))];
  const ws = XLSX.utils.aoa_to_sheet(aoa);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Planning Sheet");
  XLSX.writeFile(wb, "planning_sheet.xlsx");
}