"""
OEE Module State Audit
======================

Compares what we designed / delivered in the earlier chat against what
actually exists NOW in your database and code files. Reports:
    OK        — matches expected state
    MISSING   — was expected, not found
    EXTRA     — found, was not part of what we shipped from Claude side
    CHANGED   — signature different from what we shipped
    WARN      — potential issue worth checking

Fully read-only. No writes. Paste this whole block into your Python
shell from D:\\Het\\demo2.
"""

import os
import re
import sys

PROJECT_DIR = r"D:\Het\demo2"
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)

# ---- load .env ----
if os.path.exists(".env"):
    with open(".env") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from db import get_connection


findings = []   # (level, area, message)

def rec(level, area, msg):
    findings.append((level, area, msg))


# ===========================================================
# 1. DATABASE SCHEMA
# ===========================================================

conn = get_connection()
cur  = conn.cursor(dictionary=True)


def table_exists(t):
    cur.execute(
        "SELECT COUNT(*) AS c FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
        (t,),
    )
    return (cur.fetchone() or {}).get("c", 0) > 0


def columns_of(t):
    cur.execute(f"DESCRIBE `{t}`")
    return {r["Field"]: r for r in cur.fetchall()}


def row_count(t):
    try:
        cur.execute(f"SELECT COUNT(*) AS c FROM `{t}`")
        return int((cur.fetchone() or {}).get("c") or 0)
    except Exception:
        return -1


# ---- What Claude shipped: expected schema ----

EXPECTED_TABLES = {
    "oee_entries": {
        # columns Claude added in the migration
        "operator_master_id":     "int",
        "operator_employee_no":   "varchar",
        "formula_profile":        "varchar",
    },
    "oee_entry_losses": {
        "remarks":                "varchar",
    },
    # These were pre-existing but we depend on them
    "oee_machine_sessions":     {},
    "oee_machine_runs":         {},
    "oee_machine_loss_events":  {},
    "oee_machines":             {},
    "oee_operator_master":      {},
    "oee_loss_types":           {},
}

# New feature you mentioned (Tool Room / Development)
FEATURE_TABLES = ["oee_activity_master", "oee_activity_runs"]

# Column Claude added / that the new feature would need
FEATURE_COLUMNS_ON_LOSSES = ["activity_run_id"]


print("=" * 72)
print(" 1. DATABASE — EXPECTED TABLES")
print("=" * 72)

for tbl, expected_cols in EXPECTED_TABLES.items():
    if not table_exists(tbl):
        rec("MISSING", "db.table", f"{tbl} does not exist")
        print(f"  MISSING  {tbl}")
        continue

    cols = columns_of(tbl)
    print(f"  OK       {tbl}  ({row_count(tbl):,} rows, {len(cols)} cols)")

    for col, want_type_prefix in expected_cols.items():
        if col not in cols:
            rec("MISSING", "db.column",
                f"{tbl}.{col} missing (expected added in migration)")
            print(f"           - MISSING column {col}")
        else:
            actual_type = str(cols[col]["Type"]).lower()
            if want_type_prefix and not actual_type.startswith(want_type_prefix):
                rec("CHANGED", "db.column",
                    f"{tbl}.{col} type is {actual_type}, "
                    f"Claude added it as {want_type_prefix}(...)")
                print(f"           - CHANGED {col}: {actual_type}")


print()
print("=" * 72)
print(" 2. DATABASE — NEW FEATURE (Tool Room / Development)")
print("=" * 72)

for tbl in FEATURE_TABLES:
    if table_exists(tbl):
        cols = columns_of(tbl)
        rec("EXTRA", "db.table",
            f"{tbl} exists — this is your new feature, Claude did not create it")
        print(f"  FOUND    {tbl}  ({row_count(tbl):,} rows, {len(cols)} cols)")
        print(f"           columns: {', '.join(cols.keys())}")
    else:
        print(f"  ABSENT   {tbl}  (not built yet)")

for col in FEATURE_COLUMNS_ON_LOSSES:
    if table_exists("oee_machine_loss_events"):
        if col in columns_of("oee_machine_loss_events"):
            rec("EXTRA", "db.column",
                f"oee_machine_loss_events.{col} exists — added by new feature")
            print(f"  FOUND    oee_machine_loss_events.{col}")
        else:
            print(f"  ABSENT   oee_machine_loss_events.{col}")


print()
print("=" * 72)
print(" 3. DATABASE — DATA HEALTH")
print("=" * 72)

