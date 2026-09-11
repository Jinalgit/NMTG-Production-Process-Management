/* ═══════════════════════════════════════════════════════════
   Process Master  ·  page2.js  (BOM No → Parent → Children)
   ═══════════════════════════════════════════════════════════ */

// ── State ─────────────────────────────────────────────────────────────────────
let pmPage = 1;
let pmTotal = 0;
let pmLoading = false;
let PM_PER = (() => {
  const allowed = [25, 50, 100, 250];

  try {
    const saved = Number(
      localStorage.getItem("pm_rows_per_page") || 50
    );

    return allowed.includes(saved)
      ? saved
      : 50;
  } catch (_) {
    return 50;
  }
})();
let pmSearch = "";
let pmSearchTimer = null;
let pmFilters = {
  bom_level: "top",
  make_buy: "",
  process_status: "",
  raw_material: "",
  item_type: "",
  process_name: "",
  material: "",
  size: "",
  updated: "",
};
let selectedItem = null;
let deleteTarget = null;
let editProcessRows = [];
let knownProcessNames = [];

// ── Init ──────────────────────────────────────────────────────────────────────
/* PM_FILTER_TOGGLE_START */
function togglePmFilters() {
  const toolbar = document.querySelector(".pm-toolbar");
  const button = document.getElementById("pm-filter-toggle");

  if (!toolbar || !button) return;

  const isOpen =
    toolbar.classList.toggle("pm-filters-open");

  button.setAttribute(
    "aria-expanded",
    isOpen ? "true" : "false"
  );
}


/* Close filter panel when clicking outside it */
document.addEventListener("click", function (event) {
  const toolbar = document.querySelector(".pm-toolbar");
  const button = document.getElementById("pm-filter-toggle");

  if (!toolbar || !button) return;

  if (
    toolbar.classList.contains("pm-filters-open") &&
    !toolbar.contains(event.target)
  ) {
    toolbar.classList.remove("pm-filters-open");
    button.setAttribute("aria-expanded", "false");
  }
});
/* PM_FILTER_TOGGLE_END */


document.addEventListener("DOMContentLoaded", () => {
  // loadStats();
  loadKnownProcesses();
  bindProcessMasterFilters();
  loadBom();

  document.getElementById("pm-search").addEventListener("input", () => {
    clearTimeout(pmSearchTimer);
    pmSearchTimer = setTimeout(() => {
      pmSearch = document.getElementById("pm-search").value.trim();
      resetAndLoad();
    }, 350);
  });
});

// ── Stats ─────────────────────────────────────────────────────────────────────
// async function loadStats() {
//   try {
//     const res = await fetch("/api/bom/stats");
//     const d = await res.json();
//     if (d.success) {
//       document.getElementById("pm-stats").textContent =
//         `${(d.total_assemblies || 0).toLocaleString()} BOM Nos · ${(d.total_items || 0).toLocaleString()} items · ${(d.total_processes || 0).toLocaleString()} processes`;
//     }
//   } catch (e) { }
// }

// ── Filters ───────────────────────────────────────────────────────────────────
function toggleFilter(key) {
  if (key === "make") pmFilters.make_buy = pmFilters.make_buy === "A" ? "" : "A";
  else if (key === "buy") pmFilters.make_buy = pmFilters.make_buy === "I" ? "" : "I";
  else if (key === "proc") pmFilters.process_status = pmFilters.process_status === "has_process" ? "" : "has_process";
  else if (key === "noproc") pmFilters.process_status = pmFilters.process_status === "no_process" ? "" : "no_process";
  syncFilterControls();
  resetAndLoad();
}

function buildParams(page) {
  const p = new URLSearchParams({ page, per_page: PM_PER });
  if (pmSearch) p.set("q", pmSearch);
  Object.entries(pmFilters).forEach(([key, value]) => {
    if (value) p.set(key, value);
  });
  return p.toString();
}

function bindProcessMasterFilters() {
  const bindings = [
    ["pm-filter-bom-level", "bom_level"],
    ["pm-filter-make-buy", "make_buy"],
    ["pm-filter-process-status", "process_status"],
    ["pm-filter-raw-material", "raw_material"],
    ["pm-filter-item-type", "item_type"],
    ["pm-filter-process-name", "process_name"],
    ["pm-filter-material", "material"],
    ["pm-filter-size", "size"],
    ["pm-filter-updated", "updated"],
  ];

  bindings.forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (!el) return;

    const eventName = el.tagName === "INPUT" ? "input" : "change";
    let timer = null;

    el.addEventListener(eventName, () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        pmFilters[key] = el.value.trim();
        resetAndLoad();
      }, el.tagName === "INPUT" ? 300 : 0);
    });
  });

  syncFilterControls();
}

function syncFilterControls() {
  const controls = {
    "pm-filter-bom-level": pmFilters.bom_level,
    "pm-filter-make-buy": pmFilters.make_buy,
    "pm-filter-process-status": pmFilters.process_status,
    "pm-filter-raw-material": pmFilters.raw_material,
    "pm-filter-item-type": pmFilters.item_type,
    "pm-filter-process-name": pmFilters.process_name,
    "pm-filter-material": pmFilters.material,
    "pm-filter-size": pmFilters.size,
    "pm-filter-updated": pmFilters.updated,
  };

  Object.entries(controls).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value || "";
  });
}

function clearPmFilters() {
  pmFilters = {
    bom_level: "top",
    make_buy: "",
    process_status: "",
    raw_material: "",
    item_type: "",
    process_name: "",
    material: "",
    size: "",
    updated: "",
  };
  pmSearch = "";
  const search = document.getElementById("pm-search");
  if (search) search.value = "";
  syncFilterControls();
  resetAndLoad();
}

// ── Load BOM tree ─────────────────────────────────────────────────────────────
function resetAndLoad() {
  pmPage = 1;
  pmTotal = 0;
  document.getElementById("pm-tree").innerHTML =
    '<div class="pm-loading" id="pm-loading"><i class="fa fa-spinner fa-spin"></i> Loading...</div>';
  document.getElementById("pm-load-more").style.display = "none";
  loadBom();
}

