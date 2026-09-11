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
let woOptions = [];
let prWipOptions = [];
let statusOptions = [];
let supervisorOptions = [];
let selectedSupervisorUserId = "";
let prCurrentPage = 1;
let prTotalRows = 0;
let prPerPage = 30;
window._canSeePriorityColumn = false;
// ── Excel-like Header Filters for PPC tab ───────────────────────────────────
let excelFilters = {};
let excelFilterOptionsCache = {};
let openExcelFilterColumn = null;
let hiddenColumns = {};
let lastAuditTimeFilter = {
  from: "",
  to: ""
};

const PAGE5_HIDDEN_COLUMNS_KEY = `jms_page5_hidden_columns_v1_${window.JMS_CURRENT_USER || 'default'}`;

const EXCEL_FILTERABLE_COLUMNS = new Set([
  "is_priority",
  "job_card_no",
  "waiting_for_jc",
  "so_no",
  "customer_name",
  "parent_code",
  "child_code",
  "work_order_no",
  "assembly_name",
  "item_name",
  "size",
  "material",

  "so_qty",
  "actual_qty",

  "wip_status",
  "remarks",
  "vendor_name",

  "wip_stage_days",
  "total_days",
  "remaining_days",
  "days_overdue",

  "final_status",
  "delivery_date",
  "so_date",
  "last_audit",
]);
const DATE_KEYS = new Set([
  "so_date", "job_card_date", "work_order_date", "delivery_date",
  "created_at", "checked_at", "changed_at", "in_time", "out_time", "lead_date"
]);

