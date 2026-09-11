// -- jc_review.js -- Job Card Upload Review Page ---
//
// Required change in upload.js (confirmUpload / handleFileSelect):
//   After a successful upload_preview call, if it returns a review_token:
//
//   const token = data.review_token;
//   sessionStorage.setItem('jms_preview_rows_' + token, JSON.stringify(data.preview_rows));
//   window.location.href = '/jc_review?token=' + encodeURIComponent(token);
//
// ---

// -- State ---
let reviewToken    = null;
let reviewRecords  = [];   // visible non-duplicate records
let batchRecordCount = 0;   // total records returned by batch API
let previewRows    = [];   // original rows from sessionStorage (for upload_confirm)
let activeFilter   = null; // null | status string | 'READY' | 'PENDING'
let activeRecordId = null; // currently open panel record id
let editMode       = false;
let editedProcs    = [];   // copy of uploaded_processes in edit mode
let addProcVisible = false;
let importInProgress = false;
const expandedGroups = new Set();
const collapsedGroups = new Set();
let reviewProcessNames = [];
let previouslyApprovedExpanded = false;

// -- Status configuration ---
const STATUS_CFG = {
  MATCH:                    { label: 'Ready to import', cls: 'st-match',   icon: 'check-circle' },
  REUSED_APPROVAL:          { label: 'Previously approved', cls: 'st-reused',  icon: 'history' },
  MISSING_PROCESS:          { label: 'Missing process', cls: 'st-missing', icon: 'exclamation-circle' },
  EXTRA_PROCESS:            { label: 'Extra process',   cls: 'st-extra',   icon: 'plus-circle' },
  ORDER_MISMATCH:           { label: 'Route order differs', cls: 'st-order',   icon: 'sort-amount-asc' },
  NEW_ITEM_REVIEW_REQUIRED: { label: 'New item',        cls: 'st-newitem', icon: 'tag' },
  PROCESS_ROUTE_NOT_FOUND:  { label: 'No Process Master route', cls: 'st-noroute', icon: 'ban' },
  ITEM_CODE_REQUIRED:       { label: 'No item code',    cls: 'st-nocode',  icon: 'times-circle' },
};

const STAT_CARDS = [
  { key: 'total',   label: 'Uploaded',       filter: null,                       icon: 'list-ul', primary: true },
  { key: 'ready',   label: 'Ready',          filter: 'READY',                    icon: 'check-circle', primary: true },
  { key: 'pending', label: 'Need Review',    filter: 'PENDING',                  icon: 'hourglass-half', primary: true },
  { key: 'missing', label: 'Missing',        filter: 'MISSING_PROCESS',          icon: 'exclamation-circle' },
  { key: 'extra',   label: 'Extra',          filter: 'EXTRA_PROCESS',            icon: 'plus-circle' },
  { key: 'order',   label: 'Order mismatch', filter: 'ORDER_MISMATCH',           icon: 'sort-amount-asc' },
  { key: 'newitem', label: 'New item',       filter: 'NEW_ITEM_REVIEW_REQUIRED', icon: 'tag' },
  { key: 'noroute', label: 'No route',       filter: 'PROCESS_ROUTE_NOT_FOUND',  icon: 'ban' },
];

// -- Init ---
document.addEventListener('DOMContentLoaded', function () {
  reviewToken = new URLSearchParams(window.location.search).get('token');

  if (!reviewToken || reviewToken === 'null') {
    showError('No review token found in URL. Please upload a job card file first.');
    return;
  }

  document.getElementById('batch-token-display').textContent = reviewToken;

  const stored = sessionStorage.getItem('jms_preview_rows_' + reviewToken);
  if (stored) {
    try { previewRows = JSON.parse(stored); } catch (e) { previewRows = []; }
  }

  loadBatch();
});

// -- API - Load batch ---
async function loadBatch() {
  setPageState('loading');
  try {
    const res  = await fetch('/api/job_card/review/batch/' + encodeURIComponent(reviewToken));
    const data = await res.json();

    if (!data.success) {
      showError(data.error || 'Failed to load review batch.');
      return;
    }

    const allBatchRecords = (data.records || []).map(normalizeRecord);

    batchRecordCount = Number(data.record_count || allBatchRecords.length);

    reviewRecords = allBatchRecords.filter(function (record) {
      return record.status !== 'DUPLICATE';
    });

    const fileNames = [...new Set(
      allBatchRecords.map(r => r.source_file).filter(Boolean)
    )];
    const fileSummary = fileNames.length > 3
      ? fileNames.length + ' files'
      : (fileNames.length ? fileNames.join(', ') : 'Unknown files');
    document.getElementById('batch-files-display').textContent =
      fileSummary;
    document.getElementById('batch-count-display').textContent =
      batchRecordCount + ' record' + (batchRecordCount !== 1 ? 's' : '');
    document.getElementById('batch-info-bar').style.display = 'flex';

    setPageState('loaded');
    renderStatCards();
    applyFilter();
    updateImportButton();

  } catch (err) {
    showError('Network error: ' + err.message);
  }
}

function normalizeRecord(r) {
  return {
    id:               r.id,
    jc_no:            r.job_card_no || '',
    bom_no:           r.bom_no || '',
    parent_code:      r.parent_code || '',
    child_code:       r.child_code || '',
    item_name:        r.item_name || '',

    source_file:      r.source_file || '',
    status:           r.review_status || 'UNKNOWN',
    uploaded:         parseProcs(r.uploaded_processes),
    master:           parseProcs(r.master_processes),
    is_resolved:      !!r.is_resolved,
    review_decision:  r.review_decision || '',
    message:          r.review_message  || '',
  };
}

function parseProcs(val) {
  if (!val) return [];
  if (Array.isArray(val)) return val.filter(Boolean);
  if (typeof val === 'string') {
    const trimmed = val.trim();
    if (trimmed.startsWith('[')) {
      try { return JSON.parse(trimmed).filter(Boolean); } catch (e) { /* fall through */ }
    }
    return trimmed.split(',').map(s => s.trim()).filter(Boolean);
  }
  return [];
}

// -- Counts ---
function isReadyRecord(record) {
  return (
    record.status === 'REUSED_APPROVAL'
    || (
      record.status === 'MATCH'
      && record.is_resolved
    )
  );
}

function getCounts() {
  const c = { total: batchRecordCount, ready: 0, pending: 0,
              missing: 0, extra: 0, order: 0, newitem: 0, noroute: 0 };
  reviewRecords.forEach(r => {
    if (isReadyRecord(r)) c.ready++; else c.pending++;
    if (r.status === 'MISSING_PROCESS')          c.missing++;
    if (r.status === 'EXTRA_PROCESS')            c.extra++;
    if (r.status === 'ORDER_MISMATCH')           c.order++;
    if (r.status === 'NEW_ITEM_REVIEW_REQUIRED') c.newitem++;
    if (r.status === 'PROCESS_ROUTE_NOT_FOUND')  c.noroute++;
  });
  return c;
}

