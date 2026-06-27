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
  const s = (wipStatus || "pending").toLowerCase();
  if (s === "pending") return "pending";
  if (wipIdx === -1) return "completed";
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
      if (isSubcontract && state === "current") state = "subcontract";

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
        <div class="proc-pill-v2 pill-${state} ${isOverdue ? "pill-overdue" : ""} ${pillExtraClass} ${IS_OPERATOR_READ_ONLY ? "readonly-pill" : ""}"
             data-iidx="${iIdx}" data-jcno="${encodeURIComponent(jc.job_card_no)}"
             data-item="${encodeURIComponent(item.item_name)}" data-process="${encodeURIComponent(proc)}"
             data-pidx="${pIdx}" data-subcontract="${isSubcontract ? "1" : "0"}"
             title="${pillTitle}" style="${isRollbackPill ? "cursor:pointer;outline:2px dashed #f59e0b;outline-offset:-2px;" : ""}" ${(isClickable || isRollbackPill) ? clickHandler : ""}>
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
        ${item.wip_stage_days ? `<span style="font-size:12px;color:var(--muted);font-weight:500">${item.wip_stage_days} days in this stage</span>` : ""}
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

  const supOptions = data.supervisors.map(s => `<option value="${s}">${s}</option>`).join("");
  document.getElementById("bottom-supervisor").innerHTML =
    `<option value="">-- Select Supervisor --</option>${supOptions}`;
  renderSupervisorPicker(data.supervisors);
  document.getElementById("submit-info").textContent =
    `${data.items.length} item(s) loaded — select supervisor and submit`;
}

// ── DEV: Reset Job Card 500 ───────────────────────────────────────────────────
async function resetJC500() {
  if (!confirm("Are you sure? This will reset ALL data for JC 500.")) return;
  try {
    const res = await fetch("/api/dev/reset-jc500", { method: "POST" });
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
  if (IS_OPERATOR_READ_ONLY) return;
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

  if (wipIdx === -1) { showToast("All stages completed for this item.", "info"); return; }
  if (clickedPIdx < wipIdx) { showToast("This stage is already completed.", "info"); return; }
  if (clickedPIdx > wipIdx) {
    const processes = item.processes || [];
    const currentStageName = processes[wipIdx] || "current stage";
    showToast(`Complete "${currentStageName}" first before advancing to this stage.`, "warning");
    return;
  }

  const processes = item.processes || [];
  const nextStageName = wipIdx + 1 < processes.length ? processes[wipIdx + 1] : "Store";
  const plannedQty = item.so_qty || item.job_card_qty || "-";
  const actualQty = document.getElementById(`actual_${iIdx}`)?.value || item.actual_qty || "-";
  const wipBadge = document.getElementById(`wip - badge - ${iIdx}`);
  const currentWIP = item.wip_status || "Pending";

  pendingChange = {
    iIdx, jcNo, itemName, currentStage: currentWIP,
    newStage: isSubcontract ? clickedProc : nextStageName, isSubcontract
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
  document.getElementById("modal-title").textContent = "Change Stage?";
  document.getElementById("modal-note").textContent = "Supervisor must be selected at the bottom before confirming.";
  document.getElementById("subcontract-section").style.display = "block";
  document.getElementById("modal-confirm-btn").textContent = "Confirm";
  document.getElementById("modal-confirm-btn").style.background = "";
  document.getElementById("subcontract-checkbox").checked = false;
  document.getElementById("vendor-row").style.display = "none";
  document.getElementById("modal-vendor-name").value = "";

  updateRejReworkSection();
  document.getElementById("stage-modal").classList.add("open");
}

function closeStageModal() {
  document.getElementById("stage-modal").classList.remove("open");
  pendingChange = null;
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

// ── Subcontract vendor toggle ─────────────────────────────────────────────────
function toggleSubcontractVendor(checked) {
  if (IS_OPERATOR_READ_ONLY) return;
  document.getElementById("vendor-row").style.display = checked ? "block" : "none";
  const leadInput = document.getElementById("modal-lead-days");
  const hint = document.getElementById("lead-days-hint");
  if (checked) {
    let planLeadDays = 0;
    if (pendingChange) {
      const timeline = currentData?.items?.[pendingChange.iIdx]?.process_timeline || [];
      const target = (pendingChange.newStage || "").trim().toLowerCase();
      const match = timeline.find(t => (t.process_name || "").trim().toLowerCase() === target);
      planLeadDays = match ? parseInt(match.lead_days || 0) : 0;
    }
    if (planLeadDays > 0) {
      if (leadInput) { leadInput.value = planLeadDays; leadInput.setAttribute("readonly", "readonly"); }
      updateExpectedDate();
      if (hint) hint.textContent = " ";
    } else {
      if (leadInput) { leadInput.value = ""; leadInput.removeAttribute("readonly"); }
      if (hint) hint.textContent = "Not set in process plan — enter manually";
    }
  } else {
    if (leadInput) { leadInput.value = ""; leadInput.removeAttribute("readonly"); }
    if (hint) hint.textContent = "";
    const dateLabel = document.getElementById("modal-expected-date-label");
    if (dateLabel) dateLabel.textContent = "";
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
async function confirmStageChange() {
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

  const { jcNo, itemName, newStage, isSubcontract } = pendingChange;
  const supervisor = document.getElementById("bottom-supervisor").value || "Not Assigned";

  if (isSubcontract) {
    try {
      const res = await fetch("/api/wip/subcontract_complete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo, item_name: itemName,
          process: newStage, changed_by: supervisor
        })
      });
      const data = await res.json();
      if (data.success) { closeStageModal(); showToast(data.message, "success"); fetchJobCard(); }
      else showToast(data.error || "Failed", "error");
    } catch (e) { showToast("Server error", "error"); }
    return;
  }

  const sendToSubcontract = document.getElementById("subcontract-checkbox").checked;
  const vendorName = document.getElementById("modal-vendor-name").value.trim();

  if (sendToSubcontract) {
    if (!vendorName) { showToast("Please enter vendor name for subcontracting", "error"); return; }
    const leadDays = parseInt(document.getElementById("modal-lead-days")?.value) || 0;
    if (!leadDays || leadDays < 1) { showToast("Please enter lead days for subcontracting", "error"); return; }
    try {
      const res = await fetch("/api/wip/subcontract", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_card_no: jcNo, item_name: itemName, process: newStage,
          vendor_name: vendorName, lead_days: leadDays, changed_by: supervisor
        })
      });
      const data = await res.json();
      if (data.success) { closeStageModal(); showToast(`${newStage} sent to subcontracting — ${vendorName} `, "success"); fetchJobCard(); }
      else showToast(data.error || "Failed", "error");
    } catch (e) { showToast("Server error", "error"); }
    return;
  }

  const rejectedQty = 0;   // Reject/Rework UI disabled
  const reworkQty = 0;     // Reject/Rework UI disabled
  const reworkRemarks = "";

  try {
    const modalActualQtyValue = document.getElementById("modal-actual-qty")?.value || null;
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
        rework_remarks: reworkRemarks
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
  } catch (e) { showToast("Server error — is Flask running?", "error"); }
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

function loadPage3KanbanSummary() {
  // Kanban view disabled on Page 3.
}

/* Kanban view disabled on Page 3.
async function loadPage3KanbanSummary() {
  try {
    const res = await fetch("/api/page3/kanban_summary");
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
