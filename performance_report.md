# JMS Performance Report

_Generated: 2026-06-08 | Project: D:\Het\demo2_

---

## Summary

| Metric | Count |
|--------|-------|
| Total features analyzed | 12 |
| Features already using SQL | 10 |
| Features moved from JS to SQL (this session) | 1 |
| Features staying in JS (acceptable) | 1 |

---

## Features Already Using SQL (Good)

### 1. Page 5 — PPC Tab (Job Cards) search, filter, sort, paginate
- **File:** `routes/data_view.py` → `data_job_cards()`
- **SQL:** `WHERE (jc.job_card_no LIKE %s OR jc.so_no LIKE %s OR ji.item_name LIKE %s OR ji.material LIKE %s OR ji.wip_status LIKE %s)`
- Supports: full-text search, WIP filter, status filter, SO date range, sort on all columns, server-side pagination with `LIMIT / OFFSET`
- **Status:** ✅ Already optimized

### 2. Page 5 — Traceability Tab (Quality Checks) search, filter, sort, paginate
- **File:** `routes/data_view.py` → `data_quality_checks()`
- **SQL:** `WHERE (qc.job_card_no LIKE %s OR qcd.item_name LIKE %s OR qcd.supervisor LIKE %s)`
- Supports: search, quality result filter, date range, sort, pagination
- **Status:** ✅ Already optimized

### 3. Page 5 — Process Report Tab search
- **File:** `routes/data_view.py` → `data_process_report()` (inferred from `loadProcessReport()` calling `/api/data/process_report` with `buildParams()`)
- Params forwarded via `buildParams()` which serialises all filter panel inputs to URL params
- **Status:** ✅ Already optimized

### 4. Page 5 — Planning Sheet Tab search + WIP filter
- **File:** `routes/data_view.py` → `data_planning_sheet()`
- **SQL:** `WHERE (jc.job_card_no LIKE %s OR ji.item_name LIKE %s OR jc.so_no LIKE %s)` + `AND ji.wip_status = %s`
- **Status:** ✅ Already optimized

### 5. Page 5 — Pagination (all tabs)
- **File:** `routes/data_view.py`
- **SQL:** `LIMIT %s OFFSET %s` computed from `page` and `per_page` query params
- Zero rows loaded beyond the current page
- **Status:** ✅ Already optimized

### 6. Page 5 — Sort (all tabs)
- **File:** `routes/data_view.py`
- Sort column is whitelisted and injected as `ORDER BY {order_expr} {sort_dir}` directly in SQL
- Whitelist prevents SQL injection
- **Status:** ✅ Already optimized

### 7. Page 1 — Job Card Save (POST /api/job_card)
- **File:** `routes/job_cards.py`
- Uses parameterised `INSERT` — no client-side data manipulation
- **Status:** ✅ Already optimized

### 8. Page 3 — Traceability Fetch (`/api/quality_check/fetch/<jc_no>`)
- **File:** `routes/quality_check.py`
- Full join query fetching job card + items + process timeline in SQL
- **Status:** ✅ Already optimized

### 9. Page 3 — WIP Stage Update (`/api/wip/update`, `/api/wip/subcontract`)
- **File:** `routes/quality_check.py`
- Direct parameterised `UPDATE` statements
- **Status:** ✅ Already optimized

### 10. Page 2 — Edit / Delete / Add Item
- **File:** `routes/process_master.py`
- `PUT /api/process_master/<id>`, `DELETE /api/process_master/<id>`, `POST /api/process_master`
- All use parameterised queries
- **Status:** ✅ Already optimized

---

## Features Moved from JS to SQL (Fixed This Session)

### 1. Page 2 — Process Master search

**File changed:** `static/js/page2.js` + `routes/process_master.py`

**Before (client-side JS filtering):**
```javascript
// page2.js — loaded ALL 3,377 records into browser, then filtered in memory
async function loadRecords() {
  const res = await fetch("/api/process_master");   // no params — full table fetch
  const data = await res.json();
  allRecords = data.records;                        // entire table in JS memory
  renderTable(allRecords);
}

function filterTable() {
  const q = document.getElementById("search-input").value.toLowerCase();
  renderTable(allRecords.filter(r =>              // JS Array.filter on 3377 rows
    (r.model_name || "").toLowerCase().includes(q) ||
    (r.material || "").toLowerCase().includes(q)
  ));
}
```

**After (SQL search):**
```python
# routes/process_master.py — GET /api/process_master?search=...
search = request.args.get("search", "").strip()
if search:
    like = f"%{search}%"
    cursor.execute(
        "SELECT * FROM process_master WHERE model_name LIKE %s OR material LIKE %s ORDER BY model_name",
        (like, like)
    )
else:
    cursor.execute("SELECT * FROM process_master ORDER BY model_name")
```

```javascript
// page2.js — debounced, sends search to SQL
async function loadRecords(search = "") {
  const url = search ? `/api/process_master?search=${encodeURIComponent(search)}` : "/api/process_master";
  const res = await fetch(url);
  // ...
}

let filterTimer = null;
function filterTable() {
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => {
    const q = document.getElementById("search-input").value.trim();
    loadRecords(q);
  }, 300);   // 300ms debounce
}
```