// -- Stat cards ---
function renderStatCards() {
  const c    = getCounts();
  const vals = { total: c.total, ready: c.ready, pending: c.pending,
                 missing: c.missing, extra: c.extra, order: c.order,
                 newitem: c.newitem, noroute: c.noroute };

  document.getElementById('stat-grid').innerHTML = STAT_CARDS.map(function (sc) {
    const active = activeFilter === sc.filter ? ' active' : '';
    const filterAttr = sc.filter === null ? 'null' : sc.filter;
    const value = vals[sc.key];
    const primary = sc.primary ? ' stat-card-primary' : ' stat-card-secondary';
    const zero = !sc.primary && value === 0 ? ' stat-card-zero' : '';
    return '<button class="stat-card' + primary + zero + active + '" onclick="setFilter(\'' + filterAttr + '\')" type="button" aria-pressed="' + (activeFilter === sc.filter) + '">'
      + '<span class="sc-icon"><i class="fa fa-' + sc.icon + '" aria-hidden="true"></i></span>'
      + '<span class="sc-label">' + esc(sc.label) + '</span>'
      + '<span class="sc-value">' + value + '</span>'
      + '<span class="sc-filter">Filter</span>'
      + '</button>';
  }).join('');
}

function setFilter(filterStr) {
  const sf = (filterStr === 'null' || filterStr === null) ? null : filterStr;
  activeFilter = (activeFilter === sf) ? null : sf;
  renderStatCards();
  applyFilter();
}

function clearFilter() {
  activeFilter = null;
  document.getElementById('search-input').value = '';
  document.getElementById('clear-filter-btn').style.display = 'none';
  document.getElementById('filter-count').textContent = '';
  renderStatCards();
  renderTable(reviewRecords);
}

// -- Filter + search ---
function getFilteredRecords() {
  const q = (document.getElementById('search-input').value || '').toLowerCase().trim();
  return reviewRecords.filter(function (r) {
    const matchSearch = !q
      || r.jc_no.toLowerCase().includes(q)
      || r.bom_no.toLowerCase().includes(q)
      || r.parent_code.toLowerCase().includes(q)
      || r.child_code.toLowerCase().includes(q)
      || r.item_name.toLowerCase().includes(q);

    let matchFilter = true;
    if (activeFilter === 'READY')   matchFilter = isReadyRecord(r);
    else if (activeFilter === 'PENDING') matchFilter = !(isReadyRecord(r));
    else if (activeFilter)          matchFilter = r.status === activeFilter;

    return matchSearch && matchFilter;
  });
}

function applyFilter() {
  const q    = (document.getElementById('search-input').value || '').trim();
  const rows = getFilteredRecords();

  const clearBtn = document.getElementById('clear-filter-btn');
  const countLbl = document.getElementById('filter-count');

  if (activeFilter || q) {
    clearBtn.style.display = '';
    countLbl.textContent   = rows.length + ' of ' + reviewRecords.length + ' records';
  } else {
    clearBtn.style.display = 'none';
    countLbl.textContent   = '';
  }

  renderTable(rows);
}

// -- Table ---

// Grouping: Parent Code + Child Code
// BOM No remains record-level information because one linkage may have
// multiple Job Cards with different BOM numbers.
function getGroupKey(record) {
  return [
    record.parent_code || '__STANDALONE__',
    record.child_code || ''
  ].join('||');
}

function groupReviewRecords(rows) {
  const groups = new Map();

  rows.forEach(function (record) {
    const key = getGroupKey(record);

    if (!groups.has(key)) {
      groups.set(key, {
        key: key,
        parent_code: record.parent_code || '',
        child_code: record.child_code || '',
        item_name: record.item_name || '',
        bom_numbers: [],
        records: []
      });
    }

    const group = groups.get(key);
    const bomNo = String(record.bom_no || '').trim();

    if (bomNo && !group.bom_numbers.includes(bomNo)) {
      group.bom_numbers.push(bomNo);
    }

    group.records.push(record);
  });

  return Array.from(groups.values());
}

function toggleReviewGroup(encodedKey) {
  const key = decodeURIComponent(encodedKey);

  if (collapsedGroups.has(key)) {
    collapsedGroups.delete(key);
    expandedGroups.add(key);
  } else {
    expandedGroups.delete(key);
    collapsedGroups.add(key);
  }

  applyFilter();
}

function renderTable(rows) {
  const tbody = document.getElementById('review-table-body');
  const pendingRows = rows.filter(function (record) {
    return record.status !== 'REUSED_APPROVAL' && !isReadyRecord(record);
  });
  const readyRows = rows.filter(function (record) {
    return record.status !== 'REUSED_APPROVAL' && isReadyRecord(record);
  });
  const reusedRows = rows.filter(function (record) {
    return record.status === 'REUSED_APPROVAL';
  });

  renderNeedsReviewSection(pendingRows);
  renderReadyToImportSection(readyRows);
  renderPreviouslyApprovedSection(reusedRows);

  if (!pendingRows.length) {
    tbody.innerHTML =
      '<tr><td colspan="8" class="review-empty-cell">'
      + needsReviewEmptyText(rows, readyRows, reusedRows)
      + '</td></tr>';
    return;
  }

  tbody.innerHTML = renderGroupedRows(pendingRows, { defaultExpanded: true });
}

function renderNeedsReviewSection(rows) {
  const countEl = document.getElementById('needs-review-count');
  const copyEl = document.getElementById('needs-review-copy');
  if (countEl) {
    countEl.textContent = rows.length + ' pending';
  }
  if (copyEl) {
    copyEl.textContent = rows.length
      ? 'Records that need a route decision before import.'
      : 'All review issues are resolved.';
  }
}

function renderReadyToImportSection(rows) {
  const section = document.getElementById('ready-import-section');
  const countEl = document.getElementById('ready-import-count');
  const tbody = document.getElementById('ready-import-body-rows');

  if (!section || !countEl || !tbody) return;

  section.style.display = rows.length ? '' : 'none';
  countEl.textContent = rows.length + ' ready';

  tbody.innerHTML = rows.length
    ? renderFlatRows(rows)
    : '<tr><td colspan="8" class="review-empty-cell">No Job Cards are currently ready to import.</td></tr>';
}

function needsReviewEmptyText(rows, readyRows, reusedRows) {
  if (!reviewRecords.length) return 'No new Job Cards require review.';
  if (!rows.length && !readyRows.length && !reusedRows.length) return 'No records match the current filter.';
  if (readyRows.length || reusedRows.length) return 'All review issues are resolved.';
  return 'No records match the current filter.';
}