async function loadBom() {
  if (pmLoading) return;
  pmLoading = true;

  try {
    const res = await fetch(`/api/bom/bom_tree_nested?${buildParams(pmPage)}`);
    const data = await res.json();

    const tree = document.getElementById("pm-tree");
    const loading = document.getElementById("pm-loading");
    const empty = document.getElementById("pm-empty");

    if (loading) loading.style.display = "none";

    if (!data.success || !data.data || !data.data.length) {
      if (pmPage === 1) {
        if (empty) {
          empty.style.display = "block";
          empty.textContent = "No BOM records found.";
        }
      }

      document.getElementById("pm-load-more").style.display = "none";
      pmLoading = false;
      return;
    }

    if (empty) empty.style.display = "none";

    pmTotal = data.total || 0;

    data.data.forEach(bom => {
      tree.appendChild(createBomRow(bom));
    });

    updateLoadMore();

  } catch (e) {
    console.error("BOM nested load failed:", e);

    const loading = document.getElementById("pm-loading");
    if (loading) {
      loading.textContent = "Failed to load. Please refresh.";
    }
  }

  pmLoading = false;
}

async function loadMoreBom() {
  pmPage++;
  await loadBom();
}

function updateLoadMore() {
  const loaded = document.querySelectorAll(".bom-row").length;
  const remaining = pmTotal - loaded;
  const btn = document.getElementById("pm-load-more");
  const span = document.getElementById("pm-remaining");
  if (remaining > 0) {
    btn.style.display = "block";
    if (span) span.textContent = `(${remaining.toLocaleString()} more)`;
  } else {
    btn.style.display = "none";
  }
}
function formatBomQty(value) {
  const qty = parseFloat(value || 1);
  if (Number.isNaN(qty)) return "1";

  return qty % 1 === 0
    ? qty.toFixed(0)
    : qty.toFixed(3).replace(/\.?0+$/, "");
}

function renderAltBadge(item) {
  const isAlt = item && (
    item.is_alternate === 1 ||
    item.is_alternate === true ||
    String(item.is_alternate || "") === "1"
  );

  return isAlt
    ? `<span class="child-badge" style="background:#6d28d9;color:#fff;border-color:#6d28d9;">ALT</span>`
    : "";
}

function renderNestedBuyItem(item) {
  return `
    <div class="child-row nested-buy-row" data-code="${esc(item.child_code)}">
      <span style="color:#94a3b8;font-family:var(--pm-mono);width:22px;">├─</span>
      <span class="child-code">${esc(item.child_code)}</span>
      <span class="child-desc" title="${esc(item.child_desc)}">${esc(item.child_desc || "—")}</span>
      <span class="child-badge badge-I">Buy</span>
      ${renderAltBadge(item)}
      <span class="child-qty">${formatBomQty(item.quantity)} ${esc(item.uom || "Nos.")}</span>
    </div>
  `;
}

function renderNestedProcesses(processes) {
  if (!processes || !processes.length) {
    return `
      <div style="font-size:12px;color:var(--pm-ink-muted);margin:6px 0 8px 44px;">
        No process routing found
      </div>
    `;
  }

  return `
    <div style="margin:8px 0 8px 44px;">
      <div style="font-size:10px;font-weight:800;color:var(--pm-accent);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
        PROCESS ROUTING
      </div>
      <div class="pm-process-list">
        ${processes.map(p => `
          <span class="pm-proc-pill">
            <span class="pm-proc-num">${esc(p.step_no)}</span>
            ${esc(p.process_name)}
          </span>
        `).join("")}
      </div>
    </div>
  `;
}

function renderNestedRawMaterials(makeItem) {
  const raws = makeItem.raw_materials || [];
  const title = makeItem.raw_material_title || (
    raws.length > 1 ? "RAW MATERIAL OPTIONS" :
      raws.length === 1 ? "RAW MATERIAL" :
        "NO RAW MATERIAL FOUND"
  );

  if (!raws.length) {
    return `
      <div style="margin:8px 0 12px 44px;">
        <div style="font-size:10px;font-weight:800;color:var(--pm-red);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
          ${esc(title)}
        </div>
        <div style="font-size:12px;color:var(--pm-ink-muted);">—</div>
      </div>
    `;
  }

  return `
    <div style="margin:8px 0 12px 44px;">
      <div style="font-size:10px;font-weight:800;color:var(--pm-red);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
        ${esc(title)}
      </div>

      ${raws.map(raw => {
    const cutting = raw.cutting_size
      ? `<span class="child-cutting">Cutting Size - ${esc(raw.cutting_size)}</span>`
      : `<span class="child-cutting" style="opacity:.55;">Cutting Size -: blank</span>`;

    return `
          <div class="child-row nested-raw-row" data-code="${esc(raw.child_code)}" style="padding-left:0;">
            <span style="color:#94a3b8;font-family:var(--pm-mono);width:22px;">└─</span>
            <span class="child-code">${esc(raw.child_code)}</span>
            <span class="child-desc" title="${esc(raw.child_desc)}">${esc(raw.child_desc || "—")}</span>
            ${cutting}
            ${renderAltBadge(raw)}
            <span class="child-qty">${formatBomQty(raw.quantity)} ${esc(raw.uom || "Nos.")}</span>
          </div>
        `;
  }).join("")}
    </div>
  `;
}

function renderNestedMakeItem(item) {
  return `
    <div class="nested-make-block">
      <div class="child-row nested-make-row" data-code="${esc(item.child_code)}">
        <span style="color:#94a3b8;font-family:var(--pm-mono);width:22px;">├─</span>
        <span class="bom-no">${esc(item.bom_no || "")}</span>
        <span class="child-code">${esc(item.child_code)}</span>
        <span class="child-desc" title="${esc(item.child_desc)}">${esc(item.child_desc || "—")}</span>
        <span class="child-badge badge-A">Make</span>
        ${renderAltBadge(item)}
        <span class="child-qty">${formatBomQty(item.quantity)} ${esc(item.uom || "Nos.")}</span>
      </div>

      ${renderNestedProcesses(item.processes || [])}
      ${renderNestedRawMaterials(item)}
    </div>
  `;
}

