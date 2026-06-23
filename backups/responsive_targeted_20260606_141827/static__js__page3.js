let currentData = null;
let pendingChange = null;

// ── Fetch job card ────────────────────────────────────────────────────────────
async function fetchJobCard() {
  const jcNo = document.getElementById("jc-input").value.trim();
  if (!jcNo) { showToast("Please enter a Job Card number", "error"); return; }
  try {
    const res = await fetch(`/api/quality_check/fetch/${encodeURIComponent(jcNo)}`);
    const data = await res.json();
    if (!data.success) { showToast(data.error, "error"); return; }
    currentData = data;
    renderResults(data);
  } catch (e) { showToast("Server error. Is Flask running?", "error"); }
}

// ── Pill state ────────────────────────────────────────────────────────────────
function getPillState(pIdx, wipIdx, wipStatus) {
  const s = (wipStatus || "pending").toLowerCase();
  if (s === "pending") return "pending";
  if (wipIdx === -1) return "completed";
  if (pIdx < wipIdx) return "completed";
  if (pIdx === wipIdx) return "current";
  return "pending";
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(data) {
  document.getElementById("placeholder").style.display = "none";
  document.getElementById("results-section").style.display = "block";

  const jc = data.job_card;
  document.getElementById("jc-info-bar").innerHTML = `
    <div class="jc-field"><label>Job Card No</label><div class="val">${jc.job_card_no}</div></div>
    <div class="jc-field"><label>SO No</label><div class="val">${jc.so_no || "-"}</div></div>
    <div class="jc-field"><label>SO Date</label><div class="val">${jc.so_date || "-"}</div></div>
    <div class="jc-field"><label>Job Card Date</label><div class="val">${jc.job_card_date || "-"}</div></div>
    <div class="jc-field"><label>Final Status</label><div class="val">${jc.final_status || "-"}</div></div>
    <div class="jc-field"><label>ERP Status</label><div class="val">${jc.erp_status || "-"}</div></div>
  `;

  const container = document.getElementById("items-container");
  container.innerHTML = "";

  data.items.forEach((item, iIdx) => {
    const wipLower = (item.wip_status || "pending").toLowerCase();
    const wipClass = wipLower === "pending" ? "pending" : wipLower === "store" ? "store" : "";
    const wipIdx = item.wip_process_index ?? -1;

    // Build subcontract lookup: process_name_lower → vendor_name
    const subcontractMap = {};
    if (item.process_timeline) {
      item.process_timeline.forEach(t => {
        if (t.is_subcontract === 1 || t.is_subcontract === true) {
          subcontractMap[t.process_name.trim().toLowerCase()] = t.vendor_name || "";
        }
      });
    }

    // Build pills — ALL pills are clickable (for backtracking)
    const procPills = item.processes.map((proc, pIdx) => {
      const procKey = proc.trim().toLowerCase();
      const isSubcontract = subcontractMap.hasOwnProperty(procKey);
      let state = getPillState(pIdx, wipIdx, item.wip_status);
      if (isSubcontract && state === "current") state = "subcontract";

      const vendor = isSubcontract ? subcontractMap[procKey] : "";
      const checkmark = state === "completed" ? '<span class="pill-check">&#10003;</span>' : "";
      const pulseDot = state === "current" ? '<span class="pill-dot"></span>' : "";
      const truckIcon = state === "subcontract" ? '<i class="fa fa-truck" style="font-size:10px;margin-right:3px"></i>' : "";
      const vendorLabel = vendor ? `<br><span style="font-size:9px;opacity:0.85;">${vendor}</span>` : "";

      return `
        <div class="proc-pill-v2 pill-${state}"
             data-iidx="${iIdx}"
             data-jcno="${encodeURIComponent(jc.job_card_no)}"
             data-item="${encodeURIComponent(item.item_name)}"
             data-process="${encodeURIComponent(proc)}"
             data-pidx="${pIdx}"
             data-subcontract="${isSubcontract ? '1' : '0'}"
             title="${proc}${vendor ? ' — ' + vendor : ''}"
             onclick="openStageModal(this)">
          ${pulseDot}${truckIcon}
          <span class="pill-num">P${pIdx + 1}</span>
          <span class="pill-name">${proc}${vendorLabel}</span>
          ${checkmark}
        </div>`;
    }).join("");

    const section = document.createElement("div");
    section.className = "item-section";
    section.dataset.iidx = iIdx;
    section.innerHTML = `
      <div class="item-header">
        <div class="item-name">${item.item_name}</div>
        <div class="item-meta">
          <span class="meta-pill">Material: ${item.material || "-"}</span>
          <span class="meta-pill">Planned Qty: ${item.so_qty || item.job_card_qty || "-"}</span>
          ${item.part ? `<span class="meta-pill">Part: ${item.part}</span>` : ""}
          ${item.dia ? `<span class="meta-pill">Dia: ${item.dia}</span>` : ""}
          ${item.length ? `<span class="meta-pill">Length: ${item.length}</span>` : ""}
          <span class="meta-pill">${item.processes.length} Processes</span>
          ${item.wip_stage_days ? `<span class="meta-pill">WIP Days: ${item.wip_stage_days}</span>` : ""}
          ${item.total_days ? `<span class="meta-pill">Total Days: ${item.total_days}</span>` : ""}
          <span class="meta-pill remaining-pill" id="remaining-${iIdx}">
            Remaining: ${item.remaining_days || 0} days
          </span>
          ${item.delivery_date ? `<span class="meta-pill">Delivery: ${item.delivery_date}</span>` : ""}
        </div>
      </div>
      <div class="wip-bar">
        <span class="wip-label">Current WIP Stage</span>
        <span class="wip-badge ${wipClass}" id="wip-badge-${iIdx}">${item.wip_status || "Pending"}</span>
        ${item.wip_stage_days ? `<span style="font-size:12px;color:var(--muted);font-weight:500">${item.wip_stage_days} days in this stage</span>` : ""}
      </div>
      <div class="actual-qty-row">
        <label>Planned Qty</label>
        <div class="qty-badge">${item.so_qty || item.job_card_qty || "-"}</div>
        <label style="margin-left:12px">Actual Qty *</label>
        <input type="number" id="actual_${iIdx}" placeholder="Enter actual qty"
               min="0" value="${item.actual_qty || ""}">
      </div>
      ${item.processes.length > 0 ? `
        <div class="process-pills-section">
          <div class="pills-section-label">
            Process Stages — click a pill to change stage
          </div>
          <div class="process-pills-v2">${procPills}</div>
        </div>
      ` : `
        <div style="padding:14px 20px;color:var(--muted);font-size:13px;
                    border-bottom:1px solid var(--border);font-weight:500">
          No processes defined — please update Process Master.
        </div>
      `}
      <div class="item-row-section">
        <div class="row-label">Quality Result</div>
        <div class="radio-group">
          <label class="radio-label ok">
            <input type="radio" name="qr_${iIdx}" value="OK"> OK
          </label>
          <label class="radio-label notok">
            <input type="radio" name="qr_${iIdx}" value="NOT OK"> Not OK
          </label>
        </div>
      </div>
      <div class="remarks-row last">
        <label style="font-size:13px;font-weight:600;color:#374151;
                      white-space:nowrap;min-width:140px;flex-shrink:0;">
          Remarks
        </label>
        <textarea id="remarks_${iIdx}" class="remarks-textarea"
                  placeholder="Add or update remarks...">${item.remarks || ""}</textarea>
      </div>
    `;
    container.appendChild(section);
  });

  const supOptions = data.supervisors.map(s =>
    `<option value="${s}">${s}</option>`).join("");
  document.getElementById("bottom-supervisor").innerHTML =
    `<option value="">-- Select Supervisor --</option>${supOptions}`;
  document.getElementById("submit-info").textContent =
    `${data.items.length} item(s) loaded — select supervisor and submit`;
}

// ── Open modal ────────────────────────────────────────────────────────────────
function openStageModal(pillEl) {
  const clickedProc = decodeURIComponent(pillEl.dataset.process);
  const clickedPIdx = parseInt(pillEl.dataset.pidx);
  const iIdx = parseInt(pillEl.dataset.iidx);
  const jcNo = decodeURIComponent(pillEl.dataset.jcno);
  const itemName = decodeURIComponent(pillEl.dataset.item);
  const isSubcontract = pillEl.dataset.subcontract === "1";

  // Get current WIP from rendered badge
  const wipBadge = document.getElementById(`wip-badge-${iIdx}`);
  const currentWIP = wipBadge ? wipBadge.textContent.trim() : "Pending";

  // Store pending
  pendingChange = {
    iIdx, jcNo, itemName,
    currentStage: currentWIP,
    newStage: clickedProc,
    isSubcontract,
  };

  // Always show same modal layout
  // "Current process" = current WIP (what will be completed)
  // "Move to" = clicked pill (next stage)
  document.getElementById("modal-current-process").textContent = currentWIP;
  document.getElementById("modal-next-process").textContent = clickedProc;

  // If yellow pill (subcontract) — hide subcontract checkbox, show complete message
  document.getElementById("modal-title").textContent = "Change Stage?";
  document.getElementById("modal-note").textContent = "Supervisor must be selected at the bottom before confirming.";
  document.getElementById("subcontract-section").style.display = "block";
  document.getElementById("modal-confirm-btn").textContent = "Confirm";
  document.getElementById("modal-confirm-btn").style.background = "";
  document.getElementById("subcontract-checkbox").checked = false;
  document.getElementById("vendor-row").style.display = "none";
  document.getElementById("modal-vendor-name").value = "";

  document.getElementById("stage-modal").classList.add("open");
}

function closeStageModal() {
  document.getElementById("stage-modal").classList.remove("open");
  pendingChange = null;
}

function toggleSubcontractVendor(checked) {
  document.getElementById("vendor-row").style.display = checked ? "block" : "none";
}

// ── Confirm ───────────────────────────────────────────────────────────────────
async function confirmStageChange() {
  if (!pendingChange) return;
  const { jcNo, itemName, currentStage, newStage, isSubcontract } = pendingChange;
  const supervisor = document.getElementById("bottom-supervisor").value || "Not Assigned";

  // Case 1 — Complete subcontracting (yellow pill was clicked)
  if (isSubcontract) {
    try {
      const res = await fetch("/api/wip/subcontract_complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo,
          item_name: itemName,
          process: newStage,
          changed_by: supervisor,
        })
      });
      const data = await res.json();
      if (data.success) {
        closeStageModal();
        showToast(data.message, "success");
        fetchJobCard();
      } else showToast(data.error || "Failed", "error");
    } catch (e) { showToast("Server error", "error"); }
    return;
  }

  // Case 2 — Send to subcontracting (checkbox ticked)
  const sendToSubcontract = document.getElementById("subcontract-checkbox").checked;
  const vendorName = document.getElementById("modal-vendor-name").value.trim();

  if (sendToSubcontract) {
    if (!vendorName) {
      showToast("Please enter vendor name for subcontracting", "error");
      return;
    }
    try {
      const res = await fetch("/api/wip/subcontract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo,
          item_name: itemName,
          process: newStage,
          vendor_name: vendorName,
          changed_by: supervisor,
        })
      });
      const data = await res.json();
      if (data.success) {
        closeStageModal();
        showToast(`${newStage} sent to subcontracting — ${vendorName}`, "success");
        fetchJobCard();
      } else showToast(data.error || "Failed", "error");
    } catch (e) { showToast("Server error", "error"); }
    return;
  }

  // Case 3 — Normal stage change
  try {
    const res = await fetch("/api/wip/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_card_no: jcNo,
        item_name: itemName,
        new_stage: newStage,
        changed_by: supervisor,
      })
    });
    const data = await res.json();
    if (data.success) {
      closeStageModal();
      showToast(`Stage changed to ${newStage}`, "success");
      fetchJobCard();
    } else showToast(data.error || "Update failed", "error");
  } catch (e) { showToast("Server error — is Flask running?", "error"); }
}