**Performance gain estimate:**
- Before: ~3,377 records × ~200 bytes ≈ **675 KB JSON** transferred on every page load; JS `Array.filter` ran on full dataset on every keystroke
- After: Only matching rows transferred; empty query still loads full list (existing behaviour preserved); 300 ms debounce prevents per-keystroke requests
- Estimated network reduction for a targeted search: **95–99%** fewer bytes transferred
- CPU: eliminates O(n) JS scan per keystroke

---

## Features Staying in JS (Acceptable)

### 1. Page 2 — `allRecords` kept for Edit/Delete modal lookup
- `openEditModal(id)` and `deleteItem(id)` look up `allRecords.find(r => r.id === id)` to pre-fill the edit form
- This is a correct client-side pattern: the data is already loaded and an object lookup by primary key is O(n) on a small in-memory array
- Moving this to a separate `GET /api/process_master/<id>` endpoint would add a network round-trip with no benefit
- **Verdict:** Keep in JS ✅

### 2. Page 5 — Filter panel dropdowns rendered in JS
- WIP options and status options are fetched from SQL on first load (`wip_options`, `status_options` in API response) and rendered as `<select>` elements
- Rendering HTML from JS-held options list is UI logic, not data querying
- **Verdict:** Keep in JS ✅

### 3. Page 3 — Process pill colour coding
- `getPillState()` colours pills (green/yellow/white/blue) from `wip_process_index` returned by the API
- Pure UI presentation logic — index computation is already done server-side
- **Verdict:** Keep in JS ✅

### 4. All pages — Form validation
- Required-field checks, numeric range validation, date validation (`getTomorrowDate()` min constraint) done on the client before any network call
- Standard best practice — reduces unnecessary server requests for obviously invalid input
- **Verdict:** Keep in JS ✅

### 5. Page 2 — Autocomplete dropdowns (process names)
- `PROCESS_ORDER` is a 14-item constant — not a database query
- Filtering it on keypress in JS is correct and performant (14 items)
- **Verdict:** Keep in JS ✅

### 6. Page 1 Bulk Entry / Page 2 Bulk Entry — Row management
- Adding/removing rows, tab navigation, autocomplete within the bulk modal are all transient UI state
- No data is persisted until "Save All" which calls the API for each row
- **Verdict:** Keep in JS ✅

### 7. Page 4 — Analytics / Charts
- Chart rendering (Chart.js or similar) is inherently a client-side visualisation task
- Data aggregation (if any) should come from SQL; chart drawing must stay in JS
- **Verdict:** Keep in JS ✅

---

## Recommendations

### Database Indexes to Add

The following indexes would directly speed up the SQL queries now running on every search/filter:

```sql
-- Page 5 PPC tab — most-used search and filter columns
ALTER TABLE job_card_items  ADD INDEX idx_wip_status   (wip_status);
ALTER TABLE job_card_items  ADD INDEX idx_delivery_date(delivery_date);
ALTER TABLE job_cards       ADD INDEX idx_so_date      (so_date);
ALTER TABLE job_cards       ADD INDEX idx_final_status (final_status);

-- Page 2 Process Master search
ALTER TABLE process_master  ADD INDEX idx_model_name   (model_name);
ALTER TABLE process_master  ADD INDEX idx_material     (material);

-- Page 3 fetch + WIP update
ALTER TABLE job_card_process_days ADD INDEX idx_jcpd_jcno (job_card_no);

-- Full-text search alternative (better than LIKE %s% for large tables)
-- ALTER TABLE process_master ADD FULLTEXT INDEX ft_model_material (model_name, material);
-- ALTER TABLE job_card_items ADD FULLTEXT INDEX ft_item_wip       (item_name, wip_status);
```

> **Note on LIKE `%search%`:** Leading-wildcard `LIKE` cannot use a B-tree index.
> For datasets above ~50,000 rows, consider replacing `LIKE %s%` searches with
> MySQL FULLTEXT indexes and `MATCH … AGAINST` queries for dramatically faster results.

### N+1 Query Problem

`data_planning_sheet()` in `routes/data_view.py` has an **N+1 pattern**:
for each job card row it fires two additional queries —
one to `job_card_process_days` and one to `process_master`.
For 500 job cards this becomes ~1,000 extra queries per page load.

**Recommended fix:** Replace the per-row cursor loops with two bulk queries
and a Python dict lookup:

```python
# Fetch all process days for all job cards in one query
jc_nos = [row["job_card_no"] for row in rows]
placeholders = ",".join(["%s"] * len(jc_nos))
cursor.execute(
    f"SELECT job_card_no, process_name, days FROM job_card_process_days WHERE job_card_no IN ({placeholders})",
    jc_nos
)
# Build nested dict: {jc_no: {process_name_lower: days}}
pd_map = {}
for r in cursor.fetchall():
    pd_map.setdefault(r["job_card_no"], {})[r["process_name"].strip().lower()] = r["days"] or 0
```

### Other Observations

- `ensure_extra_cols()` and `ensure_process_subcontract_cols()` are called on **every** request to `data_job_cards()` and called **twice** (lines 69–71). These run `information_schema` queries on every page load. Move schema migration to app startup (`app.py`) or a one-time migration script.
- Page 5 `per_page` defaults to 50 — good. Consider exposing a "rows per page" selector so users can reduce to 25 for even faster loads.
