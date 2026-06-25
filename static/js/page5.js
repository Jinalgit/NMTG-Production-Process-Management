// ── State ─────────────────────────────────────────────────────────────────────
let activeTab = "jc";
let currentPage = 1;
let totalRows = 0;
let perPage = 50;
let sortCol = "";
let sortOrder = "desc";
let searchTimer = null;
let allData = [];
let prData = [];
let filterOpen = false;
let wipOptions = [];
let prWipOptions = [];
let statusOptions = [];
let prCurrentPage = 1;
let prTotalRows = 0;
let prPerPage = 30;

const DATE_KEYS = new Set([
  "so_date", "job_card_date", "work_order_date", "delivery_date",
  "created_at", "checked_at", "changed_at", "in_time", "out_time", "lead_date"
]);

function formatCellValue(key, value) {
  if (DATE_KEYS.has(key)) return formatDateForDisplay(value) || "";
  if (key === "is_priority") return value ? "Yes" : "No";
  return value ?? "";
}

// ── Tab config ────────────────────────────────────────────────────────────────
const TAB = {
  jc: {
    api: "/api/data/job_cards",
    label: "PPC",
    cols: [
      { key: "is_priority", label: "Urgent" },
      { key: "job_card_no", label: "JC No" },
      { key: "so_no", label: "SO No" },
      { key: "customer_name", label: "Customer Name" },
      { key: "parent_code", label: "Parent Code" },
      { key: "child_code", label: "Child Code" },
      { key: "item_name", label: "Item Name" },
      { key: "so_qty", label: "SO Qty" },
      { key: "actual_qty", label: "Actual Qty" },
      { key: "wip_status", label: "WIP Status" },
      { key: "remarks", label: "Remarks" },
      { key: "vendor_name", label: "Subcontractor" },
      { key: "wip_stage_days", label: "Days in Stage" },
      { key: "total_days", label: "Total Days" },
      { key: "remaining_days", label: "Remaining Days" },
      { key: "days_overdue", label: "Days Overdue" },
      { key: "final_status", label: "Status" },
      { key: "delivery_date", label: "Delivery Date" },
      { key: "so_date", label: "SO Date" },

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
  document.getElementById("btn-filter-toggle")?.classList.remove("active");
  document.getElementById("btn-filter-toggle-pr")?.classList.remove("active");

  document.getElementById("global-search").value = "";
  document.getElementById("pr-search").value = "";

  if (isReport) {
    prCurrentPage = 1;
    loadProcessReport();
  } else if (isPlan) loadPlanningSheet();
  else loadData();
}

// ── Filter toggle ─────────────────────────────────────────────────────────────
function toggleFilters() {
  filterOpen = !filterOpen;
  const panel = document.getElementById("filter-panel");
  const btn = document.getElementById(activeTab === "pr" ? "btn-filter-toggle-pr" : "btn-filter-toggle");
  panel.style.display = filterOpen ? "block" : "none";
  btn.classList.toggle("active", filterOpen);
  if (filterOpen) buildFilterPanel();
}

function buildFilterPanel() {
  const content = document.getElementById("filter-panel-content");
  let html = "";

  if (activeTab === "jc") {
    html += filterGroup("WIP Status", `
      <select data-param="wip" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option>
        ${(wipOptions || []).map(w => `<option>${w}</option>`).join("")}
      </select>`); html += filterGroup("Final Status", `
      <select data-param="status" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option><option>Pending</option><option>Completed</option>
      </select>`);
    html += filterGroup("SO Date From", `<input type="date" data-param="date_from" onchange="currentPage=1;loadData();updateFilterBadge()" />`);
    html += filterGroup("SO Date To", `<input type="date" data-param="date_to"   onchange="currentPage=1;loadData();updateFilterBadge()" />`);
    html += filterGroup("Delivery From", `<input type="date" data-param="delivery_from" onchange="currentPage=1;loadData();updateFilterBadge()" />`);
    html += filterGroup("Delivery To", `<input type="date" data-param="delivery_to"   onchange="currentPage=1;loadData();updateFilterBadge()" />`);
    html += filterGroup("Overdue Only", `
      <select data-param="overdue" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Overdue Only</option>
        <option value="critical">Critical (>7d overdue)</option>
      </select>`);
    html += filterGroup("Subcontracting", `
      <select data-param="subcontracting" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Subcontracting Only</option>
        <option value="no">Non-Subcontracting</option>
      </select>`);
    html += filterGroup("Urgent Only", `
      <select data-param="urgent_only" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Urgent Only</option>
      </select>`);
    html += filterGroup("Sort By", `
      <select data-param="sort" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="jc.created_at">Created Date</option>
        <option value="ji.delivery_date">Delivery Date</option>
        <option value="jc.job_card_no">JC No</option>
        <option value="jc.so_no">SO No</option>
      </select>
      <select data-param="order" onchange="currentPage=1;loadData();updateFilterBadge()" style="margin-top:4px;">
        <option value="desc">Newest First</option>
        <option value="asc">Oldest First</option>
      </select>`);
  }

  else if (activeTab === "qc") {
    html += filterGroup("Quality Result", `
      <select data-param="result" onchange="debounceSearch();updateFilterBadge()">
        <option value="">All</option><option value="OK">OK</option><option value="Not OK">Not OK</option>
      </select>`);
    html += filterGroup("Date From", `<input type="date" data-param="date_from" onchange="debounceSearch();updateFilterBadge()" />`);
    html += filterGroup("Date To", `<input type="date" data-param="date_to"   onchange="debounceSearch();updateFilterBadge()" />`);
    html += filterGroup("Urgent Only", `
      <select data-param="urgent_only" onchange="debounceSearch();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Urgent Only</option>
      </select>`);
    html += filterGroup("Sort By", `
      <select data-param="sort" onchange="debounceSearch();updateFilterBadge()">
        <option value="qc.checked_at">Check Date</option>
        <option value="qcd.item_name">Item Name</option>
      </select>
      <select data-param="order" onchange="debounceSearch();updateFilterBadge()" style="margin-top:4px;">
        <option value="desc">Newest First</option>
        <option value="asc">Oldest First</option>
      </select>`);
  }

  else if (activeTab === "pr") {
    html += filterGroup("WIP Status", `
      <select data-param="wip" onchange="loadProcessReport();updateFilterBadge()">
        <option value="">All</option>
        ${(prWipOptions || []).map(w => `<option>${w}</option>`).join("")}
      </select>`);
    html += filterGroup("Process Status", `
      <select data-param="proc_status" onchange="loadProcessReport();updateFilterBadge()">
        <option value="">All</option>
        <option value="Completed">Completed</option>
        <option value="In Progress">In Progress</option>
        <option value="Subcontracting">Subcontracting</option>
        <option value="Pending">Pending</option>
      </select>`);
    html += filterGroup("Delivery From", `<input type="date" data-param="delivery_from" onchange="loadProcessReport();updateFilterBadge()" />`);
    html += filterGroup("Delivery To", `<input type="date" data-param="delivery_to"   onchange="loadProcessReport();updateFilterBadge()" />`);
    html += filterGroup("Overdue Only", `
      <select data-param="overdue" onchange="loadProcessReport();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Overdue Only</option>
        <option value="critical">Critical (>7d overdue)</option>
      </select>`);
    html += filterGroup("Urgent Only", `
      <select data-param="urgent_only" onchange="loadProcessReport();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Urgent Only</option>
      </select>`);
  }

  else if (activeTab === "ps") {
    html += filterGroup("WIP Status", `
      <select data-param="wip" onchange="loadProcessReport();updateFilterBadge()">
        <option value="">All</option>
        ${(prWipOptions || []).map(w => `<option>${w}</option>`).join("")}
      </select>`);
    html += filterGroup("Delivery From", `<input type="date" data-param="delivery_from" onchange="loadPlanningSheet();updateFilterBadge()" />`);
    html += filterGroup("Delivery To", `<input type="date" data-param="delivery_to"   onchange="loadPlanningSheet();updateFilterBadge()" />`);
    html += filterGroup("Overdue Only", `
      <select data-param="overdue" onchange="loadPlanningSheet();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Overdue Only</option>
        <option value="critical">Critical (>7d overdue)</option>
      </select>`);
    html += filterGroup("Urgent Only", `
      <select data-param="urgent_only" onchange="loadPlanningSheet();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Urgent Only</option>
      </select>`);
  }

  content.innerHTML = html;
}

function filterGroup(label, input) {
  return `<div class="filter-group"><label class="filter-label">${label}</label>${input}</div>`;
}

function updateFilterBadge() {
  let count = 0;
  document.querySelectorAll("#filter-panel-content select").forEach(s => { if (s.value) count++; });
  document.querySelectorAll("#filter-panel-content input[type='date']").forEach(i => { if (i.value) count++; });
  const badge = document.getElementById(activeTab === "pr" ? "filter-count-badge-pr" : "filter-count-badge");
  if (badge) {
    badge.textContent = count;
    badge.style.display = count > 0 ? "inline-block" : "none";
  }
}

function clearAllFilters() {
  document.querySelectorAll("#filter-panel-content select").forEach(s => s.value = "");
  document.querySelectorAll("#filter-panel-content input[type='date']").forEach(i => i.value = "");
  updateFilterBadge();
  if (activeTab === "jc") { currentPage = 1; loadData(); }
  else if (activeTab === "qc") debounceSearch();
  else if (activeTab === "pr") loadProcessReport();
  else if (activeTab === "ps") loadPlanningSheet();
}

// ── Search ────────────────────────────────────────────────────────────────────
function debounceSearch() {
  const val = document.getElementById(activeTab === "pr" ? "pr-search" : "global-search").value;
  document.getElementById("btn-clear-search").style.display = val ? "block" : "none";
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage = 1;
    if (activeTab === "pr") {
      prCurrentPage = 1;
      loadProcessReport();
    } else if (activeTab === "ps") loadPlanningSheet();
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

function getFilterVal(param) {
  const el = document.querySelector(`#filter-panel-content [data-param="${param}"]`);
  return el ? el.value.trim() : "";
}

// ── Load data ─────────────────────────────────────────────────────────────────
async function loadData() {
  document.getElementById("table-body").innerHTML =
    `<tr><td colspan="20">${renderTableSkeleton(8)}</td></tr>`;
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
  const ROTATE_KEYS = [
    "wip_stage_days", "total_days", "remaining_days",
    "days_overdue", "so_qty", "actual_qty",
  ];
  const ths = cols.map(c => {
    const rotate = ROTATE_KEYS.includes(c.key) ? "th-rotate" : "";
    return `<th class="${rotate}" onclick="setSort('${c.key}')" style="cursor:pointer">${c.label}${arrows(c.key)}</th>`;
  }).join("");
  document.getElementById("table-head").innerHTML = `<tr>${ths}</tr>`;
}

function isSubcontracted(row) {
  const value = row?.is_subcontract;
  return value === 1 || value === true || value === "1";
}

function getWipBadgeClass(row, value) {
  if (isSubcontracted(row)) return "badge-subcontract";
  const s = String(value || "").toLowerCase();
  if (s === "store" || s === "complete" || s === "completed") return "badge-ok";
  if (s === "pending") return "badge-pending";
  return "badge-wip";
}

function sameProcess(a, b) {
  return String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
}

function getProcessVisualState(process, index, currentIndex, wipStatus) {
  const wip = String(wipStatus || "").trim().toLowerCase();
  if (wip === "store" || wip === "complete" || wip === "completed") return "completed";
  if (currentIndex === -1) return process.is_completed ? "completed" : "pending";
  if (index < currentIndex) return "completed";
  if (index > currentIndex) return "pending";
  return isSubcontracted(process) ? "subcontract" : "current";
}

// ── Render body ───────────────────────────────────────────────────────────────
function renderBody(cols, rows) {
  const tbody = document.getElementById("table-body");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="${cols.length}"><div class="data-state">No records found</div></td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(row => {
    const cells = cols.map(c => {
      const rawValue = row[c.key];
      let v = c.key === "wip_stage_days" ? (rawValue ?? 0) : formatCellValue(c.key, rawValue);
      if (c.key === "job_card_no" && v) {
        v = `<a class="jc-link" onclick="goToPage3('${String(v).replace(/'/g, "\\'")}')">${v}</a>`;
        if (typeof canEditRowFields === "function" && canEditRowFields(row)) {
          v += ` <i class="fa fa-pencil" style="margin-left:6px;color:var(--accent);cursor:pointer;font-size:11px;" title="Edit fields" onclick="event.stopPropagation(); openEditJobCardModalById('${String(row.job_card_no).replace(/'/g, "\\'")}', '${String(row.item_name).replace(/'/g, "\\'").replace(/"/g, '&quot;')}')"></i>`;
        }
      }
      if (c.key === "is_priority") {
        v = `<input type="checkbox" ${row.is_priority ? "checked" : ""} onchange="togglePriorityImmediate(${Number(row.item_id) || 0}, '${row.job_card_no}', '${encodeURIComponent(row.item_name)}', this.checked, this)" style="width:16px;height:16px;cursor:pointer;accent-color:#dc2626;" />`;
      }
      if (c.key === "quality_result") {
        v = v === "OK" ? `<span class="badge-ok">OK</span>`
          : v === "NOT OK" ? `<span class="badge-notok">Not OK</span>` : v;
      }
      if (c.key === "days_overdue" && v > 0) {
        v = `<span class="badge-overdue">${v}d overdue</span>`;
      }
      if (c.key === "wip_status" && v) {
        const cls = getWipBadgeClass(row, v);
        const vendor = isSubcontracted(row) && row.vendor_name ? ` title="Subcontracting: ${row.vendor_name}"` : "";
        const isStoreOrPending = ["store", "pending"].includes(String(rawValue || "").trim().toLowerCase());
        const clickAttr = (isStoreOrPending || !canEditRowProcess(row)) ? "" : ` style="cursor:pointer;" onclick='openSharedStageModal(${JSON.stringify(row.job_card_no)}, ${JSON.stringify(row.item_name)})'`;
        v = `<span class="${cls}"${vendor}${clickAttr}>${v}</span>`;
      }
      if (c.key === "final_status" && v) {
        const cls = String(v).toLowerCase() === "completed" ? "badge-ok" : "badge-pending";
        v = `<span class="${cls}">${v}</span>`;
      }
      const numericKeys = ["so_qty", "actual_qty", "total_days",
        "remaining_days", "days_overdue", "wip_stage_days"];
      const isNum = numericKeys.includes(c.key);
      const tdStyle = isNum ? "text-align:center;min-width:36px;max-width:52px;" : "";
      return `<td title="${String(formatCellValue(c.key, rawValue))}" style="${tdStyle}">${v}</td>`;
    }).join("");
    const priorityClass = row.is_priority ? "row-priority" : "";
    return `<tr class="${priorityClass}">${cells}</tr>`;
  }).join("");
}

// ── Priority toggle ───────────────────────────────────────────────────────────
// OPTION A — Immediate save, no confirmation (currently active)
async function togglePriorityImmediate(itemId, jobCardNo, encodedItemName, isChecked, checkboxEl) {
  const itemName = decodeURIComponent(encodedItemName);
  try {
    const res = await fetch("/api/job_card_item/priority", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_id: itemId || null, job_card_no: jobCardNo, item_name: itemName, is_priority: isChecked ? 1 : 0 })
    });
    const data = await res.json();
    if (data.success) {
      showToast(isChecked ? "Marked as Urgent" : "Marked as Regular", "success");
      loadData();
    } else {
      showToast(data.error || "Failed to update priority", "error");
      if (checkboxEl) checkboxEl.checked = !isChecked;
    }
  } catch (e) {
    showToast("Server error", "error");
    if (checkboxEl) checkboxEl.checked = !isChecked;
  }
}