function formatCellValue(key, value) {
  if (DATE_KEYS.has(key)) return formatDateForDisplay(value) || "";
  if (key === "is_priority") return value ? "Yes" : "No";
  return value ?? "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
function to12HourLabel(time24) {
  if (!time24) return "";

  const [hhRaw, mmRaw] = String(time24).split(":");
  const hh = parseInt(hhRaw, 10);
  const mm = mmRaw || "00";

  if (Number.isNaN(hh)) return time24;

  const ampm = hh >= 12 ? "PM" : "AM";
  const hour12 = hh % 12 || 12;

  return `${String(hour12).padStart(2, "0")}:${mm} ${ampm}`;
}

function build12HourTimeOptions(selectedValue = "") {
  let html = `<option value="">Any Time</option>`;

  for (let h = 0; h < 24; h++) {
    for (let m of [0, 30]) {
      const value = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      const label = to12HourLabel(value);
      html += `<option value="${value}" ${value === selectedValue ? "selected" : ""}>${label}</option>`;
    }
  }

  return html;
}
function getHiddenColumns() {
  try {
    const parsed = JSON.parse(localStorage.getItem(PAGE5_HIDDEN_COLUMNS_KEY) || "{}");
    if (Array.isArray(parsed)) {
      return parsed.reduce((acc, key) => {
        acc[key] = true;
        return acc;
      }, {});
    }
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (e) {
    return {};
  }
}

function saveHiddenColumns() {
  localStorage.setItem(PAGE5_HIDDEN_COLUMNS_KEY, JSON.stringify(hiddenColumns || {}));
}

function isColumnHidden(key) {
  return activeTab === "jc" && Boolean(hiddenColumns?.[key]);
}

function getVisibleColumns(cols) {
  if (activeTab !== "jc") return cols || [];
  const baseCols = (isDispatchUser() ? DISPATCH_COLS : (cols || []))
    .filter(c => c.key !== "is_priority" || window._canSeePriorityColumn !== false);
  const visible = baseCols.filter(c => !isColumnHidden(c.key));
  return visible.length ? visible : baseCols;
}

function hideColumn(key) {
  if (!key) return false;
  const visibleCount = getVisibleColumns(TAB.jc?.cols || []).length;
  if (visibleCount <= 1 && !hiddenColumns[key]) {
    showToast("At least one PPC column must remain visible", "error");
    return false;
  }
  hiddenColumns[key] = true;
  saveHiddenColumns();
  return true;
}

function showAllColumns() {
  const menu = document.getElementById("column-chooser-menu");
  if (!menu) return;
  menu.querySelectorAll("input[type='checkbox']").forEach(ch => {
    ch.checked = true;
  });
  // Apply immediately
  hiddenColumns = {};
  saveHiddenColumns();
  closeColumnChooser();
  loadData();
}

function closeColumnChooser() {
  const menu = document.getElementById("column-chooser-menu");
  if (menu) menu.remove();
}

function openColumnChooser(event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  if (activeTab !== "jc") return;

  const existing = document.getElementById("column-chooser-menu");
  if (existing) {
    closeColumnChooser();
    return;
  }

  const menu = document.createElement("div");
  menu.id = "column-chooser-menu";
  menu.className = "column-chooser-menu";
  document.body.appendChild(menu);

  const btn = document.getElementById("btn-columns");
  const rect = btn?.getBoundingClientRect();
  const top = rect ? rect.bottom + window.scrollY + 6 : window.scrollY + 90;
  const left = rect ? Math.min(rect.left + window.scrollX, window.scrollX + window.innerWidth - 292) : window.scrollX + 24;
  menu.style.top = `${top}px`;
  menu.style.left = `${Math.max(window.scrollX + 12, left)}px`;

  renderColumnChooser();
}

function renderColumnChooser() {
  const menu = document.getElementById("column-chooser-menu");
  if (!menu) return;

  const baseCols = (isDispatchUser() ? DISPATCH_COLS : TAB.jc.cols)
    .filter(c => c.key !== "is_priority" || window._canSeePriorityColumn !== false);

  menu.innerHTML = `
    <div class="column-chooser-title">Columns</div>
    <div class="column-chooser-list">
      ${baseCols.map(c => `
        <label class="column-chooser-row">
          <input
            type="checkbox"
            value="${escapeHtml(c.key)}"
            ${hiddenColumns[c.key] ? "" : "checked"}
          />
          <span>${escapeHtml(c.label)}</span>
        </label>
      `).join("")}
    </div>
    <div class="column-chooser-actions">
      <button type="button" class="column-chooser-show-all" onclick="showAllColumns()">Show All</button>
      <button type="button" class="column-chooser-cancel" onclick="closeColumnChooser()">Cancel</button>
      <button type="button" class="column-chooser-apply" onclick="applyColumnChooser()">Apply</button>
    </div>
  `;
}
function applyColumnChooser() {
  const menu = document.getElementById("column-chooser-menu");
  if (!menu) return;

  const nextHidden = {};
  let checkedCount = 0;
  menu.querySelectorAll("input[type='checkbox']").forEach(ch => {
    if (ch.checked) checkedCount++;
    else nextHidden[ch.value] = true;
  });

  if (!checkedCount) {
    showToast("At least one PPC column must remain visible", "error");
    return;
  }

  hiddenColumns = nextHidden;
  saveHiddenColumns();
  closeColumnChooser();
  loadData();
}

hiddenColumns = getHiddenColumns();

function renderSupervisorOptions() {
  return (supervisorOptions || []).map(s =>
    `<option value="${escapeHtml(s.id)}" ${String(s.id) === String(selectedSupervisorUserId) ? "selected" : ""}>${escapeHtml(s.username)}</option>`
  ).join("");
}

function getSelectedSupervisorId() {
  const selected = getFilterVal("supervisor_user_id");
  return selected || selectedSupervisorUserId;
}

function getSelectedSupervisorName() {
  const id = getSelectedSupervisorId();
  if (!id) return "";
  const match = (supervisorOptions || []).find(s => String(s.id) === String(id));
  if (match) return match.username || match.full_name || "";
  const el = document.querySelector(`#filter-panel-content [data-param="supervisor_user_id"]`);
  return el?.selectedOptions?.[0]?.textContent?.trim() || "";
}

function ensureSupervisorFilterSummary() {
  let summary = document.getElementById("ppc-supervisor-filter-summary");
  if (summary) return summary;

  const searchRow = document.querySelector("#table-view .search-row");
  if (!searchRow) return null;

  summary = document.createElement("div");
  summary.id = "ppc-supervisor-filter-summary";
  summary.style.display = "none";
  summary.style.margin = "0 0 10px";
  summary.style.alignItems = "center";
  summary.style.gap = "8px";
  summary.style.flexWrap = "wrap";
  searchRow.insertAdjacentElement("afterend", summary);
  return summary;
}

function renderSupervisorFilterSummary() {
  const summary = ensureSupervisorFilterSummary();
  if (!summary) return;

  const supervisorName = getSelectedSupervisorName();
  if (activeTab !== "jc" || !supervisorName) {
    summary.style.display = "none";
    summary.innerHTML = "";
    return;
  }

  summary.style.display = "flex";
  summary.innerHTML = `
    <span style="display:inline-flex;align-items:center;gap:8px;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:700;">
      <i class="fa fa-user" aria-hidden="true"></i>
      Viewing supervisor: ${escapeHtml(supervisorName)}
      <button type="button" onclick="clearSupervisorFilter()" title="Clear supervisor filter" style="border:0;background:transparent;color:#1d4ed8;cursor:pointer;font-size:13px;line-height:1;padding:0 0 0 2px;">
        <i class="fa fa-times" aria-hidden="true"></i>
      </button>
    </span>
  `;
}

function clearSupervisorFilter() {
  selectedSupervisorUserId = "";
  const el = document.querySelector(`#filter-panel-content [data-param="supervisor_user_id"]`);
  if (el) el.value = "";
  updateFilterBadge();
  currentPage = 1;
  loadData();
}
// ── Dispatch user column override ─────────────────────────────────────────────
const DISPATCH_COLS = [
  { key: "job_card_no", label: "JC No" },
  { key: "wip_status", label: "WIP Status" },
  { key: "so_no", label: "SO No" },
  { key: "customer_name", label: "Customer Name" },
  { key: "delivery_date", label: "Delivery Date" },
  { key: "remaining_days", label: "Remaining Days" },
  { key: "item_name", label: "Item Name" },
];
// ── Tab config ────────────────────────────────────────────────────────────────
const TAB = {
  jc: {
    api: "/api/data/job_cards",
    label: "PPC",
    cols: [
      { key: "is_priority", label: "Urgent" },
      { key: "job_card_no", label: "JC No" },
      { key: "wip_status", label: "WIP Status" },
      { key: "wip_stage_days", label: "Days in Stage" },
      { key: "remarks", label: "Remarks" },
      { key: "vendor_name", label: "Subcontractor" },
      { key: "so_no", label: "SO No" },
      { key: "customer_name", label: "Customer Name" },
      { key: "parent_code", label: "Parent Code" },
      { key: "child_code", label: "Child Code" },
      { key: "work_order_no", label: "WO No" },
      // { key: "assembly_name", label: "Assembly Item" },
      { key: "item_name", label: "Item Name" },
      // { key: "size", label: "Size" },
      { key: "material", label: "Material" },
      { key: "so_qty", label: "SO Qty" },
      { key: "actual_qty", label: "Actual Qty" },
      { key: "total_days", label: "Total Days" },
      { key: "remaining_days", label: "Remaining Days" },
      { key: "days_overdue", label: "Days Overdue" },
      { key: "final_status", label: "Status" },
      { key: "delivery_date", label: "Delivery Date" },
      { key: "so_date", label: "SO Date" },
      { key: "last_audit", label: "Last Updated", noSort: true },
      { key: "waiting_for_jc", label: "Waiting For JC" },
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
  closeColumnChooser();
  closeExcelFilterMenu();

  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("tab-" + tab).classList.add("active");

  const isReport = false;
  const isPlan = false;
  const isWs = tab === "ws";
  const isAr = false;

  document.getElementById("table-view").style.display = (!isWs) ? "block" : "none";
  const wsView = document.getElementById("ws-view");
  if (wsView) wsView.style.display = isWs ? "block" : "none";

  const columnsBtn = document.getElementById("btn-columns");
  if (columnsBtn) columnsBtn.style.display = tab === "jc" ? "" : "none";

  // Hide filter panel on tab switch
  const panel = document.getElementById("filter-panel");
  panel.style.display = "none";
  document.getElementById("btn-filter-toggle")?.classList.remove("active");

  document.getElementById("global-search").value = "";
  const prSearch = document.getElementById("pr-search");
  if (prSearch) prSearch.value = "";

  if (isReport) {
    prCurrentPage = 1;
    loadProcessReport();
  } else if (isPlan) loadPlanningSheet();
  else if (isWs) loadWipSummary();
  else if (isAr) loadAssemblyReadiness();
  else loadData();
}

// ── Filter toggle ─────────────────────────────────────────────────────────────
function toggleFilters() {
  // PPC tab uses same filter panel as other tabs

  filterOpen = !filterOpen;
  const panel = document.getElementById("filter-panel");
  const btn = document.getElementById("btn-filter-toggle");
  panel.style.display = filterOpen ? "block" : "none";
  btn?.classList.toggle("active", filterOpen);
  if (filterOpen) buildFilterPanel();
}

function buildFilterPanel() {
  const content = document.getElementById("filter-panel-content");
  let html = "";

  if (activeTab === "jc") {
    html += filterGroup("WO No", `
      <select data-param="work_order_no" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option>
        ${(woOptions || []).map(w => `<option value="${w}">${w}</option>`).join("")}
      </select>`);
    html += filterGroup("WIP Status", `
      <select data-param="wip" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option>
        ${(wipOptions || []).map(w => `<option>${w}</option>`).join("")}
      </select>`);
    html += filterGroup("Final Status", `
      <select data-param="status" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option><option>Pending</option><option>Completed</option>
      </select>`);
    html += filterGroup("Delivery From", `<input type="date" data-param="delivery_from" onchange="currentPage=1;loadData();updateFilterBadge()" />`);
    html += filterGroup("Delivery To", `<input type="date" data-param="delivery_to" onchange="currentPage=1;loadData();updateFilterBadge()" />`);
    html += filterGroup("Overdue Only", `
      <select data-param="overdue" onchange="currentPage=1;loadData();updateFilterBadge()">
        <option value="">All</option>
        <option value="yes">Overdue Only</option>
        <option value="critical">Critical (>7d overdue)</option>
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
  const badge = document.getElementById("filter-count-badge");
  if (badge) {
    badge.textContent = count;
    badge.style.display = count > 0 ? "inline-block" : "none";
  }
}

function clearAllFilters() {
  // PPC tab uses same filter panel as other tabs

  document.querySelectorAll("#filter-panel-content select").forEach(s => s.value = "");
  document.querySelectorAll("#filter-panel-content input[type='date']").forEach(i => i.value = "");
  selectedSupervisorUserId = "";
  renderSupervisorFilterSummary();
  updateFilterBadge();
  if (activeTab === "qc") debounceSearch();
  /* removed: loadProcessReport */
  /* removed: loadPlanningSheet */
}

// ── Search ────────────────────────────────────────────────────────────────────
function debounceSearch() {
  const val = document.getElementById("global-search").value;
  document.getElementById("btn-clear-search").style.display = val ? "block" : "none";
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage = 1;
    if (activeTab === "pr") {
      prCurrentPage = 1;
      loadProcessReport();
    } /* removed: loadPlanningSheet */
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
  const p = new URLSearchParams({
    search,
    page: currentPage,
    per_page: perPage,
    sort: sortCol,
    order: sortOrder
  });

  if (activeTab !== "jc") {
    document.querySelectorAll("#filter-panel-content select").forEach(sel => {
      if (sel.value) p.set(sel.dataset.param, sel.value);
    });

    document.querySelectorAll("#filter-panel-content input[type='date']").forEach(inp => {
      if (inp.value) p.set(inp.dataset.param, inp.value);
    });

    const supervisorSelect = document.querySelector(`#filter-panel-content [data-param="supervisor_user_id"]`);
    if (supervisorSelect) selectedSupervisorUserId = supervisorSelect.value || "";
  }

  const filterDate = localStorage.getItem("jms_filter_date");
  if (filterDate) p.set("filter_date", filterDate);

  // Excel-like header filters for PPC tab.
  // Backend expects params like:
  // xf_wip_status=Drawing&xf_wip_status=Raw Material
  if (activeTab === "jc") {
    p.set("include_dependencies", "1");

    Object.entries(excelFilters || {}).forEach(([columnKey, selectedValues]) => {
      if (!Array.isArray(selectedValues) || selectedValues.length === 0) return;

      selectedValues.forEach(value => {
        p.append(`xf_${columnKey}`, value === "" ? "__BLANK__" : value);
      });
    });

    if (lastAuditTimeFilter.from) {
      p.set("last_audit_time_from", lastAuditTimeFilter.from);
    }

    if (lastAuditTimeFilter.to) {
      p.set("last_audit_time_to", lastAuditTimeFilter.to);
    }
  }

  return p.toString();
}

function isExcelFilterActive(columnKey) {
  return Array.isArray(excelFilters[columnKey]) && excelFilters[columnKey].length > 0;
}

function closeExcelFilterMenu() {
  const existing = document.getElementById("excel-filter-menu");
  if (existing) existing.remove();
  openExcelFilterColumn = null;
}

function getExcelFilterValues(columnKey) {
  return Array.isArray(excelFilters[columnKey]) ? excelFilters[columnKey] : [];
}

function setExcelFilterValues(columnKey, values) {
  const cleaned = Array.from(new Set((values || []).map(v => String(v ?? ""))));
  if (cleaned.length) {
    excelFilters[columnKey] = cleaned;
  } else {
    delete excelFilters[columnKey];
  }
}

async function fetchExcelFilterOptions(columnKey) {
  if (excelFilterOptionsCache[columnKey]) {
    return excelFilterOptionsCache[columnKey];
  }

  const search = document.getElementById("global-search")?.value.trim() || "";
  const params = new URLSearchParams({ column: columnKey });
  if (search) params.set("search", search);

  const res = await fetch(`/api/data/job_cards/filter_options?${params.toString()}`);
  const data = await res.json();

  if (!data.success) {
    showToast(data.error || "Could not load filter values", "error");
    return [];
  }

  excelFilterOptionsCache[columnKey] = data.values || [];
  return excelFilterOptionsCache[columnKey];
}

async function openExcelFilterMenu(event, columnKey, columnLabel) {
  event.preventDefault();
  event.stopPropagation();

  if (activeTab !== "jc") return;

  const button = event.currentTarget;

  if (openExcelFilterColumn === columnKey) {
    closeExcelFilterMenu();
    return;
  }

  closeExcelFilterMenu();
  openExcelFilterColumn = columnKey;

  const menu = document.createElement("div");
  menu.id = "excel-filter-menu";
  menu.className = "excel-filter-menu";
  menu.innerHTML = `
  <div class="excel-filter-title">${escapeHtml(columnLabel)}</div>

  <button type="button" class="excel-filter-sort-btn" data-sort="asc">
    Sort A to Z
  </button>

  <button type="button" class="excel-filter-sort-btn" data-sort="desc">
    Sort Z to A
  </button>

  <div class="excel-filter-separator"></div>

  ${columnKey === "last_audit" ? `
    <div class="excel-time-filter-box">
  <div class="excel-time-filter-title">Filter by Time</div>

  <div class="excel-time-filter-grid">
    <label class="excel-time-filter-label">
      From
      <input
        type="time"
        class="excel-last-audit-time-from"
        value="${escapeHtml(lastAuditTimeFilter.from || "")}"
      />
    </label>

    <label class="excel-time-filter-label">
      To
      <input
        type="time"
        class="excel-last-audit-time-to"
        value="${escapeHtml(lastAuditTimeFilter.to || "")}"
      />
    </label>
  </div>
</div>

    <div class="excel-filter-separator"></div>
  ` : ""}

  <input
    type="text"
    class="excel-filter-search"
    placeholder="Search"
    autocomplete="off"
  />

  <div class="excel-filter-check-row excel-filter-select-all-row">
    <label>
      <input type="checkbox" class="excel-filter-select-all" checked />
      <span>Select All</span>
    </label>
  </div>

  <div class="excel-filter-values">
    <div class="excel-filter-loading">Loading...</div>
  </div>

  <div class="excel-filter-actions">
    <button type="button" class="excel-filter-clear">Clear</button>
    <button type="button" class="excel-filter-apply">Apply</button>
  </div>
`;

  document.body.appendChild(menu);

  const rect = button.getBoundingClientRect();

  const menuWidth = 280;
  const margin = 12;

  let left = rect.left + window.scrollX;
  let top = rect.bottom + window.scrollY + 4;

  const maxLeft = window.scrollX + window.innerWidth - menuWidth - margin;

  if (left > maxLeft) {
    left = maxLeft;
  }

  if (left < window.scrollX + margin) {
    left = window.scrollX + margin;
  }

  menu.style.width = `${menuWidth}px`;
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;

  const options = await fetchExcelFilterOptions(columnKey);
  const selected = getExcelFilterValues(columnKey);
  const hasActiveFilter = selected.length > 0;

  const valuesBox = menu.querySelector(".excel-filter-values");
  const selectAll = menu.querySelector(".excel-filter-select-all");
  const applyBtn = menu.querySelector(".excel-filter-apply");

  function renderValues(filterText = "") {
    const text = filterText.trim().toLowerCase();

    const visibleOptions = options.filter(value => {
      const label = value === "" ? "(Blanks)" : String(value);
      return !text || label.toLowerCase().includes(text);
    });

    if (!visibleOptions.length) {
      valuesBox.innerHTML = `<div class="excel-filter-empty">No values found</div>`;
      updateApplyButtonState();
      return;
    }

    valuesBox.innerHTML = visibleOptions.map(value => {
      const label = value === "" ? "(Blanks)" : String(value);
      const checked = hasActiveFilter ? selected.includes(String(value)) : true;
      const isSubcontractOption =
        columnKey === "wip_status" && String(value).toLowerCase() === "subcontract";
      const labelHtml = isSubcontractOption
        ? `<span class="excel-filter-subcontract-label"><span>${escapeHtml(label)}</span><span class="excel-filter-subcontract-dot"></span></span>`
        : escapeHtml(label);

      return `
        <div class="excel-filter-check-row" data-filter-value="${escapeHtml(value)}">
          <label>
            <input
              type="checkbox"
              class="excel-filter-value-check"
              value="${escapeHtml(value)}"
              ${checked ? "checked" : ""}
            />
            <span>${labelHtml}</span>
          </label>
        </div>
      `;
    }).join("");

    updateSelectAllState();
  }

  function updateSelectAllState() {
    const checks = Array.from(menu.querySelectorAll(".excel-filter-value-check"));

    if (!checks.length) {
      selectAll.checked = false;
      selectAll.indeterminate = false;
      updateApplyButtonState();
      return;
    }

    const checkedCount = checks.filter(ch => ch.checked).length;

    selectAll.checked = checkedCount === checks.length;
    selectAll.indeterminate = checkedCount > 0 && checkedCount < checks.length;

    updateApplyButtonState();
  }

  function updateApplyButtonState() {
    const checks = Array.from(menu.querySelectorAll(".excel-filter-value-check"));
    const checkedCount = checks.filter(ch => ch.checked).length;

    if (!applyBtn) return;

    applyBtn.disabled = checkedCount === 0;
    applyBtn.classList.toggle("disabled", checkedCount === 0);
    applyBtn.title = checkedCount === 0 ? "Select at least one value to apply filter" : "";
  }

  renderValues();

  menu.querySelector(".excel-filter-search").addEventListener("input", function () {
    renderValues(this.value);
  });

  selectAll.addEventListener("change", function () {
    menu.querySelectorAll(".excel-filter-value-check").forEach(ch => {
      ch.checked = selectAll.checked;
    });
    updateSelectAllState();
  });

  valuesBox.addEventListener("change", function (e) {
    if (e.target.classList.contains("excel-filter-value-check")) {
      updateSelectAllState();
    }
  });

  menu.querySelectorAll(".excel-filter-sort-btn").forEach(btn => {
    btn.addEventListener("click", function () {
      sortCol = columnKey;
      sortOrder = this.dataset.sort;
      currentPage = 1;
      closeExcelFilterMenu();
      loadData();
    });
  });

  menu.querySelector(".excel-filter-clear").addEventListener("click", function () {
    delete excelFilters[columnKey];

    if (columnKey === "last_audit") {
      lastAuditTimeFilter = { from: "", to: "" };
    }

    currentPage = 1;
    closeExcelFilterMenu();
    loadData();
  });

  menu.querySelector(".excel-filter-apply").addEventListener("click", function () {
    const visibleChecks = Array.from(menu.querySelectorAll(".excel-filter-value-check"));
    const checkedValues = visibleChecks
      .filter(ch => ch.checked)
      .map(ch => ch.value);

    if (checkedValues.length === options.length) {
      delete excelFilters[columnKey];
    } else {
      setExcelFilterValues(columnKey, checkedValues);
    }

    if (columnKey === "last_audit") {
      lastAuditTimeFilter = {
        from: menu.querySelector(".excel-last-audit-time-from")?.value || "",
        to: menu.querySelector(".excel-last-audit-time-to")?.value || ""
      };
    }

    currentPage = 1;
    closeExcelFilterMenu();
    loadData();
  });

  const hideBtn = menu.querySelector(".excel-filter-hide-column");
  if (hideBtn) {
    hideBtn.addEventListener("click", function () {
      if (!hideColumn(columnKey)) return;
      closeExcelFilterMenu();
      loadData();
    });
  }
}

document.addEventListener("click", function (event) {
  const menu = document.getElementById("excel-filter-menu");
  const columnChooser = document.getElementById("column-chooser-menu");

  if (
    menu?.contains(event.target) ||
    event.target.closest(".excel-filter-btn")
  ) {
    return;
  }

  if (
    columnChooser?.contains(event.target) ||
    event.target.closest("#btn-columns")
  ) {
    return;
  }

  closeExcelFilterMenu();
  closeColumnChooser();
});

function getFilterVal(param) {
  const el = document.querySelector(`#filter-panel-content [data-param="${param}"]`);
  return el ? el.value.trim() : "";
}

// ── Load data ─────────────────────────────────────────────────────────────────
async function loadData() {
  const cfg = TAB[activeTab];
  const visibleCols = getVisibleColumns(cfg?.cols || []);
  const loadingColspan = (visibleCols.length || 20) + ((activeTab === "jc" && canDeletePpcItems()) ? 1 : 0);
  document.getElementById("table-body").innerHTML =
    `<tr><td colspan="${loadingColspan}">${renderTableSkeleton(8)}</td></tr>`;
  try {
    const res = await fetch(`${cfg.api}?${buildParams()}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error, "error"); return; }

    allData = data.data;
    totalRows = data.total || data.data.length;

    if (activeTab === "jc") {
      if (data.wip_options && !wipOptions.length) wipOptions = data.wip_options;
      statusOptions = data.status_options || statusOptions;
      supervisorOptions = data.supervisor_options || supervisorOptions;
      if (data.wo_options) woOptions = data.wo_options;
      if (data.can_see_rm_status !== undefined) window._canSeeRmStatus = data.can_see_rm_status;
      if (data.can_see_priority_column !== undefined) window._canSeePriorityColumn = data.can_see_priority_column;
    }

    const renderCols = getVisibleColumns(cfg?.cols || []);
    renderHead(renderCols);
    renderBody(renderCols, data.data);
    renderPagination();
    renderSupervisorAwareRowCount();
    renderSupervisorFilterSummary();

  } catch (e) { console.error("LOADDATA ERROR:", e); showToast("Error: " + e.message, "error"); }
}

// ── Render head ───────────────────────────────────────────────────────────────
// ── Excel-like Column Resize ────────────────────────────────────────────────
const PAGE5_COL_WIDTH_KEY = "jms_page5_column_widths_v1";

const DEFAULT_COL_WIDTHS = {
  is_priority: 70,
  job_card_no: 120,
  so_no: 110,
  customer_name: 180,
  work_order_no: 120,
  parent_code: 130,
  child_code: 130,
  item_name: 260,
  so_qty: 80,
  actual_qty: 90,
  wip_status: 150,
  remarks: 220,
  vendor_name: 160,
  wip_stage_days: 70,
  total_days: 70,
  remaining_days: 80,
  days_overdue: 80,
  final_status: 110,
  delivery_date: 120,
  so_date: 120,
  last_audit: 170,
  supervisor: 140,
  __actions: 70
};

function getSavedColumnWidths() {
  try {
    return JSON.parse(localStorage.getItem(PAGE5_COL_WIDTH_KEY) || "{}");
  } catch (e) {
    return {};
  }
}

function saveColumnWidth(tab, key, width) {
  const saved = getSavedColumnWidths();
  if (!saved[tab]) saved[tab] = {};
  saved[tab][key] = width;
  localStorage.setItem(PAGE5_COL_WIDTH_KEY, JSON.stringify(saved));
}

function getColumnWidth(tab, key) {
  const saved = getSavedColumnWidths();
  return saved?.[tab]?.[key] || DEFAULT_COL_WIDTHS[key] || 140;
}

function buildResizableColgroup(table, columns) {
  const oldColgroup = table.querySelector("colgroup");
  if (oldColgroup) oldColgroup.remove();

  const colgroup = document.createElement("colgroup");

  columns.forEach(col => {
    const colEl = document.createElement("col");
    colEl.dataset.key = col.key;
    colEl.style.width = `${getColumnWidth(activeTab, col.key)}px`;
    colgroup.appendChild(colEl);
  });

  table.insertBefore(colgroup, table.firstChild);
}

function initColumnResize(table, columns) {
  const handles = table.querySelectorAll(".col-resize-handle");
  const colgroup = table.querySelector("colgroup");
  if (!colgroup) return;

  handles.forEach(handle => {
    handle.addEventListener("click", e => e.stopPropagation());

    handle.addEventListener("mousedown", function (e) {
      e.preventDefault();
      e.stopPropagation();

      const index = Number(this.dataset.colIndex);
      const key = this.dataset.colKey;
      const col = colgroup.children[index];

      const startX = e.clientX;
      const startWidth = parseInt(col.style.width, 10) || 120;
      const minWidth = 55;

      document.body.classList.add("is-resizing-column");

      function onMouseMove(moveEvent) {
        const diff = moveEvent.clientX - startX;
        const newWidth = Math.max(minWidth, startWidth + diff);
        col.style.width = `${newWidth}px`;
      }

      function onMouseUp() {
        const finalWidth = parseInt(col.style.width, 10) || startWidth;
        saveColumnWidth(activeTab, key, finalWidth);

        document.body.classList.remove("is-resizing-column");
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      }

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
  });
}

// ── Render head ───────────────────────────────────────────────────────────────
function renderHead(cols) {
  const arrows = (key) => {
    if (sortCol !== key) {
      return `<span class="sort-ind"><i class="fa fa-sort" aria-hidden="true"></i></span>`;
    }

    return sortOrder === "asc"
      ? `<span class="sort-ind"><i class="fa fa-sort-asc" aria-hidden="true"></i></span>`
      : `<span class="sort-ind"><i class="fa fa-sort-desc" aria-hidden="true"></i></span>`;
  };

  const ROTATE_KEYS = [
    "wip_stage_days",
    "total_days",
    "remaining_days",
    "days_overdue",
    "so_qty",
    "actual_qty",
  ];

  const showActionCol = activeTab === "jc" && canDeletePpcItems();

  const resizeCols = showActionCol
    ? [...cols, { key: "__actions", label: "Actions", noSort: true }]
    : [...cols];

  const table = document.getElementById("data-table");
  if (table) {
    buildResizableColgroup(table, resizeCols);
  }

  const ths = cols.map((c, index) => {
    const rotate = ROTATE_KEYS.includes(c.key) ? "th-rotate" : "";
    // Header click sorting disabled.
    // Sorting is available only from the filter dropdown menu.
    const sortClick = "";
    const cursorStyle = "";

    const filterLabel = c.key === "last_audit" ? "Last Updated By" : c.label;
    const filterBtn = activeTab === "jc" && EXCEL_FILTERABLE_COLUMNS.has(c.key)
      ? `
    <button
      type="button"
      class="excel-filter-btn ${isExcelFilterActive(c.key) ? "active" : ""}"
      title="Filter ${filterLabel}"
      onclick="openExcelFilterMenu(event, '${c.key}', '${String(filterLabel).replace(/'/g, "\\'")}')"
    >
      <i class="fa fa-filter" aria-hidden="true"></i>
    </button>
  `
      : "";

    return `
  <th class="${rotate} resizable-th" ${sortClick} ${cursorStyle}>
    <span class="th-label">${c.label}</span>
    ${filterBtn}
    <span
      class="col-resize-handle"
      data-col-index="${index}"
      data-col-key="${c.key}"
      title="Drag to resize column"
    ></span>
  </th>
`;
  }).join("");

  const actionTh = showActionCol
    ? `
      <th class="resizable-th" style="text-align:center;">
        <span class="th-label">Actions</span>
        <span
          class="col-resize-handle"
          data-col-index="${cols.length}"
          data-col-key="__actions"
          title="Drag to resize column"
        ></span>
      </th>
    `
    : "";

  document.getElementById("table-head").innerHTML = `<tr>${ths}${actionTh}</tr>`;

  if (table) {
    initColumnResize(table, resizeCols);
  }
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
  const showDeleteAction = activeTab === "jc" && canDeletePpcItems();
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="${cols.length + (showDeleteAction ? 1 : 0)}"><div class="data-state">No records found</div></td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((row, index) => {
    const cells = cols.map(c => {
      const rawValue = row[c.key];
      let v = c.key === "wip_stage_days" ? (rawValue ?? 0) : formatCellValue(c.key, rawValue);
      if (c.key === "job_card_no" && v) {
        v = `<a class="jc-link" onclick="goToPage3('${String(v).replace(/'/g, "\\'")}')">${v}</a>`;
        if (typeof canEditRowFields === "function" && canEditRowFields(row)) {
          v += ` <i class="fa fa-pencil" style="margin-left:6px;color:var(--accent);cursor:pointer;font-size:11px;" title="Edit fields" onclick="event.stopPropagation(); openEditJobCardModalById('${String(row.job_card_no).replace(/'/g, "\\'")}', '${String(row.item_name).replace(/'/g, "\\'").replace(/"/g, '&quot;')}')"></i>`;
        }
      }
      if (c.key === "waiting_for_jc" && v) {
        v = `<a class="jc-link" onclick="goToPage3('${String(v).replace(/'/g, "\'")}')">${v}</a>`;
      }
      if (c.key === "is_priority") {
        const canEditPriority = hasPage5Field(row, "is_priority");
        v = `<input type="checkbox" ${row.is_priority ? "checked" : ""} ${canEditPriority ? "" : "disabled"} onchange="togglePriorityImmediate(${Number(row.item_id) || 0}, '${row.job_card_no}', '${encodeURIComponent(row.item_name)}', this.checked, this)" style="width:16px;height:16px;cursor:${canEditPriority ? "pointer" : "not-allowed"};accent-color:#dc2626;" />`;
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
        const rmBadge = (window._canSeeRmStatus && row.rm_hold_reason) ? ` <span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:10px;margin-left:4px;${row.rm_hold_reason === 'testing' ? 'background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;' : 'background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;'}">${row.rm_hold_reason === 'testing' ? '<i class=\"fa fa-flask\"></i> Testing' : '<i class=\"fa fa-exclamation-triangle\"></i> Shortage'}</span>` : "";
        v = `<span class="${cls}"${vendor}${clickAttr}>${v}</span>${rmBadge}`;
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
    const actionCell = showDeleteAction
      ? `<td style="text-align:center;min-width:58px;max-width:58px;">
          <button type="button" title="Delete item" onclick="softDeletePpcItem(${index})" style="width:28px;height:28px;border:1px solid #fecaca;border-radius:4px;background:#fef2f2;color:#dc2626;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;">
            <i class="fa fa-trash" aria-hidden="true"></i>
          </button>
        </td>`
      : "";
    const priorityClass = window._canSeePriorityColumn !== false && row.is_priority ? "row-priority" : "";
    return `<tr class="${priorityClass}">${cells}${actionCell}</tr>`;
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
    showToast("Error: " + (e.message || e), "error");
    if (checkboxEl) checkboxEl.checked = !isChecked;
  }
}

let pendingDeleteRow = null;

function softDeletePpcItem(rowIndex) {
  if (!canDeletePpcItems()) {
    showToast("You do not have permission to delete job cards.", "error");
    return;
  }

  const row = (allData || [])[rowIndex];

  if (!row || !row.job_card_no) {
    showToast("Could not find the Job Card number.", "error");
    return;
  }

  pendingDeleteRow = row;
  openPermanentDeleteModal(row);
}

function openPermanentDeleteModal(row) {
  let modal = document.getElementById("delete-item-modal");

  if (!modal) {
    modal = document.createElement("div");
    modal.id = "delete-item-modal";

    modal.innerHTML = `
      <div style="
        width:92%;
        max-width:460px;
        background:#ffffff;
        border-radius:10px;
        box-shadow:0 18px 50px rgba(0,0,0,0.25);
        overflow:hidden;
      ">
        <div style="
          padding:18px 22px;
          background:#b91c1c;
          color:#ffffff;
          display:flex;
          align-items:center;
          justify-content:space-between;
        ">
          <div style="font-size:17px;font-weight:700;">
            <i class="fa fa-exclamation-triangle"></i>
            Permanent Delete
          </div>

          <button
            type="button"
            onclick="closeDeleteItemModal()"
            style="
              border:none;
              background:transparent;
              color:#ffffff;
              font-size:20px;
              cursor:pointer;
            "
          >
            &times;
          </button>
        </div>

        <div style="padding:22px;">
          <p style="
            margin:0 0 12px;
            font-size:14px;
            color:#111827;
            line-height:1.6;
          ">
            Are you sure you want to permanently delete this complete Job Card?
          </p>

          <div style="
            padding:12px 14px;
            background:#fef2f2;
            border:1px solid #fecaca;
            border-radius:6px;
            margin-bottom:14px;
          ">
            <div style="font-size:11px;color:#991b1b;font-weight:700;text-transform:uppercase;">
              Job Card
            </div>

            <div id="delete-item-label" style="
              margin-top:4px;
              font-family:monospace;
              font-size:14px;
              font-weight:700;
              color:#7f1d1d;
            "></div>
          </div>

          <p style="
            margin:0;
            font-size:12px;
            color:#6b7280;
            line-height:1.5;
          ">
            This will delete the Job Card and all connected records. This action cannot be undone.
          </p>
        </div>

        <div style="
          padding:14px 22px;
          background:#f9fafb;
          border-top:1px solid #e5e7eb;
          display:flex;
          justify-content:flex-end;
          gap:10px;
        ">
          <button
            type="button"
            onclick="closeDeleteItemModal()"
            style="
              padding:9px 18px;
              border:1px solid #d1d5db;
              background:#ffffff;
              border-radius:6px;
              cursor:pointer;
              font-size:13px;
            "
          >
            Cancel
          </button>

          <button
            type="button"
            id="delete-item-confirm-btn"
            onclick="confirmDeleteItem()"
            style="
              padding:9px 18px;
              border:none;
              background:#dc2626;
              color:#ffffff;
              border-radius:6px;
              cursor:pointer;
              font-size:13px;
              font-weight:700;
            "
          >
            <i class="fa fa-trash"></i>
            Delete Permanently
          </button>
        </div>
      </div>
    `;

    modal.style.cssText = `
      display:none;
      position:fixed;
      inset:0;
      z-index:9999;
      background:rgba(15,23,42,0.55);
      align-items:center;
      justify-content:center;
      padding:16px;
    `;

    modal.addEventListener("click", function (event) {
      if (event.target === modal) {
        closeDeleteItemModal();
      }
    });

    document.body.appendChild(modal);
  }

  document.getElementById("delete-item-label").textContent =
    (row.job_card_no || "") +
    (row.item_name ? " - " + row.item_name : "");

  modal.style.display = "flex";
}

function closeDeleteItemModal() {
  const modal = document.getElementById("delete-item-modal");
  if (modal) modal.style.display = "none";
  pendingDeleteRow = null;
}

async function confirmDeleteItem() {
  if (!pendingDeleteRow) return;

  const row = pendingDeleteRow;
  const confirmBtn = document.getElementById("delete-item-confirm-btn");
  const deleteReason = "Permanent deletion from Data View";
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Deleting...";
  }

  try {
    const res = await fetch("/api/job_card_item/soft_delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        item_id: row.item_id || null,
        job_card_no: row.job_card_no || "",
        item_name: row.item_name || "",
        delete_reason: deleteReason.trim()
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || "Item deleted successfully", "success");
      closeDeleteItemModal();
      loadData();
    } else {
      showToast(data.error || "Delete failed", "error");
    }
  } catch (e) {
    showToast("Error: " + (e.message || e), "error");
  } finally {
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = "Delete";
    }
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
    showToast("Error: " + (e.message || e), "error");
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
function renderSupervisorAwareRowCount() {
  const start = (currentPage - 1) * perPage + 1;
  const end = Math.min(currentPage * perPage, totalRows);
  const supervisorName = activeTab === "jc" ? getSelectedSupervisorName() : "";
  const supervisorText = supervisorName ? ` for ${supervisorName}` : "";
  document.getElementById("row-count").textContent =
    totalRows ? `Showing ${start}-${end} of ${totalRows} records${supervisorText}` : `No records${supervisorText}`;
}

async function loadProcessReport( /* DISABLED */ ) { return; }
async function _loadProcessReport_disabled() {
  document.getElementById("pr-cards").innerHTML = renderCardSkeleton(3);
  try {
    const search = document.getElementById("pr-search").value.trim();
    const prParams = new URLSearchParams({ search, page: prCurrentPage, per_page: prPerPage });
    const _prFilterDate = localStorage.getItem("jms_filter_date");
    if (_prFilterDate) prParams.append("filter_date", _prFilterDate);
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
  } catch (e) { showToast("Error: " + (e.message || e), "error"); }
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
      const inDate = jc.process_in_time_map?.[proc] || "";
      const outDate = jc.process_out_time_map?.[proc] || "";

      let cls = "proc-pending";
      let badgeText = "Pending";

      if (status === "On Time") {
        cls = "proc-ontime";
        badgeText = "On Time";
      } else if (status === "Delayed") {
        cls = "proc-delayed";
        badgeText = "Delayed";
      } else if (status === "Completed") {
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
        <div class="proc-lead">In: ${inDate ? formatDateForDisplay(inDate) : "-"}</div>
        <div class="proc-lead">Out: ${outDate ? formatDateForDisplay(outDate) : "-"}</div>
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
          <span><span class="jc-hl">JC</span><a class="jc-link" style="cursor:pointer; color:white;" onclick="goToPage3('${jc.job_card_no}')">${jc.job_card_no}</a></span>
          <span><span class="jc-hl">SO</span>${jc.so_no || "—"}</span>
          <span><span class="jc-hl">Status</span>${jc.final_status || "—"}</span>
          ${jc.delivery_date ? `<span><span class="jc-hl">Delivery</span>${formatDateForDisplay(jc.delivery_date)}</span>` : ""}
        </div>
        <div class="jc-hrow">
          <span class="jc-item-name">${jc.item_name}${window._canSeePriorityColumn !== false && jc.is_priority ? ' <span style="background:#dc2626;color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:10px;vertical-align:middle;">URGENT</span>' : ''}</span>
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
  const cols = getVisibleColumns(TAB[activeTab]?.cols || []);
  return {
    headers: cols.map(c => c.label),
    rows: allData.map(r => cols.map(c => formatCellValue(c.key, r[c.key])))
  };
}
async function exportExcel() {
  showToast("Preparing export...", "success");
  try {
    const cfg = TAB[activeTab];
    if (!cfg) return;

    // Build params same as current view but with no pagination
    const search = document.getElementById("global-search").value.trim();
    const p = new URLSearchParams({
      search,
      page: 1,
      per_page: 99999,
      sort: sortCol,
      order: sortOrder
    });

    // Apply same filters as current view
    if (activeTab !== "jc") {
      document.querySelectorAll("#filter-panel-content select").forEach(sel => {
        if (sel.value) p.set(sel.dataset.param, sel.value);
      });
      document.querySelectorAll("#filter-panel-content input[type='date']").forEach(inp => {
        if (inp.value) p.set(inp.dataset.param, inp.value);
      });
    }
    const filterDate = localStorage.getItem("jms_filter_date");
    if (filterDate) p.set("filter_date", filterDate);
    if (activeTab === "jc") {
      Object.entries(excelFilters || {}).forEach(([columnKey, selectedValues]) => {
        if (!Array.isArray(selectedValues) || selectedValues.length === 0) return;
        selectedValues.forEach(v => p.append(`xf_${columnKey}`, v));
      });
      if (lastAuditTimeFilter.from) p.set("audit_time_from", lastAuditTimeFilter.from);
      if (lastAuditTimeFilter.to) p.set("audit_time_to", lastAuditTimeFilter.to);
      const supervisorId = getSelectedSupervisorId();
      if (supervisorId) p.set("supervisor_user_id", supervisorId);

      // Export-only dependency information.
      p.set("include_dependencies", "1");
    }

    const res = await fetch(`${cfg.api}?${p.toString()}`);
    const data = await res.json();
    if (!data.success) { showToast("Export failed: " + data.error, "error"); return; }

    const cols = getVisibleColumns(cfg.cols || []);

    const dependencyCols = activeTab === "jc"
      ? [
          { key: "jc_dependency", label: "JC Dependency" },
          { key: "waiting_for_jc", label: "Waiting For JC" },
          { key: "activation_condition", label: "Activation Condition" },
        ]
      : [];

    const headers = [
      ...cols.map(c => c.label),
      ...dependencyCols.map(c => c.label),
    ];

    const rows = (data.data || []).map(r => [
      ...cols.map(c => formatCellValue(c.key, r[c.key])),
      ...dependencyCols.map(c => r[c.key] ?? ""),
    ]);

    const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Data");
    XLSX.writeFile(wb, "export.xlsx");
    showToast(`Exported ${rows.length} records.`, "success");
  } catch (e) {
    showToast("Export failed: " + e.message, "error");
  }
}

function exportPDF() {
  const { headers, rows } = getExportData();
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ orientation: "landscape" });
  doc.autoTable({ head: [headers], body: rows, styles: { fontSize: 8 }, headStyles: { fillColor: [30, 58, 95] } });
  doc.save("export.pdf");
}

function exportPRExcel( /* DISABLED */ ) { return; }
function _exportPRExcel_disabled() {
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

async function loadPlanningSheet( /* DISABLED */ ) { return; }
async function _loadPlanningSheet_disabled() {
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
    const _psFilterDate = localStorage.getItem("jms_filter_date");
    if (_psFilterDate) psParams.append("filter_date", _psFilterDate);
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
  } catch (e) { showToast("Error: " + (e.message || e), "error"); }
}

function renderPSTable(rows) {
  const COLS = [
    { key: "job_card_no", label: "JC No" },
    { key: "assembly_name", label: "Assembly" },
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
    const priorityClass = window._canSeePriorityColumn !== false && row.is_priority ? "row-priority" : "";
    return `<tr class="${priorityClass}">${cells}</tr>`;
  }).join("");
}

function clearPSSearch( /* DISABLED */ ) { return; }
function _clearPSSearch_disabled() {
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

function selectRmReason(reason) {
  const testBtn = document.getElementById("rm-btn-testing");
  const shortBtn = document.getElementById("rm-btn-shortage");
  const input = document.getElementById("rm-hold-reason-value");
  if (!input) return;

  if (input.value === reason) {
    input.value = "";
    if (testBtn) { testBtn.style.background = "#eff6ff"; testBtn.style.borderColor = "#bfdbfe"; }
    if (shortBtn) { shortBtn.style.background = "#fffbeb"; shortBtn.style.borderColor = "#fde68a"; }
    return;
  }

  input.value = reason;
  if (reason === "testing") {
    if (testBtn) { testBtn.style.background = "#1d4ed8"; testBtn.style.borderColor = "#1d4ed8"; testBtn.style.color = "#fff"; }
    if (shortBtn) { shortBtn.style.background = "#fffbeb"; shortBtn.style.borderColor = "#fde68a"; shortBtn.style.color = "#92400e"; }
  } else {
    if (shortBtn) { shortBtn.style.background = "#92400e"; shortBtn.style.borderColor = "#92400e"; shortBtn.style.color = "#fff"; }
    if (testBtn) { testBtn.style.background = "#eff6ff"; testBtn.style.borderColor = "#bfdbfe"; testBtn.style.color = "#1d4ed8"; }
  }
}

function showRmReasonIfNeeded(nextStage) {
  const section = document.getElementById("rm-reason-section");
  const input = document.getElementById("rm-hold-reason-value");
  if (!section) return;
  const isRm = (nextStage || "").trim().toLowerCase() === "raw material";
  section.style.display = isRm ? "block" : "none";
  if (!isRm && input) input.value = "";
  if (isRm) selectRmReason("");
}

async function openSharedStageModal(jcNo, itemName) {
  try {
    const res = await fetch(`/api/quality_check/fetch/${encodeURIComponent(jcNo)}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error || "Could not load job card", "error"); return; }

    sharedModalData = data;
    const item = (data.items || []).find(it => it.item_name === itemName);
    if (!item) { showToast("Item not found on this job card", "error"); return; }

    // Supervisor process-access pre-check (same rule as Page 3)
    if (!isGaurangSpecialUser() && Array.isArray(data.my_accessible_processes)) {
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

    const plannedQty = getSharedStagePlannedQty(item);
    const actualQtyInput = document.getElementById("modal-actual-qty");
    document.getElementById("modal-planned-qty").value = plannedQty ?? "";

    let autoActualQty = item.actual_qty || "";
    if (!autoActualQty || String(autoActualQty) === "0") {
      autoActualQty = plannedQty ?? "";
    }

    actualQtyInput.value = autoActualQty;
    actualQtyInput.min = "0";
    actualQtyInput.max = plannedQty ?? "";
    document.getElementById("modal-current-process").textContent = currentWIP;
    document.getElementById("modal-next-process").textContent = nextStageName;
    document.getElementById("modal-title").textContent = "Change Stage?";
    document.getElementById("modal-note").innerHTML = `
      
      <div class="logged-user-content">
        <div class="logged-user-label">Stage change will be recorded by</div>
        <div class="logged-user-name">
          ${(window.JMS_CURRENT_USER || window.JMS_CURRENT_USERNAME || "User").trim()}
        </div>
      </div>
    `;
    document.getElementById("modal-note").className = "modal-note logged-user-note";
    document.getElementById("subcontract-section").style.display = "block";
    document.getElementById("modal-confirm-btn").textContent = "Confirm";
    document.getElementById("subcontract-checkbox").checked = false;
    document.getElementById("vendor-row").style.display = "none";
    document.getElementById("modal-vendor-name").value = "";
    const stageRemarkEl = document.getElementById("modal-stage-remark");
    if (stageRemarkEl) stageRemarkEl.value = "";

    showRmReasonIfNeeded(nextStageName);
    document.getElementById("stage-modal").classList.add("open");
  } catch (e) {
    showToast("Error: " + (e.message || e), "error");
  }
}

function closeSharedStageModal() {
  document.getElementById("stage-modal").classList.remove("open");
  sharedPendingChange = null;
  const stageRemarkEl = document.getElementById("modal-stage-remark");
  if (stageRemarkEl) stageRemarkEl.value = "";
}

async function confirmSharedStageChange() {
  const rmReason = document.getElementById("rm-hold-reason-value")?.value || null;
  if (sharedPendingChange) sharedPendingChange.rm_hold_reason = rmReason;
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

  const supervisor =
    (document.getElementById("shared-bottom-supervisor")?.value ||
      window.JMS_CURRENT_USER ||
      window.JMS_CURRENT_USERNAME ||
      "System").trim();

  const actualQty =
    parseInt(document.getElementById("modal-actual-qty")?.value) || 0;

  const stageRemark =
    document.getElementById("modal-stage-remark")?.value.trim() || "";

  const sendToSubcontract =
    document.getElementById("subcontract-checkbox")?.checked || false;

  const vendorName =
    document.getElementById("modal-vendor-name")?.value.trim() || "";

  const leadDays =
    parseInt(document.getElementById("modal-lead-days")?.value) || 0;

  try {
    let res;
    let data;

    if (sendToSubcontract) {
      if (!vendorName) {
        showToast("Please enter vendor name for subcontracting", "error");
        return;
      }

      if (!leadDays || leadDays < 1) {
        showToast("Please enter lead days for subcontracting", "error");
        return;
      }

      res = await fetch("/api/wip/subcontract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo,
          item_name: itemName,
          process: newStage,
          vendor_name: vendorName,
          lead_days: leadDays,
          changed_by: supervisor,
          stage_remark: stageRemark,
        rm_hold_reason: sharedPendingChange.rm_hold_reason || null,
        }),
      });
    } else {
      res = await fetch("/api/wip/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo,
          item_name: itemName,
          new_stage: newStage,
          changed_by: supervisor,
          actual_qty: actualQty,
          rejected_qty: 0,
          rework_qty: 0,
          rework_remarks: "",
          stage_remark: stageRemark,
        }),
      });
    }

    data = await res.json();

    if (data.success) {
      closeSharedStageModal();
      showToast(data.message || "Stage updated", "success");

      if (activeTab === "pr") {
        loadProcessReport();
      } else {
        loadData();
      }
    } else {
      showToast(data.error || "Update failed", "error");
    }
  } catch (e) {
    showToast("Error: " + (e.message || e), "error");
  }
}
function validateSharedStageActualQty() {
  const plannedQty = parseSharedStageQty(document.getElementById("modal-planned-qty")?.value);
  const actualRaw = document.getElementById("modal-actual-qty")?.value;
  if (actualRaw === "" || actualRaw == null) return true;

  const actualQty = parseSharedStageQty(actualRaw);
  if (actualQty == null) {
    showToast("Please enter a valid Actual Qty", "error");
    document.getElementById("modal-actual-qty")?.focus();
    return false;
  }

  if (actualQty < 0) {
    showToast("Actual Qty cannot be negative", "error");
    document.getElementById("modal-actual-qty")?.focus();
    return false;
  }

  if (plannedQty != null && actualQty > plannedQty) {
    showToast("Actual Qty cannot be more than Planned Qty", "error");
    document.getElementById("modal-actual-qty")?.focus();
    return false;
  }
  return true;
}

function parseSharedStageQty(value) {
  if (value === null || value === undefined || value === "") return null;
  const qty = Number(String(value).replace(/,/g, "").trim());
  return Number.isFinite(qty) ? qty : null;
}

function getSharedStagePlannedQty(item) {
  const jobCardQty = parseSharedStageQty(item?.job_card_qty);
  if (jobCardQty !== null && jobCardQty > 0) return jobCardQty;

  const soQty = parseSharedStageQty(item?.so_qty);
  if (soQty !== null && soQty > 0) return soQty;

  return null;
}

// ── Editable Job Card Fields Modal ──────────────────────────────────────────
let editRowData = null;

function currentUserRole() {
  return String(window.JMS_USER_ROLE || "").trim().toLowerCase();
}

function currentUsername() {
  return String(window.JMS_CURRENT_USERNAME || "").trim();
}

function isGaurangSpecialUser() {
  return window.JMS_IS_GAURANG_SPECIAL === true || window.JMS_IS_GAURANG_SPECIAL === "true" || currentUsername().toLowerCase() === "gaurang";
}

function isAdminUser() {
  return currentUserRole() === "admin";
}

function canDeletePpcItems() {
  return isAdminUser() || isGaurangSpecialUser();
}

function isSupervisorUser() {
  return currentUserRole() === "supervisor";
}

function isEditableUser() {
  return isAdminUser() || isSupervisorUser() || isGaurangSpecialUser();
}

function canEditWipStage() {
  return isAdminUser() || isSupervisorUser() || isGaurangSpecialUser();
}

function canEditRowProcess(row) {
  if (isAdminUser() || isGaurangSpecialUser()) return true;
  if (!isSupervisorUser()) return false;
  return row?.can_edit_current_process === true || row?.can_edit_current_process === 1;
}

function hasPage5Field(row, fieldName) {
  if (isAdminUser() || isGaurangSpecialUser()) return true;
  const fields = Array.isArray(row?.page5_editable_fields) ? row.page5_editable_fields : [];
  return fields.includes(fieldName);
}

function isDispatchUser() {
  return (window.JMS_IS_DISPATCH === true || window.JMS_IS_DISPATCH === "true")
    && window.JMS_USER_ROLE !== "admin";
}

function canEditRowFields(row) {
  return isAdminUser() || isGaurangSpecialUser() || isDispatchUser() || (isSupervisorUser() && Array.isArray(row?.page5_editable_fields) && row.page5_editable_fields.length > 0);
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
  const canEditVendor = hasPage5Field(row, "vendor_name") || hasPage5Field(row, "subcontractor_name");
  setEditInputState("ejc-job-card-no", hasPage5Field(row, "job_card_no"));
  setEditInputState("ejc-so-no", hasPage5Field(row, "so_no"));
  setEditInputState("ejc-customer-name", hasPage5Field(row, "customer_name"));
  setEditInputState("ejc-parent-code", hasPage5Field(row, "parent_code"));
  setEditInputState("ejc-child-code", hasPage5Field(row, "child_code"));
  setEditInputState("ejc-work-order-no", hasPage5Field(row, "work_order_no"));
  setEditInputState("ejc-item-name", hasPage5Field(row, "item_name"));
  setEditInputState("ejc-material", hasPage5Field(row, "material"));
  setEditInputState("ejc-so-qty", hasPage5Field(row, "so_qty"));
  setEditInputState("ejc-actual-qty", hasPage5Field(row, "actual_qty"));
  setEditInputState("ejc-remarks", hasPage5Field(row, "remarks"));
  setEditInputState("ejc-is-subcontract", canEditVendor);
  setEditInputState("ejc-vendor-name", canEditVendor);
}

function openEditJobCardModalById(jcNo, itemName) {
  if (!isEditableUser()) return;
  const row = (allData || []).find(r => String(r.job_card_no) === String(jcNo) && r.item_name === itemName);
  if (!row) { showToast("Could not find this record in the current view", "error"); return; }
  openEditJobCardModal(row);
}

function openEditJobCardModal(row) {
  if (!isEditableUser()) return;

  // Dispatch user — show simplified modal with only SO No, Customer Name, Delivery Date
  if (isDispatchUser()) {
    document.getElementById("ejc-job-card-no").value = row.job_card_no || "";
    document.getElementById("ejc-so-no").value = row.so_no || "";
    document.getElementById("ejc-customer-name").value = row.customer_name || "";

    // Hide all fields
    ["ejc-job-card-no", "ejc-so-no", "ejc-customer-name", "ejc-parent-code",
      "ejc-child-code", "ejc-work-order-no", "ejc-item-name", "ejc-material", "ejc-so-qty", "ejc-actual-qty",
      "ejc-remarks", "ejc-is-subcontract", "ejc-vendor-name"].forEach(id => {
        const wrap = document.getElementById(id)?.closest("div");
        if (wrap) wrap.style.display = "none";
      });

    // Show SO No and Customer Name as read-only
    ["ejc-so-no", "ejc-customer-name"].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.readOnly = true;
        el.style.background = "#f8fafc";
        el.closest("div").style.display = "";
      }
    });

    // Show delivery date
    const deliveryWrap = document.getElementById("ejc-delivery-date-wrap");
    if (deliveryWrap) {
      deliveryWrap.style.display = "";
      document.getElementById("ejc-delivery-date").value = row.delivery_date || "";
    }

    editRowData = row;
    document.getElementById("edit-jobcard-modal").classList.add("open");
    return;
  }

  if (!canEditRowFields(row)) {
    showToast("You do not have rights to update this process.", "error");
    return;
  }

  editRowData = row;

  applyEditFieldPermissions();

  const setValue = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.value = value ?? "";
  };

  setValue("ejc-job-card-no", row.job_card_no || "");
  setValue("ejc-so-no", row.so_no || "");
  setValue("ejc-customer-name", row.customer_name || "");
  setValue("ejc-parent-code", row.parent_code || "");
  setValue("ejc-child-code", row.child_code || "");
  setValue("ejc-work-order-no", row.work_order_no || "");
  setValue("ejc-item-name", row.item_name || "");
  setValue("ejc-material", row.material || "");
  setValue("ejc-so-qty", row.so_qty ?? "");
  setValue("ejc-actual-qty", row.actual_qty ?? "");
  setValue("ejc-remarks", row.remarks || "");
  setValue("ejc-vendor-name", row.vendor_name || "");
  const subcontractCheckbox = document.getElementById("ejc-is-subcontract");
  if (subcontractCheckbox) {
    subcontractCheckbox.checked = isSubcontracted(row) || Boolean((row.vendor_name || "").trim());
  }
  toggleSubcontractVendor();

  // Show delivery date field only for Admin or Dispatch supervisor
  const deliveryWrap =
    document.getElementById("ejc-delivery-date-wrap") ||
    document.querySelector(".edit-delivery-wrap");

  const isDispatch =
    window.JMS_USER_ROLE === "admin" ||
    (window.JMS_USER_ROLE === "supervisor" && window.JMS_IS_DISPATCH === true);

  if (deliveryWrap) {
    deliveryWrap.style.display = isDispatch ? "" : "none";
  }

  if (isDispatch) {
    setValue("ejc-delivery-date", row.delivery_date || "");
  }

  const modal = document.getElementById("edit-jobcard-modal");
  if (modal) {
    modal.classList.add("open");
  }
}

function closeEditJobCardModal() {
  document.getElementById("edit-jobcard-modal").classList.remove("open");
  // Restore all fields for non-dispatch users
  ["ejc-job-card-no", "ejc-so-no", "ejc-customer-name",
    "ejc-parent-code", "ejc-child-code", "ejc-work-order-no", "ejc-item-name", "ejc-material",
    "ejc-so-qty", "ejc-actual-qty", "ejc-remarks", "ejc-is-subcontract", "ejc-vendor-name"].forEach(id => {
      const wrap = document.getElementById(id)?.closest("div");
      if (wrap) wrap.style.display = "";
      const el = document.getElementById(id);
      if (el) { el.readOnly = false; el.style.background = ""; }
    });
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

  const orig = editRowData;

  // Only send fields that actually changed
  const newJcNo = document.getElementById("ejc-job-card-no").value.trim();
  if (hasPage5Field(orig, "job_card_no") && newJcNo !== (orig.job_card_no || "")) {
    payload.new_job_card_no = newJcNo;
  }
  const newSoNo = document.getElementById("ejc-so-no")?.value.trim();
  if (hasPage5Field(orig, "so_no") && newSoNo !== (orig.so_no || "")) {
    payload.so_no = newSoNo;
  }
  const newCustomer = document.getElementById("ejc-customer-name").value.trim();
  if (hasPage5Field(orig, "customer_name") && newCustomer !== (orig.customer_name || "")) {
    payload.customer_name = newCustomer;
  }
  const newParent = document.getElementById("ejc-parent-code").value.trim();
  if (hasPage5Field(orig, "parent_code") && newParent !== (orig.parent_code || "")) {
    payload.parent_code = newParent;
  }
  const newChild = document.getElementById("ejc-child-code").value.trim();
  if (hasPage5Field(orig, "child_code") && newChild !== (orig.child_code || "")) {
    payload.child_code = newChild;
  }

  const newWorkOrderNo = document.getElementById("ejc-work-order-no").value.trim();
  if (
    hasPage5Field(orig, "work_order_no") &&
    newWorkOrderNo !== (orig.work_order_no || "")
  ) {
    payload.work_order_no = newWorkOrderNo;
  }

  const newItemName = document.getElementById("ejc-item-name").value.trim();
  if (hasPage5Field(orig, "item_name") && newItemName !== (orig.item_name || "")) {
    payload.item_name = newItemName;
  }
  const newMaterial = document.getElementById("ejc-material").value.trim();
  if (hasPage5Field(orig, "material") && newMaterial !== (orig.material || "")) {
    payload.material = newMaterial;
  }
  const newSoQty = document.getElementById("ejc-so-qty").value;
  if (hasPage5Field(orig, "so_qty") && newSoQty !== String(orig.so_qty ?? "")) {
    payload.so_qty = newSoQty;
  }
  const newActualQty = document.getElementById("ejc-actual-qty").value;
  if (hasPage5Field(orig, "actual_qty") && newActualQty !== String(orig.actual_qty ?? "")) {
    payload.actual_qty = newActualQty;
  }
  const newRemarks = document.getElementById("ejc-remarks").value.trim();
  if (hasPage5Field(orig, "remarks") && newRemarks !== (orig.remarks || "")) {
    payload.remarks = newRemarks;
  }

  const deliveryWrap = document.getElementById("ejc-delivery-date-wrap");
  if (deliveryWrap && deliveryWrap.style.display !== "none") {
    const dd = document.getElementById("ejc-delivery-date").value.trim();
    if (dd) {
      const originalDd = (orig.delivery_date || "").trim();
      if (dd !== originalDd) {
        window._pendingDdPayload = { ...payload, delivery_date: dd };
        document.getElementById("dd-old-date").textContent = originalDd || "—";
        document.getElementById("dd-new-date").textContent = dd;
        document.getElementById("dd-reason-input").value = "";
        document.getElementById("dd-reason-error").style.display = "none";
        document.getElementById("dd-reason-modal").style.display = "flex";
        return;
      } else {
        payload.delivery_date = dd;
      }
    }
  }

  if (hasPage5Field(orig, "vendor_name") || hasPage5Field(orig, "subcontractor_name")) {
    const subcontractCheckbox = document.getElementById("ejc-is-subcontract");
    const vendorInput = document.getElementById("ejc-vendor-name");
    const isSubcontract = subcontractCheckbox?.checked ? 1 : 0;
    const vendorName = vendorInput?.value.trim() || "";
    const origSubcontract = isSubcontracted(orig) ? 1 : 0;
    const origVendor = orig.vendor_name || "";
    if (isSubcontract !== origSubcontract || vendorName !== origVendor) {
      if (isSubcontract && !vendorName) {
        showToast("Please enter vendor name for subcontracting", "error");
        vendorInput?.focus();
        return;
      }
      payload.is_subcontract = isSubcontract;
      payload.vendor_name = isSubcontract ? vendorName : "";
    }
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
    showToast("Error: " + (e.message || e), "error");
  }
}
// ── Assembly Readiness ────────────────────────────────────────────────────────
function loadAssemblyReadiness( /* DISABLED */ ) { return; }
function _loadAssemblyReadiness_disabled() {
  const container = document.getElementById("ar-content");
  if (!container) return;
  container.innerHTML = `<div style="padding:32px;text-align:center;color:var(--muted);font-size:13px;">Loading...</div>`;

  const filterDate = document.getElementById("filter-date-input")?.value || "";
  const params = filterDate ? `?filter_date=${filterDate}` : "";

  fetch(`/api/data/assembly_readiness${params}`)
    .then(r => r.json())
    .then(data => {
      if (!data.success) {
        container.innerHTML = `<div style="padding:32px;color:red;">${escapeHtml(data.error)}</div>`;
        return;
      }

      const s = data.summary;
      const rows = data.data || [];

      let html = `
        <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
          <div class="card" style="padding:14px 20px;min-width:120px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:var(--accent)">${s.total}</div>
            <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">Total Assemblies</div>
          </div>
          <div class="card" style="padding:14px 20px;min-width:120px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#22c55e">${s.ready}</div>
            <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">Ready</div>
          </div>
          <div class="card" style="padding:14px 20px;min-width:120px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#f59e0b">${s.in_progress}</div>
            <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">In Progress</div>
          </div>
          <div class="card" style="padding:14px 20px;min-width:120px;text-align:center;">
            <div style="font-size:22px;font-weight:700;color:#ef4444">${s.not_started}</div>
            <div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">Not Started</div>
          </div>
        </div>`;

      arAllRows = rows;

      if (!rows.length) {
        html += `<div style="padding:32px;text-align:center;color:var(--muted);">No assembly data found.</div>`;
        container.innerHTML = html;
        return;
      }

      container.innerHTML = html;
      renderAssemblyReadiness(rows);
    })
    .catch(e => {
      container.innerHTML = `<div style="padding:32px;color:red;">Error: ${e.message}</div>`;
    });
}

function renderAssemblyReadiness(rows) {
  let rowsContainer = document.getElementById("ar-rows");
  if (!rowsContainer) {
    const arContent = document.getElementById("ar-content");
    if (!arContent) return;
    rowsContainer = document.createElement("div");
    rowsContainer.id = "ar-rows";
    arContent.appendChild(rowsContainer);
  }

  if (!rows.length) {
    rowsContainer.innerHTML = `<div style="padding:32px;text-align:center;color:var(--muted);">No results found.</div>`;
    return;
  }

  function renderNode(node, depth) {
    const pct = node.process_pct || 0;
    const isReady = node.is_completed;
    const hasChildren = node.children && node.children.length > 0;
    const statusColor = isReady ? "#22c55e" : pct > 0 ? "#f59e0b" : "#ef4444";
    const wipBg = node.wip_status && node.wip_status.toLowerCase() === "store" ? "#dcfce7" : "#fef9c3";
    const wipColor = node.wip_status && node.wip_status.toLowerCase() === "store" ? "#15803d" : "#854d0e";
    const indent = depth * 24;
    const nodeId = "ar-node-" + node.child_code + "-" + depth + "-" + Math.random().toString(36).slice(2,7);

    let childrenHtml = "";
    if (hasChildren) {
      childrenHtml = node.children.map(function(child) { return renderNode(child, depth + 1); }).join("");
    }

    let html = "<div style=\"border-top:1px solid var(--border);\">";
    html += "<div style=\"display:flex;align-items:center;gap:10px;padding:9px 16px;padding-left:" + (16 + indent) + "px;";
    html += "background:" + (depth === 0 ? "var(--surface)" : depth === 1 ? "#f8fafc" : "#f1f5f9") + ";";
    if (hasChildren) html += "cursor:pointer;\" onclick=\"toggleArNode('" + nodeId + "')\">";
    else html += "\">";

    if (hasChildren) {
      html += "<span id=\"" + nodeId + "-arrow\" style=\"font-size:10px;color:var(--muted);display:inline-block;transition:transform 0.2s;\">&#9658;</span>";
    } else {
      html += "<span style=\"width:12px;display:inline-block;\"></span>";
    }

    html += "<div style=\"flex:1;min-width:0;\">";
    html += "<div style=\"font-size:12px;font-weight:" + (depth === 0 ? "700" : "500") + ";color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;\">";
    html += escapeHtml(node.item_name || node.child_code);
    html += "</div>";
    html += "<div style=\"font-size:11px;color:var(--muted);margin-top:1px;\">";
    html += escapeHtml(node.child_code);
    if (node.job_card_no) html += " &middot; JC: " + escapeHtml(node.job_card_no);
    if (node.delivery_date) html += " &middot; " + node.delivery_date;
    html += "</div></div>";

    if (node.wip_status) {
      html += "<span style=\"padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;";
      html += "background:" + wipBg + ";color:" + wipColor + ";white-space:nowrap;\">";
      html += escapeHtml(node.wip_status) + "</span>";
    }

    html += "<div style=\"display:flex;align-items:center;gap:6px;min-width:90px;\">";
    html += "<div style=\"height:5px;width:60px;background:var(--border);border-radius:3px;overflow:hidden;\">";
    html += "<div style=\"height:100%;width:" + pct + "%;background:" + statusColor + ";border-radius:3px;\"></div></div>";
    html += "<span style=\"font-size:11px;color:var(--muted);\">" + pct + "%</span></div>";
    html += "<span style=\"font-size:14px;\">" + (isReady ? "&#10003;" : "&#8987;") + "</span>";
    html += "</div>";

    if (hasChildren) {
      html += "<div id=\"" + nodeId + "\" style=\"display:none;\">" + childrenHtml + "</div>";
    }
    html += "</div>";
    return html;
  }

  let html = "<div style=\"display:flex;flex-direction:column;gap:10px;\">";

  rows.forEach(function(row, idx) {
    const pct = row.overall_pct || 0;
    const isReady = row.is_ready;
    const statusColor = isReady ? "#22c55e" : pct > 0 ? "#f59e0b" : "#ef4444";
    const statusLabel = isReady ? "Ready for Assembly" : pct > 0 ? "In Progress" : "Not Started";
    const statusIcon = isReady ? "&#10003;" : pct > 0 ? "&#8987;" : "&#128997;";
    const assemblyId = "ar-assembly-" + idx;

    html += "<div class=\"card\" style=\"padding:0;overflow:hidden;\">";
    html += "<div style=\"padding:12px 16px;display:flex;align-items:center;gap:12px;cursor:pointer;";
    html += "border-bottom:1px solid var(--border);background:#eef2f7;border-left:4px solid var(--accent);\"";
    html += " onclick=\"toggleArAssembly('" + assemblyId + "')\">"; 
    html += "<div style=\"flex:1;\">";
    html += "<div style=\"font-size:13px;font-weight:700;color:var(--text);\">" + escapeHtml(row.assembly_name || row.parent_code) + "</div>";
    html += "<div style=\"font-size:11px;color:var(--muted);margin-top:2px;\">";
    html += escapeHtml(row.parent_code);
    if (row.so_no) html += " &middot; SO: " + escapeHtml(row.so_no);
    if (row.customer_name) html += " &middot; " + escapeHtml(row.customer_name);
    html += "</div></div>";
    html += "<div style=\"text-align:right;min-width:140px;\">";
    html += "<div style=\"font-size:11px;font-weight:700;color:" + (isReady ? "#4ade80" : pct > 0 ? "#fbbf24" : "#f87171") + ";\">";
    html += statusIcon + " " + statusLabel + "</div>";
    html += "<div style=\"font-size:11px;color:var(--muted);margin-top:2px;\">" + row.completed_parts + "/" + row.total_parts + " parts done</div>";
    html += "</div>";
    html += "<div style=\"min-width:80px;\">";
    html += "<div style=\"height:6px;background:var(--border);border-radius:3px;overflow:hidden;\">";
    html += "<div style=\"height:100%;width:" + pct + "%;background:" + (isReady ? "#4ade80" : pct > 0 ? "#fbbf24" : "#f87171") + ";border-radius:3px;\"></div></div>";
    html += "<div style=\"font-size:10px;color:var(--muted);margin-top:3px;text-align:center;\">" + pct + "%</div>";
    html += "</div>";
    html += "<div id=\"" + assemblyId + "-arrow\" style=\"font-size:12px;color:var(--muted);\" >&#9658;</div>";
    html += "</div>";
    html += "<div id=\"" + assemblyId + "\" style=\"display:none;\">";
    html += (row.children || []).map(function(child) { return renderNode(child, 0); }).join("");
    html += "</div></div>";
  });

  html += "</div>";
  rowsContainer.innerHTML = html;
}

function toggleArAssembly(id) {
  const el = document.getElementById(id);
  const arrow = document.getElementById(id + "-arrow");
  if (!el) return;
  const isOpen = el.style.display !== "none";
  el.style.display = isOpen ? "none" : "block";
  if (arrow) arrow.style.transform = isOpen ? "" : "rotate(90deg)";
}

function toggleArNode(id) {
  const el = document.getElementById(id);
  const arrow = document.getElementById(id + "-arrow");
  if (!el) return;
  const isOpen = el.style.display !== "none";
  el.style.display = isOpen ? "none" : "block";
  if (arrow) arrow.style.transform = isOpen ? "" : "rotate(90deg)";
}


function filterAssemblyReadiness( /* DISABLED */ ) { return; }
function _filterAssemblyReadiness_disabled() {
  const search = (document.getElementById("ar-search")?.value || "").toLowerCase().trim();
  if (!search) {
    renderAssemblyReadiness(arAllRows);
    return;
  }
  const filtered = arAllRows.filter(row => {
    return (
      (row.assembly_name || "").toLowerCase().includes(search) ||
      (row.parent_code || "").toLowerCase().includes(search) ||
      (row.so_no || "").toLowerCase().includes(search) ||
      (row.customer_name || "").toLowerCase().includes(search) ||
      (row.children || []).some(c =>
        (c.item_name || "").toLowerCase().includes(search) ||
        (c.child_code || "").toLowerCase().includes(search) ||
        (c.wip_status || "").toLowerCase().includes(search)
      )
    );
  });
  renderAssemblyReadiness(filtered);
}

function toggleArRow(idx) {
  const el = document.getElementById(`ar-row-${idx}`);
  if (!el) return;
  const isOpen = el.style.display !== "none";
  el.style.display = isOpen ? "none" : "block";
}

// ── WIP Summary ───────────────────────────────────────────────────────────────
async function loadWipSummary() {
  const fromDate = document.getElementById("ws-from-date").value;
  const toDate = document.getElementById("ws-to-date").value;
  const loading = document.getElementById("ws-loading");
  const table = document.getElementById("ws-table");
  const thead = document.getElementById("ws-thead");
  const tbody = document.getElementById("ws-tbody");

  loading.textContent = "Loading...";
  loading.style.display = "block";
  table.style.display = "none";

  const params = new URLSearchParams();
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);

  try {
    const res = await fetch(`/api/wip_summary?${params.toString()}`);
    const data = await res.json();

    if (!data.success || !data.rows.length) {
      loading.textContent = "No data found for the selected date range.";
      return;
    }

    const processes = data.processes;

    // Build header
    thead.innerHTML = `<tr>
      <th style="padding:10px 14px; text-align:left; font-size:12px; letter-spacing:0.5px; white-space:nowrap; border-right:1px solid rgba(255,255,255,0.15);">Date</th>
      ${processes.map(p => `<th style="padding:10px 14px; text-align:center; font-size:12px; letter-spacing:0.5px; white-space:nowrap; border-right:1px solid rgba(255,255,255,0.15);">${escapeHtml(p)}</th>`).join("")}
    </tr>`;

    // Build body
    tbody.innerHTML = data.rows.map((row, idx) => `
      <tr style="background:${idx % 2 === 0 ? '#ffffff' : '#f1f5f9'};">
        <td style="padding:9px 14px; font-weight:600; white-space:nowrap; border-right:1px solid var(--border); color:var(--text);">${row.date}</td>
        ${processes.map(p => {
      const val = row[p] || 0;
      return `<td style="padding:9px 14px; text-align:center; border-right:1px solid var(--border); color:${val > 0 ? 'var(--accent)' : 'var(--muted)'}; font-weight:${val > 0 ? '700' : '400'}; ${val > 0 ? 'cursor:pointer;' : ''}" ${val > 0 ? `onclick="openWipDetailModal('${row.date}', '${p.replace(/'/g, "\\'")}')"` : ''}>${val > 0 ? val : '—'}</td>`;
    }).join("")}
      </tr>
    `).join("");

    loading.style.display = "none";
    table.style.display = "table";

  } catch (e) {
    loading.textContent = "Failed to load WIP Summary. Please try again.";
  }
}

// ── WIP Summary Detail Modal ──────────────────────────────────────────────────
async function openWipDetailModal(date, process) {
  // Create modal if not exists
  let overlay = document.getElementById("wip-detail-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "wip-detail-overlay";
    overlay.style.cssText = `
      position:fixed; inset:0; background:rgba(0,0,0,0.45);
      z-index:9999; display:flex; align-items:center; justify-content:center;
    `;
    overlay.onclick = function (e) { if (e.target === overlay) closeWipDetailModal(); };
    document.body.appendChild(overlay);
  }

  overlay.innerHTML = `
    <div style="background:var(--card-bg); border-radius:10px; width:90vw; max-width:860px;
                max-height:85vh; display:flex; flex-direction:column; box-shadow:0 8px 40px rgba(0,0,0,0.18);">
      <div style="background:white; color:#fff; padding:16px 20px; border-radius:10px 10px 0 0;
                  display:flex; align-items:center; justify-content:space-between;">
        <div>
          <div style="font-size:16px; font-weight:700;">${escapeHtml(process)} — Completed on ${date}</div>
          <div style="font-size:12px; opacity:0.75; margin-top:3px;">Job cards that advanced out of this stage</div>
        </div>
        <button onclick="closeWipDetailModal()"
          style="background:rgba(255,255,255,0.15); border:none; color:#fff; border-radius:6px;
                 padding:6px 12px; cursor:pointer; font-size:18px; line-height:1;">✕</button>
      </div>

      <div id="wip-detail-body" style="overflow-y:auto; padding:20px;">
        <div style="text-align:center; padding:32px; color:var(--muted); font-size:13px;">Loading...</div>
      </div>
    </div>
  `;
  overlay.style.display = "flex";

  try {
    const res = await fetch(`/api/wip_summary/detail?date=${encodeURIComponent(date)}&process=${encodeURIComponent(process)}`);
    const data = await res.json();

    const body = document.getElementById("wip-detail-body");

    if (!data.success || !data.rows.length) {
      body.innerHTML = `<div style="text-align:center; padding:32px; color:var(--muted); font-size:13px;">No records found.</div>`;
      return;
    }

    // Group by changed_by for summary
    const byUser = {};
    data.rows.forEach(r => {
      const user = r.changed_by || "Unknown";
      byUser[user] = (byUser[user] || 0) + 1;
    });

    const summaryHtml = Object.entries(byUser).map(([user, count]) => `
      <span style="display:inline-flex; align-items:center; gap:6px; background:#eff6ff;
                   border:1px solid #bfdbfe; border-radius:20px; padding:4px 12px;
                   font-size:12px; font-weight:600; color:#1d4ed8; margin:3px;">
        <i class="fa fa-user"></i> ${escapeHtml(user)} &nbsp;·&nbsp; ${count} job card${count > 1 ? 's' : ''}
      </span>
    `).join("");

    body.innerHTML = `
      <!-- Summary chips -->
      <div style="margin-bottom:16px; padding:12px 14px; background:#f8fafc;
                  border:1px solid var(--border); border-radius:8px;">
        <div style="font-size:11px; font-weight:700; color:var(--muted); text-transform:uppercase;
                    letter-spacing:0.5px; margin-bottom:8px;">Completed By</div>
        <div>${summaryHtml}</div>
      </div>

      <!-- Count -->
      <div style="font-size:12px; font-weight:600; color:var(--muted); margin-bottom:10px;">
        Showing ${data.count} record${data.count > 1 ? 's' : ''}
      </div>

      <!-- Table -->
      <div style="border:1px solid var(--border); border-radius:6px; overflow:hidden;">
        <table style="width:100%; border-collapse:collapse; font-size:13px;">
          <thead>
            <tr style="background:var(--header-bg); color:#fff;">
              <th style="padding:10px 14px; text-align:left; font-size:11px; letter-spacing:0.5px;">#</th>
              <th style="padding:10px 14px; text-align:left; font-size:11px; letter-spacing:0.5px;">JC No</th>
              <th style="padding:10px 14px; text-align:left; font-size:11px; letter-spacing:0.5px;">Item Name</th>
              <th style="padding:10px 14px; text-align:left; font-size:11px; letter-spacing:0.5px;">Advanced To</th>
              <th style="padding:10px 14px; text-align:left; font-size:11px; letter-spacing:0.5px;">Completed By</th>
              <th style="padding:10px 14px; text-align:left; font-size:11px; letter-spacing:0.5px;">Time</th>
            </tr>
          </thead>
          <tbody>
            ${data.rows.map((r, i) => `
              <tr style="background:${i % 2 === 0 ? '#ffffff' : '#f9f1f1'}; border-top:1px solid var(--border);">
                <td style="padding:9px 14px; color:var(--muted); font-size:12px;">${i + 1}</td>
                <td style="padding:9px 14px; font-weight:700; color:var(--accent);">${escapeHtml(r.job_card_no)}</td>
                <td style="padding:9px 14px; color:var(--text);">${escapeHtml(r.item_name || '—')}</td>
                <td style="padding:9px 14px;">
<span style="background:${r.advanced_to && r.advanced_to.includes('Rolled Back') ? '#fef2f2' : '#dcfce7'}; 
                               color:${r.advanced_to && r.advanced_to.includes('Rolled Back') ? '#b91c1c' : '#15803d'}; 
                               border-radius:12px; padding:3px 10px; font-size:11px; font-weight:600;">
                    ${r.advanced_to && r.advanced_to.includes('Rolled Back') ? '↩' : '→'} ${escapeHtml(r.advanced_to || '—')}
                  </span>
                </td>
                <td style="padding:9px 14px; font-weight:600; color:var(--text);">
                  <i class="fa fa-user" style="color:var(--muted); margin-right:5px;"></i>${escapeHtml(r.changed_by || '—')}
                </td>
                <td style="padding:9px 14px; color:var(--muted); font-size:12px;">${escapeHtml(r.changed_at_ist || '—')}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  } catch (e) {
    document.getElementById("wip-detail-body").innerHTML =
      `<div style="text-align:center; padding:32px; color:#ef4444; font-size:13px;">Failed to load details.</div>`;
  }
}

function closeWipDetailModal() {
  const overlay = document.getElementById("wip-detail-overlay");
  if (overlay) overlay.style.display = "none";
}

// ── Delivery Date Change Reason Modal ────────────────────────────────────────────────────
function closeDdReasonModal() {
  document.getElementById("dd-reason-modal").style.display = "none";
  window._pendingDdPayload = null;
}

async function confirmDdReasonAndSave() {
  const reason = (document.getElementById("dd-reason-input").value || "").trim();
  if (!reason) {
    document.getElementById("dd-reason-error").style.display = "block";
    return;
  }
  document.getElementById("dd-reason-error").style.display = "none";
  document.getElementById("dd-reason-modal").style.display = "none";

  const payload = { ...window._pendingDdPayload, dd_change_reason: reason };
  window._pendingDdPayload = null;

  try {
    const res = await fetch("/api/job_card/update_fields", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || "Delivery date updated.", "success");
      closeEditJobCardModal();
      loadData();
    } else {
      showToast(data.error || "Update failed", "error");
    }
  } catch (e) {
    showToast("Error: " + (e.message || e), "error");
  }
}
function getSubcontractVendorControls(source) {
  const stageModalOpen = document.getElementById("stage-modal")?.classList.contains("open");
  const editModalOpen = document.getElementById("edit-jobcard-modal")?.classList.contains("open");
  const sourceId = source?.id || "";
  const useStageControls = sourceId === "subcontract-checkbox" || (!sourceId && stageModalOpen && !editModalOpen);

  if (useStageControls) {
    return {
      checkbox: document.getElementById("subcontract-checkbox"),
      vendorWrap: document.getElementById("vendor-row"),
      vendorInput: document.getElementById("modal-vendor-name"),
    };
  }

  return {
    checkbox: document.getElementById("ejc-is-subcontract"),
    vendorWrap: document.getElementById("ejc-vendor-wrap"),
    vendorInput: document.getElementById("ejc-vendor-name"),
  };
}

function toggleSubcontractVendor(source) {
  const sourceElement = source?.target || (source?.nodeType === 1 ? source : null);
  const sourceId = sourceElement?.id || "";

  const controls = getSubcontractVendorControls(sourceElement);

  const isChecked =
    typeof source === "boolean"
      ? source
      : Boolean(controls.checkbox?.checked);

  if (controls.checkbox && controls.checkbox.checked !== isChecked) {
    controls.checkbox.checked = isChecked;
  }

  if (controls.vendorWrap) {
    controls.vendorWrap.style.display = isChecked ? "" : "none";
  }

  if (controls.vendorInput) {
    controls.vendorInput.disabled = !isChecked || Boolean(controls.checkbox?.disabled);

    if (!isChecked) {
      controls.vendorInput.value = "";
    } else if (sourceElement && !controls.vendorInput.disabled) {
      controls.vendorInput.focus();
    }
  }

  const isStageModal =
    controls.checkbox?.id === "subcontract-checkbox" ||
    sourceId === "subcontract-checkbox" ||
    document.getElementById("stage-modal")?.classList.contains("open");

  if (!isStageModal) {
    return;
  }

  const leadInput = document.getElementById("modal-lead-days");
  const hint = document.getElementById("lead-days-hint");
  const dateLabel = document.getElementById("modal-expected-date-label");

  if (!leadInput) {
    return;
  }

  if (!isChecked) {
    leadInput.value = "";
    leadInput.removeAttribute("readonly");

    if (hint) hint.textContent = "";
    if (dateLabel) dateLabel.textContent = "";

    if (typeof updateExpectedDate === "function") {
      updateExpectedDate();
    }

    return;
  }

  const normalize = (value) =>
    String(value || "").trim().toLowerCase();

  const nextProcess =
    sharedPendingChange?.newStage ||
    document.getElementById("modal-next-process")?.textContent ||
    "";

  let item = null;

  if (sharedPendingChange?.itemName) {
    item = (sharedModalData?.items || []).find(it =>
      normalize(it.item_name) === normalize(sharedPendingChange.itemName)
    );
  }

  if (!item) {
    item = (sharedModalData?.items || [])[0] || {};
  }

  const leadRow = (item.process_timeline || []).find(t =>
    normalize(t.process_name) === normalize(nextProcess)
  );

  const planLeadDays = parseInt(leadRow?.lead_days || 0, 10);

  if (planLeadDays > 0) {
    leadInput.value = String(planLeadDays);
    leadInput.setAttribute("readonly", "readonly");

    if (hint) hint.textContent = "";
  } else {
    leadInput.value = "";
    leadInput.removeAttribute("readonly");

    if (hint) {
      hint.textContent = "Not set in process plan — enter manually";
    }
  }

  if (typeof updateExpectedDate === "function") {
    updateExpectedDate();
  }
}

function bindSubcontractVendorToggles() {
  ["ejc-is-subcontract", "subcontract-checkbox"].forEach(id => {
    const checkbox = document.getElementById(id);
    if (checkbox && !checkbox.dataset.subcontractToggleBound) {
      checkbox.addEventListener("change", toggleSubcontractVendor);
      checkbox.dataset.subcontractToggleBound = "1";
    }
  });
}

bindSubcontractVendorToggles();
window.toggleSubcontractVendor = toggleSubcontractVendor;