function bindNestedItemClicks(container) {
  container.querySelectorAll("[data-code]").forEach(el => {
    el.addEventListener("click", e => {
      e.stopPropagation();

      const code = el.dataset.code;
      if (!code) return;

      document.querySelectorAll(".child-row.selected").forEach(row => {
        row.classList.remove("selected");
      });

      el.classList.add("selected");
      loadItemDetail(code, {});
    });
  });
}
// ── Create BOM row ────────────────────────────────────────────────────────────
function createBomRow(bom) {
  const wrap = document.createElement("div");
  wrap.className = "pm-tree-block";

  const buyItems = bom.buy_items || [];
  const makeItems = bom.make_items || [];
  const totalParts = buyItems.length + makeItems.length;

  const bomId = `bom-${String(bom.bom_no || bom.parent_code || Math.random()).replace(/[^a-zA-Z0-9_-]/g, "_")}`;

  wrap.innerHTML = `
    <div class="pm-tree-line pm-tree-bom-row" data-toggle-target="${bomId}">
      <button type="button" class="pm-tree-toggle" aria-label="Expand">+</button>
      <span class="pm-tree-bom">${esc(bom.bom_no || "NO BOM")}</span>
      <span class="pm-tree-code pm-tree-clickable" data-item-code="${esc(bom.parent_code)}">${esc(bom.parent_code || "")}</span>
      <span class="pm-tree-desc" title="${esc(bom.parent_desc || "")}">
        ${esc(bom.parent_desc || "—")}${bom.parent_size ? " · " + esc(bom.parent_size) : ""}
      </span>
      <span class="pm-tree-badge pm-tree-badge-assembly">${esc(bom.parent_type || "ASSEMBLY")}</span>
      <button type="button" class="pm-flow-btn" data-flow-bom="${esc(bom.bom_no || "")}" onclick="window.pmOpenManufacturingFlow && window.pmOpenManufacturingFlow(this, event)">Manufacturing Flow</button>
      <span class="pm-tree-count">${totalParts} part${totalParts !== 1 ? "s" : ""}</span>
    </div>

    <div class="pm-tree-children" id="${bomId}">
      ${renderPmTreeGroup("A / MAKE ITEMS", makeItems.map(item => renderPmMakeNode(item)))}
      ${renderPmTreeGroup("I / BUY ITEMS", buyItems.map(item => renderPmBuyNode(item)))}
    </div>
  `;

  bindPmTreeInteractions(wrap);
  return wrap;
}

function renderPmTreeGroup(title, rows) {
  return `
    <div class="pm-tree-group">
      <div class="pm-tree-group-title">${esc(title)}</div>
      ${rows.length ? rows.join("") : `<div class="pm-tree-empty-line">No records</div>`}
    </div>
  `;
}

function renderPmBuyNode(item) {
  const nodeId = `buy-${String(item.child_code || Math.random()).replace(/[^a-zA-Z0-9_-]/g, "_")}`;

  return `
    <div class="pm-tree-line pm-tree-level-1 pm-tree-buy-row" data-toggle-target="${nodeId}">
      <button type="button" class="pm-tree-toggle pm-tree-leaf" aria-label="No children">•</button>
      <span class="pm-tree-bom">${esc(item.bom_no || "")}</span>
      <span class="pm-tree-code pm-tree-clickable" data-item-code="${esc(item.child_code)}">${esc(item.child_code || "")}</span>
      <span class="pm-tree-desc" title="${esc(item.child_desc || "")}">${esc(item.child_desc || "—")}</span>
      <span class="pm-tree-badge pm-tree-badge-buy">BUY</span>
      ${renderAltBadge(item)}
      <span class="pm-tree-qty">${formatBomQty(item.quantity)} ${esc(item.uom || "Nos.")}</span>
      ${item.cutting_size ? `<span class="pm-tree-cutting">Cutting Size - ${esc(item.cutting_size)}</span>` : ""}
    </div>
  `;
}

function renderPmMakeNode(item) {
  const codeSafe = String(item.child_code || Math.random()).replace(/[^a-zA-Z0-9_-]/g, "_");
  const nodeId = `make-${codeSafe}`;
  const procId = `proc-${codeSafe}`;
  const rawId = `raw-${codeSafe}`;
  const processRows = item.processes || [];
  const rawRows = item.raw_materials || [];

  return `
    <div class="pm-tree-node">
      <div class="pm-tree-line pm-tree-level-1 pm-tree-make-row" data-toggle-target="${nodeId}">
        <button type="button" class="pm-tree-toggle" aria-label="Expand">+</button>
        <span class="pm-tree-bom">${esc(item.bom_no || "")}</span>
        <span class="pm-tree-code pm-tree-clickable" data-item-code="${esc(item.child_code)}">${esc(item.child_code || "")}</span>
        <span class="pm-tree-desc" title="${esc(item.child_desc || "")}">${esc(item.child_desc || "—")}</span>
        <span class="pm-tree-badge pm-tree-badge-make">MAKE</span>
        <span class="pm-tree-qty">${formatBomQty(item.quantity)} ${esc(item.uom || "Nos.")}</span>
      </div>

      <div class="pm-tree-children" id="${nodeId}">
        <div class="pm-tree-line pm-tree-level-2 pm-tree-section-row" data-toggle-target="${procId}">
          <button type="button" class="pm-tree-toggle" aria-label="Expand">+</button>
          <span class="pm-tree-section-name">Process Routing</span>
          <span class="pm-tree-count">${processRows.length} process${processRows.length !== 1 ? "es" : ""}</span>
        </div>

        <div class="pm-tree-children" id="${procId}">
          ${processRows.length ? processRows.map(renderPmProcessNode).join("") : `<div class="pm-tree-empty-line pm-tree-level-3">No process routing found</div>`}
        </div>

        <div class="pm-tree-line pm-tree-level-2 pm-tree-section-row" data-toggle-target="${rawId}">
          <button type="button" class="pm-tree-toggle" aria-label="Expand">+</button>
          <span class="pm-tree-section-name">${esc(item.raw_material_title || "Raw Materials")}</span>
          <span class="pm-tree-count">${rawRows.length} item${rawRows.length !== 1 ? "s" : ""}</span>
        </div>

        <div class="pm-tree-children" id="${rawId}">
          ${rawRows.length ? rawRows.map(renderPmRawNode).join("") : `<div class="pm-tree-empty-line pm-tree-level-3">No raw material found</div>`}
        </div>
      </div>
    </div>
  `;
}