function renderGroupedRows(rows, options) {
  options = options || {};
  const groups = groupReviewRecords(rows);
  let serialNo = 0;
  let html = '';

  groups.forEach(function (group) {
    const isExpanded = options.defaultExpanded
      ? !collapsedGroups.has(group.key)
      : expandedGroups.has(group.key);

    const readyCount = group.records.filter(function (record) {
      return isReadyRecord(record);
    }).length;

    const pendingCount = group.records.length - readyCount;
    const encodedKey = encodeURIComponent(group.key);
    const itemName = group.item_name || group.records[0].item_name || '';

    html +=
      '<tr class="review-group-row"'
      + ' onclick="toggleReviewGroup(\'' + encodedKey + '\')"'
      + '>'

      + '<td class="review-group-toggle">'
      + '<i class="fa fa-'
      + (isExpanded ? 'chevron-down' : 'chevron-right')
      + '" aria-hidden="true"></i>'
      + '</td>'

      + '<td colspan="3">'
      + '<div class="review-group-main">'
      + '<span>Parent Code '
      + '<span class="code-mono code-strong">'
      + (group.parent_code ? esc(group.parent_code) : 'Standalone Items')
      + '</span></span>'
      + '<span>Child Code '
      + '<span class="code-mono code-strong">'
      + displayCode(group.child_code)
      + '</span></span>'
      + '</div>'
      + '<div class="review-group-sub" title="' + esc(itemName) + '">'
      + esc(itemName || 'Unnamed item')
      + '</div>'
      + '</td>'

      + '<td colspan="2">'
      + '<div class="review-group-meta-label">BOM Numbers</div>'
      + '<div class="review-group-bom-list">'
      + (
          group.bom_numbers.length
            ? group.bom_numbers.map(function (bomNo) {
                return '<span class="code-mono review-bom-chip">'
                  + esc(bomNo)
                  + '</span>';
              }).join('')
            : '<span class="review-empty-code">?</span>'
        )
      + '</div>'
      + '</td>'

      + '<td>'
      + '<span class="group-count-pill">' + group.records.length + ' Job Card'
      + (group.records.length !== 1 ? 's' : '') + '</span>'
      + '</td>'

      + '<td class="review-group-status">'
      + (
          pendingCount
            ? '<span class="status-badge st-missing">' + pendingCount + ' pending</span>'
            : '<span class="status-badge st-match">' + readyCount + ' ready</span>'
        )
      + '</td>'

      + '</tr>';

    if (!isExpanded) {
      return;
    }

    group.records.forEach(function (r) {
      serialNo += 1;

      html += renderRecordRow(r, serialNo);
    });
  });

  return html;
}

function renderFlatRows(rows) {
  return rows.map(function (r, index) {
    return renderRecordRow(r, index + 1);
  }).join('');
}

function renderRecordRow(r, serialNo) {
  const isSelected = r.id === activeRecordId;
  const routeCountText = routeMatchText(r);
  const canEdit = !isReadyRecord(r);
  const action = primaryActionForRecord(r);
  const actionClick = action.directImport
    ? 'approveSingle(' + r.id + ')'
    : 'openPanel(' + r.id + ',\'' + action.mode + '\')';

  return '<tr data-review-id="' + r.id + '"'
    + ' class="' + (isSelected ? 'row-selected' : '') + '"'
    + ' onclick="openPanel(' + r.id + ',\'view\')"'
    + '>'
    + '<td class="review-serial">' + serialNo + '</td>'
    + '<td><span class="jc-mono">' + esc(r.jc_no) + '</span></td>'
    + '<td><span class="code-mono">' + displayCode(r.child_code) + '</span></td>'
    + '<td class="review-item-cell" title="' + esc(r.item_name) + '">' + esc(r.item_name || 'Unnamed item') + '</td>'
    + '<td class="review-source-cell" title="' + esc(r.source_file) + '">' + esc(r.source_file || '\u2014') + '</td>'
    + '<td class="review-route-cell">' + esc(routeCountText) + '</td>'
    + '<td>' + badge(r.status, r) + '</td>'
    + '<td><div class="tbl-action-btns">'
    + '<button class="' + action.cls + '" type="button"'
    + ' onclick="event.stopPropagation();' + actionClick + '"'
    + ' aria-label="' + esc(action.label + ' job card ' + r.jc_no) + '">'
    + '<i class="fa fa-' + action.icon + '" aria-hidden="true"></i>&nbsp;' + esc(action.label)
    + '</button>'
    + (
        canEdit && action.mode !== 'edit'
          ? '<button class="btn-tbl-edit" type="button"'
            + ' onclick="event.stopPropagation();openPanel(' + r.id + ',\'edit\')"'
            + ' aria-label="Edit route for job card ' + esc(r.jc_no) + '">'
            + '<i class="fa fa-pencil" aria-hidden="true"></i>&nbsp;Edit'
            + '</button>'
          : ''
      )
    + '</div></td>'
    + '</tr>';
}

function renderPreviouslyApprovedSection(rows) {
  const section = document.getElementById('previously-approved-section');
  const countEl = document.getElementById('previously-approved-count');
  const body = document.getElementById('previously-approved-body');
  const tbody = document.getElementById('previously-approved-body-rows');
  const toggle = document.getElementById('previously-approved-toggle');
  const icon = document.getElementById('previously-approved-icon');

  if (!section || !countEl || !body || !tbody || !toggle || !icon) return;

  section.style.display = rows.length ? '' : 'none';
  countEl.textContent = rows.length + ' ready';
  body.hidden = !previouslyApprovedExpanded;
  toggle.setAttribute('aria-expanded', previouslyApprovedExpanded ? 'true' : 'false');
  icon.className = 'fa fa-' + (previouslyApprovedExpanded ? 'chevron-down' : 'chevron-right');

  tbody.innerHTML = renderFlatRows(rows);
}

function togglePreviouslyApproved() {
  previouslyApprovedExpanded = !previouslyApprovedExpanded;
  applyFilter();
}

// -- Panel ---
function openPanel(reviewId, mode) {
  mode = mode || 'view';
  const record = reviewRecords.find(function (r) { return r.id === reviewId; });
  if (!record) return;

  activeRecordId = reviewId;
  editMode       = (mode === 'edit' && !isReadyRecord(record));
  editedProcs    = record.uploaded.slice();
  addProcVisible = false;

  refreshTableSelection();
  hidePanelToast();

  document.getElementById('panel-overlay').classList.add('open');
  document.getElementById('review-panel').classList.add('open');

  renderPanelHeader(record);
  renderPanelContent(record);
}

function closePanel() {
  activeRecordId = null;
  editMode       = false;
  addProcVisible = false;

  document.getElementById('panel-overlay').classList.remove('open');
  document.getElementById('review-panel').classList.remove('open');
  hidePanelToast();
  refreshTableSelection();
}

function refreshTableSelection() {
  document.querySelectorAll('#review-table-body tr, #ready-import-body-rows tr, #previously-approved-body-rows tr').forEach(function (tr) {
    const id = parseInt(tr.dataset.reviewId, 10);
    tr.classList.toggle('row-selected', id === activeRecordId);
  });
}

function renderPanelHeader(record) {
  document.getElementById('panel-jc-no').innerHTML =
    '<span>' + esc(record.jc_no || '\u2014') + '</span>'
    + '<span class="panel-header-code">' + displayCode(record.child_code) + '</span>'
    + badge(record.status);
  document.getElementById('panel-mode-label').textContent = editMode ? 'Edit route' : 'Review detail';
}

