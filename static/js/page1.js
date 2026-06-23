let allItems = [];
let defaultDays = {}; // process_name â†’ default days
let selectedItemId = null;
const PROCESS_STAGE_COUNT = 25;

// â”€â”€ Load items and default days on startup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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

// â”€â”€ Input restrictions â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
document.addEventListener("DOMContentLoaded", function () {
  ["so_no", "work_order_no"].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("input", function () {
        this.value = this.value.replace(/[^0-9]/g, "");
      });
    }
  });

  const parentCode = document.getElementById("parent_code");
  if (parentCode) {
    parentCode.addEventListener("input", function () {
      this.value = this.value.replace(/[^a-zA-Z0-9]/g, "");
    });
  }
});

function getSoNo() {
  const val = document.getElementById("so_no").value.trim();
  return val ? "S" + val : "";
}

function getWorkOrderNo() {
  const val = document.getElementById("work_order_no").value.trim();
  return val ? "WO" + val : "";
}

// â”€â”€ Date helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function getTodayDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function getTomorrowDate() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isValidFutureDeliveryDate(dateStr) {
  return Boolean(dateStr) && dateStr >= getTomorrowDate();
}

function setDefaultDates() {
  const today = getTodayDate();
  document.getElementById("so_date").value = today;
  document.getElementById("job_card_date").value = today;
  document.getElementById("work_order_date").value = today;
  document.getElementById("delivery_date").min = getTomorrowDate();
}

// â”€â”€ Autocomplete â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function getItemDisplayName(item) {
  const modelName = String(item.model_name || "").trim();
  const size = String(item.size || "").trim();
  const partName = String(item.part_name || "").trim();

  // Normalize for comparison: lowercase, strip all spaces
  const normalize = (s) => s.toLowerCase().replace(/\s+/g, "");
  const modelNorm = normalize(modelName);
  const sizeNorm = normalize(size);

  // If the size is already embedded in the model name, don't repeat it
  const sizeAlreadyInModel = sizeNorm && modelNorm.includes(sizeNorm);

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
    if (active) { active.classList.remove("active"); idx = Array.from(items).indexOf(active); idx = (idx + 1) % items.length; }
    else idx = 0;
    items[idx].classList.add("active");
    items[idx].scrollIntoView({ block: "nearest" });
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    if (active) { active.classList.remove("active"); idx = Array.from(items).indexOf(active); idx = (idx - 1 + items.length) % items.length; }
    else idx = items.length - 1;
    items[idx].classList.add("active");
    items[idx].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (active) active.dispatchEvent(new Event("mousedown"));
  } else if (e.key === "Escape") {
    list.classList.remove("open");
  }
}

document.addEventListener("click", function (e) {
  if (!e.target.closest(".ac-wrap"))
    document.getElementById("ac-list").classList.remove("open");
});

document.addEventListener("DOMContentLoaded", function () {
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

// â”€â”€ Auto-fill: Material + Process Days â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function fillItemDetails(item) {
  document.getElementById("item-autofill").style.display = "block";
  document.getElementById("af_material").value = item.material || "";
  document.getElementById("af_size").value = item.size || "";
  document.getElementById("af_part_name").value = item.part_name || "";

  const grid = document.getElementById("process-days-grid");
  grid.innerHTML = "";

  const processes = [];
  for (let i = 1; i <= PROCESS_STAGE_COUNT; i++) {
    const p = item["p" + i];
    if (p) processes.push(p);
  }

  processes.forEach((proc, idx) => {
    const normProc = (proc || "").trim().toLowerCase();
    const defDays = Object.prototype.hasOwnProperty.call(defaultDays, normProc) ? defaultDays[normProc] : 0;

    const div = document.createElement("div");
    div.className = "process-day-item";
    div.innerHTML = `
      <label>P${idx + 1}: ${proc}</label>
      <input type="number" id="pdays_${idx}" placeholder="Days" min="0"
             value="${defDays}" oninput="updateTotalDays()" data-process="${proc}" />
    `;
    grid.appendChild(div);
  });

  updateTotalDays();
}

// â”€â”€ Total Days live sum â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function updateTotalDays() {
  const inputs = document.querySelectorAll("[id^='pdays_']");
  let total = 0;
  inputs.forEach(inp => {
    const v = parseInt(inp.value);
    if (!isNaN(v) && v > 0) total += v;
  });
  document.getElementById("total-days-display").textContent = total;
}