/* OPTION B — Confirm before saving (commented out, swap with Option A to test)
   NOTE: window.confirm() is used here only as a placeholder for the manager demo.
   If Option B is chosen for production, replace confirm() with the project's
   custom modal pattern (same two-step modal used on Page 3 for stage changes).
   To activate: change onchange= in the checkbox from togglePriorityImmediate(...)
   to togglePriorityWithConfirm('${row.job_card_no}', '${encodeURIComponent(row.item_name)}', this.checked, this)
   and swap the comment blocks.

async function togglePriorityWithConfirm(jobCardNo, encodedItemName, isChecked, checkboxEl) {
  const itemName = decodeURIComponent(encodedItemName);
  const action = isChecked ? "mark this item as URGENT" : "mark this item as REGULAR (remove urgent status)";
  const confirmed = window.confirm(`Are you sure you want to ${action}?`);
  if (!confirmed) {
    checkboxEl.checked = !isChecked;
    return;
  }
  try {
    const res = await fetch("/api/job_card_item/priority", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_card_no: jobCardNo, item_name: itemName, is_priority: isChecked ? 1 : 0 })
    });
    const data = await res.json();
    if (data.success) {
      showToast(isChecked ? "Marked as Urgent" : "Marked as Regular", "success");
      loadData();
    } else {
      showToast(data.error || "Failed to update priority", "error");
      checkboxEl.checked = !isChecked;
    }
  } catch (e) {
    showToast("Server error", "error");
    checkboxEl.checked = !isChecked;
  }
}
*/

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
  document.getElementById("pr-cards").innerHTML = renderCardSkeleton(3);
  try {
    const search = document.getElementById("pr-search").value.trim();
    const prParams = new URLSearchParams({ search, page: prCurrentPage, per_page: prPerPage });
    const _prWip = getFilterVal("wip");
    const _prProcStatus = getFilterVal("proc_status");
    const _prDelivFrom = getFilterVal("delivery_from");
    const _prDelivTo = getFilterVal("delivery_to");
    const _prOverdue = getFilterVal("overdue");
    const _prUrgent = getFilterVal("urgent_only");
    if (_prWip) prParams.append("wip", _prWip);
    if (_prProcStatus) prParams.append("proc_status", _prProcStatus);
    if (_prDelivFrom) prParams.append("delivery_from", _prDelivFrom);
    if (_prDelivTo) prParams.append("delivery_to", _prDelivTo);
    if (_prOverdue) prParams.append("overdue", _prOverdue);
    if (_prUrgent) prParams.append("urgent_only", _prUrgent);
    const res = await fetch(`/api/data/process_report?${prParams.toString()}`); const data = await res.json();
    if (!data.success) { showToast(data.error, "error"); return; }
    prData = data.data || [];
    if (data.wip_options) prWipOptions = data.wip_options;
    prTotalRows = data.total || prData.length;
    prTotalRows = data.total || prData.length;
    prCurrentPage = data.page || prCurrentPage;
    prPerPage = data.per_page || prPerPage;
    renderPRCards(prData);
    renderPRPagination();
    renderPRRowCount();
    function renderPRPagination() {
      let bar = document.getElementById("pr-pagination-bar");

      if (!bar) {
        bar = document.createElement("div");
        bar.id = "pr-pagination-bar";
        bar.className = "pagination-bar";
        document.getElementById("pr-row-count").before(bar);
      }

      const totalPages = Math.ceil(prTotalRows / prPerPage);

      if (totalPages <= 1) {
        bar.innerHTML = "";
        return;
      }

      bar.innerHTML = `
    <button onclick="goPRPage(${prCurrentPage - 1})" ${prCurrentPage === 1 ? "disabled" : ""}>Prev</button>
    <span style="padding:0 10px;font-weight:700;">Page ${prCurrentPage} of ${totalPages}</span>
    <button onclick="goPRPage(${prCurrentPage + 1})" ${prCurrentPage === totalPages ? "disabled" : ""}>Next</button>
  `;
    }

    function renderPRRowCount() {
      const start = (prCurrentPage - 1) * prPerPage + 1;
      const end = Math.min(prCurrentPage * prPerPage, prTotalRows);

      document.getElementById("pr-row-count").textContent =
        prTotalRows ? `Showing ${start}–${end} of ${prTotalRows} job card(s)` : "No records";
    }
  } catch (e) { showToast("Server error", "error"); }
}
function goPRPage(p) {
  const totalPages = Math.ceil(prTotalRows / prPerPage);

  if (p < 1 || p > totalPages) return;

  prCurrentPage = p;
  loadProcessReport();
}

