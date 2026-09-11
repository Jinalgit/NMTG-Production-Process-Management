// ── State ─────────────────────────────────────────────────────────────────────
let allItems = [];
let defaultDays = {};
let selectedItemId = null;
let customerSearchTimer = null;
let customerSearchRequestId = 0;
let bomProcessList = [];
const PROCESS_STAGE_COUNT = 25;

// Multi-child BOM state
let childRows = []; // [{ child_code, item_code, item_description, material, size, checked }]
let isBomMode = false; // true when parent code found children

// ── Load default days ─────────────────────────────────────────────────────────
async function loadDefaultDays() {
  try {
    const res = await fetch("/api/process_default_days");
    const data = await res.json();
    if (data.success) {
      data.defaults.forEach(d => {
        defaultDays[(d.process_name || "").trim().toLowerCase()] = d.default_days;
      });
    }
  } catch (e) { }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function getSoNo() {
  const val = document.getElementById("so_no").value.trim();
  return val ? "S" + val : "";
}

function getWorkOrderNo() {
  const val = document.getElementById("work_order_no").value.trim();
  return val ? "WO" + val : "";
}

function getTodayDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function getTomorrowDate() {
  const d = new Date(); d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isValidFutureDeliveryDate(dateStr) {
  return Boolean(dateStr) && dateStr >= getTomorrowDate();
}

function setDefaultDates() {
  const today = getTodayDate();
  ["so_date", "job_card_date", "work_order_date"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = today;
  });
  const dd = document.getElementById("delivery_date");
  if (dd) dd.min = getTomorrowDate();
}

function setParentStatus(msg, color) {
  const el = document.getElementById("parent-code-status");
  if (!el) return;
  el.textContent = msg;
  el.style.color = color || "var(--muted)";
  el.style.display = msg ? "block" : "none";
}

// ── Customer autocomplete ─────────────────────────────────────────────────────
function hideCustomerSuggestions() {
  document.getElementById("customer-ac-list")?.classList.remove("open");
}

function selectCustomerSuggestion(value) {
  const input = document.getElementById("customer_name");
  if (input) input.value = value;
  hideCustomerSuggestions();
}

async function searchCustomers(query, requestId) {
  try {
    const res = await fetch(`/api/customer-search?q=${encodeURIComponent(query)}`);
    const customers = await res.json();
    const list = document.getElementById("customer-ac-list");
    if (!list || requestId !== customerSearchRequestId || !Array.isArray(customers)) return;
    list.replaceChildren();
    customers.forEach(customer => {
      if (!customer.value) return;
      const suggestion = document.createElement("button");
      suggestion.type = "button";
      suggestion.className = "customer-ac-item";
      suggestion.textContent = customer.value;
      suggestion.setAttribute("role", "option");
      suggestion.addEventListener("mousedown", e => {
        e.preventDefault();
        selectCustomerSuggestion(customer.value);
      });
      list.appendChild(suggestion);
    });
    list.classList.toggle("open", list.childElementCount > 0);
  } catch (e) {
    if (requestId === customerSearchRequestId) hideCustomerSuggestions();
  }
}

// ── Item autocomplete ─────────────────────────────────────────────────────────
function getItemDisplayName(item) {
  const modelName = String(item.model_name || "").trim();
  const size = String(item.size || "").trim();
  const partName = String(item.part_name || "").trim();
  const normalize = s => s.toLowerCase().replace(/\s+/g, "");
  const sizeAlreadyInModel = normalize(size) && normalize(modelName).includes(normalize(size));
  const parts = [modelName];
  if (size && !sizeAlreadyInModel) parts.push(size);
  if (partName) parts.push(partName);
  return parts.filter(Boolean).join(" - ");
}

async function onItemNameInput() {
  const val = document.getElementById("item_name").value.trim();
  const list = document.getElementById("ac-list");
  selectedItemId = null;
  if (!val) { list.classList.remove("open"); clearAutofill(); return; }
  clearAutofill();
  try {
    const res = await fetch(`/api/items?q=${encodeURIComponent(val)}`);
    const data = await res.json();
    if (!data.success || !data.items.length) { list.classList.remove("open"); return; }
    allItems = data.items;
    list.innerHTML = data.items.map(i =>
      `<div class="ac-item" onmousedown="event.preventDefault();selectSuggestion(${i.id})">${escapeHtml(getItemDisplayName(i))}</div>`
    ).join("");
    list.classList.add("open");
  } catch (e) { }
}

function selectSuggestion(itemId) {
  const item = allItems.find(i => i.id === itemId);
  if (!item) return;
  selectedItemId = item.id;
  document.getElementById("item_name").value = getItemDisplayName(item);
  document.getElementById("ac-list").classList.remove("open");
  fillItemDetails(item);
}

function onItemNameKeydown(e) {
  const list = document.getElementById("ac-list");
  const items = list.querySelectorAll(".ac-item");
  const active = list.querySelector(".ac-item.active");
  let idx = -1;
  if (!items.length) return;
  if (e.key === "ArrowDown") {
    e.preventDefault();
    if (active) { active.classList.remove("active"); idx = Array.from(items).indexOf(active); idx = (idx + 1) % items.length; } else idx = 0;
    items[idx].classList.add("active"); items[idx].scrollIntoView({ block: "nearest" });
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    if (active) { active.classList.remove("active"); idx = Array.from(items).indexOf(active); idx = (idx - 1 + items.length) % items.length; } else idx = items.length - 1;
    items[idx].classList.add("active"); items[idx].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault(); if (active) active.dispatchEvent(new Event("mousedown"));
  } else if (e.key === "Escape") {
    list.classList.remove("open");
  }
}

// ── Process / autofill ────────────────────────────────────────────────────────
function fillItemDetails(item) {
  document.getElementById("item-autofill").style.display = "block";
  document.getElementById("af_material").value = item.material || "";
  document.getElementById("af_size").value = item.size || "";
  document.getElementById("af_part_name").value = item.part_name || "";
  const grid = document.getElementById("process-days-grid");
  grid.innerHTML = "";
  const processes = [];
  for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) { const p = item["p" + i]; if (p) processes.push(p); }
  processes.forEach((proc, idx) => {
    const normProc = (proc || "").trim().toLowerCase();
    const defDays = Object.prototype.hasOwnProperty.call(defaultDays, normProc) ? defaultDays[normProc] : 0;
    const div = document.createElement("div");
    div.className = "process-day-item";
    div.innerHTML = `<label>P${idx + 1}: ${proc}</label><input type="number" id="pdays_${idx}" placeholder="Days" min="0" value="${defDays}" oninput="updateTotalDays()" data-process="${proc}" />`;
    grid.appendChild(div);
  });
  updateTotalDays();
}