function renderPmProcessNode(process) {
  return `
    <div class="pm-tree-line pm-tree-level-3 pm-tree-process-row">
      <button type="button" class="pm-tree-toggle pm-tree-leaf" aria-label="No children">•</button>
      <span class="pm-tree-process-step">P${esc(process.step_no || "")}</span>
      <span class="pm-tree-process-name">${esc(process.process_name || "—")}</span>
    </div>
  `;
}

function renderPmRawNode(raw) {
  // PROCESS_MASTER_RAW_QTY_UOM_HIDE_V1
  const isAlt = raw && (
    raw.is_alternate === 1 ||
    raw.is_alternate === true ||
    String(raw.is_alternate || "") === "1"
  );

  return `
    <div class="pm-tree-line pm-tree-level-3 pm-tree-raw-row">
      <button type="button" class="pm-tree-toggle pm-tree-leaf" aria-label="No children"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#1d4ed8;"></span></button>
      <span class="pm-tree-bom">${esc(raw.bom_no || "")}</span>
      <span class="pm-tree-code pm-tree-clickable" data-item-code="${esc(raw.child_code)}">${esc(raw.child_code || "")}</span>
      <span class="pm-tree-desc" title="${esc(raw.child_desc || "")}">${esc(raw.child_desc || "?")}</span>

      <span style="display:flex;gap:6px;align-items:center;justify-content:flex-end;white-space:nowrap;">
        <span class="pm-tree-badge pm-tree-badge-buy">BUY</span>
        ${isAlt ? `<span style="display:inline-block;padding:2px 8px;border-radius:999px;background:#6d28d9;color:#fff;font-size:10px;font-weight:900;">ALT</span>` : ""}
      </span>

      ${raw.cutting_size ? `<span class="pm-tree-cutting">Cutting Size - ${esc(raw.cutting_size)}</span>` : ""}
    </div>
  `;
}
function bindPmTreeInteractions(container) {
  container.querySelectorAll("[data-toggle-target]").forEach(row => {
    row.addEventListener("click", e => {
      if (e.target.closest(".pm-tree-clickable")) return;

      const targetId = row.dataset.toggleTarget;
      const target = container.querySelector(`#${CSS.escape(targetId)}`);

      if (!target) return;

      const isOpen = target.classList.contains("open");
      target.classList.toggle("open", !isOpen);
      row.classList.toggle("expanded", !isOpen);

      const btn = row.querySelector(".pm-tree-toggle:not(.pm-tree-leaf)");
      if (btn) btn.textContent = isOpen ? "+" : "-";
    });
  });

  
  container.querySelectorAll(".pm-flow-btn[data-flow-bom]").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      const bomNo = btn.dataset.flowBom;
      if (!bomNo) return;
      loadBomProcessFlow(bomNo);
    });
  });

container.querySelectorAll(".pm-tree-clickable[data-item-code]").forEach(el => {
    el.addEventListener("click", e => {
      e.stopPropagation();

      const code = el.dataset.itemCode;
      if (!code) return;

      document.querySelectorAll(".pm-tree-line.selected").forEach(row => {
        row.classList.remove("selected");
      });

      el.closest(".pm-tree-line")?.classList.add("selected");
      loadItemDetail(code, {});
    });
  });
}

// ── Item Detail ───────────────────────────────────────────────────────────────
async function loadItemDetail(itemCode, hint) {
  selectedItem = itemCode;
  const right = document.getElementById("pm-right");
  document.querySelector(".pm-body")?.classList.add("detail-open");

  right.innerHTML = `<div class="pm-detail"><div class="pm-loading"><i class="fa fa-spinner fa-spin"></i> Loading...</div></div>`;

  try {
    const res = await fetch(`/api/bom/item/${encodeURIComponent(itemCode)}`);
    const data = await res.json();

    if (!data.success) {
      right.innerHTML = `<div class="pm-right-empty"><div>Item not found</div></div>`;
      return;
    }

    const item = data.item;
    const procs = item.processes || [];
    const comps = data.children || [];

    const procHtml = procs.length
      ? procs.map(p => `<span class="pm-proc-pill"><span class="pm-proc-num">${p.step_no}</span>${esc(p.process_name)}</span>`).join("")
      : `<span style="font-size:12px;color:var(--pm-ink-muted);">No processes defined</span>`;

    const compsHtml = comps.length
      ? comps.map(c => {
        const qty = parseFloat(c.quantity || 1);
        const qtyStr = qty % 1 === 0 ? qty.toFixed(0) : qty.toFixed(3).replace(/\.?0+$/, "");
        const cutting = c.cutting_size ? `<span class="child-cutting" style="margin-left:4px;">Cutting Size - ${esc(c.cutting_size)}</span>` : "";
        return `<div class="child-row" style="padding-left:8px;cursor:pointer;" onclick="loadItemDetail('${esc(c.child_code)}', {})">
            <span class="child-code">${esc(c.child_code)}</span>
            <span class="child-desc">${esc(c.child_desc || c.item_description || "—")}</span>
            ${cutting}
            <span class="child-badge badge-${c.make_buy || "I"}">${c.make_buy === "A" ? "Make" : "Buy"}</span>
            ${renderAltBadge(c)}
            <span class="child-qty">${qtyStr} ${esc(c.uom || "Nos.")}</span>
          </div>`;
      }).join("")
      : `<div style="font-size:12px;color:var(--pm-ink-muted);padding:8px 0;">No child components</div>`;

    right.innerHTML = `
      <div class="pm-detail">
        <div style="display:flex;justify-content:flex-end;margin-bottom:8px;">
          <button class="pm-btn pm-btn-secondary" onclick="closePmDetailPanel()">
            ✕ Close
          </button>
        </div>
        <div class="pm-detail-header">
          <div class="pm-detail-code">${esc(item.item_code)}</div>
          <div class="pm-detail-desc">${esc(item.item_description || "—")}</div>
          <div class="pm-detail-grid">
            <div class="pm-detail-field"><label>Type</label><span>${esc(item.item_type || "—")}</span></div>
            <div class="pm-detail-field"><label>Make/Buy</label><span>${esc(item.make_default || "—")}</span></div>
            <div class="pm-detail-field"><label>Material</label><span>${esc(item.material || "—")}</span></div>
            <div class="pm-detail-field"><label>Size</label><span>${esc(item.size || "—")}</span></div>
            <div class="pm-detail-field"><label>Part Name</label><span>${esc(item.part_name || "—")}</span></div>
          </div>
        </div>

        <div class="pm-section">
          <div class="pm-section-title">Process Routing (${procs.length})</div>
          <div class="pm-process-list">${procHtml}</div>
        </div>

        <div class="pm-section">
          <div class="pm-section-title" style="display:flex;align-items:center;justify-content:space-between;">
            <span>Components (${comps.length})</span>
            <button class="pm-btn pm-btn-secondary" style="font-size:11px;padding:3px 10px;" onclick="openAddChildModal('${esc(item.item_code)}')">+ Add Child</button>
          </div>
          <div style="margin:0 -16px;">${compsHtml}</div>
        </div>

        <div class="pm-detail-actions">
          <button class="pm-btn pm-btn-primary" onclick="openEditModal('${esc(item.item_code)}')"><i class="fa fa-pencil"></i> Edit Item / Process</button>
          <button class="pm-btn pm-btn-danger" onclick="openDeleteModal('${esc(item.item_code)}', '${esc(item.item_description || "")}')"><i class="fa fa-trash"></i> Delete</button>
        </div>
      </div>`;

  } catch (e) {
    right.innerHTML = `<div class="pm-right-empty"><div>Failed to load item details.</div></div>`;
  }
}