function renderPRCards(items) {
  const container = document.getElementById("pr-cards");

  if (!items.length) {
    container.innerHTML = `<div class="pr-empty">No records found</div>`;
    return;
  }

  container.innerHTML = items.map(jc => {
    const processNames = jc.process_order || [];

    const procs = processNames.map(proc => {
      const status = jc.process_status_map?.[proc] || "Pending";
      const vendor = jc.process_vendor_map?.[proc] || "";
      const lead = jc.process_lead_days_map?.[proc] ?? 0;
      const actual = jc[proc] || "0d";

      let cls = "proc-pending";
      let badgeText = "Pending";

      if (status === "Completed") {
        cls = "proc-ontime";
        badgeText = "Completed";
      } else if (status === "In Progress") {
        cls = vendor ? "proc-subcontract" : "proc-inprogress";
        badgeText = vendor ? "Subcontracting" : "In Progress";
      } else if (proc === jc.wip_status) {
        cls = "proc-inprogress";
        badgeText = "In Progress";
      }

      const vendorLine = vendor
        ? `<div class="proc-vendor">${vendor}</div>`
        : "";

      const isClickable = (status !== "Completed" && proc === jc.wip_status);
      const clickAttr = isClickable
        ? `onclick='openSharedStageModal(${JSON.stringify(jc.job_card_no)}, ${JSON.stringify(jc.item_name)})' style="cursor:pointer;"`
        : "";

      return `<div class="proc-col ${cls}" ${clickAttr}>
        <div class="proc-name" title="${proc}">${proc}</div>
        <div class="proc-lead">Lead: ${lead}d</div>
        <div class="proc-actual">${actual}</div>
        ${vendorLine}
        <div class="proc-badge">${badgeText}</div>
      </div>`;
    }).join("");

    const rem = jc.delivery_date
      ? Math.ceil((new Date(jc.delivery_date + "T00:00:00") - new Date().setHours(0, 0, 0, 0)) / 86400000)
      : (jc.remaining_days ?? 0);
    const remStyle = rem <= 0
      ? "background:#f0fdf4;border:1px solid #86efac;color:#16a34a;"
      : "background:#fffbeb;border:1px solid #fde68a;color:#92400e;";

    return `<div class="jc-card">
      <div class="jc-card-header">
        <div class="jc-hrow">
          <span><span class="jc-hl">JC</span><a class="jc-link" onclick="goToPage3('${jc.job_card_no}')">${jc.job_card_no}</a></span>
          <span><span class="jc-hl">SO</span>${jc.so_no || "—"}</span>
          <span><span class="jc-hl">Status</span>${jc.final_status || "—"}</span>
          ${jc.delivery_date ? `<span><span class="jc-hl">Delivery</span>${formatDateForDisplay(jc.delivery_date)}</span>` : ""}
        </div>
        <div class="jc-hrow">
          <span class="jc-item-name">${jc.item_name}${jc.is_priority ? ' <span style="background:#dc2626;color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;vertical-align:middle;">URGENT</span>' : ''}</span>
          <span><span class="jc-hl">WIP</span>${jc.wip_status || "—"}</span>
          <span style="${remStyle};padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700;">Remaining: ${rem}d</span>
        </div>
      </div>
      <div class="jc-card-body">
        <div class="proc-grid">${procs}</div>
      </div>
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
    rows: allData.map(r => cols.map(c => formatCellValue(c.key, r[c.key])))
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
  const items = prData || [];
  const processHeaders = [];

  items.forEach(jc => {
    (jc.process_order || []).forEach(proc => {
      if (proc && !processHeaders.includes(proc)) {
        processHeaders.push(proc);
      }
    });
  });

  const headers = [
    "JC No",
    "SO No",
    "Item Name",
    "WIP Status",
    "Delivery Date",
    "Final Status",
    ...processHeaders,
    "Remaining Days"
  ];

  const rows = items.map(jc => [
    jc.job_card_no || "",
    jc.so_no || "",
    jc.item_name || "",
    jc.wip_status || "",
    formatDateForDisplay(jc.delivery_date) || "",
    jc.final_status || "",
    ...processHeaders.map(proc => jc[proc] || "0d"),
    jc.remaining_days ?? 0
  ]);

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet([headers, ...rows]), "Process Report");
  XLSX.writeFile(wb, "process_report.xlsx");
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadData();
// ── Planning Sheet ────────────────────────────────────────────────────────────
let psData = [];

async function loadPlanningSheet() {
  document.getElementById("ps-body").innerHTML =
    `<tr><td colspan="25">${renderTableSkeleton(8)}</td></tr>`;

  try {
    const search = document.getElementById("ps-search").value.trim();
    const wip = getFilterVal("wip") || document.getElementById("ps-wip-filter")?.value || "";
    const _psDelivFrom = getFilterVal("delivery_from");
    const _psDelivTo = getFilterVal("delivery_to");
    const _psOverdue = getFilterVal("overdue");
    const _psUrgent = getFilterVal("urgent_only");
    const psParams = new URLSearchParams({ search, wip });
    if (_psDelivFrom) psParams.append("delivery_from", _psDelivFrom);
    if (_psDelivTo) psParams.append("delivery_to", _psDelivTo);
    if (_psOverdue) psParams.append("overdue", _psOverdue);
    if (_psUrgent) psParams.append("urgent_only", _psUrgent);
    const res = await fetch(`/api/data/planning_sheet?${psParams.toString()}`);
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
    { key: "pend_days", label: "Pend Days" },
    { key: "next_process", label: "Next Stage" },
    { key: "delivery_date", label: "Delivery Date" },
  ];

  // Header
  document.getElementById("ps-head").innerHTML =
    `<tr>${COLS.map(c => `<th>${c.label}</th>`).join("")}</tr>`;

  const tbody = document.getElementById("ps-body");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="${COLS.length}"><div class="data-state">No records found</div></td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(row => {
    const cells = COLS.map(c => {
      let v = row[c.key] ?? "";
      if (DATE_KEYS.has(c.key)) v = formatDateForDisplay(v) || "";

      // WIP status badge
      if (c.key === "wip_status" && v) {
        const cls = getWipBadgeClass(row, v);
        const vendor = isSubcontracted(row) && row.vendor_name ? ` title="Subcontracting: ${row.vendor_name}"` : "";
        v = `<span class="${cls}"${vendor}>${v}</span>`;
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

      return `<td title="${String(formatCellValue(c.key, row[c.key]))}">${v}</td>`;
    }).join("");
    const priorityClass = row.is_priority ? "row-priority" : "";
    return `<tr class="${priorityClass}">${cells}</tr>`;
  }).join("");
}

function clearPSSearch() {
  document.getElementById("ps-search").value = "";
  document.getElementById("ps-clear-search").style.display = "none";
  loadPlanningSheet();
}

function exportPSExcel() {
  if (!psData.length) {
    showToast("No data to export", "error");
    return;
  }

  const fixedHeaders = [
    "JC No", "SO No", "Item Name", "WIP Status",
    "Live Stage Days", "Next Process"
  ];

  const fixedKeys = [
    "job_card_no", "so_no", "item_name", "wip_status",
    "live_stage_days", "next_process"
  ];

  const processHeaders = [
    "Drawing",
    "Raw Material",
    "Cutting",
    "Forging",
    "Normalising",
    "R/Turning",
    "Rough Turning",
    "Heat Treatment",
    "CNC Machining",
    "Conventional Machining",
    "Other Outside Process",
    "Quality Check",
    "Store",
    "Assembly",
    "Blackening",
    "Face Grinding",
    "Slitting",
    "Drilling & Tapping"
  ].filter(p => psData.some(r => Object.prototype.hasOwnProperty.call(r, p)));

  const endHeaders = [
    "Total Days", "Pend Days", "Final Delivery Date", "Final Status"
  ];

  const endKeys = [
    "total_days", "pend_days", "delivery_date", "final_status"
  ];

  const headers = [...fixedHeaders, ...processHeaders, ...endHeaders];

  const rows = psData.map(r => {
    const fixedVals = fixedKeys.map(k => formatCellValue(k, r[k]));
    const processVals = processHeaders.map(p => r[p] ?? 0);
    const endVals = endKeys.map(k => formatCellValue(k, r[k]));
    return [...fixedVals, ...processVals, ...endVals];
  });

  const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
  const wb = XLSX.utils.book_new();

  XLSX.utils.book_append_sheet(wb, ws, "Planning Sheet");
  XLSX.writeFile(wb, "planning_sheet.xlsx");
}
function renderTableSkeleton(rowCount = 6) {
  let rows = "";
  for (let i = 0; i < rowCount; i++) {
    rows += `<div class="skeleton-table-row">
      <div class="skeleton-line short"></div>
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line long"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-line medium"></div>
    </div>`;
  }
  return `<div class="skeleton-wrap">${rows}</div>`;
}
function renderCardSkeleton(cardCount = 3) {
  let cards = "";
  for (let i = 0; i < cardCount; i++) {
    cards += `<div class="skeleton-block" style="height: 140px;"></div>`;
  }
  return `<div class="skeleton-wrap">${cards}</div>`;
}

// ── Shared Stage-Change Modal (reused on PPC tab + Process Report tab) ──────
// Self-contained: fetches full job card data, then reuses the SAME modal
// markup/IDs as Page 3 (#stage-modal, #confirm-stage-modal) which are
// included in page5.html. On success, reloads whichever Page 5 view is
// currently active instead of Page 3's fetchJobCard().
let sharedModalData = null;
let sharedPendingChange = null;

async function openSharedStageModal(jcNo, itemName) {
  try {
    const res = await fetch(`/api/quality_check/fetch/${encodeURIComponent(jcNo)}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error || "Could not load job card", "error"); return; }

    sharedModalData = data;
    const item = (data.items || []).find(it => it.item_name === itemName);
    if (!item) { showToast("Item not found on this job card", "error"); return; }

    // Supervisor process-access pre-check (same rule as Page 3)
    if (Array.isArray(data.my_accessible_processes)) {
      const currentWip = (item.wip_status || "").trim().toLowerCase();
      const hasAccess = data.my_accessible_processes.some(p => p.trim().toLowerCase() === currentWip);
      if (!hasAccess) {
        showToast(`You do not have permission to move items out of '${item.wip_status}'.`, "error");
        return;
      }
    }

    if ((item.wip_status || "").trim().toLowerCase() === "store") {
      showToast("This item is in Store.", "info");
      return;
    }

    const wipIdx = item.wip_process_index ?? -1;
    if (wipIdx === -1) { showToast("All stages completed for this item.", "info"); return; }

    const processes = item.processes || [];
    const nextStageName = wipIdx + 1 < processes.length ? processes[wipIdx + 1] : "Store";
    const currentWIP = item.wip_status || "Pending";

    sharedPendingChange = { jcNo, itemName, currentStage: currentWIP, newStage: nextStageName };

    const plannedQty = item.so_qty || item.job_card_qty || "";
    const actualQtyInput = document.getElementById("modal-actual-qty");
    document.getElementById("modal-planned-qty").value = plannedQty;
    actualQtyInput.value = item.actual_qty || "";
    actualQtyInput.max = plannedQty || "";
    document.getElementById("modal-current-process").textContent = currentWIP;
    document.getElementById("modal-next-process").textContent = nextStageName;
    document.getElementById("modal-title").textContent = "Change Stage?";
    document.getElementById("modal-note").textContent = "Supervisor must be selected at the bottom before confirming.";
    document.getElementById("subcontract-section").style.display = "block";
    document.getElementById("modal-confirm-btn").textContent = "Confirm";
    document.getElementById("subcontract-checkbox").checked = false;
    document.getElementById("vendor-row").style.display = "none";
    document.getElementById("modal-vendor-name").value = "";

    // Populate supervisor select for this modal instance
    const supSelect = document.getElementById("shared-bottom-supervisor");
    if (supSelect) {
      supSelect.innerHTML = `<option value="">-- Select Supervisor --</option>` +
        (data.supervisors || []).map(s => `<option value="${s}">${s}</option>`).join("");
    }

    document.getElementById("stage-modal").classList.add("open");
  } catch (e) {
    showToast("Server error", "error");
  }
}