function fillItemDetailsFromBom(data) {
  document.getElementById("item-autofill").style.display = "block";
  document.getElementById("af_material").value = data.material || "";
  document.getElementById("af_size").value = data.size || "";
  document.getElementById("af_part_name").value = data.part_name || "";
  const grid = document.getElementById("process-days-grid");
  grid.innerHTML = "";
  bomProcessList.forEach((proc, idx) => {
    const normProc = (proc.process_name || "").trim().toLowerCase();
    const defDays = Object.prototype.hasOwnProperty.call(defaultDays, normProc) ? defaultDays[normProc] : 0;
    const div = document.createElement("div");
    div.className = "process-day-item";
    div.dataset.idx = idx;
    div.innerHTML = `
      <label>P${idx + 1}: <span class="proc-label">${proc.process_name}</span>
        <button type="button" onclick="removeBomProcess(${idx})" title="Remove" style="margin-left:6px;background:none;border:none;color:#ef4444;cursor:pointer;font-size:13px;line-height:1;">✕</button>
      </label>
      <input type="number" id="pdays_${idx}" placeholder="Days" min="0" value="${defDays}" oninput="updateTotalDays()" data-process="${proc.process_name}" />`;
    grid.appendChild(div);
  });
  renderAddProcessRow();
  updateTotalDays();
}

function removeBomProcess(idx) {
  bomProcessList.splice(idx, 1);
  fillItemDetailsFromBom({
    material: document.getElementById("af_material").value,
    size: document.getElementById("af_size").value,
    part_name: document.getElementById("af_part_name").value,
  });
}