// ── Add Item ──────────────────────────────────────────────────────────────────
function openAddItemModal() {
  ["add-item-code", "add-item-desc", "add-item-size", "add-item-material", "add-item-part"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  document.getElementById("add-item-type").value = "ASSEMBLY";
  document.getElementById("add-item-modal").classList.add("open");
}

function closeAddItemModal() { document.getElementById("add-item-modal").classList.remove("open"); }

async function saveNewItem() {
  const code = document.getElementById("add-item-code").value.trim();
  const desc = document.getElementById("add-item-desc").value.trim();
  if (!code || !desc) { showToast("Item Code and Description are required.", "error"); return; }

  try {
    const res = await fetch("/api/bom/item", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        item_code: code,
        item_description: desc,
        item_type: document.getElementById("add-item-type").value,
        size: document.getElementById("add-item-size").value.trim(),
        material: document.getElementById("add-item-material").value.trim(),
        part_name: document.getElementById("add-item-part").value.trim(),
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Item added successfully.", "success");
      closeAddItemModal();
      // loadStats();
    } else {
      showToast(data.error || "Failed to add item.", "error");
    }
  } catch (e) { showToast("Network error.", "error"); }
}

// ── Edit Item ─────────────────────────────────────────────────────────────────
async function openEditModal(itemCode) {
  try {
    await loadKnownProcesses();
    const res = await fetch(`/api/bom/item/${encodeURIComponent(itemCode)}`);
    const data = await res.json();
    if (!data.success) { showToast("Could not load item.", "error"); return; }
    const item = data.item;
    document.getElementById("edit-item-code").value = item.item_code || "";
    document.getElementById("edit-item-desc").value = item.item_description || "";
    document.getElementById("edit-item-type").value = item.item_type || "PART";
    document.getElementById("edit-item-make").value = item.make_default || "";
    document.getElementById("edit-item-size").value = item.size || "";
    document.getElementById("edit-item-material").value = item.material || "";
    document.getElementById("edit-item-part").value = item.part_name || "";
    document.getElementById("edit-change-remark").value = "";
    editProcessRows = (item.processes || []).map(p => p.process_name || "").filter(Boolean);
    renderEditProcessRows();
    document.getElementById("edit-item-modal").classList.add("open");
  } catch (e) { showToast("Network error.", "error"); }
}

function closeEditItemModal() {
  document.getElementById("edit-item-modal").classList.remove("open");
  editProcessRows = [];
}

async function loadKnownProcesses() {
  if (knownProcessNames.length) {
    renderProcessOptions();
    return;
  }
  try {
    const res = await fetch("/api/bom/processes");
    const data = await res.json();
    if (data.success) {
      knownProcessNames = (data.processes || []).map(p => p.process_name).filter(Boolean);
      renderProcessOptions();
    }
  } catch (e) { }
}

function renderProcessOptions() {
  const list = document.getElementById("pm-process-options");
  if (list) {
    list.innerHTML = knownProcessNames.map(name => `<option value="${esc(name)}"></option>`).join("");
  }

  const select = document.getElementById("pm-filter-process-name");
  if (select) {
    const selected = select.value;
    select.innerHTML = `<option value="">All processes</option>` +
      knownProcessNames.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join("");
    select.value = selected;
  }
}

function syncEditProcessRowsFromInputs() {
  editProcessRows = Array.from(document.querySelectorAll(".pm-process-edit-input"))
    .map(input => input.value.trim());
}

function renderEditProcessRows() {
  const wrap = document.getElementById("edit-process-rows");
  if (!wrap) return;

  if (!editProcessRows.length) {
    wrap.innerHTML = `<div class="pm-process-empty">No process routing defined.</div>`;
    return;
  }

  wrap.innerHTML = editProcessRows.map((name, idx) => `
    <div class="pm-process-edit-row">
      <span class="pm-process-step">${idx + 1}</span>
      <input
        type="text"
        class="pm-process-edit-input"
        list="pm-process-options"
        value="${esc(name)}"
        placeholder="Process name"
        oninput="editProcessRows[${idx}] = this.value"
      />
      <div class="pm-process-row-actions">
        <button type="button" class="pm-icon-btn" title="Move up" onclick="moveEditProcess(${idx}, -1)" ${idx === 0 ? "disabled" : ""}><i class="fa fa-arrow-up"></i></button>
        <button type="button" class="pm-icon-btn" title="Move down" onclick="moveEditProcess(${idx}, 1)" ${idx === editProcessRows.length - 1 ? "disabled" : ""}><i class="fa fa-arrow-down"></i></button>
        <button type="button" class="pm-icon-btn pm-icon-danger" title="Remove" onclick="removeEditProcess(${idx})"><i class="fa fa-times"></i></button>
      </div>
    </div>
  `).join("");
}

function addEditProcess() {
  syncEditProcessRowsFromInputs();
  editProcessRows.push("");
  renderEditProcessRows();
  const inputs = document.querySelectorAll(".pm-process-edit-input");
  inputs[inputs.length - 1]?.focus();
}

function removeEditProcess(index) {
  syncEditProcessRowsFromInputs();
  editProcessRows.splice(index, 1);
  renderEditProcessRows();
}

function moveEditProcess(index, direction) {
  syncEditProcessRowsFromInputs();
  const target = index + direction;
  if (target < 0 || target >= editProcessRows.length) return;
  [editProcessRows[index], editProcessRows[target]] = [editProcessRows[target], editProcessRows[index]];
  renderEditProcessRows();
}

async function updateItem(itemCode) {
  const desc = document.getElementById("edit-item-desc").value.trim();
  const remark = document.getElementById("edit-change-remark").value.trim();
  if (!desc) { showToast("Description is required.", "error"); return; }
  if (!remark) { showToast("Remark / reason for change is required.", "error"); return; }

  const processes = Array.from(document.querySelectorAll(".pm-process-edit-input"))
    .map(input => input.value.trim())
    .filter(Boolean);

  try {
    const res = await fetch(`/api/bom/item/${encodeURIComponent(itemCode)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        item_description: desc,
        item_type: document.getElementById("edit-item-type").value,
        make_default: document.getElementById("edit-item-make").value,
        size: document.getElementById("edit-item-size").value.trim(),
        material: document.getElementById("edit-item-material").value.trim(),
        part_name: document.getElementById("edit-item-part").value.trim(),
        processes,
        change_remark: remark,
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Item updated.", "success");
      closeEditItemModal();
      loadItemDetail(itemCode, {});
      resetAndLoad();
      // loadStats();
    } else {
      showToast(data.error || "Update failed.", "error");
    }
  } catch (e) { showToast("Network error.", "error"); }
}

// ── Delete Item ───────────────────────────────────────────────────────────────
function openDeleteModal(itemCode, itemDesc) {
  deleteTarget = itemCode;
  document.getElementById("delete-item-name").textContent = itemDesc || itemCode;
  document.getElementById("delete-item-modal").classList.add("open");
}

function closeDeleteModal() { document.getElementById("delete-item-modal").classList.remove("open"); deleteTarget = null; }

async function confirmDeleteItem() {
  if (!deleteTarget) return;
  try {
    const res = await fetch(`/api/bom/item/${encodeURIComponent(deleteTarget)}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      showToast("Item deleted.", "success");
      closeDeleteModal();
      document.getElementById("pm-right").innerHTML = `<div class="pm-right-empty"><div>Item deleted. Select another item.</div></div>`;
      resetAndLoad();
      // loadStats();
    } else {
      showToast(data.error || "Delete failed.", "error");
    }
  } catch (e) { showToast("Network error.", "error"); }
}

// ── Add Child (placeholder) ───────────────────────────────────────────────────
function openAddChildModal(parentCode) {
  showToast("Add Child feature coming soon.", "error");
}

// ── Export ────────────────────────────────────────────────────────────────────
async function exportBomExcel() {
  showToast("Preparing export...", "success");
  try {
    const params = new URLSearchParams(buildParams(1));
    params.set("page", "1");
    params.set("per_page", "999999");

    const res = await fetch(`/api/bom/bom_tree?${params.toString()}`);
    const data = await res.json();
    if (!data.success) { showToast("Export failed.", "error"); return; }

    const rows = [["BOM No", "Parent Code", "Parent Description", "Child Code", "Child Description", "Make/Buy", "Quantity", "UOM", "Cutting Size -"]];
    data.data.forEach(bom => {
      bom.children.forEach(ch => {
        rows.push([bom.bom_no, bom.parent_code, bom.parent_desc, ch.child_code, ch.child_desc, ch.make_buy, ch.is_alternate ? "ALT" : "", ch.quantity, ch.uom, ch.cutting_size || ""]);
      });
    });

    const ws = XLSX.utils.aoa_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "BOM");
    XLSX.writeFile(wb, "BOM_Export.xlsx");
    showToast(`Exported ${rows.length - 1} rows.`, "success");
  } catch (e) { showToast("Export failed: " + e.message, "error"); }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(str) {
  if (str == null) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function closePmDetailPanel() {
  document.querySelector(".pm-body")?.classList.remove("detail-open");
  document.getElementById("pm-right").innerHTML = `
    <div class="pm-right-empty">
      <div style="text-align:center">
        <div style="font-size:40px;margin-bottom:12px">🔩</div>
        <div style="font-weight:600;color:var(--pm-ink);margin-bottom:4px">
          Select an item
        </div>
        <div style="font-size:12px">
          Click any item in the BOM tree to view details
        </div>
      </div>
    </div>
  `;
}
function onPmSearch() { } // handled by event listener

/* PM_TREE_SCROLL_FIX_START */
function fixPmTreeScroll() {
  const tree = document.getElementById("pm-tree");
  if (!tree) return;

  const loadMore = document.getElementById("pm-load-more");
  const rect = tree.getBoundingClientRect();

  const loadMoreHeight =
    loadMore && loadMore.style.display !== "none"
      ? loadMore.offsetHeight + 16
      : 20;

  const availableHeight = Math.max(
    260,
    window.innerHeight - rect.top - loadMoreHeight - 12
  );

  tree.style.height = availableHeight + "px";
  tree.style.maxHeight = availableHeight + "px";
  tree.style.overflowY = "auto";
  tree.style.overflowX = "auto";
  tree.style.minHeight = "0";
}

window.addEventListener("resize", () => {
  setTimeout(fixPmTreeScroll, 50);
});

document.addEventListener("DOMContentLoaded", () => {
  setTimeout(fixPmTreeScroll, 300);
});

if (typeof loadBom === "function" && !window.__pmTreeScrollLoadBomWrapped) {
  window.__pmTreeScrollLoadBomWrapped = true;
  const originalLoadBom = loadBom;

  loadBom = async function () {
    const result = await originalLoadBom.apply(this, arguments);
    setTimeout(fixPmTreeScroll, 100);
    return result;
  };
}

if (typeof loadMoreBom === "function" && !window.__pmTreeScrollLoadMoreWrapped) {
  window.__pmTreeScrollLoadMoreWrapped = true;
  const originalLoadMoreBom = loadMoreBom;

  loadMoreBom = async function () {
    const result = await originalLoadMoreBom.apply(this, arguments);
    setTimeout(fixPmTreeScroll, 100);
    return result;
  };
}

document.addEventListener("click", function (event) {
  if (
    event.target.closest(".pm-tree-toggle") ||
    event.target.closest("[data-toggle-target]")
  ) {
    setTimeout(fixPmTreeScroll, 80);
  }
});
/* PM_TREE_SCROLL_FIX_END */

async function loadBomProcessFlow(bomNo) {
  const panel = document.getElementById("pm-right") || document.querySelector(".pm-right");

  if (panel) {
    panel.style.display = "block";
    panel.style.visibility = "visible";
    panel.classList.add("open", "active", "show");
  }

  if (!panel) {
    alert("Right panel not found.");
    return;
  }

  panel.innerHTML = `
    <div class="pm-detail-card">
      <div class="pm-detail-title">Manufacturing Process Flow</div>
      <div class="pm-detail-muted">Loading flow for ${esc(bomNo)}...</div>
    </div>
  `;

  try {
    const res = await fetch(`/api/bom/process_flow/${encodeURIComponent(bomNo)}`);
    const data = await res.json();

    if (!data.success) {
      panel.innerHTML = `
        <div class="pm-detail-card">
          <div class="pm-detail-title">Manufacturing Process Flow</div>
          <div class="pm-error">${esc(data.error || "Unable to load process flow.")}</div>
        </div>
      `;
      return;
    }

    const rows = data.process_flow || [];

    if (!rows.length) {
      panel.innerHTML = `
        <div class="pm-detail-card">
          <div class="pm-detail-title">Manufacturing Process Flow</div>
          <div class="pm-detail-muted">No manufacturing process flow found for ${esc(bomNo)}.</div>
        </div>
      `;
      return;
    }

    const childRows = rows.filter(r => r.item_level_type === "CHILDEST - C ITEM");
    const upperRows = rows.filter(r => r.item_level_type !== "CHILDEST - C ITEM");

    panel.innerHTML = `
      <div class="pm-flow-panel">
        <div class="pm-flow-head">
          <div>
            <div class="pm-flow-title">Manufacturing Process Flow</div>
            <div class="pm-flow-subtitle">BOM No: <b>${esc(data.bom_no || bomNo)}</b> · ${rows.length} process steps</div>
          </div>
          <div class="pm-flow-rule">Bottom-up Flow</div>
        </div>

        <div class="pm-flow-note">
          <b>Rule:</b> Deepest <b>- C</b> item processes complete first, then upper level MAKE item processes start. After top level completes, assembly/store is allowed.
        </div>

        <div class="pm-flow-section">
          <div class="pm-flow-section-title">1. Childest - C Item Processes</div>
          ${renderBomFlowRows(childRows)}
        </div>

        <div class="pm-flow-section">
          <div class="pm-flow-section-title">2. Upper Level MAKE Item Processes</div>
          ${renderBomFlowRows(upperRows)}
        </div>

        <div class="pm-flow-store">
          <div class="pm-flow-store-icon">✓</div>
          <div>
            <b>Final:</b> After all above processes complete, BOM can be moved to <b>Assembly / Store</b>.
          </div>
        </div>
      </div>
    `;

  } catch (err) {
    panel.innerHTML = `
      <div class="pm-detail-card">
        <div class="pm-detail-title">Manufacturing Process Flow</div>
        <div class="pm-error">${esc(err.message || err)}</div>
      </div>
    `;
  }
}

function renderBomFlowRows(rows) {
  if (!rows.length) {
    return `<div class="pm-flow-empty">No process found</div>`;
  }

  let lastItemCode = "";

  return rows.map(row => {
    const showItem = row.item_code !== lastItemCode;
    lastItemCode = row.item_code;

    return `
      <div class="pm-flow-step">
        <div class="pm-flow-seq">${esc(row.process_sequence)}</div>
        <div class="pm-flow-body">
          ${showItem ? `
            <div class="pm-flow-item">
              <span class="pm-flow-code">${esc(row.item_code)}</span>
              <span class="pm-flow-item-desc">${esc(row.item_description)}</span>
            </div>
            <div class="pm-flow-path">${esc(row.path_text || "")}</div>
          ` : ""}
          <div class="pm-flow-process">
            <span class="pm-flow-stepno">P${esc(row.step_no)}</span>
            <span>${esc(row.process_name)}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

/* PM_FLOW_CLICK_FIX_START */
document.addEventListener("click", function (event) {
  const btn = event.target.closest(".pm-flow-btn[data-flow-bom]");
  if (!btn) return;

  event.preventDefault();
  event.stopPropagation();

  const bomNo = btn.dataset.flowBom;
  if (!bomNo) {
    alert("BOM No not found on this button.");
    return;
  }

  if (typeof loadBomProcessFlow !== "function") {
    alert("loadBomProcessFlow function not found in page2.js");
    return;
  }

  loadBomProcessFlow(bomNo);
});
/* PM_FLOW_CLICK_FIX_END */

/* PM_FLOW_FORCE_CLICK_START */
window.pmOpenManufacturingFlow = function (btn, event) {
  if (event) {
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
  }

  const bomNo = btn?.dataset?.flowBom || btn?.getAttribute("data-flow-bom") || "";

  console.log("Manufacturing Flow button clicked:", bomNo);

  if (!bomNo) {
    alert("BOM No missing on Manufacturing Flow button.");
    return false;
  }

  if (typeof loadBomProcessFlow !== "function") {
    alert("loadBomProcessFlow function not found. Please restart Flask and hard refresh.");
    return false;
  }

  loadBomProcessFlow(bomNo);
  return false;
};

document.addEventListener("click", function (event) {
  const btn = event.target.closest(".pm-flow-btn[data-flow-bom]");
  if (!btn) return;

  window.pmOpenManufacturingFlow(btn, event);
}, true);
/* PM_FLOW_FORCE_CLICK_END */

/* PM_FLOW_DRAWER_FIX_START */
function pmSafeText(value) {
  if (typeof esc === "function") return esc(value);
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pmEnsureFlowDrawer() {
  let drawer = document.getElementById("pm-flow-drawer");

  if (!drawer) {
    drawer = document.createElement("div");
    drawer.id = "pm-flow-drawer";
    drawer.innerHTML = `
      <div class="pm-flow-drawer-backdrop" onclick="pmCloseFlowDrawer()"></div>
      <div class="pm-flow-drawer-panel">
        <div class="pm-flow-drawer-content" id="pm-flow-drawer-content"></div>
      </div>
    `;
    document.body.appendChild(drawer);
  }

  return drawer;
}

function pmCloseFlowDrawer() {
  const drawer = document.getElementById("pm-flow-drawer");
  if (drawer) drawer.classList.remove("open");
}

function pmRenderFlowRowsDrawer(rows) {
  if (!rows || !rows.length) {
    return `<div class="pm-flow-empty">No process found</div>`;
  }

  let lastItemCode = "";

  return rows.map(row => {
    const showItem = row.item_code !== lastItemCode;
    lastItemCode = row.item_code;

    return `
      <div class="pm-flow-step">
        <div class="pm-flow-seq">${pmSafeText(row.process_sequence)}</div>
        <div class="pm-flow-body">
          ${showItem ? `
            <div class="pm-flow-item">
              <span class="pm-flow-code">${pmSafeText(row.item_code)}</span>
              <span class="pm-flow-item-desc">${pmSafeText(row.item_description)}</span>
            </div>
            <div class="pm-flow-path">${pmSafeText(row.path_text || "")}</div>
          ` : ""}
          <div class="pm-flow-process">
            <span class="pm-flow-stepno">P${pmSafeText(row.step_no)}</span>
            <span>${pmSafeText(row.process_name)}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

async function pmOpenFlowDrawer(bomNo) {
  const drawer = pmEnsureFlowDrawer();
  const content = document.getElementById("pm-flow-drawer-content");

  drawer.classList.add("open");

  content.innerHTML = `
    <div class="pm-flow-drawer-top">
      <div>
        <div class="pm-flow-title">Manufacturing Process Flow</div>
        <div class="pm-flow-subtitle">Loading BOM No: <b>${pmSafeText(bomNo)}</b></div>
      </div>
      <button type="button" class="pm-flow-close-btn" onclick="pmCloseFlowDrawer()">×</button>
    </div>
    <div class="pm-flow-loading">Loading...</div>
  `;

  try {
    const res = await fetch(`/api/bom/process_flow/${encodeURIComponent(bomNo)}`);
    const data = await res.json();

    if (!data.success) {
      content.innerHTML = `
        <div class="pm-flow-drawer-top">
          <div>
            <div class="pm-flow-title">Manufacturing Process Flow</div>
            <div class="pm-flow-subtitle">BOM No: <b>${pmSafeText(bomNo)}</b></div>
          </div>
          <button type="button" class="pm-flow-close-btn" onclick="pmCloseFlowDrawer()">×</button>
        </div>
        <div class="pm-error">${pmSafeText(data.error || "Unable to load process flow.")}</div>
      `;
      return;
    }

    const rows = data.process_flow || [];
    const childRows = rows.filter(r => r.item_level_type === "CHILDEST - C ITEM");
    const upperRows = rows.filter(r => r.item_level_type !== "CHILDEST - C ITEM");

    content.innerHTML = `
      <div class="pm-flow-drawer-top">
        <div>
          <div class="pm-flow-title">Manufacturing Process Flow</div>
          <div class="pm-flow-subtitle">BOM No: <b>${pmSafeText(data.bom_no || bomNo)}</b> · ${rows.length} process steps</div>
        </div>
        <button type="button" class="pm-flow-close-btn" onclick="pmCloseFlowDrawer()">×</button>
      </div>

      <div class="pm-flow-rule-big">Bottom-up Manufacturing Flow</div>

      <div class="pm-flow-note">
        <b>Rule:</b> Deepest <b>- C</b> item processes complete first, then upper level MAKE item processes start. After top level completes, Assembly / Store is allowed.
      </div>

      <div class="pm-flow-section">
        <div class="pm-flow-section-title">1. Childest - C Item Processes</div>
        ${pmRenderFlowRowsDrawer(childRows)}
      </div>

      <div class="pm-flow-section">
        <div class="pm-flow-section-title">2. Upper Level MAKE Item Processes</div>
        ${pmRenderFlowRowsDrawer(upperRows)}
      </div>

      <div class="pm-flow-store">
        <div class="pm-flow-store-icon">✓</div>
        <div>
          <b>Final:</b> After all above processes complete, BOM can be moved to <b>Assembly / Store</b>.
        </div>
      </div>
    `;

  } catch (err) {
    content.innerHTML = `
      <div class="pm-flow-drawer-top">
        <div>
          <div class="pm-flow-title">Manufacturing Process Flow</div>
          <div class="pm-flow-subtitle">BOM No: <b>${pmSafeText(bomNo)}</b></div>
        </div>
        <button type="button" class="pm-flow-close-btn" onclick="pmCloseFlowDrawer()">×</button>
      </div>
      <div class="pm-error">${pmSafeText(err.message || err)}</div>
    `;
  }
}

/* Override old hidden-panel function */
window.loadBomProcessFlow = pmOpenFlowDrawer;
/* PM_FLOW_DRAWER_FIX_END */
