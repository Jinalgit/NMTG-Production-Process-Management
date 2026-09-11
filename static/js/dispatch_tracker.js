/* ── Dispatch Tracker JS ─────────────────────────────────────────────────── */

let dtData = [];
let dtFilter = null;
let dtExpanded = false;
let dtPendingDd = null; // { job_card_no, item_name, old_date }

// ADVANCE_PLAN_ASSIGN_MODAL_V1
let dtAdvancePlanItemId = null;
let dtAdvancePlanEditingId = null;
let dtAdvancePlanData = null;
let dtAdvancePlanAllocations = [];
let dtAdvanceCustomerTimer = null;
// ADVANCE_PLAN_CUSTOMER_MASTER_ID_V1
let dtAdvanceCustomerMap = new Map();
let dtAdvancePlanSelectedCustomer = null;


// ── Helpers ───────────────────────────────────────────────────────────────────
function dtEsc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function dtFmtDate(str) {
  if (!str) return '—';
  const d = new Date(str + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function dtDaysText(days) {
  if (days === null || days === undefined) return '';
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return 'due today';
  return `${days}d left`;
}

function dtDeliveryClass(status) {
  if (status === 'overdue') return 'late';
  if (status === 'soon') return 'soon';
  return '';
}

function dtStatusChip(wip_status, delivery_status) {
  if (wip_status && wip_status.toLowerCase() === 'store') return '<span class="dt-chip green">✓ In Store</span>';
  if (delivery_status === 'overdue') return '<span class="dt-chip red">⚠ Overdue</span>';
  if (delivery_status === 'soon') return '<span class="dt-chip amber">⏰ Due Soon</span>';
  return '<span class="dt-chip blue">' + dtEsc(wip_status || 'In Progress') + '</span>';
}

// ── Load data ─────────────────────────────────────────────────────────────────
async function dtLoad() {
  document.getElementById('dt-tree').innerHTML =
    '<div class="dt-loading"><i class="fa fa-spinner fa-spin"></i> Loading dispatch data…</div>';

  try {
    const res = await fetch('/api/dispatch/tracker');
    const d = await res.json();
    if (!d.success) {
      document.getElementById('dt-tree').innerHTML =
        '<div class="dt-loading" style="color:#dc2626;">Failed to load: ' + dtEsc(d.error) + '</div>';
      return;
    }
    dtData = d.data || [];
    dtRenderSummary();
    dtRenderTree();
  } catch (e) {
    document.getElementById('dt-tree').innerHTML =
      '<div class="dt-loading" style="color:#dc2626;">Network error. Please refresh.</div>';
  }
}

function dtRefresh() { dtLoad(); }

// ── Summary ───────────────────────────────────────────────────────────────────
function dtRenderSummary() {
  let totalSO = 0, overdue = 0, soon = 0, store = 0, totalJC = 0;

  dtData.forEach(c => c.sos.forEach(so => {
    totalSO++;
    so.wos.forEach(wo => wo.jcs.forEach(jc => {
      totalJC++;
      if (jc.wip_status && jc.wip_status.toLowerCase() === 'store') store++;
      if (jc.delivery_status === 'overdue') overdue++;
      if (jc.delivery_status === 'soon') soon++;
    }));
  }));

  document.getElementById('dt-sum-so').textContent = totalSO;
  document.getElementById('dt-sum-overdue').textContent = overdue;
  document.getElementById('dt-sum-soon').textContent = soon;
  document.getElementById('dt-sum-store').textContent = store;
  document.getElementById('dt-sum-jc').textContent = totalJC;

  document.getElementById('dt-sum-overdue-card').onclick = () => dtSetFilter('overdue');
  document.getElementById('dt-sum-soon-card').onclick = () => dtSetFilter('soon');
}

// ── Render Tree ───────────────────────────────────────────────────────────────
function dtRenderTree() {
  const tree = document.getElementById('dt-tree');
  tree.innerHTML = '';

  if (!dtData.length) {
    tree.innerHTML = '<div class="dt-empty">No job cards found.</div>';
    return;
  }

  dtData.forEach(cust => {
    const soCount = cust.sos.length;
    const jcCount = cust.sos.reduce((a, so) => a + so.wos.reduce((b, wo) => b + wo.jcs.length, 0), 0);

    const custEl = document.createElement('div');
    custEl.className = 'dt-customer';
    custEl.dataset.customer = (cust.customer_name || '').toLowerCase();

    custEl.innerHTML = `
      <div class="dt-row" data-toggle>
        <div class="dt-caret">▶</div>
        <div>
          <div class="dt-cust-name">${dtEsc(cust.customer_name || 'Unknown')}</div>
          <div class="dt-cust-meta">${soCount} sales order${soCount !== 1 ? 's' : ''} · ${jcCount} job card${jcCount !== 1 ? 's' : ''}</div>
        </div>
        <div class="dt-spacer"></div>
        <span class="dt-badge">${soCount} SO</span>
      </div>
      <div class="dt-children"></div>`;

    const soWrap = custEl.querySelector('.dt-children');

    cust.sos.forEach(so => {
      const soEl = document.createElement('div');
      soEl.className = 'dt-so';
      soEl.dataset.so = (so.so_no || '').toLowerCase();

      // Find nearest delivery date for SO
      let nearestDate = null;
      let nearestStatus = 'ok';
      so.wos.forEach(wo => wo.jcs.forEach(jc => {
        if (jc.delivery_date && (!nearestDate || jc.delivery_date < nearestDate)) {
          nearestDate = jc.delivery_date;
          nearestStatus = jc.delivery_status;
        }
      }));

      const jcCountSo = so.wos.reduce((a, wo) => a + wo.jcs.length, 0);

      const canEditSoDd = window.JMS_IS_DISPATCH || window.JMS_IS_ADMIN;
      const soEditBtn = (canEditSoDd && so.so_no && so.so_no !== '—') ? `
        <button class="dt-edit-dd" onclick="event.stopPropagation(); dtOpenSoDdModal('${dtEsc(so.so_no)}', '${so.so_delivery_date || ''}')">
          <i class="fa fa-calendar"></i> Change SO Date
        </button>` : '';

      soEl.innerHTML = `
        <div class="dt-row" data-toggle>
          <div class="dt-caret">▶</div>
          <div>
            <div class="dt-so-num">${dtEsc(so.so_no || '—')}</div>
            <div class="dt-so-meta">SO date ${dtFmtDate(so.so_date)} · ${jcCountSo} job card${jcCountSo !== 1 ? 's' : ''}</div>
          </div>
          <div class="dt-spacer"></div>
          <div class="dt-datebox">
            <div class="d">${dtFmtDate(so.so_delivery_date)}</div>
            <div class="l">SO delivery</div>
          </div>
          ${soEditBtn}
        </div>
        <div class="dt-children"></div>`;

      const woWrap = soEl.querySelector('.dt-children');

      so.wos.forEach(wo => {
        const woEl = document.createElement('div');
        woEl.className = 'dt-wo';
        woEl.dataset.wo = (wo.work_order_no || '').toLowerCase();

        const doneJcs = wo.jcs.filter(j => j.wip_status && j.wip_status.toLowerCase() === 'store').length;
        const pct = wo.jcs.length > 0 ? Math.round(100 * doneJcs / wo.jcs.length) : 0;

        const woCurrentDd = wo.jcs.length > 0 && wo.jcs[0].wo_delivery_date
          ? wo.jcs[0].wo_delivery_date
          : '';
        const canEditWoDd = (window.JMS_IS_DISPATCH || window.JMS_IS_ADMIN) && wo.work_order_no && wo.work_order_no !== '—';
        const woEditBtn = canEditWoDd ? `
          <button class="dt-edit-dd" onclick="event.stopPropagation(); dtOpenWoDdModal('${dtEsc(wo.work_order_no)}', '${woCurrentDd}')">
            <i class="fa fa-calendar"></i> Change WO Date
          </button>` : '';
        woEl.innerHTML = `
          <div class="dt-row" data-toggle>
            <div class="dt-caret">▶</div>
            <div>
              <div class="dt-wo-num">${dtEsc(wo.work_order_no || '—')}</div>
              <div class="dt-wo-desc">${wo.jcs.length > 0 ? dtEsc(wo.jcs[0].item_name) : '—'}</div>
            </div>
            <div class="dt-spacer"></div>
            <span class="dt-qty">${wo.jcs.length} JC${wo.jcs.length !== 1 ? 's' : ''}</span>
            <div class="dt-progress"><div class="dt-progress-fill" style="width:${pct}%"></div></div>
            <div class="dt-datebox">
              <div class="d">${dtFmtDate(wo.wo_delivery_date)}</div>
              <div class="l">WO delivery</div>
            </div>
            ${woEditBtn}
          </div>
          <div class="dt-children"></div>`;

        const jcWrap = woEl.querySelector('.dt-children');

        wo.jcs.forEach(jc => {
          const jcEl = document.createElement('div');
          jcEl.className = 'dt-jc';
          jcEl.dataset.jc = (jc.job_card_no || '').toLowerCase();
          // DISPATCH_PARENT_CODE_SEARCH_V3
          jcEl.dataset.parentCode = (jc.parent_code || '').toLowerCase();

          // Build process rail
          const rail = (jc.processes || []).map(proc => {
            let cls = '';
            if (proc.is_completed) cls = 'done';
            else if (proc.in_progress) cls = 'now';
            return `<div class="dt-step ${cls}">
              <div class="dt-dot"></div>
              <div class="dt-step-label">${dtEsc(proc.process_name)}</div>
            </div>`;
          }).join('');

          const canEditDd = false; // DD now set at WO level
          const editBtn = '';


          const advancePlanBtn =
            jc.is_advance_plan && jc.item_id
              ? `<button
                   class="dt-ap-btn"
                   onclick="event.stopPropagation(); dtOpenAdvancePlanModal(${Number(jc.item_id)})"
                 >
                   Assign SO
                 </button>`
              : '';

          jcEl.innerHTML = `
            <div class="dt-jc-head">
              <span class="dt-jc-num">${dtEsc(jc.job_card_no)}</span>
              <span class="dt-jc-meta">${dtEsc(jc.item_name)} · Qty ${jc.so_qty}</span>
              <div class="dt-spacer"></div>
              ${advancePlanBtn}
              ${dtStatusChip(jc.wip_status, jc.delivery_status)}
              <div class="dt-datebox ${dtDeliveryClass(jc.delivery_status)}">
                <div class="d">${dtFmtDate(jc.delivery_date)}</div>
                <div class="l">${dtDaysText(jc.remaining_days)}</div>
              </div>
              ${editBtn}
            </div>
            <div class="dt-rail">${rail || '<span style="font-size:12px;color:var(--dt-gray);">No processes defined</span>'}</div>`;

          if (jc.is_advance_plan && jc.item_id) {
            const apHead = jcEl.querySelector('.dt-jc-head');

            if (apHead) {
              apHead.classList.add('dt-ap-clickable');
              apHead.title = 'Click to assign this Advance Plan Job Card';

              apHead.addEventListener('click', (event) => {
                if (event.target.closest('button')) return;
                dtOpenAdvancePlanModal(Number(jc.item_id));
              });
            }
          }

          // ASSIGNED_ADVANCE_MANAGE_ALLOCATION_V1
          if (jc.is_advance_allocation) {
            const manageAllocationBtn =
              document.createElement('button');

            manageAllocationBtn.type = 'button';
            manageAllocationBtn.className =
              'dt-edit-dd dt-ap-manage-allocation';

            manageAllocationBtn.innerHTML =
              '<i class="fa fa-edit"></i> Manage Allocation';

            manageAllocationBtn.title =
              'View or edit all allocations for this Job Card';

            manageAllocationBtn.addEventListener(
              'click',
              event => {
                event.stopPropagation();

                if (!jc.item_id) {
                  if (typeof showToast === 'function') {
                    showToast(
                      'Job Card item ID is missing.',
                      'error'
                    );
                  }
                  return;
                }

                dtOpenAdvancePlanModal(jc.item_id);
              }
            );

            const jcHead =
              jcEl.querySelector('.dt-jc-head');

            if (jcHead) {
              jcHead.appendChild(
                manageAllocationBtn
              );
            }
          }

          jcWrap.appendChild(jcEl);
        });

        woWrap.appendChild(woEl);
      });

      soWrap.appendChild(soEl);
    });

    tree.appendChild(custEl);
  });

  // Toggle on row click
  tree.addEventListener('click', e => {
    const row = e.target.closest('[data-toggle]');
    if (row) row.parentElement.classList.toggle('dt-open');
  });

  dtApplyFilters();
}

// ── Filters ───────────────────────────────────────────────────────────────────
function dtSetFilter(f) {
  dtFilter = dtFilter === f ? null : f;
  document.getElementById('dt-f-overdue').classList.toggle('on', dtFilter === 'overdue');
  document.getElementById('dt-f-soon').classList.toggle('on', dtFilter === 'soon');
  dtApplyFilters();
}

function dtToggleExpand() {
  dtExpanded = !dtExpanded;
  const btn = document.getElementById('dt-f-expand');
  btn.textContent = dtExpanded ? 'Collapse all' : 'Expand all';
  btn.classList.toggle('on', dtExpanded);
  document.querySelectorAll('.dt-customer, .dt-so, .dt-wo').forEach(el => {
    el.classList.toggle('dt-open', dtExpanded);
  });
}

function dtApplyFilters() {
  const term = (document.getElementById('dt-search')?.value || '').trim().toLowerCase();
  let anyVisible = false;

  document.querySelectorAll('.dt-customer').forEach(custEl => {
    let custVisible = false;

    custEl.querySelectorAll('.dt-so').forEach(soEl => {
      let soVisible = true;

      // Filter by overdue/soon
      if (dtFilter === 'overdue') {
        const hasOverdue = Array.from(soEl.querySelectorAll('.dt-jc')).some(jcEl =>
          jcEl.querySelector('.dt-chip.red'));
        if (!hasOverdue) soVisible = false;
      }
      if (dtFilter === 'soon') {
        const hasSoon = Array.from(soEl.querySelectorAll('.dt-jc')).some(jcEl =>
          jcEl.querySelector('.dt-chip.amber'));
        if (!hasSoon) soVisible = false;
      }

      // Search filter
      // DISPATCH_GRANULAR_SEARCH_V2
      if (term) {

        // ----------------------------------------------------
        // Detect what type of search the user is performing.
        // Parent Code gets highest priority.
        // ----------------------------------------------------

        const allJCs = Array.from(
          document.querySelectorAll('.dt-jc')
        );

        const allWOs = Array.from(
          document.querySelectorAll('.dt-wo')
        );

        const isParentCodeSearch = allJCs.some(jcEl =>
          String(
            jcEl.dataset.parentCode || ''
          ).toLowerCase().includes(term)
        );

        const isWOSearch =
          !isParentCodeSearch &&
          allWOs.some(woEl =>
            String(
              woEl.dataset.wo || ''
            ).toLowerCase().includes(term)
          );

        const customerMatch = String(
          custEl.dataset.customer || ''
        ).toLowerCase().includes(term);

        const soMatch = String(
          soEl.dataset.so || ''
        ).toLowerCase().includes(term);

        let soHasMatch = false;

        // Only direct WO children of this SO.
        const woElements = Array.from(
          soEl.querySelectorAll(
            ':scope > .dt-children > .dt-wo'
          )
        );

        woElements.forEach(woEl => {

          const woValue = String(
            woEl.dataset.wo || ''
          ).toLowerCase();

          const woMatch =
            woValue.includes(term);

          let woHasMatch = false;

          // Only direct JC children of this WO.
          const jcElements = Array.from(
            woEl.querySelectorAll(
              ':scope > .dt-children > .dt-jc'
            )
          );

          jcElements.forEach(jcEl => {

            const jcNo = String(
              jcEl.dataset.jc || ''
            ).toLowerCase();

            const parentCode = String(
              jcEl.dataset.parentCode || ''
            ).toLowerCase();

            const jcText = String(
              jcEl.textContent || ''
            ).toLowerCase();

            let jcMatch = false;

            // Parent Code search:
            // ONLY JCs belonging to matching PC.
            if (isParentCodeSearch) {

              jcMatch =
                parentCode.includes(term);

            }

            // Work Order search:
            // all JCs inside matching WO.
            else if (isWOSearch) {

              jcMatch = woMatch;

            }

            // Customer / SO / normal JC/item search.
            else {

              jcMatch =
                customerMatch ||
                soMatch ||
                jcNo.includes(term) ||
                jcText.includes(term);

            }

            jcEl.classList.toggle(
              'dt-hidden',
              !jcMatch
            );

            if (jcMatch) {
              woHasMatch = true;
            }
          });

          let showWO = false;

          if (isParentCodeSearch) {
            showWO = woHasMatch;
          }
          else if (isWOSearch) {
            showWO = woMatch;
          }
          else {
            showWO =
              customerMatch ||
              soMatch ||
              woMatch ||
              woHasMatch;
          }

          woEl.classList.toggle(
            'dt-hidden',
            !showWO
          );

          if (showWO) {
            woEl.classList.add('dt-open');
            soHasMatch = true;
          }
        });

        if (
          !soHasMatch &&
          !customerMatch &&
          !soMatch
        ) {
          soVisible = false;
        } else {
          soEl.classList.add('dt-open');
          custEl.classList.add('dt-open');
        }

      } else {

        // Search cleared -> restore WO + JC visibility.
        soEl.querySelectorAll(
          '.dt-wo, .dt-jc'
        ).forEach(el => {
          el.classList.remove('dt-hidden');
        });
      }

      soEl.classList.toggle('dt-hidden', !soVisible);
      if (soVisible) custVisible = true;
    });

    if ((dtFilter || term) && custVisible) custEl.classList.add('dt-open');
    custEl.classList.toggle('dt-hidden', !custVisible);
    if (custVisible) anyVisible = true;
  });

  document.getElementById('dt-empty').classList.toggle('dt-hidden', anyVisible);
}

// ── Delivery Date Modal ───────────────────────────────────────────────────────
function dtOpenDdModal(jobCardNo, itemName, currentDate) {
  dtPendingDd = { jobCardNo, itemName, currentDate };
  document.getElementById('dt-dd-modal-jc').textContent = `JC ${jobCardNo} · ${itemName}`;
  document.getElementById('dt-dd-new-date').value = currentDate || '';
  document.getElementById('dt-dd-reason').value = '';
  document.getElementById('dt-dd-reason-error').style.display = 'none';
  document.getElementById('dt-dd-modal').classList.add('open');
}

function dtOpenWoDdModal(workOrderNo, currentDate) {
  dtPendingDd = { workOrderNo, currentDate: currentDate || wo.wo_delivery_date };
  document.getElementById('dt-dd-modal-jc').textContent = `WO ${workOrderNo}`;
  document.getElementById('dt-dd-new-date').value = currentDate || '';
  document.getElementById('dt-dd-reason').value = '';
  document.getElementById('dt-dd-reason-error').style.display = 'none';
  document.getElementById('dt-dd-modal').classList.add('open');
}

function dtOpenSoDdModal(soNo, currentDate) {
  dtPendingDd = { soNo, currentDate };
  document.getElementById('dt-dd-modal-jc').textContent = `SO ${soNo}`;
  document.getElementById('dt-dd-new-date').value = currentDate || '';
  document.getElementById('dt-dd-reason').value = '';
  document.getElementById('dt-dd-reason-error').style.display = 'none';
  document.getElementById('dt-dd-modal').classList.add('open');
}

function dtCloseDdModal() {
  document.getElementById('dt-dd-modal').classList.remove('open');
  dtPendingDd = null;
}

async function dtConfirmDdChange() {
  const newDate = document.getElementById('dt-dd-new-date').value;
  const reason = (document.getElementById('dt-dd-reason').value || '').trim();

  if (!reason) {
    document.getElementById('dt-dd-reason-error').style.display = 'block';
    return;
  }
  document.getElementById('dt-dd-reason-error').style.display = 'none';

  if (!newDate || newDate === dtPendingDd.currentDate) {
    dtCloseDdModal();
    return;
  }

  const btn = document.getElementById('dt-dd-confirm-btn');
  btn.textContent = 'Saving…';
  btn.disabled = true;

  try {
    const isWoLevel = !!dtPendingDd.workOrderNo;
    const isSoLevel = !!dtPendingDd.soNo;
    const endpoint = isSoLevel
      ? '/api/dispatch/update_so_dd'
      : isWoLevel
        ? '/api/dispatch/update_wo_dd'
        : '/api/job_card/update_fields';
    const payload = isSoLevel
      ? { so_no: dtPendingDd.soNo, so_delivery_date: newDate, reason }
      : isWoLevel
        ? { work_order_no: dtPendingDd.workOrderNo, wo_delivery_date: newDate, reason }
        : { job_card_no: dtPendingDd.jobCardNo, original_item_name: dtPendingDd.itemName, delivery_date: newDate, dd_change_reason: reason };

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const d = await res.json();
    dtCloseDdModal();
    if (d.success) {
      if (typeof showToast === 'function') showToast('Delivery date updated.', 'success');
      dtLoad(); // refresh tree
    } else {
      if (typeof showToast === 'function') showToast(d.error || 'Update failed.', 'error');
    }
  } catch (e) {
    dtCloseDdModal();
    if (typeof showToast === 'function') showToast('Network error.', 'error');
  } finally {
    btn.textContent = 'Save Change';
    btn.disabled = false;
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────


// -----------------------------------------------------------------------------
// Advance Plan SO Assignment
// -----------------------------------------------------------------------------

async function dtOpenAdvancePlanModal(itemId) {
  dtAdvancePlanItemId = Number(itemId);
  dtAdvancePlanEditingId = null;

  const modal = document.getElementById('dt-ap-modal');

  modal.classList.add('open');

  document.getElementById('dt-ap-allocation-wrap').innerHTML =
    '<div class="dt-ap-empty">Loading...</div>';

  dtApClearForm();

  await dtApLoad();
}


function dtCloseAdvancePlanModal() {
  document.getElementById('dt-ap-modal').classList.remove('open');

  dtAdvancePlanItemId = null;
  dtAdvancePlanEditingId = null;
  dtAdvancePlanData = null;
  dtAdvancePlanAllocations = [];
}


async function dtApLoad() {
  if (!dtAdvancePlanItemId) return;

  try {
    const res = await fetch(
      `/api/advance-plan/allocations/${dtAdvancePlanItemId}`
    );

    const d = await res.json();

    if (!d.success) {
      throw new Error(d.error || 'Unable to load allocations.');
    }

    dtAdvancePlanData = d;
    dtAdvancePlanAllocations = d.allocations || [];

    const item = d.item || {};

    document.getElementById('dt-ap-jc-info').textContent =
      `JC ${item.job_card_no || ''} ? ${item.item_name || ''}`;

    document.getElementById('dt-ap-total').textContent =
      d.total_qty ?? 0;

    document.getElementById('dt-ap-assigned').textContent =
      d.assigned_qty ?? 0;

    document.getElementById('dt-ap-remaining').textContent =
      d.remaining_qty ?? 0;

    // ADVANCE_PLAN_ASSIGN_UI_V2
    const statusEl = document.getElementById('dt-ap-status');
    const allocationStatus =
      d.allocation_status || 'Unassigned';

    statusEl.textContent = allocationStatus;

    statusEl.classList.remove(
      'status-full',
      'status-partial',
      'status-unassigned'
    );

    if (allocationStatus === 'Fully Assigned') {
      statusEl.classList.add('status-full');
    } else if (allocationStatus === 'Partially Assigned') {
      statusEl.classList.add('status-partial');
    } else {
      statusEl.classList.add('status-unassigned');
    }

    const qtyHelp =
      document.getElementById('dt-ap-qty-help');

    if (qtyHelp) {
      qtyHelp.textContent =
        `Available for allocation: ${d.remaining_qty ?? 0}`;
    }

    if (!dtAdvancePlanEditingId) {
      const qty = document.getElementById('dt-ap-qty');

      qty.max = String(d.remaining_qty ?? 0);

      if ((d.remaining_qty ?? 0) === 0) {
        qty.value = '';
        qty.disabled = true;
        document.getElementById('dt-ap-save').disabled = true;
      } else {
        qty.disabled = false;
        document.getElementById('dt-ap-save').disabled = false;
      }
    }

    dtApRenderAllocations();

  } catch (e) {
    document.getElementById('dt-ap-allocation-wrap').innerHTML =
      `<div class="dt-ap-empty" style="color:#dc2626;">
         ${dtEsc(e.message || 'Failed to load allocations.')}
       </div>`;
  }
}


// ADVANCE_PLAN_HISTORY_UI_V4
function dtApRenderAllocations() {
  const wrap = document.getElementById(
    'dt-ap-allocation-wrap'
  );

  if (!dtAdvancePlanAllocations.length) {
    wrap.innerHTML = `
      <div class="dt-ap-history-empty">
        <div class="dt-ap-history-empty-title">
          No SO allocations yet
        </div>

        <div class="dt-ap-history-empty-text">
          Available quantity can be assigned using
          the form above.
        </div>
      </div>
    `;
    return;
  }

  const activeRows = dtAdvancePlanAllocations.filter(
    a => a.status === 'active'
  );

  const cancelledRows = dtAdvancePlanAllocations.filter(
    a => a.status === 'cancelled'
  );

  const cards = dtAdvancePlanAllocations.map(a => {
    const cancelled = a.status === 'cancelled';

    const actions = cancelled
      ? `
        <div class="dt-ap-history-no-action">
          No action
        </div>
      `
      : `
        <div class="dt-ap-history-actions">

          <button
            type="button"
            class="dt-ap-history-btn edit"
            data-ap-edit="${a.id}"
          >
            Edit
          </button>

          <button
            type="button"
            class="dt-ap-history-btn cancel"
            data-ap-cancel="${a.id}"
          >
            Cancel
          </button>

        </div>
      `;

    return `
      <div class="
        dt-ap-history-card
        ${cancelled ? 'cancelled' : 'active'}
      ">

        <div class="dt-ap-history-main">

          <div class="dt-ap-history-topline">

            <div class="dt-ap-history-so">
              <span>SO No.</span>
              <strong>${dtEsc(a.so_no || '?')}</strong>
            </div>

            <span class="
              dt-ap-history-status
              ${cancelled ? 'cancelled' : 'active'}
            ">
              ${cancelled ? 'Cancelled' : 'Active'}
            </span>

          </div>


          <div class="dt-ap-history-customer-label">
            Customer
          </div>

          <div class="dt-ap-history-customer-name">
            ${dtEsc(a.customer_name || '?')}
          </div>

        </div>


        <div class="dt-ap-history-qty">

          <span>
            Allocated Qty
          </span>

          <strong>
            ${Number(a.allocated_qty || 0)}
          </strong>

        </div>


        <div class="dt-ap-history-action-col">
          ${actions}
        </div>

      </div>
    `;
  }).join('');


  wrap.innerHTML = `

    <div class="dt-ap-history-overview">

      <div class="dt-ap-history-overview-text">
        <strong>
          ${activeRows.length}
        </strong>
        Active Allocation${activeRows.length === 1 ? '' : 's'}
      </div>

      <div class="dt-ap-history-divider"></div>

      <div class="dt-ap-history-overview-text muted">
        <strong>
          ${cancelledRows.length}
        </strong>
        Cancelled
      </div>

    </div>


    <div class="dt-ap-history-list">
      ${cards}
    </div>
  `;


  wrap.querySelectorAll('[data-ap-edit]').forEach(btn => {
    btn.addEventListener('click', () => {
      dtApStartEdit(
        Number(btn.dataset.apEdit)
      );
    });
  });


  wrap.querySelectorAll('[data-ap-cancel]').forEach(btn => {
    btn.addEventListener('click', () => {
      dtApCancelAllocation(
        Number(btn.dataset.apCancel)
      );
    });
  });
}


function dtApStartEdit(allocationId) {
  const a = dtAdvancePlanAllocations.find(
    x => Number(x.id) === Number(allocationId)
  );

  if (!a || a.status !== 'active') return;

  dtAdvancePlanEditingId = Number(allocationId);

  document.getElementById('dt-ap-form-title').textContent =
    'Edit SO Allocation';

  document.getElementById('dt-ap-so').value =
    a.so_no || '';

  document.getElementById('dt-ap-customer').value =
    a.customer_name || '';

  dtAdvancePlanSelectedCustomer =
    a.customer_master_id
      ? {
          id: Number(a.customer_master_id),
          customer_code: a.customer_code || '',
          full_customer_text: a.customer_name || ''
        }
      : null;

  document.getElementById('dt-ap-qty').disabled = false;

  document.getElementById('dt-ap-qty').value =
    Number(a.allocated_qty || 0);

  document.getElementById('dt-ap-save').disabled = false;
  document.getElementById('dt-ap-save').textContent =
    'Save Changes';

  document.getElementById('dt-ap-edit-cancel').style.display =
    'inline-block';
}

function dtApCancelEdit() {
  dtAdvancePlanEditingId = null;
  dtApClearForm();

  if (dtAdvancePlanData) {
    const remaining = Number(
      dtAdvancePlanData.remaining_qty || 0
    );

    document.getElementById('dt-ap-qty').max =
      String(remaining);

    document.getElementById('dt-ap-qty').disabled =
      remaining === 0;

    document.getElementById('dt-ap-save').disabled =
      remaining === 0;
  }
}


function dtApClearForm() {
  dtAdvancePlanSelectedCustomer = null;

  document.getElementById('dt-ap-form-title').textContent =
    'New SO Allocation';

  document.getElementById('dt-ap-so').value = '';
  document.getElementById('dt-ap-customer').value = '';
  document.getElementById('dt-ap-qty').value = '';

  document.getElementById('dt-ap-save').textContent =
    'Assign Quantity';

  document.getElementById('dt-ap-edit-cancel').style.display =
    'none';
}

async function dtApSave() {
  if (!dtAdvancePlanItemId) return;

  const soNo =
    (document.getElementById('dt-ap-so').value || '').trim();

  const customerText =
    (document.getElementById('dt-ap-customer').value || '').trim();

  const qty = Number(
    document.getElementById('dt-ap-qty').value || 0
  );

  if (!soNo) {
    if (typeof showToast === 'function') {
      showToast('SO No. is required.', 'error');
    }
    return;
  }

  if (!customerText) {
    if (typeof showToast === 'function') {
      showToast('Customer is required.', 'error');
    }
    return;
  }

  const customerKey = customerText.toLocaleLowerCase();

  let selectedCustomer = null;

  if (
    dtAdvancePlanSelectedCustomer &&
    String(
      dtAdvancePlanSelectedCustomer.full_customer_text || ''
    ).trim().toLocaleLowerCase() === customerKey
  ) {
    selectedCustomer = dtAdvancePlanSelectedCustomer;
  } else {
    selectedCustomer =
      dtAdvanceCustomerMap.get(customerKey) || null;
  }

  if (!selectedCustomer || !selectedCustomer.id) {
    if (typeof showToast === 'function') {
      showToast(
        'Please select the customer from Customer Master suggestions.',
        'error'
      );
    }
    return;
  }

  if (!Number.isInteger(qty) || qty <= 0) {
    if (typeof showToast === 'function') {
      showToast('Enter a valid allocation Qty.', 'error');
    }
    return;
  }

  const editing = !!dtAdvancePlanEditingId;

  const endpoint = editing
    ? `/api/advance-plan/allocations/${dtAdvancePlanEditingId}`
    : '/api/advance-plan/allocations';

  const payload = {
    so_no: soNo,
    customer_master_id: Number(selectedCustomer.id),
    customer_code: selectedCustomer.customer_code || '',
    customer_name:
      selectedCustomer.full_customer_text || customerText,
    allocated_qty: qty
  };

  if (!editing) {
    payload.job_card_item_id = dtAdvancePlanItemId;
  }

  const btn = document.getElementById('dt-ap-save');
  btn.disabled = true;

  try {
    const res = await fetch(endpoint, {
      method: editing ? 'PUT' : 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    const d = await res.json();

    if (!d.success) {
      throw new Error(d.error || 'Allocation failed.');
    }

    if (typeof showToast === 'function') {
      showToast(
        editing
          ? 'Allocation updated successfully.'
          : 'SO allocation created successfully.',
        'success'
      );
    }

    dtAdvancePlanEditingId = null;
    dtApClearForm();

    await dtApLoad();
    await dtLoad();

  } catch (e) {
    if (typeof showToast === 'function') {
      showToast(
        e.message || 'Allocation failed.',
        'error'
      );
    }
  } finally {
    btn.disabled = false;
  }
}

async function dtApCancelAllocation(allocationId) {
  const a = dtAdvancePlanAllocations.find(
    x => Number(x.id) === Number(allocationId)
  );

  if (!a) return;

  if (!window.confirm(
    `Cancel allocation ${a.so_no} / Qty ${a.allocated_qty}?`
  )) {
    return;
  }

  try {
    const res = await fetch(
      `/api/advance-plan/allocations/${allocationId}/cancel`,
      {
        method: 'POST'
      }
    );

    const d = await res.json();

    if (!d.success) {
      throw new Error(d.error || 'Cancellation failed.');
    }

    if (
      Number(dtAdvancePlanEditingId) === Number(allocationId)
    ) {
      dtAdvancePlanEditingId = null;
      dtApClearForm();
    }

    if (typeof showToast === 'function') {
      showToast(
        'Allocation cancelled successfully.',
        'success'
      );
    }

    await dtApLoad();

    // Reload customer/SO hierarchy after cancellation.
    await dtLoad();

  } catch (e) {
    if (typeof showToast === 'function') {
      showToast(
        e.message || 'Cancellation failed.',
        'error'
      );
    }
  }
}


// ADVANCE_PLAN_CANONICAL_CUSTOMER_PICK_V1
async function dtApSearchCustomers(query) {
  const list = document.getElementById(
    'dt-ap-customer-list'
  );

  if (!list) return;

  if (query.length < 2) {
    list.innerHTML = '';
    dtAdvanceCustomerMap.clear();
    return;
  }

  try {
    const res = await fetch(
      `/api/advance-plan/customer-search?q=${encodeURIComponent(query)}`
    );

    const rows = await res.json();

    if (!Array.isArray(rows)) {
      list.innerHTML = '';
      dtAdvanceCustomerMap.clear();
      return;
    }

    dtAdvanceCustomerMap.clear();

    rows.forEach(row => {
      const full = String(
        row.full_customer_text ||
        row.customer_name ||
        ''
      ).trim();

      if (!full || !row.id) return;

      dtAdvanceCustomerMap.set(
        full.toLocaleLowerCase(),
        {
          id: Number(row.id),
          customer_code: row.customer_code || '',
          customer_name: row.customer_name || '',
          full_customer_text: full
        }
      );
    });

    list.innerHTML = rows.map(row => {
      const full =
        row.full_customer_text ||
        row.customer_name ||
        '';

      return `
        <option
          value="${dtEsc(full)}"
          label="${dtEsc(
            row.customer_code
              ? row.customer_code + ' - ' + row.customer_name
              : row.customer_name
          )}"
        ></option>
      `;
    }).join('');

  } catch (e) {
    list.innerHTML = '';
    dtAdvanceCustomerMap.clear();
  }
}

document.addEventListener('input', event => {
  if (event.target.id !== 'dt-ap-customer') return;

  clearTimeout(dtAdvanceCustomerTimer);

  const query = (event.target.value || '').trim();
  const key = query.toLocaleLowerCase();

  dtAdvancePlanSelectedCustomer =
    dtAdvanceCustomerMap.get(key) || null;

  dtAdvanceCustomerTimer = setTimeout(() => {
    dtApSearchCustomers(query);
  }, 250);
});

document.addEventListener('keydown', event => {
  if (
    event.key === 'Escape' &&
    document.getElementById('dt-ap-modal')?.classList.contains('open')
  ) {
    dtCloseAdvancePlanModal();
  }
});


document.addEventListener('DOMContentLoaded', dtLoad);


// ============================================================
// ASSIGNED ADVANCE PLAN VIEW
// ============================================================
// ASSIGNED_ADVANCE_PLAN_VIEW_V1

let dtAssignedAdvanceOnly = false;

function dtApplyAssignedAdvanceView() {
  // Always restore WO visibility first.
  document.querySelectorAll('.dt-wo').forEach(woEl => {
    woEl.classList.remove('dt-hidden');
  });

  // Run all existing Dispatch Tracker filters first.
  dtOriginalApplyFilters();

  if (!dtAssignedAdvanceOnly) return;

  document.querySelectorAll('.dt-customer').forEach(custEl => {
    let customerHasAssigned = false;

    custEl.querySelectorAll('.dt-so').forEach(soEl => {
      // Preserve any existing search/overdue/soon filtering.
      const alreadyHidden = soEl.classList.contains('dt-hidden');

      let soHasAssigned = false;

      soEl.querySelectorAll('.dt-wo').forEach(woEl => {
        const woName = String(
          woEl.dataset.wo || ''
        ).trim().toLowerCase();

        const isAdvanceAllocation =
          woName === 'advance allocation';

        woEl.classList.toggle(
          'dt-hidden',
          !isAdvanceAllocation
        );

        if (isAdvanceAllocation) {
          soHasAssigned = true;
          woEl.classList.add('dt-open');
        }
      });

      if (!soHasAssigned || alreadyHidden) {
        soEl.classList.add('dt-hidden');
      } else {
        soEl.classList.remove('dt-hidden');
        soEl.classList.add('dt-open');
        customerHasAssigned = true;
      }
    });

    custEl.classList.toggle(
      'dt-hidden',
      !customerHasAssigned
    );

    if (customerHasAssigned) {
      custEl.classList.add('dt-open');
    }
  });
}


// Keep existing dtApplyFilters logic untouched.
// Add Assigned Advance Plan filtering after it.
const dtOriginalApplyFilters = dtApplyFilters;

dtApplyFilters = function () {
  dtApplyAssignedAdvanceView();
};


function dtInitAssignedAdvanceView() {
  if (document.getElementById('dt-f-assigned-advance')) {
    return;
  }

  const expandBtn = document.getElementById('dt-f-expand');

  if (!expandBtn) {
    console.warn(
      'Assigned Advance Plan button anchor not found.'
    );
    return;
  }

  const btn = expandBtn.cloneNode(false);

  btn.id = 'dt-f-assigned-advance';
  btn.textContent = 'Assigned Advance Plan';
  btn.classList.remove('on');

  expandBtn.insertAdjacentElement('afterend', btn);

  btn.addEventListener('click', () => {
    dtAssignedAdvanceOnly = !dtAssignedAdvanceOnly;

    btn.classList.toggle(
      'on',
      dtAssignedAdvanceOnly
    );

    btn.textContent = dtAssignedAdvanceOnly
      ? 'Assigned Advance Plan ?'
      : 'Assigned Advance Plan';

    dtApplyFilters();
  });
}


if (document.readyState === 'loading') {
  document.addEventListener(
    'DOMContentLoaded',
    dtInitAssignedAdvanceView
  );
} else {
  dtInitAssignedAdvanceView();
}


// ============================================================
// DISPATCH TRACKER - EXCEL EXPORT BUTTON
// ============================================================
// DISPATCH_EXCEL_EXPORT_BUTTON_V1

function dtInitExcelExportButton() {
  if (document.getElementById('dt-export-excel')) {
    return;
  }

  const expandBtn = document.getElementById('dt-f-expand');

  if (!expandBtn) {
    console.warn('Dispatch Export button anchor not found.');
    return;
  }

  const btn = document.createElement('button');

  btn.type = 'button';
  btn.id = 'dt-export-excel';
  btn.className = expandBtn.className;
  btn.textContent = 'Export Excel';
  btn.title = 'Export Dispatch Tracker to Excel';

  expandBtn.insertAdjacentElement('afterend', btn);

  btn.addEventListener('click', () => {
    const oldText = btn.textContent;

    btn.disabled = true;
    btn.textContent = 'Exporting...';

    window.location.href =
      '/api/dispatch-tracker/export-excel';

    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = oldText;
    }, 1500);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener(
    'DOMContentLoaded',
    dtInitExcelExportButton
  );
} else {
  dtInitExcelExportButton();
}


// ============================================================
// ADVANCE PLAN - ALLOCATION QTY MAX VALIDATION
// ============================================================
// ADVANCE_PLAN_QTY_MAX_VALIDATION_V1

function dtApApplyQtyMaxValidation() {

  // Find Allocation Qty number input
  const qtyInput = Array.from(
    document.querySelectorAll('input[type="number"]')
  ).find(input => {
    const context = String(
      (
        input.closest('form') ||
        input.parentElement?.parentElement ||
        input.parentElement
      )?.textContent || ''
    ).toLowerCase();

    const identity = (
      String(input.id || '') + ' ' +
      String(input.name || '') + ' ' +
      context
    ).toLowerCase();

    return identity.includes('allocation qty');
  });

  if (!qtyInput) return;

  // Find Remaining Qty value from the allocation modal
  const allElements = Array.from(
    document.querySelectorAll('*')
  );

  const remainingLabel = allElements.find(el =>
    el.children.length === 0 &&
    String(el.textContent || '')
      .trim()
      .toLowerCase() === 'remaining qty'
  );

  if (!remainingLabel) return;

  let box = remainingLabel.parentElement;
  let remainingQty = null;

  // Walk upward until numeric Remaining Qty is found
  for (let i = 0; i < 4 && box; i++) {

    const text = String(box.textContent || '')
      .replace(/remaining qty/i, ' ')
      .trim();

    const match = text.match(/\b\d+\b/);

    if (match) {
      remainingQty = Number(match[0]);
      break;
    }

    box = box.parentElement;
  }

  if (
    remainingQty === null ||
    Number.isNaN(remainingQty)
  ) return;

  qtyInput.max = String(remainingQty);
  qtyInput.min = '1';

  if (qtyInput.dataset.qtyMaxValidation === '1') {
    return;
  }

  qtyInput.dataset.qtyMaxValidation = '1';

  qtyInput.addEventListener('input', () => {

    const maxQty = Number(qtyInput.max || 0);
    const enteredQty = Number(qtyInput.value || 0);

    if (
      maxQty >= 0 &&
      enteredQty > maxQty
    ) {
      qtyInput.value = String(maxQty);

      qtyInput.setCustomValidity(
        `Maximum available quantity is ${maxQty}.`
      );
    } else {
      qtyInput.setCustomValidity('');
    }
  });

  qtyInput.addEventListener('change', () => {

    const maxQty = Number(qtyInput.max || 0);
    const enteredQty = Number(qtyInput.value || 0);

    if (enteredQty > maxQty) {
      qtyInput.value = String(maxQty);
    }

    qtyInput.setCustomValidity('');
  });
}


// Apply whenever modal data changes / opens
const dtApQtyValidationObserver =
  new MutationObserver(() => {
    window.requestAnimationFrame(
      dtApApplyQtyMaxValidation
    );
  });

if (document.body) {
  dtApQtyValidationObserver.observe(
    document.body,
    {
      childList: true,
      subtree: true,
      characterData: true
    }
  );
}

document.addEventListener(
  'focusin',
  event => {
    if (
      event.target &&
      event.target.matches('input[type="number"]')
    ) {
      dtApApplyQtyMaxValidation();
    }
  }
);


