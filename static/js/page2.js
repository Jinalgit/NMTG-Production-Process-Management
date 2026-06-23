let allRecords = [];
var currentViewId = null;
let currentPage = 1;
let totalRecords = 0;
const PER_PAGE = 50;
const PROCESS_STAGE_COUNT = 25;
const MAX_MIDDLE_PROCESSES = PROCESS_STAGE_COUNT - 6;

const FIXED_START = ["Drawing", "Raw Material", "Cutting"];
const FIXED_END = ["Quality Check", "Assembly", "Store"];
const FIXED_PROCESS_KEYS = new Set([...FIXED_START, ...FIXED_END].map(p => p.toLowerCase()));

function isFixedProcess(process) {
  return FIXED_PROCESS_KEYS.has(String(process || "").trim().toLowerCase());
}

function uniqueProcessNames(processes) {
  const names = [];
  const seen = new Set();

  processes.forEach(process => {
    const name = String(process || "").trim();
    const key = name.toLowerCase();
    if (!name || seen.has(key)) return;
    seen.add(key);
    names.push(name);
  });

  return names;
}

const DB_PROCESS_LIST = Array.isArray(window.PROCESS_MASTER_PROCESS_LIST)
  ? window.PROCESS_MASTER_PROCESS_LIST
  : [];
const DB_MIDDLE_PROCESS_LIST = DB_PROCESS_LIST.filter(process => !isFixedProcess(process));
const PROCESS_LIST = uniqueProcessNames([...FIXED_START, ...DB_MIDDLE_PROCESS_LIST, ...FIXED_END]);
const PROCESS_ORDER = PROCESS_LIST;
const MIDDLE_PROCESS_LIST = PROCESS_LIST.filter(
  p => !isFixedProcess(p)
);

function getMiddleProcesses(processes) {
  const seen = new Set();
  return processes
    .filter(p => p && !isFixedProcess(p))
    .filter(p => {
      if (seen.has(p)) return false;
      seen.add(p);
      return true;
    })
    .slice(0, MAX_MIDDLE_PROCESSES);
}

function buildFinalProcesses(processes) {
  return [...FIXED_START, ...getMiddleProcesses(processes), ...FIXED_END].slice(0, PROCESS_STAGE_COUNT);
}