function renderAddProcessRow() {
  const grid = document.getElementById("process-days-grid");
  const addRow = document.createElement("div");
  addRow.className = "process-day-item"; addRow.id = "add-process-row"; addRow.style.gridColumn = "1/-1";
  addRow.innerHTML = `<div style="display:flex;gap:8px;align-items:center;margin-top:6px;">
    <input type="text" id="new-process-input" placeholder="Add process name..." style="flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-size:13px;font-family:'IBM Plex Sans',sans-serif;" />
    <button type="button" onclick="addBomProcess()" style="padding:6px 14px;background:var(--accent);color:#fff;border:none;border-radius:4px;font-size:13px;cursor:pointer;">+ Add</button>
  </div>`;
  grid.appendChild(addRow);
}

function addBomProcess() {
  const input = document.getElementById("new-process-input");
  const name = (input?.value || "").trim();
  if (!name) { showToast("Enter a process name to add.", "error"); return; }
  bomProcessList.push({ step_no: bomProcessList.length + 1, process_name: name });
  fillItemDetailsFromBom({
    material: document.getElementById("af_material").value,
    size: document.getElementById("af_size").value,
    part_name: document.getElementById("af_part_name").value,
  });
}

function updateTotalDays() {
  let total = 0;
  document.querySelectorAll("[id^='pdays_']").forEach(inp => {
    const v = parseInt(inp.value);
    if (!isNaN(v) && v > 0) total += v;
  });
  document.getElementById("total-days-display").textContent = total;
}

function clearAutofill() {
  selectedItemId = null; bomProcessList = [];
  const el = document.getElementById("item-autofill");
  if (el) el.style.display = "none";
  ["af_material", "af_size", "af_part_name"].forEach(id => { const e = document.getElementById(id); if (e) e.value = ""; });
  const grid = document.getElementById("process-days-grid");
  if (grid) grid.innerHTML = "";
  const tdd = document.getElementById("total-days-display");
  if (tdd) tdd.textContent = "0";
}

// ── BOM Multi-Child Flow ──────────────────────────────────────────────────────
async function lookupParentCode(parentCode) {
  if (!parentCode) {
    resetToManualMode();
    return;
  }
  setParentStatus("Looking up...", "var(--muted)");

  try {
    const res = await fetch(`/api/bom/children/${encodeURIComponent(parentCode)}`);
    const data = await res.json();

    if (!res.ok || data.error || !data.children || !data.children.length) {
      resetToManualMode();
      setParentStatus("No BOM children found — enter child code and item details manually.", "#f59e0b");
      return;
    }

    // Parse children — support both object and string formats
    const children = data.children.map(child => {
      if (typeof child === "object" && child !== null) {
        return {
          child_code: child.item_code || child.child_code || "",
          item_description: child.item_description || "",
          material: child.material || "",
          size: child.size || "",
          checked: false,
        };
      }
      return { child_code: child, item_description: "", material: "", size: "", checked: false };
    });

    childRows = children;
    isBomMode = true;
    renderChildTable();
    showBomMode();
    setParentStatus(`${children.length} child code(s) found.`, "#16a34a");
    updateSaveButton();

  } catch (e) {
    resetToManualMode();
    setParentStatus("Lookup failed — enter child code manually.", "#ef4444");
  }
}

function showBomMode() {
  document.getElementById("child-table-section").style.display = "block";
  document.getElementById("manual-child-section").style.display = "none";
  document.getElementById("single-jc-section").style.display = "none";
  document.getElementById("main-save-label").textContent = "Preview & Create";
}

function resetToManualMode() {
  childRows = [];
  isBomMode = false;
  document.getElementById("child-table-section").style.display = "none";
  document.getElementById("manual-child-section").style.display = "block";
  document.getElementById("single-jc-section").style.display = "block";
  document.getElementById("child_code_manual").value = "";
  document.getElementById("main-save-label").textContent = "Save Job Card";
  updateSaveButton();
}

function updateSaveButton() {
  const btn = document.getElementById("main-save-btn");
  const label = document.getElementById("main-save-label");
  if (isBomMode) {
    const checked = childRows.filter(r => r.checked).length;
    label.textContent = checked > 0 ? `Preview & Create (${checked})` : "Preview & Create";
  } else {
    label.textContent = "Save Job Card";
  }
}