function clearAutofill() {
  selectedItemId = null;
  document.getElementById("item-autofill").style.display = "none";
  document.getElementById("af_material").value = "";
  document.getElementById("af_size").value = "";
  document.getElementById("af_part_name").value = "";
  document.getElementById("process-days-grid").innerHTML = "";
  document.getElementById("total-days-display").textContent = "0";
}

// â”€â”€ Submit â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function submitJobCard() {
  const job_card_no = document.getElementById("job_card_no").value.trim();
  const so_no = getSoNo();
  const work_order_no = getWorkOrderNo();
  const parent_code = document.getElementById("parent_code").value.trim();
  const so_date = document.getElementById("so_date").value;
  const job_card_date = document.getElementById("job_card_date").value;
  const work_order_date = document.getElementById("work_order_date").value;
  const child_code = document.getElementById("child_code").value.trim();
  const delivery_date = document.getElementById("delivery_date").value;
  const final_status = document.querySelector("input[name='final_status']:checked")?.value || "Pending";
  const item_name = document.getElementById("item_name").value.trim();
  const material = document.getElementById("af_material").value.trim();
  const item_qty = document.getElementById("item_qty").value;
  const advance_stock = document.getElementById("advance_stock").value.trim();
  const is_priority = document.getElementById("is_priority").checked;
  const remarks = document.getElementById("remarks").value.trim();
  const total_days = parseInt(document.getElementById("total-days-display").textContent) || 0;
  const customer_name = document.getElementById("customer_name").value.trim();

  // Collect process days
  const processDays = {};
  document.querySelectorAll("[id^='pdays_']").forEach(inp => {
    processDays[inp.dataset.process] = {
      days: parseInt(inp.value) || 0,
      lead_date: null
    };
  });

  const firstProcess = Object.keys(processDays)[0] || "";

  if (!job_card_no) { showToast("Job Card No is required!", "error"); return; }
  if (!delivery_date) { showToast("Final Delivery Date is required!", "error"); return; }
  if (!isValidFutureDeliveryDate(delivery_date)) { showToast("Final Delivery Date must be after today.", "error"); return; }
  if (!item_name) { showToast("Item name is required!", "error"); return; }
  if (!item_qty) { showToast("Quantity is required!", "error"); return; }

  if (!/^[\d\/]+$/.test(job_card_no)) {
    showToast("Job Card No must contain only numbers and /", "error"); return;
  }

  try {
    const res = await fetch("/api/job_card", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_card_no,
        so_no,
        work_order_no,
        parent_code,
        so_date: so_date || null,
        job_card_date: job_card_date || null,
        work_order_date: work_order_date || null,
        child_code,
        delivery_date,
        final_status,
        total_days,
        process_days: processDays,
        items: [{ item_name, material, qty: parseInt(item_qty), advance_stock, first_process: firstProcess, process_master_id: selectedItemId, is_priority }],
        customer_name,
        remarks
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(data.message, "success");
      resetForm();
    } else {
      const errMsg = data.error || data.message || `Server error: ${res.status} ${res.statusText}`;
      showToast(errMsg, "error");
    }
  } catch (e) {
    showToast("Network error: " + (e.message || "Unable to connect"), "error");
  }
}

// â”€â”€ Reset â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function resetForm() {
  document.getElementById("job_card_no").value = "";
  document.getElementById("so_no").value = "";
  document.getElementById("work_order_no").value = "";
  document.getElementById("parent_code").value = "";
  document.getElementById("child_code").value = "";
  document.getElementById("delivery_date").value = "";
  document.getElementById("item_name").value = "";
  document.getElementById("item_qty").value = "";
  document.getElementById("advance_stock").value = "";
  document.getElementById("remarks").value = "";
  setDefaultDates();
  clearAutofill();
}