// -- Panel content ---
function renderPanelContent(record) {
  const body   = document.getElementById('panel-body');
  const footer = document.getElementById('panel-footer');
  const isSpecial = record.status === 'NEW_ITEM_REVIEW_REQUIRED'
                 || record.status === 'PROCESS_ROUTE_NOT_FOUND';

  // -- Info grid --
  const msgClass = msgBarClass(record.status);
  let infoHtml =
    '<div class="panel-record-title">'
    + '<div class="panel-record-name">' + esc(record.item_name || 'Unnamed item') + '</div>'
    + '</div>'
    + '<div class="panel-info-grid">'
    + '<div class="panel-info-item"><div class="pi-label">BOM No</div><div class="pi-value mono">' + displayCode(record.bom_no) + '</div></div>'
    + '<div class="panel-info-item"><div class="pi-label">Parent Code</div><div class="pi-value mono">' + displayCode(record.parent_code) + '</div></div>'
    + '<div class="panel-info-item"><div class="pi-label">Child Code</div><div class="pi-value mono">' + displayCode(record.child_code) + '</div></div>'
    + '<div class="panel-info-item"><div class="pi-label">Source file</div><div class="pi-value">' + esc(record.source_file || '\u2014') + '</div></div>'
    + '</div>'
    + '<div class="panel-message-bar ' + msgClass + '">'
    + '<div class="panel-message-title">' + esc(statusLabel(record)) + '</div>'
    + '<div>' + esc(record.message || statusReasonText(record)) + '</div>'
    + '</div>';

  // -- Process area --
  let procHtml = '';

  if (editMode) {
    procHtml = renderEditMode(record);
  } else if (isSpecial) {
    procHtml = renderSpecialStatus(record);
  } else {
    procHtml = renderDiffView(record);
  }

  body.innerHTML = infoHtml + procHtml;

  // -- Footer buttons --
  footer.innerHTML = renderFooter(record, isSpecial);
}

// -- Diff view (MATCH / MISSING / EXTRA / ORDER) ---
function renderDiffView(record) {
  const diffRows = computeDiff(record);
  const status   = record.status;

  let legendHtml = '';
  if (status === 'MISSING_PROCESS')
    legendHtml = '<div class="diff-legend"><span class="status-badge st-missing"><i class="fa fa-exclamation-circle" aria-hidden="true"></i> Red = missing from upload</span></div>';
  else if (status === 'EXTRA_PROCESS')
    legendHtml = '<div class="diff-legend"><span class="status-badge st-extra"><i class="fa fa-plus-circle" aria-hidden="true"></i> Orange = not in master</span></div>';
  else if (status === 'ORDER_MISMATCH')
    legendHtml = '<div class="diff-legend"><span class="status-badge st-order"><i class="fa fa-sort-amount-asc" aria-hidden="true"></i> Purple = out of sequence</span></div>';
  else if (status === 'MATCH')
    legendHtml = '<div class="diff-legend"><span class="status-badge st-match"><i class="fa fa-check-circle" aria-hidden="true"></i> All steps matched</span></div>';
  else if (status === 'REUSED_APPROVAL')
    legendHtml = '<div class="diff-legend"><span class="status-badge st-reused"><i class="fa fa-history" aria-hidden="true"></i> Previously approved route</span></div>';

  const leftSteps  = diffRows.map(function (row, i) { return renderStep(row.left, i); }).join('');
  const rightSteps = diffRows.map(function (row, i) {
    return row.right ? renderStep(row.right, i) : '<div class="proc-step-spacer"></div>';
  }).join('');

  return legendHtml
    + '<div class="diff-columns">'
    + '<div><div class="diff-col-header">Uploaded route</div>' + (leftSteps || emptyRoute()) + '</div>'
    + '<div><div class="diff-col-header">Process master</div>' + (rightSteps || emptyRoute()) + '</div>'
    + '</div>';
}

function computeDiff(record) {
  const up  = record.uploaded;
  const mp  = record.master;
  const st  = record.status;

  if (st === 'MATCH') {
    const len = Math.max(up.length, mp.length);
    return Array.from({ length: len }, function (_, i) {
      const uploadedName = up[i] || null;
      const masterName = mp[i] || null;
      return {
        left: uploadedName ? { name: uploadedName, cls: 'step-match' } : { name: '\u2014 missing \u2014', cls: 'step-ghost' },
        right: masterName ? { name: masterName, cls: 'step-match' } : { name: '\u2014 missing \u2014', cls: 'step-ghost' }
      };
    });
  }

  if (st === 'REUSED_APPROVAL') {
    const len = Math.max(up.length, mp.length);
    return Array.from({ length: len }, function (_, i) {
      const uploadedName = up[i] || null;
      const masterName = mp[i] || null;
      const fallbackName = uploadedName || masterName || '\u2014 missing \u2014';
      return {
        left: { name: uploadedName || fallbackName, cls: uploadedName ? 'step-match' : 'step-ghost' },
        right: { name: masterName || fallbackName, cls: masterName ? 'step-match' : 'step-ghost' }
      };
    });
  }

  if (st === 'MISSING_PROCESS') {
    const availableUploaded = up.map(function (name) {
      return String(name || '').trim().toLowerCase();
    });

    const availableMaster = mp.map(function (name) {
      return String(name || '').trim().toLowerCase();
    });

    const uploadedMatched = up.map(function (processName) {
      const key = String(processName || '').trim().toLowerCase();
      const index = availableMaster.indexOf(key);

      if (index !== -1) {
        availableMaster.splice(index, 1);
        return true;
      }

      return false;
    });

    const masterMatched = mp.map(function (processName) {
      const key = String(processName || '').trim().toLowerCase();
      const index = availableUploaded.indexOf(key);

      if (index !== -1) {
        availableUploaded.splice(index, 1);
        return true;
      }

      return false;
    });

    const rowCount = Math.max(up.length, mp.length);

    return Array.from({ length: rowCount }, function (_, index) {
      const uploadedName = up[index] || null;
      const masterName = mp[index] || null;

      return {
        left: uploadedName
          ? {
              name: uploadedName,
              cls: uploadedMatched[index] ? '' : 'step-extra'
            }
          : {
              name: '\u2014 missing \u2014',
              cls: 'step-ghost'
            },

        right: masterName
          ? {
              name: masterName,
              cls: masterMatched[index] ? '' : 'step-missing'
            }
          : {
              name: '\u2014 missing \u2014',
              cls: 'step-ghost'
            }
      };
    });
  }

  if (st === 'EXTRA_PROCESS') {
    const remainingMaster = mp.map(processKey);
    return up.map(function (p) {
      const key = processKey(p);
      const index = remainingMaster.indexOf(key);
      const inMp = index !== -1;
      if (inMp) remainingMaster.splice(index, 1);
      return {
        left:  { name: p, cls: inMp ? '' : 'step-extra' },
        right: inMp ? { name: p, cls: '' } : { name: '\u2014 missing \u2014', cls: 'step-ghost' },
      };
    });
  }

  if (st === 'ORDER_MISMATCH') {
    const len = Math.max(up.length, mp.length);
    return Array.from({ length: len }, function (_, i) {
      const u = up[i] || null;
      const m = mp[i] || null;
      const mismatch = u !== m;
      return {
        left:  u ? { name: u, cls: mismatch ? 'step-mismatch' : '' } : { name: '\u2014 missing \u2014', cls: 'step-ghost' },
        right: m ? { name: m, cls: mismatch ? 'step-mismatch' : '' } : { name: '\u2014 missing \u2014', cls: 'step-ghost' },
      };
    });
  }

  return up.map(function (p) { return { left: { name: p, cls: '' }, right: null }; });
}