function renderChildTable() {
  const tbody = document.getElementById("child-table-body");
  const badge = document.getElementById("child-count-badge");
  const searchTerm = (document.getElementById("child-search")?.value || "").toLowerCase();

  const visible = childRows.filter(r =>
    !searchTerm ||
    r.child_code.toLowerCase().includes(searchTerm) ||
    r.item_description.toLowerCase().includes(searchTerm)
  );

  badge.textContent = `${childRows.length} child codes · ${childRows.filter(r => r.checked).length} selected`;

  tbody.innerHTML = visible.map((row, visIdx) => {
    const realIdx = childRows.indexOf(row);
    const cls = row.checked ? "row-checked" : "row-unchecked";
    return `<tr class="${cls}" id="crow-${realIdx}">
      <td style="text-align:center;">
        <input type="checkbox" ${row.checked ? "checked" : ""} onchange="toggleChildRow(${realIdx}, this.checked)" />
      </td>
      <td class="child-code-cell">${escapeHtml(row.child_code)}</td>
      <td class="child-desc-cell" title="${escapeHtml(row.item_description)}">${escapeHtml(row.item_description || "—")}</td>
      <td>
        <input type="number" class="child-input qty-input" id="cqty-${realIdx}"
          placeholder="Qty" min="1" value=""
          ${row.checked ? "" : "disabled"}
          oninput="updateChildRow(${realIdx})" />
      </td>
      <td>
        <input type="text" class="child-input jc-input" id="cjc-${realIdx}"
          placeholder="e.g. 112832"
          ${row.checked ? "" : "disabled"}
          oninput="updateChildRow(${realIdx})" />
      </td>
    </tr>`;
  }).join("");

  updateSaveButton();
}

function toggleChildRow(idx, checked) {
  childRows[idx].checked = checked;
  const tr = document.getElementById(`crow-${idx}`);
  if (tr) tr.className = checked ? "row-checked" : "row-unchecked";
  const qtyEl = document.getElementById(`cqty-${idx}`);
  const jcEl = document.getElementById(`cjc-${idx}`);
  if (qtyEl) qtyEl.disabled = !checked;
  if (jcEl) jcEl.disabled = !checked;
  updateSaveButton();
}

function updateChildRow(idx) {
  // Values are read directly from inputs at submit time
  updateSaveButton();
}

function toggleAllChildren(checked) {
  childRows.forEach((_, i) => { childRows[i].checked = checked; });
  renderChildTable();
}

function selectAllChildren() {
  childRows.forEach((_, i) => { childRows[i].checked = true; });
  renderChildTable();
}

function deselectAllChildren() {
  childRows.forEach((_, i) => { childRows[i].checked = false; });
  renderChildTable();
}

function filterChildTable() {
  renderChildTable();
}

// ── Main Save Handler ─────────────────────────────────────────────────────────
function handleMainSave() {
  if (isBomMode) {
    showPreviewModal();
  } else {
    submitJobCard();
  }
}

// ── Preview Modal ─────────────────────────────────────────────────────────────
function showPreviewModal() {
  const delivery_date = document.getElementById("delivery_date").value;
  const customer_name = document.getElementById("customer_name").value.trim();

  if (!delivery_date) { showToast("Final Delivery Date is required!", "error"); return; }
  if (!isValidFutureDeliveryDate(delivery_date)) { showToast("Final Delivery Date must be after today.", "error"); return; }
  if (!customer_name) { showToast("Customer Name is required!", "error"); return; }

  // Collect checked rows
  const selectedRows = [];
  const errors = [];

  childRows.forEach((row, idx) => {
    if (!row.checked) return;
    const jcNo = (document.getElementById(`cjc-${idx}`)?.value || "").trim();
    const qty = parseInt(document.getElementById(`cqty-${idx}`)?.value || "0");

    if (!jcNo) { errors.push(`${row.child_code}: Job Card No is required`); return; }
    if (!qty || qty < 1) { errors.push(`${row.child_code}: Quantity must be > 0`); return; }
    if (!/^[\d\/]+$/.test(jcNo)) { errors.push(`${row.child_code}: JC No must contain only numbers and /`); return; }

    selectedRows.push({
      job_card_no: jcNo,
      child_code: row.child_code,
      item_name: row.item_description || row.child_code,
      material: row.material || "",
      size: row.size || "",
      qty,
    });
  });

  if (errors.length) { showToast(errors[0], "error"); return; }
  if (!selectedRows.length) { showToast("Select at least one child code to create a job card.", "error"); return; }

  // Build preview
  const fmtDate = (d) => {
    if (!d) return "—";
    const [y, m, day] = d.split("-");
    return `${day}-${m}-${y}`;
  };

  document.getElementById("preview-summary").innerHTML =
    `<strong>${selectedRows.length}</strong> job card(s) will be created for <strong>${escapeHtml(customer_name)}</strong> · Delivery: <strong>${fmtDate(delivery_date)}</strong>`;

  document.getElementById("preview-table-body").innerHTML = selectedRows.map((r, i) => `
    <tr>
      <td style="color:var(--muted);">${i + 1}</td>
      <td style="font-weight:700;font-family:'IBM Plex Mono',monospace;color:var(--accent);">${escapeHtml(r.job_card_no)}</td>
      <td style="font-family:'IBM Plex Mono',monospace;font-size:12px;">${escapeHtml(r.child_code)}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(r.item_name)}">${escapeHtml(r.item_name)}</td>
      <td style="text-align:center;">${r.qty}</td>
      <td>${fmtDate(delivery_date)}</td>
    </tr>`).join("");

  // Store for confirm
  window._pendingBulkRows = selectedRows;
  document.getElementById("preview-modal").classList.add("open");
}

