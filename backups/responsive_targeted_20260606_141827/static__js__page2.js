let allRecords = [];

// Predefined process list in correct factory order
const PROCESS_ORDER = [
  "Drawing", "Raw Material", "Cutting", "Forging", "Normalising",
  "Rough Turning", "Drilling & Tapping", "Heat Treatment",
  "CNC Machining", "Conventional Machining", "Other Outside Process",
  "Quality Check", "Assembly","Store"
];

// ── Load records ──────────────────────────────────────────────────────────────
async function loadRecords() {
  try {
    const res = await fetch("/api/process_master");
    const data = await res.json();
    if (data.success) {
      allRecords = data.records;
      renderTable(allRecords);
      updateStats(allRecords);
    }
  } catch (e) { showToast(); }
}

function updateStats(records) {
  document.getElementById("stat-total").textContent = records.length;
  const avg = records.reduce((s, r) => s + (r.num_operations || 0), 0) / (records.length || 1);
  document.getElementById("stat-avg").textContent = avg.toFixed(1);
  const mats = new Set(records.map(r => r.material).filter(Boolean));
  document.getElementById("stat-materials").textContent = mats.size;
}

function renderTable(records) {
  const tbody = document.getElementById("table-body");
  if (!records.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6">Loading Data...</td></tr>';
    return;
  }
  tbody.innerHTML = records.map((r, i) => {
    const procs = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]
      .map(k => r[k]).filter(Boolean)
      .map((p, idx) => `<span class="process-tag"><span class="p-num">P${idx + 1}</span>${p}</span>`).join("");
    return `<tr>
      <td style="color:var(--muted);font-weight:400">${i + 1}</td>
      <td style="max-width:220px">${r.model_name}</td>
      <td><span class="material-tag">${r.material || "—"}</span></td>
      <td><span style="font-size:12px;font-weight:600;color:#374151;">${r.part_name||"—"}</span></td>
      <td><div class="process-tags">${procs || '<span style="color:var(--muted)">—</span>'}</div></td>
      <td><span class="ops-badge">${r.num_operations || 0}</span></td>
      <td>
        <div style="display:flex;gap:6px;align-items:center;">
          <button class="btn-edit" onclick="openEditModal(${r.id})">Edit</button>
          <button class="btn-del" onclick="deleteItem(${r.id})">Delete</button>
        </div>
      </td>
    </tr>`;
  }).join("");
}

function filterTable() {
  const q = document.getElementById("search-input").value.toLowerCase();
  renderTable(allRecords.filter(r =>
    (r.model_name || "").toLowerCase().includes(q) ||
    (r.material || "").toLowerCase().includes(q)
  ));
}

// ── ADD MODAL ─────────────────────────────────────────────────────────────────
let addSelectedProcesses = []; // tracks order of selection

function openAddModal() {
  document.getElementById("m-name").value = "";
  document.getElementById("m-material").value = "";
  addSelectedProcesses = [];
  renderAddCheckboxes();
  renderAddSelectedList();
  document.getElementById("add-modal").classList.add("open");
}

function closeAddModal() {
  document.getElementById("add-modal").classList.remove("open");
}

function renderAddCheckboxes() {
  const container = document.getElementById("add-process-checkboxes");
  container.innerHTML = PROCESS_ORDER.map(proc => {
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
      <span class="sel-num">P${idx + 1}</span>
      <span class="sel-name">${proc}</span>
      <button class="btn-proc-del" onclick="removeAddProcess('${proc}')">✕</button>
    </div>
  `).join("");
}

function toggleAddProcess(proc) {
  if (addSelectedProcesses.includes(proc)) {
    addSelectedProcesses = addSelectedProcesses.filter(p => p !== proc);
  } else {
    if (addSelectedProcesses.length >= 8) {
      showToast("Maximum 8 processes allowed", "error"); return;
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

  const body = {
    model_name: name,
    material: document.getElementById("m-material").value.trim()
  };
  for (let i = 1; i <= 8; i++) body[`p${i}`] = addSelectedProcesses[i - 1] || null;

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
async function deleteItem(id) {
  const rec = allRecords.find(r => r.id === id);
  const name = rec ? rec.model_name : "this item";
  if (!confirm(`Delete "${name}"?`)) return;
  try {
    const res = await fetch(`/api/process_master/${id}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) { showToast(data.message, "success"); loadRecords(); }
    else showToast(data.error, "error");
  } catch (e) { showToast("Server error", "error"); }
}

// ── EDIT MODAL ────────────────────────────────────────────────────────────────
let editDragSrc = null;

