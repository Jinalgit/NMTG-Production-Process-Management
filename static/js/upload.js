// Upload logic shared by Page 1 (Job Cards) and Page 2 (Process Master).
let uploadMode = ""; // "jc" or "pm"
let previewRows = [];
let jcReviewToken = null; // review token from upload_preview; null for PM uploads
let uploadFakeProgressTimer = null;
let uploadCurrentProgress = 0;

const UPLOAD_COLS = {
  jc: [
    { key: "source_file", label: "Source File" },
    { key: "job_card_no", label: "JC No" },
    { key: "so_no", label: "SO No" },
    { key: "customer_name", label: "Customer" },
    { key: "parent_code", label: "Parent Code" },
    { key: "match_status", label: "Match" },
    { key: "warning", label: "Warning" },
    { key: "so_date", label: "SO Date" },
    { key: "job_card_date", label: "Job Date" },
    { key: "work_order_no", label: "WO No" },
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
  if (mode === "jc") {
    setTimeout(() => {
      fetch("/api/so_mapping/status")
        .then(r => r.json())
        .then(data => {
          const el = document.getElementById("so-mapping-status");
          if (!el) return;
          if (data.success && data.last_updated) {
            el.innerHTML = `✅ SO mapping last updated: <strong>${data.last_updated}</strong> &nbsp;·&nbsp; ${data.total_rows} SOs loaded`;
            el.style.color = "#16a34a";
          } else {
            el.innerHTML = `⚠️ No SO mapping loaded yet — upload 222-type file to enable customer & parent code auto-fill`;
            el.style.color = "#f59e0b";
          }
        })
        .catch(() => {
          const el = document.getElementById("so-mapping-status");
          if (el) el.style.display = "none";
        });
    }, 100);
  }
  document.getElementById("upload-modal").classList.add("open");
}

function closeUploadModal() {
  document.getElementById("upload-modal").classList.remove("open");
  resetUpload();
}

function resetUpload() {
  previewRows = [];
  jcReviewToken = null;
  document.getElementById("upload-step-1").style.display = "block";
  document.getElementById("upload-step-2").style.display = "none";
  document.getElementById("upload-filename").textContent = "";
  document.getElementById("upload-file-input").value = "";
  document.getElementById("upload-summary").innerHTML = "";
  document.getElementById("upload-preview-head").innerHTML = "";
  document.getElementById("upload-preview-body").innerHTML = "";
}

function escapeUploadCell(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function clampUploadPercent(percent) {
  const value = Number(percent);
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function setUploadProgress(percent) {
  uploadCurrentProgress = clampUploadPercent(percent);

  const percentEl = document.getElementById("upload-loading-percent");
  const barFill = document.querySelector(".upload-loading-bar-fill");

  if (percentEl) percentEl.textContent = `${uploadCurrentProgress}%`;
  if (barFill) barFill.style.width = `${uploadCurrentProgress}%`;
}

function startFakeUploadProgress(startPercent, maxPercent) {
  stopFakeUploadProgress();

  const max = clampUploadPercent(maxPercent);
  setUploadProgress(startPercent);

  uploadFakeProgressTimer = window.setInterval(() => {
    if (uploadCurrentProgress >= max) {
      stopFakeUploadProgress();
      return;
    }

    const remaining = max - uploadCurrentProgress;
    const increment = remaining > 20 ? 3 : remaining > 8 ? 2 : 1;
    setUploadProgress(Math.min(max, uploadCurrentProgress + increment));
  }, 650);
}

function stopFakeUploadProgress(finalPercent) {
  if (uploadFakeProgressTimer) {
    window.clearInterval(uploadFakeProgressTimer);
    uploadFakeProgressTimer = null;
  }

  if (finalPercent !== undefined) {
    setUploadProgress(finalPercent);
  }
}

function waitForUploadLoading(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function showUploadLoading(title, message, percent = 5) {
  const overlay = document.getElementById("upload-loading-overlay");
  const titleEl = document.getElementById("upload-loading-title");
  const messageEl = document.getElementById("upload-loading-message");

  if (titleEl) titleEl.textContent = title || "Uploading Job Cards...";
  if (messageEl) {
    messageEl.textContent = message || "Please wait while system reads and validates your files.";
  }
  setUploadProgress(percent);
  if (overlay) overlay.classList.add("show");
}

function updateUploadLoading(title, message, percent) {
  const titleEl = document.getElementById("upload-loading-title");
  const messageEl = document.getElementById("upload-loading-message");

  if (titleEl && title) titleEl.textContent = title;
  if (messageEl && message) messageEl.textContent = message;
  if (percent !== undefined) setUploadProgress(percent);
}

function hideUploadLoading() {
  stopFakeUploadProgress();
  const overlay = document.getElementById("upload-loading-overlay");
  if (overlay) overlay.classList.remove("show");
}

async function handleFileSelect(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;

  document.getElementById("upload-filename").textContent =
    files.length === 1 ? files[0].name : `${files.length} files selected`;

  previewRows = [];

  try {
    if (uploadMode === "jc") {
      showUploadLoading(
        "Uploading Job Cards...",
        "Please wait while system reads and validates your files.",
        5
      );
      updateUploadLoading(
        "Uploading Job Cards...",
        "Please wait while system reads and validates your files.",
        20
      );
      startFakeUploadProgress(20, 45);
    }

    showToast(`Reading ${files.length} file(s)...`, "success");

    if (uploadMode === "jc") {
      const formData = new FormData();
      files.forEach((file) => formData.append("files", file));
      formData.append("file", files[0]);

      updateUploadLoading(
        "Uploading Job Cards...",
        "Please wait while system reads and validates your files.",
        45
      );
      startFakeUploadProgress(45, 70);

      const res = await fetch("/api/job_card/upload_preview", {
        method: "POST",
        body: formData,
      });
      updateUploadLoading(
        "Preparing Preview...",
        "System is preparing preview rows. Please wait.",
        70
      );
      stopFakeUploadProgress(90);
      const data = await res.json();

      if (!data.success) {
        showToast(data.error || "Upload preview failed", "error");
        return;
      }

      // SO mapping only — show success popup
      updateUploadLoading(
        "Preparing Preview...",
        "System is preparing preview rows. Please wait.",
        90
      );

      if (data.so_mapping_only) {
        stopFakeUploadProgress(100);
        await waitForUploadLoading(400);
        hideUploadLoading();
        showSoMappingSuccessPopup(data.so_count, data.message);
        return;
      }

      jcReviewToken = data.review_token || null;
      previewRows = data.preview || [];
      // Open review page only when manual review is required.
      const hasBlockedRows = previewRows.some(function (row) {
        return ![
          'MATCH',
          'REUSED_APPROVAL',
          'DUPLICATE'
        ].includes(row.review_status);
      });

      if (jcReviewToken && hasBlockedRows) {
        const redirectToken = jcReviewToken;
        const rowsForReview = previewRows.slice();

        stopFakeUploadProgress(100);
        await waitForUploadLoading(400);
        hideUploadLoading();

        sessionStorage.setItem(
          "jms_preview_rows_" + redirectToken,
          JSON.stringify(rowsForReview)
        );

        closeUploadModal();

        showToast(
          "Job Cards uploaded. Redirecting to review...",
          "info"
        );

        window.setTimeout(function () {
          window.location.href =
            "/jc_review?token=" + encodeURIComponent(redirectToken);
        }, 500);

        return;
      }

      showPreview({

        preview: previewRows,
        new_count: Number(data.new_count || 0),
        dup_count: Number(data.dup_count || 0),
      });
      stopFakeUploadProgress(100);
      await waitForUploadLoading(400);
      return;
    }

    let totalNew = 0;
    let totalDup = 0;
    let allPreview = [];

    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/bom/upload_preview", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (!data.success) {
        showToast(`${file.name}: ${data.error}`, "error");
        return;
      }

      allPreview = allPreview.concat((data.preview || []).map((row) => ({
        ...row,
        source_file: file.name,
      })));
      totalNew += Number(data.new_count || 0);
      totalDup += Number(data.dup_count || 0);
    }

    previewRows = allPreview;
    showPreview({
      preview: allPreview,
      new_count: totalNew,
      dup_count: totalDup,
    });
  } catch (e) {
    showToast("Error reading file: " + e.message, "error");
  } finally {
    hideUploadLoading();
  }
}

function showPreview(data) {
  document.getElementById("upload-step-1").style.display = "none";
  document.getElementById("upload-step-2").style.display = "block";

  document.getElementById("upload-summary").innerHTML = `
    <span style="color:var(--success)">${data.new_count} new records</span>
    &nbsp;&nbsp;
    <span style="color:#92400e">${data.dup_count} duplicates (will be updated)</span>
    &nbsp;&nbsp;
    <span style="color:var(--muted)">Total: ${data.preview.length} rows</span>
  `;

  const cols = UPLOAD_COLS[uploadMode] || [];
  document.getElementById("upload-preview-head").innerHTML =
    `<tr style="font-size:11px;text-transform:uppercase;letter-spacing:0.5px;">
      <th style="padding:8px 10px;text-align:left;font-weight:700;border-right:1px solid rgba(255,255,255,0.15)">Status</th>
      ${cols.map((c) => `<th style="padding:8px 10px;text-align:left;font-weight:700;border-right:1px solid rgba(255,255,255,0.15)">${c.label}</th>`).join("")}
    </tr>`;

  document.getElementById("upload-preview-body").innerHTML = data.preview.map((row) => {
    const bg = row.is_duplicate ? "#fffbeb" : "#ffffff";
    const status = row.is_duplicate
      ? `<span style="background:#fde68a;color:#92400e;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">UPDATE</span>`
      : `<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;">NEW</span>`;
    const cells = cols.map((c) =>
      `<td style="padding:7px 10px;border-bottom:1px solid #f3f4f6;border-right:1px solid #f3f4f6;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
           title="${escapeUploadCell(row[c.key] || "")}">${escapeUploadCell(row[c.key] || "")}</td>`
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
    : "/api/bom/upload_confirm";

  try {
    if (uploadMode === "jc") {
      showUploadLoading(
        "Saving Job Cards...",
        "System is inserting/updating job cards, items, process timeline and process master.",
        5
      );
      updateUploadLoading(
        "Saving Job Cards...",
        "System is sending job card data for import.",
        30
      );
      startFakeUploadProgress(30, 60);
      updateUploadLoading(
        "Saving Job Cards...",
        "System is inserting/updating job cards and items.",
        60
      );
      startFakeUploadProgress(60, 85);
    }

    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        uploadMode === "jc"
          ? { review_token: jcReviewToken, rows: previewRows }
          : { rows: previewRows }
      ),
    });
    if (uploadMode === "jc") {
      updateUploadLoading(
        "Saving Job Cards...",
        "System is creating process timeline and process master.",
        85
      );
    }
    const data = await res.json();

    if (data.success) {
      if (uploadMode === "jc") {
        stopFakeUploadProgress(100);
        await waitForUploadLoading(400);
      }
      showToast(data.message, "success");
      closeUploadModal();
      if (typeof loadRecords === "function") loadRecords();
    } else {
      showToast(data.error, "error");
    }
  } catch (e) {
    showToast("Error saving: " + e.message, "error");
  } finally {
    hideUploadLoading();
    btn.textContent = "Confirm Import";
    btn.disabled = false;
  }
}

// ── SO Mapping Success Popup ──────────────────────────────────────────────────
function showSoMappingSuccessPopup(count, message) {
  const existing = document.getElementById("so-mapping-popup");
  if (existing) existing.remove();

  const popup = document.createElement("div");
  popup.id = "so-mapping-popup";
  popup.style.cssText = `
    position:fixed; inset:0; background:rgba(0,0,0,0.45);
    z-index:9999; display:flex; align-items:center; justify-content:center;
  `;
  popup.innerHTML = `
    <div style="background:#fff; border-radius:10px; width:90vw; max-width:480px;
                box-shadow:0 8px 40px rgba(0,0,0,0.18); overflow:hidden;">
      <div style="background:#16a34a; padding:20px 24px;">
        <div style="display:flex; align-items:center; gap:12px;">
          <i class="fa fa-check-circle" style="color:#fff; font-size:28px;"></i>
          <div>
            <div style="color:#fff; font-size:16px; font-weight:700;">SO Mapping Loaded</div>
            <div style="color:rgba(255,255,255,0.85); font-size:12px; margin-top:2px;">${count} SO records ready</div>
          </div>
        </div>
      </div>
      <div style="padding:20px 24px;">
        <div style="font-size:13px; color:#374151; margin-bottom:20px; line-height:1.6;">
          ${message}<br><br>
          Customer names and parent codes will now auto-fill when uploading job cards.
        </div>
        <div style="display:flex; gap:10px; justify-content:flex-end;">
          <button onclick="document.getElementById('so-mapping-popup').remove(); closeUploadModal();"
            style="padding:8px 16px; background:#f3f4f6; border:1px solid #d1d5db;
                   border-radius:6px; font-size:13px; cursor:pointer; font-family:'IBM Plex Sans',sans-serif;">
            Close
          </button>
          <button onclick="document.getElementById('so-mapping-popup').remove(); triggerJobCardFileSelect();"
            style="padding:8px 18px; background:var(--accent); color:#fff; border:none;
                   border-radius:6px; font-size:13px; font-weight:600; cursor:pointer; font-family:'IBM Plex Sans',sans-serif;">
            <i class="fa fa-upload"></i> Upload Job Cards Now
          </button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(popup);
}

function triggerJobCardFileSelect() {
  const input = document.getElementById("upload-file-input");
  if (input) {
    input.value = "";
    input.click();
  }
}

window.openUploadModal = openUploadModal;
window.closeUploadModal = closeUploadModal;
window.resetUpload = resetUpload;
window.handleFileSelect = handleFileSelect;
window.confirmUpload = confirmUpload;
window.setUploadProgress = setUploadProgress;
window.showUploadLoading = showUploadLoading;
window.updateUploadLoading = updateUploadLoading;
window.hideUploadLoading = hideUploadLoading;
window.startFakeUploadProgress = startFakeUploadProgress;
window.stopFakeUploadProgress = stopFakeUploadProgress;
window.showSoMappingSuccessPopup = showSoMappingSuccessPopup;
window.triggerJobCardFileSelect = triggerJobCardFileSelect;