function closePreviewModal() {
  document.getElementById("preview-modal").classList.remove("open");
  window._pendingBulkRows = null;
}

async function confirmBulkCreate() {
  const rows = window._pendingBulkRows;
  if (!rows || !rows.length) return;

  const btn = document.getElementById("preview-confirm-btn");
  btn.textContent = "Creating...";
  btn.disabled = true;

  const so_no = getSoNo();
  const work_order_no = getWorkOrderNo();
  const parent_code = document.getElementById("parent_code").value.trim();
  const so_date = document.getElementById("so_date").value || null;
  const job_card_date = document.getElementById("job_card_date").value || null;
  const work_order_date = document.getElementById("work_order_date").value || null;
  const delivery_date = document.getElementById("delivery_date").value;
  const customer_name = document.getElementById("customer_name").value.trim();
  const remarks = document.getElementById("remarks").value.trim();

  try {
    const res = await fetch("/api/job_card/bulk_create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        so_no, work_order_no, parent_code,
        so_date, job_card_date, work_order_date,
        delivery_date, customer_name, remarks,
        rows,
      })
    });
    const data = await res.json();
    closePreviewModal();
    if (data.success) {
      showToast(data.message, "success");
      if (data.errors && data.errors.length) {
        data.errors.forEach(e => setTimeout(() => showToast(e, "error"), 500));
      }
      resetForm();
    } else {
      showToast(data.error || "Bulk create failed.", "error");
    }
  } catch (e) {
    closePreviewModal();
    showToast("Network error: " + e.message, "error");
  } finally {
    btn.textContent = "Confirm & Create";
    btn.disabled = false;
  }
}