// â”€â”€ Init â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
setDefaultDates();
loadDefaultDays();
// â”€â”€ Bulk Entry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
let bulkRowCount = 0;
let bulkACTarget = null; // which row's autocomplete is active

function openBulkModal() {
  bulkRowCount = 0;
  document.getElementById("bulk-tbody").innerHTML = "";
  // Set today's date in common fields
  const today = getTodayDate();
  document.getElementById("bulk-so-date").value = today;
  document.getElementById("bulk-jc-date").value = today;
  // Add 10 empty rows
  for (let i = 0; i < 10; i++) addBulkRow();
  document.getElementById("bulk-modal").classList.add("open");
}

function closeBulkModal() {
  document.getElementById("bulk-modal").classList.remove("open");
}

function addBulkRow() {
  const idx = bulkRowCount++;
  const tbody = document.getElementById("bulk-tbody");
  const tr = document.createElement("tr");
  tr.id = `bulk-row-${idx}`;
  tr.innerHTML = `
    <td style="color:var(--muted);text-align:center;font-size:12px;padding:6px 8px;">${idx + 1}</td>
    <td style="padding:4px;">
      <input type="text" id="b_jc_${idx}" placeholder="e.g. 110020"
             style="width:100%;padding:7px 8px;border:1px solid var(--border);border-radius:4px;
                    font-size:13px;font-family:'IBM Plex Sans',sans-serif;outline:none;"
             onfocus="this.style.borderColor='var(--accent)'"
             onblur="this.style.borderColor='var(--border)'"
             onkeydown="bulkTabNext(event,${idx},'jc')" />
    </td>
    <td style="padding:4px;position:relative;">
      <input type="text" id="b_item_${idx}" placeholder="Type to search..."
             autocomplete="off"
             style="width:100%;padding:7px 8px;border:1px solid var(--border);border-radius:4px;
                    font-size:13px;font-family:'IBM Plex Sans',sans-serif;outline:none;"
             onfocus="this.style.borderColor='var(--accent)'"
             onblur="this.style.borderColor='var(--border)'"
             oninput="bulkItemSearch(${idx})"
             onkeydown="bulkItemKeydown(event,${idx})" />
      <div id="b_ac_${idx}" class="bulk-ac-list"></div>
    </td>
    <td style="padding:4px;">
      <input type="number" id="b_qty_${idx}" placeholder="Qty" min="1"
             style="width:100%;padding:7px 8px;border:1px solid var(--border);border-radius:4px;
                    font-size:13px;font-family:'IBM Plex Sans',sans-serif;outline:none;"
             onfocus="this.style.borderColor='var(--accent)'"
             onblur="this.style.borderColor='var(--border)'"
             onkeydown="bulkTabNext(event,${idx},'qty')" />
    </td>
    <td style="padding:4px;">
      <input type="text" id="b_adv_${idx}" placeholder="Advance stock"
             style="width:100%;padding:7px 8px;border:1px solid var(--border);border-radius:4px;
                    font-size:13px;font-family:'IBM Plex Sans',sans-serif;outline:none;"
             onfocus="this.style.borderColor='var(--accent)'"
             onblur="this.style.borderColor='var(--border)'"
             onkeydown="bulkTabNext(event,${idx},'adv')" />
    </td>
    <td style="padding:4px;">
      <input type="date" id="b_del_${idx}" min="${getTomorrowDate()}" required
             style="width:100%;padding:7px 8px;border:1px solid var(--border);border-radius:4px;
                    font-size:13px;font-family:'IBM Plex Sans',sans-serif;outline:none;"
             onfocus="this.style.borderColor='var(--accent)'"
             onblur="this.style.borderColor='var(--border)'"
             onkeydown="bulkTabNext(event,${idx},'del')" />
    </td>
    <td style="padding:4px;text-align:center;">
      <button onclick="removeBulkRow(${idx})"
              style="background:none;border:none;color:#dc2626;cursor:pointer;
                     font-size:16px;padding:4px 8px;"
              title="Remove row"><i class="fa fa-close" aria-hidden="true"></i></button>
    </td>
  `;
  tbody.appendChild(tr);
}