// ── Load records ──────────────────────────────────────────────────────────────
async function loadRecords() {
  document.getElementById("table-body").innerHTML =
    `<tr><td colspan="8">${renderTableSkeleton(8)}</td></tr>`;
  try {
    const search = document.getElementById("search-input")?.value.trim() ?? "";
    const params = new URLSearchParams({
      search,
      page: currentPage,
      per_page: PER_PAGE,
    });

    const res = await fetch(`/api/process_master?${params}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error || "Load failed", "error"); return; }

    allRecords = data.records;
    totalRecords = data.total;

    renderTable(data.records);
    updateStats(data.records);
    renderPagination(data.total, data.page, PER_PAGE);
  } catch (e) { showToast("Server error", "error"); }
}

function updateStats(records) {
  const totalEl = document.getElementById("stat-total");
  const avgEl = document.getElementById("stat-avg");
  const materialsEl = document.getElementById("stat-materials");
  if (!totalEl || !avgEl || !materialsEl) return;

  totalEl.textContent = records.length;
  const avg = records.reduce((s, r) => s + (r.num_operations || 0), 0) / (records.length || 1);
  avgEl.textContent = avg.toFixed(1);
  const mats = new Set(records.map(r => r.material).filter(Boolean));
  materialsEl.textContent = mats.size;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getRecordProcesses(record) {
  return Array.from({ length: PROCESS_STAGE_COUNT }, (_, i) => record[`p${i + 1}`])
    .filter(Boolean);
}

function renderTable(records) {
  const tbody = document.getElementById("table-body");
  if (!records.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="8">No records found</td></tr>';
    return;
  }
  tbody.innerHTML = records.map((r, i) => {
    const procs = getRecordProcesses(r)
      .map((p, idx) => `<span class="process-tag"><span class="p-num">P${idx + 1}</span>${escapeHtml(p)}</span>`).join("");
    const id = Number(r.id);
    return `<tr class="pm-table-row" onclick="openViewModal(${id})">
      <td class="pm-col-index" style="color:var(--muted);font-weight:400">${((currentPage - 1) * PER_PAGE) + i + 1}</td>
      <td class="pm-col-item" style="max-width:260px">${formatItemNameDisplay(r.model_name || "")}</td>
      <td class="pm-col-material"><span class="material-tag" title="${r.material || ''}">${r.material || "—"}</span></td>
      <td class="size-cell" title="${r.size || ''}">${r.size || "—"}</td>
      <td class="pm-col-part"><span style="font-size:12px;font-weight:600;color:#374151;">${escapeHtml(r.part_name || "-")}</span></td>
      <td class="pm-col-processes"><div class="process-tags">${procs || '<span style="color:var(--muted)">-</span>'}</div></td>
      <td class="pm-col-ops"><span class="ops-badge">${escapeHtml(r.num_operations || 0)}</span></td>
      <td class="pm-col-actions">
        <div class="pm-actions">
          <button class="btn-icon-edit" onclick="event.stopPropagation(); openEditModal(${id})" title="Edit" aria-label="Edit">
            <i class="fa fa-pencil" aria-hidden="true"></i>
          </button>
          <button class="btn-icon-delete" onclick="event.stopPropagation(); openDeleteModal(${id})" title="Delete" aria-label="Delete">
            <i class="fa fa-trash" aria-hidden="true"></i>
          </button>
        </div>
      </td>
    </tr>`;
  }).join("");
  renderMobileCards(records);
}

function renderMobileCards(records) {
  const container = document.getElementById("mobile-cards");
  if (!container) return;
  if (!records.length) {
    container.innerHTML = '<div class="mobile-card-empty">No records found</div>';
    return;
  }
  container.innerHTML = records.map(r => {
    const id = Number(r.id);
    return `<div class="mobile-card" onclick="openViewModal(${id})">
      <div class="mobile-card-name">${escapeHtml(r.model_name || "—")}</div>
      ${r.size ? `<div class="mobile-card-size">${escapeHtml(r.size)}</div>` : ''}
      <div class="mobile-card-actions">
        <button class="btn-icon-edit" onclick="event.stopPropagation(); openEditModal(${id})" title="Edit">
          <i class="fa fa-pencil" aria-hidden="true"></i>
        </button>
        <button class="btn-icon-delete" onclick="event.stopPropagation(); openDeleteModal(${id})" title="Delete">
          <i class="fa fa-trash" aria-hidden="true"></i>
        </button>
      </div>
    </div>`;
  }).join("");
}

let filterTimer = null;
function filterTable() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => {
    currentPage = 1;
    loadRecords();
  }, 300);
}

function renderPagination(total, page, perPage) {
  const bar = document.getElementById("pm-pagination");
  if (!bar) return;

  if (total === 0) { bar.innerHTML = ""; return; }

  const totalPages = Math.ceil(total / perPage);
  let html = "";

  html += `<button ${page <= 1 ? "disabled" : ""} onclick="goToPage(${page - 1})">← Prev</button>`;

  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  if (start > 1) html += `<button onclick="goToPage(1)">1</button>`;
  if (start > 2) html += `<span>…</span>`;
  for (let i = start; i <= end; i++) {
    html += `<button class="${i === page ? "active" : ""}" onclick="goToPage(${i})">${i}</button>`;
  }
  if (end < totalPages - 1) html += `<span>…</span>`;
  if (end < totalPages) html += `<button onclick="goToPage(${totalPages})">${totalPages}</button>`;

  html += `<button ${page >= totalPages ? "disabled" : ""} onclick="goToPage(${page + 1})">Next →</button>`;

  const from = (page - 1) * perPage + 1;
  const to = Math.min(page * perPage, total);
  html += `<span class="pm-page-info">${from}–${to} of ${total} records</span>`;

  bar.innerHTML = html;
}

function goToPage(page) {
  currentPage = page;
  loadRecords();
  document.querySelector(".table-wrap")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function formatDetailLabel(key) {
  return key
    .replace(/^p(\d)$/i, "P$1")
    .replace(/_/g, " ")
    .replace(/\b\w/g, ch => ch.toUpperCase());
}

function getProcessFlowTone(index, total) {
  if (total <= 1) return "flow-green";
  const ratio = index / (total - 1);
  if (ratio < 0.34) return "flow-red";
  if (ratio < 0.67) return "flow-yellow";
  return "flow-green";
}

function buildProcessFlow(processes) {
  if (!processes.length) {
    return '<span class="detail-empty">No processes available</span>';
  }

  return `
    <div class="process-flow-timeline">
      ${processes.map((proc, idx) => `
          <div class="process-flow-step">
            <div class="process-flow-node">
              <span class="process-flow-num">P${idx + 1}</span>
              <span class="process-flow-name">${escapeHtml(proc)}</span>
            </div>
            ${idx < processes.length - 1 ? `<span class="process-flow-arrow" aria-hidden="true"></span>` : ""}
          </div>
        `).join("")}
    </div>
  `;
}

function buildItemDetailsContent(record) {
  const processes = getRecordProcesses(record);
  const details = [
    ["Item Name", record.model_name || "-"],
    ["Material", record.material || "-"],
    ["Size", record.size || "-"],
    ["Part Name", record.part_name || "-"],
    ["Operations Count", record.num_operations || processes.length || 0],
    ["Created Date", formatDateForDisplay(record.created_at) || "-"]
  ];

  return `
    <div class="item-detail-layout">
      <section class="item-detail-section">
        <div class="item-detail-section-title">Item Details</div>
        <div class="item-detail-card-grid">
          ${details.map(([label, value], idx) => `
            <div class="item-detail-card ${idx === 0 ? "item-detail-card-wide" : ""}">
              <span class="item-detail-label">${escapeHtml(label)}</span>
              <span class="item-detail-value">${escapeHtml(value)}</span>
            </div>
          `).join("")}
        </div>
      </section>

      <section class="item-detail-section">
        <div class="item-detail-section-title">Process Flow</div>
        ${buildProcessFlow(processes)}
      </section>
    </div>
  `;
}

function openViewModal(id) {
  if (window.matchMedia("(max-width: 768px)").matches) return;

  const r = allRecords.find(x => Number(x.id) === Number(id));
  if (!r) return;
  currentViewId = id;

  document.getElementById("item-view-content").innerHTML = buildItemDetailsContent(r);

  document.getElementById("item-view-modal").classList.add("open");
}

function closeViewModal() {
  document.getElementById("item-view-modal").classList.remove("open");
}

function openProcessDetail(id, event, rowClickOnly = false) {
  if (event) event.stopPropagation();
  if (rowClickOnly && !window.matchMedia("(max-width: 720px)").matches) return;

  const record = allRecords.find(r => Number(r.id) === Number(id));
  if (!record) return;
  currentViewId = id;
  document.getElementById("process-detail-content").innerHTML = buildItemDetailsContent(record);

  document.getElementById("view-detail-modal").classList.add("open");
}

function closeProcessDetailModal() {
  document.getElementById("view-detail-modal").classList.remove("open");
}

// ── ADD MODAL ─────────────────────────────────────────────────────────────────
let addSelectedProcesses = []; // tracks order of selection

function openAddModal() {
  document.getElementById("m-name").value = "";
  document.getElementById("m-material").value = "";
  document.getElementById("m-part-name").value = "";
  addSelectedProcesses = [];
  renderAddCheckboxes();
  renderAddSelectedList();
  document.getElementById("add-modal").classList.add("open");
}

function closeAddModal() {
  document.getElementById("add-modal").classList.remove("open");
  document.getElementById("m-size").value = "";
}

function renderAddCheckboxes() {
  const container = document.getElementById("add-process-checkboxes");
  container.innerHTML = MIDDLE_PROCESS_LIST.map(proc => {
    const isSelected = addSelectedProcesses.includes(proc);
    return `
      <div class="proc-checkbox-item ${isSelected ? 'selected' : ''}"
           onclick="toggleAddProcess('${proc}')" data-proc="${proc}">
        <span class="checkbox-icon">${isSelected ? '✓' : ''}</span>
        <span>${proc}</span>
      </div>`;
  }).join("");
}

function renderAddSelectedList() {
  const list = document.getElementById("add-selected-list");
  const emptyMsg = document.getElementById("empty-selected-msg");

  if (!addSelectedProcesses.length) {
    list.innerHTML = `<div class="empty-selected" id="empty-selected-msg">
      No processes selected yet.<br>Click processes on the left to add them.
    </div>`;
    return;
  }

  list.innerHTML = addSelectedProcesses.map((proc, idx) => `
    <div class="selected-proc-item">
      <span class="sel-num">P${idx + 4}</span>
      <span class="sel-name">${proc}</span>
      <button class="btn-proc-del" onclick="removeAddProcess('${proc}')">✕</button>
    </div>
  `).join("");
}

function toggleAddProcess(proc) {
  if (addSelectedProcesses.includes(proc)) {
    addSelectedProcesses = addSelectedProcesses.filter(p => p !== proc);
  } else {
    if (addSelectedProcesses.length >= MAX_MIDDLE_PROCESSES) {
      showToast(`Maximum ${MAX_MIDDLE_PROCESSES} middle processes allowed`, "error");
      return;
    }
    addSelectedProcesses.push(proc);
  }
  renderAddCheckboxes();
  renderAddSelectedList();
}


function removeAddProcess(proc) {
  addSelectedProcesses = addSelectedProcesses.filter(p => p !== proc);
  renderAddCheckboxes();
  renderAddSelectedList();
}

async function saveItem() {
  const name = document.getElementById("m-name").value.trim();
  if (!name) { showToast("Item name is required!", "error"); return; }
  if (!addSelectedProcesses.length) { showToast("Select at least one process!", "error"); return; }

  const FIXED_START = ["Drawing", "Raw Material", "Cutting"];
  const FIXED_END = ["Quality Check", "Assembly", "Store"];
  const middle = addSelectedProcesses.filter(
    p => !FIXED_START.includes(p) && !FIXED_END.includes(p)
  );
  const finalProcs = [...FIXED_START, ...middle, ...FIXED_END].slice(0, PROCESS_STAGE_COUNT);

  const body = {
    model_name: name,
    material: document.getElementById("m-material").value.trim(),
    part_name: document.getElementById("m-part-name").value.trim()
  };
  for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) body[`p${i}`] = finalProcs[i - 1] || null;

  try {
    const res = await fetch("/api/process_master", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      closeAddModal();
      loadRecords();
    } else showToast(data.error, "error");
  } catch (e) { showToast("Server error", "error"); }
}

// ── DELETE ────────────────────────────────────────────────────────────────────
let pendingDeleteId = null;

function deleteItem(id) {
  const rec = allRecords.find(r => Number(r.id) === Number(id));
  pendingDeleteId = id;
  document.getElementById("delete-item-name").textContent = rec?.model_name || "this item";
  document.getElementById("delete-modal").classList.add("open");
}

function closeDeleteModal() {
  pendingDeleteId = null;
  document.getElementById("delete-modal").classList.remove("open");
}

async function confirmDeleteItem() {
  if (!pendingDeleteId) return;
  const id = pendingDeleteId;
  const btn = document.getElementById("delete-confirm-btn");
  btn.disabled = true;
  btn.textContent = "Deleting...";

  try {
    const res = await fetch(`/api/process_master/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) { showToast(data.message, "success"); closeDeleteModal(); loadRecords(); }
    else showToast(data.error, "error");
  } catch (e) { showToast("Server error", "error"); }
  finally {
    btn.disabled = false;
    btn.textContent = "Delete Item";
  }
}