// ── Single JC Submit ──────────────────────────────────────────────────────────
async function submitJobCard() {
  const job_card_no = document.getElementById("job_card_no").value.trim();
  const so_no = getSoNo();
  const work_order_no = getWorkOrderNo();
  const parent_code = document.getElementById("parent_code").value.trim();
  const so_date = document.getElementById("so_date").value;
  const job_card_date = document.getElementById("job_card_date").value;
  const work_order_date = document.getElementById("work_order_date").value;
  const child_code = document.getElementById("child_code_manual").value.trim();
  const delivery_date = document.getElementById("delivery_date").value;
  const item_name = document.getElementById("item_name").value.trim();
  const material = document.getElementById("af_material").value.trim();
  const item_qty = document.getElementById("item_qty").value;
  const advance_stock = document.getElementById("advance_stock").value.trim();
  const is_priority = document.getElementById("is_priority").checked;
  const remarks = document.getElementById("remarks").value.trim();
  const total_days = parseInt(document.getElementById("total-days-display").textContent) || 0;
  const customer_name = document.getElementById("customer_name").value.trim();

  const processDays = {};
  document.querySelectorAll("[id^='pdays_']").forEach(inp => {
    processDays[inp.dataset.process] = { days: parseInt(inp.value) || 0, lead_date: null };
  });

  const bom_processes = bomProcessList.length > 0 ? bomProcessList.map(p => p.process_name) : [];
  const firstProcess = bom_processes.length > 0 ? bom_processes[0] : (Object.keys(processDays)[0] || "");

  if (!job_card_no) { showToast("Job Card No is required!", "error"); return; }
  if (!delivery_date) { showToast("Final Delivery Date is required!", "error"); return; }
  if (!isValidFutureDeliveryDate(delivery_date)) { showToast("Final Delivery Date must be after today.", "error"); return; }
  if (!item_name) { showToast("Item name is required!", "error"); return; }
  if (!item_qty) { showToast("Quantity is required!", "error"); return; }
  if (!/^[\d\/]+$/.test(job_card_no)) { showToast("Job Card No must contain only numbers and /", "error"); return; }

  try {
    const res = await fetch("/api/job_card", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_card_no, so_no, work_order_no, parent_code,
        so_date: so_date || null, job_card_date: job_card_date || null,
        work_order_date: work_order_date || null,
        child_code, delivery_date, final_status: "Pending",
        total_days, process_days: processDays, bom_processes,
        items: [{ item_name, material, qty: parseInt(item_qty), advance_stock, first_process: firstProcess, process_master_id: selectedItemId, is_priority }],
        customer_name, remarks
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message, "success");
      resetForm();
    } else {
      showToast(data.error || data.message || `Server error: ${res.status}`, "error");
    }
  } catch (e) {
    showToast("Network error: " + (e.message || "Unable to connect"), "error");
  }
}

// ── Reset ─────────────────────────────────────────────────────────────────────
function resetForm() {
  ["so_no", "work_order_no", "parent_code", "delivery_date", "item_name",
    "item_qty", "advance_stock", "remarks", "customer_name", "child_code_manual",
    "job_card_no"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
  childRows = [];
  isBomMode = false;
  document.getElementById("child-table-section").style.display = "none";
  document.getElementById("manual-child-section").style.display = "block";
  document.getElementById("single-jc-section").style.display = "block";
  setParentStatus("", "");
  hideCustomerSuggestions();
  setDefaultDates();
  clearAutofill();
  updateSaveButton();
  const priorityChip = document.getElementById("priority-chip");
  if (priorityChip) {
    priorityChip.classList.remove("active");
    priorityChip.style.background = "#fef2f2";
    priorityChip.style.color = "#b91c1c";
  }
  const isPriority = document.getElementById("is_priority");
  if (isPriority) isPriority.checked = false;
}

// ── Event listeners ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  // SO No / WO No — numbers only
  ["so_no", "work_order_no"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", function () { this.value = this.value.replace(/[^0-9]/g, ""); });
  });

  // Parent code
  const parentCode = document.getElementById("parent_code");
  if (parentCode) {
    parentCode.addEventListener("input", function () { this.value = this.value.replace(/[^a-zA-Z0-9]/g, ""); });
    parentCode.addEventListener("blur", function () { lookupParentCode(this.value.trim()); });
  }

  // Customer autocomplete
  const customerInput = document.getElementById("customer_name");
  if (customerInput) {
    customerInput.addEventListener("input", function () {
      const query = this.value.trim();
      customerSearchRequestId += 1;
      const requestId = customerSearchRequestId;
      clearTimeout(customerSearchTimer);
      if (query.length < 2) { hideCustomerSuggestions(); return; }
      customerSearchTimer = setTimeout(() => searchCustomers(query, requestId), 250);
    });
  }

  // Delivery date validation
  const deliveryDateInput = document.getElementById("delivery_date");
  if (deliveryDateInput) {
    deliveryDateInput.addEventListener("change", function () {
      if (this.value && !isValidFutureDeliveryDate(this.value)) {
        this.value = "";
        showToast("Final Delivery Date must be after today.", "error");
      }
    });
  }
});

document.addEventListener("click", function (e) {
  if (!e.target.closest(".ac-wrap")) document.getElementById("ac-list")?.classList.remove("open");
  if (!e.target.closest(".customer-ac-wrap")) hideCustomerSuggestions();
});

// ── Init ──────────────────────────────────────────────────────────────────────
setDefaultDates();
loadDefaultDays();