function closeSharedStageModal() {
  document.getElementById("stage-modal").classList.remove("open");
  sharedPendingChange = null;
}

async function confirmSharedStageChange() {
  if (!sharedPendingChange) return;
  if (!validateSharedStageActualQty()) return;
  document.getElementById("csm-from").textContent = sharedPendingChange.currentStage;
  document.getElementById("csm-to").textContent = sharedPendingChange.newStage;
  document.getElementById("confirm-stage-modal").classList.add("open");
}

function closeSharedConfirmModal() {
  document.getElementById("confirm-stage-modal").classList.remove("open");
}

async function proceedSharedStageChange() {
  closeSharedConfirmModal();
  if (!sharedPendingChange) return;
  if (!validateSharedStageActualQty()) return;

  const { jcNo, itemName, newStage } = sharedPendingChange;
  const supervisor = document.getElementById("shared-bottom-supervisor")?.value || "Not Assigned";

  const sendToSubcontract = document.getElementById("subcontract-checkbox").checked;
  const vendorName = document.getElementById("modal-vendor-name").value.trim();

  try {
    let res, data;
    if (sendToSubcontract) {
      if (!vendorName) { showToast("Please enter vendor name for subcontracting", "error"); return; }
      const leadDays = parseInt(document.getElementById("modal-lead-days")?.value) || 0;
      if (!leadDays || leadDays < 1) { showToast("Please enter lead days for subcontracting", "error"); return; }
      res = await fetch("/api/wip/subcontract", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo, item_name: itemName, process: newStage,
          vendor_name: vendorName, lead_days: leadDays, changed_by: supervisor
        })
      });
    } else {
      res = await fetch("/api/wip/update", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo, item_name: itemName, new_stage: newStage,
          changed_by: supervisor,
          actual_qty: parseInt(document.getElementById("modal-actual-qty")?.value) || 0,
          rejected_qty: 0, rework_qty: 0, rework_remarks: ""
        })
      });
    }
    data = await res.json();
    if (data.success) {
      closeSharedStageModal();
      showToast(data.message || "Stage updated", "success");
      // Reload whichever Page 5 view is currently active
      if (activeTab === "pr") loadProcessReport();
      else loadData();
    } else {
      showToast(data.error || "Update failed", "error");
    }
  } catch (e) {
    showToast("Server error", "error");
  }
}