// ── EDIT MODAL ────────────────────────────────────────────────────────────────
let editDragSrc = null;

function openEditModal(id) {
  const r = allRecords.find(rec => rec.id === id);
  if (!r) return;
  document.getElementById("e-id").value = r.id;
  document.getElementById("e-name").value = r.model_name || "";
  document.getElementById("e-material").value = r.material || "";
  document.getElementById("e-part-name").value = r.part_name || "";

  const processes = getRecordProcesses(r);
  renderEditProcessList(processes);
  populateAddProcSelect(processes);
  document.getElementById("edit-modal").classList.add("open");
}

function closeEditModal() {
  document.getElementById("edit-modal").classList.remove("open");
  document.getElementById("e-size").value = "";
}

function populateAddProcSelect(existing) {
  const sel = document.getElementById("add-proc-select");
  sel.innerHTML = `<option value="">+ Add a process...</option>` +
    MIDDLE_PROCESS_LIST
      .filter(p => !existing.includes(p))
      .map(p => `<option value="${p}">${p}</option>`)
      .join("");
}

function addProcessToEdit() {
  const sel = document.getElementById("add-proc-select");
  const proc = sel.value;
  if (!proc) { showToast("Select a process to add", "error"); return; }

  const container = document.getElementById("edit-process-list");
  if (getCurrentEditProcesses().length >= MAX_MIDDLE_PROCESSES) {
    showToast(`Maximum ${MAX_MIDDLE_PROCESSES} middle processes allowed`, "error");
    return;
  }

  addProcCard(container, proc);

  // Remove from dropdown
  sel.querySelector(`option[value="${proc}"]`)?.remove();
  sel.value = "";
}