function renderStep(step, index) {
  if (!step) return '';
  return '<div class="proc-step ' + step.cls + '">'
    + '<span class="proc-step-num">' + (index + 1) + '</span>'
    + '<span class="proc-step-name">' + esc(step.name) + '</span>'
    + '</div>';
}

function emptyRoute() {
  return '<div class="proc-step step-ghost"><span class="proc-step-name">No route configured</span></div>';
}

// -- Special status (NEW_ITEM / PROCESS_ROUTE_NOT_FOUND) ---
function renderSpecialStatus(record) {
  const isNew = record.status === 'NEW_ITEM_REVIEW_REQUIRED';
  const cls   = isNew ? 'si-blue' : 'si-grey';
  const icon  = isNew ? 'user-plus' : 'ban';
  const msg   = isNew
    ? 'This child item does not exist in Item Master. Create the Item Master and Process Master before rechecking.'
    : 'This item exists, but no Process Master route is configured. Review the uploaded route, then save it to Process Master for this Child Code.';

  const uploadedSteps = record.uploaded.map(function (p, i) {
    return renderStep({ name: p, cls: '' }, i);
  }).join('') || emptyRoute();

  return '<div class="diff-col-header">Uploaded route</div>'
    + uploadedSteps
    + '<div class="special-info-box ' + cls + '">'
    + '<i class="fa fa-' + icon + ' special-inline-icon" aria-hidden="true"></i>'
    + esc(msg)
    + '</div>'
    + '<div class="special-action-btns">'
    + '<a href="/" class="btn-cancel btn-sm">'
    + '<i class="fa fa-external-link" aria-hidden="true"></i>&nbsp;Item master</a>'
    + '<a href="/page2" class="btn-cancel btn-sm">'
    + '<i class="fa fa-external-link" aria-hidden="true"></i>&nbsp;Process master</a>'
    + '</div>';
}

// -- Edit mode ---
function renderEditMode(record) {
  const stepRows = editedProcs.map(function (p, i) {
    return '<div class="edit-proc-row">'
      + '<div class="proc-step">'
      + '<span class="proc-step-num">' + (i + 1) + '</span>'
      + '<span class="proc-step-name">' + esc(p) + '</span>'
      + '</div>'
      + '<button type="button" class="btn-proc-move" onclick="moveProc(' + i + ',-1)" ' + (i === 0 ? 'disabled' : '') + ' title="Move up" aria-label="Move process up">'
      + '<i class="fa fa-arrow-up" aria-hidden="true"></i></button>'
      + '<button type="button" class="btn-proc-move" onclick="moveProc(' + i + ',1)" ' + (i === editedProcs.length - 1 ? 'disabled' : '') + ' title="Move down" aria-label="Move process down">'
      + '<i class="fa fa-arrow-down" aria-hidden="true"></i></button>'
      + '<button type="button" class="btn-proc-del" onclick="deleteProc(' + i + ')" title="Remove" aria-label="Remove process">'
      + '<i class="fa fa-trash-o" aria-hidden="true"></i></button>'
      + '</div>';
  }).join('');

  const masterSteps = record.master.length
    ? record.master.map(function (p, i) { return renderStep({ name: p, cls: 'step-match' }, i); }).join('')
    : emptyRoute();

  return '<div class="edit-proc-list">'
    + '<div class="edit-proc-header">'
    + '<span>Uploaded route</span>'
    + '<button type="button" class="btn-copy-master" onclick="copyMaster()" title="Replace uploaded route with Process Master route">'
    + '<i class="fa fa-clipboard" aria-hidden="true"></i>&nbsp;Copy master route</button>'
    + '</div>'
    + (stepRows || '<div class="review-muted-empty">No processes added yet.</div>')
    + '<div class="add-proc-wrap">'
    + '<div class="add-proc-input-row' + (addProcVisible ? ' visible' : '') + '" id="add-proc-row">'
    + '<input'
    + ' type="text"'
    + ' id="add-proc-input"'
    + ' class="pm-process-edit-input"'
    + ' list="review-process-options"'
    + ' placeholder="Process name"'
    + ' onkeydown="addProcKeydown(event)"'
    + ' aria-label="Process name to add"'
    + ' autocomplete="off"'
    + ' />'
    + '<datalist id="review-process-options">'
    + reviewProcessNames
      .filter(function (name) {
        const key = String(name || '').trim().toLowerCase();

        return !editedProcs.some(function (existing) {
          return String(existing || '').trim().toLowerCase() === key;
        });
      })
      .map(function (name) {
        return '<option value="' + esc(name) + '"></option>';
      }).join('')
    + '</datalist>'
    + '<button type="button" class="btn-cancel btn-sm btn-icon-only" onclick="confirmAddProc()" title="Add process" aria-label="Add process"><i class="fa fa-check" aria-hidden="true"></i></button>'
    + '<button type="button" class="btn-cancel btn-sm btn-icon-only" onclick="cancelAddProc()" title="Cancel add process" aria-label="Cancel add process"><i class="fa fa-times" aria-hidden="true"></i></button>'
    + '</div>'
    + '<button type="button" class="btn-cancel btn-sm btn-add-process' + (addProcVisible ? ' is-hidden' : '') + '" onclick="showAddProc()" id="show-add-proc-btn">'
    + '<i class="fa fa-plus" aria-hidden="true"></i>&nbsp;Add process</button>'
    + '</div>'
    + '</div>'
    + '<div class="process-master-warning">'
    + '<i class="fa fa-exclamation-triangle" aria-hidden="true"></i>'
    + '<span>This will replace the Process Master route for this Child Code.</span>'
    + '</div>'
    + '<div class="edit-master-route">'
    + '<div class="diff-col-header">Process master route</div>'
    + masterSteps
    + '</div>';
}