function validateSharedStageActualQty() {
  const plannedQty = parseFloat(document.getElementById("modal-planned-qty")?.value);
  const actualRaw = document.getElementById("modal-actual-qty")?.value;
  if (actualRaw === "" || actualRaw == null || Number.isNaN(plannedQty)) return true;

  const actualQty = parseFloat(actualRaw);
  if (!Number.isNaN(actualQty) && actualQty > plannedQty) {
    showToast("Actual Qty cannot be more than Planned Qty", "error");
    document.getElementById("modal-actual-qty")?.focus();
    return false;
  }
  return true;
}

// ── Editable Job Card Fields Modal ──────────────────────────────────────────
let editRowData = null;

function currentUserRole() {
  return String(window.JMS_USER_ROLE || "").trim().toLowerCase();
}

function isAdminUser() {
  return currentUserRole() === "admin";
}

function isSupervisorUser() {
  return currentUserRole() === "supervisor";
}

function isEditableUser() {
  return isAdminUser() || isSupervisorUser();
}

function canEditWipStage() {
  return isAdminUser() || isSupervisorUser();
}

function canEditRowProcess(row) {
  if (isAdminUser()) return true;
  if (!isSupervisorUser()) return false;
  return row?.can_edit_current_process === true || row?.can_edit_current_process === 1;
}