function renderEditProcessList(processes) {
  const container = document.getElementById("edit-process-list");
  container.innerHTML = "";
  processes.forEach(proc => addProcCard(container, proc));
}

function addProcCard(container, proc) {
  const card = document.createElement("div");
  card.className = "proc-card";
  card.draggable = true;
  card.dataset.value = proc;
  card.innerHTML = `
    <span class="proc-card-handle">⠿</span>
    <span class="proc-card-label">${escapeHtml(proc)}</span>
    <button type="button" class="btn-proc-del" onclick="removeEditProcess(this, decodeURIComponent('${encodeURIComponent(proc)}'))">✕</button>
  `;
  card.addEventListener("dragstart", onEditProcessDragStart);
  card.addEventListener("dragover", onEditProcessDragOver);
  card.addEventListener("dragleave", onEditProcessDragLeave);
  card.addEventListener("drop", onEditProcessDrop);
  card.addEventListener("dragend", onEditProcessDragEnd);
  container.appendChild(card);
}

function removeEditProcess(button, proc) {
  button.closest(".proc-card").remove();
  populateAddProcSelect(getCurrentEditProcesses());
}

function getCurrentEditProcesses() {
  return Array.from(document.querySelectorAll("#edit-process-list .proc-card"))
    .map(card => (card.dataset.value || "").trim())
    .filter(Boolean);
}

// Drag and drop
function onEditProcessDragStart(e) {
  editDragSrc = e.currentTarget;
  e.dataTransfer.effectAllowed = "move";
  e.currentTarget.classList.add("dragging");
}
function onEditProcessDragOver(e) {
  e.preventDefault();
  e.currentTarget.classList.add("drag-over");
}
function onEditProcessDragLeave(e) {
  e.currentTarget.classList.remove("drag-over");
}
function onEditProcessDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove("drag-over");
  if (!editDragSrc || editDragSrc === e.currentTarget) return;
  const container = e.currentTarget.parentNode;
  const targetRect = e.currentTarget.getBoundingClientRect();
  const insertAfter = e.clientY > targetRect.top + targetRect.height / 2;
  if (insertAfter) container.insertBefore(editDragSrc, e.currentTarget.nextSibling);
  else container.insertBefore(editDragSrc, e.currentTarget);
}
function onEditProcessDragEnd(e) {
  e.currentTarget.classList.remove("dragging");
  document.querySelectorAll(".proc-card.drag-over").forEach(el => el.classList.remove("drag-over"));
  editDragSrc = null;
}