function openEditModal(id) {
  const r = allRecords.find(rec => rec.id === id);
  if (!r) return;
  document.getElementById("e-id").value = r.id;
  document.getElementById("e-name").value = r.model_name || "";
  document.getElementById("e-material").value = r.material || "";

  const processes = ["p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"]
    .map(k => r[k]).filter(Boolean);
  renderEditProcessList(processes);
  populateAddProcSelect(processes);
  document.getElementById("edit-modal").classList.add("open");
}

function closeEditModal() {
  document.getElementById("edit-modal").classList.remove("open");
}

function populateAddProcSelect(existing) {
  const sel = document.getElementById("add-proc-select");
  sel.innerHTML = `<option value="">+ Add a process...</option>` +
    PROCESS_ORDER
      .filter(p => !existing.includes(p))
      .map(p => `<option value="${p}">${p}</option>`)
      .join("");
}

function addProcessToEdit() {
  const sel = document.getElementById("add-proc-select");
  const proc = sel.value;
  if (!proc) { showToast("Select a process to add", "error"); return; }

  const container = document.getElementById("edit-process-list");
  const cards = container.querySelectorAll(".proc-card");
  if (cards.length >= 8) { showToast("Maximum 8 processes allowed", "error"); return; }

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
    <span class="proc-card-label">${proc}</span>
    <button type="button" class="btn-proc-del" onclick="removeEditProcess(this,'${proc}')">✕</button>
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
  // Add back to dropdown
  const sel = document.getElementById("add-proc-select");
  const opt = document.createElement("option");
  opt.value = proc; opt.textContent = proc;
  sel.appendChild(opt);
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

  const body = { model_name: name, material: document.getElementById("e-material").value.trim() };
  for (let i = 1; i <= 8; i++) body[`p${i}`] = ordered[i - 1] || null;

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

  const procCells = [1,2,3,4,5,6,7,8].map(n => `
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

// Tab navigation: name → mat → p1 → p2 … p8 → next row name
function pmBulkTab(e, idx, field) {
  if (e.key !== "Tab") return;
  e.preventDefault();
  if (field === "name") { document.getElementById(`pm-bmat_${idx}`)?.focus(); return; }
  if (field === "mat")  { document.getElementById(`pm-bp1_${idx}`)?.focus();  return; }
  const n = parseInt(field.replace("p", ""));
  if (n < 8) { document.getElementById(`pm-bp${n+1}_${idx}`)?.focus(); return; }
  const next = document.getElementById(`pm-bname_${idx + 1}`);
  if (next) { next.focus(); return; }
  addBulkRow();
  setTimeout(() => document.getElementById(`pm-bname_${idx + 1}`)?.focus(), 50);
}

// Process dropdown
function pmBulkProcSearch(idx, n) {
  const val = document.getElementById(`pm-bp${n}_${idx}`).value.trim().toLowerCase();
  const dd = document.getElementById(`pm-bdd${n}_${idx}`);
  const filtered = val ? PROCESS_ORDER.filter(p => p.toLowerCase().includes(val)) : PROCESS_ORDER;
  if (!filtered.length) { dd.classList.remove("open"); return; }
  dd.innerHTML = filtered.map(p =>
    `<div class="pm-bulk-proc-opt" onmousedown="event.preventDefault();pmBulkSelectProc(${idx},${n},'${p.replace(/'/g,"\\'")}')">
      ${p}
    </div>`).join("");
  dd.classList.add("open");
}

function pmBulkSelectProc(idx, n, proc) {
  document.getElementById(`pm-bp${n}_${idx}`).value = proc;
  pmCloseDd(idx, n);
  document.getElementById(`pm-bp${n+1}_${idx}`)?.focus();
}

function pmCloseDd(idx, n) {
  document.getElementById(`pm-bdd${n}_${idx}`)?.classList.remove("open");
}

function pmBulkProcKeydown(e, idx, n) {
  const dd = document.getElementById(`pm-bdd${n}_${idx}`);
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

document.addEventListener("click", function(e) {
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
    const mat  = document.getElementById(`pm-bmat_${idx}`)?.value.trim() || "";
    const procs = [1,2,3,4,5,6,7,8].map(n =>
      document.getElementById(`pm-bp${n}_${idx}`)?.value.trim() || null
    );
    const hasData = name || procs.some(Boolean);
    if (!hasData) return;
    if (!name) { errors.push(`Row ${parseInt(idx)+1}: Item Name is required`); return; }
    const body = { model_name: name, material: mat };
    for (let i = 1; i <= 8; i++) body[`p${i}`] = procs[i-1] || null;
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
