let currentData = null;
let pendingChange = null;

const IS_GAURANG_SPECIAL = window.JMS_IS_GAURANG_SPECIAL === true || window.JMS_IS_GAURANG_SPECIAL === "true";
const IS_OPERATOR_READ_ONLY = window.JMS_USER_ROLE === "operator" && !IS_GAURANG_SPECIAL;

function canEditProcess(processName) {
  if (IS_GAURANG_SPECIAL) return true;
  if (window.JMS_USER_ROLE === "admin") return true;
  if (window.JMS_USER_ROLE !== "supervisor") return false;
  if (!Array.isArray(window.myAccessibleProcesses)) return false;
  const current = String(processName || "").trim().toLowerCase();
  return window.myAccessibleProcesses.some(p => String(p || "").trim().toLowerCase() === current);
}

// ── Fetch job card ────────────────────────────────────────────────────────────
async function fetchJobCard() {
  const jcNo = document.getElementById("jc-input").value.trim();
  window.history.replaceState({}, "", "/page3");
  if (!jcNo) { showToast("Please enter a Job Card number", "error"); return; }
  // Hide operator grid when searching
  if (IS_OPERATOR_READ_ONLY) {
    const ov = document.getElementById("operator-view");
    if (ov) ov.style.display = "none";
  }
  document.getElementById("placeholder").style.display = "none";
  document.getElementById("results-section").style.display = "block";

  document.getElementById("items-container").innerHTML = renderCardSkeleton(2);
  try {
    const res = await fetch(`/api/quality_check/fetch/${encodeURIComponent(jcNo)}`);
    const data = await res.json();
    if (!data.success) {
      showToast(data.error, "error");
      document.getElementById("results-section").style.display = "none";
      document.getElementById("placeholder").style.display = "block";
      return;
    }
    currentData = data;

    // OPERATOR_SEARCH_DIRECT_QUEUE_V2
    if (IS_OPERATOR_READ_ONLY) {
      if (!Array.isArray(operatorCards) || operatorCards.length === 0) {
        await loadOperatorView();
      }

      const actualJc = String(
        data?.job_card?.job_card_no || jcNo
      ).trim();

      const globalIdx = operatorCards.findIndex(function(card) {
        return String(card?.job_card_no || "").trim() === actualJc;
      });

      document.getElementById("results-section").style.display = "none";

      const ov = document.getElementById("operator-view");
      if (ov) ov.style.display = "block";

      if (globalIdx >= 0) {
        openOperatorCompleteModal(globalIdx);
      } else {
        showToast(
          "This Job Card is not active in your assigned operator queue.",
          "error"
        );
      }

      return;
    }

    window.myAccessibleProcesses = data.my_accessible_processes; // null = admin / unrestricted
    renderResults(data);
    // Kanban view disabled on Page 3.
    // loadPage3KanbanSummary();
  } catch (e) {
    showToast("Server error. Is Flask running?", "error");
  }
}

function calcRemainingDays(deliveryDate) {
  if (!deliveryDate) return 0;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const delivery = new Date(deliveryDate + "T00:00:00");
  return Math.ceil((delivery - today) / (1000 * 60 * 60 * 24));
}

// ── Pill state ────────────────────────────────────────────────────────────────
function getPillState(pIdx, wipIdx, wipStatus) {
  const s = String(wipStatus || "pending").trim().toLowerCase();

  if (s === "pending") return "pending";

  // Only genuinely finished items should show every pill completed.
  if (s === "store" || s === "completed" || s === "complete") {
    return "completed";
  }

  // Missing WIP from the route is a data mismatch, not completion.
  if (wipIdx === -1) return "pending";

  if (pIdx < wipIdx) return "completed";
  if (pIdx === wipIdx) return "current";
  return "pending";
}

function calcRemainingDays(deliveryDate) {
  if (!deliveryDate) return 0;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const delivery = new Date(deliveryDate + "T00:00:00");
  return Math.ceil((delivery - today) / (1000 * 60 * 60 * 24));
}

function isStoreProcess(name) {
  return String(name || "").trim().toLowerCase() === "store";
}

function isItemInStore(item) {
  return isStoreProcess(item?.wip_status);
}

function showStoreMessage() {
  showToast("This item is in Store.", "info");
}

function isTimelineCompleted(t) {
  const status = String(t?.status || "").trim().toLowerCase();
  return Boolean(t?.out_time) || status === "on time" || status === "completed" || status === "delayed";
}

function isTimelineOverdue(t) {
  if (!t) return false;
  const status = String(t.status || "").trim().toLowerCase();
  if (status === "delayed") return true;

  let actualDays = Number(t.actual_days);
  if (Number.isNaN(actualDays) && t.in_time) {
    actualDays = calculateTimelineDaysTaken(t.in_time, t.out_time);
  }
  const leadDays = Number(t.lead_days);
  if (!Number.isNaN(actualDays) && !Number.isNaN(leadDays) && leadDays >= 0 && actualDays > leadDays) {
    return true;
  }

  const leadDate = parseTimelineDay(t.lead_date);
  if (!isTimelineCompleted(t) && leadDate) {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return today > leadDate;
  }
  return false;
}

function calculateRejectedQty(plannedQty, actualQty) {
  const planned = parseInt(plannedQty, 10);
  const actual = parseInt(actualQty, 10);
  if (Number.isNaN(planned) || Number.isNaN(actual)) return "-";
  return actual < planned ? planned - actual : "-";
}

function getRejectedQtyClass(value) {
  return value !== "-" ? " rejected-qty-alert" : "";
}

function updateRejectedQty(iIdx) {
  const item = currentData?.items?.[iIdx];
  if (!item) return;
  const plannedQty = item.so_qty ?? item.job_card_qty ?? "";
  const actualQty = document.getElementById(`actual_${iIdx}`)?.value || item.actual_qty || item.so_qty || "";
  const rejectedQty = calculateRejectedQty(plannedQty, actualQty);
  const rejectedEl = document.getElementById(`rejected_${iIdx}`);
  if (!rejectedEl) return;
  rejectedEl.textContent = rejectedQty;
  rejectedEl.classList.toggle("rejected-qty-alert", rejectedQty !== "-");
}

function validateMainActualQty(input, planned) {
  const actual = parseInt(input.value) || 0;
  if (actual > planned) {
    input.value = planned;
    showToast(`Actual qty cannot exceed planned qty (${planned})`, "warning");
  }
}

function getRemainingClass(days) {
  const n = parseInt(days || 0, 10);
  if (n < 0) return "remaining-red";
  if (n <= 7) return "remaining-yellow";
  return "remaining-green";
}

function esc(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(data) {
  document.getElementById("placeholder").style.display = "none";
  document.getElementById("results-section").style.display = "block";

  const jc = data.job_card;
  const advanceStockValues = [...new Set(
    (data.items || [])
      .map(item => String(item.advance_stock || "").trim())
      .filter(Boolean)
  )];
  const advanceStockText = advanceStockValues.length ? advanceStockValues.join(", ") : "-";
  document.getElementById("jc-info-bar").innerHTML = `
    <div class="jc-field"><label>Job Card No</label><div class="val">${jc.job_card_no}</div></div>
    <div class="jc-field"><label>SO No</label><div class="val">${jc.so_no || "-"}</div></div>
    <div class="jc-field"><label>SO Date</label><div class="val">${formatDateForDisplay(jc.so_date) || "-"}</div></div>
    <div class="jc-field"><label>Job Card Date</label><div class="val">${formatDateForDisplay(jc.job_card_date) || "-"}</div></div>
    <div class="jc-field"><label>Advance Stock</label><div class="val">${advanceStockText}</div></div>
    <div class="jc-field"><label>Final Status</label><div class="val">${jc.final_status || "-"}</div></div>
    <div class="jc-field"><label>ERP Status</label><div class="val">${jc.erp_status || "-"}</div></div>
    ${jc.job_card_no === "500"
      ? `<div class="jc-field">
           <button onclick="resetJC500()"
                   style="background:#dc2626;color:#fff;border:none;
                          border-radius:4px;padding:6px 14px;font-size:12px;
                          font-weight:700;cursor:pointer;">
             ⚠ Reset JC 500
           </button>
         </div>`
      : ""}
  `;

  const container = document.getElementById("items-container");
  container.innerHTML = "";

  data.items.forEach((item, iIdx) => {
    const wipLower = (item.wip_status || "pending").toLowerCase();
    const wipClass = wipLower === "pending" ? "pending" : wipLower === "store" ? "store" : "";
    const wipIdx = item.wip_process_index ?? -1;

    const subcontractMap = {};
    if (item.process_timeline) {
      item.process_timeline.forEach(t => {
        if (t.is_subcontract === 1 || t.is_subcontract === true) {
          subcontractMap[t.process_name.trim().toLowerCase()] = {
            vendor: t.vendor_name || "",
            status: t.subcontract_status || "",
            days_remaining: t.subcontract_days_remaining,
            expected_date: t.subcontract_expected_date || "",
            lead_days: t.subcontract_lead_days || 0,
          };
        }
      });
    }

    const procPills = item.processes.map((proc, pIdx) => {
      const procKey = proc.trim().toLowerCase();
      const isStore = isStoreProcess(proc);
      const isSubcontract = Object.prototype.hasOwnProperty.call(subcontractMap, procKey);
      let state = getPillState(pIdx, wipIdx, item.wip_status);
      if (isSubcontract && state !== "completed") state = "subcontract";

      const subInfo = isSubcontract ? subcontractMap[procKey] : null;
      const vendor = subInfo ? subInfo.vendor : "";
      const tl = item.process_timeline
        ? item.process_timeline.find(t => t.process_name.trim().toLowerCase() === procKey)
        : null;
      const isOverdue = isTimelineOverdue(tl);
      if (isStore && (isItemInStore(item) || tl?.in_time || tl?.out_time || tl?.status === "On Time" || tl?.status === "Delayed")) {
        state = "completed";
      }
      const plannedDays = tl ? parseInt(tl.lead_days || 0) : 0;
      const actualDays = tl ? tl.actual_days : null;
      const inTime = tl ? tl.in_time : null;

      let daysSoFar = 0;
      if (inTime) {
        const inDate = new Date(inTime);
        const today = new Date();
        daysSoFar = Math.max(0, Math.floor((today - inDate) / 86400000));
      }

      let daysBadge = "";
      if (state === "completed") {
        const taken = actualDays !== null ? actualDays : daysSoFar;
        if (taken !== null && taken !== undefined) {
          const diff = taken - plannedDays;
          if (taken === 0) daysBadge = `<span class="pill-days pill-days-ontime">0d <i class="fa fa-check" aria-hidden="true"></i></span>`;
          else if (diff > 0) daysBadge = `<span class="pill-days pill-days-delayed">${taken}d <span class="pill-days-tag">+${diff}d late</span></span>`;
          else if (diff < 0) daysBadge = `<span class="pill-days pill-days-early">${taken}d <span class="pill-days-tag">${Math.abs(diff)}d early</span></span>`;
          else daysBadge = `<span class="pill-days pill-days-ontime">${taken}d <i class="fa fa-check" aria-hidden="true"></i></span>`;
        }
      } else if (state === "current") {
        if (plannedDays > 0 && daysSoFar > plannedDays)
          daysBadge = `<span class="pill-days pill-days-delayed">${daysSoFar}d/${plannedDays}d <span class="pill-days-tag">+${daysSoFar - plannedDays}d over</span></span>`;
        else if (plannedDays > 0)
          daysBadge = `<span class="pill-days pill-days-inprogress">${daysSoFar}d / ${plannedDays}d</span>`;
        else
          daysBadge = `<span class="pill-days pill-days-inprogress">${daysSoFar}d so far</span>`;
      } else if (state === "subcontract") {
        let cls = "sub-ontime";
        let txt = "";
        if (inTime && plannedDays > 0) {
          const inDate = new Date(inTime);
          const today = new Date();
          const daysIn = Math.max(0, Math.floor((today - inDate) / 86400000));
          const daysRem = plannedDays - daysIn;
          cls = daysRem > 0 ? "sub-advance" : daysRem === 0 ? "sub-ontime" : "sub-overdue";
          txt = daysRem > 0 ? `${daysRem}d left` : daysRem === 0 ? "due today" : `${Math.abs(daysRem)}d late`;
        }
        const v = vendor ? vendor.split(" ")[0] : "Sub";
        daysBadge = `<span class="pill-days pill-days-sub ${cls}">🚚 ${v} ${txt ? `<span class="pill-days-tag">${txt}</span>` : ""}</span>`;
      } else if (state === "pending" && plannedDays > 0) {
        daysBadge = `<span class="pill-days pill-days-planned">${plannedDays}d</span>`;
      }


      const isStoreFinalClickable = isStore && isItemInStore(item);
      const isClickable = !IS_OPERATOR_READ_ONLY && (
        state === "current" || state === "subcontract" || isStoreFinalClickable
      );
      const canRollback = !IS_OPERATOR_READ_ONLY && (IS_GAURANG_SPECIAL || window.JMS_USER_ROLE === "admin" || window.JMS_USER_ROLE === "supervisor");
      const isRollbackPill = canRollback && state === "completed" && pIdx === wipIdx - 1 && wipIdx > 0;
      const pillExtraClass = state === "completed" ? "pill-done" : state === "pending" ? "pill-locked" : "";
      const pillTitle = isRollbackPill
        ? `↩ Roll back to ${proc}`
        : isStoreFinalClickable
          ? "This item is in Store."
          : state === "pending" ? "Complete previous stages first" : `${proc}${vendor ? " — " + vendor : ""}`;
      const _jsq = (s) => String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      const clickHandler = isRollbackPill
        ? `onclick="openRollbackModal('${_jsq(jc.job_card_no)}', '${_jsq(item.item_name)}', '${_jsq(item.wip_status)}', '${_jsq(proc)}')"`
        : isStoreFinalClickable ? 'onclick="showStoreMessage()"' : 'onclick="openStageModal(this)"';

      return `
        <div class="proc-pill-v2 pill-${state} ${isOverdue ? "pill-overdue" : ""} ${pillExtraClass} ${IS_OPERATOR_READ_ONLY ? "readonly-pill" : ""}" style="${isRollbackPill ? "cursor:pointer;outline:2px dashed #f59e0b;outline-offset:-2px;" : ""}position:relative;" style="${isRollbackPill ? "cursor:pointer;outline:2px dashed #f59e0b;outline-offset:-2px;" : ""}position:relative;" style="${isRollbackPill ? "cursor:pointer;outline:2px dashed #f59e0b;outline-offset:-2px;" : ""}position:relative;"
             data-iidx="${iIdx}" data-jcno="${encodeURIComponent(jc.job_card_no)}"
             data-item="${encodeURIComponent(item.item_name)}" data-process="${encodeURIComponent(proc)}"
             data-pidx="${pIdx}" data-subcontract="${isSubcontract && state !== 'completed' ? "1" : "0"}"
             title="${pillTitle}" ${(isClickable || isRollbackPill) ? clickHandler : ""}>
          <div class="pill-header">
            <span class="pill-num">P${pIdx + 1}</span>
            ${state === "completed" ? '<i class="fa fa-check pill-icon-check"></i>' : ""}
            ${state === "current" ? '<span class="pill-dot"></span>' : ""}
            ${state === "subcontract" ? '<i class="fa fa-truck pill-icon-truck"></i>' : ""}
          </div>
          <div class="pill-body">
            <span class="pill-name">${proc}</span>
            ${daysBadge}
          </div>
          ${IS_GAURANG_SPECIAL ? `
          <button
            onclick="event.stopPropagation(); removeProcess('${_jsq(jc.job_card_no)}', '${_jsq(item.item_name)}', '${_jsq(proc)}')"
            title="Remove this process"
            style="position:absolute; top:4px; right:4px; background:rgba(239,68,68,0.12); border:none;
                   color:#ef4444; border-radius:4px; width:18px; height:18px; font-size:10px;
                   cursor:pointer; display:flex; align-items:center; justify-content:center;
                   line-height:1; padding:0; z-index:10;"
          >✕</button>` : ""}
        </div>`;
    }).join("");

    const plannedQtyValue = item.so_qty || item.job_card_qty || "-";
    const actualQtyValue = item.actual_qty ?? "-";
    const rejectedQtyValue = calculateRejectedQty(plannedQtyValue, actualQtyValue);
    const rejectedQtyClass = getRejectedQtyClass(rejectedQtyValue);
    const canEditCurrentProcess = !IS_OPERATOR_READ_ONLY && canEditProcess(item.wip_status);

    const readOnlyQtyRow = `
      <div class="actual-qty-row">
        <label>Planned Qty</label>
        <div class="qty-badge">${plannedQtyValue}</div>
        <label style="margin-left:12px">Actual Qty</label>
        <div class="qty-badge">${actualQtyValue}</div>
      </div>`;

    const editableQtyRow = `
      <div class="actual-qty-row">
        <label>Planned Qty</label>
        <div class="qty-badge">${plannedQtyValue}</div>
        <label style="margin-left:12px">Actual Qty &nbsp;<span style="color:#ef4444;">*</span></label>
        <input type="number" id="actual_${iIdx}" placeholder="Enter actual qty" min="0"
               value="${item.actual_qty ?? ""}" oninput="updateRejectedQty(${iIdx}); validateMainActualQty(this, ${plannedQtyValue})">
      </div>`;

    const readOnlyQualityRows = ``;

    const editableQualityRows = `
      <div class="item-row-section">
        <div class="row-label">Quality Result&nbsp;<span style="color:#ef4444;">*</span></div>
        <div class="radio-group">
          <label class="radio-label ok">
            <input type="radio" name="qr_${iIdx}" value="OK" required>
            <i class="fa fa-thumbs-up" aria-hidden="true"></i> OK
          </label>
          <label class="radio-label notok">
            <input type="radio" name="qr_${iIdx}" value="NOT OK" required>
            <i class="fa fa-thumbs-down" aria-hidden="true"></i> Not OK
          </label>
        </div>
      </div>
      <div class="remarks-row last">
        <label style="font-size:13px;font-weight:600;color:#374151;white-space:nowrap;min-width:140px;flex-shrink:0;">
          Remarks&nbsp;<i class="fa fa-info-circle" aria-hidden="true"></i>
        </label>
        <textarea id="remarks_${iIdx}" class="remarks-textarea"
                  placeholder="Add or update remarks...">${item.remarks || ""}</textarea>
      </div>`;

    const section = document.createElement("div");
    section.className = "item-section";
    section.dataset.iidx = iIdx;
    section.innerHTML = `
      <div class="item-header item-header-clean">
        <div class="item-header-left">
          <div class="item-name">${item.item_name}
  <span onclick="event.stopPropagation(); togglePage3Priority(${Number(item.id) || 0}, '${jc.job_card_no}', '${encodeURIComponent(item.item_name || "")}', ${item.is_priority ? 0 : 1}, this)"
        style="cursor:pointer; margin-left:8px; display:inline-flex; align-items:center; gap:4px; background:${item.is_priority ? '#dc2626' : '#f3f4f6'}; color:${item.is_priority ? '#fff' : '#6b7280'}; font-size:11px; font-weight:700; padding:3px 10px; border-radius:10px; vertical-align:middle; border:1px solid ${item.is_priority ? '#dc2626' : '#d1d5db'};"
        title="Click to ${item.is_priority ? 'remove' : 'mark'} urgent status">
    ${item.is_priority ? '<i class="fa fa-exclamation-triangle" aria-hidden="true"></i> URGENT' : '○ Regular'}
  </span>
</div>
          <div class="item-basic-info">
  <span><strong>Material:</strong> ${item.material || "-"}</span>
  <span><strong>Part:</strong> ${item.part || "-"}</span>
  <span><strong>Parent Code:</strong> ${jc.parent_code || "-"}</span>
  <span><strong>Child Code:</strong> ${jc.child_code || "-"}</span>
</div>
        </div>
        <div class="item-header-right">
          <div class="header-stat"><span>Planned Qty</span><strong>${item.so_qty || item.job_card_qty || "-"}</strong></div>
          <div class="header-stat"><span>Processes</span><strong>${item.processes.length}</strong></div>
          <div class="header-stat"><span>Total Days</span><strong>${item.total_days || 0}</strong></div>
          <div class="header-stat"><span>Delivery</span><strong>${formatDateForDisplay(item.delivery_date) || "-"}</strong></div>
          <div class="header-stat remaining-stat ${getRemainingClass(calcRemainingDays(item.delivery_date))}" id="remaining-${iIdx}">
            <span>Remaining</span><strong>${calcRemainingDays(item.delivery_date)} days</strong>
          </div>
        </div>
      </div>
      <div class="wip-bar">
        <span class="wip-label">Current WIP Stage</span>
        <span class="wip-badge ${wipClass}" id="wip-badge-${iIdx}">${item.wip_status || "Pending"}</span>
        ${
          String(item.wip_status || "").trim().toLowerCase() === "raw material" &&
          item.rm_hold_reason
            ? `<span style="font-size:10px;font-weight:700;padding:3px 8px;border-radius:10px;margin-left:4px;${
                item.rm_hold_reason === "testing"
                  ? "background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;"
                  : "background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;"
              }">${
                item.rm_hold_reason === "testing"
                  ? '<i class="fa fa-flask"></i> Testing'
                  : '<i class="fa fa-exclamation-triangle"></i> Shortage'
              }</span>`
            : ""
        }
        ${item.wip_stage_days ? `<span
          id="wip-days-${iIdx}"
          data-days="${item.wip_stage_days}"
          style="font-size:12px;color:var(--muted);font-weight:500"
        >${item.wip_stage_days} days in this stage</span>` : ""}
      </div>
      ${canEditCurrentProcess ? editableQtyRow : readOnlyQtyRow}
      ${(!canEditCurrentProcess && !IS_OPERATOR_READ_ONLY) ? `<div style="padding:8px 20px;color:#dc2626;font-size:12px;font-weight:600;">You do not have rights to update this process.</div>` : ""}
      ${item.processes.length > 0 ? `
        <div class="process-pills-section">
          <div class="pills-section-label">Process Stages</div>
          <div class="process-pills-v2">${procPills}</div>
        </div>` : `
        <div style="padding:14px 20px;color:var(--muted);font-size:13px;border-bottom:1px solid var(--border);font-weight:500">
          No processes defined — please update Process Master.
        </div>`}
      <div id="timeline-section-${iIdx}"></div>
      <div id="qty-summary-section-${iIdx}"></div>
      ${canEditCurrentProcess ? editableQualityRows : readOnlyQualityRows}
    `;

    container.appendChild(section);
    renderTimeline(iIdx, item.process_timeline);
    // renderRevokePanel(iIdx, data.job_card.job_card_no, item.item_name); // UI disabled
    // renderReworkPanel(iIdx, data.job_card.job_card_no, item.item_name); // UI disabled
    //(iIdx, data.job_card.job_card_no, item.item_name);
  });

  if (IS_OPERATOR_READ_ONLY) {
    const submitBar = document.querySelector(".submit-bar");
    if (submitBar) submitBar.style.display = "none";
    return;
  }

  const loggedInUser =
    (window.JMS_CURRENT_USER || window.JMS_CURRENT_USERNAME || "").trim();

  document.getElementById("bottom-supervisor").innerHTML =
    `<option value="${loggedInUser}" selected>${loggedInUser}</option>`;

  const picker = document.getElementById("supervisor-picker");
  if (picker) picker.style.display = "none";

  document.getElementById("submit-info").textContent =
    `${data.items.length} item(s) loaded — submitting as ${loggedInUser}`;
}

// ── DEV: Reset Job Card 500 ───────────────────────────────────────────────────
async function resetJC500() {
  if (!confirm("Are you sure? This will reset ALL data for JC 500.")) return;
  try {
    console.info("Disabled old dev API: /api/dev/reset-jc500"); return;
    const data = await res.json();
    if (data.success) {
      showToast("JC 500 reset successfully", "success");
      currentData = null;
      document.getElementById("results-section").style.display = "none";
      document.getElementById("placeholder").style.display = "block";
      document.getElementById("jc-input").value = "";
    } else {
      showToast(data.error || "Reset failed", "error");
    }
  } catch (e) {
    showToast("Server error", "error");
  }
}