async function updateItem() {
  const id = document.getElementById("e-id").value;
  const name = document.getElementById("e-name").value.trim();
  if (!name) { showToast("Item name is required!", "error"); return; }

  const ordered = Array.from(document.querySelectorAll("#edit-process-list .proc-card"))
    .map(c => c.dataset.value.trim()).filter(Boolean);

  const FIXED_START = ["Drawing", "Raw Material", "Cutting"];
  const FIXED_END = ["Quality Check", "Assembly", "Store"];
  const middle = ordered.filter(
    p => !FIXED_START.includes(p) && !FIXED_END.includes(p)
  );
  const finalProcs = [...FIXED_START, ...middle, ...FIXED_END].slice(0, 14);

  const body = {
    model_name: name,
    material: document.getElementById("e-material").value.trim(),
    part_name: document.getElementById("e-part-name").value.trim()
  };
  for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) body[`p${i}`] = finalProcs[i - 1] || null;

  try {
    const res = await fetch(`/api/process_master/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
    });
    const data = await res.json();
    if (data.success) { showToast(data.message, "success"); closeEditModal(); loadRecords(); }
    else showToast(data.error, "error");
  } catch (e) { showToast("Server error", "error"); }
}

loadRecords();

// ── Bulk Entry ────────────────────────────────────────────────────────────────
let pmBulkRowCount = 0;

function openBulkModal() {
  pmBulkRowCount = 0;
  document.getElementById("pm-bulk-tbody").innerHTML = "";
  for (let i = 0; i < 10; i++) addBulkRow();
  document.getElementById("pm-bulk-modal").classList.add("open");
}

function closeBulkModal() {
  document.getElementById("pm-bulk-modal").classList.remove("open");
}

function addBulkRow() {
  const idx = pmBulkRowCount++;
  const tbody = document.getElementById("pm-bulk-tbody");
  const tr = document.createElement("tr");
  tr.id = `pm-br-${idx}`;

  const procCells = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14].map(n => `
    <td>
      <div class="pm-bulk-proc-wrap">
        <input class="pm-bulk-input" id="pm-bp${n}_${idx}" autocomplete="off"
               placeholder="P${n}…"
               oninput="pmBulkProcSearch(${idx},${n})"
               onkeydown="pmBulkProcKeydown(event,${idx},${n})"
               onblur="setTimeout(()=>pmCloseDd(${idx},${n}),150)" />
        <div class="pm-bulk-proc-dd" id="pm-bdd${n}_${idx}"></div>
      </div>
    </td>`).join("");

  tr.innerHTML = `
    <td style="text-align:center;color:var(--muted);font-size:12px;padding:6px 4px">${idx + 1}</td>
    <td><input class="pm-bulk-input" id="pm-bname_${idx}" placeholder="Item name…"
               onkeydown="pmBulkTab(event,${idx},'name')" /></td>
    <td><input class="pm-bulk-input" id="pm-bmat_${idx}" placeholder="Material…"
               onkeydown="pmBulkTab(event,${idx},'mat')" /></td>
    ${procCells}
    <td style="text-align:center">
      <button onclick="removeBulkRow(${idx})"
              style="background:none;border:none;color:#dc2626;cursor:pointer;
                     font-size:15px;padding:4px 8px" title="Remove">✕</button>
    </td>`;
  tbody.appendChild(tr);
}

function removeBulkRow(idx) {
  const row = document.getElementById(`pm-br-${idx}`);
  if (row) row.remove();
}

function clearBulkAll() {
  pmBulkRowCount = 0;
  document.getElementById("pm-bulk-tbody").innerHTML = "";
  for (let i = 0; i < 10; i++) addBulkRow();
}

// Tab navigation: name → mat → p1 → p2 … p25 → next row name
function pmBulkTab(e, idx, field) {
  if (e.key !== "Tab") return;
  e.preventDefault();
  if (field === "name") { document.getElementById(`pm-bmat_${idx}`)?.focus(); return; }
  if (field === "mat") { document.getElementById(`pm-bp4_${idx}`)?.focus(); return; }
  const n = parseInt(field.replace("p", ""));
  if (n < PROCESS_STAGE_COUNT) { document.getElementById(`pm-bp${n + 1}_${idx}`)?.focus(); return; }
  const next = document.getElementById(`pm-bname_${idx + 1}`);
  if (next) { next.focus(); return; }
  addBulkRow();
  setTimeout(() => document.getElementById(`pm-bname_${idx + 1}`)?.focus(), 50);
}

// Process dropdown
function pmBulkProcSearch(idx, n) {
  const val = document.getElementById(`pm-bp${n}_${idx}`).value.trim().toLowerCase();
  const dd = document.getElementById(`pm-bdd${n}_${idx}`);
  const filtered = val ? MIDDLE_PROCESS_LIST.filter(p => p.toLowerCase().includes(val)) : MIDDLE_PROCESS_LIST;
  if (!filtered.length) { dd.classList.remove("open"); return; }
  dd.innerHTML = filtered.map(p =>
    `<div class="pm-bulk-proc-opt" onmousedown="event.preventDefault();pmBulkSelectProc(${idx},${n},'${p.replace(/'/g, "\\'")}')">
      ${p}
    </div>`).join("");
  dd.classList.add("open");
}

function pmBulkSelectProc(idx, n, proc) {
  document.getElementById(`pm-bp${n}_${idx}`).value = proc;
  pmCloseDd(idx, n);
  document.getElementById(`pm-bp${n + 1}_${idx}`)?.focus();
}

function pmCloseDd(idx, n) {
  document.getElementById(`pm-bdd${n}_${idx}`)?.classList.remove("open");
}

function pmBulkProcKeydown(e, idx, n) {
  const dd = document.getElementById(`pm-bdd${n}_${idx}`);
  if (!dd) return;
  const opts = dd.querySelectorAll(".pm-bulk-proc-opt");
  const active = dd.querySelector(".pm-bulk-proc-opt.active");

  if (e.key === "ArrowDown") {
    e.preventDefault();
    let i = active ? Array.from(opts).indexOf(active) + 1 : 0;
    if (i >= opts.length) i = 0;
    opts.forEach(o => o.classList.remove("active"));
    opts[i]?.classList.add("active");
    opts[i]?.scrollIntoView({ block: "nearest" });
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    let i = active ? Array.from(opts).indexOf(active) - 1 : opts.length - 1;
    if (i < 0) i = opts.length - 1;
    opts.forEach(o => o.classList.remove("active"));
    opts[i]?.classList.add("active");
    opts[i]?.scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (active) pmBulkSelectProc(idx, n, active.textContent.trim());
  } else if (e.key === "Escape") {
    pmCloseDd(idx, n);
  } else if (e.key === "Tab") {
    pmCloseDd(idx, n);
    pmBulkTab(e, idx, `p${n}`);
  }
}

document.addEventListener("click", function (e) {
  if (!e.target.closest(".pm-bulk-proc-wrap"))
    document.querySelectorAll(".pm-bulk-proc-dd.open").forEach(d => d.classList.remove("open"));
});

async function saveBulkAll() {
  const rows = document.querySelectorAll("#pm-bulk-tbody tr");
  const valid = [];
  const errors = [];

  rows.forEach(row => {
    const idx = row.id.replace("pm-br-", "");
    const name = document.getElementById(`pm-bname_${idx}`)?.value.trim();
    const mat = document.getElementById(`pm-bmat_${idx}`)?.value.trim() || "";
    const procs = Array.from({ length: PROCESS_STAGE_COUNT }, (_, i) => i + 1).map(n =>
      document.getElementById(`pm-bp${n}_${idx}`)?.value.trim() || null
    );
    const hasData = name || procs.some(Boolean);
    if (!hasData) return;
    if (!name) { errors.push(`Row ${parseInt(idx) + 1}: Item Name is required`); return; }
    const body = { model_name: name, material: mat };
    for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) body[`p${i}`] = procs[i - 1] || null;
    valid.push(body);
  });

  if (errors.length) { showToast(errors[0], "error"); return; }
  if (!valid.length) { showToast("No rows to save", "error"); return; }

  const btn = document.getElementById("pm-bulk-save-btn");
  btn.textContent = "Saving…";
  btn.disabled = true;

  let saved = 0, failed = 0, firstErr = "";

  for (const body of valid) {
    try {
      const res = await fetch("/api/process_master", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (res.ok && data.success) saved++;
      else { failed++; if (!firstErr) firstErr = data.error || "error"; }
    } catch (e) { failed++; }
  }

  btn.textContent = "Save All";
  btn.disabled = false;

  if (failed === 0) {
    showToast(`${saved} item${saved !== 1 ? "s" : ""} saved successfully!`, "success");
    closeBulkModal();
    loadRecords();
  } else {
    showToast(`${saved} saved, ${failed} failed. ${firstErr}`, "error");
  }
}

// Page 2 refinements: fixed process packing, view/edit icons, and bulk selects.
function renderAddCheckboxes() {
  const container = document.getElementById("add-process-checkboxes");
  const available = MIDDLE_PROCESS_LIST.filter(proc => !addSelectedProcesses.includes(proc));
  const isFull = addSelectedProcesses.length >= MAX_MIDDLE_PROCESSES;
  const disabled = isFull || available.length === 0;
  const placeholder = isFull
    ? `Maximum ${MAX_MIDDLE_PROCESSES} middle processes selected`
    : available.length
      ? "Select process to add..."
      : "No more processes available";

  container.innerHTML = `
    <select id="add-process-select"
            class="process-dropdown-select"
            onchange="addProcessFromDropdown(this)"
            ${disabled ? "disabled" : ""}>
      <option value="">${placeholder}</option>
      ${available.map(proc => `<option value="${escapeHtml(proc)}">${escapeHtml(proc)}</option>`).join("")}
    </select>
    <div class="process-dropdown-help">Selected process will be added automatically.</div>
  `;
}

function renderAddSelectedList() {
  const list = document.getElementById("add-selected-list");
  const middleHtml = addSelectedProcesses.length
    ? addSelectedProcesses.map((proc, idx) => `
      <div class="selected-proc-item">
        <span class="sel-num">P${idx + 4}</span>
        <span class="sel-name">${escapeHtml(proc)}</span>
        <button class="btn-proc-del" onclick="removeAddProcess(decodeURIComponent('${encodeURIComponent(proc)}'))" title="Remove" aria-label="Remove">
          <i class="fa fa-close" aria-hidden="true"></i>
        </button>
      </div>
    `).join("")
    : `<div class="empty-selected" id="empty-selected-msg">Select middle processes from the left.</div>`;

  const endStart = FIXED_START.length + addSelectedProcesses.length + 1;
  list.innerHTML = `
    ${FIXED_START.map((proc, idx) => `
      <div class="selected-proc-item locked">
        <span class="sel-num">P${idx + 1}</span>
        <span class="sel-name"><i class="fa fa-lock" aria-hidden="true"></i> ${escapeHtml(proc)} <em></em></span>
      </div>
    `).join("")}
    ${middleHtml}
    ${FIXED_END.map((proc, idx) => `
      <div class="selected-proc-item locked">
        <span class="sel-num">P${endStart + idx}</span>
        <span class="sel-name"><i class="fa fa-lock" aria-hidden="true"></i> ${escapeHtml(proc)} <em></em></span>
      </div>
    `).join("")}
  `;
}

function toggleAddProcess(proc) {
  if (addSelectedProcesses.includes(proc)) {
    addSelectedProcesses = addSelectedProcesses.filter(p => p !== proc);
  } else {
    if (addSelectedProcesses.length >= MAX_MIDDLE_PROCESSES) {
      showToast(`Maximum ${MAX_MIDDLE_PROCESSES} middle processes allowed`, "error");
      return;
    }
    addSelectedProcesses.push(proc);
  }
  renderAddCheckboxes();
  renderAddSelectedList();
}

function addProcessFromDropdown(select) {
  const proc = select.value;
  if (!proc) return;

  if (addSelectedProcesses.length >= MAX_MIDDLE_PROCESSES) {
    showToast(`Maximum ${MAX_MIDDLE_PROCESSES} middle processes allowed`, "error");
    select.value = "";
    return;
  }

  if (!addSelectedProcesses.includes(proc)) {
    addSelectedProcesses.push(proc);
  }

  renderAddCheckboxes();
  renderAddSelectedList();
}

async function saveItem() {
  const name = document.getElementById("m-name").value.trim();
  if (!name) { showToast("Item name is required!", "error"); return; }
  if (!addSelectedProcesses.length) {
    showToast("Select at least one middle process!", "error");
    return;
  }

  const finalProcs = buildFinalProcesses(addSelectedProcesses);
  const body = {
    model_name: name,
    material: document.getElementById("m-material").value.trim(),
    size: document.getElementById("m-size").value.trim(),
    part_name: document.getElementById("m-part-name").value.trim()
  };
  for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) body[`p${i}`] = finalProcs[i - 1] || null;

  try {
    const res = await fetch("/api/process_master", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      closeAddModal();
      loadRecords();
    } else showToast(data.error, "error");
  } catch (e) { showToast("Server error", "error"); }
}

function openDeleteModal(id) {
  deleteItem(id);
}

function openEditModal(id) {
  const r = allRecords.find(rec => Number(rec.id) === Number(id));
  if (!r) return;
  document.getElementById("e-id").value = r.id;
  document.getElementById("e-name").value = r.model_name || "";
  document.getElementById("e-material").value = r.material || "";
  document.getElementById("e-size").value = r.size || "";
  document.getElementById("e-part-name").value = r.part_name || "";

  const middleProcesses = getMiddleProcesses(getRecordProcesses(r));
  renderEditProcessList(middleProcesses);
  populateAddProcSelect(middleProcesses);
  document.getElementById("edit-modal").classList.add("open");
}

function populateAddProcSelect(existing) {
  const sel = document.getElementById("add-proc-select");
  const current = existing || getCurrentEditProcesses();
  const available = MIDDLE_PROCESS_LIST.filter(p => !current.includes(p));
  const isFull = current.length >= MAX_MIDDLE_PROCESSES;
  const disabled = isFull || available.length === 0;
  const placeholder = isFull
    ? `Maximum ${MAX_MIDDLE_PROCESSES} middle processes selected`
    : available.length
      ? "+ Add a middle process..."
      : "No more processes available";

  sel.innerHTML = `<option value="">${placeholder}</option>` +
    available
      .map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`)
      .join("");
  sel.disabled = disabled;
  sel.value = "";
}

