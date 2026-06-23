// ── Upload logic — shared by Page 1 (JC) and Page 2 (PM) ─────────────────────
let uploadMode = ""; // "jc" or "pm"
let previewRows = [];

// Column definitions for preview table
const UPLOAD_COLS = {
  jc: [
    { key: "job_card_no", label: "JC No" },
    { key: "so_no", label: "SO No" },
    { key: "so_date", label: "SO Date" },
    { key: "child_code", label: "Child Code" },
    { key: "item_name", label: "Item Name" },
    { key: "size", label: "Size" },
    { key: "material", label: "Material" },
    { key: "so_qty", label: "SO Qty" },
    { key: "plan_qty", label: "Plan Qty" },
    { key: "part", label: "Part" },
    { key: "dia", label: "Dia" },
    { key: "length", label: "Length" },
    { key: "wip_status", label: "WIP" },
    { key: "total_days", label: "Total Days" },
    { key: "delivery_date", label: "Delivery" },
  ],
  pm: [
    { key: "model_name", label: "Item Name" },
    { key: "material", label: "Material" },
    { key: "size", label: "Size" },
    ...Array.from({ length: 25 }, (_, i) => ({ key: `p${i + 1}`, label: `P${i + 1}` })),
    { key: "num_operations", label: "Ops" },
  ],
};

function openUploadModal(mode) {
  uploadMode = mode;
  document.getElementById("upload-modal-title").textContent =
    mode === "jc" ? "Upload Job Cards (Excel)" : "Upload Process Master (Excel)";
  resetUpload();
  document.getElementById("upload-modal").classList.add("open");
}

function closeUploadModal() {
  document.getElementById("upload-modal").classList.remove("open");
  resetUpload();
}

function resetUpload() {
  previewRows = [];
  document.getElementById("upload-step-1").style.display = "block";
  document.getElementById("upload-step-2").style.display = "none";
  document.getElementById("upload-filename").textContent = "";
  document.getElementById("upload-file-input").value = "";
  document.getElementById("upload-summary").innerHTML = "";
  document.getElementById("upload-preview-head").innerHTML = "";
  document.getElementById("upload-preview-body").innerHTML = "";
}

async function handleFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;
  document.getElementById("upload-filename").textContent = file.name;

  const formData = new FormData();
  formData.append("file", file);

  const endpoint = uploadMode === "jc"
    ? "/api/job_card/upload_preview"
    : "/api/process_master/upload_preview";

  try {
    showToast("Reading file...", "success");
    const res = await fetch(endpoint, { method: "POST", body: formData });
    const data = await res.json();

    if (!data.success) { showToast(data.error, "error"); return; }

    previewRows = data.preview;
    showPreview(data);
  } catch (e) {
    showToast("Error reading file: " + e.message, "error");
  }
}

function showPreview(data) {
  document.getElementById("upload-step-1").style.display = "none";
  document.getElementById("upload-step-2").style.display = "block";

  // Summary
  document.getElementById("upload-summary").innerHTML = `
    <span style="color:var(--success)">✅ ${data.new_count} new records</span>
    &nbsp;&nbsp;
    <span style="color:#92400e">🟡 ${data.dup_count} duplicates (will be updated)</span>
    &nbsp;&nbsp;
    <span style="color:var(--muted)">Total: ${data.preview.length} rows</span>
  `;

  // Table header
  const cols = UPLOAD_COLS[uploadMode];
  document.getElementById("upload-preview-head").innerHTML =
    `<tr style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">
      <th style="padding:8px 10px;text-align:left;font-weight:700;border-right:1px solid rgba(255,255,255,0.15)">Status</th>
      ${cols.map(c => `<th style="padding:8px 10px;text-align:left;font-weight:700;border-right:1px solid rgba(255,255,255,0.15)">${c.label}</th>`).join("")}
    </tr>`;

  // Table body
  document.getElementById("upload-preview-body").innerHTML = data.preview.map(row => {
    const bg = row.is_duplicate ? "#fffbeb" : "#ffffff";
    const status = row.is_duplicate
      ? `<span style="background:#fde68a;color:#92400e;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">UPDATE</span>`
      : `<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">NEW</span>`;
    const cells = cols.map(c =>
      `<td style="padding:7px 10px;border-bottom:1px solid #f3f4f6;border-right:1px solid #f3f4f6;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
           title="${row[c.key] || ''}">${row[c.key] || ""}</td>`
    ).join("");
    return `<tr style="background:${bg};">
      <td style="padding:7px 10px;border-bottom:1px solid #f3f4f6;border-right:1px solid #f3f4f6;">${status}</td>
      ${cells}
    </tr>`;
  }).join("");
}

async function confirmUpload() {
  if (!previewRows.length) return;

  const btn = document.getElementById("confirm-upload-btn");
  btn.textContent = "Saving...";
  btn.disabled = true;

  const endpoint = uploadMode === "jc"
    ? "/api/job_card/upload_confirm"
    : "/api/process_master/upload_confirm";

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows: previewRows })
    });
    const data = await res.json();

    if (data.success) {
      showToast(data.message, "success");
      closeUploadModal();
      // Reload table if on page 2
      if (typeof loadRecords === "function") loadRecords();
    } else {
      showToast(data.error, "error");
    }
  } catch (e) {
    showToast("Error saving: " + e.message, "error");
  } finally {
    btn.textContent = "Confirm Import";
    btn.disabled = false;
  }
}