// -- Footer buttons ---
function renderFooter(record, isSpecial) {
  if (
    record.status === 'NEW_ITEM_REVIEW_REQUIRED'
    && !record.is_resolved
  ) {
    return '<button class="btn-submit"'
      + ' onclick="createProcessMasterItem(' + record.id + ')"'
      + '>'
      + '<i class="fa fa-plus-circle" aria-hidden="true"></i>'
      + '&nbsp;Import New Item'
      + '</button>'
      + '<button class="btn-cancel" onclick="closePanel()">Close</button>';
  }

  if (isReadyRecord(record)) {
    return '<button class="btn-success" onclick="approveSingle(' + record.id + ')">'
      + '<i class="fa fa-check" aria-hidden="true"></i>&nbsp;Approve &amp; import</button>'
      + '<button class="btn-cancel" onclick="closePanel()">Close</button>';
  }

  if (record.status === 'PROCESS_ROUTE_NOT_FOUND') {
    return '<button class="btn-submit"'
      + ' onclick="saveAndUpdateProcessMaster()"'
      + ' style="flex:1">'
      + '<i class="fa fa-database" aria-hidden="true"></i>'
      + '&nbsp;Save &amp; Update Process Master'
      + '</button>'
      + '<button class="btn-cancel" onclick="closePanel()">Close</button>';
  }

  if (editMode) {
    return '<button class="btn-submit"'
      + ' onclick="saveAndUpdateProcessMaster()"'
      + '>'
      + '<i class="fa fa-database" aria-hidden="true"></i>'
      + '&nbsp;Save &amp; Update Process Master'
      + '</button>'
      + '<button class="btn-cancel" onclick="cancelEdit()">Cancel</button>';
  }

  if (isSpecial) {
    return '<button class="btn-recheck" onclick="recheckRecord(' + record.id + ')">'
      + '<i class="fa fa-refresh" aria-hidden="true"></i>&nbsp;Recheck</button>'
      + '<button class="btn-cancel" onclick="closePanel()">Close</button>';
  }

  return '<button class="btn-primary" onclick="switchToEdit()">'
    + '<i class="fa fa-pencil" aria-hidden="true"></i>&nbsp;Edit uploaded route</button>'
    + '<button class="btn-cancel" onclick="closePanel()">Close</button>';
}

// -- Edit mode actions ---
function switchToEdit() {
  const record = getActive();
  if (!record) return;
  editMode      = true;
  editedProcs   = record.uploaded.slice();
  addProcVisible = false;
  renderPanelHeader(record);
  renderPanelContent(record);
}

function cancelEdit() {
  const record = getActive();
  if (!record) return;
  editMode      = false;
  addProcVisible = false;
  renderPanelHeader(record);
  renderPanelContent(record);
}

function moveProc(idx, dir) {
  const ni = idx + dir;
  if (ni < 0 || ni >= editedProcs.length) return;
  const tmp = editedProcs[idx];
  editedProcs[idx] = editedProcs[ni];
  editedProcs[ni]  = tmp;
  const record = getActive();
  if (record) renderPanelContent(record);
}

function deleteProc(idx) {
  editedProcs.splice(idx, 1);
  const record = getActive();
  if (record) renderPanelContent(record);
}

function copyMaster() {
  const record = getActive();
  if (!record) return;
  editedProcs = record.master.slice();
  renderPanelContent(record);
}


async function loadReviewProcessNames() {
  if (reviewProcessNames.length) return;

  try {
    const response = await fetch('/api/bom/processes');
    const data = await response.json();

    if (!data.success) {
      throw new Error(data.error || 'Could not load process names.');
    }

    reviewProcessNames = (data.processes || [])
      .map(function (row) {
        return String(row.process_name || '').trim();
      })
      .filter(Boolean);

  } catch (error) {
    showToast(
      'Could not load process names: ' + error.message,
      'error'
    );
  }
}

async function showAddProc() {
  await loadReviewProcessNames();

  addProcVisible = true;

  const record = getActive();
  if (record) renderPanelContent(record);

  setTimeout(function () {
    const inp = document.getElementById('add-proc-input');
    if (inp) inp.focus();
  }, 50);
}

function cancelAddProc() {
  addProcVisible = false;
  const record = getActive();
  if (record) renderPanelContent(record);
}

function confirmAddProc() {
  const inp = document.getElementById('add-proc-input');
  if (!inp) return;

  const val = inp.value.trim();

  if (!val) return;

  const duplicateExists = editedProcs.some(function (processName) {
    return String(processName || '').trim().toLowerCase()
      === val.toLowerCase();
  });

  if (duplicateExists) {
    showToast(
      'This process is already present in the route.',
      'warning'
    );

    inp.focus();
    inp.select();
    return;
  }

  editedProcs.push(val);
  addProcVisible = false;

  const record = getActive();
  if (record) renderPanelContent(record);
}

function addProcKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    confirmAddProc();
  }

  if (e.key === 'Escape') {
    e.preventDefault();
    cancelAddProc();
  }
}

// -- API - Save & Recheck ---

// API - Create new item in Process Master
async function createProcessMasterItem(reviewId) {
  const record = reviewRecords.find(function (r) {
    return r.id === reviewId;
  });

  if (!record) return;

  const button = document.querySelector(
    '#panel-footer .btn-submit'
  );

  if (button) {
    button.disabled = true;
    button.innerHTML =
      '<i class="fa fa-spinner fa-spin"></i>&nbsp;Creating...';
  }

  showPanelToast(
    'Creating item and process route in Process Master...',
    'warning'
  );

  try {
    const response = await fetch(
      '/api/job_card/review/create_process_master/' + reviewId,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          item_description: record.item_name
        })
      }
    );

    const data = await response.json();

    if (!data.success) {
      hidePanelToast();
      showToast(
        data.error || 'Failed to create Process Master item.',
        'error'
      );

      renderPanelContent(record);
      return;
    }

    record.status = 'MATCH';
    record.is_resolved = true;
    record.review_decision = 'APPROVED';
    record.master = parseProcs(data.processes);
    record.message = data.message
      || 'New item created in Process Master.';

    showPanelToast(
      'Item added to Process Master. Importing Job Card...',
      'success'
    );

    renderPanelHeader(record);
    renderPanelContent(record);
    renderStatCards();
    applyFilter();
    updateImportButton();

    await doImport([record]);

  } catch (error) {
    hidePanelToast();

    showToast(
      'Network error: ' + error.message,
      'error'
    );

    renderPanelContent(record);
  }
}


// Save reviewed route and update Process Master
async function saveAndUpdateProcessMaster() {
  const record = getActive();

  if (!record) return;

  if (!editedProcs.length) {
    showToast(
      'At least one process is required.',
      'error'
    );
    return;
  }

  const confirmed = window.confirm(
    'This will replace the Process Master route for Child Code '
    + record.child_code
    + '.\n\nContinue?'
  );

  if (!confirmed) return;

  const button = document.querySelector(
    '#panel-footer .btn-submit'
  );

  if (button) {
    button.disabled = true;
    button.innerHTML =
      '<i class="fa fa-spinner fa-spin"></i>'
      + '&nbsp;Updating Process Master...';
  }

  showPanelToast(
    'Updating Process Master for '
      + record.child_code
      + '...',
    'warning'
  );

  try {
    const response = await fetch(
      '/api/job_card/review/update_process_master/'
        + record.id,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          uploaded_processes: editedProcs
        })
      }
    );

    const data = await response.json();

    if (!data.success) {
      hidePanelToast();

      showToast(
        data.error || 'Process Master update failed.',
        'error'
      );

      renderPanelContent(record);
      return;
    }

    record.uploaded = parseProcs(
      data.uploaded_processes
    );

    record.master = parseProcs(
      data.master_processes
    );

    record.status = 'MATCH';
    record.is_resolved = true;
    record.review_decision = 'APPROVED';
    record.message = data.message || (
      'Process Master route updated successfully.'
    );

    editMode = false;
    editedProcs = [];
    addProcVisible = false;

    showPanelToast(
      'Process Master updated - Job Card is ready to import.',
      'success'
    );

    renderPanelHeader(record);
    renderPanelContent(record);
    renderStatCards();
    applyFilter();
    updateImportButton();

  } catch (error) {
    hidePanelToast();

    showToast(
      'Network error: ' + error.message,
      'error'
    );

    renderPanelContent(record);
  }
}