# Sessions that never closed
if table_exists("oee_machine_sessions"):
    cur.execute(
        "SELECT session_status, COUNT(*) AS c "
        "FROM oee_machine_sessions GROUP BY session_status"
    )
    for r in cur.fetchall():
        st = r['session_status']
        c  = r['c']
        print(f"  oee_machine_sessions status={st!r:12s} count={c}")
        if st == "OPEN" and c > 5:
            rec("WARN", "db.data",
                f"{c} sessions stuck at OPEN. Expected — we chose not to close.")

# Runs by status
if table_exists("oee_machine_runs"):
    cur.execute(
        "SELECT run_status, COUNT(*) AS c "
        "FROM oee_machine_runs GROUP BY run_status"
    )
    for r in cur.fetchall():
        print(f"  oee_machine_runs status={r['run_status']!r:15s} count={r['c']}")

# Orphan losses (no run_id AND no activity_run_id)
if table_exists("oee_machine_loss_events"):
    cols = columns_of("oee_machine_loss_events")
    if "activity_run_id" in cols:
        cur.execute(
            "SELECT COUNT(*) AS c FROM oee_machine_loss_events "
            "WHERE run_id IS NULL AND activity_run_id IS NULL"
        )
    else:
        cur.execute(
            "SELECT COUNT(*) AS c FROM oee_machine_loss_events "
            "WHERE run_id IS NULL"
        )
    orphan = (cur.fetchone() or {}).get("c") or 0
    print(f"  Orphan loss events (no parent link): {orphan}")
    if orphan > 0:
        rec("WARN", "db.data",
            f"{orphan} loss events have no parent run/activity link")

# Runs COMPLETED but not mirrored to oee_entries
if table_exists("oee_machine_runs") and table_exists("oee_entries"):
    cur.execute("""
        SELECT COUNT(*) AS c
        FROM oee_machine_runs r
        JOIN oee_machine_sessions s ON s.id = r.session_id
        LEFT JOIN oee_entries e
               ON e.job_card_no = r.job_card_no
              AND e.machine_id  = r.machine_id
              AND e.entry_date  = s.session_date
              AND (e.operator_master_id <=> r.operator_master_id)
              AND (e.start_time <=> r.oee_start_time)
        WHERE r.run_status = 'COMPLETED'
          AND e.id IS NULL
    """)
    unsynced = (cur.fetchone() or {}).get("c") or 0
    print(f"  COMPLETED runs not mirrored to oee_entries: {unsynced}")
    if unsynced > 0:
        rec("WARN", "db.data",
            f"{unsynced} COMPLETED runs have no matching oee_entries row — "
            f"sync hook may not be firing")


# ===========================================================
# 4. CODE FILES — what Claude patched
# ===========================================================

print()
print("=" * 72)
print(" 4. CODE FILES — CLAUDE'S CHANGES")
print("=" * 72)

CODE_CHECKS = [
    # (path, must_contain, description)
    (r"routes\oee_persistence.py",
     "def sync_completed_run_to_oee_entries",
     "sync hook function present"),
    (r"routes\oee_persistence.py",
     "get_oee_formula_profile",
     "formula profile helper present"),

    (r"routes\quality_check.py",
     "from .oee_persistence import sync_completed_run_to_oee_entries",
     "sync hook is invoked from JC completion"),
    (r"routes\quality_check.py",
     "sync_completed_run_to_oee_entries(",
     "sync hook call site present"),

    (r"routes\oee_machine_summary.py",
     "@oee_machine_summary_bp.route(\"/api/oee-machine-summary/export-excel\")",
     "Excel export endpoint present"),
    (r"routes\oee_machine_summary.py",
     "FROM oee_entries",
     "summary queries read from oee_entries"),
    (r"routes\oee_machine_summary.py",
     "def api_oee_machine_summary_kpi",
     "KPI endpoint present"),
    (r"routes\oee_machine_summary.py",
     "def api_oee_machine_summary_machine_wise",
     "Machine-wise endpoint present"),
    (r"routes\oee_machine_summary.py",
     "def api_oee_machine_summary_operator_wise",
     "Operator-wise endpoint present"),
    (r"routes\oee_machine_summary.py",
     "def api_oee_machine_summary_drill_down",
     "Drill-down endpoint present"),

    (r"templates\oee_machine_summary.html",
     "/api/oee-machine-summary/export-excel",
     "template wires the Excel button to the endpoint"),
    (r"templates\oee_machine_summary.html",
     "Machine-wise",
     "template has Machine-wise tab"),
    (r"templates\oee_machine_summary.html",
     "Operator-wise",
     "template has Operator-wise tab"),

    (r"templates\base.html",
     "OEE Summary",
     "sidebar shows OEE Summary link"),

    (r"app.py",
     "oee_machine_summary_bp",
     "blueprint registered in app.py"),
]