// ── Process Timeline ──────────────────────────────────────────────────────────
function renderTimeline(iIdx, timeline) {
  const host = document.getElementById(`timeline-section-${iIdx}`);
  if (!host) return;
  if (!timeline || timeline.length === 0) { host.innerHTML = ""; return; }

  const rows = timeline.map((t, idx) => {
    const isStore = isStoreProcess(t.process_name);
    let status = t.status || "Pending";
    if (isStore && t.in_time && status === "In Progress") status = "On Time";
    const isOverdue = isTimelineOverdue({ ...t, status });
    const isSub = t.is_subcontract === 1 || t.is_subcontract === true;
    const badgeClass =
      (status === "On Time" || status === "Completed") ? "timeline-badge-ontime"
        : status === "Delayed" ? "timeline-badge-delayed"
          : status === "In Progress" ? "timeline-badge-inprogress"
            : "timeline-badge-pending";
    const rowClasses = [];
    if (status === "Delayed") rowClasses.push("timeline-row-delayed");
    else if (isSub) rowClasses.push("timeline-row-subcontract");
    if (status === "Pending") rowClasses.push("timeline-row-pending");
    if (isOverdue) rowClasses.push("timeline-row-overdue");

    const inDate = formatTimelineDate(t.in_time);
    const outDate = t.out_time
      ? formatTimelineDate(t.out_time)
      : (isStore && t.in_time ? formatTimelineDate(t.in_time) : (t.in_time ? "In Progress" : "-"));
    const daysTaken = `${calculateTimelineDaysTaken(t.in_time, t.out_time)}d`;
    const leadDays = `${t.lead_days != null ? t.lead_days : 0}d`;
    const vendor = t.vendor_name && String(t.vendor_name).trim()
      ? String(t.vendor_name).trim()
      : "-";
    return `
      <tr class="${rowClasses.join(" ")}">
        <td>P${idx + 1}</td><td>${t.process_name || "—"}</td>
        <td>${inDate}</td><td>${outDate}</td>
        <td>${daysTaken}</td><td>${leadDays}</td>
        <td>
          <span class="timeline-badge ${badgeClass}">${status}</span>
                  </td>
        <td>${vendor}</td>
      </tr>`;
  }).join("");

  host.innerHTML = `
    <div class="timeline-section">
      <div class="timeline-toggles-row">
        <button type="button" class="timeline-toggle" id="timeline-toggle-${iIdx}"
                onclick="toggleTimeline(${iIdx})">
          Process Timeline <span class="timeline-caret"><i class="fa fa-caret-down" aria-hidden="true"></i></span>
        </button>
        </button>
      </div>
      <div class="timeline-body" id="timeline-body-${iIdx}">
        <div class="timeline-table-wrap">
          <table class="timeline-table">
            <thead>
              <tr><th>Stage</th><th>Process</th><th>In Date</th><th>Out Date</th>
                  <th>Days Taken</th><th>Lead Days</th><th>Status</th><th>Vendor</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
      <div class="timeline-body" id="qty-summary-body-${iIdx}">
        <div id="qty-summary-table-${iIdx}" style="padding:14px 20px;color:var(--muted);font-size:13px;">
          Loading...
        </div>
      </div>
    </div>`;
}

function toggleTimeline(iIdx) {
  const body = document.getElementById(`timeline-body-${iIdx}`);
  const toggle = document.getElementById(`timeline-toggle-${iIdx}`);
  if (!body || !toggle) return;
  const open = body.classList.toggle("open");
  const caret = toggle.querySelector(".timeline-caret");
  if (caret) caret.innerHTML = open
    ? '<i class="fa fa-caret-down" aria-hidden="true"></i>'
    : '<i class="fa fa-caret-up" aria-hidden="true"></i>';
}

function toggleQtySummary(iIdx) {
  const body = document.getElementById(`qty-summary-body-${iIdx}`);
  const toggle = document.getElementById(`qty-summary-toggle-${iIdx}`);
  if (!body || !toggle) return;
  const open = body.classList.toggle("open");
  const caret = toggle.querySelector(".timeline-caret");
  if (caret) caret.innerHTML = open
    ? '<i class="fa fa-caret-down" aria-hidden="true"></i>'
    : '<i class="fa fa-caret-up" aria-hidden="true"></i>';
}