async function saveAndRecheck() {
  const record = getActive();
  if (!record) return;

  const footerBtn = document.querySelector('#panel-footer .btn-submit');
  if (footerBtn) { footerBtn.disabled = true; footerBtn.textContent = 'Saving...'; }

  try {
    // Step 1: update uploaded processes
    const updateRes  = await fetch('/api/job_card/review/update/' + record.id, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uploaded_processes: editedProcs }),
    });
    const updateData = await updateRes.json();

    if (!updateData.success) {
      showToast(updateData.error || 'Failed to save changes.', 'error');
      if (footerBtn) { footerBtn.disabled = false; footerBtn.innerHTML = '<i class="fa fa-refresh" aria-hidden="true"></i>&nbsp;Save &amp; recheck'; }
      return;
    }

    // Step 2: recheck against Process Master
    const recheckRes  = await fetch('/api/job_card/review/recheck/' + record.id, { method: 'POST' });
    const recheckData = await recheckRes.json();

    if (!recheckData.success) {
      showToast(recheckData.error || 'Recheck failed.', 'error');
      if (footerBtn) { footerBtn.disabled = false; footerBtn.innerHTML = '<i class="fa fa-refresh" aria-hidden="true"></i>&nbsp;Save &amp; recheck'; }
      return;
    }

    // Update local state
    record.status      = recheckData.status || recheckData.review_status || record.status;
    record.is_resolved = !!recheckData.is_resolved;
    record.uploaded    = parseProcs(recheckData.uploaded_processes) || editedProcs;
    record.message     = recheckData.message || record.message;

    editMode       = false;
    addProcVisible = false;

    if (isReadyRecord(record)) {
      showPanelToast('Route matched - ready to import.', 'success');
    } else {
      showPanelToast('Recheck complete. Status: ' + (STATUS_CFG[record.status] || { label: record.status }).label, 'warning');
    }

    renderPanelHeader(record);
    renderPanelContent(record);
    renderStatCards();
    applyFilter();
    updateImportButton();

  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
    if (footerBtn) { footerBtn.disabled = false; footerBtn.innerHTML = '<i class="fa fa-refresh" aria-hidden="true"></i>&nbsp;Save &amp; recheck'; }
  }
}

// -- API - Recheck only (for NEW_ITEM / NO_ROUTE after external fix) ---
async function recheckRecord(reviewId) {
  const record = reviewRecords.find(function (r) { return r.id === reviewId; });
  if (!record) return;

  showPanelToast('Rechecking against Process Master...', 'warning');

  try {
    const res  = await fetch('/api/job_card/review/recheck/' + reviewId, { method: 'POST' });
    const data = await res.json();

    if (!data.success) {
      showToast(data.error || 'Recheck failed.', 'error');
      hidePanelToast();
      return;
    }

    record.status      = data.status || data.review_status || record.status;
    record.is_resolved = !!data.is_resolved;
    record.master      = parseProcs(data.master_processes) || record.master;
    record.message     = data.message || record.message;

    if ((record.status === 'MATCH' || record.status === 'REUSED_APPROVAL')) {
      showPanelToast('Route matched - ready to import.', 'success');
    } else {
      hidePanelToast();
      showToast('Status updated: ' + (STATUS_CFG[record.status] || { label: record.status }).label, 'info');
    }

    renderPanelContent(record);
    renderStatCards();
    applyFilter();
    updateImportButton();

  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
    hidePanelToast();
  }
}

// -- Import - single record ---
async function approveSingle(reviewId) {
  const record = reviewRecords.find(function (r) { return r.id === reviewId; });
  if (!record || !isReadyRecord(record)) return;

  await doImport([record]);
}

// -- Import - all ready ---
function openImportModal() {
  const ready   = reviewRecords.filter(function (r) { return isReadyRecord(r) && !r._imported; });
  const pending = reviewRecords.filter(function (r) { return !r._imported && !(isReadyRecord(r)); });

  document.getElementById('import-confirm-msg').textContent =
    'The following ' + ready.length + ' job card' + (ready.length !== 1 ? 's' : '') + ' will be imported:';

  document.getElementById('import-confirm-list').innerHTML = ready.map(function (r) {
    return '<div class="import-list-item">'
      + '<i class="fa fa-check-circle" aria-hidden="true"></i>'
      + '<span class="jc-mono">' + esc(r.jc_no) + '</span>'
      + '<span class="import-list-code">' + esc(r.child_code) + '</span>'
      + '</div>';
  }).join('');

  const warnEl = document.getElementById('import-pending-warning');
  if (pending.length) {
    document.getElementById('import-pending-warning-text').textContent = pending.length + ' ';
    warnEl.style.display = '';
  } else {
    warnEl.style.display = 'none';
  }

  document.getElementById('import-confirm-modal').classList.add('open');
}

function closeImportModal() {
  document.getElementById('import-confirm-modal').classList.remove('open');
}

async function confirmImport() {
  if (importInProgress) return;

  const ready = reviewRecords.filter(function (r) { return isReadyRecord(r) && !r._imported; });
  closeImportModal();
  await doImport(ready);
}

async function doImport(records) {
  if (importInProgress) return;

  if (!records.length) {
    showToast('No records ready to import.', 'error');
    return;
  }

  importInProgress = true;

  const confirmBtn = document.getElementById('import-confirm-btn');
  if (confirmBtn) {
    confirmBtn.disabled = true;
  }

  const btn = document.getElementById('import-all-btn');
  document.getElementById('import-all-label').textContent = 'Importing...';

  // Build rows payload - merge with original preview rows if available
  const rows = records.map(function (r) {
    const original = previewRows.find(function (p) { return p.job_card_no === r.jc_no; }) || {};
    return Object.assign({}, original, {
      job_card_no:           r.jc_no,
      child_code:            r.child_code,
      uploaded_processes:    r.uploaded,
      review_status:         r.status,
      review_import_allowed: true,
    });
  });

  try {
    const res  = await fetch('/api/job_card/upload_confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ review_token: reviewToken, rows: rows }),
    });
    const data = await res.json();

    if (!data.success) {
      const msg = data.error || 'Import failed.';
      showToast(msg, 'error');
      updateImportButton();
      return;
    }

    const inserted = data.inserted || 0;
    const updated  = data.updated  || 0;
    showToast(inserted + ' job card' + (inserted !== 1 ? 's' : '') + ' imported'
      + (updated ? ', ' + updated + ' updated.' : '.'), 'success');

    // Remove successfully imported records from this review page.
    const importedIds = new Set(records.map(function (r) { return r.id; }));

    reviewRecords = reviewRecords.filter(function (r) {
      return !importedIds.has(r.id);
    });

    sessionStorage.removeItem('jms_preview_rows_' + reviewToken);

    renderStatCards();
    applyFilter();
    updateImportButton();
    closePanel();

    if (!reviewRecords.length) {
      showToast('All reviewed Job Cards imported successfully.', 'success');
    }

  } catch (err) {
    showToast('Network error: ' + err.message, 'error');
    updateImportButton();
  } finally {
    importInProgress = false;

    const confirmBtn = document.getElementById('import-confirm-btn');
    if (confirmBtn) {
      confirmBtn.disabled = false;
    }
  }
}