// Close on overlay click
document.addEventListener("click", function (e) {
  const modal = document.getElementById("stage-modal");
  if (modal && e.target === modal) closeStageModal();
});

// ── Submit quality check ──────────────────────────────────────────────────────
async function submitQualityCheck() {
  if (!currentData) return;
  const supervisor = document.getElementById("bottom-supervisor").value;
  if (!supervisor) { showToast("Select supervisor before submitting", "error"); return; }

  const details = [];
  let valid = true;

  currentData.items.forEach((item, iIdx) => {
    if (!valid) return;
    const actualQty = parseInt(document.getElementById(`actual_${iIdx}`)?.value);
    if (!actualQty && actualQty !== 0) {
      valid = false; showToast(`Enter actual qty for: ${item.item_name}`, "error"); return;
    }
    const qr = Array.from(document.querySelectorAll(`input[name="qr_${iIdx}"]`))
      .find(r => r.checked);
    if (!qr) {
      valid = false; showToast(`Select quality result for: ${item.item_name}`, "error"); return;
    }
    details.push({
      item_name: item.item_name,
      actual_qty: actualQty,
      completed_process: item.wip_status || "",
      quality_result: qr.value,
      supervisor,
      remarks: document.getElementById(`remarks_${iIdx}`)?.value.trim() || "",
    });
  });
  if (!valid) return;

  try {
    const res = await fetch("/api/quality_check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_card_no: currentData.job_card.job_card_no, details })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      document.getElementById("results-section").style.display = "none";
      document.getElementById("placeholder").style.display = "block";
      document.getElementById("jc-input").value = "";
      currentData = null;
    } else showToast(data.error, "error");
  } catch (e) { showToast("Server error", "error"); }
}

// ── Init ──────────────────────────────────────────────────────────────────────
(function () {
  const jcNo = sessionStorage.getItem("prefillJC");
  if (jcNo) {
    sessionStorage.removeItem("prefillJC");
    document.getElementById("jc-input").value = jcNo;
    fetchJobCard();
  }
})();

const urlParams = new URLSearchParams(window.location.search);
const jcFromUrl = urlParams.get("jc");
if (jcFromUrl) {
  document.getElementById("jc-input").value = jcFromUrl;
  fetchJobCard();
}