async function renderQtySummary(iIdx, jcNo, itemName) {
  const role = window.JMS_USER_ROLE;
  if (!IS_GAURANG_SPECIAL && role !== "admin" && role !== "supervisor") return;
  try {
    const res = await fetch(`/api/stage-qty-log/${encodeURIComponent(jcNo)}?item=${encodeURIComponent(itemName)}`);
    const result = await res.json();
    if (!result.success || !result.data || result.data.length === 0) return;

    const toggleBtn = document.getElementById(`qty-summary-toggle-${iIdx}`);
    if (toggleBtn) toggleBtn.style.display = "inline-flex";

    const rows = result.data.map((r, idx) => `
      <tr>
        <td>P${idx + 1}</td>
        <td style="font-weight:600;">${esc(r.process_name)}</td>
        <td style="text-align:center;">${r.planned_qty ?? "—"}</td>
        <td style="text-align:center;">${r.actual_qty ?? "—"}</td>
        <td style="text-align:center;color:#dc2626;font-weight:600;">${r.rejected_qty > 0 ? r.rejected_qty : "—"}</td>
        <td style="text-align:center;color:#f59e0b;font-weight:600;">${r.rework_qty > 0 ? r.rework_qty : "—"}</td>
        <td style="text-align:center;color:#16a34a;font-weight:700;">${r.proceeding_qty ?? "—"}</td>
        <td style="font-size:12px;color:var(--muted);">${esc(r.remarks || "—")}</td>
      </tr>`).join("");

    document.getElementById(`qty-summary-table-${iIdx}`).innerHTML = `
      <div class="timeline-table-wrap">
        <table class="timeline-table">
          <thead>
            <tr>
              <th>Stage</th><th>Process</th>
              <th style="text-align:center;">Planned</th>
              <th style="text-align:center;">Actual</th>
              <th style="text-align:center;">Rejected</th>
              <th style="text-align:center;">Rework</th>
              <th style="text-align:center;">Proceeding</th>
              <th>Remarks</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch (e) { /* silently fail */ }
}

function formatTimelineDate(val) {
  if (!val) return "-";
  const raw = String(val).trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  const d = match
    ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
    : new Date(raw);
  if (isNaN(d.getTime())) return val;
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${String(d.getDate()).padStart(2, "0")} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

function parseTimelineDay(val) {
  if (!val) return null;
  const raw = String(val).trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  const d = new Date(raw);
  if (isNaN(d.getTime())) return null;
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function calculateTimelineDaysTaken(inTime, outTime) {
  const start = parseTimelineDay(inTime);
  if (!start) return 0;
  const end = parseTimelineDay(outTime) || new Date();
  const endDay = new Date(end.getFullYear(), end.getMonth(), end.getDate());
  return Math.max(0, Math.floor((endDay - start) / 86400000));
}

// ── Revoke Panel ──────────────────────────────────────────────────────────────
async function renderRevokePanel(iIdx, jcNo, itemName) {
  const host = document.getElementById(`revoke-panel-${iIdx}`);
  if (!host) return;
  try {
    const res = await fetch(`/api/revoke/list/${encodeURIComponent(jcNo)}`);
    const result = await res.json();
    if (!result.success) { host.innerHTML = ""; return; }

    const entries = (result.data || []).filter(
      r => (r.item_name || "").trim().toLowerCase() === (itemName || "").trim().toLowerCase()
    );
    if (entries.length === 0) { host.innerHTML = ""; return; }

    const open = entries.filter(r => r.status === "Open");
    const done = entries.filter(r => r.status === "Completed");

    const renderRow = (r) => {
      const isOpen = r.status === "Open";
      const statusBadge = isOpen
        ? `<span class="revoke-status-badge revoke-status-open">Open</span>`
        : `<span class="revoke-status-badge revoke-status-done">Completed</span>`;
      const passedCol = isOpen
        ? `<span class="revoke-td-muted">—</span>`
        : `<span class="revoke-passed">${r.passed_qty ?? 0} passed${r.rejected_qty ? `, ${r.rejected_qty} rejected` : ""}</span>`;
      return `
        <tr class="${isOpen ? "revoke-row-open" : "revoke-row-done"}">
          <td class="revoke-td-from">${esc(r.from_process)}</td>
          <td><span class="revoke-arrow">←</span><span class="revoke-td-to">${esc(r.to_process)}</span></td>
          <td><strong>${r.revoke_qty}</strong></td>
          <td>${passedCol}</td>
          <td>${statusBadge}</td>
          <td class="revoke-td-remarks">${esc(r.remarks || "—")}</td>
          <td class="revoke-td-date">${r.created_at || "—"}</td>
          <td>${isOpen ? '<button class="revoke-complete-btn" onclick="openCompleteRevokeModal(' + r.id + ', \'' + esc(r.to_process) + '\', ' + r.revoke_qty + ', ' + (r.rework_stages && r.rework_stages.every(function (s) { return s.is_completed === 1; }) ? 'true' : 'false') + ')">Complete Revoke</button>' : ""}</td>
        </tr>
        ${isOpen && r.rework_stages && r.rework_stages.length > 0 ? `
        <tr class="revoke-rework-row">
          <td colspan="8">
            <div class="rework-stages-wrap">
              <div class="rework-stages-label"><i class="fa fa-wrench"></i> Rework Progress</div>
              <div class="rework-stages-pills">
                ${r.rework_stages.map(s => {
        const done = s.is_completed === 1;
        const active = !done && s.in_time !== null;
        const cls = done ? "rework-pill-done" : active ? "rework-pill-active" : "rework-pill-pending";
        const icon = done ? '<i class="fa fa-check" aria-hidden="true"></i>' : active ? "●" : "○";
        const btn = active && !done
          ? `<button class="rework-advance-btn" onclick="advanceReworkStage(${s.id}, ${r.id})">Advance</button>`
          : "";
        return `<span class="rework-pill ${cls}">${icon} ${esc(s.process_name)} (${s.lead_days}d)${btn}</span>`;
      }).join('<span class="rework-arrow-sep">→</span>')}
              </div>
            </div>
          </td>
        </tr>` : ""}`;
    };

    host.innerHTML = `
      
        <div class="revoke-panel-header">
          <span class="revoke-panel-title"><i class="fa fa-undo"></i> Active Revokes</span>
          ${open.length > 0
        ? `<span class="revoke-panel-count">${open.length} open</span>`
        : `<span class="revoke-panel-count revoke-panel-count-done">All resolved</span>`}
        </div>
        <div class="revoke-table-wrap">
          <table class="revoke-table">
            <thead>
              <tr><th>From Process</th><th>Rework At</th><th>Qty</th>
    <th>Result</th><th>Status</th><th>Remarks</th><th>Created</th><th>Revoke</th></tr>
            </thead>
            <tbody>${[...open, ...done].map(renderRow).join("")}</tbody>
          </table>
        </div>
      </div > `;
  } catch (e) {
    host.innerHTML = "";
  }
}

// ── Rework Panel (new flow) ───────────────────────────────────────────────────
async function renderReworkPanel(iIdx, jcNo, itemName) {
  const host = document.getElementById(`rework-panel-${iIdx}`);
  if (!host) return;
  try {
    const res = await fetch(`/api/revoke/list/${encodeURIComponent(jcNo)}`);
    const result = await res.json();
    if (!result.success) { host.innerHTML = ""; return; }
    const entries = (result.data || []).filter(
      r => (r.item_name || "").trim().toLowerCase() === (itemName || "").trim().toLowerCase()
    );
    if (entries.length === 0) { host.innerHTML = ""; return; }
    const open = entries.filter(r => r.status === "Open");
    const done = entries.filter(r => r.status === "Completed");

    const renderRow = (r) => {
      const isOpen = r.status === "Open";
      const statusBadge = isOpen
        ? `<span class="revoke-status-badge revoke-status-open">Open</span>`
        : `<span class="revoke-status-badge revoke-status-done">Completed</span>`;
      const resultCol = isOpen
        ? `<span class="revoke-td-muted">—</span>`
        : `<span class="revoke-passed">${r.passed_qty ?? 0} passed${r.final_rejected ? `, ${r.final_rejected} rejected` : ""}</span>`;
      const allStageDone = r.rework_stages && r.rework_stages.length > 0 &&
        r.rework_stages.every(s => s.is_completed === 1);
      const completeBtn = isOpen
        ? '<button class="revoke-complete-btn" onclick="openCompleteReworkModal(' +
        r.id + ', \'' + esc(r.to_process) + '\', ' + r.rework_qty + ', ' +
        (allStageDone ? 'true' : 'false') + ')">Complete Rework</button>'
        : "";
      const reworkProgress = isOpen && r.rework_stages && r.rework_stages.length > 0
        ? `<tr class="revoke-rework-row">
            <td colspan="8">
              <div class="rework-stages-wrap">
                <div class="rework-stages-label"><i class="fa fa-wrench"></i> Rework Progress</div>
                <div class="rework-stages-pills">
                  ${r.rework_stages.map(s => {
          const done2 = s.is_completed === 1;
          const active2 = !done2 && s.in_time !== null;
          const cls2 = done2 ? "rework-pill-done" : active2 ? "rework-pill-active" : "rework-pill-pending";
          const icon2 = done2 ? '<i class="fa fa-check" aria-hidden="true"></i>' : active2 ? "●" : "○";
          const btn2 = active2 && !done2
            ? `<button class="rework-advance-btn" onclick="advanceReworkStageNew(${s.id}, ${r.id})">Advance</button>`
            : "";
          return `<span class="rework-pill ${cls2}">${icon2} ${esc(s.process_name)} (${s.lead_days}d)${btn2}</span>`;
        }).join('<span class="rework-arrow-sep">→</span>')}
                </div>
              </div>
            </td>
          </tr>` : "";
      return `
        <tr class="${isOpen ? "revoke-row-open" : "revoke-row-done"}">
          <td class="revoke-td-from">${esc(r.from_process)}</td>
          <td><strong>${r.rework_qty}</strong></td>
          <td>${resultCol}</td>
          <td>${statusBadge}</td>
          <td class="revoke-td-remarks">${esc(r.remarks || "—")}</td>
          <td class="revoke-td-date">${r.created_at || "—"}</td>
          <td>${completeBtn}</td>
        </tr>${reworkProgress}`;
    };

    host.innerHTML = `
      <div class="revoke-panel">
        <div class="revoke-panel-header">
          <span class="revoke-panel-title"><i class="fa fa-undo"></i> Active Reworks</span>
          ${open.length > 0
        ? `<span class="revoke-panel-count">${open.length} open</span>`
        : `<span class="revoke-panel-count revoke-panel-count-done">All resolved</span>`}
        </div>
        <div class="revoke-table-wrap">
          <table class="revoke-table">
            <thead>
              <tr><th>From Process</th><th>Qty</th>
                  <th>Result</th><th>Status</th><th>Remarks</th><th>Created</th><th></th></tr>
            </thead>
            <tbody>${[...open, ...done].map(renderRow).join("")}</tbody>
          </table>
        </div>
      </div>`;
  } catch (e) { host.innerHTML = ""; }
}

/* ── Reject/Rework panel functions (UI disabled — restore with page3.html markup to re-enable) ──
async function advanceReworkStageNew(stageId, reworkId) { ... }
let pendingRework = null;
function openCompleteReworkModal(reworkId, toProcess, reworkQty, allDone) { ... }
async function confirmCompleteRework() { ... }
── */


// ── Supervisor picker ─────────────────────────────────────────────────────────
function renderSupervisorPicker(supervisors) {
  if (IS_OPERATOR_READ_ONLY) return;
  const hiddenSelect = document.getElementById("bottom-supervisor");
  const button = document.getElementById("supervisor-picker-btn");
  const list = document.getElementById("supervisor-picker-list");
  if (!hiddenSelect || !button || !list) return;

  // Default to the logged-in user — operator can still change it if a
  // different person physically did the work.
  const currentUser = (window.JMS_CURRENT_USER || "").trim();
  hiddenSelect.value = currentUser;
  button.textContent = currentUser || "-- Select Supervisor --";
  list.classList.remove("open");
  list.innerHTML = `
      <button type = "button" class="supervisor-picker-option" onclick = "selectSupervisor('')" >
        --Select Supervisor--
    </button >
      ${supervisors.map(s => `
      <button type="button" class="supervisor-picker-option ${s === currentUser ? 'active' : ''}"
              onclick="selectSupervisor('${String(s).replace(/\\/g, "\\\\").replace(/'/g, "\\'")}')">
        ${s}
      </button>`).join("")
    } `;
}

function toggleSupervisorPicker() {
  if (IS_OPERATOR_READ_ONLY) return;
  document.getElementById("supervisor-picker-list")?.classList.toggle("open");
}

function selectSupervisor(value) {
  if (IS_OPERATOR_READ_ONLY) return;
  const hiddenSelect = document.getElementById("bottom-supervisor");
  const button = document.getElementById("supervisor-picker-btn");
  const list = document.getElementById("supervisor-picker-list");
  if (!hiddenSelect || !button || !list) return;
  hiddenSelect.value = value;
  button.textContent = value || "-- Select Supervisor --";
  list.classList.remove("open");
  list.querySelectorAll(".supervisor-picker-option").forEach(opt => {
    opt.classList.toggle("active",
      opt.textContent.trim() === (value || "-- Select Supervisor --"));
  });
}

document.addEventListener("click", function (event) {
  if (IS_OPERATOR_READ_ONLY) return;
  const picker = document.getElementById("supervisor-picker");
  if (!picker || picker.contains(event.target)) return;
  document.getElementById("supervisor-picker-list")?.classList.remove("open");
});

// ── Open stage modal ──────────────────────────────────────────────────────────
function openStageModal(pillEl) {
  if (IS_OPERATOR_READ_ONLY) {
    // OPERATOR_SEARCH_ACTION_FIX_V1
    // Operator queue is already filtered by assigned process.
    // Search results therefore resolve back to that queue instead
    // of depending on window.myAccessibleProcesses.
    const clickedProc = decodeURIComponent(
      pillEl.dataset.process || ""
    ).trim();

    const searchedJc = decodeURIComponent(
      pillEl.dataset.jcno || ""
    ).trim();

    const iIdx = parseInt(pillEl.dataset.iidx);
    const item = currentData?.items?.[iIdx] || {};
    const searchedItem = String(item.item_name || "").trim();

    let globalIdx = operatorCards.findIndex(function(card) {
      const sameJc =
        String(card?.job_card_no || "").trim() === searchedJc;

      const cardProcess = String(
        card?.current_process || card?.wip_status || ""
      ).trim().toLowerCase();

      const sameProcess =
        cardProcess === clickedProc.toLowerCase();

      const cardItem = String(card?.item_name || "").trim();
      const sameItem =
        !searchedItem || !cardItem || cardItem === searchedItem;

      return sameJc && sameProcess && sameItem;
    });

    // Fallback for older queue payloads with incomplete item/process fields.
    if (globalIdx < 0) {
      globalIdx = operatorCards.findIndex(function(card) {
        return String(card?.job_card_no || "").trim() === searchedJc;
      });
    }

    if (globalIdx >= 0) {
      openOperatorCompleteModal(globalIdx);
    } else {
      showToast(
        "This Job Card is not active in your assigned operator queue.",
        "error"
      );
    }

    return;
  }
  const clickedProc = decodeURIComponent(pillEl.dataset.process);
  const clickedPIdx = parseInt(pillEl.dataset.pidx);
  const iIdx = parseInt(pillEl.dataset.iidx);
  const jcNo = decodeURIComponent(pillEl.dataset.jcno);
  const itemName = decodeURIComponent(pillEl.dataset.item);
  const isSubcontract = pillEl.dataset.subcontract === "1";
  const item = currentData?.items?.[iIdx] || {};
  const wipIdx = item.wip_process_index ?? -1;

  // ── Supervisor process-access pre-check ────────────────────────────────
  // Block before opening any modal if this supervisor doesn't manage the
  // CURRENT stage (the one being moved out of), instead of letting them
  // click through both modals and only fail at the final confirm step.
  if (Array.isArray(window.myAccessibleProcesses)) {
    const currentWip = (item.wip_status || "").trim().toLowerCase();
    const hasAccess = window.myAccessibleProcesses.some(
      p => p.trim().toLowerCase() === currentWip
    );
    if (!hasAccess) {
      showToast(`You do not have permission to move items out of '${item.wip_status}'.`, "error");
      return;
    }
  }

  if (isStoreProcess(clickedProc) || isItemInStore(item)) {
    showStoreMessage();
    return;
  }

  if (wipIdx === -1) {
    const currentWipKey = String(item.wip_status || "").trim().toLowerCase();

    if (["store", "completed", "complete"].includes(currentWipKey)) {
      showToast("All stages completed for this item.", "info");
    } else {
      showToast(
        `Current WIP stage '${item.wip_status || "-"}' is not found in the saved process route. Please correct the job-card data.`,
        "error"
      );
    }

    return;
  }
  if (clickedPIdx < wipIdx) { showToast("This stage is already completed.", "info"); return; }
  if (clickedPIdx > wipIdx) {
    const processes = item.processes || [];
    const currentStageName = processes[wipIdx] || "current stage";
    showToast(`Complete "${currentStageName}" first before advancing to this stage.`, "warning");
    return;
  }

  const processes = item.processes || [];
  // TERMINAL_C_COMPLETION_START
  const compactItemName = String(item.item_name || "")
    .toUpperCase()
    .replace(/\s+/g, "");

  const isTerminalCItem = compactItemName.endsWith("-C");
  const isLastSavedProcess = wipIdx === processes.length - 1;

  const nextStageName =
    isTerminalCItem && isLastSavedProcess
      ? "Completed"
      : wipIdx + 1 < processes.length
        ? processes[wipIdx + 1]
        : "Store";
  // TERMINAL_C_COMPLETION_END
  const timeline = item.process_timeline || [];

  const currentTimelineRow = timeline.find(t =>
    String(t.process_name || "").trim().toLowerCase() ===
    String(clickedProc || "").trim().toLowerCase()
  );

  const nextTimelineRow = timeline.find(t =>
    String(t.process_name || "").trim().toLowerCase() ===
    String(nextStageName || "").trim().toLowerCase()
  );

  const plannedQty = item.job_card_qty || item.so_qty || "-";
  let actualQty = document.getElementById(`actual_${iIdx}`)?.value;

  if (!actualQty || actualQty === "0") {
    actualQty = plannedQty;
  }
  const nextLeadDays = nextTimelineRow?.lead_days || currentTimelineRow?.lead_days || 1;
  const wipBadge = document.getElementById(`wip - badge - ${iIdx}`);
  const currentWIP = item.wip_status || "Pending";

  pendingChange = {
    jcNo,
    itemName,
    currentStage: clickedProc,
    newStage: nextStageName,
    isSubcontract
  };

  document.getElementById("modal-planned-qty").value = plannedQty === "-" ? "" : plannedQty;
  document.getElementById("modal-actual-qty").value = actualQty === "-" ? "" : actualQty;
  document.getElementById("modal-actual-qty").oninput = function () {
    const actualInput = document.getElementById(`actual_${iIdx}`);
    if (actualInput) actualInput.value = this.value;
    updateRejectedQty(iIdx);
    const planned = parseInt(document.getElementById("modal-planned-qty").value) || 0;
    const actual = parseInt(this.value) || 0;
    if (actual > planned) {
      this.value = planned;
      if (actualInput) actualInput.value = this.value;
      showToast(`Actual qty cannot exceed planned qty (${planned})`, "warning");
    }
    updateRejReworkSection();
  };

  document.getElementById("modal-current-process").textContent = currentWIP;
  document.getElementById("modal-next-process").textContent = nextStageName;
  const leadDaysRow = (item.process_timeline || []).find(t =>
    String(t.process_name || "").trim().toLowerCase() ===
    String(nextStageName || "").trim().toLowerCase()
  );

  const leadDaysInput = document.getElementById("modal-lead-days");

  if (leadDaysInput) {
    leadDaysInput.value = leadDaysRow && leadDaysRow.lead_days ? leadDaysRow.lead_days : 1;

    if (typeof updateExpectedDate === "function") {
      updateExpectedDate();
    }
  }
  document.getElementById("modal-title").textContent = "Change Stage?";
  document.getElementById("modal-note").textContent =
    `Stage change will be recorded by ${(window.JMS_CURRENT_USER || window.JMS_CURRENT_USERNAME || "").trim()}.`;
  document.getElementById("subcontract-section").style.display = "block";
  document.getElementById("modal-confirm-btn").textContent = "Confirm";
  document.getElementById("modal-confirm-btn").style.background = "";
  document.getElementById("subcontract-checkbox").checked = false;
  document.getElementById("vendor-row").style.display = "none";
  document.getElementById("modal-vendor-name").value = "";
  const leadDaysEl = document.getElementById("modal-lead-days");
  if (leadDaysEl) {
    leadDaysEl.value = nextLeadDays;
  }
  const stageRemarkEl = document.getElementById("modal-stage-remark");
  if (stageRemarkEl) stageRemarkEl.value = "";

  updateRejReworkSection();
  if (typeof showRmReasonIfNeeded === "function") showRmReasonIfNeeded(nextStageName);
  document.getElementById("stage-modal").classList.add("open");
}

function closeStageModal() {
  document.getElementById("stage-modal").classList.remove("open");
  pendingChange = null;
  const stageRemarkEl = document.getElementById("modal-stage-remark");
  if (stageRemarkEl) stageRemarkEl.value = "";
  // Reset reject/rework section
  const rejQtyEl = document.getElementById("modal-reject-qty");
  if (rejQtyEl) rejQtyEl.value = "";
  const rwQtyEl = document.getElementById("modal-rework-qty");
  if (rwQtyEl) rwQtyEl.value = "";
  const rejSec = document.getElementById("reject-input-section");
  if (rejSec) rejSec.style.display = "none";
  const rwSec = document.getElementById("rework-input-section");
  if (rwSec) rwSec.style.display = "none";
  const rrSec = document.getElementById("rej-rework-section");
  if (rrSec) rrSec.style.display = "none";
  const errEl = document.getElementById("rej-rework-error");
  if (errEl) errEl.textContent = "";
}

// ── Reject / Rework section logic ────────────────────────────────────────────
function updateRejReworkSection() {
  return; // Reject/Rework UI disabled — see page3.html for commented-out markup
}

function validateRejRework() {
  const actual = parseInt(document.getElementById("modal-actual-qty")?.value) || 0;
  const rejected = parseInt(document.getElementById("modal-reject-qty")?.value) || 0;
  const rework = parseInt(document.getElementById("modal-rework-qty")?.value) || 0;
  const errorEl = document.getElementById("rej-rework-error");
  if (rejected + rework > actual) {
    if (errorEl) errorEl.textContent = `Rejected (${rejected}) + Rework (${rework}) cannot exceed Actual Qty (${actual})`;
    return false;
  }
  if (errorEl) errorEl.textContent = "";
  return true;
}

function toggleRejSection(show) {
  const sec = document.getElementById("reject-input-section");
  if (sec) sec.style.display = show ? "block" : "none";
  if (!show) {
    const el = document.getElementById("modal-reject-qty");
    if (el) el.value = "";
    validateRejRework();
  }
}

function toggleReworkSection(show) {
  const sec = document.getElementById("rework-input-section");
  if (sec) sec.style.display = show ? "block" : "none";
  // Rework stays in current process — always hide rework-to-detail
  const detEl = document.getElementById("rework-to-detail");
  if (detEl) detEl.style.display = "none";
  if (!show) {
    const el = document.getElementById("modal-rework-qty");
    if (el) el.value = "";
    validateRejRework();
  }
}

// Backward compat aliases
function updateRevokeSection() { updateRejReworkSection(); }
function updateRevokedQty() { validateRejRework(); }
function fillLeadDaysForNextSubcontract() {
  const leadInput = document.getElementById("modal-lead-days");
  if (!leadInput || !pendingChange) return;

  const itemName = pendingChange.itemName || "";
  const nextProcess = pendingChange.newStage || "";

  const item = (currentData?.items || []).find(it =>
    String(it.item_name || "").trim().toLowerCase() ===
    String(itemName || "").trim().toLowerCase()
  );

  if (!item) return;

  const row = (item.process_timeline || []).find(t =>
    String(t.process_name || "").trim().toLowerCase() ===
    String(nextProcess || "").trim().toLowerCase()
  );

  const leadDays = row && row.lead_days ? row.lead_days : "";

  if (leadDays) {
    leadInput.value = String(leadDays);

    if (typeof updateExpectedDate === "function") {
      updateExpectedDate();
    }
  }
}
// ── Subcontract vendor toggle ─────────────────────────────────────────────────
function toggleSubcontractVendor(checked) {
  if (IS_OPERATOR_READ_ONLY) return;

  const vendorRow = document.getElementById("vendor-row");
  const leadInput = document.getElementById("modal-lead-days");
  const hint = document.getElementById("lead-days-hint");
  const dateLabel = document.getElementById("modal-expected-date-label");

  if (vendorRow) {
    vendorRow.style.display = checked ? "block" : "none";
  }

  if (!checked) {
    if (leadInput) {
      leadInput.value = "";
      leadInput.removeAttribute("readonly");
    }

    if (hint) {
      hint.textContent = "";
    }

    if (dateLabel) {
      dateLabel.textContent = "";
    }

    return;
  }

  const normalize = (value) =>
    String(value || "").trim().toLowerCase();

  const nextProcess =
    pendingChange?.newStage ||
    document.getElementById("modal-next-process")?.textContent ||
    "";

  let item = null;

  if (pendingChange?.itemName) {
    item = (currentData?.items || []).find(it =>
      normalize(it.item_name) === normalize(pendingChange.itemName)
    );
  }

  if (!item && Number.isInteger(pendingChange?.iIdx)) {
    item = currentData?.items?.[pendingChange.iIdx];
  }

  if (!item) {
    item = currentData?.items?.[0] || {};
  }

  const leadRow = (item.process_timeline || []).find(t =>
    normalize(t.process_name) === normalize(nextProcess)
  );

  const planLeadDays = parseInt(leadRow?.lead_days || 0, 10);

  if (planLeadDays > 0) {
    if (leadInput) {
      leadInput.value = planLeadDays;
      leadInput.setAttribute("readonly", "readonly");
    }

    if (hint) {
      hint.textContent = "";
    }
  } else {
    if (leadInput) {
      leadInput.value = "";
      leadInput.removeAttribute("readonly");
    }

    if (hint) {
      hint.textContent = "Not set in process plan — enter manually";
    }
  }

  if (typeof updateExpectedDate === "function") {
    updateExpectedDate();
  }
}

// ── Expected date label ───────────────────────────────────────────────────────
function updateExpectedDate() {
  if (IS_OPERATOR_READ_ONLY) return;
  const days = parseInt(document.getElementById("modal-lead-days")?.value) || 0;
  const label = document.getElementById("modal-expected-date-label");
  if (!label) return;
  if (days > 0) {
    const d = new Date();
    d.setDate(d.getDate() + days);
    label.textContent = `→ Expected: ${formatDateForDisplay(d)} `;
    label.style.color = "#16a34a";
  } else {
    label.textContent = "";
  }
}

// ── Confirm stage change ──────────────────────────────────────────────────────
async function selectRmReason(reason) {
  var testBtn = document.getElementById("rm-btn-testing");
  var shortBtn = document.getElementById("rm-btn-shortage");
  var input = document.getElementById("rm-hold-reason-value");
  if (!input) return;
  if (input.value === reason) {
    input.value = "";
    if (testBtn) { testBtn.style.background = "#eff6ff"; testBtn.style.borderColor = "#bfdbfe"; testBtn.style.color = "#1d4ed8"; }
    if (shortBtn) { shortBtn.style.background = "#fffbeb"; shortBtn.style.borderColor = "#fde68a"; shortBtn.style.color = "#92400e"; }
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
  var section = document.getElementById("rm-reason-section");
  var input = document.getElementById("rm-hold-reason-value");
  if (!section) return;
  var isRm = (nextStage || "").trim().toLowerCase() === "raw material";
  section.style.display = isRm ? "block" : "none";
  if (!isRm && input) input.value = "";
  if (isRm) selectRmReason("");
}

function confirmStageChange() {
  if (IS_OPERATOR_READ_ONLY) { showToast("Operator has read-only access", "error"); return; }
  if (!pendingChange) return;
  if (!pendingChange) return;
  // Show confirmation modal instead of proceeding directly
  document.getElementById("csm-from").textContent = pendingChange.currentStage;
  document.getElementById("csm-to").textContent = pendingChange.newStage;
  document.getElementById("confirm-stage-modal").classList.add("open");
}

function closeConfirmStageModal() {
  document.getElementById("confirm-stage-modal").classList.remove("open");
  const arrowIcon = document.querySelector("#confirm-stage-modal .fa-arrow-left");
  if (arrowIcon) arrowIcon.className = "fa fa-arrow-right";
}

function openRollbackModal(jcNo, itemName, currentStage, previousStage) {
  if (Array.isArray(window.myAccessibleProcesses)) {
    const currentWip = (currentStage || "").trim().toLowerCase();
    const hasAccess = window.myAccessibleProcesses.some(
      p => String(p || "").trim().toLowerCase() === currentWip
    );
    if (!hasAccess) {
      showToast(`You do not have permission to roll back from '${currentStage}'.`, "error");
      return;
    }
  }
  pendingChange = { jcNo, itemName, currentStage, newStage: previousStage, isRollback: true };
  document.getElementById("csm-from").textContent = previousStage;
  document.getElementById("csm-to").textContent = currentStage;
  const arrowIcon = document.querySelector("#confirm-stage-modal .fa-arrow-right");
  if (arrowIcon) arrowIcon.className = "fa fa-arrow-left";
  document.getElementById("confirm-stage-modal").classList.add("open");
}

async function proceedStageChange() {
  closeConfirmStageModal();
  if (!pendingChange) return;

  // ── Rollback flow ─────────────────────────────────────────────
  if (pendingChange.isRollback) {
    const { jcNo, itemName, currentStage, newStage: previousStage } = pendingChange;
    const changedBy = document.getElementById("bottom-supervisor")?.value || "Not Assigned";

    try {
      const res = await fetch("/api/wip/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo,
          item_name: itemName,
          current_stage: currentStage,
          target_stage: previousStage,
          changed_by: changedBy
        })
      });

      const data = await res.json();

      if (data.success) {
        showToast(data.message, "success");
        fetchJobCard();
      } else {
        showToast(data.error || "Rollback failed", "error");
      }
    } catch (e) {
      showToast("Server error", "error");
    }

    return;
  }

  const { jcNo, itemName, currentStage, newStage, isSubcontract } = pendingChange;

  const supervisor =
    document.getElementById("bottom-supervisor")?.value || "Not Assigned";

  const stageRemark =
    document.getElementById("modal-stage-remark")?.value.trim() || "";

  const sendToSubcontract =
    document.getElementById("subcontract-checkbox")?.checked || false;

  const vendorName =
    document.getElementById("modal-vendor-name")?.value.trim() || "";

  const leadDays =
    parseInt(document.getElementById("modal-lead-days")?.value) || 0;

  // ── IMPORTANT LOGIC ───────────────────────────────────────────
  // If checkbox is checked, next process must go to subcontract first.
  // This must run BEFORE current subcontract complete logic.
  if (sendToSubcontract) {
    if (!vendorName) {
      showToast("Please enter vendor name for subcontracting", "error");
      return;
    }

    if (!leadDays || leadDays < 1) {
      showToast("Please enter lead days for subcontracting", "error");
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
          lead_days: leadDays,
          changed_by: supervisor,
          stage_remark: stageRemark
        })
      });

      const data = await res.json();

      if (data.success) {
        closeStageModal();
        showToast(`${newStage} sent to subcontracting — ${vendorName}`, "success");
        fetchJobCard();
      } else {
        showToast(data.error || "Failed", "error");
      }
    } catch (e) {
      showToast("Server error", "error");
    }

    return;
  }

  // ── If current process itself is subcontract and checkbox is NOT checked,
  // complete current subcontract and move next process normally.
  if (isSubcontract) {
    try {
      const res = await fetch("/api/wip/subcontract_complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo,
          item_name: itemName,
          process: currentStage,
          changed_by: supervisor
        })
      });

      const data = await res.json();

      if (data.success) {
        closeStageModal();
        showToast(data.message || "Subcontract completed", "success");
        fetchJobCard();
      } else {
        showToast(data.error || "Update failed", "error");
      }
    } catch (e) {
      showToast("Server error", "error");
    }

    return;
  }

  // ── Normal process movement ───────────────────────────────────
  const rejectedQty = 0;
  const reworkQty = 0;
  const reworkRemarks = "";

  try {
    const modalActualQtyValue =
      document.getElementById("modal-actual-qty")?.value || null;

    console.log("Sending actual_qty:", modalActualQtyValue);

    const res = await fetch("/api/wip/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_card_no: jcNo,
        item_name: itemName,
        new_stage: newStage,
        changed_by: supervisor,
        actual_qty: modalActualQtyValue,
        rejected_qty: rejectedQty,
        rework_qty: reworkQty,
        rework_remarks: reworkRemarks,
        stage_remark: stageRemark,
        rm_hold_reason: document.getElementById("rm-hold-reason-value")?.value || null
      })
    });

    const data = await res.json();

    if (data.success) {
      closeStageModal();

      let msg = `Stage changed to ${newStage}`;
      if (rejectedQty > 0) msg += ` | ${rejectedQty} rejected`;
      if (reworkQty > 0) msg += ` | ${reworkQty} sent for rework`;

      showToast(msg, "success");
      fetchJobCard();
    } else {
      showToast(data.error || "Update failed", "error");
    }
  } catch (e) {
    showToast("Server error — is Flask running?", "error");
  }
}

// ── Modal close events ────────────────────────────────────────────────────────
document.addEventListener("click", function (e) {
  if (IS_OPERATOR_READ_ONLY) return;
  const modal = document.getElementById("stage-modal");
  if (modal && e.target === modal) closeStageModal();
});

document.addEventListener("keydown", function (e) {
  if (IS_OPERATOR_READ_ONLY) return;
  if (e.key === "Escape") closeStageModal();
});

// ── Submit quality check ──────────────────────────────────────────────────────
async function submitQualityCheck() {
  if (IS_OPERATOR_READ_ONLY) { showToast("Operator has read-only access", "error"); return; }
  if (!currentData) return;
  const supervisor = document.getElementById("bottom-supervisor").value;
  if (!supervisor) { showToast("Select supervisor before submitting", "error"); return; }

  const details = [];
  let valid = true;

  currentData.items.forEach((item, iIdx) => {
    if (!valid) return;
    if (!canEditProcess(item.wip_status)) {
      valid = false;
      showToast(`You do not have rights to update process: ${item.wip_status || "-"}`, "error");
      return;
    }
    const actualQty = parseInt(document.getElementById(`actual_${iIdx}`)?.value);
    const plannedQty = item.so_qty ?? item.job_card_qty ?? "";
    const rejectedQty = calculateRejectedQty(plannedQty, actualQty);
    if (!actualQty && actualQty !== 0) {
      valid = false; showToast(`Enter actual qty for: ${item.item_name} `, "error"); return;
    }
    const qr = Array.from(document.querySelectorAll(`input[name = "qr_${iIdx}"]`)).find(r => r.checked);
    if (!qr) {
      valid = false; showToast(`Select quality result for: ${item.item_name} `, "error"); return;
    }
    details.push({
      item_name: item.item_name, actual_qty: actualQty,
      rejected_qty: rejectedQty === "-" ? null : rejectedQty,
      completed_process: item.wip_status || "", quality_result: qr.value,
      supervisor, remarks: document.getElementById(`remarks_${iIdx}`)?.value.trim() || "",
    });
  });

  if (!valid) return;

  try {
    const res = await fetch("/api/quality_check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_card_no: currentData.job_card.job_card_no, details })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      document.getElementById("results-section").style.display = "none";
      document.getElementById("placeholder").style.display = "block";
      document.getElementById("jc-input").value = "";
      currentData = null;
      // Show operator grid again after submit
      if (IS_OPERATOR_READ_ONLY) {
        const ov = document.getElementById("operator-view");
        if (ov) { ov.style.display = "block"; loadOperatorView(); }
      }
    } else {
      showToast(data.error, "error");
    }
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
/* ── Complete Revoke Modal functions (UI disabled — restore with page3.html markup to re-enable) ──
let pendingRevoke = null;
function openCompleteRevokeModal(revokeId, toProcess, revokeQty, allReworkDone) { ... }
function closeCompleteRevokeModal() { ... }
function updateCrmRejected() { ... }
function updateCrmPassed() { ... }
function updateCrmBalance() { ... }
async function confirmCompleteRevoke() { ... }
async function advanceReworkStage(reworkStageId, revokeId) { ... }
── */
async function togglePage3Priority(itemId, jobCardNo, itemName, newValue, badgeEl) {
  try {
    const cleanItemName = decodeURIComponent(itemName || "");

    const res = await fetch("/api/job_card_item/priority", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        item_id: itemId || null,
        job_card_no: jobCardNo,
        item_name: cleanItemName,
        is_priority: newValue
      })
    });

    const data = await res.json();

    if (data.success) {
      badgeEl.style.background = newValue ? "#dc2626" : "#f3f4f6";
      badgeEl.style.color = newValue ? "#fff" : "#6b7280";
      badgeEl.style.border = `1px solid ${newValue ? "#dc2626" : "#d1d5db"}`;
      badgeEl.innerHTML = newValue
        ? '<i class="fa fa-exclamation-triangle" aria-hidden="true"></i> URGENT'
        : "○ Regular";

      const safeItemName = encodeURIComponent(cleanItemName);

      badgeEl.setAttribute(
        "onclick",
        `event.stopPropagation(); togglePage3Priority(${Number(itemId) || 0}, '${jobCardNo}', '${safeItemName}', ${newValue ? 0 : 1}, this)`
      );

      showToast("Priority updated successfully", "success");
    } else {
      showToast(data.error || "Failed to update priority", "error");
    }
  } catch (err) {
    console.error("Priority update error:", err);
    showToast("Priority update failed", "error");
  }
}
function renderCardSkeleton(cardCount = 2) {
  let cards = "";
  for (let i = 0; i < cardCount; i++) {
    cards += `<div class="skeleton-block" style="height: 220px;"></div>`;
  }
  return `<div class="skeleton-wrap">${cards}</div>`;
}
// ── Remove Process (Gaurang only) ─────────────────────────────────────────────
// ── Remove Process (Gaurang only) ─────────────────────────────────────────────
let _removeProcessPending = null;

function removeProcess(jobCardNo, itemName, processName) {
  if (!IS_GAURANG_SPECIAL) return;
  _removeProcessPending = {
    jobCardNo: decodeURIComponent(jobCardNo),
    itemName: decodeURIComponent(itemName),
    processName: decodeURIComponent(processName),
  };
  document.getElementById("remove-process-name").textContent = decodeURIComponent(processName);
  document.getElementById("remove-process-modal").classList.add("open");
}

function closeRemoveProcessModal() {
  document.getElementById("remove-process-modal").classList.remove("open");
  _removeProcessPending = null;
}

async function confirmRemoveProcess() {
  if (!_removeProcessPending) return;
  const { jobCardNo, itemName, processName } = _removeProcessPending;
  const btn = document.getElementById("remove-process-confirm-btn");
  btn.textContent = "Removing...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/wip/remove_process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_card_no: jobCardNo,
        item_name: itemName,
        process_name: processName,
      })
    });
    const data = await res.json();
    closeRemoveProcessModal();
    if (data.success) {
      showToast(data.message, "success");
      fetchJobCard();
    } else {
      showToast(data.error || "Failed to remove process.", "error");
    }
  } catch (e) {
    closeRemoveProcessModal();
    showToast("Network error.", "error");
  } finally {
    btn.textContent = "Remove";
    btn.disabled = false;
  }
}
function loadPage3KanbanSummary() {
  // Kanban view disabled on Page 3.
}

/* Kanban view disabled on Page 3.
async function loadPage3KanbanSummary() {
  try {
    const res = { ok: true, json: async () => ({ success: true, data: [], summary: {} }) };
    const data = await res.json();

    if (!data.success) {
      console.error("Kanban summary error:", data.error);
      return;
    }

    renderPage3KanbanSummary(data);
  } catch (err) {
    console.error("Kanban summary failed:", err);
  }
}

function ensureKanbanSummaryHost() {
  let host = document.getElementById("page3-kanban-summary");

  if (host) return host;

  host = document.createElement("div");
  host.id = "page3-kanban-summary";

  const resultsSection = document.getElementById("results-section");
  const placeholder = document.getElementById("placeholder");

  if (resultsSection && resultsSection.parentNode) {
    resultsSection.parentNode.insertBefore(host, resultsSection);
  } else if (placeholder && placeholder.parentNode) {
    placeholder.parentNode.insertBefore(host, placeholder);
  } else {
    document.body.prepend(host);
  }

  return host;
}

function renderPage3KanbanSummary(data) {
  const host = ensureKanbanSummaryHost();
  const summary = data.summary || {};
  const processes = data.processes || [];
  const cards = data.cards || [];

  const processCardsHtml = processes.map(p => {
    const procName = p.process_name || "-";
    const procCards = cards.filter(c => String(c.process_name || "").trim().toLowerCase() === String(procName).trim().toLowerCase());

    const pendingCards = procCards.filter(c => c.card_status === "pending");
    const completedCards = procCards.filter(c => c.card_status === "completed");

    const renderMiniCard = (c) => `
      <div class="kanban-mini-card ${c.card_status === "completed" ? "done" : "pending"}"
           onclick="document.getElementById('jc-input').value='${esc(c.job_card_no)}'; fetchJobCard();">
        <div class="kanban-mini-card-top">
          <strong>JC ${esc(c.job_card_no)}</strong>
          ${c.is_priority ? `<span class="kanban-urgent">URGENT</span>` : ""}
        </div>
        <div class="kanban-mini-item">${esc(c.item_name || "-")}</div>
        <div class="kanban-mini-meta">
          <span>SO: ${esc(c.so_no || "-")}</span>
          <span>${c.card_status === "completed" ? "Completed" : "Pending"}</span>
        </div>
      </div>
    `;

    return `
      <div class="kanban-process-column">
        <div class="kanban-process-head">
          <div>
            <div class="kanban-process-title">${esc(procName)}</div>
            <div class="kanban-process-sub">${p.total_jobcards || 0} total</div>
          </div>
          <div class="kanban-process-counts">
            <span class="pending">${p.pending_jobcards || 0} Pending</span>
            <span class="completed">${p.completed_jobcards || 0} Completed</span>
          </div>
        </div>

        <div class="kanban-status-title">Pending Job Cards</div>
        <div class="kanban-card-list">
          ${pendingCards.length ? pendingCards.map(renderMiniCard).join("") : `<div class="kanban-empty">No pending job card</div>`}
        </div>

        <div class="kanban-status-title completed-title">Completed Job Cards</div>
        <div class="kanban-card-list completed-list">
          ${completedCards.length ? completedCards.slice(0, 10).map(renderMiniCard).join("") : `<div class="kanban-empty">No completed job card</div>`}
          ${completedCards.length > 10 ? `<div class="kanban-more">+${completedCards.length - 10} more completed</div>` : ""}
        </div>
      </div>
    `;
  }).join("");

  host.innerHTML = `
    <div class="page3-kanban-wrap">
      <div class="kanban-main-head">
        <div>
          <div class="kanban-title">My Process</div>
          <div class="kanban-subtitle">
            ${window.JMS_USER_ROLE === "supervisor" && !IS_GAURANG_SPECIAL ? "Showing only your assigned processes" : "All process view"}
          </div>
        </div>

        <button type="button" class="kanban-refresh-btn" onclick="loadPage3KanbanSummary()">
          Refresh
        </button>
      </div>

      <div class="kanban-summary-grid">
        <div class="kanban-summary-box total">
          <span>Total</span>
          <strong>${summary.total_jobcards || 0}</strong>
        </div>
        <div class="kanban-summary-box pending">
          <span>Pending</span>
          <strong>${summary.pending_jobcards || 0}</strong>
        </div>
        <div class="kanban-summary-box completed">
          <span>Completed</span>
          <strong>${summary.completed_jobcards || 0}</strong>
        </div>
      </div>

      <div class="kanban-process-grid">
        ${processCardsHtml || `<div class="kanban-empty">No process data found.</div>`}
      </div>
    </div>
  `;
}

document.addEventListener("DOMContentLoaded", function () {
  loadPage3KanbanSummary();
});
*/

/* CHILD_C_STABLE_GATE_UI_START */

/*
  Stable Child -C UI Gate
  Purpose:
  - One single child-C UI logic only
  - No flickering
  - No scary red error
  - No modal opening when blocked
  - Timeline display is cleaned
*/

window.__childCGateCache = window.__childCGateCache || {};

function childCStableMessage(data) {
  const row = (data && data.blocking_rows && data.blocking_rows[0]) ? data.blocking_rows[0] : {};
  const childJc = row.c_job_card_no || "";
  const childItem = row.c_item_description || "required child -C item";

  if (childJc && childJc !== "NOT FOUND") {
    return "Waiting for child job card " + childJc + " to complete first.";
  }

  return "Waiting because child job card is not found for: " + childItem;
}

async function childCStableCheck(jcNo) {
  if (!jcNo) {
    return { allowed: true, message: "", data: null };
  }

  if (window.__childCGateCache[jcNo]) {
    return window.__childCGateCache[jcNo];
  }

  try {
    const res = await fetch("/api/wip/check-c-child-gate/" + encodeURIComponent(jcNo));
    const data = await res.json();

    const result = {
      allowed: Boolean(data.success && data.can_start_upper !== false),
      message: data.success && data.can_start_upper === false
        ? childCStableMessage(data)
        : "",
      data: data
    };

    window.__childCGateCache[jcNo] = result;
    return result;

  } catch (err) {
    return {
      allowed: false,
      message: "Unable to check child -C status. Please refresh and try again.",
      data: null
    };
  }
}

function childCStableEnsureStyle() {
  if (document.getElementById("child-c-stable-style")) return;

  const style = document.createElement("style");
  style.id = "child-c-stable-style";
  style.textContent = `
    .child-c-note {
      margin: 10px 20px 0 20px;
      padding: 10px 12px;
      border: 1px solid #fdba74;
      background: #fff7ed;
      color: #9a3412;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 700;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }

    .child-c-note-close {
      width: 26px;
      height: 26px;
      flex: 0 0 26px;
      border: 1px solid #fb923c;
      border-radius: 50%;
      background: #ffffff;
      color: #c2410c;
      font-size: 20px;
      line-height: 20px;
      font-weight: 800;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
    }

    .child-c-note-close:hover {
      background: #ffedd5;
      border-color: #ea580c;
    }

    .child-c-note > span,
    .child-c-note-message {
      flex: 1;
      min-width: 0;
      line-height: 1.5;
    }

    .child-c-jc-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin: 0 4px;
      padding: 3px 9px;
      border: 1px solid #fb923c;
      border-radius: 999px;
      background: #ffffff;
      color: #c2410c !important;
      font-weight: 900;
      text-decoration: none !important;
      white-space: nowrap;
      cursor: pointer;
    }

    .child-c-jc-link:hover {
      background: #ffedd5;
      border-color: #ea580c;
      text-decoration: none !important;
    }

    .pill-child-c-waiting .pill-days {
      max-width: 145px;
      line-height: 1.25;
      white-space: normal;
      text-align: center;
    }

    .pill-child-c-waiting {
      background: #fff7ed !important;
      border: 1.5px solid #fdba74 !important;
      color: #9a3412 !important;
      cursor: not-allowed !important;
      box-shadow: none !important;
      opacity: 1 !important;
    }

    .pill-child-c-waiting .pill-name,
    .pill-child-c-waiting .pill-num,
    .pill-child-c-waiting .pill-days {
      color: #9a3412 !important;
    }

    .pill-child-c-waiting .pill-dot {
      display: none !important;
    }

    .pill-child-c-waiting::after {
      content: "Waiting";
      position: absolute;
      right: 8px;
      top: 6px;
      background: #fed7aa;
      color: #9a3412;
      font-size: 10px;
      font-weight: 900;
      padding: 3px 7px;
      border-radius: 999px;
    }

    .wip-badge.child-c-waiting-badge {
      background: #fff7ed !important;
      color: #9a3412 !important;
      border: 1px solid #fdba74 !important;
    }

    .child-c-waiting-status {
      background: #fff7ed;
      color: #9a3412;
      border: 1px solid #fdba74;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 800;
      display: inline-flex;
    }
  `;
  document.head.appendChild(style);
}

function childCStableRemoveNotes() {
  document.querySelectorAll(".child-c-note").forEach(el => el.remove());
}

function childCIsNotFoundMessage(message) {
  return String(message || "")
    .toLowerCase()
    .includes("child job card is not found");
}


function childCStableAddNote(pill, message) {
  const card =
    pill.closest(".item-card") ||
    pill.closest(".qc-card") ||
    pill.closest(".job-card-item") ||
    pill.closest(".card") ||
    pill.closest(".item-block") ||
    pill.parentElement;

  if (!card) return;

  let note = card.querySelector(".child-c-note");

  if (!note) {
    note = document.createElement("div");
    note.className = "child-c-note";

    const processSection =
      card.querySelector(".process-pills-section") ||
      pill.closest(".process-pills-section");

    if (processSection) {
      processSection.insertAdjacentElement("beforebegin", note);
    } else {
      card.insertAdjacentElement("afterbegin", note);
    }
  }

  const jcNo = decodeURIComponent(pill.dataset.jcno || "");
  const itemName = decodeURIComponent(pill.dataset.item || "");
  const role = String(window.JMS_USER_ROLE || "").toLowerCase();
  const canOverride =
    role === "admin" ||
    role === "supervisor" ||
    window.JMS_IS_GAURANG_SPECIAL === true;

  note.innerHTML = "";

  const messageSpan = document.createElement("span");
  messageSpan.textContent = message;
  note.appendChild(messageSpan);

  if (canOverride) {
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "child-c-note-close";
    closeButton.innerHTML = "&times;";
    closeButton.title = "Continue Anyway";
    closeButton.setAttribute("aria-label", "Continue Anyway");

    closeButton.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();

      openChildCGateModal(
        jcNo,
        itemName,
        message
      );
    });

    note.appendChild(closeButton);
  }
}


window.__childCGateOverrideContext = null;


function openChildCGateModal(jobCardNo, itemName, message) {
  const modal = document.getElementById("child-c-gate-modal");

  if (!modal) {
    alert("Continue Anyway modal was not found.");
    return;
  }

  window.__childCGateOverrideContext = {
    jobCardNo: jobCardNo,
    itemName: itemName,
    message: message
  };

  const jcEl = document.getElementById("child-c-gate-job-card");
  const itemEl = document.getElementById("child-c-gate-item-name");
  const reasonEl = document.getElementById("child-c-gate-block-reason");
  const remarkEl = document.getElementById(
    "child-c-gate-override-reason"
  );

  if (jcEl) jcEl.textContent = jobCardNo;
  if (itemEl) itemEl.textContent = itemName;
  if (reasonEl) reasonEl.textContent = message;

  if (remarkEl && !remarkEl.value.trim()) {
    remarkEl.value =
      "Approved to continue without completion of the required child -C Job Card.";
  }

  modal.style.display = "flex";
}


function closeChildCGateModal() {
  const modal = document.getElementById("child-c-gate-modal");

  if (modal) {
    modal.style.display = "none";
  }

  window.__childCGateOverrideContext = null;
}


async function confirmChildCGateOverride() {
  const context = window.__childCGateOverrideContext;

  if (!context) {
    alert("Child gate override details are missing.");
    return;
  }

  const remarkEl = document.getElementById(
    "child-c-gate-override-reason"
  );

  const overrideReason = String(
    remarkEl ? remarkEl.value : ""
  ).trim();

  if (!overrideReason) {
    alert("Please enter an override remark.");
    return;
  }

  const button = document.getElementById(
    "child-c-gate-continue-btn"
  );

  if (button) {
    button.disabled = true;
    button.textContent = "Saving...";
  }

  try {
    const response = await fetch(
      "/api/quality_check/child_c_gate/continue_anyway",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          job_card_no: context.jobCardNo,
          item_name: context.itemName,
          override_reason: overrideReason
        })
      }
    );

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(
        data.error || "Unable to save Continue Anyway approval."
      );
    }

    delete window.__childCGateCache[context.jobCardNo];

    const jobCardNo = context.jobCardNo;

    closeChildCGateModal();

    const input = document.getElementById("jc-input");
    if (input) {
      input.value = jobCardNo;
    }

    await fetchJobCard();

  } catch (error) {
    alert(error.message || "Unable to save Continue Anyway approval.");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Continue Anyway";
    }
  }
}

function childCStableCleanTimeline() {
  const blockedPill = document.querySelector(".pill-child-c-waiting");
  if (!blockedPill) return;

  document.querySelectorAll("table").forEach(table => {
    const headers = Array.from(table.querySelectorAll("thead th")).map(th =>
      (th.textContent || "").trim().toLowerCase()
    );

    const stageIdx = headers.findIndex(h => h === "stage");
    const inDateIdx = headers.findIndex(h => h.includes("in date"));
    const outDateIdx = headers.findIndex(h => h.includes("out date"));
    const daysTakenIdx = headers.findIndex(h => h.includes("days taken"));
    const statusIdx = headers.findIndex(h => h.includes("status"));

    if (statusIdx < 0) return;

    table.querySelectorAll("tbody tr").forEach(row => {
      const cells = row.querySelectorAll("td");
      if (!cells.length) return;

      const stageText = stageIdx >= 0 ? (cells[stageIdx].textContent || "").trim().toUpperCase() : "";
      const statusText = (cells[statusIdx].textContent || "").trim().toLowerCase();

      if (stageText === "P1" || statusText.includes("in progress")) {
        if (inDateIdx >= 0) cells[inDateIdx].textContent = "-";
        if (outDateIdx >= 0) cells[outDateIdx].textContent = "-";
        if (daysTakenIdx >= 0) cells[daysTakenIdx].textContent = "0d";
        cells[statusIdx].innerHTML = '<span class="child-c-waiting-status">Waiting for Child Job Card</span>';
      }
    });
  });
}

async function childCStableApply() {
  childCStableEnsureStyle();

  const pills = Array.from(document.querySelectorAll(".proc-pill-v2[data-jcno][data-item]"));

  for (const pill of pills) {
    const isCurrent =
      pill.classList.contains("pill-current") ||
      pill.classList.contains("pill-subcontract");

    if (!isCurrent && !pill.classList.contains("pill-child-c-waiting")) continue;

    const jcNo = decodeURIComponent(pill.dataset.jcno || "");
    if (!jcNo) continue;

    const result = await childCStableCheck(jcNo);

    if (!result.allowed) {
      pill.classList.remove("pill-current");
      pill.classList.add("pill-child-c-waiting");
      pill.setAttribute("data-child-c-blocked", "1");
      pill.title = result.message;

      const days = pill.querySelector(".pill-days");
      if (days) days.textContent = "Waiting for Child JC";

      const iIdx = pill.dataset.iidx;
      const wipBadge = document.getElementById("wip-badge-" + iIdx);

      if (wipBadge) {
        wipBadge.classList.add("child-c-waiting-badge");
        wipBadge.textContent = "Waiting for Child JC";
      }

      const wipDays = document.getElementById("wip-days-" + iIdx);

      if (wipDays) {
        const waitingDays = String(
          wipDays.dataset.days || ""
        ).trim();

        if (waitingDays) {
          wipDays.textContent =
            "Waiting for " + waitingDays + " days";
        }
      }

      childCStableAddNote(pill, result.message);
      childCStableCleanTimeline();
    }
  }
}

/* Stop modal before opening */
if (typeof openStageModal === "function" && !window.__childCStableOpenWrapped) {
  window.__childCStableOpenWrapped = true;
  const originalOpenStageModal = openStageModal;

  openStageModal = async function (pillEl) {
    const jcNo = decodeURIComponent(pillEl && pillEl.dataset ? pillEl.dataset.jcno || "" : "");

    if (jcNo) {
      const result = await childCStableCheck(jcNo);

      if (!result.allowed) {
        childCStableEnsureStyle();

        pillEl.classList.remove("pill-current");
        pillEl.classList.add("pill-child-c-waiting");
        pillEl.title = result.message;

        const days = pillEl.querySelector(".pill-days");
        if (days) days.textContent = "Waiting for Child JC";

        childCStableAddNote(pillEl, result.message);
        childCStableCleanTimeline();

        return;
      }
    }

    return originalOpenStageModal.apply(this, arguments);
  };
}

/* Re-apply after job card fetch */
if (typeof fetchJobCard === "function" && !window.__childCStableFetchWrapped) {
  window.__childCStableFetchWrapped = true;
  const originalFetchJobCard = fetchJobCard;

  fetchJobCard = async function () {
    window.__childCGateCache = {};
    const result = await originalFetchJobCard.apply(this, arguments);
    setTimeout(childCStableApply, 350);
    setTimeout(childCStableApply, 900);
    return result;
  };
}

document.addEventListener("DOMContentLoaded", function () {
  childCStableEnsureStyle();
  setTimeout(childCStableApply, 500);
});

document.addEventListener("click", function () {
  setTimeout(childCStableCleanTimeline, 150);
});

/* CHILD_C_STABLE_GATE_UI_END */

/* CHILD_C_NOTE_DEDUPE_FIX_START */

/*
  Remove duplicate child -C waiting notes.
  Keep only one clean note per job card item.
*/

function childCRemoveDuplicateNotes() {
  // Remove old class notes from previous patches
  document.querySelectorAll(".child-c-block-banner").forEach(el => el.remove());

  const cards = document.querySelectorAll(".item-card, .qc-card, .job-card-item, .card, .item-block");

  if (cards.length) {
    cards.forEach(card => {
      const notes = Array.from(card.querySelectorAll(".child-c-note"));
      notes.forEach((note, index) => {
        if (index > 0) note.remove();
      });
    });
  } else {
    const notes = Array.from(document.querySelectorAll(".child-c-note"));
    notes.forEach((note, index) => {
      if (index > 0) note.remove();
    });
  }
}

/* Wrap stable apply to dedupe after render */
if (typeof childCStableApply === "function" && !window.__childCNoteDedupeWrapped) {
  window.__childCNoteDedupeWrapped = true;
  const oldChildCStableApply = childCStableApply;

  childCStableApply = async function () {
    const result = await oldChildCStableApply.apply(this, arguments);
    setTimeout(childCRemoveDuplicateNotes, 50);
    setTimeout(childCRemoveDuplicateNotes, 300);
    return result;
  };
}

/* Dedupe after clicks and page render */
document.addEventListener("DOMContentLoaded", function () {
  setTimeout(childCRemoveDuplicateNotes, 500);
  setTimeout(childCRemoveDuplicateNotes, 1000);
});

document.addEventListener("click", function () {
  setTimeout(childCRemoveDuplicateNotes, 100);
  setTimeout(childCRemoveDuplicateNotes, 400);
});

/* CHILD_C_NOTE_DEDUPE_FIX_END */

/* CHILD_C_JC_LINK_FIX_START */

/*
  Make child -C job card number clickable.
  Example:
  Waiting for child job card 0000113182 to complete first.
  Clicking 0000113182 loads that job card on Page 3.
*/

function childCEscapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function childCOpenJobCard(jobCardNo) {
  const jc = String(jobCardNo || "").trim();
  if (!jc) return;

  const input =
    document.querySelector("#job-card-no") ||
    document.querySelector("#jobCardNo") ||
    document.querySelector("#job_card_no") ||
    document.querySelector("input[name='job_card_no']") ||
    document.querySelector("input[placeholder*='Job Card']") ||
    document.querySelector("input[type='text']");

  if (input) {
    input.value = jc;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  const newUrl = "/page3?job_card_no=" + encodeURIComponent(jc);
  window.history.pushState({}, "", newUrl);

  if (typeof fetchJobCard === "function") {
    fetchJobCard();
    return;
  }

  const fetchBtn = Array.from(document.querySelectorAll("button")).find(btn =>
    /fetch records/i.test(btn.textContent || "")
  );

  if (fetchBtn) {
    fetchBtn.click();
    return;
  }

  window.location.href = newUrl;
}

function childCMessageToHtml(message) {
  const msg = String(message || "");
  const match = msg.match(/job card\s+([0-9]+)/i);

  if (!match) {
    return childCEscapeHtml(msg);
  }

  const jc = match[1];

  return childCEscapeHtml(msg).replace(
    jc,
    `<a href="/page3?job_card_no=${encodeURIComponent(jc)}" class="child-c-jc-link" data-jc="${childCEscapeHtml(jc)}">${childCEscapeHtml(jc)}</a>`
  );
}

/* Override note renderer to allow clickable JC link */
if (typeof childCStableAddNote === "function" && !window.__childCJcLinkNoteWrapped) {
  window.__childCJcLinkNoteWrapped = true;

  childCStableAddNote = function (pill, message) {
    const card =
      pill.closest(".item-card") ||
      pill.closest(".qc-card") ||
      pill.closest(".job-card-item") ||
      pill.closest(".card") ||
      pill.closest(".item-block") ||
      pill.parentElement;

    if (!card) return;

    let note = card.querySelector(".child-c-note");

    if (!note) {
      note = document.createElement("div");
      note.className = "child-c-note";

      const processSection =
        card.querySelector(".process-pills-section") ||
        pill.closest(".process-pills-section");

      if (processSection) {
        processSection.insertAdjacentElement("beforebegin", note);
      } else {
        card.insertAdjacentElement("afterbegin", note);
      }
    }

    note.innerHTML =
      '<span class="child-c-note-message">' +
      childCMessageToHtml(message) +
      '</span>';

    const jcNo = decodeURIComponent(pill.dataset.jcno || "");
    const itemName = decodeURIComponent(pill.dataset.item || "");
    const role = String(window.JMS_USER_ROLE || "").toLowerCase();

    const canOverride =
      role === "admin" ||
      role === "supervisor" ||
      window.JMS_IS_GAURANG_SPECIAL === true;

    if (canOverride && childCIsNotFoundMessage(message)) {
      const closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "child-c-note-close";
      closeButton.innerHTML = "&times;";
      closeButton.title = "Continue Anyway";
      closeButton.setAttribute("aria-label", "Continue Anyway");

      closeButton.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();

        openChildCGateModal(
          jcNo,
          itemName,
          message
        );
      });

      note.appendChild(closeButton);
    }
  };
}

/* Click handler for child job card link */
document.addEventListener("click", function (event) {
  const link = event.target.closest(".child-c-jc-link[data-jc]");
  if (!link) return;

  event.preventDefault();
  event.stopPropagation();

  childCOpenJobCard(link.dataset.jc);
});

/* Auto-load if page opened with /page3?job_card_no=0000113182 */
document.addEventListener("DOMContentLoaded", function () {
  const params = new URLSearchParams(window.location.search);
  const jc = params.get("job_card_no");

  if (jc) {
    setTimeout(() => childCOpenJobCard(jc), 300);
  }
});

/* Link style */
(function addChildCJcLinkStyle() {
  if (document.getElementById("child-c-jc-link-style")) return;

  const style = document.createElement("style");
  style.id = "child-c-jc-link-style";
  style.textContent = `
    .child-c-jc-link {
      color: #075bb5 !important;
      font-weight: 900 !important;
      text-decoration: underline !important;
      cursor: pointer !important;
    }

    .child-c-jc-link:hover {
      color: #0f3f7a !important;
    }
  `;
  document.head.appendChild(style);
})();

/* CHILD_C_JC_LINK_FIX_END */
// ?? Operator Card View ?????????????????????????????????????????????????????
let operatorCards = [];
let operatorCompletedCards = [];
let operatorPage = 0;
let _operatorActiveIdx = null;

const OPERATOR_PAGE_SIZE = 6;


function operatorEnsureUxStyles() {
  if (document.getElementById("operator-ux-styles")) return;

  const style = document.createElement("style");
  style.id = "operator-ux-styles";
  style.textContent = `
    .operator-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }

    .operator-job-card {
      position: relative;
      border: 1px solid var(--border);
      border-radius: 14px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      background: var(--surface, #fff);
      transition:
        transform .28s ease,
        opacity .35s ease,
        box-shadow .28s ease,
        border-color .28s ease;
    }

    .operator-job-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 10px 28px rgba(15, 42, 77, .10);
    }

    .operator-job-card.operator-card-success {
      border-color: #22c55e;
      box-shadow: 0 0 0 4px rgba(34, 197, 94, .14);
      transform: scale(.985);
    }

    .operator-success-overlay {
      position: absolute;
      inset: 0;
      z-index: 8;
      background: rgba(240, 253, 244, .97);
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      animation: operatorSuccessIn .28s ease both;
    }

    .operator-success-check {
      width: 58px;
      height: 58px;
      margin: 0 auto 10px;
      border-radius: 50%;
      background: #16a34a;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 27px;
      box-shadow: 0 8px 22px rgba(22, 163, 74, .25);
    }

    .operator-modal-panel {
      background: var(--surface, #fff);
      border-radius: 16px;
      width: min(94vw, 590px);
      max-height: 92vh;
      overflow-y: auto;
      border: 1px solid var(--border);
      box-shadow: 0 24px 70px rgba(15, 23, 42, .24);
      animation: operatorModalIn .24s ease both;
    }

    .operator-outcome-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .operator-outcome-box {
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      min-width: 0;
    }

    .operator-outcome-box.ok {
      background: #f0fdf4;
      border-color: #86efac;
    }

    .operator-outcome-box.not-ok {
      background: #fef2f2;
      border-color: #fecaca;
    }

    .operator-outcome-box.hold {
      background: #fffbeb;
      border-color: #fde68a;
    }

    .operator-qty-control {
      margin-top: 8px;
      display: grid;
      grid-template-columns: 34px minmax(42px, 1fr) 34px;
      gap: 5px;
      align-items: center;
    }

    .operator-qty-control button {
      height: 36px;
      border: 1px solid var(--border);
      background: #fff;
      border-radius: 7px;
      font-size: 18px;
      font-weight: 900;
      cursor: pointer;
    }

    .operator-qty-control input,
    .operator-ok-input {
      width: 100%;
      height: 36px;
      box-sizing: border-box;
      text-align: center;
      border: 1px solid var(--border);
      border-radius: 7px;
      background: #fff;
      font-size: 16px;
      font-weight: 900;
      color: var(--text);
    }

    .operator-ok-input {
      margin-top: 8px;
      color: #15803d;
      border-color: #86efac;
    }

    .operator-qty-equation {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 9px;
      background: var(--surface-secondary, #f8fafc);
      color: var(--text);
      font-size: 12px;
      font-weight: 800;
      text-align: center;
    }

    .operator-qty-equation.invalid {
      background: #fef2f2;
      color: #b91c1c;
    }

    @keyframes operatorModalIn {
      from { opacity: 0; transform: translateY(10px) scale(.985); }
      to   { opacity: 1; transform: translateY(0) scale(1); }
    }

    @keyframes partialPulse {
      0%, 100% { opacity: 1; }
      50% { opacity: .7; }
    }

    @keyframes operatorSuccessIn {
      from { opacity: 0; transform: scale(.96); }
      to   { opacity: 1; transform: scale(1); }
    }

    @media (max-width: 1050px) {
      .operator-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }

    @media (max-width: 680px) {
      .operator-grid {
        grid-template-columns: 1fr;
      }

      .operator-outcome-grid {
        grid-template-columns: 1fr;
      }
    }

  `;

  document.head.appendChild(style);
}


function operatorNumber(value, fallback = 0) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}


function operatorAvailableQty(card) {
  // OPERATOR_STAGE_QTY_SCOPE_V1
  if (card?.is_partial) {
    const pendingQty = operatorNumber(card?.pending_qty, 0);
    const holdQty = operatorNumber(card?.hold_qty, 0);
    const remaining = pendingQty + holdQty;
    if (remaining > 0) return remaining;
  }

  const previousOkQty = operatorNumber(card?.actual_qty, 0);
  const previousRejectedQty = operatorNumber(card?.rejected_qty, 0);

  if (previousOkQty > 0 || previousRejectedQty > 0) {
    return Math.max(0, previousOkQty);
  }

  const jobCardQty = operatorNumber(card?.job_card_qty, 0);
  if (jobCardQty > 0) {
    return jobCardQty;
  }

  return Math.max(0, operatorNumber(card?.so_qty, 0));
}


async function loadOperatorView() {
  if (!IS_OPERATOR_READ_ONLY) return;

  operatorEnsureUxStyles();

  const container = document.getElementById("operator-view");
  if (!container) return;

  container.innerHTML = `
    <div style="padding:32px;text-align:center;color:var(--muted);">
      Loading your job cards...
    </div>
  `;

  try {
    const res = await fetch("/api/operator/job_cards");
    const data = await res.json();

    if (!data.success) {
      container.innerHTML = `
        <div style="padding:32px;text-align:center;color:#dc2626;">
          ${esc(data.error || "Unable to load job cards")}
        </div>
      `;
      return;
    }

    operatorCards = data.job_cards || [];
    operatorPage = 0;
    renderOperatorGrid();
  } catch (error) {
    container.innerHTML = `
      <div style="padding:32px;text-align:center;color:#dc2626;">
        Error loading job cards
      </div>
    `;
  }
}


async function loadRecentlyCompleted() {
  try {
    const res = await fetch("/api/operator/recent_completions");
    const data = await res.json();
    if (data.success) {
      operatorCompletedCards = data.completions
        || data.completed_job_cards
        || [];
    }
  } catch (e) {
    console.error("Failed to load recent completions", e);
  }
  renderRecentlyCompleted();
}


function renderRecentlyCompleted() {
  const container = document.getElementById("operator-completed-section");
  if (!container) return;

  if (!operatorCompletedCards.length) {
    container.innerHTML = `
      <div style="
        background:#f0fdf4;
        border-radius:14px;
        border:1px solid #86efac;
        padding:24px;
        margin-top:0;
        box-shadow:0 1px 8px rgba(22,163,74,0.08);
      ">
        <div style="
          display:flex;
          align-items:center;
          gap:10px;
          margin-bottom:6px;
        ">
          <span style="
            width:28px;height:28px;
            background:#f0fdf4;
            border-radius:50%;
            display:flex;align-items:center;justify-content:center;
            color:#16a34a;font-size:14px;
          "><i class="fa fa-check-circle"></i></span>
          <span style="font-size:16px;font-weight:800;color:#111;">
            Recently Completed
          </span>
          <span style="
            margin-left:auto;
            background:#f3f4f6;
            border-radius:20px;
            padding:2px 10px;
            font-size:13px;
            font-weight:700;
            color:#6b7280;
          ">0</span>
        </div>
        <div style="font-size:13px;color:#9ca3af;margin-top:4px;">
          No completions yet this session.
        </div>
      </div>
    `;
    return;
  }

  const cards = operatorCompletedCards.map(function(card) {
    const okQty = operatorNumber(card.ok_qty, 0);
    const notOkQty = operatorNumber(card.not_ok_qty || card.rejected_qty, 0);
    const holdQty = operatorNumber(card.hold_qty, 0);

    const completedAt = card.completed_at
      ? new Date(card.completed_at).toLocaleString("en-IN", {
          month: "short", day: "numeric",
          hour: "2-digit", minute: "2-digit"
        })
      : "";

    return `
      <div style="
        background:#fff;
        border-radius:10px;
        border:1px solid #e5e7eb;
        border-left:4px solid #16a34a;
        padding:14px 16px;
        min-width:280px;
        max-width:340px;
        flex-shrink:0;
      ">
        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          margin-bottom:6px;
        ">
          <span style="
            font-size:14px;font-weight:900;color:#1d4ed8;
          ">${esc(card.job_card_no)}</span>
          <span style="
            font-size:11px;font-weight:700;
            color:#16a34a;
            background:#f0fdf4;
            border:1px solid #bbf7d0;
            border-radius:20px;
            padding:2px 8px;
          "><i class="fa fa-check"></i> COMPLETED</span>
        </div>

        <div style="
          font-size:13px;font-weight:600;color:#374151;
          margin-bottom:8px;
          white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
        " title="${esc(card.item_name)}">${esc(card.item_name)}</div>

        <div style="
          font-size:12px;color:#6b7280;
          margin-bottom:10px;
          display:flex;align-items:center;gap:6px;
        ">
          <span>${esc(card.old_stage)}</span>
          <span>→</span>
          <span style="font-weight:700;color:#374151;">${esc(card.new_stage)}</span>
        </div>

        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
          <span style="
            background:#f0fdf4;border:1px solid #bbf7d0;
            color:#15803d;border-radius:20px;
            padding:3px 10px;font-size:12px;font-weight:700;
          ">OK ${okQty}</span>
          <span style="
            background:#fef2f2;border:1px solid #fecaca;
            color:#dc2626;border-radius:20px;
            padding:3px 10px;font-size:12px;font-weight:700;
          ">Not OK ${notOkQty}</span>
          <span style="
            background:#fffbeb;border:1px solid #fde68a;
            color:#92400e;border-radius:20px;
            padding:3px 10px;font-size:12px;font-weight:700;
          ">Hold ${holdQty}</span>
        </div>

        <div style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          border-top:1px solid #f3f4f6;
          padding-top:10px;
          gap:8px;
        ">
          <span style="font-size:11px;color:#9ca3af;">${completedAt}</span>
          <button
            onclick="openOperatorUndoModalV2(${operatorNumber(card.id, 0)},'${esc(card.job_card_no)}','${esc(card.item_name)}')"
            style="
              background:#fff;
              border:1px solid #fbbf24;
              color:#92400e;
              border-radius:8px;
              padding:5px 12px;
              font-size:12px;
              font-weight:700;
              cursor:pointer;
            "
          ><i class="fa fa-undo"></i> Undo</button>
        </div>
      </div>
    `;
  }).join("");

  container.innerHTML = `
    <div style="
      background:#f0fdf4;
      border-radius:14px;
      border:1px solid #bbf7d0;
      padding:24px;
      margin-top:0;
      box-shadow:0 1px 8px rgba(22,163,74,0.06);
    ">
      <div style="
        display:flex;
        align-items:center;
        gap:10px;
        margin-bottom:16px;
      ">
        <span style="
          width:28px;height:28px;
          background:#bbf7d0;
          border-radius:50%;
          display:flex;align-items:center;justify-content:center;
          color:#15803d;font-size:13px;
        "><i class="fa fa-check-circle"></i></span>
        <span style="font-size:16px;font-weight:800;color:#15803d;">
          Recently Completed
        </span>
        <span style="
          margin-left:auto;
          background:#f3f4f6;
          border-radius:20px;
          padding:2px 10px;
          font-size:13px;
          font-weight:700;
          color:#6b7280;
        ">${operatorCompletedCards.length}</span>
      </div>
      <div style="
        display:flex;
        gap:14px;
        overflow-x:auto;
        padding-bottom:6px;
      ">
        ${cards}
      </div>
    </div>
  `;
}


function renderOperatorGrid() {
  operatorEnsureUxStyles();

  const container = document.getElementById("operator-view");
  if (!container) return;

  if (!operatorCards.length) {
    container.innerHTML = `
      <div style="
        background:#fff;
        border-radius:12px;
        border:1px solid #e5e7eb;
        padding:48px;
        text-align:center;
        margin-bottom:20px;
      ">
        <div style="
          width:56px;height:56px;
          margin:0 auto 16px;
          border-radius:50%;
          background:#f0fdf4;
          color:#16a34a;
          display:flex;align-items:center;
          justify-content:center;
          font-size:24px;
        "><i class="fa fa-check-circle"></i></div>
        <div style="font-size:18px;font-weight:900;color:#111;margin-bottom:6px;">
          All done!
        </div>
        <div style="font-size:14px;color:#6b7280;">
          No pending job cards for your assigned processes.
        </div>
      </div>
      <div style="margin:28px 0 24px;border-top:2px solid #e2e8f0;"></div>
      <div id="operator-completed-section"></div>
    `;
    renderRecentlyCompleted();
    return;
  }

  const start = operatorPage * OPERATOR_PAGE_SIZE;
  const pageCards = operatorCards.slice(start, start + OPERATOR_PAGE_SIZE);
  const total = operatorCards.length;
  const totalPages = Math.ceil(total / OPERATOR_PAGE_SIZE);

  const cardsHtml = pageCards.map(function(card, idx) {
    const globalIdx = start + idx;
    const availableQty = operatorAvailableQty(card);
    const remainingDays = operatorNumber(card.remaining_days, 0);
    const isOverdue = card.status === "Overdue";
    const isDueSoon = !isOverdue && remainingDays <= 3;
    const isPartial = card.is_partial === true;

    const deliveryLabel = remainingDays < 0
      ? Math.abs(remainingDays) + "d overdue"
      : remainingDays === 0
        ? "Due today"
        : remainingDays + "d left";

    const deliveryColor = remainingDays <= 0
      ? "#dc2626"
      : remainingDays <= 3
        ? "#f59e0b"
        : "#16a34a";

    const leftBorderColor = isPartial
      ? "#f59e0b"
      : isOverdue
        ? "#ef4444"
        : "#3b82f6";

    const statusDot = isOverdue ? "#dc2626" : isDueSoon ? "#f59e0b" : "#16a34a";
    const statusLabel = isOverdue ? "Overdue" : isDueSoon ? "Due soon" : "On time";

    const prevHtml = card.prev_process
      ? `<span style="color:#000000;">${esc(card.prev_process)}</span>
         <span style="color:#000000;margin:0 4px;">→</span>`
      : "";

    const nextHtml = card.next_process
      ? `<span style="color:#000000;margin:0 4px;">→</span>
         <span style="color:#000000;">${esc(card.next_process)}</span>`
      : "";

    // Qty badges — only shown when any qty has been recorded
    const okQty = operatorNumber(card.actual_qty, 0);
    const notOkQty = operatorNumber(card.rejected_qty, 0);
    const holdQty = operatorNumber(card.hold_qty, 0);
    const pendingQty = operatorNumber(card.pending_qty, 0);
    const hasQty = okQty > 0 || notOkQty > 0 || holdQty > 0;

    const qtyBadgeItems = [];
    if (okQty > 0) qtyBadgeItems.push('<span style="background:#f0fdf4;border:1px solid #bbf7d0;color:#15803d;border-radius:20px;padding:4px 12px;font-size:13px;font-weight:800;"><i class=\"fa fa-check\"></i> ' + okQty + '</span>');
    if (notOkQty > 0) qtyBadgeItems.push('<span style="background:#fef2f2;border:1px solid #fecaca;color:#dc2626;border-radius:20px;padding:4px 12px;font-size:13px;font-weight:800;"><i class=\"fa fa-times\"></i> ' + notOkQty + '</span>');
    if (holdQty > 0) qtyBadgeItems.push('<span style="background:#fffbeb;border:1px solid #fde68a;color:#92400e;border-radius:20px;padding:4px 12px;font-size:13px;font-weight:800;"><i class=\"fa fa-pause\"></i> ' + holdQty + '</span>');
    if (isPartial && pendingQty > 0) qtyBadgeItems.push('<span style="background:#fff7ed;border:1px solid #fed7aa;color:#c2410c;border-radius:20px;padding:4px 12px;font-size:13px;font-weight:800;"><i class=\"fa fa-clock-o\"></i> ' + pendingQty + '</span>');

    const qtyBadges = qtyBadgeItems.length ? '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">' + qtyBadgeItems.join('') + '</div>' : "";

    const partialBadge = isPartial ? `
      <span style="
        background:#c2410c;
        color:#fff;
        border-radius:20px;
        padding:4px 12px;
        font-size:12px;
        font-weight:800;
        margin-left:8px;
        letter-spacing:.5px;
        display:inline-flex;
        align-items:center;
        gap:5px;
        animation:partialPulse 2s ease-in-out infinite;
      "><i class="fa fa-clock-o"></i> PARTIAL</span>
    ` : "";

    return `
      <div
        class="operator-job-card"
        data-operator-card-index="${globalIdx}"
        style="
          background:#fff;
          border-radius:12px;
          border:1px solid ${isPartial ? '#fed7aa' : '#e5e7eb'};
          border-left:6px solid ${leftBorderColor};
          box-shadow:${isPartial ? '0 2px 12px rgba(194,65,12,0.12)' : '0 1px 4px rgba(0,0,0,0.06)'};
          overflow:hidden;
          display:flex;
          flex-direction:column;
        "
      >
        <!-- Card Header -->
        <div style="
          padding:12px 16px;
          border-bottom:1px solid #f3f4f6;
          background:#f9fafb;
          display:flex;
          justify-content:space-between;
          align-items:center;
        ">
          <div>
            <span style="
              font-size:15px;font-weight:900;color:#1d4ed8;
            ">${esc(card.job_card_no)}</span>
            ${partialBadge}
          </div>
          <span style="
            font-size:13px;font-weight:700;color:${deliveryColor};
            white-space:nowrap;
          ">${deliveryLabel}</span>
        </div>

        <!-- Card Body -->
        <div style="padding:14px 16px;flex:1;">
          <div style="
            font-size:14px;font-weight:700;color:#111;
            margin-bottom:12px;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
          " title="${esc(card.item_name)}">${esc(card.item_name)}</div>

          <div style="
            font-size:13px;text-transform:uppercase;
            letter-spacing:.5px;color:#000000;
            margin-bottom:4px;
          ">Current Process</div>

          <div style="
            font-size:24px;font-weight:900;color:#111;
            margin-bottom:12px;line-height:1.1;
          ">${esc(card.current_process)}</div>

          <div style="
            display:flex;gap:20px;
            margin-bottom:12px;flex-wrap:wrap;
          ">
            <div>
              <div style="font-size:13px;color:#000000;">Lead</div>
              <div style="font-size:14px;font-weight:800;color:#374151;">
                ${operatorNumber(card.lead_days, 0)}d
              </div>
            </div>
            <div>
              <div style="font-size:13px;color:#000000;">In stage</div>
              <div style="font-size:14px;font-weight:800;color:#374151;">
                ${operatorNumber(card.days_in_stage, 0)}d
              </div>
            </div>
            <div>
              <div style="font-size:13px;color:#000000;">Job Card Qty</div>
              <div style="font-size:14px;font-weight:800;color:#374151;">
                ${operatorNumber(card.job_card_qty, 0)}
              </div>
            </div>
          </div>

          ${qtyBadges}

          <div style="
            font-size:14px;color:#000000;
            display:flex;align-items:center;gap:4px;
            flex-wrap:wrap;
          ">
            ${prevHtml}
            <span style="font-weight:700;color:#374151;">
              ${esc(card.current_process)}
            </span>
            ${nextHtml}
          </div>

          <div style="
            display:flex;align-items:center;gap:6px;
            margin-top:10px;
          ">
            <span style="
              width:7px;height:7px;border-radius:50%;
              background:${statusDot};display:inline-block;
            "></span>
            <span style="
              font-size:14px;font-weight:700;
              color:${statusDot};
            ">${statusLabel}</span>
          </div>
        </div>

        <!-- Complete Button -->
        <div style="padding:12px 16px;border-top:1px solid #f3f4f6;">
          <button
            onclick="openOperatorCompleteModal(${globalIdx})"
            style="
              width:100%;
              padding:16px;
              background:${isPartial ? '#c2410c' : '#1e3a5f'};
              color:#fff;
              border:0;
              border-radius:10px;
              font-size:16px;
              font-weight:800;
              cursor:pointer;
              letter-spacing:.3px;
              min-height:54px;
              display:flex;
              align-items:center;
              justify-content:center;
              gap:8px;
            "
          ><i class="fa ${isPartial ? 'fa-arrow-right' : 'fa-check'}"></i> ${isPartial ? "Continue process" : "Complete process"}</button>
        </div>
      </div>
    `;
  }).join("");

  const paginationHtml = totalPages > 1 ? `
    <div style="
      display:flex;
      justify-content:space-between;
      align-items:center;
      padding:12px 0;
      margin-top:8px;
    ">
      <button
        onclick="operatorPrevPage()"
        ${operatorPage === 0 ? "disabled" : ""}
        style="
          padding:8px 18px;
          border:1px solid #e5e7eb;
          border-radius:8px;
          background:#fff;
          color:${operatorPage === 0 ? "#d1d5db" : "#374151"};
          font-weight:700;
          cursor:${operatorPage === 0 ? "default" : "pointer"};
        "
      >← Prev</button>

      <span style="font-size:13px;color:#6b7280;">
        Showing ${start + 1}–${Math.min(start + OPERATOR_PAGE_SIZE, total)} of ${total} job cards
      </span>

      <button
        onclick="operatorNextPage()"
        ${operatorPage >= totalPages - 1 ? "disabled" : ""}
        style="
          padding:8px 18px;
          border:1px solid #e5e7eb;
          border-radius:8px;
          background:#fff;
          color:${operatorPage >= totalPages - 1 ? "#d1d5db" : "#374151"};
          font-weight:700;
          cursor:${operatorPage >= totalPages - 1 ? "default" : "pointer"};
        "
      >Next →</button>
    </div>
  ` : "";

  container.innerHTML = `
    <div style="
      background:#ffffff;
      border-radius:14px;
      border:1px solid #e2e8f0;
      padding:24px;
      margin-bottom:0;
      box-shadow:0 1px 8px rgba(0,0,0,0.04);
    ">
      <div style="
        display:flex;align-items:center;gap:10px;margin-bottom:16px;
      ">
        <span style="
          width:28px;height:28px;background:#eff6ff;border-radius:50%;
          display:flex;align-items:center;justify-content:center;
          color:#1d4ed8;font-size:13px;
        "><i class="fa fa-tasks"></i></span>
        <span style="font-size:16px;font-weight:800;color:#111;">
          Active Jobs
        </span>
        <span style="
          margin-left:auto;
          background:#f3f4f6;border-radius:20px;
          padding:2px 10px;font-size:13px;font-weight:700;color:#6b7280;
        ">${total}</span>
      </div>

      <div class="operator-grid" style="
        display:grid;
        grid-template-columns:repeat(auto-fill,minmax(280px,1fr));
        gap:16px;
      ">
        ${cardsHtml}
      </div>

      ${paginationHtml}
    </div>

    <div id="operator-completed-section" style="margin-top:24px;"></div>
  `;

  renderRecentlyCompleted();
}


/* OEE_OPERATOR_INPUT_UI_V1_START */
function operatorOeeIsApplicable(card) {
  const processName = String(
    card?.current_process || card?.wip_status || ""
  ).trim().toLowerCase();

  // OEE_PROCESS_PREFIX_SUPPORT_V1
  // Covers CNC/VMC variants such as:
  // CNC Machining, CNC Machining 1st Side, CNC Machining 2nd Side, etc.
  return (
    processName.startsWith("cnc machining") ||
    processName.startsWith("vmc machining")
  );
}

async function loadOperatorOeeMasterData() {
  const machineSelect = document.getElementById("operator-oee-machine");
  const lossesContainer = document.getElementById("operator-oee-losses");

  // OEE_LOSS_3_COLUMN_UI_V1
  lossesContainer.style.display = "grid";
  lossesContainer.style.gridTemplateColumns = "repeat(3, minmax(0, 1fr))";
  lossesContainer.style.gridTemplateRows = "repeat(9, auto)";
  lossesContainer.style.gridAutoFlow = "column";
  lossesContainer.style.columnGap = "12px";
  lossesContainer.style.rowGap = "8px";

  if (!machineSelect || !lossesContainer) return;

  try {
    const response = await fetch("/api/oee/master-data");
    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || "Unable to load OEE master data.");
    }

    machineSelect.innerHTML =
      '<option value="">-- Select Machine --</option>';

    (data.machines || []).forEach(function (machine) {
      const option = document.createElement("option");
      option.value = machine.id;

      const zoneText = machine.zone
        ? ` | Zone ${machine.zone}`
        : "";

      option.textContent =
        `${machine.machine_no} | ${machine.machine_name}${zoneText}`;

      option.dataset.machineNo = machine.machine_no || "";
      option.dataset.machineName = machine.machine_name || "";
      option.dataset.machineCategory = machine.machine_category || "";
      option.dataset.zone = machine.zone || "";

      machineSelect.appendChild(option);
    });

    lossesContainer.innerHTML = "";

    (data.loss_types || []).forEach(function (loss) {
      const row = document.createElement("div");
      row.style.cssText =
        "display:grid;" +
        "grid-template-columns:minmax(0,1fr) 90px;" +
        "gap:8px;" +
        "align-items:center;" +
        "padding:8px 10px;" +
        "border:1px solid #e5e7eb;" +
        "border-radius:8px;" +
        "background:#fff;";

      const label = document.createElement("label");
      label.htmlFor = `operator-oee-loss-${loss.loss_code}`;
      label.style.cssText =
        "font-size:12px;" +
        "line-height:1.35;" +
        "color:#334155;" +
        "font-weight:600;";
      label.textContent =
        `${loss.loss_code} - ${loss.loss_name || ""}`;

      const input = document.createElement("input");
      input.type = "number";
      input.id = `operator-oee-loss-${loss.loss_code}`;
      input.dataset.lossId = loss.id;
      input.dataset.lossCode = loss.loss_code;
      input.min = "0";
      input.step = "any";
      input.value = "0";
      input.placeholder = "Min";
      input.style.cssText =
        "width:100%;" +
        "box-sizing:border-box;" +
        "padding:8px 7px;" +
        "border:1px solid #cbd5e1;" +
        "border-radius:7px;" +
        "font-size:13px;" +
        "text-align:right;";

      row.appendChild(label);
      row.appendChild(input);
      lossesContainer.appendChild(row);
    });

  
    // OEE_ORIGINAL_TWO_COLUMN_UI_RESTORE
    lossesContainer.style.display = "grid";
    lossesContainer.style.gridTemplateColumns = "repeat(2, minmax(0, 1fr))";
    lossesContainer.style.gridTemplateRows = "";
    lossesContainer.style.gridAutoFlow = "row";
    lossesContainer.style.columnGap = "10px";
    lossesContainer.style.rowGap = "8px";

  } catch (error) {
    machineSelect.innerHTML =
      '<option value="">Unable to load machines</option>';

    lossesContainer.innerHTML =
      '<div style="color:#b91c1c;font-size:13px;">' +
      'Unable to load OEE loss master.' +
      '</div>';

    console.error("OEE master-data load failed:", error);
  }
}
/* OEE_OPERATOR_INPUT_UI_V1_END */

function openOperatorCompleteModal(globalIdx) {
  _operatorActiveIdx = globalIdx;

  const card = operatorCards[globalIdx];

  // Ensure modal container exists in DOM
  let modal = document.getElementById("operator-complete-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "operator-complete-modal";
    modal.style.cssText = "display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);align-items:center;justify-content:center;";
    document.body.appendChild(modal);
  }

  if (!card) return;

  const availableQty = operatorAvailableQty(card);
  const nextProcess = card.next_process || "Store";

  const isOeeProcess = operatorOeeIsApplicable(card);

  const oeeProcessName = String(
    card.current_process || card.wip_status || ""
  ).trim();

  const oeeSectionHtml = isOeeProcess ? `
    <div
      id="operator-oee-section"
      style="
        margin:10px 20px 4px;
        padding:16px;
        border:1px solid #93c5fd;
        border-radius:10px;
        background:#f8fbff;
      "
    >
      <div style="
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:10px;
        margin-bottom:14px;
      ">
        <div>
          <div style="font-size:16px;font-weight:900;color:#1e3a5f;">
            OEE Entry
          </div>
          <div style="font-size:12px;color:#64748b;margin-top:2px;">
            ${esc(oeeProcessName)}
          </div>
        </div>
        <span style="
          padding:4px 9px;
          border-radius:20px;
          background:#dbeafe;
          color:#1d4ed8;
          font-size:11px;
          font-weight:800;
        ">CNC / VMC</span>
      </div>

      <div style="
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:12px;
      ">
        <div>
          <label style="display:block;margin-bottom:5px;font-size:11px;font-weight:900;color:#475569;text-transform:uppercase;">Date</label>
          <input type="date" id="operator-oee-date" style="width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #cbd5e1;border-radius:8px;">
        </div>

        <div>
          <label style="display:block;margin-bottom:5px;font-size:11px;font-weight:900;color:#475569;text-transform:uppercase;">Shift</label>
          <input type="text" id="operator-oee-shift" placeholder="Enter shift" autocomplete="off" style="width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #cbd5e1;border-radius:8px;">
        </div>

        <div style="grid-column:1 / -1;">
          <label style="display:block;margin-bottom:5px;font-size:11px;font-weight:900;color:#475569;text-transform:uppercase;">Machine</label>
          <select id="operator-oee-machine" style="width:100%;box-sizing:border-box;padding:10px;border:1px solid #93c5fd;border-radius:8px;background:#fff;">
            <option value="">Loading machines...</option>
          </select>
        </div>

        <div>
          <label style="display:block;margin-bottom:5px;font-size:11px;font-weight:900;color:#475569;text-transform:uppercase;">Start Time</label>
          <input type="time" id="operator-oee-start-time" step="1" style="width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #cbd5e1;border-radius:8px;">
        </div>

        <div>
          <label style="display:block;margin-bottom:5px;font-size:11px;font-weight:900;color:#475569;text-transform:uppercase;">End Time</label>
          <input type="time" id="operator-oee-end-time" step="1" style="width:100%;box-sizing:border-box;padding:9px 10px;border:1px solid #cbd5e1;border-radius:8px;">
        </div>

        <div>
          <label style="display:block;margin-bottom:5px;font-size:11px;font-weight:900;color:#475569;text-transform:uppercase;">Cycle Time</label>
          <div style="display:block;width:100%;">
            <input type="number" id="operator-oee-cycle-min" min="0" step="1" placeholder="Minutes" style="width:100%;box-sizing:border-box;padding:9px;border:1px solid #cbd5e1;border-radius:8px;">
            <input type="number" id="operator-oee-cycle-sec" min="0" max="59" step="1" placeholder="Seconds" style="width:100%;box-sizing:border-box;padding:9px;border:1px solid #cbd5e1;border-radius:8px;">
          </div>
        </div>

        <div>
          <label style="display:block;margin-bottom:5px;font-size:11px;font-weight:900;color:#475569;text-transform:uppercase;">Load / Unload</label>
          <div style="display:block;width:100%;">
            <input type="number" id="operator-oee-load-min" min="0" step="1" placeholder="Minutes" style="width:100%;box-sizing:border-box;padding:9px;border:1px solid #cbd5e1;border-radius:8px;">
            <input type="number" id="operator-oee-load-sec" min="0" max="59" step="1" placeholder="Seconds" style="width:100%;box-sizing:border-box;padding:9px;border:1px solid #cbd5e1;border-radius:8px;">
          </div>
        </div>
      </div>

      <details style="margin-top:14px;border-top:1px solid #dbeafe;padding-top:12px;">
        <summary style="cursor:pointer;font-size:13px;font-weight:900;color:#1e3a5f;user-select:none;">
          Detailed Loss Entry - A1 to A27
        </summary>

        <div style="font-size:11px;color:#64748b;margin:6px 0 10px;">
          Enter loss time in minutes.
        </div>

        <div
          id="operator-oee-losses"
          style="
            display:grid;
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:8px;
          "
        >
          <div style="font-size:12px;color:#64748b;">
            Loading loss master...
          </div>
        </div>
      </details>
    </div>
  ` : "";


  modal.innerHTML = `
    <div class="operator-modal-panel" style="max-width:560px;">
      <div style="
        padding:17px 20px;
        border-bottom:1px solid var(--border);
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
      ">
        <div style="font-size:19px;font-weight:900;color:var(--text);">
          Complete ? ${esc(card.job_card_no)}
        </div>

        <button
          type="button"
          onclick="closeOperatorCompleteModal()"
          style="
            width:34px;
            height:34px;
            border:0;
            border-radius:50%;
            background:transparent;
            color:var(--muted);
            font-size:21px;
            cursor:pointer;
          "
        >?</button>
      </div>

      <div style="padding:20px 20px 10px;">
        <div style="
          padding:13px 15px;
          border:1px solid #bfdbfe;
          border-radius:9px;
          background:#eff6ff;
          color:#245b91;
          font-size:13px;
          line-height:1.45;
        ">
          <strong>${esc(card.item_name)}</strong><br>
        </div>
      </div>

      ${oeeSectionHtml}

      <div style="padding:10px 20px 16px;">
        <input
          type="hidden"
          id="operator-available-qty"
          value="${availableQty}"
        >

        <div style="
          display:grid;
          grid-template-columns:repeat(3,minmax(0,1fr));
          gap:12px;
        ">
          <div>
            <label style="
              display:block;
              margin-bottom:6px;
              color:#475569;
              font-size:12px;
              font-weight:900;
              text-transform:uppercase;
            ">OK Qty</label>

            <div class="operator-qty-control" style="
              margin-top:0;
              border:1px solid #86efac;
              border-radius:8px;
              padding:0;
              overflow:hidden;
              grid-template-columns:38px minmax(45px,1fr) 38px;
              gap:0;
            ">
              <button
                type="button"
                onclick="operatorAdjustOkQty(-1)"
                style="border:0;border-radius:0;background:#f0fdf4;"
              >&minus;</button>

              <input
                type="number"
                id="operator-ok-qty"
                min="0"
                max="${availableQty}"
                step="1"
                value="${availableQty}"
                onfocus="this.select()"
                oninput="operatorSyncOutcomeQty('operator-ok-qty')"
                style="border-width:0 1px;border-radius:0;color:#15803d;background:#ffffff;"
              >

              <button
                type="button"
                onclick="operatorAdjustOkQty(1)"
                style="border:0;border-radius:0;background:#f0fdf4;"
              >+</button>
            </div>
          </div>

          <div>
            <label style="
              display:block;
              margin-bottom:6px;
              color:#475569;
              font-size:12px;
              font-weight:900;
              text-transform:uppercase;
            ">Not OK Qty</label>

            <div class="operator-qty-control" style="
              margin-top:0;
              border:1px solid #fecaca;
              border-radius:8px;
              padding:0;
              overflow:hidden;
              grid-template-columns:38px minmax(45px,1fr) 38px;
              gap:0;
            ">
              <button
                type="button"
                onclick="operatorAdjustQty('operator-notok-qty',-1)"
                style="border:0;border-radius:0;background:#fef2f2;"
              >&minus;</button>

              <input
                type="number"
                id="operator-notok-qty"
                min="0"
                max="${availableQty}"
                value="0"
                oninput="operatorSyncOutcomeQty('operator-notok-qty')"
                style="border-width:0 1px;border-radius:0;"
              >

              <button
                type="button"
                onclick="operatorAdjustQty('operator-notok-qty',1)"
                style="border:0;border-radius:0;background:#fef2f2;"
              >+</button>
            </div>
          </div>

          <div>
            <label style="
              display:block;
              margin-bottom:6px;
              color:#475569;
              font-size:12px;
              font-weight:900;
              text-transform:uppercase;
            ">Hold Qty</label>

            <div class="operator-qty-control" style="
              margin-top:0;
              border:1px solid #fde68a;
              border-radius:8px;
              padding:0;
              overflow:hidden;
              grid-template-columns:38px minmax(45px,1fr) 38px;
              gap:0;
            ">
              <button
                type="button"
                onclick="operatorAdjustQty('operator-hold-qty',-1)"
                style="border:0;border-radius:0;background:#fffbeb;"
              >&minus;</button>

              <input
                type="number"
                id="operator-hold-qty"
                min="0"
                max="${availableQty}"
                value="0"
                oninput="operatorSyncOutcomeQty('operator-hold-qty')"
                style="border-width:0 1px;border-radius:0;"
              >

              <button
                type="button"
                onclick="operatorAdjustQty('operator-hold-qty',1)"
                style="border:0;border-radius:0;background:#fffbeb;"
              >+</button>
            </div>
          </div>
        </div>

        <br/>

        <div
          id="operator-pending-qty-display"
          style="display:none;margin-bottom:10px;"
        ></div>

        <div
          id="operator-rejection-reason-row"
          style="display:none;margin-bottom:14px;"
        >
          <label style="
            display:block;
            margin-bottom:6px;
            color:#475569;
            font-size:12px;
            font-weight:900;
            text-transform:uppercase;
          ">
            Rejection Reason <span style="color:#dc2626;">*</span>
          </label>

          <select
            id="operator-rejection-reason"
            onchange="operatorToggleReasonOther('rejection')"
            style="
              width:100%;
              padding:11px 13px;
              border:1px solid #fca5a5;
              border-radius:8px;
              background:#fff;
              color:var(--text);
              font-size:14px;
            "
          >
            <option value="">Select rejection reason</option>
            <option value="Dimensional oversize">Dimensional oversize</option>
            <option value="Dimensional undersize">Dimensional undersize</option>
            <option value="Surface finish NG">Surface finish NG</option>
            <option value="Thread damage">Thread damage</option>
            <option value="Concentricity NG">Concentricity NG</option>
            <option value="Tool mark">Tool mark</option>
            <option value="Material defect">Material defect</option>
            <option value="Setup error">Setup error</option>
            <option value="Other">Other</option>
          </select>

          <input
            type="text"
            id="operator-rejection-other"
            placeholder="Enter other rejection reason"
            style="
              display:none;
              width:100%;
              box-sizing:border-box;
              margin-top:8px;
              padding:10px 12px;
              border:1px solid #fca5a5;
              border-radius:8px;
              font-size:14px;
            "
          >
        </div>

        <div
          id="operator-hold-reason-row"
          style="display:none;margin-bottom:14px;"
        >
          <label style="
            display:block;
            margin-bottom:6px;
            color:#475569;
            font-size:12px;
            font-weight:900;
            text-transform:uppercase;
          ">
            Hold Reason <span style="color:#dc2626;">*</span>
          </label>

          <select
            id="operator-hold-reason"
            onchange="operatorToggleReasonOther('hold')"
            style="
              width:100%;
              padding:11px 13px;
              border:1px solid #fbbf24;
              border-radius:8px;
              background:#fff;
              color:var(--text);
              font-size:14px;
            "
          >
            <option value="">Select hold reason</option>
            <option value="Awaiting QC decision">Awaiting QC decision</option>
            <option value="Dimension borderline">Dimension borderline</option>
            <option value="Fixture issue">Fixture issue</option>
            <option value="Program correction needed">Program correction needed</option>
            <option value="Customer clarification">Customer clarification</option>
            <option value="Rework decision pending">Rework decision pending</option>
            <option value="Other">Other</option>
          </select>

          <input
            type="text"
            id="operator-hold-other"
            placeholder="Enter other hold reason"
            style="
              display:none;
              width:100%;
              box-sizing:border-box;
              margin-top:8px;
              padding:10px 12px;
              border:1px solid #fbbf24;
              border-radius:8px;
              font-size:14px;
            "
          >
        </div>

        <div>
          <label style="
            display:block;
            margin-bottom:6px;
            color:#475569;
            font-size:12px;
            font-weight:900;
            text-transform:uppercase;
          ">
            Remarks
            <span style="color:var(--muted);font-weight:500;text-transform:none;">
              (Optional)
            </span>
          </label>

          <textarea
            id="operator-stage-remark"
            placeholder="Anything the supervisor should know..."
            style="
              width:100%;
              min-height:66px;
              box-sizing:border-box;
              resize:vertical;
              padding:10px 12px;
              border:1px solid var(--border);
              border-radius:8px;
              font-family:inherit;
              font-size:14px;
            "
          ></textarea>
        </div>
      </div>

      <div style="
        padding:14px 20px;
        border-top:1px solid var(--border);
        display:flex;
        justify-content:flex-end;
        gap:10px;
      ">
        <button
          type="button"
          onclick="closeOperatorCompleteModal()"
          style="
            padding:10px 18px;
            border:1px solid var(--border);
            border-radius:8px;
            background:#fff;
            color:var(--text);
            font-weight:800;
            cursor:pointer;
          "
        >Cancel</button>

        <button
          type="button"
          id="operator-complete-confirm-btn"
          onclick="confirmOperatorComplete()"
          style="
            padding:10px 18px;
            border:0;
            border-radius:8px;
            background:var(--header-bg);
            color:#fff;
            font-weight:900;
            cursor:pointer;
          "
        >
          <i class="fa fa-check"></i> Submit completion
        </button>
      </div>
    </div>
  `;

  modal.style.display = "flex";
  operatorSyncOutcomeQty();

  if (isOeeProcess) {
    loadOperatorOeeMasterData();
  }
}


function operatorAdjustQty(fieldId, delta) {
  const input = document.getElementById(fieldId);
  if (!input) return;

  const current = Math.max(0, operatorNumber(input.value, 0));
  input.value = Math.max(0, current + delta);
  operatorSyncOutcomeQty(fieldId);
}


function operatorSyncOutcomeQty(changedFieldId = "") {
  const availableInput = document.getElementById("operator-available-qty");
  const okInput = document.getElementById("operator-ok-qty");
  const notOkInput = document.getElementById("operator-notok-qty");
  const holdInput = document.getElementById("operator-hold-qty");
  const equation = document.getElementById("operator-qty-equation");
  const pendingDisplay = document.getElementById("operator-pending-qty-display");
  const rejectionRow = document.getElementById("operator-rejection-reason-row");
  const holdRow = document.getElementById("operator-hold-reason-row");

  if (!availableInput || !okInput || !notOkInput || !holdInput) return;

  const available = Math.max(0, operatorNumber(availableInput.value, 0));

  let notOk = Math.max(0, operatorNumber(notOkInput.value, 0));
  let hold = Math.max(0, operatorNumber(holdInput.value, 0));
  let ok = Math.max(0, operatorNumber(okInput.value, 0));

  // Cap: notOk + hold cannot exceed available
  if (notOk + hold > available) {
    if (changedFieldId === "operator-hold-qty") {
      hold = Math.max(0, available - notOk);
    } else {
      notOk = Math.max(0, available - hold);
    }
  }

  // Cap ok: cannot exceed available - notOk - hold
  const maxOk = Math.max(0, available - notOk - hold);
  if (ok > maxOk) ok = maxOk;

  okInput.value = ok;
  notOkInput.value = notOk;
  holdInput.value = hold;

  // Pending = what operator hasn't accounted for yet this submission
  const pending = Math.max(0, available - ok - notOk - hold);

  // Update pending display
  if (pendingDisplay) {
    pendingDisplay.textContent = `⏳ Pending: ${pending}`;
    pendingDisplay.style.color = pending === 0 ? "#16a34a" : "#f59e0b";
    pendingDisplay.style.fontWeight = "900";
    pendingDisplay.style.fontSize = "14px";
    pendingDisplay.style.marginTop = "8px";
    pendingDisplay.style.display = "block";
  }

  // Show/hide rejection reason
  if (rejectionRow) {
    rejectionRow.style.display = notOk > 0 ? "block" : "none";
    if (notOk === 0) {
      const select = document.getElementById("operator-rejection-reason");
      const other = document.getElementById("operator-rejection-other");
      if (select) select.value = "";
      if (other) { other.value = ""; other.style.display = "none"; }
    }
  }

  // Show/hide hold reason
  if (holdRow) {
    holdRow.style.display = hold > 0 ? "block" : "none";
    if (hold === 0) {
      const select = document.getElementById("operator-hold-reason");
      const other = document.getElementById("operator-hold-other");
      if (select) select.value = "";
      if (other) { other.value = ""; other.style.display = "none"; }
    }
  }

  // Equation display
  if (equation) {
    const total = ok + notOk + hold;
    equation.textContent = `OK ${ok} + Not OK ${notOk} + Hold ${hold} + Pending ${pending} = ${available}`;
    equation.classList.toggle("invalid", total > available);
  }
}


function operatorAdjustOkQty(delta) {
  const availableInput = document.getElementById(
    "operator-available-qty"
  );
  const notOkInput = document.getElementById(
    "operator-notok-qty"
  );
  const holdInput = document.getElementById(
    "operator-hold-qty"
  );

  if (!availableInput || !notOkInput || !holdInput) return;

  const available = Math.max(
    0,
    operatorNumber(availableInput.value, 0)
  );

  let notOk = Math.max(0, operatorNumber(notOkInput.value, 0));
  let hold = Math.max(0, operatorNumber(holdInput.value, 0));
  const ok = Math.max(0, available - notOk - hold);

  if (delta < 0 && ok > 0) {
    notOk += 1;
  }

  if (delta > 0) {
    if (notOk > 0) {
      notOk -= 1;
    } else if (hold > 0) {
      hold -= 1;
    }
  }

  notOkInput.value = notOk;
  holdInput.value = hold;
  operatorSyncOutcomeQty("operator-notok-qty");
}


function operatorToggleReasonOther(type) {
  const select = document.getElementById(
    type === "rejection"
      ? "operator-rejection-reason"
      : "operator-hold-reason"
  );

  const input = document.getElementById(
    type === "rejection"
      ? "operator-rejection-other"
      : "operator-hold-other"
  );

  if (!select || !input) return;

  const showOther = select.value === "Other";
  input.style.display = showOther ? "block" : "none";

  if (!showOther) {
    input.value = "";
  } else {
    input.focus();
  }
}


function closeOperatorCompleteModal() {
  const modal = document.getElementById("operator-complete-modal");

  if (modal) {
    modal.style.display = "none";
    modal.innerHTML = "";
  }

  _operatorActiveIdx = null;
}


function operatorShowCompletionSuccess(card, activeIdx, quantities) {
  const modal = document.getElementById("operator-complete-modal");
  const cardElement = document.querySelector(
    `[data-operator-card-index="${activeIdx}"]`
  );

  if (cardElement) {
    cardElement.classList.add("operator-card-success");

    cardElement.insertAdjacentHTML(
      "afterbegin",
      `
        <div class="operator-success-overlay">
          <div>
            <div class="operator-success-check">
              <i class="fa fa-check"></i>
            </div>
            <div style="font-size:17px;font-weight:900;color:#166534;">
              Process Completed
            </div>
            <div style="font-size:12px;color:#15803d;margin-top:5px;">
              OK ${quantities.ok} &nbsp;|&nbsp;
              Not OK ${quantities.notOk} &nbsp;|&nbsp;
              Hold ${quantities.hold}
            </div>
          </div>
        </div>
      `
    );
  }

  if (modal) {
    modal.innerHTML = `
      <div class="operator-modal-panel" style="max-width:430px;">
        <div style="padding:30px 24px;text-align:center;">
          <div class="operator-success-check">
            <i class="fa fa-check"></i>
          </div>

          <div style="font-size:20px;font-weight:900;color:#166534;">
            ${esc(card.current_process)} Completed
          </div>

          <div style="font-size:13px;color:var(--muted);margin-top:7px;">
            Job Card ${esc(card.job_card_no)} is moving to
            <strong>${esc(card.next_process || "Store")}</strong>
          </div>

          <div style="
            margin-top:17px;
            display:grid;
            grid-template-columns:repeat(3, 1fr);
            gap:8px;
          ">
            <div style="padding:10px;border-radius:9px;background:#f0fdf4;color:#15803d;">
              <div style="font-size:10px;font-weight:800;">OK</div>
              <div style="font-size:20px;font-weight:900;">${quantities.ok}</div>
            </div>

            <div style="padding:10px;border-radius:9px;background:#fef2f2;color:#b91c1c;">
              <div style="font-size:10px;font-weight:800;">NOT OK</div>
              <div style="font-size:20px;font-weight:900;">${quantities.notOk}</div>
            </div>

            <div style="padding:10px;border-radius:9px;background:#fffbeb;color:#a16207;">
              <div style="font-size:10px;font-weight:800;">HOLD</div>
              <div style="font-size:20px;font-weight:900;">${quantities.hold}</div>
            </div>
          </div>

          <div style="font-size:11px;color:var(--muted);margin-top:16px;">
            Updating your job-card list...
          </div>
        </div>
      </div>
    `;
  }

  window.setTimeout(function () {
    if (
      Number.isInteger(activeIdx) &&
      activeIdx >= 0 &&
      activeIdx < operatorCards.length
    ) {
      const completedSource = operatorCards[activeIdx];

      if (completedSource) {
        const completionDraft =
          completedSource._operatorCompletionDraft || {};

        const completedRecord = {
          job_card_no: completedSource.job_card_no || "",
          so_no: completedSource.so_no || "",
          item_name: completedSource.item_name || "",
          completed_process:
            completionDraft.completed_process ||
            completedSource.wip_status ||
            "",
          moved_to:
            completionDraft.moved_to ||
            completedSource.next_process ||
            "",
          ok_qty: operatorNumber(completionDraft.ok_qty, 0),
          rejected_qty: operatorNumber(
            completionDraft.rejected_qty,
            0
          ),
          hold_qty: operatorNumber(completionDraft.hold_qty, 0),
          rejection_reason:
            completionDraft.rejection_reason || "",
          hold_reason: completionDraft.hold_reason || "",
          stage_remark: completionDraft.stage_remark || "",
          completed_at: new Date().toISOString()
        };

        operatorCompletedCards = operatorCompletedCards.filter(
          function (existing) {
            return !(
              String(existing.job_card_no) ===
                String(completedRecord.job_card_no) &&
              String(existing.completed_process) ===
                String(completedRecord.completed_process)
            );
          }
        );

        operatorCompletedCards.unshift(completedRecord);
        operatorCompletedCards =
          operatorCompletedCards.slice(0, 10);

        operatorSaveCompletedReviewV1();
      }

      operatorCards.splice(activeIdx, 1);
    }

    if (
      operatorPage * OPERATOR_PAGE_SIZE >= operatorCards.length &&
      operatorPage > 0
    ) {
      operatorPage--;
    }

    _operatorActiveIdx = null;
    renderOperatorGrid();
    showToast("Process completed successfully.", "success");
  }, 1450);
}


/* OEE_COMPLETION_PAYLOAD_V1_START */
function operatorCollectOeePayloadV1(card) {
  const processName = String(
    card?.current_process ||
    card?.wip_status ||
    ""
  )
    .trim()
    .toLowerCase();

  if (
    !processName.startsWith("cnc machining") &&
    !processName.startsWith("vmc machining")
  ) {
    return {
      required: false,
      payload: null,
      error: null
    };
  }

  const valueOf = function(id) {
    return String(
      document.getElementById(id)?.value ?? ""
    ).trim();
  };

  const entryDate = valueOf("operator-oee-date");
  const shiftName = valueOf("operator-oee-shift");
  const machineRaw = valueOf("operator-oee-machine");

  if (!entryDate) {
    return {
      required: true,
      payload: null,
      error: "Please select the OEE Date."
    };
  }

  if (!shiftName) {
    return {
      required: true,
      payload: null,
      error: "Please select the OEE Shift."
    };
  }

  const machineId = Number(machineRaw);

  if (!Number.isInteger(machineId) || machineId <= 0) {
    return {
      required: true,
      payload: null,
      error: "Please select the OEE Machine."
    };
  }

  const readWholeNumber = function(id, label, maxValue = null) {
    const raw = valueOf(id);
    const number = raw === "" ? 0 : Number(raw);

    if (
      !Number.isFinite(number) ||
      !Number.isInteger(number) ||
      number < 0
    ) {
      return {
        error: `${label} must be a whole number of 0 or more.`
      };
    }

    if (maxValue !== null && number > maxValue) {
      return {
        error: `${label} must be between 0 and ${maxValue}.`
      };
    }

    return { value: number };
  };

  const cycleMin = readWholeNumber(
    "operator-oee-cycle-min",
    "Cycle Time Minutes"
  );
  if (cycleMin.error) {
    return { required: true, payload: null, error: cycleMin.error };
  }

  const cycleSec = readWholeNumber(
    "operator-oee-cycle-sec",
    "Cycle Time Seconds",
    59
  );
  if (cycleSec.error) {
    return { required: true, payload: null, error: cycleSec.error };
  }

  const loadMin = readWholeNumber(
    "operator-oee-load-min",
    "Load/Unload Minutes"
  );
  if (loadMin.error) {
    return { required: true, payload: null, error: loadMin.error };
  }

  const loadSec = readWholeNumber(
    "operator-oee-load-sec",
    "Load/Unload Seconds",
    59
  );
  if (loadSec.error) {
    return { required: true, payload: null, error: loadSec.error };
  }

  const losses = [];

  for (let index = 1; index <= 27; index += 1) {
    const lossCode = `A${index}`;
    const input = document.getElementById(
      `operator-oee-loss-${lossCode}`
    );

    if (!input) {
      return {
        required: true,
        payload: null,
        error: `OEE loss field ${lossCode} is missing from the form.`
      };
    }

    const raw = String(input.value ?? "").trim();
    const minutes = raw === "" ? 0 : Number(raw);

    if (!Number.isFinite(minutes) || minutes < 0) {
      return {
        required: true,
        payload: null,
        error: `${lossCode} loss minutes must be 0 or more.`
      };
    }

    losses.push({
      loss_code: lossCode,
      loss_minutes: minutes
    });
  }

  return {
    required: true,
    error: null,
    payload: {
      entry_date: entryDate,
      shift_name: shiftName,
      machine_id: machineId,
      start_time: valueOf("operator-oee-start-time") || null,
      end_time: valueOf("operator-oee-end-time") || null,
      cycle_minutes: cycleMin.value,
      cycle_seconds: cycleSec.value,
      load_unload_minutes: loadMin.value,
      load_unload_seconds: loadSec.value,
      losses: losses
    }
  };
}
/* OEE_COMPLETION_PAYLOAD_V1_END */


async function confirmOperatorComplete() {
  const activeIdx = _operatorActiveIdx;
  const card = operatorCards[activeIdx];

  if (!card) return;

  operatorSyncOutcomeQty();

  const available = operatorAvailableQty(card);
  const okQty = Math.max(
    0,
    operatorNumber(
      document.getElementById("operator-ok-qty")?.value,
      0
    )
  );
  const notOkQty = Math.max(
    0,
    operatorNumber(
      document.getElementById("operator-notok-qty")?.value,
      0
    )
  );
  const holdQty = Math.max(
    0,
    operatorNumber(
      document.getElementById("operator-hold-qty")?.value,
      0
    )
  );

  const rejectionSelect = document.getElementById(
    "operator-rejection-reason"
  );
  const rejectionOther = document.getElementById(
    "operator-rejection-other"
  );
  const holdSelect = document.getElementById(
    "operator-hold-reason"
  );
  const holdOther = document.getElementById(
    "operator-hold-other"
  );

  let rejectionReason = String(
    rejectionSelect?.value || ""
  ).trim();

  if (rejectionReason === "Other") {
    rejectionReason = String(rejectionOther?.value || "").trim();
  }

  let holdReason = String(holdSelect?.value || "").trim();

  if (holdReason === "Other") {
    holdReason = String(holdOther?.value || "").trim();
  }

  const stageRemark = String(
    document.getElementById("operator-stage-remark")?.value || ""
  ).trim();

  if (okQty + notOkQty + holdQty > available) {
    showToast(
      `Total cannot exceed available qty (${available}).`,
      "error"
    );
    return;
  }

  if (okQty + notOkQty + holdQty === 0) {
    showToast(
      "Please enter at least some quantity before submitting.",
      "error"
    );
    return;
  }

  if (notOkQty > 0 && !rejectionReason) {
    showToast(
      "Please select a rejection reason for the Not OK quantity.",
      "error"
    );
    rejectionSelect?.focus();
    return;
  }

  if (holdQty > 0 && !holdReason) {
    showToast(
      "Please select a hold reason for the Hold quantity.",
      "error"
    );
    holdSelect?.focus();
    return;
  }

  const oeeResult = operatorCollectOeePayloadV1(card);

  if (oeeResult.error) {
    showToast(oeeResult.error, "error");
    return;
  }

  const oeePayload = oeeResult.payload;

  const button = document.getElementById(
    "operator-complete-confirm-btn"
  );

  if (button) {
    button.innerHTML =
      '<i class="fa fa-spinner fa-spin"></i> Saving...';
    button.disabled = true;
    button.style.opacity = ".7";
  }

  card._operatorCompletionDraft = {
    completed_process: card.wip_status || "",
    moved_to: card.next_process || "Store",
    ok_qty: okQty,
    rejected_qty: notOkQty,
    hold_qty: holdQty,
    rejection_reason: rejectionReason,
    hold_reason: holdReason,
    stage_remark: stageRemark
  };

  try {
    const response = await fetch("/api/wip/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        job_card_no: card.job_card_no,
        item_name: card.item_name,
        new_stage: card.next_process || "Store",
        changed_by:
          window.JMS_CURRENT_USER ||
          window.JMS_CURRENT_USERNAME ||
          "Operator",

        actual_qty: okQty,
        ok_qty: okQty,
        rejected_qty: notOkQty,
        hold_qty: holdQty,
        rejection_reason: rejectionReason,
        hold_reason: holdReason,
        rework_qty: 0,
        rework_remarks: "",
        stage_remark: stageRemark,
        oee: oeePayload
      })
    });

    const data = await response.json();

    if (!data.success) {
      showToast(
        data.error || "Failed to complete process",
        "error"
      );
      return;
    }

    closeOperatorCompleteModal();

    if (data.is_partial) {
      // Update card in place with new qty values
      const cardInList = operatorCards[activeIdx];
      if (cardInList) {
        cardInList.actual_qty = data.ok_qty;
        cardInList.rejected_qty = data.rejected_qty;
        cardInList.hold_qty = data.hold_qty;
        cardInList.pending_qty = data.pending_qty;
        cardInList.is_partial = true;
      }
      showToast(
        `Partial entry saved. ${data.pending_qty} pieces still pending.`,
        "warning"
      );
      renderOperatorGrid();
    } else {
      // Full completion — remove from active list
      operatorCards.splice(activeIdx, 1);
      if (
        operatorPage * OPERATOR_PAGE_SIZE >= operatorCards.length &&
        operatorPage > 0
      ) {
        operatorPage--;
      }
      showToast("Process completed successfully.", "success");
      renderOperatorGrid();
      // Refresh recently completed from DB
      await loadRecentlyCompleted();
    }
  } catch (error) {
    showToast(
      "Server error while completing the process.",
      "error"
    );
  } finally {
    if (button && document.body.contains(button)) {
      button.innerHTML =
        '<i class="fa fa-check"></i> Submit completion';
      button.disabled = false;
      button.style.opacity = "1";
    }
  }
}


function operatorPrevPage() {
  if (operatorPage > 0) {
    operatorPage--;
    renderOperatorGrid();
  }
}


function operatorNextPage() {
  if (
    (operatorPage + 1) * OPERATOR_PAGE_SIZE <
    operatorCards.length
  ) {
    operatorPage++;
    renderOperatorGrid();
  }
}

// Auto-load operator view on page load
if (IS_OPERATOR_READ_ONLY) {
  document.addEventListener("DOMContentLoaded", function () {
    const placeholder = document.getElementById("placeholder");
    if (placeholder) placeholder.style.display = "none";
    const resultsSection = document.getElementById("results-section");
    if (resultsSection) resultsSection.style.display = "none";
    loadOperatorView();
  });
}

/* OPERATOR_CARD_CONTRAST_FIX_START */
(function applyOperatorCardContrastFix() {
  const styleId = "operator-card-contrast-fix";
  let style = document.getElementById(styleId);

  if (!style) {
    style = document.createElement("style");
    style.id = styleId;
    document.head.appendChild(style);
  }

  style.textContent = `
    #operator-view {
      background: transparent !important;
      border: none !important;
      border-radius: 0 !important;
      padding: 0 !important;
      margin-top: 16px !important;
      box-sizing: border-box !important;
    }

    #operator-view .operator-grid {
      gap: 16px !important;
    }

    #operator-view .operator-job-card {
      background: #d5dce5 !important;
      border: 1px solid #c9d5e3 !important;
      box-shadow:
        0 4px 14px rgba(15, 42, 77, 0.10),
        0 1px 3px rgba(15, 42, 77, 0.06) !important;
    }

    #operator-view .operator-job-card:hover {
      border-color: #9fb3ca !important;
      box-shadow:
        0 10px 26px rgba(15, 42, 77, 0.15),
        0 2px 6px rgba(15, 42, 77, 0.08) !important;
    }

    #operator-view .operator-job-card > div:last-child {
      background: #f8fafc !important;
      border-top-color: #d7e0ea !important;
    }

    #operator-view .operator-success-overlay {
      background: rgba(240, 253, 244, 0.98) !important;
    }

    @media (max-width: 680px) {
      #operator-view {
        padding: 6px !important;
        border-radius: 12px !important;
      }
    }
  `;
})();
/* OPERATOR_CARD_CONTRAST_FIX_END */

/* OPERATOR_SPLIT_WORKSPACE_V1_START */
/*
 * Operator-only manager review workspace.
 *
 * This layer affects only IS_OPERATOR_READ_ONLY users.
 * Admin and Supervisor retain the original Page3 renderer.
 * Recently Completed is stored only in this operator's browser session.
 */

let _operatorCompletedReviewLoadedV1 = false;

const OPERATOR_COMPLETED_REVIEW_LIMIT_V1 = 10;


function operatorCompletedStorageKeyV1() {
  const identity = String(
    window.JMS_CURRENT_USER ||
    window.JMS_CURRENT_USERNAME ||
    "operator"
  )
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_");

  return `jms_operator_recent_completed_v1_${identity}`;
}


function operatorLoadCompletedReviewV1() {
  if (_operatorCompletedReviewLoadedV1) return;

  _operatorCompletedReviewLoadedV1 = true;

  try {
    const saved = JSON.parse(
      sessionStorage.getItem(
        operatorCompletedStorageKeyV1()
      ) || "[]"
    );

    operatorCompletedCards = Array.isArray(saved)
      ? saved.slice(0, OPERATOR_COMPLETED_REVIEW_LIMIT_V1)
      : [];
  } catch (error) {
    operatorCompletedCards = [];
  }
}


function operatorSaveCompletedReviewV1() {
  try {
    sessionStorage.setItem(
      operatorCompletedStorageKeyV1(),
      JSON.stringify(
        operatorCompletedCards.slice(
          0,
          OPERATOR_COMPLETED_REVIEW_LIMIT_V1
        )
      )
    );
  } catch (error) {
    // The completion itself is already stored by the backend.
    // Browser session storage failure must not block production work.
  }
}


function operatorFormatCompletedTimeV1(value) {
  if (!value) return "-";

  const completedDate = new Date(value);

  if (Number.isNaN(completedDate.getTime())) {
    return "-";
  }

  return completedDate.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit"
  });
}


function operatorEnsureSplitStylesV1() {
  if (
    document.getElementById(
      "operator-split-workspace-styles-v1"
    )
  ) {
    return;
  }

  const style = document.createElement("style");

  style.id = "operator-split-workspace-styles-v1";

  style.textContent = `
    .operator-split-workspace-v1 {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 18px;
      align-items: start;
      width: 100%;
    }

    .operator-panel-v1 {
      min-width: 0;
      background: var(--surface, #fff);
      border: 1px solid var(--border, #dbe3ec);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 8px 24px rgba(15, 42, 77, .07);
    }

    .operator-panel-header-v1 {
      min-height: 70px;
      padding: 15px 18px;
      box-sizing: border-box;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      border-bottom: 1px solid var(--border, #dbe3ec);
    }

    .operator-pending-header-v1 {
      background: linear-gradient(
        135deg,
        #eff6ff 0%,
        #f8fbff 100%
      );
    }

    .operator-completed-header-v1 {
      background: linear-gradient(
        135deg,
        #ecfdf5 0%,
        #f7fffb 100%
      );
    }

    .operator-panel-heading-v1 {
      display: flex;
      align-items: center;
      gap: 11px;
      color: var(--text, #0f172a);
      font-size: 17px;
      font-weight: 900;
    }

    .operator-panel-heading-v1 i {
      width: 35px;
      height: 35px;
      border-radius: 10px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
    }

    .operator-pending-header-v1 i {
      color: #1d4ed8;
      background: #dbeafe;
    }

    .operator-completed-header-v1 i {
      color: #15803d;
      background: #dcfce7;
    }

    .operator-count-badge-v1 {
      min-width: 34px;
      height: 30px;
      padding: 0 10px;
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #fff;
      border: 1px solid var(--border, #dbe3ec);
      color: var(--text, #0f172a);
      font-size: 13px;
      font-weight: 900;
    }

    .operator-panel-subtitle-v1 {
      margin-top: 3px;
      color: var(--muted, #64748b);
      font-size: 12px;
      font-weight: 600;
    }

    .operator-pending-body-v1 {
      padding: 15px;
      min-width: 0;
    }

    .operator-pending-body-v1 .operator-grid {
      grid-template-columns:
        repeat(3, minmax(0, 1fr)) !important;
    }

    .operator-completed-body-v1 {
      padding: 12px;
    }

    .operator-completed-empty-v1 {
      padding: 42px 18px;
      text-align: center;
      color: var(--muted, #64748b);
    }

    .operator-completed-empty-v1 i {
      width: 52px;
      height: 52px;
      margin: 0 auto 12px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f1f5f9;
      color: #94a3b8;
      font-size: 21px;
    }

    .operator-recent-list-v1 {
      display: grid;
      grid-template-columns:
        repeat(3, minmax(0, 1fr));
      gap: 12px;
    }

    .operator-recent-card-v1 {
      position: relative;
      padding: 12px 13px;
      border: 1px solid #dbe3ec;
      border-radius: 12px;
      background: #fff;
      overflow: hidden;
    }

    .operator-recent-card-v1.latest {
      padding: 15px;
      border-color: #4ade80;
      background: linear-gradient(
        135deg,
        #f0fdf4 0%,
        #ffffff 100%
      );
      box-shadow: 0 0 0 3px rgba(34, 197, 94, .10);
      animation: operatorRecentArrivalV1 .45s ease both;
    }

    .operator-recent-card-v1.latest::before {
      content: "";
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 5px;
      background: #22c55e;
    }

    .operator-recent-top-v1 {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 9px;
      margin-bottom: 6px;
    }

    .operator-recent-jc-v1 {
      color: #166534;
      font-size: 14px;
      font-weight: 900;
    }

    .operator-recent-status-v1 {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      color: #15803d;
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
    }

    .operator-recent-item-v1 {
      color: var(--text, #0f172a);
      font-size: 12px;
      font-weight: 750;
      line-height: 1.35;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .operator-recent-process-v1 {
      margin-top: 7px;
      color: #334155;
      font-size: 12px;
      font-weight: 800;
    }

    .operator-recent-qty-v1 {
      margin-top: 9px;
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }

    .operator-recent-qty-v1 span {
      padding: 4px 7px;
      border-radius: 6px;
      font-size: 10px;
      font-weight: 900;
    }

    .operator-recent-ok-v1 {
      color: #166534;
      background: #dcfce7;
    }

    .operator-recent-rejected-v1 {
      color: #991b1b;
      background: #fee2e2;
    }

    .operator-recent-hold-v1 {
      color: #92400e;
      background: #fef3c7;
    }

    .operator-recent-footer-v1 {
      margin-top: 9px;
      padding-top: 8px;
      border-top: 1px solid rgba(148, 163, 184, .25);
      display: flex;
      justify-content: space-between;
      gap: 8px;
      color: var(--muted, #64748b);
      font-size: 10px;
      font-weight: 700;
    }

    @keyframes operatorRecentArrivalV1 {
      from {
        opacity: 0;
        transform: translateY(-10px) scale(.98);
      }

      to {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    @media (max-width: 1180px) {
      .operator-pending-body-v1 .operator-grid,
      .operator-recent-list-v1 {
        grid-template-columns:
          repeat(2, minmax(0, 1fr)) !important;
      }
    }

    @media (max-width: 760px) {
      .operator-pending-body-v1 .operator-grid,
      .operator-recent-list-v1 {
        grid-template-columns: 1fr !important;
      }

      .operator-panel-header-v1 {
        padding: 13px 14px;
      }
    }
  `;

  document.head.appendChild(style);
}


function operatorRenderCompletedReviewV1() {
  if (!operatorCompletedCards.length) {
    return `
      <div class="operator-completed-empty-v1">
        <i class="fa fa-check"></i>
        <div style="
          font-size:14px;
          font-weight:900;
          color:var(--text, #0f172a);
          margin-bottom:5px;
        ">
          No completion yet
        </div>
        <div style="font-size:12px;line-height:1.45;">
          Completed work will appear here without disappearing.
        </div>
      </div>
    `;
  }

  return `
    <div class="operator-recent-list-v1">
      ${operatorCompletedCards.map(function (card, index) {
        const latestClass = index === 0 ? "latest" : "";

        return `
          <div class="operator-recent-card-v1 ${latestClass}">
            <div class="operator-recent-top-v1">
              <div class="operator-recent-jc-v1">
                ${esc(card.job_card_no || "-")}
              </div>

              <div class="operator-recent-status-v1">
                <i class="fa fa-check-circle"></i>
                Completed
              </div>
            </div>

            <div
              class="operator-recent-item-v1"
              title="${esc(card.item_name || "")}"
            >
              ${esc(card.item_name || "-")}
            </div>

            <div class="operator-recent-process-v1">
              ${esc(card.completed_process || "-")}
              <i
                class="fa fa-arrow-right"
                style="margin:0 5px;color:#94a3b8;"
              ></i>
              ${esc(card.moved_to || "Completed")}
            </div>

            <div class="operator-recent-qty-v1">
              <span class="operator-recent-ok-v1">
                OK ${operatorNumber(card.ok_qty, 0)}
              </span>

              <span class="operator-recent-rejected-v1">
                Not OK ${operatorNumber(card.rejected_qty, 0)}
              </span>

              <span class="operator-recent-hold-v1">
                Hold ${operatorNumber(card.hold_qty, 0)}
              </span>
            </div>

            <div class="operator-recent-footer-v1">
              <span>
                ${index === 0 ? "Latest completion" : "Previous completion"}
              </span>

              <span>
                ${esc(
                  operatorFormatCompletedTimeV1(
                    card.completed_at
                  )
                )}
              </span>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}


/* renderOperatorSplitWorkspaceV1 removed — renderOperatorGrid handles all rendering */

/* NEUTRALISED_SPLIT_WORKSPACE_ORIGINAL_BELOW_FOR_REFERENCE
function renderOperatorSplitWorkspaceV1_DISABLED() {
    // Neutralised — full rendering now handled by our renderOperatorGrid above
    return _operatorRenderGridBeforeSplitV1();
  };


if (IS_OPERATOR_READ_ONLY) {
  setTimeout(function () {
    if (
      document.getElementById("operator-view") &&
      operatorCards.length
    ) {
      renderOperatorGrid();
    }
  }, 0);
}

OPERATOR_SPLIT_WORKSPACE_V1_DISABLED_END */

/* OPERATOR_SPLIT_WORKSPACE_V1_END */

/* OPERATOR_DATABASE_RECENT_UNDO_UI_V2_START */
/*
 * Database-backed Operator Recently Completed + Undo.
 *
 * Operator only:
 * - Admin UI remains unchanged.
 * - Supervisor UI remains unchanged.
 * - Admin/Supervisor rollback remains unchanged.
 */

let _operatorWorkspaceRefreshInFlightV2 = false;


function operatorEnsureUndoStylesV2() {
  if (
    document.getElementById(
      "operator-database-undo-styles-v2"
    )
  ) {
    return;
  }

  const style = document.createElement("style");

  style.id = "operator-database-undo-styles-v2";

  style.textContent = `
    .operator-undo-btn-v2 {
      width: 100%;
      min-height: 38px;
      margin-top: 11px;
      padding: 8px 12px;
      border: 1px solid #f59e0b;
      border-radius: 8px;
      background: #fffbeb;
      color: #92400e;
      font-size: 11px;
      font-weight: 900;
      cursor: pointer;
      transition:
        background .18s ease,
        transform .18s ease,
        box-shadow .18s ease;
    }

    .operator-undo-btn-v2:hover {
      background: #fef3c7;
      transform: translateY(-1px);
      box-shadow: 0 5px 15px rgba(245, 158, 11, .17);
    }

    .operator-undo-btn-v2:disabled {
      cursor: not-allowed;
      opacity: .55;
      transform: none;
      box-shadow: none;
    }

    .operator-undo-modal-overlay-v2 {
      display: none;
      position: fixed;
      inset: 0;
      z-index: 10050;
      padding: 15px;
      align-items: center;
      justify-content: center;
      background: rgba(15, 23, 42, .58);
      backdrop-filter: blur(3px);
    }

    .operator-undo-modal-panel-v2 {
      width: min(94vw, 520px);
      overflow: hidden;
      border: 1px solid #dbe3ec;
      border-radius: 16px;
      background: #fff;
      box-shadow: 0 24px 70px rgba(15, 23, 42, .28);
      animation: operatorUndoModalInV2 .22s ease both;
    }

    .operator-undo-modal-header-v2 {
      padding: 16px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid #e2e8f0;
      background: #fffbeb;
    }

    .operator-undo-modal-title-v2 {
      color: #92400e;
      font-size: 17px;
      font-weight: 900;
    }

    .operator-undo-modal-close-v2 {
      width: 34px;
      height: 34px;
      border: 0;
      border-radius: 50%;
      background: transparent;
      color: #64748b;
      font-size: 20px;
      cursor: pointer;
    }

    .operator-undo-summary-v2 {
      padding: 13px 14px;
      border: 1px solid #fde68a;
      border-radius: 10px;
      background: #fffbeb;
      color: #78350f;
      font-size: 12px;
      line-height: 1.55;
    }

    .operator-undo-field-v2 {
      margin-top: 15px;
    }

    .operator-undo-field-v2 label {
      display: block;
      margin-bottom: 6px;
      color: #334155;
      font-size: 12px;
      font-weight: 900;
    }

    .operator-undo-field-v2 select,
    .operator-undo-field-v2 textarea {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #cbd5e1;
      border-radius: 9px;
      background: #fff;
      color: #0f172a;
      font-size: 13px;
      outline: none;
    }

    .operator-undo-field-v2 select {
      height: 42px;
      padding: 0 11px;
    }

    .operator-undo-field-v2 textarea {
      min-height: 78px;
      padding: 10px 11px;
      resize: vertical;
    }

    .operator-undo-field-v2 select:focus,
    .operator-undo-field-v2 textarea:focus {
      border-color: #f59e0b;
      box-shadow: 0 0 0 3px rgba(245, 158, 11, .12);
    }

.operator-undo-inline-error-v3 {
      display: none;
      margin-top: 13px;
      padding: 11px 13px;
      border: 1px solid #fecaca;
      border-radius: 9px;
      background: #fef2f2;
      color: #b91c1c;
      font-size: 12px;
      font-weight: 800;
      line-height: 1.45;
      animation: operatorUndoErrorInV3 .22s ease both;
    }

    .operator-undo-inline-error-v3.visible {
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }

    .operator-undo-inline-error-v3 i {
      margin-top: 2px;
      flex: 0 0 auto;
    }

    @keyframes operatorUndoErrorInV3 {
      from {
        opacity: 0;
        transform: translateY(-5px);
      }

      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .operator-undo-warning-v2 {
      margin-top: 13px;
      padding: 10px 11px;
      border-radius: 8px;
      background: #fef2f2;
      color: #991b1b;
      font-size: 11px;
      font-weight: 700;
      line-height: 1.45;
    }

    .operator-undo-actions-v2 {
      padding: 14px 18px 18px;
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }

    .operator-undo-cancel-v2,
    .operator-undo-confirm-v2 {
      min-height: 40px;
      padding: 9px 16px;
      border-radius: 9px;
      font-size: 12px;
      font-weight: 900;
      cursor: pointer;
    }

    .operator-undo-cancel-v2 {
      border: 1px solid #cbd5e1;
      background: #fff;
      color: #475569;
    }

    .operator-undo-confirm-v2 {
      border: 1px solid #dc2626;
      background: #dc2626;
      color: #fff;
    }

    .operator-undo-confirm-v2:disabled {
      cursor: not-allowed;
      opacity: .65;
    }

    @keyframes operatorUndoModalInV2 {
      from {
        opacity: 0;
        transform: translateY(10px) scale(.98);
      }

      to {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }
  `;

  document.head.appendChild(style);
}


function operatorEnsureUndoModalV2() {
  operatorEnsureUndoStylesV2();

  let modal = document.getElementById(
    "operator-undo-modal-v2"
  );

  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "operator-undo-modal-v2";
  modal.className = "operator-undo-modal-overlay-v2";

  modal.addEventListener("click", function (event) {
    if (event.target === modal) {
      closeOperatorUndoModalV2();
    }
  });

  document.body.appendChild(modal);

  return modal;
}


async function operatorReadJsonV2(response) {
  let payload = {};

  try {
    payload = await response.json();
  } catch (error) {
    payload = {
      success: false,
      error: `Server returned HTTP ${response.status}.`
    };
  }

  if (!response.ok || payload.success === false) {
    const requestError = new Error(
      payload.error ||
      `Request failed with HTTP ${response.status}.`
    );

    requestError.payload = payload;
    requestError.status = response.status;

    throw requestError;
  }

  return payload;
}

async function operatorRefreshWorkspaceV2(isInitialLoad = false) {
  try {
    const [jobCardsRes, completionsRes] = await Promise.all([
      fetch("/api/operator/job_cards"),
      fetch("/api/operator/recent_completions")
    ]);

    const jobCardsData = await jobCardsRes.json();
    const completionsData = await completionsRes.json();

    if (jobCardsData.success) {
      operatorCards = jobCardsData.job_cards || [];
      operatorPage = 0;
    }

    if (completionsData.success) {
      operatorCompletedCards = completionsData.completions
        || completionsData.completed_job_cards
        || [];
    }

    renderOperatorGrid();

  } catch (error) {
    console.error("Failed to refresh operator workspace:", error);
  }
}

/*
 * Disable V1 browser-session completed storage.
 * All completed cards now come from MySQL.
 */
operatorLoadCompletedReviewV1 = function () {
  _operatorCompletedReviewLoadedV1 = true;
};


operatorSaveCompletedReviewV1 = function () {
  // Database-backed in V2.
};


try {
  sessionStorage.removeItem(
    operatorCompletedStorageKeyV1()
  );
} catch (error) {
  // Browser storage may be unavailable.
}


operatorRenderCompletedReviewV1 =
  function operatorRenderDatabaseCompletedV2() {
    if (!operatorCompletedCards.length) {
      return `
        <div class="operator-completed-empty-v1">
          <i class="fa fa-check"></i>

          <div style="
            margin-bottom:5px;
            color:var(--text, #0f172a);
            font-size:14px;
            font-weight:900;
          ">
            No recent completion
          </div>

          <div style="
            color:var(--muted, #64748b);
            font-size:12px;
            line-height:1.45;
          ">
            New database-backed completions will appear here.
          </div>
        </div>
      `;
    }

    return `
      <div class="operator-recent-list-v1">
        ${operatorCompletedCards.map(
          function (card, index) {
            const latestClass =
              index === 0 ? "latest" : "";

            const completionId =
              operatorNumber(card.id, 0);

            const canUndo =
              Boolean(card.can_undo) &&
              completionId > 0;

            const undoButton = canUndo
              ? `
                <button
                  type="button"
                  class="operator-undo-btn-v2"
                  onclick="
                    openOperatorUndoModalV2(
                      ${completionId}
                    )
                  "
                >
                  <i
                    class="fa fa-undo"
                    style="margin-right:6px;"
                  ></i>
                  Undo Incorrect Entry
                </button>
              `
              : `
                <button
                  type="button"
                  class="operator-undo-btn-v2"
                  disabled
                >
                  Undo Not Available
                </button>
              `;

            return `
              <div
                class="
                  operator-recent-card-v1
                  ${latestClass}
                "
              >
                <div class="operator-recent-top-v1">
                  <div class="operator-recent-jc-v1">
                    ${esc(card.job_card_no || "-")}
                  </div>

                  <div class="operator-recent-status-v1">
                    <i class="fa fa-check-circle"></i>
                    Completed
                  </div>
                </div>

                <div
                  class="operator-recent-item-v1"
                  title="${esc(card.item_name || "")}"
                >
                  ${esc(card.item_name || "-")}
                </div>

                <div class="operator-recent-process-v1">
                  ${esc(card.completed_process || "-")}

                  <i
                    class="fa fa-arrow-right"
                    style="
                      margin:0 5px;
                      color:#94a3b8;
                    "
                  ></i>

                  ${esc(card.moved_to || "Completed")}
                </div>

                <div class="operator-recent-qty-v1">
                  <span class="operator-recent-ok-v1">
                    OK ${operatorNumber(card.ok_qty, 0)}
                  </span>

                  <span class="operator-recent-rejected-v1">
                    Not OK
                    ${operatorNumber(card.rejected_qty, 0)}
                  </span>

                  <span class="operator-recent-hold-v1">
                    Hold
                    ${operatorNumber(card.hold_qty, 0)}
                  </span>
                </div>

                <div class="operator-recent-footer-v1">
                  <span>
                    ${index === 0
                      ? "Latest completion"
                      : "Completed entry"}
                  </span>

                  <span>
                    ${esc(
                      operatorFormatCompletedTimeV1(
                        card.completed_at
                      )
                    )}
                  </span>
                </div>

                ${undoButton}
              </div>
            `;
          }
        ).join("")}
      </div>
    `;
  };


/* OPERATOR_UNDO_MODAL_UX_V3_START */

function operatorShowUndoInlineErrorV3(message) {
  const errorBox = document.getElementById(
    "operator-undo-inline-error-v3"
  );

  const errorText = document.getElementById(
    "operator-undo-inline-error-text-v3"
  );

  if (!errorBox || !errorText) return;

  errorText.textContent =
    String(message || "Please check the entered details.");

  errorBox.classList.add("visible");

  errorBox.scrollIntoView({
    behavior: "smooth",
    block: "nearest"
  });
}


function operatorClearUndoInlineErrorV3() {
  const errorBox = document.getElementById(
    "operator-undo-inline-error-v3"
  );

  const errorText = document.getElementById(
    "operator-undo-inline-error-text-v3"
  );

  if (errorText) {
    errorText.textContent = "";
  }

  if (errorBox) {
    errorBox.classList.remove("visible");
  }
}


/* OPERATOR_UNDO_MODAL_UX_V3_END */


function openOperatorUndoModalV2(completionId) {
  const card = operatorCompletedCards.find(
    function (record) {
      return (
        operatorNumber(record.id, 0) ===
        operatorNumber(completionId, 0)
      );
    }
  );

  if (!card) {
    showToast(
      "Completed entry was not found. Refresh the page.",
      "error"
    );
    return;
  }

  const modal = operatorEnsureUndoModalV2();

  modal.dataset.completionId = String(
    completionId
  );

  modal.innerHTML = `
    <div class="operator-undo-modal-panel-v2">
      <div class="operator-undo-modal-header-v2">
        <div class="operator-undo-modal-title-v2">
          <i
            class="fa fa-exclamation-triangle"
            style="margin-right:7px;"
          ></i>
          Undo Incorrect Entry
        </div>

        <button
          type="button"
          class="operator-undo-modal-close-v2"
          onclick="closeOperatorUndoModalV2()"
          aria-label="Close"
        >
          &times;
        </button>
      </div>

      <div style="padding:18px 18px 4px;">
        <div class="operator-undo-summary-v2">
          <strong>
            Job Card:
            ${esc(card.job_card_no || "-")}
          </strong>
          <br>

          ${esc(card.item_name || "-")}
          <br>

          Process:
          <strong>
            ${esc(card.completed_process || "-")}
          </strong>

          &nbsp;&rarr;&nbsp;

          ${esc(card.moved_to || "Completed")}
          <br>

          OK:
          <strong>
            ${operatorNumber(card.ok_qty, 0)}
          </strong>

          &nbsp;|&nbsp; Not OK:
          <strong>
            ${operatorNumber(card.rejected_qty, 0)}
          </strong>

          &nbsp;|&nbsp; Hold:
          <strong>
            ${operatorNumber(card.hold_qty, 0)}
          </strong>
        </div>

        <div class="operator-undo-field-v2">
          <label for="operator-undo-reason-v2">
            Why is this entry incorrect?
          </label>

          <select
            id="operator-undo-reason-v2"
            onchange="operatorToggleUndoOtherV2()"
          >
            <option value="">
              Select correction reason
            </option>

            <option value="Wrong quantity entered">
              Wrong quantity entered
            </option>

            <option value="Wrong job card completed">
              Wrong job card completed
            </option>

            <option value="Wrong process completed">
              Wrong process completed
            </option>

            <option value="Wrong rejection or hold details">
              Wrong rejection or hold details
            </option>

            <option value="Duplicate completion entry">
              Duplicate completion entry
            </option>

            <option value="Other">
              Other
            </option>
          </select>
        </div>

        <div
          class="operator-undo-field-v2"
          id="operator-undo-other-row-v2"
          style="display:none;"
        >
          <label for="operator-undo-other-v2">
            Enter the correction reason
          </label>

          <textarea
            id="operator-undo-other-v2"
            maxlength="255"
            placeholder="Explain what was entered incorrectly"
          ></textarea>
        </div>

        <div class="operator-undo-warning-v2">
          Undo will restore the previous process and quantity
          values. It will be blocked when this job card has
          already moved or another user has changed it.
        </div>

        <div
          id="operator-undo-inline-error-v3"
          class="operator-undo-inline-error-v3"
          role="alert"
        >
          <i class="fa fa-exclamation-circle"></i>

          <span id="operator-undo-inline-error-text-v3"></span>
        </div>
      </div>

      <div class="operator-undo-actions-v2">
        <button
          type="button"
          class="operator-undo-cancel-v2"
          onclick="closeOperatorUndoModalV2()"
        >
          Cancel
        </button>

        <button
          type="button"
          class="operator-undo-confirm-v2"
          id="operator-undo-confirm-btn-v2"
          onclick="confirmOperatorUndoV2()"
        >
          <i
            class="fa fa-undo"
            style="margin-right:6px;"
          ></i>
          Confirm Undo
        </button>
      </div>
    </div>
  `;

  modal.style.display = "flex";
}


function closeOperatorUndoModalV2() {
  const modal = document.getElementById(
    "operator-undo-modal-v2"
  );

  if (!modal) return;

  modal.style.display = "none";
  modal.dataset.completionId = "";
  modal.innerHTML = "";
}


function operatorToggleUndoOtherV2() {
  operatorClearUndoInlineErrorV3();

  const select = document.getElementById(
    "operator-undo-reason-v2"
  );

  const otherRow = document.getElementById(
    "operator-undo-other-row-v2"
  );

  if (!select || !otherRow) return;

  otherRow.style.display =
    select.value === "Other"
      ? "block"
      : "none";
}


async function confirmOperatorUndoV2() {
  const modal = document.getElementById(
    "operator-undo-modal-v2"
  );

  const completionId = operatorNumber(
    modal?.dataset?.completionId,
    0
  );

  const reasonSelect = document.getElementById(
    "operator-undo-reason-v2"
  );

  const otherInput = document.getElementById(
    "operator-undo-other-v2"
  );

  let undoReason = String(
    reasonSelect?.value || ""
  ).trim();

  if (undoReason === "Other") {
    undoReason = String(
      otherInput?.value || ""
    ).trim();
  }

  operatorClearUndoInlineErrorV3();

  if (!completionId) {
    operatorShowUndoInlineErrorV3(
      "Completion record is missing. Refresh the page and try again."
    );
    return;
  }

  if (!undoReason) {
    operatorShowUndoInlineErrorV3(
      reasonSelect?.value === "Other"
        ? "Please enter the correction reason."
        : "Please select why this entry is incorrect."
    );

    if (
      reasonSelect?.value === "Other"
    ) {
      otherInput?.focus();
    } else {
      reasonSelect?.focus();
    }

    return;
  }

  const button = document.getElementById(
    "operator-undo-confirm-btn-v2"
  );

  if (button) {
    button.disabled = true;
    button.innerHTML = `
      <i class="fa fa-spinner fa-spin"></i>
      Undoing...
    `;
  }

  try {
    const response = await fetch(
      "/api/operator/undo_completion",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          completion_id: completionId,
          undo_reason: undoReason
        })
      }
    );

    const data = await operatorReadJsonV2(
      response
    );

    closeOperatorUndoModalV2();

    showToast(
      data.message ||
      "Completion was undone successfully.",
      "success"
    );

    operatorPage = 0;

    await operatorRefreshWorkspaceV2(false);

  } catch (error) {
    console.error(
      "Operator Undo failed:",
      error
    );

    operatorShowUndoInlineErrorV3(
      error.message ||
      "Unable to undo this completion."
    );

  } finally {
    if (
      button &&
      document.body.contains(button)
    ) {
      button.disabled = false;
      button.innerHTML = `
        <i
          class="fa fa-undo"
          style="margin-right:6px;"
        ></i>
        Confirm Undo
      `;
    }
  }
}


/*
 * Replace only the Operator loading workflow.
 * Admin and Supervisor still use the original function.
 */
const _loadOperatorViewBeforeDatabaseV2 =
  loadOperatorView;


loadOperatorView =
  async function loadOperatorDatabaseWorkspaceV2() {
    if (!IS_OPERATOR_READ_ONLY) {
      return _loadOperatorViewBeforeDatabaseV2();
    }

    return operatorRefreshWorkspaceV2(true);
  };


/*
 * After a completion succeeds, refresh from MySQL.
 * The second refresh runs after the existing success animation.
 */
const _confirmOperatorCompleteBeforeDatabaseV2 =
  confirmOperatorComplete;


confirmOperatorComplete =
  async function confirmOperatorCompleteDatabaseV2() {
    // V2 override neutralised — our confirmOperatorComplete handles
    // partial/full completion, grid refresh, and loadRecentlyCompleted
    return await _confirmOperatorCompleteBeforeDatabaseV2();
  };


if (IS_OPERATOR_READ_ONLY) {
  setTimeout(function () {
    operatorRefreshWorkspaceV2(true);
  }, 0);
}

/* OPERATOR_DATABASE_RECENT_UNDO_UI_V2_END */



// OEE_MODAL_INPUT_UI_V3
// Operator-friendly OEE modal controls.
//
// Date:
//   Defaults to today, remains editable.
//
// Shift:
//   1st / 2nd pills.
//
// Time fields:
//   HH : MM : SS segmented inputs.
//   Auto-focus to next segment.
//   No colon typing required.
//   Start/End HH limited to 00-23.
//   MM/SS limited to 00-59.
//   Cycle/Load duration HH limited to 00-99.

(function () {

  const STYLE_ID =
    "oee-modal-input-ui-v3-style";


  function ensureStyles() {

    if (
      document.getElementById(
        STYLE_ID
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id = STYLE_ID;

    style.textContent = `

      .oee-shift-pills-v3 {
        display: flex;
        gap: 8px;
        width: 100%;
      }

      .oee-shift-pill-v3 {
        flex: 1;
        min-height: 40px;

        border:
          1px solid #cbd5e1;

        border-radius: 7px;

        background: #ffffff;
        color: #334155;

        font-size: 14px;
        font-weight: 700;

        cursor: pointer;
      }

      .oee-shift-pill-v3.active {
        background: #0b5cab;
        border-color: #0b5cab;
        color: #ffffff;
      }


      .oee-hms-group-v3 {
        display: flex;
        align-items: center;
        justify-content: center;

        width: 100%;
        min-height: 42px;

        padding: 4px 7px;

        box-sizing: border-box;

        border:
          1px solid #cbd5e1;

        border-radius: 7px;

        background: #ffffff;
      }


      .oee-hms-segment-v3 {
        width: 42px;
        height: 32px;

        box-sizing: border-box;

        border: 0;
        outline: 0;

        background: transparent;
        color: #0f172a;

        text-align: center;

        font-size: 16px;
        font-weight: 700;

        padding: 0;
      }


      .oee-hms-segment-v3:focus {
        background: #eef6ff;
        border-radius: 5px;
      }


      .oee-hms-colon-v3 {
        color: #475569;

        font-size: 18px;
        font-weight: 800;

        padding: 0 2px;
      }


      .oee-hms-group-v3:focus-within {
        border-color: #0b5cab;

        box-shadow:
          0 0 0 2px
          rgba(11, 92, 171, 0.10);
      }


      .oee-hms-hint-v3 {
        display: flex;
        justify-content: center;

        gap: 19px;

        margin-top: 3px;

        color: #94a3b8;

        font-size: 9px;
        font-weight: 700;

        letter-spacing: 0.4px;
      }

    `;

    document.head.appendChild(
      style
    );
  }


  function fieldKey(input) {

    return [
      input.id || "",
      input.name || "",
      input.placeholder || "",
      input.className || ""
    ]
      .join(" ")
      .toLowerCase()
      .replace(/[_-]+/g, " ");
  }


  function isOeeInput(input) {

    if (!input) {
      return false;
    }

    if (
      input.dataset.oeeHmsSegmentV3
    ) {
      return false;
    }

    if (
      fieldKey(input).includes("oee")
    ) {
      return true;
    }

    let parent =
      input.parentElement;

    for (
      let i = 0;
      parent && i < 6;
      i++
    ) {

      const text = [
        parent.id || "",
        parent.className || ""
      ]
        .join(" ")
        .toLowerCase();

      if (
        text.includes("oee")
      ) {
        return true;
      }

      parent =
        parent.parentElement;
    }

    return false;
  }


  function findInput(tokens) {

    return Array.from(
      document.querySelectorAll(
        "input"
      )
    ).find(input => {

      if (
        !isOeeInput(input)
      ) {
        return false;
      }

      const key =
        fieldKey(input);

      return tokens.every(
        token =>
          key.includes(token)
      );

    }) || null;
  }


  function findLabel(input) {

    if (
      !input
      || !input.id
    ) {
      return null;
    }

    return Array.from(
      document.querySelectorAll(
        "label"
      )
    ).find(
      label =>
        label.htmlFor === input.id
    ) || null;
  }


  function localToday() {

    const now =
      new Date();

    const yyyy =
      now.getFullYear();

    const mm =
      String(
        now.getMonth() + 1
      ).padStart(2, "0");

    const dd =
      String(
        now.getDate()
      ).padStart(2, "0");

    return (
      `${yyyy}-${mm}-${dd}`
    );
  }


  // ========================================================
  // DATE
  // ========================================================

  function setupDate() {

    const input =
      findInput([
        "entry",
        "date"
      ])
      || findInput([
        "date"
      ]);

    if (!input) {
      return;
    }

    if (
      input.type === "date"
      && !input.value
    ) {

      input.value =
        localToday();

      input.dispatchEvent(
        new Event(
          "change",
          {
            bubbles: true
          }
        )
      );
    }
  }


  // ========================================================
  // SHIFT
  // ========================================================

  function setupShift() {

    const input =
      findInput([
        "shift"
      ]);

    if (
      !input
      || input.dataset
        .oeeShiftV3 === "1"
    ) {
      return;
    }

    input.dataset
      .oeeShiftV3 = "1";

    input.type =
      "hidden";

    const wrap =
      document.createElement(
        "div"
      );

    wrap.className =
      "oee-shift-pills-v3";


    function makePill(
      label,
      value
    ) {

      const button =
        document.createElement(
          "button"
        );

      button.type =
        "button";

      button.className =
        "oee-shift-pill-v3";

      button.textContent =
        label;

      button.addEventListener(
        "click",
        () => {

          input.value =
            value;

          input.dispatchEvent(
            new Event(
              "input",
              {
                bubbles: true
              }
            )
          );

          input.dispatchEvent(
            new Event(
              "change",
              {
                bubbles: true
              }
            )
          );

          Array.from(
            wrap.children
          ).forEach(
            child =>
              child.classList
                .remove(
                  "active"
                )
          );

          button.classList.add(
            "active"
          );
        }
      );

      if (
        String(
          input.value || ""
        ) === value
      ) {
        button.classList.add(
          "active"
        );
      }

      return button;
    }


    wrap.appendChild(
      makePill(
        "1st",
        "1"
      )
    );

    wrap.appendChild(
      makePill(
        "2nd",
        "2"
      )
    );

    input.insertAdjacentElement(
      "afterend",
      wrap
    );
  }


  // ========================================================
  // HH : MM : SS CONTROL
  // ========================================================

  function makeSegment(
    placeholder,
    maxValue,
    type
  ) {

    const input =
      document.createElement(
        "input"
      );

    input.type =
      "text";

    input.inputMode =
      "numeric";

    input.maxLength =
      2;

    input.placeholder =
      placeholder;

    input.className =
      "oee-hms-segment-v3";

    input.dataset
      .oeeHmsSegmentV3 = "1";

    input.dataset
      .segmentType = type;

    input.dataset
      .maxValue =
        String(maxValue);

    return input;
  }


  function cleanSegment(
    input
  ) {

    let value =
      String(
        input.value || ""
      )
        .replace(
          /\D/g,
          ""
        )
        .slice(
          0,
          2
        );

    const type =
      input.dataset
        .segmentType;

    // Start / End Hour:
    // first digit cannot exceed 2.
    if (
      type === "clock-hour"
      && value.length >= 1
      && Number(
        value[0]
      ) > 2
    ) {
      value = "";
    }

    // Minute / Second:
    // first digit cannot exceed 5.
    if (
      (
        type === "minute"
        || type === "second"
      )
      && value.length >= 1
      && Number(
        value[0]
      ) > 5
    ) {
      value = "";
    }

    if (
      value.length === 2
    ) {

      const maxValue =
        Number(
          input.dataset
            .maxValue
        );

      if (
        Number(value)
        > maxValue
      ) {
        value =
          value[0];
      }
    }

    input.value =
      value;
  }


  function createHmsControl(
    initialValue,
    clockMode,
    onChange
  ) {

    const outer =
      document.createElement(
        "div"
      );

    const group =
      document.createElement(
        "div"
      );

    group.className =
      "oee-hms-group-v3";

    const hh =
      makeSegment(
        "HH",
        clockMode
          ? 23
          : 99,
        clockMode
          ? "clock-hour"
          : "duration-hour"
      );

    const mm =
      makeSegment(
        "MM",
        59,
        "minute"
      );

    const ss =
      makeSegment(
        "SS",
        59,
        "second"
      );


    function colon() {

      const span =
        document.createElement(
          "span"
        );

      span.className =
        "oee-hms-colon-v3";

      span.textContent =
        ":";

      return span;
    }


    group.appendChild(hh);
    group.appendChild(colon());
    group.appendChild(mm);
    group.appendChild(colon());
    group.appendChild(ss);


    const hint =
      document.createElement(
        "div"
      );

    hint.className =
      "oee-hms-hint-v3";

    hint.innerHTML =
      "<span>HR</span>"
      + "<span>MIN</span>"
      + "<span>SEC</span>";


    outer.appendChild(group);
    outer.appendChild(hint);


    const fields =
      [hh, mm, ss];


    function currentValue() {

      if (
        fields.every(
          field =>
            field.value.length === 2
        )
      ) {

        return (
          hh.value
          + ":"
          + mm.value
          + ":"
          + ss.value
        );
      }

      return "";
    }


    function notify() {

      onChange(
        currentValue(),
        {
          hour:
            Number(
              hh.value || 0
            ),

          minute:
            Number(
              mm.value || 0
            ),

          second:
            Number(
              ss.value || 0
            ),

          complete:
            fields.every(
              field =>
                field.value.length
                === 2
            ),

          partial:
            fields.some(
              field =>
                field.value.length
                > 0
            )
            &&
            !fields.every(
              field =>
                field.value.length
                === 2
            )
        }
      );
    }


    fields.forEach(
      (
        field,
        index
      ) => {

        field.addEventListener(
          "input",
          () => {

            cleanSegment(
              field
            );

            notify();

            if (
              field.value.length
              === 2
              && index
                < fields.length - 1
            ) {

              fields[
                index + 1
              ].focus();

              fields[
                index + 1
              ].select();
            }
          }
        );


        field.addEventListener(
          "keydown",
          event => {

            if (
              event.key ===
                "Backspace"
              && field.value === ""
              && index > 0
            ) {

              fields[
                index - 1
              ].focus();
            }

            if (
              event.key.length === 1
              && !/[0-9]/.test(
                event.key
              )
            ) {
              event.preventDefault();
            }
          }
        );


        field.addEventListener(
          "blur",
          () => {

            if (
              field.value.length
              === 1
            ) {

              field.value =
                field.value
                  .padStart(
                    2,
                    "0"
                  );

              notify();
            }
          }
        );
      }
    );


    if (initialValue) {

      const parts =
        String(
          initialValue
        ).split(":");

      if (
        parts.length >= 2
      ) {

        hh.value =
          String(
            parts[0] || "0"
          ).padStart(
            2,
            "0"
          );

        mm.value =
          String(
            parts[1] || "0"
          ).padStart(
            2,
            "0"
          );

        ss.value =
          String(
            parts[2] || "0"
          ).padStart(
            2,
            "0"
          );
      }
    }


    outer.dataset
      .oeeHmsControlV3 = "1";

    return outer;
  }


  // ========================================================
  // START / END
  // ========================================================

  function setupClockField(
    input
  ) {

    if (
      !input
      || input.dataset
        .oeeClockV3 === "1"
    ) {
      return;
    }

    input.dataset
      .oeeClockV3 = "1";

    let initial =
      input.value || "";

    if (
      initial
      && initial.split(":")
        .length === 2
    ) {
      initial += ":00";
    }

    input.type =
      "hidden";

    const control =
      createHmsControl(
        initial,
        true,
        value => {

          input.value =
            value;

          input.dispatchEvent(
            new Event(
              "input",
              {
                bubbles: true
              }
            )
          );

          input.dispatchEvent(
            new Event(
              "change",
              {
                bubbles: true
              }
            )
          );
        }
      );

    input.insertAdjacentElement(
      "afterend",
      control
    );
  }


  function setupStartEnd() {

    setupClockField(
      findInput([
        "start",
        "time"
      ])
    );

    setupClockField(
      findInput([
        "end",
        "time"
      ])
    );
  }


  // ========================================================
  // CYCLE / LOAD-UNLOAD
  // ========================================================

  function setupDuration(
    minutesInput,
    secondsInput,
    labelText
  ) {

    if (
      !minutesInput
      || !secondsInput
      || minutesInput.dataset
        .oeeDurationV3 === "1"
    ) {
      return;
    }

    minutesInput.dataset
      .oeeDurationV3 = "1";

    secondsInput.dataset
      .oeeDurationV3 = "1";


    const oldMinutes =
      Number(
        minutesInput.value || 0
      );

    const oldSeconds =
      Number(
        secondsInput.value || 0
      );


    const hours =
      Math.floor(
        oldMinutes / 60
      );

    const minutes =
      oldMinutes % 60;


    let initial = "";

    if (
      oldMinutes > 0
      || oldSeconds > 0
    ) {

      initial =
        String(hours)
          .padStart(
            2,
            "0"
          )
        + ":"
        + String(minutes)
          .padStart(
            2,
            "0"
          )
        + ":"
        + String(oldSeconds)
          .padStart(
            2,
            "0"
          );
    }


    minutesInput.type =
      "hidden";

    secondsInput.type =
      "hidden";


    const minLabel =
      findLabel(
        minutesInput
      );

    const secLabel =
      findLabel(
        secondsInput
      );


    if (minLabel) {
      minLabel.textContent =
        labelText;
    }


    if (secLabel) {
      secLabel.style.display =
        "none";
    }


    // Make Cycle / Load-Unload use the same
    // full field width as Start / End Time.
    const minuteContainer =
      minutesInput.parentElement;

    const secondContainer =
      secondsInput.parentElement;

    if (minuteContainer) {
      minuteContainer.style.width = "100%";
      minuteContainer.style.maxWidth = "100%";
      minuteContainer.style.gridColumn = "1 / -1";
      minuteContainer.style.flex = "1 1 100%";
    }

    if (
      secondContainer
      && secondContainer !== minuteContainer
    ) {
      secondContainer.style.display = "none";
    }

    // Original Cycle / Load-Unload layout had
    // separate Minute + Second columns.
    // Collapse that inner row to one full-width column.
    const durationRow =
      (
        minuteContainer
        && secondContainer
        && minuteContainer.parentElement
          === secondContainer.parentElement
      )
        ? minuteContainer.parentElement
        : null;

    if (durationRow) {
      durationRow.style.display = "grid";
      durationRow.style.gridTemplateColumns = "1fr";
      durationRow.style.width = "100%";
      durationRow.style.gap = "0";
    }


    const control =
      createHmsControl(
        initial,
        false,
        (
          value,
          parts
        ) => {

          if (
            parts.complete
          ) {

            minutesInput.value =
              String(
                parts.hour * 60
                + parts.minute
              );

            secondsInput.value =
              String(
                parts.second
              );

          } else {

            // Prevent stale values if operator
            // partially edits the duration.
            minutesInput.value =
              "";

            secondsInput.value =
              "";
          }


          [
            minutesInput,
            secondsInput
          ].forEach(
            input => {

              input.dispatchEvent(
                new Event(
                  "input",
                  {
                    bubbles: true
                  }
                )
              );

              input.dispatchEvent(
                new Event(
                  "change",
                  {
                    bubbles: true
                  }
                )
              );
            }
          );
        }
      );


    minutesInput.insertAdjacentElement(
      "afterend",
      control
    );
  }


  function setupCycleLoad() {

    setupDuration(
      findInput([
        "cycle",
        "minute"
      ]),

      findInput([
        "cycle",
        "second"
      ]),

      "Cycle Time"
    );


    let loadMinutes =
      findInput([
        "load",
        "minute"
      ]);

    let loadSeconds =
      findInput([
        "load",
        "second"
      ]);


    if (!loadMinutes) {
      loadMinutes =
        findInput([
          "unload",
          "minute"
        ]);
    }

    if (!loadSeconds) {
      loadSeconds =
        findInput([
          "unload",
          "second"
        ]);
    }


    setupDuration(
      loadMinutes,
      loadSeconds,
      "Load / Unload"
    );
  }


  // ========================================================
  // APPLY TO DYNAMIC MODAL
  // ========================================================

  function enhance() {

    ensureStyles();

    setupDate();
    setupShift();

    setupStartEnd();
    setupCycleLoad();
  }


  if (
    document.readyState
    === "loading"
  ) {

    document.addEventListener(
      "DOMContentLoaded",
      enhance
    );

  } else {

    enhance();
  }


  const observer =
    new MutationObserver(
      enhance
    );

  observer.observe(
    document.documentElement,
    {
      childList: true,
      subtree: true
    }
  );

})();