// -- Import button state ---
function updateImportButton() {
  const ready  = reviewRecords.filter(function (r) { return isReadyRecord(r) && !r._imported; });
  const btn    = document.getElementById('import-all-btn');
  const label  = document.getElementById('import-all-label');
  if (!btn || !label) return;

  if (ready.length) {
    label.textContent = 'Import ' + ready.length + ' ready';
    btn.disabled      = false;
  } else {
    label.textContent = 'Import Ready';
    btn.disabled      = true;
  }
}

// -- Helpers ---
function esc(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function displayCode(value) {
  const clean = String(value == null ? '' : value).trim();
  return clean ? esc(clean) : '&mdash;';
}

function processKey(name) {
  return String(name || '').trim().toLowerCase();
}

function routeMatchStats(record) {
  const remainingMaster = record.master.map(processKey);
  let matched = 0;

  record.uploaded.forEach(function (name) {
    const index = remainingMaster.indexOf(processKey(name));
    if (index !== -1) {
      matched += 1;
      remainingMaster.splice(index, 1);
    }
  });

  const missing = Math.max(record.master.length - matched, 0);
  const extra = Math.max(record.uploaded.length - matched, 0);

  return {
    matched: matched,
    missing: missing,
    extra: extra,
    uploaded: record.uploaded.length,
    master: record.master.length
  };
}

function routeMatchText(record) {
  const stats = routeMatchStats(record);

  if (record.status === 'PROCESS_ROUTE_NOT_FOUND') {
    return record.uploaded.length
      ? record.uploaded.length + ' uploaded process' + (record.uploaded.length !== 1 ? 'es' : '')
      : 'No master route';
  }

  if (record.status === 'NEW_ITEM_REVIEW_REQUIRED') {
    return 'New item';
  }

  if (record.status === 'REUSED_APPROVAL') {
    return 'Previously approved';
  }

  if (!stats.master) {
    return 'No master route';
  }

  if (record.status === 'EXTRA_PROCESS' && stats.extra) {
    return stats.matched + ' / ' + stats.master + ' master steps matched - '
      + stats.extra + ' extra';
  }

  if (record.status === 'MISSING_PROCESS' && stats.missing) {
    return stats.matched + ' / ' + stats.master + ' matched - '
      + stats.missing + ' missing';
  }

  return stats.matched + ' / ' + stats.master + ' matched';
}

function statusLabel(record) {
  const cfg = STATUS_CFG[record.status] || { label: record.status };
  const stats = routeMatchStats(record);

  if (record.status === 'MISSING_PROCESS' && stats.missing) {
    return 'Missing ' + stats.missing + ' process' + (stats.missing !== 1 ? 'es' : '');
  }

  if (record.status === 'EXTRA_PROCESS' && stats.extra) {
    return stats.extra + ' extra process' + (stats.extra !== 1 ? 'es' : '');
  }

  return cfg.label;
}

function statusReasonText(record) {
  const map = {
    MATCH: 'This route is resolved and ready to import.',
    REUSED_APPROVAL: 'These routes were approved earlier and do not require another manual review.',
    MISSING_PROCESS: 'The uploaded route is missing one or more Process Master steps.',
    EXTRA_PROCESS: 'The uploaded route contains one or more steps that are not in Process Master.',
    ORDER_MISMATCH: 'The uploaded and Process Master routes contain different step order.',
    NEW_ITEM_REVIEW_REQUIRED: 'Create or approve the new item flow before import.',
    PROCESS_ROUTE_NOT_FOUND: 'Save the uploaded route to Process Master for this Child Code.',
    ITEM_CODE_REQUIRED: 'A Child Code is required before this Job Card can be imported.'
  };

  return map[record.status] || 'Review this record before import.';
}

function primaryActionForRecord(record) {
  if (isReadyRecord(record)) {
    return { label: 'Import', icon: 'cloud-upload', cls: 'btn-tbl-import', mode: 'view', directImport: true };
  }

  if (record.status === 'ORDER_MISMATCH') {
    return { label: 'Reorder', icon: 'sort', cls: 'btn-tbl-edit', mode: 'edit' };
  }

  if (record.status === 'PROCESS_ROUTE_NOT_FOUND') {
    return { label: 'Edit route', icon: 'database', cls: 'btn-tbl-edit', mode: 'edit' };
  }

  if (record.status === 'NEW_ITEM_REVIEW_REQUIRED') {
    return { label: 'New item', icon: 'plus-circle', cls: 'btn-tbl-view', mode: 'view' };
  }

  if (record.status === 'ITEM_CODE_REQUIRED') {
    return { label: 'View issue', icon: 'exclamation-triangle', cls: 'btn-tbl-view', mode: 'view' };
  }

  return { label: 'Edit route', icon: 'pencil', cls: 'btn-tbl-edit', mode: 'edit' };
}

function badge(status, record) {
  const cfg = STATUS_CFG[status] || { label: status, cls: 'st-nocode', icon: 'question-circle' };
  const label = record ? statusLabel(record) : cfg.label;
  return '<span class="status-badge ' + cfg.cls + '">'
    + '<i class="fa fa-' + cfg.icon + '" aria-hidden="true"></i>&nbsp;' + esc(label) + '</span>';
}

function msgBarClass(status) {
  const map = {
    MATCH:                    'msg-success',
    REUSED_APPROVAL:          'msg-success',
    MISSING_PROCESS:          'msg-danger',
    EXTRA_PROCESS:            'msg-warning',
    ORDER_MISMATCH:           'msg-purple',
    NEW_ITEM_REVIEW_REQUIRED: 'msg-blue',
    PROCESS_ROUTE_NOT_FOUND:  '',
    ITEM_CODE_REQUIRED:       'msg-danger',
  };
  return map[status] || '';
}

function getActive() {
  return reviewRecords.find(function (r) { return r.id === activeRecordId; }) || null;
}

function setPageState(state) {
  document.getElementById('loading-state').style.display  = state === 'loading' ? '' : 'none';
  document.getElementById('error-state').style.display    = state === 'error'   ? '' : 'none';
  document.getElementById('main-content').style.display   = state === 'loaded'  ? '' : 'none';
}

function showError(msg) {
  setPageState('error');
  document.getElementById('error-message').textContent = msg;
}

function showPanelToast(msg, type) {
  const bar  = document.getElementById('panel-toast-bar');
  const span = document.getElementById('panel-toast-msg');
  const icon = document.getElementById('panel-toast-icon');
  if (!bar || !span) return;
  span.textContent = msg;
  bar.className    = 'panel-toast-bar show ' + (type === 'success' ? 'toast-success' : 'toast-warning');
  if (icon) icon.className = 'fa fa-' + (type === 'success' ? 'check-circle' : 'exclamation-triangle');
}

function hidePanelToast() {
  const bar = document.getElementById('panel-toast-bar');
  if (bar) bar.className = 'panel-toast-bar';
}