function removeBulkRow(idx) {
  const row = document.getElementById(`bulk-row-${idx}`);
  if (row) row.remove();
  delete bulkSelectedItems[idx];
}

function clearBulkAll() {
  document.getElementById("bulk-tbody").innerHTML = "";
  bulkRowCount = 0;
  bulkACItems = {};
  bulkSelectedItems = {};
  for (let i = 0; i < 10; i++) addBulkRow();
}

// Tab navigation between cells
function bulkTabNext(e, idx, field) {
  if (e.key !== "Tab") return;
  e.preventDefault();
  const fields = ["jc", "item", "qty", "adv", "del"];
  const cur = fields.indexOf(field);
  if (cur < fields.length - 1) {
    const nextField = fields[cur + 1];
    const nextEl = document.getElementById(`b_${nextField}_${idx}`);
    if (nextEl) nextEl.focus();
  } else {
    // Move to next row JC field
    const nextEl = document.getElementById(`b_jc_${idx + 1}`);
    if (nextEl) nextEl.focus();
    else { addBulkRow(); setTimeout(() => document.getElementById(`b_jc_${idx + 1}`)?.focus(), 50); }
  }
}

// Autocomplete per bulk row
let bulkACItems = {};
let bulkSelectedItems = {};

async function bulkItemSearch(idx) {
  const val = document.getElementById(`b_item_${idx}`).value.trim();
  const list = document.getElementById(`b_ac_${idx}`);
  delete bulkSelectedItems[idx];
  if (!val) { list.classList.remove("open"); return; }

  try {
    const res = await fetch(`/api/items?q=${encodeURIComponent(val)}`);
    const data = await res.json();
    if (!data.success || !data.items.length) { list.classList.remove("open"); return; }
    bulkACItems[idx] = data.items;
    list.innerHTML = data.items.map(i =>
      `<div class="bulk-ac-item" onmousedown="event.preventDefault();bulkSelectItem(${idx},${i.id})">${escapeHtml(getItemDisplayName(i))}</div>`
    ).join("");
    list.classList.add("open");
    bulkACTarget = idx;
  } catch (e) { }
}

function bulkSelectItem(idx, itemId) {
  const items = bulkACItems[idx] || [];
  const item = items.find(i => i.id === itemId);
  if (!item) return;
  bulkSelectedItems[idx] = item;
  document.getElementById(`b_item_${idx}`).value = getItemDisplayName(item);
  document.getElementById(`b_ac_${idx}`).classList.remove("open");
  // Focus qty
  document.getElementById(`b_qty_${idx}`)?.focus();
}

function bulkItemKeydown(e, idx) {
  const list = document.getElementById(`b_ac_${idx}`);
  const items = list.querySelectorAll(".bulk-ac-item");
  const active = list.querySelector(".bulk-ac-item.active");
  if (!items.length) return;

  if (e.key === "ArrowDown") {
    e.preventDefault();
    let i = active ? Array.from(items).indexOf(active) + 1 : 0;
    if (i >= items.length) i = 0;
    items.forEach(el => el.classList.remove("active"));
    items[i].classList.add("active");
    items[i].scrollIntoView({ block: "nearest" });
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    let i = active ? Array.from(items).indexOf(active) - 1 : items.length - 1;
    if (i < 0) i = items.length - 1;
    items.forEach(el => el.classList.remove("active"));
    items[i].classList.add("active");
    items[i].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (active) active.dispatchEvent(new Event("mousedown"));
  } else if (e.key === "Escape") {
    list.classList.remove("open");
  } else if (e.key === "Tab") {
    list.classList.remove("open");
    bulkTabNext(e, idx, "item");
  }
}

// Close autocomplete on outside click
document.addEventListener("click", function (e) {
  document.querySelectorAll(".bulk-ac-list.open").forEach(l => {
    if (!e.target.closest("td")) l.classList.remove("open");
  });
});