function hasPage5Field(row, fieldName) {
  if (isAdminUser()) return true;
  const fields = Array.isArray(row?.page5_editable_fields) ? row.page5_editable_fields : [];
  return fields.includes(fieldName);
}

function canEditRowFields(row) {
  return isAdminUser() || (isSupervisorUser() && Array.isArray(row?.page5_editable_fields) && row.page5_editable_fields.length > 0);
}

function setEditInputState(id, enabled) {
  const el = document.getElementById(id);
  if (!el) return;
  el.disabled = !enabled;
  el.style.background = enabled ? "" : "#f8fafc";
  el.style.color = enabled ? "" : "var(--muted)";
  el.style.cursor = enabled ? "" : "not-allowed";
}

function applyEditFieldPermissions() {
  const row = editRowData || {};
  setEditInputState("ejc-job-card-no", hasPage5Field(row, "job_card_no"));
  setEditInputState("ejc-so-no", hasPage5Field(row, "so_no"));
  setEditInputState("ejc-customer-name", hasPage5Field(row, "customer_name"));
  setEditInputState("ejc-parent-code", hasPage5Field(row, "parent_code"));
  setEditInputState("ejc-child-code", hasPage5Field(row, "child_code"));
  setEditInputState("ejc-item-name", hasPage5Field(row, "item_name"));
  setEditInputState("ejc-so-qty", hasPage5Field(row, "so_qty"));
  setEditInputState("ejc-actual-qty", hasPage5Field(row, "actual_qty"));
  setEditInputState("ejc-remarks", hasPage5Field(row, "remarks"));
  setEditInputState("ejc-vendor-name", hasPage5Field(row, "vendor_name") || hasPage5Field(row, "subcontractor_name"));
}