function addProcessToEdit() {
  const sel = document.getElementById("add-proc-select");
  const proc = sel.value;
  if (!proc) return;

  const container = document.getElementById("edit-process-list");
  const current = getCurrentEditProcesses();
  if (current.length >= MAX_MIDDLE_PROCESSES) {
    showToast(`Maximum ${MAX_MIDDLE_PROCESSES} middle processes allowed`, "error");
    populateAddProcSelect(current);
    return;
  }

  if (!current.includes(proc)) {
    addProcCard(container, proc);
  }
  populateAddProcSelect(getCurrentEditProcesses());
}

async function updateItem() {
  const id = document.getElementById("e-id").value;
  const name = document.getElementById("e-name").value.trim();
  if (!name) { showToast("Item name is required!", "error"); return; }

  const ordered = Array.from(document.querySelectorAll("#edit-process-list .proc-card"))
    .map(c => c.dataset.value.trim()).filter(Boolean);
  const finalProcs = buildFinalProcesses(ordered);

  const body = {
    model_name: name,
    material: document.getElementById("e-material").value.trim(),
    size: document.getElementById("e-size").value.trim(),
    part_name: document.getElementById("e-part-name").value.trim()
  };
  for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) body[`p${i}`] = finalProcs[i - 1] || null;

  try {
    const res = await fetch(`/api/process_master/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = await res.json();
    if (data.success) { showToast(data.message, "success"); closeEditModal(); loadRecords(); }
    else showToast(data.error, "error");
  } catch (e) { showToast("Server error", "error"); }
}

function renderBulkProcessSelect(idx, n) {
  const fixedBySlot = {
    1: "Drawing",
    2: "Raw Material",
    3: "Cutting",
    23: "Quality Check",
    24: "Assembly",
    25: "Store"
  };
  const fixed = fixedBySlot[n];
  if (fixed) {
    return `
      <select class="pm-bulk-select pm-bulk-select-fixed" id="pm-bp${n}_${idx}"
              style="background:#f0f4fa;color:var(--muted);pointer-events:none;"
              tabindex="-1" disabled aria-label="P${n} fixed process">
        <option value="${escapeHtml(fixed)}" selected>${escapeHtml(fixed)}</option>
      </select>`;
  }

  return `
    <select class="pm-bulk-select" id="pm-bp${n}_${idx}"
            onchange="refreshBulkProcessDropdowns(${idx})"
            onkeydown="pmBulkTab(event,${idx},'p${n}')"
            aria-label="P${n} process">
      <option value="">-- Select --</option>
      ${MIDDLE_PROCESS_LIST.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join("")}
    </select>`;
}

function getBulkPreviousSelections(idx, n) {
  const selected = [];
  for (let p = 4; p < n && p <= 22; p++) {
    const value = document.getElementById(`pm-bp${p}_${idx}`)?.value.trim();
    if (value) selected.push(value);
  }
  return selected;
}

function renderBulkSelectOptions(select, blocked, current) {
  const available = MIDDLE_PROCESS_LIST.filter(proc => proc === current || !blocked.includes(proc));
  select.innerHTML = `<option value="">-- Select --</option>` +
    available.map(proc => `<option value="${escapeHtml(proc)}">${escapeHtml(proc)}</option>`).join("");
  select.value = current;
}

function refreshBulkProcessDropdowns(idx) {
  for (let n = 4; n <= 11; n++) {
    const select = document.getElementById(`pm-bp${n}_${idx}`);
    if (!select) continue;

    const blocked = getBulkPreviousSelections(idx, n);
    let current = select.value.trim();
    if (current && blocked.includes(current)) current = "";

    renderBulkSelectOptions(select, blocked, current);
  }
}

function addBulkRow() {
  const idx = pmBulkRowCount++;
  const tbody = document.getElementById("pm-bulk-tbody");
  const tr = document.createElement("tr");
  tr.id = `pm-br-${idx}`;

  const procCells = Array.from({ length: PROCESS_STAGE_COUNT }, (_, i) => i + 1).map(n => `
    <td>
      <div class="pm-bulk-proc-wrap">
        ${renderBulkProcessSelect(idx, n)}
      </div>
    </td>`).join("");

  tr.innerHTML = `
    <td style="text-align:center;color:var(--muted);font-size:12px;padding:6px 4px">${idx + 1}</td>
    <td><input class="pm-bulk-input" id="pm-bname_${idx}" placeholder="Item name..."
               onkeydown="pmBulkTab(event,${idx},'name')" /></td>
    <td><input class="pm-bulk-input" id="pm-bmat_${idx}" placeholder="Material..."
               onkeydown="pmBulkTab(event,${idx},'mat')" /></td>
    ${procCells}
    <td style="text-align:center">
      <button onclick="removeBulkRow(${idx})"
              style="background:none;border:none;color:#dc2626;cursor:pointer;
                     font-size:15px;padding:4px 8px" title="Remove" aria-label="Remove">
        <i class="fa fa-close" aria-hidden="true"></i>
      </button>
    </td>`;
  tbody.appendChild(tr);
  refreshBulkProcessDropdowns(idx);
}

function pmBulkTab(e, idx, field) {
  if (e.key !== "Tab") return;
  e.preventDefault();
  if (field === "name") { document.getElementById(`pm-bmat_${idx}`)?.focus(); return; }
  if (field === "mat") { document.getElementById(`pm-bp4_${idx}`)?.focus(); return; }
  const n = parseInt(field.replace("p", ""), 10);
  if (n < 22) { document.getElementById(`pm-bp${n + 1}_${idx}`)?.focus(); return; }
  const next = document.getElementById(`pm-bname_${idx + 1}`);
  if (next) { next.focus(); return; }
  addBulkRow();
  setTimeout(() => document.getElementById(`pm-bname_${idx + 1}`)?.focus(), 50);
}

async function saveBulkAll() {
  const rows = document.querySelectorAll("#pm-bulk-tbody tr");
  const valid = [];
  const errors = [];

  rows.forEach(row => {
    const idx = row.id.replace("pm-br-", "");
    const name = document.getElementById(`pm-bname_${idx}`)?.value.trim();
    const mat = document.getElementById(`pm-bmat_${idx}`)?.value.trim() || "";
    const middle = Array.from({ length: MAX_MIDDLE_PROCESSES }, (_, i) => i + 4)
      .map(n => document.getElementById(`pm-bp${n}_${idx}`)?.value.trim())
      .filter(Boolean);

    const hasData = name || middle.length;
    if (!hasData) return;
    if (!name) { errors.push(`Row ${parseInt(idx, 10) + 1}: Item Name is required`); return; }
    if (!middle.length) { errors.push(`Row ${parseInt(idx, 10) + 1}: Select at least one middle process`); return; }

    const finalProcs = buildFinalProcesses(middle);
    const body = { model_name: name, material: mat };
    for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) body[`p${i}`] = finalProcs[i - 1] || null;
    valid.push(body);
  });

  if (errors.length) { showToast(errors[0], "error"); return; }
  if (!valid.length) { showToast("No rows to save", "error"); return; }

  const btn = document.getElementById("pm-bulk-save-btn");
  btn.textContent = "Saving...";
  btn.disabled = true;

  let saved = 0, failed = 0, firstErr = "";
  for (const body of valid) {
    try {
      const res = await fetch("/api/process_master", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (res.ok && data.success) saved++;
      else { failed++; if (!firstErr) firstErr = data.error || "error"; }
    } catch (e) { failed++; }
  }

  btn.textContent = "Save All";
  btn.disabled = false;

  if (failed === 0) {
    showToast(`${saved} item${saved !== 1 ? "s" : ""} saved successfully!`, "success");
    closeBulkModal();
    loadRecords();
  } else {
    showToast(`${saved} saved, ${failed} failed. ${firstErr}`, "error");
  }
}

function formatItemNameDisplay(name) {
  const value = String(name || "").trim();

  let line1 = value;
  let line2 = "";

  // Case 1: Locking Assembly Model: N7016.1
  const modelMatch = value.match(/^(.*?)\s+Model:\s*(.*)$/i);
  if (modelMatch) {
    line1 = modelMatch[1].trim();
    line2 = `Model: ${modelMatch[2].trim()}`;
  }

  // Case 2: Cage NSC 37D.sp1 - 37 x 55 x 14.5
  else if (value.includes(" - ")) {
    const parts = value.split(" - ");
    line1 = parts[0].trim();
    line2 = `Size: ${parts.slice(1).join(" - ").trim()}`;
  }

  // Case 3: CLS Cam Size: 12 x 19 TL / RH Cage Plate: ...
  else if (value.includes(":")) {
    const parts = value.split(":");
    line1 = parts[0].trim();
    line2 = parts.slice(1).join(":").trim();
  }

  // Case 4: No separator available
  else {
    line1 = value;
    line2 = "";
  }

  return `
    <div class="pm-item-display">
      <div class="pm-item-title">${escapeHtml(line1)}</div>
      ${line2 ? `<div class="pm-item-model">${escapeHtml(line2)}</div>` : `<div class="pm-item-model">&nbsp;</div>`}
    </div>
  `;
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