// Resolve the first process (p1) for an item from process_master.
// Returns "" on any miss or fetch error so bulk save still works.
async function resolveFirstProcess(itemName, selectedItem) {
  if (selectedItem) return selectedItem.p1 || "";
  try {
    const res = await fetch(`/api/items?q=${encodeURIComponent(itemName)}`);
    const data = await res.json();
    if (!data.success || !data.items || !data.items.length) return "";
    const target = itemName.trim().toLowerCase();
    const match = data.items.find(
      it => (it.model_name || "").trim().toLowerCase() === target
        || getItemDisplayName(it).trim().toLowerCase() === target
    );
    return match ? (match.p1 || "") : "";
  } catch (e) {
    return "";
  }
}

// Save all bulk rows
async function saveBulkAll() {
  const soNo = document.getElementById("bulk-so").value.trim();
  const woNo = document.getElementById("bulk-wo").value.trim();
  const jcDate = document.getElementById("bulk-jc-date").value;
  const soDate = document.getElementById("bulk-so-date").value;

  const rows = document.querySelectorAll("#bulk-tbody tr");
  const valid = [];
  const errors = [];

  for (const row of rows) {
    const idx = row.id.replace("bulk-row-", "");
    const jcNo = document.getElementById(`b_jc_${idx}`)?.value.trim();
    const itemName = document.getElementById(`b_item_${idx}`)?.value.trim();
    const qty = parseInt(document.getElementById(`b_qty_${idx}`)?.value) || 0;
    const advanceStock = document.getElementById(`b_adv_${idx}`)?.value.trim() || "";
    const del = document.getElementById(`b_del_${idx}`)?.value || null;

    if (!jcNo && !itemName) continue; // empty row â€” skip

    if (!jcNo) { errors.push(`Row ${parseInt(idx) + 1}: JC No missing`); continue; }
    if (!itemName) { errors.push(`Row ${parseInt(idx) + 1}: Item Name missing`); continue; }
    if (!qty || qty < 1) { errors.push(`Row ${parseInt(idx) + 1}: Qty must be > 0`); continue; }
    if (!del) { errors.push(`Row ${parseInt(idx) + 1}: Delivery Date missing`); continue; }

    if (!/^[\d\/]+$/.test(jcNo)) {
      errors.push(`Row ${parseInt(idx) + 1}: JC No must contain only numbers and /`); continue;
    }

    const selectedItem = bulkSelectedItems[idx] || null;
    const firstProc = await resolveFirstProcess(itemName, selectedItem);

    valid.push({
      job_card_no: jcNo,
      so_no: soNo ? "S" + soNo : "",
      work_order_no: woNo ? "WO" + woNo : "",
      so_date: soDate || null,
      job_card_date: jcDate || null,
      delivery_date: del,
      final_status: "Pending",
      total_days: 0,
      process_days: {},
      items: [{
        item_name: itemName,
        qty,
        advance_stock: advanceStock,
        first_process: firstProc,
        process_master_id: selectedItem ? selectedItem.id : null
      }],
      remarks: "",
    });
  }

  if (errors.length) {
    showToast(errors[0], "error"); return;
  }
  if (!valid.length) {
    showToast("No valid rows to save", "error"); return;
  }

  const btn = document.getElementById("bulk-save-btn");
  btn.textContent = "Saving...";
  btn.disabled = true;

  let saved = 0, failed = 0, failMsgs = [];

  for (const row of valid) {
    try {
      const res = await fetch("/api/job_card", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(row)
      });
      const data = await res.json();
      if (res.ok && data.success) saved++;
      else { failed++; failMsgs.push(`JC ${row.job_card_no}: ${data.error || "error"}`); }
    } catch (e) { failed++; }
  }

  btn.textContent = "Save All";
  btn.disabled = false;

  if (failed === 0) {
    showToast(`âœ… ${saved} job cards saved successfully!`, "success");
    closeBulkModal();
  } else {
    showToast(`${saved} saved, ${failed} failed. First error: ${failMsgs[0]}`, "error");
  }
}