function openEditJobCardModalById(jcNo, itemName) {
  if (!isEditableUser()) return;
  const row = (allData || []).find(r => String(r.job_card_no) === String(jcNo) && r.item_name === itemName);
  if (!row) { showToast("Could not find this record in the current view", "error"); return; }
  openEditJobCardModal(row);
}

function openEditJobCardModal(row) {
  if (!isEditableUser()) return;
  if (!canEditRowFields(row)) {
    showToast("You do not have rights to update this process.", "error");
    return;
  }
  editRowData = row;

  applyEditFieldPermissions();
  document.getElementById("ejc-job-card-no").value = row.job_card_no || "";
  document.getElementById("ejc-so-no").value = row.so_no || "";
  document.getElementById("ejc-customer-name").value = row.customer_name || "";
  document.getElementById("ejc-parent-code").value = row.parent_code || "";
  document.getElementById("ejc-child-code").value = row.child_code || "";
  document.getElementById("ejc-item-name").value = row.item_name || "";
  document.getElementById("ejc-so-qty").value = row.so_qty ?? "";
  document.getElementById("ejc-actual-qty").value = row.actual_qty ?? "";
  document.getElementById("ejc-remarks").value = row.remarks || "";
  document.getElementById("ejc-vendor-name").value = row.vendor_name || "";

  document.getElementById("edit-jobcard-modal").classList.add("open");
}