for path, needle, desc in CODE_CHECKS:
    full = os.path.join(PROJECT_DIR, path)
    if not os.path.exists(full):
        rec("MISSING", "code.file", f"{path} does not exist")
        print(f"  MISSING  {path}")
        continue
    try:
        with open(full, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        rec("WARN", "code.file", f"could not read {path}: {e}")
        print(f"  WARN     could not read {path}: {e}")
        continue

    if needle in content:
        print(f"  OK       {path}  -- {desc}")
    else:
        rec("MISSING", "code.pattern",
            f"{path} missing expected pattern: {desc}")
        print(f"  MISSING  {path}  -- {desc}")

# Detect that quality_check.py still writes to old tables (expected)
qc = os.path.join(PROJECT_DIR, "routes", "quality_check.py")
if os.path.exists(qc):
    with open(qc, encoding="utf-8", errors="ignore") as f:
        qc_src = f.read()
    if "INSERT INTO oee_machine_sessions" in qc_src:
        print(f"  OK       routes\\quality_check.py  -- operator page still writes to sessions (expected)")
    else:
        rec("WARN", "code.pattern",
            "quality_check.py no longer INSERTs into oee_machine_sessions "
            "— operator page may have been rewritten")


# ===========================================================
# 5. NEW FEATURE — did the other AI touch anything Claude built?
# ===========================================================

print()
print("=" * 72)
print(" 5. NEW-FEATURE FOOTPRINT")
print("=" * 72)

# Scan every .py in routes/ for references to activity tables
activity_hits = []
routes_dir = os.path.join(PROJECT_DIR, "routes")
if os.path.isdir(routes_dir):
    for fn in os.listdir(routes_dir):
        if not fn.endswith(".py"):
            continue
        with open(os.path.join(routes_dir, fn), encoding="utf-8",
                  errors="ignore") as f:
            src = f.read()
        for pat in ("oee_activity_master", "oee_activity_runs",
                    "activity_run_id", "TOOL_ROOM", "DEVELOPMENT"):
            for m in re.finditer(re.escape(pat), src):
                line_no = src.count("\n", 0, m.start()) + 1
                activity_hits.append((fn, line_no, pat))

if activity_hits:
    print(f"  Found {len(activity_hits)} activity-feature references:")
    seen = set()
    for fn, ln, pat in activity_hits:
        key = (fn, pat)
        if key in seen:
            continue
        seen.add(key)
        print(f"    routes\\{fn}  line {ln}  contains {pat!r}")
else:
    print("  No routes/*.py file references the new activity tables yet.")

# Templates and JS for the operator page
op_files = [
    r"templates\oee_machine_operator.html",
    r"static\js\oee_machine_operator.js",
]
print()
print("  Operator page files (checking for Tool Room / Development):")
for path in op_files:
    full = os.path.join(PROJECT_DIR, path)
    if not os.path.exists(full):
        print(f"    ABSENT   {path}")
        continue
    with open(full, encoding="utf-8", errors="ignore") as f:
        src = f.read()
    has_tool = "Tool Room" in src or "TOOL_ROOM" in src or "tool-room" in src.lower()
    has_dev  = "Development" in src or "DEVELOPMENT" in src.lower()
    tag = "TOOL ROOM present" if has_tool else "no Tool Room UI"
    tag2 = "DEVELOPMENT present" if has_dev else "no Development UI"
    print(f"    {path}: {tag}, {tag2}")


# ===========================================================
# 6. FINAL REPORT
# ===========================================================

print()
print("=" * 72)
print(" 6. SUMMARY OF FINDINGS")
print("=" * 72)

by_level = {}
for lvl, area, msg in findings:
    by_level.setdefault(lvl, []).append((area, msg))

for lvl in ("MISSING", "CHANGED", "EXTRA", "WARN"):
    items = by_level.get(lvl, [])
    print(f"\n  {lvl} ({len(items)})")
    if not items:
        print("    (none)")
        continue
    for area, msg in items:
        print(f"    [{area}] {msg}")

print()
print("=" * 72)
print(" LEGEND")
print("=" * 72)
print("  MISSING — Claude's shipped code/schema is not present anymore.")
print("            Either it never ran, or it was reverted / overwritten.")
print("  CHANGED — Something Claude added is now different (type / signature).")
print("  EXTRA   — Something exists that Claude did NOT ship — likely built by")
print("            the other AI (Tool Room / Development work).")
print("  WARN    — Not necessarily broken, but worth eyeballing.")
print()

cur.close()
conn.close()