function closeEditJobCardModal() {
  document.getElementById("edit-jobcard-modal").classList.remove("open");
  editRowData = null;
}

async function saveEditJobCard() {
  if (!editRowData) return;
  const payload = {
    job_card_no: editRowData.job_card_no, // identifies which row (original JC No)
    item_id: editRowData.item_id || null,
    original_item_name: editRowData.item_name,
    process_name: editRowData.wip_status || "",
  };

  if (hasPage5Field(editRowData, "job_card_no")) {
    payload.new_job_card_no = document.getElementById("ejc-job-card-no").value.trim();
  }
  if (hasPage5Field(editRowData, "so_no")) {
    payload.so_no = document.getElementById("ejc-so-no").value.trim();
  }
  if (hasPage5Field(editRowData, "customer_name")) {
    payload.customer_name = document.getElementById("ejc-customer-name").value.trim();
  }
  if (hasPage5Field(editRowData, "parent_code")) {
    payload.parent_code = document.getElementById("ejc-parent-code").value.trim();
  }
  if (hasPage5Field(editRowData, "child_code")) {
    payload.child_code = document.getElementById("ejc-child-code").value.trim();
  }
  if (hasPage5Field(editRowData, "item_name")) {
    payload.item_name = document.getElementById("ejc-item-name").value.trim();
  }
  if (hasPage5Field(editRowData, "so_qty")) {
    payload.so_qty = document.getElementById("ejc-so-qty").value;
  }

  if (hasPage5Field(editRowData, "actual_qty")) {
    payload.actual_qty = document.getElementById("ejc-actual-qty").value;
  }
  if (hasPage5Field(editRowData, "remarks")) {
    payload.remarks = document.getElementById("ejc-remarks").value.trim();
  }
  if (hasPage5Field(editRowData, "vendor_name") || hasPage5Field(editRowData, "subcontractor_name")) {
    payload.vendor_name = document.getElementById("ejc-vendor-name").value.trim();
  }

  try {
    const res = await fetch("/api/job_card/update_fields", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || "Updated", "success");
      closeEditJobCardModal();
      loadData();
    } else {
      showToast(data.error || "Update failed", "error");
    }
  } catch (e) {
    showToast("Server error", "error");
  }
}
