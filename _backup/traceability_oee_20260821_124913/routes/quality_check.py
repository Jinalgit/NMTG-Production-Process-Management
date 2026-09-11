"""
Quality Check / Tracibility routes for Demo 2.
Includes WIP status tracking, in/out time recording, and audit trail.
"""

import re
from datetime import date as date_cls
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, session
from mysql.connector import Error

from db import get_connection
from .oee_persistence import save_oee_entry
from permission_utils import (
    PAGE3_TRACEABILITY,
    can_user_edit_field,
    ensure_permission_tables,
    is_gaurang_special_identity,
    is_gaurang_special_user,
    seed_default_permissions,
)

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt


quality_check_bp = Blueprint("quality_check", __name__)

PROCESS_COUNT = 25
PROCESS_COLUMNS = [f"p{i}" for i in range(1, PROCESS_COUNT + 1)]
PROCESS_COLUMNS_SQL = ",".join(PROCESS_COLUMNS)


def _fmt(v, date_only=False):
    """Format a date or datetime object to string, or return None."""
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d") if date_only else v.strftime("%Y-%m-%d")
    s = str(v)
    return s[:10] if s else None


def _has_column(cursor, table, column):
    """Check if a column exists in the given table."""
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = %s
          AND COLUMN_NAME  = %s
    """,
        (table, column),
    )
    return cursor.fetchone()["cnt"] > 0


def supervisor_has_process_access(cursor, user_id, process_name):
    if is_gaurang_special_identity(user_id) or is_gaurang_special_user():
        return True
    cursor.execute("""
        SELECT 1
        FROM supervisor_process_access
        WHERE user_id = %s
          AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
        LIMIT 1
    """, (user_id, process_name or ""))
    return cursor.fetchone() is not None


def _match_processes(a, b):
    """
    Fuzzy match two process names.
    Handles variations like 'R/Turning' == 'Rough Turning' == 'RT'.
    """
    a_low = (a or "").lower().strip()
    b_low = (b or "").lower().strip()
    if not a_low or not b_low:
        return False
    if a_low == b_low:
        return True
    a_norm = re.sub(r"[\s/\-]+", " ", a_low).strip()
    b_norm = re.sub(r"[\s/\-]+", " ", b_low).strip()
    aliases = {
        "rm": "raw material",
        "raw mat": "raw material",
        "rawmaterial": "raw material",
        "qc": "quality check",
        "quality": "quality check",
        "qualitycheck": "quality check",
    }
    a_alias = aliases.get(a_norm, aliases.get(
        re.sub(r"[^a-z0-9]+", "", a_norm), a_norm))
    b_alias = aliases.get(b_norm, aliases.get(
        re.sub(r"[^a-z0-9]+", "", b_norm), b_norm))
    if a_alias == b_alias:
        return True
    if a_norm == b_norm:
        return True
    a_words = [w for w in re.split(r"[\s/\-]+", a_low) if w]
    b_words = [w for w in re.split(r"[\s/\-]+", b_low) if w]
    a_init = "".join(w[0] for w in a_words)
    b_init = "".join(w[0] for w in b_words)
    if a_init == b_init and len(a_init) > 1:
        return True
    if len(a_words) == len(b_words):
        if all(
            wa == wb or wb.startswith(wa) or wa.startswith(wb)
            for wa, wb in zip(a_words, b_words)
        ):
            return True
    return False


def _norm_process_name(v):
    """Normalize process name for safer matching."""
    return re.sub(r"[\s/\-]+", " ", (v or "").lower().strip())


def _find_pd_row(proc_name, pd_rows):
    proc_raw = (proc_name or "").strip().lower()
    proc_norm = _norm_process_name(proc_name)
    for row in pd_rows:
        row_name = (row.get("process_name") or "").strip().lower()
        if row_name == proc_raw:
            return row
    for row in pd_rows:
        row_norm = _norm_process_name(row.get("process_name"))
        if row_norm == proc_norm:
            return row
    return None


def _wip_process_index(wip_status, processes):
    if not wip_status or wip_status.lower().strip() == "pending":
        return -1
    wip_raw = wip_status.strip().lower()
    wip_norm = _norm_process_name(wip_status)
    for i, proc in enumerate(processes):
        if (proc or "").strip().lower() == wip_raw:
            return i
    for i, proc in enumerate(processes):
        if _norm_process_name(proc) == wip_norm:
            return i
    return -1


def _processes_from_pm_row(pm_row):
    if not pm_row:
        return []
    return [
        pm_row.get(col)
        for col in PROCESS_COLUMNS
        if pm_row.get(col)
    ]


def _fetch_process_master_row(cursor, job_card_no, item_name):
    cursor.execute(
        """
        SELECT """ + PROCESS_COLUMNS_SQL + """
        FROM process_master pm
        JOIN job_card_items ji
          ON LOWER(TRIM(pm.model_name)) = LOWER(TRIM(ji.item_name))
        WHERE ji.job_card_no = %s
          AND TRIM(ji.item_name) = TRIM(%s)
        LIMIT 1
        """,
        (job_card_no, item_name.strip()),
    )
    pm_row = cursor.fetchone()
    if pm_row:
        return pm_row

    # NOTE: the previous fuzzy LIKE fallback here was removed — it matched
    # on a generic prefix shared by hundreds of unrelated rows (e.g. every
    # "Freewheel Oneway Clutch Model: ..." variant), causing MySQL to return
    # an arbitrary, wrong process_master record for items with no exact
    # match. Callers of this function already fall back to
    # job_card_process_days (the actual saved process sequence for the job
    # card) when this returns None, which is the correct, safe behavior.
    return None


def _fetch_process_day_sequence(cursor, job_card_no):
    cursor.execute(
        """
        SELECT process_name
        FROM job_card_process_days
        WHERE job_card_no = %s
          AND process_name IS NOT NULL
          AND TRIM(process_name) <> ''
        ORDER BY id
        """,
        (job_card_no,),
    )
    return [row["process_name"] for row in cursor.fetchall()]


def _fetch_process_sequence(cursor, job_card_no, item_name):
    processes = _fetch_process_day_sequence(cursor, job_card_no)
    if processes:
        return processes, "job_card_process_days", None
    pm_row = _fetch_process_master_row(cursor, job_card_no, item_name)
    return _processes_from_pm_row(pm_row), "process_master", pm_row


def _ensure_current_drawing_started(cursor, job_card_no, job_card_date=None):
    cursor.execute(
        """
        SELECT 1
        FROM job_card_items
        WHERE job_card_no = %s
          AND LOWER(TRIM(wip_status)) = 'drawing'
        LIMIT 1
        """,
        (job_card_no,),
    )
    if not cursor.fetchone():
        return

    cursor.execute(
        """
        UPDATE job_card_process_days
        SET in_time = COALESCE(%s, NOW()),
            out_time = NULL,
            is_completed = 0,
            actual_days = NULL,
            end_date = NULL
        WHERE job_card_no = %s
          AND LOWER(TRIM(process_name)) = 'drawing'
          AND in_time IS NULL
        """,
        (job_card_date, job_card_no),
    )


def _process_index(processes, stage):
    for i, proc in enumerate(processes):
        if _match_processes(proc, stage):
            return i
    return None


def _is_store_stage(stage):
    return (stage or "").strip().lower() == "store"


def _remaining_days_from_delivery(delivery_date):
    if not delivery_date:
        return 0
    try:
        if isinstance(delivery_date, str):
            delivery_date = datetime.strptime(
                delivery_date[:10], "%Y-%m-%d").date()
        elif hasattr(delivery_date, "date") and not isinstance(delivery_date, date_cls):
            delivery_date = delivery_date.date()
        return (delivery_date - date_cls.today()).days
    except Exception:
        return 0


def _pending_previous_stage_error(cursor, job_card_no, processes, new_idx, old_idx, new_stage):
    # Do not block previous stages here.
    # Main sequence validation already checks old_stage -> next_stage.
    # This avoids false error like:
    # "Complete Drawing before moving to Cutting"
    # when current WIP is already Raw Material.
    return None


def _validate_next_stage(cursor, job_card_no, processes, old_stage, new_stage):
    old_idx = _process_index(processes, old_stage)
    new_idx = _process_index(processes, new_stage)

    if _is_store_stage(old_stage):
        return "Item is already in Store. No further movement allowed.", old_idx, new_idx

    if not processes:
        return None, old_idx, new_idx

    if new_idx is None:
        return f"Process '{new_stage}' is not defined for this job card.", old_idx, new_idx

    store_idx = _process_index(processes, "Store")
    if store_idx is not None and new_idx > store_idx:
        return "Item is already in Store. No further movement allowed.", old_idx, new_idx

    if (old_stage or "").strip().lower() == "pending":
        if new_idx != 0:
            return (
                f"Stage skip not allowed. Complete '{processes[0]}' "
                f"before moving to '{new_stage}'."
            ), old_idx, new_idx
    elif old_idx is None:
        return f"Current stage '{old_stage}' is not defined for this job card.", old_idx, new_idx
    elif new_idx != old_idx + 1:
        return (
            f"Stage skip not allowed. Complete '{processes[old_idx]}' "
            f"before moving to '{new_stage}'."
        ), old_idx, new_idx

    pending_error = _pending_previous_stage_error(
        cursor, job_card_no, processes, new_idx, old_idx, new_stage
    )
    return pending_error, old_idx, new_idx


def _resolve_job_card_no(cursor, job_card_no):
    """Resolve a job_card_no string to the exact stored value (exact match only)."""
    cursor.execute(
        "SELECT job_card_no FROM job_cards WHERE job_card_no = %s LIMIT 1",
        (job_card_no,),
    )
    row = cursor.fetchone()
    return row["job_card_no"] if row else None


# PAGE3_ROUTE_SYNC_FROM_ITEM_PROCESS_MASTER_START
def _norm_process_key(value):
    return " ".join(str(value or "").strip().lower().split())


def _resequence_item_processes(cursor, item_code):
    """
    Re-number Process Master routing step_no for one child/item code.
    Example: 1,2,4 becomes 1,2,3.
    """
    if not item_code:
        return

    cursor.execute("""
        SELECT id
        FROM item_processes
        WHERE item_code = %s
        ORDER BY step_no, id
    """, (item_code,))

    rows = cursor.fetchall()

    for new_step_no, row in enumerate(rows, start=1):
        cursor.execute("""
            UPDATE item_processes
            SET step_no = %s
            WHERE id = %s
        """, (new_step_no, row["id"]))


def _ensure_job_card_process_exclusions_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_card_process_exclusions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            job_card_no VARCHAR(50) NOT NULL,
            process_name VARCHAR(255) NOT NULL,
            process_name_norm VARCHAR(255) NOT NULL,
            removed_by VARCHAR(100) NULL,
            removed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_jc_process_exclusion (job_card_no, process_name_norm),
            INDEX idx_jc_process_exclusion_job_card (job_card_no)
        )
    """)


def _excluded_process_keys_for_job_card(cursor, job_card_no):
    try:
        _ensure_job_card_process_exclusions_table(cursor)
        cursor.execute(
            """
            SELECT process_name_norm
            FROM job_card_process_exclusions
            WHERE job_card_no = %s
            """,
            (job_card_no,),
        )
        return {
            (r.get("process_name_norm") or "").strip()
            for r in cursor.fetchall()
            if (r.get("process_name_norm") or "").strip()
        }
    except Exception as ex:
        print("Warning: process exclusion check failed:", ex)
        return set()


def _sync_job_card_process_days_with_item_route(cursor, job_card_no):
    """
    Sync Page3 saved timeline from Page2 item routing.

    Safe behavior:
    - Uses job_cards.child_code as item_code.
    - Adds missing Page2 routing processes into job_card_process_days.
    - Rebuilds row order so Page3 ORDER BY id shows correct sequence.
    - Preserves existing in_time, out_time, is_completed, subcontract and vendor.
    - Does not update item_processes / Process Master.
    - Does not remove extra existing job-card-specific process rows.
    """
    if not job_card_no:
        return {"success": False, "reason": "missing_job_card_no"}

    cursor.execute(
        """
        SELECT
            jc.job_card_no,
            jc.child_code,
            ji.item_name
        FROM job_cards jc
        JOIN job_card_items ji
          ON ji.job_card_no = jc.job_card_no
        WHERE jc.job_card_no = %s
          AND COALESCE(ji.is_deleted, 0) = 0
        ORDER BY ji.id
        LIMIT 1
        """,
        (job_card_no,),
    )
    item_row = cursor.fetchone()
    if not item_row:
        return {"success": False, "reason": "job_card_not_found"}

    item_code = (item_row.get("child_code") or "").strip()
    item_name = (item_row.get("item_name") or "").strip()

    # Fallback: if child_code is blank, resolve item_code from item description.
    if not item_code and item_name:
        cursor.execute(
            """
            SELECT item_code
            FROM items
            WHERE TRIM(item_description) = TRIM(%s)
            ORDER BY item_code
            LIMIT 1
            """,
            (item_name,),
        )
        found_item = cursor.fetchone()
        if found_item:
            item_code = (found_item.get("item_code") or "").strip()

    if not item_code:
        return {"success": False, "reason": "item_code_not_found"}

    # Page2 / Process Master route for this item code.
    cursor.execute(
        """
        SELECT
            ip.step_no,
            p.process_name
        FROM item_processes ip
        JOIN processes p
          ON p.id = ip.process_id
        WHERE ip.item_code = %s
          AND p.process_name IS NOT NULL
          AND TRIM(p.process_name) <> ''
        ORDER BY ip.step_no
        """,
        (item_code,),
    )
    route_rows = cursor.fetchall()

    route_names = []
    seen = set()
    for r in route_rows:
        name = (r.get("process_name") or "").strip()
        key = _norm_process_key(name)
        if name and key not in seen:
            route_names.append(name)
            seen.add(key)

    if not route_names:
        return {"success": False, "reason": "no_item_route_found", "item_code": item_code}

    optional_cols = []
    for col in ("lead_date", "end_date"):
        try:
            if _has_column(cursor, "job_card_process_days", col):
                optional_cols.append(col)
        except Exception:
            pass

    select_cols = [
        "id",
        "process_name",
        "days",
        "is_completed",
        "in_time",
        "out_time",
        "actual_days",
        "is_subcontract",
        "vendor_name",
    ] + optional_cols

    cursor.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM job_card_process_days
        WHERE job_card_no = %s
          AND process_name IS NOT NULL
          AND TRIM(process_name) <> ''
        ORDER BY id
        """,
        (job_card_no,),
    )
    existing_rows = cursor.fetchall()

    if not existing_rows:
        return {"success": False, "reason": "no_existing_job_card_process_rows"}

    existing_map = {}
    existing_order_keys = []

    for row in existing_rows:
        key = _norm_process_key(row.get("process_name"))
        if key:
            existing_order_keys.append(key)
            if key not in existing_map:
                existing_map[key] = row

    excluded_keys = _excluded_process_keys_for_job_card(cursor, job_card_no)

    # STRICT MIRROR MODE WITH JOB-CARD EXCEPTION:
    # Page3 timeline follows Page2 item routing,
    # but any process removed from Page3 for this job card is skipped.
    final_names = []
    final_seen = set()

    for name in route_names:
        key = _norm_process_key(name)
        if key in excluded_keys:
            continue
        if key not in final_seen:
            final_names.append(name)
            final_seen.add(key)

    for tail in ("Quality Check", "Store"):
        key = _norm_process_key(tail)
        if key in excluded_keys:
            continue
        if key not in final_seen:
            final_names.append(tail)
            final_seen.add(key)

    final_keys = [_norm_process_key(x) for x in final_names]

    if final_keys == existing_order_keys:
        return {
            "success": True,
            "synced": False,
            "reason": "already_in_sync",
            "item_code": item_code,
        }

    cursor.execute(
        """
        SELECT process_name, default_days
        FROM process_default_days
        WHERE process_name IS NOT NULL
          AND TRIM(process_name) <> ''
        """
    )
    default_days_map = {
        _norm_process_key(r.get("process_name")): r.get("default_days")
        for r in cursor.fetchall()
    }

    insert_cols = [
        "job_card_no",
        "process_name",
        "days",
        "is_completed",
        "in_time",
        "out_time",
        "actual_days",
        "is_subcontract",
        "vendor_name",
    ] + optional_cols

    insert_sql = f"""
        INSERT INTO job_card_process_days
        ({", ".join(insert_cols)})
        VALUES ({", ".join(["%s"] * len(insert_cols))})
    """

    insert_values = []

    for name in final_names:
        key = _norm_process_key(name)
        old = existing_map.get(key)

        if old:
            days = old.get("days")
            if days is None:
                days = default_days_map.get(key, 0)

            row_values = [
                job_card_no,
                name,
                days,
                old.get("is_completed", 0) or 0,
                old.get("in_time"),
                old.get("out_time"),
                old.get("actual_days"),
                old.get("is_subcontract", 0) or 0,
                old.get("vendor_name"),
            ]
            for col in optional_cols:
                row_values.append(old.get(col))
        else:
            row_values = [
                job_card_no,
                name,
                default_days_map.get(key, 0) or 0,
                0,
                None,
                None,
                None,
                0,
                None,
            ]
            for col in optional_cols:
                row_values.append(None)

        insert_values.append(tuple(row_values))

    cursor.execute(
        "DELETE FROM job_card_process_days WHERE job_card_no = %s",
        (job_card_no,),
    )
    cursor.executemany(insert_sql, insert_values)

    return {
        "success": True,
        "synced": True,
        "item_code": item_code,
        "old_sequence": existing_order_keys,
        "new_sequence": final_keys,
    }
# PAGE3_ROUTE_SYNC_FROM_ITEM_PROCESS_MASTER_END


@quality_check_bp.route("/api/quality_check/fetch/<path:job_card_no>", methods=["GET"])
def fetch_for_quality_check(job_card_no):
    """
    Fetch job card + items + processes + process timeline + supervisors.
    Supports search by Job Card No or SO No.
    """
    conn = None
    cursor = None

    try:
        search_value = (job_card_no or "").strip()

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1) Fetch job card by Job Card No OR SO No
        cursor.execute(
            """
    SELECT *
    FROM job_cards
    WHERE TRIM(job_card_no) = TRIM(%s)
       OR TRIM(so_no) = TRIM(%s)
       OR (
            %s REGEXP '^[0-9]+$'
            AND TRIM(job_card_no) REGEXP '^[0-9]+$'
            AND CAST(TRIM(job_card_no) AS UNSIGNED) = CAST(%s AS UNSIGNED)
       )
    ORDER BY
        CASE
            WHEN TRIM(job_card_no) = TRIM(%s) THEN 0
            WHEN TRIM(so_no) = TRIM(%s) THEN 1
            ELSE 2
        END
    LIMIT 1
    """,
            (
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
                search_value,
            ),
        )
        job_card = cursor.fetchone()

        if not job_card:
            return jsonify({
                "success": False,
                "error": "Job Card not found!"
            }), 404

        # IMPORTANT: use actual job_card_no from DB for all further queries
        actual_job_card_no = job_card["job_card_no"]

        # Format job_card date fields
        for df in ["so_date", "job_card_date", "work_order_date", "created_at"]:
            if job_card.get(df) and hasattr(job_card[df], "strftime"):
                job_card[df] = job_card[df].strftime("%Y-%m-%d")

        # Ensure parent/child code keys are always available in response
        job_card["parent_code"] = job_card.get("parent_code") or ""
        job_card["child_code"] = job_card.get("child_code") or ""

        # 2) Fetch items using actual job card no
        cursor.execute(
            """
            SELECT *
            FROM job_card_items
            WHERE job_card_no = %s
            ORDER BY id
            """,
            (actual_job_card_no,),
        )
        items = cursor.fetchall()

        enriched_items = []

        for item in items:
            item_name = item.get("item_name") or ""

            # Exact process master match only
            cursor.execute(
                """
                SELECT """ + PROCESS_COLUMNS_SQL + """,
                       num_operations,
                       material,
                       part_name
                FROM process_master
                WHERE LOWER(TRIM(model_name)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                (item_name,),
            )
            pm = cursor.fetchone()

            processes = []
            if pm:
                for i in range(1, PROCESS_COUNT + 1):
                    p = pm.get(f"p{i}")
                    if p and str(p).strip():
                        processes.append(str(p).strip())

            delivery = item.get("delivery_date")
            remaining_days = _remaining_days_from_delivery(delivery)

            current_wip = item.get("wip_status") or "Pending"
            rm_reason = (item.get("rm_hold_reason") or "").strip().lower()
            is_rm_shortage = (
                current_wip.strip().lower() == "raw material"
                and rm_reason == "shortage"
            )

            calculated_wip_stage_days = item.get("wip_stage_days") or 0

            if is_rm_shortage:
                calculated_wip_stage_days = 0
            else:
                cursor.execute(
                    """
                    SELECT in_time
                    FROM job_card_process_days
                    WHERE job_card_no = %s
                      AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                      AND in_time IS NOT NULL
                      AND out_time IS NULL
                      AND COALESCE(is_completed, 0) = 0
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (actual_job_card_no, current_wip),
                )
                active_process = cursor.fetchone()

                if active_process and active_process.get("in_time"):
                    in_time = active_process.get("in_time")
                    in_date = (
                        in_time.date()
                        if hasattr(in_time, "date")
                        else datetime.strptime(str(in_time)[:10], "%Y-%m-%d").date()
                    )
                    calculated_wip_stage_days = max(
                        0,
                        (date_cls.today() - in_date).days
                    )

            if delivery and hasattr(delivery, "strftime"):
                delivery = delivery.strftime("%Y-%m-%d")

            # Fetch raw material from BOM if not set on job card item
            bom_material = ""
            child_code = job_card.get("child_code") or ""
            if child_code:
                cursor.execute("""
                    SELECT i.item_description
                    FROM bom_links bl
                    JOIN items i ON i.item_code = bl.child_code
                    WHERE bl.parent_code = %s
                    AND bl.make_buy = 'I'
                    AND bl.is_alternate = 0
                    LIMIT 1
                """, (child_code,))
                bom_row = cursor.fetchone()
                if bom_row:
                    bom_material = bom_row.get("item_description") or ""

            enriched_items.append(
                {
                    "id": item.get("id"),
                    "job_card_no": actual_job_card_no,
                    "item_name": item_name,
                    "material": item.get("material") or bom_material or (pm.get("material") if pm else "") or "",
                    "so_qty": item.get("so_qty"),
                    "job_card_qty": item.get("job_card_qty"),
                    "actual_qty": item.get("actual_qty") or 0,
                    "wip_status": item.get("wip_status") or "Pending",
                    "rm_hold_reason": item.get("rm_hold_reason") or "",
                    "wip_stage_days": calculated_wip_stage_days,
                    "total_days": item.get("total_days") or 0,
                    "remaining_days": remaining_days,
                    "delivery_date": delivery,
                    "remarks": item.get("remarks") or "",
                    "part": item.get("part") or (pm.get("part_name") if pm else "") or "",
                    "dia": item.get("dia") or "",
                    "length": item.get("length") or "",
                    "processes": processes,
                    "is_priority": item.get("is_priority") or 0,
                }
            )

        # 3) Ensure required columns exist in job_card_process_days
        for col, defn in [
            ("lead_date", "DATE NULL"),
            ("in_time", "DATETIME NULL"),
            ("out_time", "DATETIME NULL"),
            ("actual_days", "INT NULL"),
            ("end_date", "DATE NULL"),
            ("is_subcontract", "TINYINT(1) DEFAULT 0"),
            ("vendor_name", "VARCHAR(255)"),
        ]:
            if not _has_column(cursor, "job_card_process_days", col):
                cursor.execute(
                    f"ALTER TABLE job_card_process_days ADD COLUMN {col} {defn}"
                )

        # Page3 must display the saved job-card timeline.
        # Do not rebuild running job cards from the current Process Master route.
        # _sync_job_card_process_days_with_item_route(cursor, actual_job_card_no)

        has_time_cols = _has_column(cursor, "job_card_process_days", "in_time")
        if has_time_cols:
            _ensure_current_drawing_started(
                cursor,
                actual_job_card_no,
                job_card.get("job_card_date") or None,
            )

        # AUTO_CUTTING_PLAN_WIP_HOOK_V1
        cutting_plan_result = None
        cutting_plan_warning = None

        # Raw Material -> Cutting trigger placeholder
        # Installed safely. Backend helper can be connected here.
        # AUTO_CUTTING_PLAN_WIP_HOOK_V1

        conn.commit()

        # 4) Fetch process day rows using actual job card no
        if has_time_cols:
            cursor.execute(
                """
                SELECT
                    jpd.id,
                    jpd.process_name,
                    jpd.lead_date,
                    COALESCE(pdd.default_days, jpd.days, 0) AS lead_days,
                    jpd.in_time,
                    jpd.out_time,
                    jpd.actual_days,
                    COALESCE(jpd.is_completed, 0) AS is_completed,
                    COALESCE(jpd.is_subcontract, 0) AS is_subcontract,
                    COALESCE(jpd.vendor_name, '') AS vendor_name
                FROM job_card_process_days jpd
                LEFT JOIN process_default_days pdd
                    ON LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(pdd.process_name))
                WHERE jpd.job_card_no = %s
                ORDER BY jpd.id
                """,
                (actual_job_card_no,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    jpd.id,
                    jpd.process_name,
                    jpd.lead_date,
                    COALESCE(pdd.default_days, jpd.days, 0) AS lead_days,
                    COALESCE(jpd.is_subcontract, 0) AS is_subcontract,
                    COALESCE(jpd.vendor_name, '') AS vendor_name
                FROM job_card_process_days jpd
                LEFT JOIN process_default_days pdd
                    ON LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(pdd.process_name))
                WHERE jpd.job_card_no = %s
                ORDER BY jpd.id
                """,
                (actual_job_card_no,),
            )

        pd_rows = cursor.fetchall()

        # 5) Build process timeline item-wise
        for ei in enriched_items:
            processes = [
                row["process_name"].strip()
                for row in pd_rows
                if row.get("process_name")
            ]
            ei["processes"] = processes

            wip_status = ei.get("wip_status") or "Pending"
            ei["wip_process_index"] = _wip_process_index(wip_status, processes)

            item_timeline = []

            for proc in processes:
                pd_row = _find_pd_row(proc, pd_rows)

                in_time = pd_row.get("in_time") if (
                    pd_row and has_time_cols) else None
                out_time = pd_row.get("out_time") if (
                    pd_row and has_time_cols) else None
                act_days = pd_row.get("actual_days") if (
                    pd_row and has_time_cols) else None

                lead_days = int((pd_row.get("lead_days") or 0)
                                if pd_row else 0)
                lead_date = pd_row.get("lead_date") if pd_row else None

                if _is_store_stage(proc) and in_time:
                    status = "On Time" if (
                        act_days is None or act_days <= lead_days) else "Delayed"
                elif not in_time:
                    status = "Pending"
                elif not out_time:
                    status = "In Progress"
                elif act_days is not None:
                    status = "On Time" if act_days <= lead_days else "Delayed"
                else:
                    status = "On Time"

                is_sub = int(pd_row.get("is_subcontract", 0)
                             or 0) if pd_row else 0
                vendor = (pd_row.get("vendor_name", "")
                          or "") if pd_row else ""

                item_timeline.append(
                    {
                        "process_name": proc,
                        "in_time": _fmt(in_time),
                        "out_time": _fmt(out_time),
                        "actual_days": act_days,
                        "lead_days": lead_days,
                        "lead_date": _fmt(lead_date),
                        "status": status,
                        "is_subcontract": is_sub,
                        "vendor_name": vendor,
                    }
                )

            ei["process_timeline"] = item_timeline

        # 6) Supervisors
        cursor.execute(
            "SELECT full_name AS name FROM users WHERE role = 'supervisor' ORDER BY full_name")
        supervisors = [r["name"] for r in cursor.fetchall()]

        # ── Current logged-in user's process access (supervisors only) ─────────
        # Used by the frontend to block the stage-change modal entirely before
        # it opens, instead of letting the user click through and only failing
        # at the final confirm step.
        my_accessible_processes = None
        if session.get("role") == "supervisor" and not is_gaurang_special_user():
            cursor.execute("""
                SELECT process_name FROM supervisor_process_access
                WHERE user_id = %s
            """, (session.get("user_id"),))
            my_accessible_processes = [
                r["process_name"] for r in cursor.fetchall()
            ]

        return jsonify(
            {
                "success": True,
                "job_card": job_card,
                "items": enriched_items,
                "supervisors": supervisors,
                "my_accessible_processes": my_accessible_processes,
            }
        )

    except Error as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except Exception:
            pass


# Kanban view disabled on Page 3.
# @quality_check_bp.route("/api/page3/kanban_summary", methods=["GET"])
def page3_kanban_summary():
    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()
        user_id = session.get("user_id")

        if role not in ["admin", "supervisor"] and not is_gaurang_special_user():
            return jsonify({
                "success": True,
                "summary": {
                    "total_jobcards": 0,
                    "pending_jobcards": 0,
                    "completed_jobcards": 0
                },
                "processes": [],
                "cards": []
            })

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Admin = all process access
        # Supervisor = only assigned processes from supervisor_process_access
        if role == "supervisor" and not is_gaurang_special_user():
            access_join = """
                JOIN supervisor_process_access spa
                  ON spa.user_id = %s
                 AND LOWER(TRIM(spa.process_name)) = LOWER(TRIM(jpd.process_name))
            """
            access_params = [user_id]
        else:
            access_join = ""
            access_params = []

        # IMPORTANT:
        # This condition excludes future untouched stages.
        # It shows only:
        # 1) Current/pending stage
        # 2) Already completed stage
        active_condition = """
            AND (
                   LOWER(TRIM(ji.wip_status)) = LOWER(TRIM(jpd.process_name))
                OR jpd.out_time IS NOT NULL
                OR COALESCE(jpd.is_completed, 0) = 1
            )
        """

        # 1) Overall summary
        summary_sql = f"""
            SELECT
                COUNT(DISTINCT jpd.id) AS total_jobcards,

                COUNT(DISTINCT CASE
                    WHEN LOWER(TRIM(ji.wip_status)) = LOWER(TRIM(jpd.process_name))
                     AND jpd.out_time IS NULL
                     AND COALESCE(jpd.is_completed, 0) = 0
                    THEN jpd.id
                END) AS pending_jobcards,

                COUNT(DISTINCT CASE
                    WHEN jpd.out_time IS NOT NULL
                      OR COALESCE(jpd.is_completed, 0) = 1
                    THEN jpd.id
                END) AS completed_jobcards

            FROM job_card_process_days jpd
            JOIN job_card_items ji
              ON ji.job_card_no = jpd.job_card_no
            {access_join}
            WHERE 1 = 1
            {active_condition}
        """

        cursor.execute(summary_sql, access_params)
        summary = cursor.fetchone() or {}

        # 2) Process-wise summary
        process_sql = f"""
            SELECT
                jpd.process_name,

                COUNT(DISTINCT jpd.id) AS total_jobcards,

                COUNT(DISTINCT CASE
                    WHEN LOWER(TRIM(ji.wip_status)) = LOWER(TRIM(jpd.process_name))
                     AND jpd.out_time IS NULL
                     AND COALESCE(jpd.is_completed, 0) = 0
                    THEN jpd.id
                END) AS pending_jobcards,

                COUNT(DISTINCT CASE
                    WHEN jpd.out_time IS NOT NULL
                      OR COALESCE(jpd.is_completed, 0) = 1
                    THEN jpd.id
                END) AS completed_jobcards

            FROM job_card_process_days jpd
            JOIN job_card_items ji
              ON ji.job_card_no = jpd.job_card_no
            {access_join}
            WHERE 1 = 1
            {active_condition}
            GROUP BY jpd.process_name
            ORDER BY jpd.process_name
        """

        cursor.execute(process_sql, access_params)
        processes = cursor.fetchall()

        # 3) Cards for Kanban process view
        cards_sql = f"""
            SELECT
                jpd.id AS process_day_id,
                jpd.job_card_no,
                jc.so_no,
                jpd.process_name,
                ji.item_name,
                ji.wip_status,
                ji.is_priority,
                ji.delivery_date,
                jpd.in_time,
                jpd.out_time,
                COALESCE(jpd.is_completed, 0) AS is_completed,

                CASE
                    WHEN jpd.out_time IS NOT NULL
                      OR COALESCE(jpd.is_completed, 0) = 1
                    THEN 'completed'
                    ELSE 'pending'
                END AS card_status

            FROM job_card_process_days jpd
            JOIN job_card_items ji
              ON ji.job_card_no = jpd.job_card_no
            LEFT JOIN job_cards jc
              ON jc.job_card_no = jpd.job_card_no
            {access_join}
            WHERE 1 = 1
            {active_condition}
            ORDER BY
                jpd.process_name,
                CASE
                    WHEN jpd.out_time IS NOT NULL
                      OR COALESCE(jpd.is_completed, 0) = 1
                    THEN 1 ELSE 0
                END,
                jpd.job_card_no
            LIMIT 500
        """

        cursor.execute(cards_sql, access_params)
        cards = cursor.fetchall()

        for c in cards:
            for df in ["delivery_date", "in_time", "out_time"]:
                if c.get(df) and hasattr(c[df], "strftime"):
                    c[df] = c[df].strftime("%Y-%m-%d")

        return jsonify({
            "success": True,
            "summary": {
                "total_jobcards": int(summary.get("total_jobcards") or 0),
                "pending_jobcards": int(summary.get("pending_jobcards") or 0),
                "completed_jobcards": int(summary.get("completed_jobcards") or 0),
            },
            "processes": processes,
            "cards": cards
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def _ensure_child_c_gate_override_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS child_c_gate_overrides (
            id BIGINT NOT NULL AUTO_INCREMENT,
            job_card_no VARCHAR(50) NOT NULL,
            item_name VARCHAR(500) NOT NULL,
            item_name_norm VARCHAR(500) NOT NULL,
            override_reason VARCHAR(500) NULL,
            overridden_by VARCHAR(100) NULL,
            overridden_user_id INT NULL,
            overridden_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_active TINYINT(1) NOT NULL DEFAULT 1,

            PRIMARY KEY (id),
            UNIQUE KEY uq_child_c_gate_override (
                job_card_no,
                item_name_norm
            ),
            INDEX idx_child_c_gate_job_card (
                job_card_no,
                is_active
            )
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
    """)


def _child_c_gate_override_exists(cursor, job_card_no, item_name):
    _ensure_child_c_gate_override_table(cursor)

    item_name_norm = " ".join(
        str(item_name or "").strip().lower().split()
    )

    cursor.execute("""
        SELECT id
        FROM child_c_gate_overrides
        WHERE job_card_no = %s
          AND item_name_norm = %s
          AND is_active = 1
        LIMIT 1
    """, (
        job_card_no,
        item_name_norm,
    ))

    return cursor.fetchone() is not None


def _get_pending_c_child_gate_rows(cursor, job_card_no, item_name):
    """
    Returns blocking child -C rows for an upper-level job card item.

    Blocking conditions:
    1. Child -C job card not found under same SO
    2. Child -C has no process rows
    3. Child -C has any pending process
    """
    cursor.execute("SET SESSION group_concat_max_len = 100000")

    cursor.execute("""
        WITH RECURSIVE upper_item AS (
            SELECT
                jc.so_no AS upper_so_no,
                jci.job_card_no AS upper_job_card_no,
                jci.item_name AS upper_item_description,
                i.item_code AS upper_item_code
            FROM job_card_items jci
            JOIN job_cards jc
                ON jc.job_card_no = jci.job_card_no
            JOIN items i
                ON (TRIM(i.item_description) COLLATE utf8mb4_unicode_ci)
                 = (TRIM(jci.item_name) COLLATE utf8mb4_unicode_ci)
            WHERE jci.job_card_no = %s
              AND (TRIM(jci.item_name) COLLATE utf8mb4_unicode_ci)
                = (TRIM(%s) COLLATE utf8mb4_unicode_ci)
        ),

        bom_descendants AS (
            SELECT
                ui.upper_so_no,
                ui.upper_job_card_no,
                ui.upper_item_code,
                ui.upper_item_description,
                bl.bom_no,
                bl.parent_code,
                bl.child_code,
                ci.item_description AS child_description,
                bl.make_buy,
                1 AS level_no,
                CAST(CONCAT(bl.parent_code, ' > ', bl.child_code) AS CHAR(2000)) AS path_text
            FROM upper_item ui
            JOIN bom_links bl
                ON bl.parent_code = ui.upper_item_code
            JOIN items ci
                ON ci.item_code = bl.child_code

            UNION ALL

            SELECT
                bd.upper_so_no,
                bd.upper_job_card_no,
                bd.upper_item_code,
                bd.upper_item_description,
                bl2.bom_no,
                bl2.parent_code,
                bl2.child_code,
                ci2.item_description AS child_description,
                bl2.make_buy,
                bd.level_no + 1 AS level_no,
                CAST(CONCAT(bd.path_text, ' > ', bl2.child_code) AS CHAR(2000)) AS path_text
            FROM bom_descendants bd
            JOIN bom_links bl2
                ON bl2.parent_code = bd.child_code
            JOIN items ci2
                ON ci2.item_code = bl2.child_code
            WHERE bd.level_no < 10
        ),

        c_items AS (
            SELECT DISTINCT
                upper_so_no,
                upper_job_card_no,
                upper_item_code,
                upper_item_description,
                bom_no,
                parent_code,
                child_code AS c_item_code,
                child_description AS c_item_description,
                level_no,
                path_text
            FROM bom_descendants
            WHERE make_buy = 'A'
              AND TRIM(child_description) REGEXP '[[:space:]]-[[:space:]]*C$'
        ),

        c_job_cards AS (
            SELECT
                jc.so_no,
                jci.job_card_no,
                jci.item_name,
                jci.wip_status
            FROM job_card_items jci
            JOIN job_cards jc
                ON jc.job_card_no = jci.job_card_no
        ),

        gate_rows AS (
            SELECT
                ci.upper_job_card_no,
                ci.upper_so_no,
                ci.upper_item_code,
                ci.upper_item_description,

                ci.bom_no,
                ci.level_no,
                ci.path_text,

                ci.c_item_code,
                ci.c_item_description,

                cj.job_card_no AS c_job_card_no,
                cj.wip_status AS c_wip_status,

                (
                    SELECT COUNT(*)
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                ) AS c_total_processes,

                (
                    SELECT COUNT(*)
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                      AND COALESCE(jpd.is_completed, 0) = 1
                      AND jpd.out_time IS NOT NULL
                ) AS c_completed_processes,

                (
                    SELECT COUNT(*)
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                      AND (
                          COALESCE(jpd.is_completed, 0) = 0
                          OR jpd.out_time IS NULL
                      )
                ) AS c_pending_processes,

                (
                    SELECT GROUP_CONCAT(
                        CONCAT(
                            jpd.process_name,
                            ' | completed=', COALESCE(jpd.is_completed, 0),
                            ' | in=', COALESCE(DATE_FORMAT(jpd.in_time, '%Y-%m-%d %H:%i'), 'NULL'),
                            ' | out=', COALESCE(DATE_FORMAT(jpd.out_time, '%Y-%m-%d %H:%i'), 'NULL')
                        )
                        ORDER BY jpd.id
                        SEPARATOR ' || '
                    )
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                ) AS c_process_status,

                CASE
                    WHEN cj.job_card_no IS NULL THEN 'CHILD -C JOB CARD NOT FOUND'
                    WHEN (
                        SELECT COUNT(*)
                        FROM job_card_process_days jpd
                        WHERE jpd.job_card_no = cj.job_card_no
                    ) = 0 THEN 'CHILD -C HAS NO PROCESS ROWS'
                    WHEN (
                        SELECT COUNT(*)
                        FROM job_card_process_days jpd
                        WHERE jpd.job_card_no = cj.job_card_no
                          AND (
                              COALESCE(jpd.is_completed, 0) = 0
                              OR jpd.out_time IS NULL
                          )
                    ) = 0 THEN 'CHILD -C COMPLETED - UPPER CAN START'
                    ELSE 'CHILD -C PENDING - BLOCK UPPER'
                END AS gate_status

            FROM c_items ci
            LEFT JOIN c_job_cards cj
                ON (TRIM(cj.item_name) COLLATE utf8mb4_unicode_ci)
                 = (TRIM(ci.c_item_description) COLLATE utf8mb4_unicode_ci)
               AND (COALESCE(NULLIF(TRIM(cj.so_no), ''), '__BLANK_SO__') COLLATE utf8mb4_unicode_ci)
                 = (COALESCE(NULLIF(TRIM(ci.upper_so_no), ''), '__BLANK_SO__') COLLATE utf8mb4_unicode_ci)
        )

        SELECT *
        FROM gate_rows
        WHERE gate_status IN (
            'CHILD -C PENDING - BLOCK UPPER',
            'CHILD -C JOB CARD NOT FOUND',
            'CHILD -C HAS NO PROCESS ROWS'
        )
        ORDER BY level_no DESC, c_item_description, c_job_card_no
    """, (job_card_no, item_name))

    return cursor.fetchall()


# OPERATOR_COMPLETION_UNDO_BACKEND_V1_START
def _ensure_operator_completion_log_table(cursor):
    """
    Stores the exact pre-completion database state required for a safe
    Operator-only reversal.

    Admin and Supervisor workflows do not use this table.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operator_completion_log (
            id BIGINT NOT NULL AUTO_INCREMENT,
            operator_user_id INT NOT NULL,
            operator_name VARCHAR(100) NULL,

            job_card_no VARCHAR(50) NOT NULL,
            item_name VARCHAR(500) NOT NULL,

            old_stage VARCHAR(100) NOT NULL,
            new_stage VARCHAR(100) NOT NULL,

            old_process_id INT NOT NULL,
            next_process_id INT NULL,

            previous_item_wip_status VARCHAR(100) NULL,
            previous_item_actual_qty INT NULL,
            previous_item_rejected_qty INT NULL,
            previous_item_hold_qty INT NULL,
            previous_item_rejection_reason VARCHAR(255) NULL,
            previous_item_hold_reason VARCHAR(255) NULL,
            previous_item_remarks VARCHAR(500) NULL,
            previous_item_remaining_days INT NULL,
            previous_item_wip_stage_days INT NULL,
            previous_job_final_status VARCHAR(50) NULL,

            old_process_in_time DATETIME NULL,
            old_process_out_time DATETIME NULL,
            old_process_is_completed TINYINT NULL,
            old_process_actual_days INT NULL,
            old_process_end_date DATE NULL,
            old_process_is_subcontract TINYINT NULL,
            old_process_vendor_name VARCHAR(255) NULL,

            next_process_in_time DATETIME NULL,
            next_process_out_time DATETIME NULL,
            next_process_is_completed TINYINT NULL,
            next_process_actual_days INT NULL,
            next_process_end_date DATE NULL,
            next_process_is_subcontract TINYINT NULL,
            next_process_vendor_name VARCHAR(255) NULL,

            submitted_ok_qty INT NULL,
            submitted_rejected_qty INT NULL,
            submitted_hold_qty INT NULL,
            submitted_rejection_reason VARCHAR(255) NULL,
            submitted_hold_reason VARCHAR(255) NULL,
            submitted_stage_remark VARCHAR(500) NULL,

            completion_audit_id INT NULL,
            reversal_audit_id INT NULL,

            status VARCHAR(20) NOT NULL DEFAULT 'active',
            completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            undone_at DATETIME NULL,
            undo_reason VARCHAR(255) NULL,

            PRIMARY KEY (id),
            INDEX idx_operator_completion_user (
                operator_user_id,
                status,
                id
            ),
            INDEX idx_operator_completion_job (
                job_card_no,
                item_name,
                id
            ),
            INDEX idx_operator_completion_audit (
                completion_audit_id
            )
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
    """)


def _update_wip_from_saved_timeline():
    conn = None
    cursor = None
    try:
        data = request.json or {}
        role = (session.get("role") or "").strip().lower()
        if role not in ("admin", "supervisor", "operator") and not is_gaurang_special_user():
            return jsonify({"success": False, "error": "You do not have permission to update WIP stage."}), 403

        job_card_no = (data.get("job_card_no") or "").strip()
        item_name = (data.get("item_name") or "").strip()
        requested_stage = (data.get("new_stage") or "").strip()
        changed_by = data.get("changed_by") or ""
        if not changed_by or changed_by.strip().lower() in ("not assigned", "system", ""):
            changed_by = session.get("username") or session.get(
                "full_name") or "System"

        stage_remark = (data.get("stage_remark") or "").strip()
        rm_hold_reason = (data.get("rm_hold_reason") or "").strip() or None
        actual_qty = data.get("actual_qty")
        try:
            actual_qty = int(actual_qty) if actual_qty not in (
                None, "") else None
        except Exception:
            actual_qty = None

        # Optional operator quantity-outcome payload.
        # Existing supervisor/admin requests remain backward compatible.
        outcome_keys_present = (
            role == "operator"
            and all(
                key in data
                for key in ("ok_qty", "rejected_qty", "hold_qty")
            )
        )

        ok_qty = None
        rejected_qty = None
        hold_qty = None

        rejection_reason = (
            data.get("rejection_reason") or ""
        ).strip()

        hold_reason = (
            data.get("hold_reason") or ""
        ).strip()

        if outcome_keys_present:
            try:
                ok_qty = int(data.get("ok_qty"))
                rejected_qty = int(data.get("rejected_qty"))
                hold_qty = int(data.get("hold_qty"))
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "OK, Not OK and Hold quantities must be whole numbers."
                }), 400

            if min(ok_qty, rejected_qty, hold_qty) < 0:
                return jsonify({
                    "success": False,
                    "error": "OK, Not OK and Hold quantities cannot be negative."
                }), 400

            if rejected_qty > 0 and not rejection_reason:
                return jsonify({
                    "success": False,
                    "error": (
                        "A rejection reason is required when "
                        "Not OK Qty is greater than zero."
                    )
                }), 400

            if hold_qty > 0 and not hold_reason:
                return jsonify({
                    "success": False,
                    "error": (
                        "A hold reason is required when "
                        "Hold Qty is greater than zero."
                    )
                }), 400

            if rejected_qty == 0:
                rejection_reason = ""

            if hold_qty == 0:
                hold_reason = ""

        if not outcome_keys_present:
            pending_qty = 0

        if not all([job_card_no, item_name, requested_stage, changed_by]):
            return jsonify({"success": False, "error": "All fields required"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_permission_tables(cursor)
        seed_default_permissions(cursor)
        conn.commit()

        actual_job_card_no = _resolve_job_card_no(cursor, job_card_no)
        if not actual_job_card_no:
            return jsonify({"success": False, "error": f"Job Card not found: {job_card_no}"}), 404
        job_card_no = actual_job_card_no

        for col, defn in [
            ("lead_date", "DATE NULL"),
            ("in_time", "DATETIME NULL"),
            ("out_time", "DATETIME NULL"),
            ("actual_days", "INT NULL"),
            ("end_date", "DATE NULL"),
            ("is_subcontract", "TINYINT(1) DEFAULT 0"),
            ("vendor_name", "VARCHAR(255)"),
        ]:
            if not _has_column(cursor, "job_card_process_days", col):
                cursor.execute(
                    f"ALTER TABLE job_card_process_days ADD COLUMN {col} {defn}")

        if not _has_column(cursor, "job_card_items", "hold_qty"):
            cursor.execute("""
                ALTER TABLE job_card_items
                ADD COLUMN hold_qty INT NOT NULL DEFAULT 0
                AFTER rejected_qty
            """)

        if not _has_column(
            cursor,
            "job_card_items",
            "rejection_reason"
        ):
            cursor.execute("""
                ALTER TABLE job_card_items
                ADD COLUMN rejection_reason VARCHAR(255) NULL
                AFTER rejected_qty
            """)

        if not _has_column(
            cursor,
            "job_card_items",
            "hold_reason"
        ):
            cursor.execute("""
                ALTER TABLE job_card_items
                ADD COLUMN hold_reason VARCHAR(255) NULL
                AFTER hold_qty
            """)
        if not _has_column(cursor, "job_card_items", "pending_qty"):
            cursor.execute("""
                ALTER TABLE job_card_items
                ADD COLUMN pending_qty INT NOT NULL DEFAULT 0
                AFTER hold_qty
            """)

        if not _has_column(cursor, "job_card_items", "rm_hold_reason"):
            cursor.execute("""
                ALTER TABLE job_card_items
                ADD COLUMN rm_hold_reason VARCHAR(50) NULL
                AFTER pending_qty
            """)

        cursor.execute(
            """
            SELECT ji.id AS job_card_item_id,
                   ji.wip_status,
                   ji.total_days,
                   ji.delivery_date,
                   ji.job_card_qty,
                   ji.so_qty,
                   ji.actual_qty,
                   ji.rejected_qty,
                   ji.hold_qty,
                   COALESCE(ji.pending_qty, 0) AS pending_qty,
                   ji.rejection_reason,
                   ji.hold_reason,
                   ji.remarks,
                   ji.remaining_days,
                   ji.wip_stage_days,
                   jc.job_card_date,
                   jc.final_status AS job_final_status
            FROM job_card_items ji
            JOIN job_cards jc ON jc.job_card_no = ji.job_card_no
            WHERE ji.job_card_no = %s
              AND TRIM(ji.item_name) = TRIM(%s)
            LIMIT 1
            """,
            (job_card_no, item_name),
        )
        item_row = cursor.fetchone()
        if not item_row:
            return jsonify({
                "success": False,
                "error": f"Item not found in job card {job_card_no}"
            }), 404

        available_qty = int(item_row.get("job_card_qty") or 0)

        if available_qty <= 0:
            available_qty = int(item_row.get("so_qty") or 0)

        if outcome_keys_present:
            # OPERATOR_STAGE_QTY_SCOPE_V1
            prev_actual = int(item_row.get("actual_qty") or 0)
            prev_rejected = int(item_row.get("rejected_qty") or 0)
            prev_hold = int(item_row.get("hold_qty") or 0)
            prev_pending = int(item_row.get("pending_qty") or 0)

            current_stage_is_partial = (
                prev_pending > 0 or prev_hold > 0
            )

            if current_stage_is_partial:
                stage_available_qty = (
                    prev_actual
                    + prev_rejected
                    + prev_hold
                    + prev_pending
                )
                base_actual = prev_actual
                base_rejected = prev_rejected
            else:
                prior_outcome_exists = (
                    prev_actual > 0 or prev_rejected > 0
                )

                stage_available_qty = (
                    prev_actual
                    if prior_outcome_exists
                    else available_qty
                )
                base_actual = 0
                base_rejected = 0

            available_qty = stage_available_qty

            if available_qty <= 0:
                return jsonify({
                    "success": False,
                    "error": "No quantity is available for this process."
                }), 400

            outcome_total = ok_qty + rejected_qty + hold_qty

            if outcome_total > available_qty:
                return jsonify({
                    "success": False,
                    "error": (
                        f"Quantity exceeded. OK ({ok_qty}) + "
                        f"Not OK ({rejected_qty}) + Hold ({hold_qty}) "
                        f"cannot exceed Available Qty ({available_qty})."
                    )
                }), 400

            submitted_ok = ok_qty
            submitted_rej = rejected_qty
            submitted_hold = hold_qty

            new_actual = base_actual + ok_qty
            new_rejected = base_rejected + rejected_qty
            new_hold = hold_qty

            accumulated_total = new_actual + new_rejected + new_hold
            pending_qty = available_qty - accumulated_total

            if pending_qty < 0:
                return jsonify({
                    "success": False,
                    "error": (
                        f"Quantity exceeded. This process has "
                        f"Available Qty={available_qty}. "
                        f"Current accumulated OK={base_actual}, "
                        f"Not OK={base_rejected}; adding "
                        f"OK={ok_qty}, Not OK={rejected_qty}, "
                        f"Hold={hold_qty} exceeds the available quantity."
                    )
                }), 400

            ok_qty = new_actual
            rejected_qty = new_rejected
            hold_qty = new_hold

            actual_qty = ok_qty

        old_stage = item_row.get("wip_status") or "Pending"
        if _is_store_stage(old_stage):
            return jsonify({
                "success": False,
                "error": "Item is already in Store. No further movement allowed."
            }), 400

        if role == "supervisor" and not is_gaurang_special_user() and not supervisor_has_process_access(
            cursor, session.get("user_id"), old_stage
        ):
            return jsonify({
                "success": False,
                "error": f"You do not have rights to update process: {old_stage}"
            }), 403

        if (
            role == "supervisor"
            and not is_gaurang_special_user()
            and actual_qty is not None
            and not can_user_edit_field(
                cursor, role, session.get(
                    "user_id"), PAGE3_TRACEABILITY, "actual_qty"
            )
        ):
            return jsonify({
                "success": False,
                "error": "You do not have rights to update actual_qty"
            }), 403

        cursor.execute(
            """
            SELECT jpd.id,
                   jpd.process_name,
                   jpd.in_time,
                   jpd.out_time,
                   COALESCE(jpd.is_completed, 0) AS is_completed,
                   jpd.actual_days,
                   jpd.end_date,
                   COALESCE(jpd.is_subcontract, 0) AS is_subcontract,
                   jpd.vendor_name,
                   COALESCE(pdd.default_days, jpd.days, 0) AS lead_days
            FROM job_card_process_days jpd
            LEFT JOIN process_default_days pdd
              ON LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(pdd.process_name))
            WHERE jpd.job_card_no = %s
              AND jpd.process_name IS NOT NULL
              AND TRIM(jpd.process_name) <> ''
            ORDER BY jpd.id
            """,
            (job_card_no,),
        )
        process_rows = cursor.fetchall()
        if not process_rows:
            return jsonify({
                "success": False,
                "error": "No process timeline found for this job card."
            }), 400

        old_idx = None
        new_idx = None
        for idx, process_row in enumerate(process_rows):
            process_name = process_row.get("process_name") or ""
            if _match_processes(process_name, old_stage):
                old_idx = idx
            if _match_processes(process_name, requested_stage):
                new_idx = idx

        if old_idx is None:
            return jsonify({
                "success": False,
                "error": f"Current stage '{old_stage}' is not defined for this job card."
            }), 400

        # TERMINAL_C_COMPLETION_START
        compact_item_name = "".join(
            str(item_name or "").upper().split()
        )
        is_c_item = compact_item_name.endswith("-C")

        requested_stage_key = (
            str(requested_stage or "").strip().lower()
        )

        is_last_defined_process = (
            old_idx == len(process_rows) - 1
        )

        # Existing -C explicit completion rule.
        is_terminal_c_completion = (
            is_c_item
            and is_last_defined_process
            and requested_stage_key
            in ("completed", "complete")
        )

        # MISSING_STORE_TERMINAL_FALLBACK_V1
        # If Store does not exist in the process array, but the
        # current process is already the final defined process,
        # moving to Store is treated as a valid terminal movement.
        #
        # This protects:
        #   1. -C JCs where Store is intentionally not defined.
        #   2. Any JC where Store was accidentally deleted.
        is_missing_store_terminal_completion = (
            requested_stage_key == "store"
            and new_idx is None
            and is_last_defined_process
        )

        is_terminal_without_next_process = (
            is_terminal_c_completion
            or is_missing_store_terminal_completion
        )

        if not is_terminal_without_next_process:
            if new_idx is None:
                return jsonify({
                    "success": False,
                    "error": f"Process '{requested_stage}' is not defined for this job card."
                }), 400

            if new_idx != old_idx + 1:
                return jsonify({
                    "success": False,
                    "error": (
                        f"Stage skip not allowed. Complete '{process_rows[old_idx]['process_name']}' "
                        f"before moving to '{requested_stage}'."
                    )
                }), 400

        old_process = process_rows[old_idx]

        new_process = (
            None
            if is_terminal_without_next_process
            else process_rows[new_idx]
        )

        if is_missing_store_terminal_completion:
            # Store is the terminal WIP/status even though there is
            # intentionally no Store process-day row.
            new_stage = "Store"
        elif is_terminal_c_completion:
            new_stage = "Completed"
        else:
            new_stage = new_process["process_name"]

        # TERMINAL_C_COMPLETION_END

        # OEE_COMPLETION_INTEGRATION_V1
        # Canonical machine/loss values are resolved server-side.
        # AR/PR category snapshots remain NULL until Production confirms
        # the genuine workbook grouping conflict.
        # OEE_PROCESS_PREFIX_SUPPORT_V1
        normalized_oee_process = (
            (old_stage or "").strip().lower()
        )
        oee_required = (
            role == "operator"
            and (
                normalized_oee_process.startswith("cnc machining")
                or normalized_oee_process.startswith("vmc machining")
            )
        )
        oee_payload = None
        oee_machine = None
        oee_resolved_losses = []
        oee_result = None

        if oee_required:
            oee_payload = data.get("oee")

            if not isinstance(oee_payload, dict):
                return jsonify({
                    "success": False,
                    "error": (
                        "OEE details are required before completing "
                        f"'{old_stage}'."
                    ),
                }), 400

            try:
                oee_machine_id = int(oee_payload.get("machine_id"))
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "Please select a valid OEE Machine.",
                }), 400

            if oee_machine_id <= 0:
                return jsonify({
                    "success": False,
                    "error": "Please select a valid OEE Machine.",
                }), 400

            cursor.execute(
                """
                SELECT
                    id,
                    machine_no,
                    machine_name,
                    machine_category,
                    zone
                FROM oee_machines
                WHERE id = %s
                  AND is_active = 1
                LIMIT 1
                """,
                (oee_machine_id,),
            )
            oee_machine = cursor.fetchone()

            if not oee_machine:
                return jsonify({
                    "success": False,
                    "error": (
                        "Selected OEE Machine is not active "
                        "or does not exist."
                    ),
                }), 400

            expected_machine_category = (
                "CNC"
                if normalized_oee_process.startswith("cnc machining")
                else "VMC"
            )

            if (
                str(oee_machine.get("machine_category") or "")
                .strip()
                .upper()
                != expected_machine_category
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        f"{old_stage} requires an "
                        f"{expected_machine_category} machine."
                    ),
                }), 400

            submitted_losses = oee_payload.get("losses")

            if not isinstance(submitted_losses, list):
                return jsonify({
                    "success": False,
                    "error": "OEE loss details A1-A27 are required.",
                }), 400

            submitted_loss_map = {}

            for submitted_loss in submitted_losses:
                if not isinstance(submitted_loss, dict):
                    return jsonify({
                        "success": False,
                        "error": "Every OEE loss row must be valid.",
                    }), 400

                loss_code = str(
                    submitted_loss.get("loss_code") or ""
                ).strip().upper()

                if not loss_code:
                    return jsonify({
                        "success": False,
                        "error": "OEE Loss Code is required.",
                    }), 400

                if loss_code in submitted_loss_map:
                    return jsonify({
                        "success": False,
                        "error": f"Duplicate OEE loss code: {loss_code}",
                    }), 400

                try:
                    loss_minutes = float(
                        submitted_loss.get("loss_minutes", 0) or 0
                    )
                except (TypeError, ValueError):
                    return jsonify({
                        "success": False,
                        "error": (
                            f"{loss_code} loss minutes must be numeric."
                        ),
                    }), 400

                if loss_minutes < 0:
                    return jsonify({
                        "success": False,
                        "error": (
                            f"{loss_code} loss minutes cannot be negative."
                        ),
                    }), 400

                submitted_loss_map[loss_code] = loss_minutes

            cursor.execute(
                """
                SELECT
                    id,
                    loss_code,
                    loss_name
                FROM oee_loss_types
                WHERE is_active = 1
                ORDER BY display_order, id
                """
            )
            oee_loss_master_rows = cursor.fetchall()

            expected_loss_codes = [
                f"A{index}" for index in range(1, 28)
            ]

            oee_loss_master = {
                str(row.get("loss_code") or "").strip().upper(): row
                for row in oee_loss_master_rows
                if str(row.get("loss_code") or "").strip()
            }

            if set(oee_loss_master) != set(expected_loss_codes):
                return jsonify({
                    "success": False,
                    "error": (
                        "Active OEE loss master must contain "
                        "exactly A1-A27 before completion."
                    ),
                }), 400

            submitted_codes = set(submitted_loss_map)
            expected_codes = set(expected_loss_codes)

            if submitted_codes != expected_codes:
                missing_codes = sorted(expected_codes - submitted_codes)
                extra_codes = sorted(submitted_codes - expected_codes)
                details = []

                if missing_codes:
                    details.append("missing " + ", ".join(missing_codes))

                if extra_codes:
                    details.append("unknown " + ", ".join(extra_codes))

                return jsonify({
                    "success": False,
                    "error": (
                        "OEE loss details must contain exactly A1-A27"
                        + (
                            " (" + "; ".join(details) + ")"
                            if details
                            else ""
                        )
                        + "."
                    ),
                }), 400

            oee_resolved_losses = []

            for loss_code in expected_loss_codes:
                master_row = oee_loss_master[loss_code]
                oee_resolved_losses.append({
                    "loss_type_id": master_row["id"],
                    "loss_code": loss_code,
                    "loss_name": master_row["loss_name"],
                    "loss_minutes": submitted_loss_map[loss_code],
                })

        operator_completion_log_id = None

        if role == "operator":
            operator_user_id = session.get("user_id")

            if not operator_user_id:
                return jsonify({
                    "success": False,
                    "error": "Operator session is missing the user ID."
                }), 403

            _ensure_operator_completion_log_table(cursor)

            next_snapshot = new_process or {}

            snapshot_values = (
                operator_user_id,
                changed_by,
                job_card_no,
                item_name,
                old_stage,
                new_stage,
                old_process["id"],
                next_snapshot.get("id"),

                item_row.get("wip_status"),
                item_row.get("actual_qty"),
                item_row.get("rejected_qty"),
                item_row.get("hold_qty"),
                item_row.get("rejection_reason"),
                item_row.get("hold_reason"),
                item_row.get("remarks"),
                item_row.get("remaining_days"),
                item_row.get("wip_stage_days"),
                item_row.get("job_final_status"),

                old_process.get("in_time"),
                old_process.get("out_time"),
                old_process.get("is_completed"),
                old_process.get("actual_days"),
                old_process.get("end_date"),
                old_process.get("is_subcontract"),
                old_process.get("vendor_name"),

                next_snapshot.get("in_time"),
                next_snapshot.get("out_time"),
                next_snapshot.get("is_completed"),
                next_snapshot.get("actual_days"),
                next_snapshot.get("end_date"),
                next_snapshot.get("is_subcontract"),
                next_snapshot.get("vendor_name"),

                submitted_ok if outcome_keys_present else actual_qty,
                submitted_rej if outcome_keys_present else rejected_qty,
                submitted_hold if outcome_keys_present else hold_qty,
                rejection_reason,
                hold_reason,
                stage_remark,
            )

            placeholders = ",".join(
                ["%s"] * len(snapshot_values)
            )

            cursor.execute(
                f"""
                INSERT INTO operator_completion_log (
                    operator_user_id,
                    operator_name,
                    job_card_no,
                    item_name,
                    old_stage,
                    new_stage,
                    old_process_id,
                    next_process_id,

                    previous_item_wip_status,
                    previous_item_actual_qty,
                    previous_item_rejected_qty,
                    previous_item_hold_qty,
                    previous_item_rejection_reason,
                    previous_item_hold_reason,
                    previous_item_remarks,
                    previous_item_remaining_days,
                    previous_item_wip_stage_days,
                    previous_job_final_status,

                    old_process_in_time,
                    old_process_out_time,
                    old_process_is_completed,
                    old_process_actual_days,
                    old_process_end_date,
                    old_process_is_subcontract,
                    old_process_vendor_name,

                    next_process_in_time,
                    next_process_out_time,
                    next_process_is_completed,
                    next_process_actual_days,
                    next_process_end_date,
                    next_process_is_subcontract,
                    next_process_vendor_name,

                    submitted_ok_qty,
                    submitted_rejected_qty,
                    submitted_hold_qty,
                    submitted_rejection_reason,
                    submitted_hold_reason,
                    submitted_stage_remark
                )
                VALUES ({placeholders})
                """,
                snapshot_values,
            )

            operator_completion_log_id = cursor.lastrowid

        stage_days = int(old_process.get("lead_days") or 0)
        new_remaining = _remaining_days_from_delivery(
            item_row.get("delivery_date"))

        # CHILD_C_GATE_BLOCK_START
        # Upper-level process cannot move/start until all child -C job cards
        # are completed, unless an authorised Continue Anyway override exists.
        pending_c_rows = _get_pending_c_child_gate_rows(
            cursor,
            job_card_no,
            item_name
        )

        child_c_gate_overridden = _child_c_gate_override_exists(
            cursor,
            job_card_no,
            item_name
        )

        if pending_c_rows and not child_c_gate_overridden:
            first_block = pending_c_rows[0]
            child_jc = first_block.get("c_job_card_no") or "NOT FOUND"
            child_item = first_block.get("c_item_description") or "-"
            child_wip = first_block.get("c_wip_status") or "-"
            gate_status = first_block.get("gate_status") or "CHILD -C BLOCKED"

            return jsonify({
                "success": False,
                "status": "CHILD_C_GATE_BLOCKED",
                "error": (
                    "Cannot start / move upper-level process. "
                    f"Child -C item is not completed. "
                    f"Child JC: {child_jc}, "
                    f"Child Item: {child_item}, "
                    f"Child WIP: {child_wip}, "
                    f"Status: {gate_status}"
                ),
                "gate_status": gate_status,
                "blocking_count": len(pending_c_rows),
                "blocking_rows": pending_c_rows,
                "continue_anyway_allowed": True
            }), 400
        # CHILD_C_GATE_BLOCK_END

        if old_process.get("in_time") is None:
            cursor.execute(
                """
                UPDATE job_card_process_days
                SET in_time = COALESCE(%s, NOW())
                WHERE id = %s
                """,
                (item_row.get("job_card_date"), old_process["id"]),
            )

        cursor.execute(
            """
            UPDATE job_card_process_days
            SET out_time = NOW(),
                is_completed = 1,
                end_date = CURDATE(),
                actual_days = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
            WHERE id = %s
            """,
            (old_process["id"],),
        )

        # A terminal -C completion has no next process row.
        if not is_terminal_c_completion:
            if _is_store_stage(new_stage):
                cursor.execute(
                    """
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, NOW()),
                        out_time = COALESCE(out_time, NOW()),
                        is_completed = 1,
                        end_date = CURDATE(),
                        actual_days = COALESCE(actual_days, 0)
                    WHERE id = %s
                    """,
                    (new_process["id"],),
                )
            else:
                cursor.execute(
                    """
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, NOW()),
                        out_time = NULL,
                        is_completed = 0,
                        actual_days = NULL,
                        end_date = NULL
                    WHERE id = %s
                    """,
                    (new_process["id"],),
                )

        # If partial submission, stay on current process instead of advancing.
        if outcome_keys_present and (pending_qty > 0 or hold_qty > 0):
            effective_stage = old_stage
        else:
            effective_stage = new_stage

        cursor.execute(
            """
            UPDATE job_card_items
            SET wip_status = %s,
                remaining_days = %s,
                wip_stage_days = 0,
                actual_qty = COALESCE(%s, actual_qty),
                rejected_qty = CASE
                    WHEN %s IS NULL THEN rejected_qty
                    ELSE %s
                END,
                hold_qty = CASE
                    WHEN %s IS NULL THEN hold_qty
                    ELSE %s
                END,
                pending_qty = CASE
                    WHEN %s IS NULL THEN pending_qty
                    ELSE %s
                END,
                rejection_reason = CASE
                    WHEN %s IS NULL THEN rejection_reason
                    ELSE %s
                END,
                hold_reason = CASE
                    WHEN %s IS NULL THEN hold_reason
                    ELSE %s
                END,
                remarks = CASE
                    WHEN %s = '' THEN remarks
                    ELSE %s
                END,
                rm_hold_reason = CASE
                    WHEN %s IS NULL THEN rm_hold_reason
                    ELSE %s
                END
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
            """,
            (
                effective_stage,
                new_remaining,
                actual_qty,
                rejected_qty,
                rejected_qty,
                hold_qty,
                hold_qty,
                pending_qty if outcome_keys_present else None,
                pending_qty if outcome_keys_present else None,
                rejection_reason
                if outcome_keys_present else None,
                rejection_reason,
                hold_reason
                if outcome_keys_present else None,
                hold_reason,
                stage_remark,
                stage_remark,
                rm_hold_reason,
                rm_hold_reason,
                job_card_no,
                item_name,
            ),
        )

        # Undo the process_days advancement if partial submission.
        # Fix completion log: store effective_stage, not requested stage
        if operator_completion_log_id is not None and effective_stage != new_stage:
            cursor.execute(
                """
                UPDATE operator_completion_log
                SET new_stage = %s
                WHERE id = %s
                """,
                (effective_stage, operator_completion_log_id),
            )

        if outcome_keys_present and (pending_qty > 0 or hold_qty > 0):
            # Revert old process — mark it back as not completed.
            cursor.execute(
                """
                UPDATE job_card_process_days
                SET out_time = NULL,
                    is_completed = 0,
                    end_date = NULL,
                    actual_days = NULL
                WHERE id = %s
                """,
                (old_process["id"],),
            )
            # Revert next process in_time if it was set.
            if not is_terminal_c_completion and new_process:
                cursor.execute(
                    """
                    UPDATE job_card_process_days
                    SET in_time = NULL,
                        is_completed = 0
                    WHERE id = %s
                    """,
                    (new_process["id"],),
                )

        cursor.execute("""
            SELECT
                COUNT(*) AS total_items,
                SUM(
                    CASE
                        WHEN LOWER(TRIM(wip_status)) IN ('completed', 'store')
                        THEN 1 ELSE 0
                    END
                ) AS completed_items,
                SUM(
                    CASE
                        WHEN COALESCE(pending_qty, 0) > 0
                          OR COALESCE(hold_qty, 0) > 0
                        THEN 1 ELSE 0
                    END
                ) AS partial_items
            FROM job_card_items
            WHERE job_card_no = %s
        """, (job_card_no,))
        status_row = cursor.fetchone()

        total = int(status_row["total_items"] or 0)
        completed = int(status_row["completed_items"] or 0)
        partial = int(status_row["partial_items"] or 0)

        if total > 0 and total == completed:
            new_final_status = 'Completed'
        elif partial > 0:
            new_final_status = 'Partial'
        else:
            new_final_status = 'Pending'

        cursor.execute("""
            UPDATE job_cards
            SET final_status = %s
            WHERE job_card_no = %s
        """, (new_final_status, job_card_no,))

        cursor.execute(
            """
            INSERT INTO audit_trail
            (job_card_no, item_name, old_stage, new_stage, changed_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (job_card_no, item_name, old_stage, new_stage, changed_by),
        )

        completion_audit_id = cursor.lastrowid

        if operator_completion_log_id is not None:
            cursor.execute(
                """
                UPDATE operator_completion_log
                SET completion_audit_id = %s,
                    status = 'active'
                WHERE id = %s
                  AND operator_user_id = %s
                """,
                (
                    completion_audit_id,
                    operator_completion_log_id,
                    session.get("user_id"),
                ),
            )

        if oee_required:
            if operator_completion_log_id is None:
                raise RuntimeError(
                    "OEE completion link was not created."
                )

            try:
                oee_result = save_oee_entry(
                    cursor,
                    operator_completion_id=operator_completion_log_id,
                    job_card_item_id=item_row.get("job_card_item_id"),
                    process_day_id=old_process.get("id"),
                    machine=oee_machine,
                    operator_user_id=session.get("user_id"),
                    operator_name=(
                        session.get("full_name")
                        or session.get("username")
                        or changed_by
                        or "Operator"
                    ),
                    entry_date=oee_payload.get("entry_date"),
                    shift_name=oee_payload.get("shift_name"),
                    job_card_no=job_card_no,
                    item_name=item_name,
                    process_name=old_stage,
                    start_time=oee_payload.get("start_time"),
                    end_time=oee_payload.get("end_time"),
                    cycle_minutes=oee_payload.get("cycle_minutes"),
                    cycle_seconds=oee_payload.get("cycle_seconds"),
                    load_unload_minutes=oee_payload.get(
                        "load_unload_minutes"
                    ),
                    load_unload_seconds=oee_payload.get(
                        "load_unload_seconds"
                    ),
                    ok_qty=submitted_ok,
                    rejected_qty=submitted_rej,
                    hold_qty=submitted_hold,
                    losses=oee_resolved_losses,
                    remarks=stage_remark,
                )
            except ValueError as oee_error:
                conn.rollback()
                return jsonify({
                    "success": False,
                    "error": str(oee_error),
                }), 400

        # AUTO_CUTTING_PLAN_LIVE_WIP_HOOK_V1
        #
        # Create/reuse AUTO Cutting Plan ONLY when the item
        # genuinely advances:
        #
        # Raw Material -> Cutting
        #
        # Partial RM submissions remain on Raw Material because
        # effective_stage == old_stage, therefore they do not trigger.
        #
        # SAVEPOINT protects normal Job Card movement:
        # a Cutting Plan failure rolls back only this hook.

        cutting_plan_result = None
        cutting_plan_warning = None

        is_raw_material_to_cutting = (
            (old_stage or "").strip().lower() == "raw material"
            and
            (effective_stage or "").strip().lower() == "cutting"
            and
            (effective_stage or "").strip().lower()
            != (old_stage or "").strip().lower()
        )

        if is_raw_material_to_cutting:

            cutting_savepoint_started = False

            try:
                cursor.execute(
                    "SAVEPOINT auto_cutting_plan_hook"
                )

                cutting_savepoint_started = True

                # Local import avoids changing module startup /
                # Blueprint import behaviour.
                from .cutting_plan import (
                    _create_or_reuse_auto_plan,
                    _resolve_auto_source,
                )

                source, source_error = _resolve_auto_source(
                    cursor,
                    job_card_no,
                    item_id=item_row.get(
                        "job_card_item_id"
                    ),
                    item_name=item_name,
                )

                if source_error:
                    raise RuntimeError(source_error)

                cutting_actor = {
                    "user_id": session.get("user_id"),
                    "name": changed_by or "System",
                }

                cutting_plan_id, cutting_created = (
                    _create_or_reuse_auto_plan(
                        cursor,
                        source,
                        cutting_actor,
                    )
                )

                cutting_plan_result = {
                    "plan_id": cutting_plan_id,
                    "created": bool(cutting_created),
                    "source_job_card_no": job_card_no,
                    "source_item_id": item_row.get(
                        "job_card_item_id"
                    ),
                    "trigger": "Raw Material -> Cutting",
                }

                cursor.execute(
                    "RELEASE SAVEPOINT auto_cutting_plan_hook"
                )

                cutting_savepoint_started = False

            except Exception as cutting_error:

                if cutting_savepoint_started:
                    try:
                        cursor.execute(
                            "ROLLBACK TO SAVEPOINT "
                            "auto_cutting_plan_hook"
                        )

                        cursor.execute(
                            "RELEASE SAVEPOINT "
                            "auto_cutting_plan_hook"
                        )

                    except Exception:
                        pass

                cutting_plan_result = None

                cutting_plan_warning = str(
                    cutting_error
                )

        conn.commit()

        return jsonify({
            "success": True,
            "message": f"WIP updated from '{old_stage}' to '{effective_stage}'" if (pending_qty == 0 and int(hold_qty or 0) == 0) else f"Partial entry saved. {pending_qty} pending + {int(hold_qty or 0)} on hold on '{old_stage}'.",
            "old_stage": old_stage,
            "new_stage": effective_stage,
            "stage_days": stage_days,
            "process_found": True,
            "remaining_days": new_remaining,
            "total_days": item_row.get("total_days") or 0,
            "available_qty": available_qty,
            "ok_qty": ok_qty if outcome_keys_present else actual_qty,
            "submitted_ok": submitted_ok if outcome_keys_present else actual_qty,
            "submitted_rejected": submitted_rej if outcome_keys_present else rejected_qty,
            "submitted_hold": submitted_hold if outcome_keys_present else hold_qty,
            "rejected_qty": rejected_qty,
            "hold_qty": hold_qty,
            "pending_qty": pending_qty if outcome_keys_present else 0,
            "is_partial": (pending_qty > 0 or hold_qty > 0) if outcome_keys_present else False,
            "rejection_reason": rejection_reason,
            "hold_reason": hold_reason,
            "rm_hold_reason": rm_hold_reason,
            "operator_completion_id": operator_completion_log_id,
            "cutting_plan": cutting_plan_result,
            "cutting_plan_warning": cutting_plan_warning,
            "oee_entry_id": (
                oee_result.get("oee_entry_id")
                if oee_result
                else None
            ),
        })

    except Error as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@quality_check_bp.route(
    "/api/quality_check/child_c_gate/continue_anyway",
    methods=["POST"]
)
def continue_anyway_child_c_gate():
    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()

        if role not in ("admin", "supervisor") and not is_gaurang_special_user():
            return jsonify({
                "success": False,
                "error": "Admin or Supervisor access is required."
            }), 403

        data = request.json or {}

        job_card_no = str(
            data.get("job_card_no") or ""
        ).strip()

        item_name = str(
            data.get("item_name") or ""
        ).strip()

        override_reason = str(
            data.get("override_reason") or
            "User selected Continue Anyway."
        ).strip()

        if not job_card_no or not item_name:
            return jsonify({
                "success": False,
                "error": "Job Card number and item name are required."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        actual_job_card_no = _resolve_job_card_no(
            cursor,
            job_card_no
        )

        if not actual_job_card_no:
            return jsonify({
                "success": False,
                "error": f"Job Card not found: {job_card_no}"
            }), 404

        cursor.execute("""
            SELECT id
            FROM job_card_items
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
            LIMIT 1
        """, (
            actual_job_card_no,
            item_name,
        ))

        if not cursor.fetchone():
            return jsonify({
                "success": False,
                "error": "The selected item was not found in this Job Card."
            }), 404

        pending_rows = _get_pending_c_child_gate_rows(
            cursor,
            actual_job_card_no,
            item_name
        )

        if not pending_rows:
            return jsonify({
                "success": False,
                "status": "CHILD_C_GATE_NOT_BLOCKED",
                "error": (
                    "This Job Card item is not currently blocked "
                    "by a child -C gate."
                )
            }), 400

        _ensure_child_c_gate_override_table(cursor)

        item_name_norm = " ".join(
            item_name.lower().split()
        )

        overridden_by = (
            session.get("username")
            or session.get("full_name")
            or "System"
        )

        overridden_user_id = session.get("user_id")

        cursor.execute("""
            INSERT INTO child_c_gate_overrides (
                job_card_no,
                item_name,
                item_name_norm,
                override_reason,
                overridden_by,
                overridden_user_id,
                overridden_at,
                is_active
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, NOW(), 1
            )
            ON DUPLICATE KEY UPDATE
                item_name = VALUES(item_name),
                override_reason = VALUES(override_reason),
                overridden_by = VALUES(overridden_by),
                overridden_user_id = VALUES(overridden_user_id),
                overridden_at = NOW(),
                is_active = 1
        """, (
            actual_job_card_no,
            item_name,
            item_name_norm,
            override_reason,
            overridden_by,
            overridden_user_id,
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "status": "CHILD_C_GATE_OVERRIDE_SAVED",
            "message": (
                "Continue Anyway approval was saved for this "
                "Job Card item."
            ),
            "job_card_no": actual_job_card_no,
            "item_name": item_name,
            "blocking_count": len(pending_rows)
        })

    except Exception as e:
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


@quality_check_bp.route("/api/wip/update", methods=["POST"])
def update_wip():
    return _update_wip_from_saved_timeline()


@quality_check_bp.route(
    "/api/operator/recent_completions",
    methods=["GET"]
)
def operator_recent_completions():
    """
    Database-backed recent completions for the logged-in Operator only.
    """
    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()
        operator_user_id = session.get("user_id")

        if role != "operator":
            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403

        if not operator_user_id:
            return jsonify({
                "success": False,
                "error": "Operator session is missing the user ID."
            }), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        _ensure_operator_completion_log_table(cursor)
        conn.commit()

        cursor.execute(
            """
            SELECT
                ocl.id,
                ocl.job_card_no,
                ocl.item_name,
                ocl.old_stage AS completed_process,
                ocl.new_stage AS moved_to,
                COALESCE(ji.actual_qty, ocl.submitted_ok_qty) AS ok_qty,
                COALESCE(ji.rejected_qty, ocl.submitted_rejected_qty) AS rejected_qty,
                COALESCE(ji.hold_qty, ocl.submitted_hold_qty) AS hold_qty,
                ocl.submitted_rejection_reason AS rejection_reason,
                ocl.submitted_hold_reason AS hold_reason,
                ocl.submitted_stage_remark AS stage_remark,
                ocl.completed_at
            FROM operator_completion_log ocl
            LEFT JOIN job_card_items ji
              ON (ji.job_card_no COLLATE utf8mb4_unicode_ci) = (ocl.job_card_no COLLATE utf8mb4_unicode_ci)
              AND (TRIM(ji.item_name) COLLATE utf8mb4_unicode_ci) = (TRIM(ocl.item_name) COLLATE utf8mb4_unicode_ci)
            WHERE ocl.operator_user_id = %s
AND ocl.status = 'active'
AND ocl.old_stage != ocl.new_stage

AND NOT EXISTS (
    SELECT 1
    FROM operator_completion_log newer
    WHERE newer.operator_user_id = ocl.operator_user_id
    AND newer.status = 'active'
    AND newer.old_stage != newer.new_stage

    AND (
        newer.job_card_no
        COLLATE utf8mb4_unicode_ci
    ) = (
        ocl.job_card_no
        COLLATE utf8mb4_unicode_ci
    )

    AND (
        TRIM(newer.item_name)
        COLLATE utf8mb4_unicode_ci
    ) = (
        TRIM(ocl.item_name)
        COLLATE utf8mb4_unicode_ci
    )

    AND newer.id > ocl.id
)

ORDER BY ocl.id DESC
LIMIT 10
            """,
            (operator_user_id,),
        )

        rows = cursor.fetchall()

        for row in rows:
            row["can_undo"] = True
            row["undo_validation"] = "server_checked"

            if (
                row.get("completed_at")
                and hasattr(row["completed_at"], "strftime")
            ):
                row["completed_at"] = row[
                    "completed_at"
                ].strftime("%Y-%m-%d %H:%M:%S")

        return jsonify({
            "success": True,
            "completed_job_cards": rows,
            "completions": rows,
            "total": len(rows),
        })

    except Exception as error:
        return jsonify({
            "success": False,
            "error": str(error),
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


@quality_check_bp.route(
    "/api/operator/undo_completion",
    methods=["POST"]
)
def operator_undo_completion():
    """
    Reverses only the logged-in Operator's latest valid completion.

    It does not use or modify the Admin/Supervisor rollback route.
    """
    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()
        operator_user_id = session.get("user_id")
        operator_name = (
            session.get("full_name")
            or session.get("username")
            or "Operator"
        )

        if role != "operator":
            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403

        if not operator_user_id:
            return jsonify({
                "success": False,
                "error": "Operator session is missing the user ID."
            }), 403

        data = request.json or {}

        try:
            completion_id = int(data.get("completion_id"))
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "error": "A valid completion ID is required."
            }), 400

        undo_reason = (
            data.get("undo_reason")
            or ""
        ).strip()

        if not undo_reason:
            return jsonify({
                "success": False,
                "error": "Undo reason is required."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        _ensure_operator_completion_log_table(cursor)
        conn.commit()
        conn.start_transaction()

        # Undo is validated per job card and item.
        # A later completion on another job card does not block this Undo.
        cursor.execute(
            """
            SELECT *
            FROM operator_completion_log
            WHERE id = %s
              AND operator_user_id = %s
              AND status = 'active'
            LIMIT 1
            FOR UPDATE
            """,
            (
                completion_id,
                operator_user_id,
            ),
        )

        log_row = cursor.fetchone()

        if not log_row:
            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "This completion is no longer available "
                    "for Undo."
                )
            }), 404

        job_card_no = log_row["job_card_no"]
        item_name = log_row["item_name"]
        old_stage = log_row["old_stage"]
        new_stage = log_row["new_stage"]

        cursor.execute(
            """
            SELECT 1
            FROM supervisor_process_access
            WHERE user_id = %s
              AND LOWER(TRIM(process_name))
                  = LOWER(TRIM(%s))
            LIMIT 1
            """,
            (
                operator_user_id,
                old_stage,
            ),
        )

        if not cursor.fetchone():
            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "You are no longer assigned to the "
                    f"process '{old_stage}'."
                )
            }), 403

        cursor.execute(
            """
            SELECT
                jci.wip_status,
                jc.final_status,
                jc.so_no,
                jc.child_code
            FROM job_card_items jci
            JOIN job_cards jc
              ON jc.job_card_no = jci.job_card_no
            WHERE jci.job_card_no = %s
              AND TRIM(jci.item_name) = TRIM(%s)
            LIMIT 1
            FOR UPDATE
            """,
            (
                job_card_no,
                item_name,
            ),
        )

        current_item = cursor.fetchone()

        if not current_item:
            conn.rollback()

            return jsonify({
                "success": False,
                "error": "Job-card item was not found."
            }), 404

        if (
            str(current_item.get("wip_status") or "")
            .strip()
            .lower()
            != str(new_stage or "").strip().lower()
        ):
            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Undo is blocked because the job card "
                    "has already moved again."
                )
            }), 409

        cursor.execute(
            """
            SELECT id
            FROM audit_trail
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                job_card_no,
                item_name,
            ),
        )

        latest_audit = cursor.fetchone()

        if (
            not latest_audit
            or int(latest_audit["id"])
            != int(log_row["completion_audit_id"] or 0)
        ):
            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Undo is blocked because another user or "
                    "process has modified this job card."
                )
            }), 409

        # Extra dependency protection for a terminal -C completion.
        # Block Undo when a related upper-level job card has moved
        # after this child completion.
        if str(new_stage or "").strip().lower() == "completed":
            child_code = (
                current_item.get("child_code")
                or ""
            ).strip()

            if not child_code:
                conn.rollback()

                return jsonify({
                    "success": False,
                    "error": (
                        "This final -C completion requires "
                        "Supervisor reversal because its item "
                        "code cannot be verified safely."
                    )
                }), 409

            cursor.execute(
                """
                WITH RECURSIVE ancestors AS (
                    SELECT bl.parent_code
                    FROM bom_links bl
                    WHERE bl.child_code = %s

                    UNION

                    SELECT bl.parent_code
                    FROM bom_links bl
                    JOIN ancestors a
                      ON bl.child_code = a.parent_code
                )
                SELECT
                    at.job_card_no,
                    at.old_stage,
                    at.new_stage,
                    at.changed_at
                FROM job_cards upper_jc
                JOIN audit_trail at
                  ON at.job_card_no = upper_jc.job_card_no
                WHERE COALESCE(
                          NULLIF(TRIM(upper_jc.so_no), ''),
                          '__BLANK_SO__'
                      )
                      =
                      COALESCE(
                          NULLIF(TRIM(%s), ''),
                          '__BLANK_SO__'
                      )
                  AND upper_jc.child_code IN (
                      SELECT parent_code
                      FROM ancestors
                  )
                  AND at.changed_at > %s
                ORDER BY at.changed_at DESC
                LIMIT 1
                """,
                (
                    child_code,
                    current_item.get("so_no"),
                    log_row["completed_at"],
                ),
            )

            upper_activity = cursor.fetchone()

            if upper_activity:
                conn.rollback()

                return jsonify({
                    "success": False,
                    "error": (
                        "Undo is blocked because a related "
                        "upper-level job card has already moved "
                        "after this -C completion. Contact the "
                        "Supervisor."
                    ),
                    "upper_job_card_no": (
                        upper_activity.get("job_card_no")
                    ),
                }), 409

        cursor.execute(
            """
            SELECT
                id,
                in_time,
                out_time,
                COALESCE(is_completed, 0) AS is_completed,
                actual_days,
                end_date
            FROM job_card_process_days
            WHERE id = %s
              AND job_card_no = %s
            LIMIT 1
            FOR UPDATE
            """,
            (
                log_row["old_process_id"],
                job_card_no,
            ),
        )

        current_old_process = cursor.fetchone()

        if (
            not current_old_process
            or int(
                current_old_process.get("is_completed") or 0
            ) != 1
            or current_old_process.get("out_time") is None
        ):
            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Undo is blocked because the completed "
                    "process state has changed."
                )
            }), 409

        if log_row.get("next_process_id") is not None:
            cursor.execute(
                """
                SELECT
                    id,
                    in_time,
                    out_time,
                    COALESCE(is_completed, 0) AS is_completed,
                    actual_days,
                    end_date
                FROM job_card_process_days
                WHERE id = %s
                  AND job_card_no = %s
                LIMIT 1
                FOR UPDATE
                """,
                (
                    log_row["next_process_id"],
                    job_card_no,
                ),
            )

            current_next_process = cursor.fetchone()

            if not current_next_process:
                conn.rollback()

                return jsonify({
                    "success": False,
                    "error": (
                        "Undo is blocked because the next "
                        "process row no longer exists."
                    )
                }), 409

            is_store_move = (
                str(new_stage or "").strip().lower()
                == "store"
            )

            if is_store_move:
                next_state_valid = (
                    int(
                        current_next_process.get(
                            "is_completed"
                        ) or 0
                    ) == 1
                    and current_next_process.get(
                        "out_time"
                    ) is not None
                )
            else:
                next_state_valid = (
                    int(
                        current_next_process.get(
                            "is_completed"
                        ) or 0
                    ) == 0
                    and current_next_process.get(
                        "in_time"
                    ) is not None
                    and current_next_process.get(
                        "out_time"
                    ) is None
                )

            if not next_state_valid:
                conn.rollback()

                return jsonify({
                    "success": False,
                    "error": (
                        "Undo is blocked because the next "
                        "process has already started or changed."
                    )
                }), 409

        # Restore the process that was incorrectly completed.
        cursor.execute(
            """
            UPDATE job_card_process_days
            SET in_time = %s,
                out_time = %s,
                is_completed = %s,
                actual_days = %s,
                end_date = %s,
                is_subcontract = %s,
                vendor_name = %s
            WHERE id = %s
              AND job_card_no = %s
            """,
            (
                log_row.get("old_process_in_time"),
                log_row.get("old_process_out_time"),
                log_row.get(
                    "old_process_is_completed"
                ),
                log_row.get("old_process_actual_days"),
                log_row.get("old_process_end_date"),
                log_row.get(
                    "old_process_is_subcontract"
                ),
                log_row.get("old_process_vendor_name"),
                log_row["old_process_id"],
                job_card_no,
            ),
        )

        # Restore the automatically opened/completed next row.
        if log_row.get("next_process_id") is not None:
            cursor.execute(
                """
                UPDATE job_card_process_days
                SET in_time = %s,
                    out_time = %s,
                    is_completed = %s,
                    actual_days = %s,
                    end_date = %s,
                    is_subcontract = %s,
                    vendor_name = %s
                WHERE id = %s
                  AND job_card_no = %s
                """,
                (
                    log_row.get("next_process_in_time"),
                    log_row.get("next_process_out_time"),
                    log_row.get(
                        "next_process_is_completed"
                    ),
                    log_row.get(
                        "next_process_actual_days"
                    ),
                    log_row.get("next_process_end_date"),
                    log_row.get(
                        "next_process_is_subcontract"
                    ),
                    log_row.get(
                        "next_process_vendor_name"
                    ),
                    log_row["next_process_id"],
                    job_card_no,
                ),
            )

        # Restore the exact item values from before completion.
        cursor.execute(
            """
            UPDATE job_card_items
            SET wip_status = %s,
                actual_qty = %s,
                rejected_qty = %s,
                hold_qty = %s,
                rejection_reason = %s,
                hold_reason = %s,
                remarks = %s,
                remaining_days = %s,
                wip_stage_days = %s
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
            """,
            (
                log_row.get(
                    "previous_item_wip_status"
                ),
                log_row.get(
                    "previous_item_actual_qty"
                ),
                log_row.get(
                    "previous_item_rejected_qty"
                ),
                log_row.get(
                    "previous_item_hold_qty"
                ),
                log_row.get(
                    "previous_item_rejection_reason"
                ),
                log_row.get(
                    "previous_item_hold_reason"
                ),
                log_row.get(
                    "previous_item_remarks"
                ),
                log_row.get(
                    "previous_item_remaining_days"
                ),
                log_row.get(
                    "previous_item_wip_stage_days"
                ),
                job_card_no,
                item_name,
            ),
        )

        cursor.execute(
            """
            UPDATE job_cards
            SET final_status = %s
            WHERE job_card_no = %s
            """,
            (
                log_row.get(
                    "previous_job_final_status"
                ) or "Pending",
                job_card_no,
            ),
        )

        # Cascade: also undo all active partial entries for same JC+item.
        # Partial entries have old_stage == new_stage (process didn't advance).
        # Find the earliest partial entry to get the true original state.
        cursor.execute(
            """
            SELECT id, previous_item_actual_qty, previous_item_rejected_qty,
                   previous_item_hold_qty, previous_item_remarks,
                   previous_item_remaining_days, previous_item_wip_stage_days
            FROM operator_completion_log
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
              AND operator_user_id = %s
              AND status = 'active'
              AND old_stage = new_stage
            ORDER BY id ASC
            LIMIT 1
            """,
            (job_card_no, item_name, operator_user_id),
        )
        earliest_partial = cursor.fetchone()

        if earliest_partial:
            # Restore to the state BEFORE the first partial entry
            cursor.execute(
                """
                UPDATE job_card_items
                SET actual_qty = %s,
                    rejected_qty = %s,
                    hold_qty = %s,
                    pending_qty = 0,
                    remarks = %s,
                    remaining_days = %s,
                    wip_stage_days = %s
                WHERE job_card_no = %s
                  AND TRIM(item_name) = TRIM(%s)
                """,
                (
                    earliest_partial.get("previous_item_actual_qty") or 0,
                    earliest_partial.get("previous_item_rejected_qty") or 0,
                    earliest_partial.get("previous_item_hold_qty") or 0,
                    earliest_partial.get("previous_item_remarks"),
                    earliest_partial.get("previous_item_remaining_days"),
                    earliest_partial.get("previous_item_wip_stage_days"),
                    job_card_no,
                    item_name,
                ),
            )

            # OEE_UNDO_INTEGRATION_V1
            # Mirror the existing cascade semantics exactly:
            # active partial completion rows being cascaded below
            # must have their linked active OEE entries marked undone
            # inside this same transaction.
            cursor.execute(
                """
                UPDATE oee_entries oe
                JOIN operator_completion_log ocl
                  ON ocl.id = oe.operator_completion_id
                SET oe.record_status = 'undone',
                    oe.undone_at = NOW(),
                    oe.undone_by_user_id = %s,
                    oe.undo_reason = %s
                WHERE ocl.job_card_no = %s
                  AND TRIM(ocl.item_name) = TRIM(%s)
                  AND ocl.operator_user_id = %s
                  AND ocl.status = 'active'
                  AND ocl.old_stage = ocl.new_stage
                  AND oe.record_status = 'active'
                """,
                (
                    operator_user_id,
                    'Cascade undo: ' + undo_reason,
                    job_card_no,
                    item_name,
                    operator_user_id,
                ),
            )

            # Mark all partial entries as undone
            cursor.execute(
                """
                UPDATE operator_completion_log
                SET status = 'undone',
                    undone_at = NOW(),
                    undo_reason = %s
                WHERE job_card_no = %s
                  AND TRIM(item_name) = TRIM(%s)
                  AND operator_user_id = %s
                  AND status = 'active'
                  AND old_stage = new_stage
                """,
                (
                    'Cascade undo: ' + undo_reason,
                    job_card_no,
                    item_name,
                    operator_user_id,
                ),
            )

        cursor.execute(
            """
            INSERT INTO audit_trail (
                job_card_no,
                item_name,
                old_stage,
                new_stage,
                changed_by,
                changed_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                job_card_no,
                item_name,
                new_stage,
                old_stage,
                operator_name,
            ),
        )

        reversal_audit_id = cursor.lastrowid

        cursor.execute(
            """
            UPDATE operator_completion_log
            SET status = 'undone',
                undone_at = NOW(),
                undo_reason = %s,
                reversal_audit_id = %s
            WHERE id = %s
              AND operator_user_id = %s
              AND status = 'active'
            """,
            (
                undo_reason,
                reversal_audit_id,
                completion_id,
                operator_user_id,
            ),
        )

        if cursor.rowcount != 1:
            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Undo could not be completed because "
                    "the completion status changed."
                )
            }), 409

        # Mark the OEE entry linked to the selected completion as undone.
        # Non-OEE completions simply update zero rows, which is valid.
        cursor.execute(
            """
            UPDATE oee_entries
            SET record_status = 'undone',
                undone_at = NOW(),
                undone_by_user_id = %s,
                undo_reason = %s
            WHERE operator_completion_id = %s
              AND record_status = 'active'
            """,
            (
                operator_user_id,
                undo_reason,
                completion_id,
            ),
        )

        conn.commit()

        return jsonify({
            "success": True,
            "message": (
                f"Completion undone. Job card returned "
                f"to '{old_stage}'."
            ),
            "job_card_no": job_card_no,
            "item_name": item_name,
            "restored_stage": old_stage,
            "undo_reason": undo_reason,
        })

    except Exception as error:
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "error": str(error),
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


@quality_check_bp.route("/api/quality_check", methods=["POST"])
def save_quality_check():
    try:
        data = request.json
        role = (session.get("role") or "").strip().lower()
        if role not in ("admin", "supervisor") and not is_gaurang_special_user():
            return jsonify({"success": False, "error": "Operator has read-only access"}), 403

        job_card_no = data.get("job_card_no")
        details = data.get("details", [])

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_permission_tables(cursor)
        seed_default_permissions(cursor)
        conn.commit()

        if role == "supervisor" and not is_gaurang_special_user():
            for d in details:
                item_name = (d.get("item_name") or "").strip()
                cursor.execute("""
                    SELECT wip_status
                    FROM job_card_items
                    WHERE job_card_no = %s
                      AND TRIM(item_name) = TRIM(%s)
                    LIMIT 1
                """, (job_card_no, item_name))
                item_row = cursor.fetchone()
                current_process = item_row["wip_status"] if item_row else ""
                if not supervisor_has_process_access(
                    cursor, session.get("user_id"), current_process
                ):
                    cursor.close()
                    conn.close()
                    return jsonify({
                        "success": False,
                        "error": f"You do not have rights to update process: {current_process}"
                    }), 403
                if not can_user_edit_field(
                    cursor, role, session.get(
                        "user_id"), PAGE3_TRACEABILITY, "actual_qty"
                ):
                    cursor.close()
                    conn.close()
                    return jsonify({
                        "success": False,
                        "error": "You do not have rights to update actual_qty"
                    }), 403
                if (d.get("remarks") or "").strip() and not can_user_edit_field(
                    cursor, role, session.get(
                        "user_id"), PAGE3_TRACEABILITY, "remarks"
                ):
                    cursor.close()
                    conn.close()
                    return jsonify({
                        "success": False,
                        "error": "You do not have rights to update remarks"
                    }), 403

        cursor.execute(
            "INSERT INTO quality_checks (job_card_no) VALUES (%s)", (job_card_no,)
        )
        qc_id = cursor.lastrowid
        has_qcd_rejected_qty = _has_column(
            cursor, "quality_check_details", "rejected_qty")
        has_item_rejected_qty = _has_column(
            cursor, "job_card_items", "rejected_qty")

        for d in details:
            if has_qcd_rejected_qty:
                cursor.execute(
                    """
                    INSERT INTO quality_check_details
                    (quality_check_id, item_name, actual_qty, rejected_qty, process_name, quality_result, supervisor)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                    (
                        qc_id,
                        d["item_name"],
                        d["actual_qty"],
                        d.get("rejected_qty"),
                        d["completed_process"],
                        d["quality_result"],
                        d["supervisor"],
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO quality_check_details
                    (quality_check_id, item_name, actual_qty, process_name, quality_result, supervisor)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """,
                    (
                        qc_id,
                        d["item_name"],
                        d["actual_qty"],
                        d["completed_process"],
                        d["quality_result"],
                        d["supervisor"],
                    ),
                )

            if has_item_rejected_qty:
                cursor.execute(
                    """
                    UPDATE job_card_items SET actual_qty = %s, rejected_qty = %s, remarks = %s
                    WHERE job_card_no = %s AND item_name = %s
                """,
                    (d["actual_qty"], d.get("rejected_qty"), d.get(
                        "remarks", ""), job_card_no, d["item_name"]),
                )
            else:
                cursor.execute(
                    """
                    UPDATE job_card_items SET actual_qty = %s, remarks = %s
                    WHERE job_card_no = %s AND item_name = %s
                """,
                    (d["actual_qty"], d.get("remarks", ""),
                     job_card_no, d["item_name"]),
                )

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Quality check saved!"})

    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quality_check_bp.route(
    "/api/quality_check/history/<path:job_card_no>", methods=["GET"]
)
def get_quality_history(job_card_no):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT qcd.*, qc.checked_at
            FROM quality_check_details qcd
            JOIN quality_checks qc ON qcd.quality_check_id = qc.id
            WHERE qc.job_card_no = %s
            ORDER BY qc.checked_at DESC
        """,
            (job_card_no,),
        )
        rows = cursor.fetchall()
        for r in rows:
            if r.get("checked_at"):
                r["checked_at"] = _to_ist(
                    r["checked_at"]).strftime("%Y-%m-%d %H:%M")
        cursor.close()
        conn.close()
        return jsonify({"success": True, "history": rows})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quality_check_bp.route("/api/wip/subcontract", methods=["POST"])
def set_subcontract():
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        TEST_API_KEY = "NMTG_TEST_123"

        api_key = (request.headers.get("X-API-Key") or "").strip()
        api_key_ok = api_key == TEST_API_KEY

        role = (session.get("role") or "").strip().lower()

        if not api_key_ok:
            if role not in ("admin", "supervisor") and not is_gaurang_special_user():
                return jsonify({
                    "success": False,
                    "error": "You do not have permission to update WIP stage."
                }), 403
        else:
            role = "admin"

        job_card_no = (data.get("job_card_no") or "").strip()
        item_name = (data.get("item_name") or "").strip()
        next_process = (data.get("process") or "").strip()

        vendor_name = (
            data.get("vendor_name")
            or data.get("subcontractor_name")
            or ""
        ).strip()

        changed_by = (data.get("changed_by") or "").strip()
        stage_remark = (data.get("stage_remark") or "").strip()

        if not changed_by or changed_by.lower() in ("not assigned", "system", ""):
            changed_by = session.get("username") or session.get(
                "full_name") or "System"

        if not job_card_no or not item_name or not next_process:
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400

        if not vendor_name:
            return jsonify({
                "success": False,
                "error": "Vendor name is required for subcontracting"
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        actual_job_card_no = _resolve_job_card_no(cursor, job_card_no)
        if not actual_job_card_no:
            return jsonify({
                "success": False,
                "error": f"Job Card not found: {job_card_no}"
            }), 404

        job_card_no = actual_job_card_no

        for col, defn in [
            ("is_subcontract", "TINYINT(1) DEFAULT 0"),
            ("vendor_name", "VARCHAR(255)")
        ]:
            if not _has_column(cursor, "job_card_process_days", col):
                cursor.execute(
                    f"ALTER TABLE job_card_process_days ADD COLUMN {col} {defn}"
                )

        cursor.execute("""
            SELECT 
                ji.id,
                ji.wip_status,
                ji.remaining_days,
                ji.delivery_date,
                jc.job_card_date
            FROM job_card_items ji
            JOIN job_cards jc ON jc.job_card_no = ji.job_card_no
            WHERE ji.job_card_no = %s
              AND TRIM(ji.item_name) = TRIM(%s)
            LIMIT 1
        """, (job_card_no, item_name))

        current_item = cursor.fetchone()

        if not current_item:
            return jsonify({
                "success": False,
                "error": f"Item not found in job card {job_card_no}"
            }), 404

        current_wip = (current_item.get("wip_status") or "Pending").strip()

        if _is_store_stage(current_wip):
            return jsonify({
                "success": False,
                "error": "Item is already in Store. No further movement allowed."
            }), 400

        cursor.execute("""
            SELECT 
                id,
                process_name,
                in_time,
                out_time,
                is_completed,
                is_subcontract,
                vendor_name
            FROM job_card_process_days
            WHERE job_card_no = %s
              AND process_name IS NOT NULL
              AND TRIM(process_name) <> ''
            ORDER BY id
        """, (job_card_no,))

        process_rows = cursor.fetchall()

        if not process_rows:
            return jsonify({
                "success": False,
                "error": "No process timeline found for this job card."
            }), 400

        processes = [r["process_name"] for r in process_rows]

        current_idx = _process_index(processes, current_wip)
        next_idx = _process_index(processes, next_process)

        if next_idx is None:
            return jsonify({
                "success": False,
                "error": f"Process not found in process sequence: {next_process}"
            }), 400

        # Rule:
        # Pending → only first process can start
        # Any current process → only immediate next process can go subcontract
        if current_wip.lower() == "pending":
            if next_idx != 0:
                return jsonify({
                    "success": False,
                    "error": f"Stage skip not allowed. First process must be '{processes[0]}'."
                }), 400
            current_row = None
            next_row = process_rows[next_idx]
        else:
            if current_idx is None:
                return jsonify({
                    "success": False,
                    "error": f"Current stage '{current_wip}' is not defined for this job card."
                }), 400

            if next_idx != current_idx + 1:
                return jsonify({
                    "success": False,
                    "error": (
                        f"Stage skip not allowed. Complete '{processes[current_idx]}' "
                        f"before moving to '{next_process}'."
                    )
                }), 400

            current_row = process_rows[current_idx]
            next_row = process_rows[next_idx]

        # Supervisor must have access to current running process.
        # If current is Pending, access check is for the first process being started.
        access_process = next_process if current_wip.lower() == "pending" else current_wip

        if role == "supervisor" and not is_gaurang_special_user() and not supervisor_has_process_access(
            cursor, session.get("user_id"), access_process
        ):
            return jsonify({
                "success": False,
                "error": f"You do not have rights to update process: {access_process}"
            }), 403

        cursor.execute("SELECT NOW() AS now_ts")
        completion_time = cursor.fetchone()["now_ts"]

        # 1) Complete current process first, if current process exists.
        # Vendor name is NOT cleared, so subcontract vendor history remains stored.
        # is_subcontract is set to 0 because this process is no longer active subcontract.
        if current_row:
            cursor.execute("""
                UPDATE job_card_process_days
                SET in_time = COALESCE(in_time, %s),
                    out_time = %s,
                    end_date = DATE(%s),
                    is_completed = 1,
                    actual_days = DATEDIFF(%s, COALESCE(in_time, %s))
                WHERE id = %s
            """, (
                current_item.get("job_card_date") or completion_time,
                completion_time,
                completion_time,
                completion_time,
                current_item.get("job_card_date") or completion_time,
                current_row["id"]
            ))

        # 2) Start immediate next process as subcontract.
        # This is the only process that can become subcontract now.
        cursor.execute("""
            UPDATE job_card_process_days
            SET in_time = %s,
                out_time = NULL,
                end_date = NULL,
                is_completed = 0,
                is_subcontract = 1,
                vendor_name = %s,
                actual_days = NULL
            WHERE id = %s
        """, (
            completion_time,
            vendor_name,
            next_row["id"]
        ))

        # 3) Update item current WIP to the next process.
        cursor.execute("""
            UPDATE job_card_items
            SET wip_status = %s,
                wip_stage_days = 0,
                remarks = CASE
                    WHEN %s = '' THEN remarks
                    ELSE %s
                END
            WHERE id = %s
        """, (
            next_row["process_name"],
            stage_remark,
            stage_remark,
            current_item["id"]
        ))

        cursor.execute("""
            INSERT INTO audit_trail
            (job_card_no, item_name, old_stage, new_stage, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (
            job_card_no,
            item_name,
            current_wip,
            f"{next_row['process_name']} (Subcontract - {vendor_name})",
            changed_by
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "message": f"{next_row['process_name']} started in subcontracting - {vendor_name}",
            "old_stage": current_wip,
            "new_stage": next_row["process_name"],
            "vendor_name": vendor_name
        })

    except Exception as e:
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@quality_check_bp.route("/api/wip/subcontract_complete", methods=["POST"])
def complete_subcontract():
    try:
        data = request.json
        TEST_API_KEY = "NMTG_TEST_123"

        api_key = (request.headers.get("X-API-Key") or "").strip()
        api_key_ok = api_key == TEST_API_KEY

        role = (session.get("role") or "").strip().lower()

        if not api_key_ok:
            if role not in ("admin", "supervisor") and not is_gaurang_special_user():
                return jsonify({
                    "success": False,
                    "error": "You do not have permission to update WIP stage."
                }), 403
        else:
            role = "admin"

        job_card_no = data.get("job_card_no")
        item_name = data.get("item_name")
        process = data.get("process")
        changed_by = data.get("changed_by", "")
        if not changed_by or changed_by.strip().lower() in ("not assigned", "system", ""):
            changed_by = session.get("username") or session.get(
                "full_name") or "System"

        if not all([job_card_no, item_name, process]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # ── Supervisor process-access check ────────────────────────────────────
        if role == "supervisor" and not is_gaurang_special_user() and not supervisor_has_process_access(
            cursor, session.get("user_id"), process
        ):
            cursor.close()
            conn.close()
            return jsonify({
                "success": False,
                "error": f"You do not have rights to update process: {process}"
            }), 403

        cursor.execute("""
            SELECT id, in_time FROM job_card_process_days
            WHERE job_card_no = %s AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
            ORDER BY id LIMIT 1
        """, (job_card_no, process))
        sub_pd = cursor.fetchone()

        if sub_pd and sub_pd["in_time"] is None:
            cursor.execute("""
                SELECT out_time FROM job_card_process_days
                WHERE job_card_no = %s AND id < %s AND is_completed = 1
                ORDER BY id DESC LIMIT 1
            """, (job_card_no, sub_pd["id"]))
            prev_pd = cursor.fetchone()
            resolved_in = prev_pd["out_time"] if (
                prev_pd and prev_pd["out_time"] is not None) else None

            if resolved_in is None:
                cursor.execute(
                    "SELECT job_card_date FROM job_cards WHERE job_card_no = %s",
                    (job_card_no,),
                )
                jc_row = cursor.fetchone()
                resolved_in = jc_row["job_card_date"] if (
                    jc_row and jc_row["job_card_date"] is not None) else None

            if resolved_in is not None:
                cursor.execute("""
                    UPDATE job_card_process_days
                    SET in_time = %s
                    WHERE id = %s
                """, (resolved_in, sub_pd["id"]))

        cursor.execute("""
            UPDATE job_card_process_days
            SET is_completed   = 1,
                out_time       = NOW(),
                actual_days    = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
            WHERE job_card_no = %s
              AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
        """, (job_card_no, process))

        procs, process_source, pm = _fetch_process_sequence(
            cursor, job_card_no, item_name
        )
        next_stage = ""
        proc_idx = _process_index(procs, process)
        if proc_idx is not None and proc_idx + 1 < len(procs):
            next_stage = procs[proc_idx + 1]

        cursor.execute("""
            SELECT delivery_date FROM job_card_items
            WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
        """, (job_card_no, item_name.strip()))
        delivery_row = cursor.fetchone()
        new_remaining = _remaining_days_from_delivery(
            delivery_row.get("delivery_date") if delivery_row else None
        )

        new_wip = next_stage if next_stage else "Store"
        cursor.execute("""
            UPDATE job_card_items
            SET wip_status = %s, remaining_days = %s, wip_stage_days = 0
            WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
        """, (new_wip, new_remaining, job_card_no, item_name.strip()))

        if next_stage:
            # Get the id of the current subcontract process and next process
            cursor.execute("""
                SELECT id FROM job_card_process_days
                WHERE job_card_no = %s
                AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                ORDER BY id LIMIT 1
            """, (job_card_no, process))
            current_proc_row = cursor.fetchone()
            current_proc_id = current_proc_row["id"] if current_proc_row else None

            cursor.execute("""
                SELECT id FROM job_card_process_days
                WHERE job_card_no = %s
                AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                ORDER BY id LIMIT 1
            """, (job_card_no, next_stage))
            next_proc_row = cursor.fetchone()
            next_proc_id = next_proc_row["id"] if next_proc_row else None

            if current_proc_id and next_proc_id:
                # Mark only processes strictly between current and next as completed
                cursor.execute("""
                    UPDATE job_card_process_days
                    SET is_completed = 1,
                        end_date = CURDATE(),
                        out_time = NOW(),
                        actual_days = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
                    WHERE job_card_no = %s
                    AND is_completed = 0
                    AND is_subcontract = 0
                    AND id > %s
                    AND id < %s
                """, (job_card_no, current_proc_id, next_proc_id))

            if _is_store_stage(next_stage):
                if next_proc_id:
                    cursor.execute("""
                        UPDATE job_card_process_days
                        SET in_time = COALESCE(in_time, NOW()),
                            out_time = COALESCE(out_time, NOW()),
                            is_completed = 1,
                            end_date = CURDATE(),
                            actual_days = COALESCE(actual_days, 0)
                        WHERE job_card_no = %s AND id = %s
                    """, (job_card_no, next_proc_id))
                cursor.execute(
                    "UPDATE job_cards SET final_status = 'Completed' WHERE job_card_no = %s",
                    (job_card_no,),
                )
            else:
                if next_proc_id:
                    cursor.execute("""
                        UPDATE job_card_process_days
                        SET in_time = NOW(),
                            out_time = NULL,
                            is_completed = 0,
                            actual_days = NULL,
                            is_subcontract = 0,
                            vendor_name = NULL
                        WHERE job_card_no = %s AND id = %s
                    """, (job_card_no, next_proc_id))

        cursor.execute("""
            INSERT INTO audit_trail
            (job_card_no, item_name, old_stage, new_stage, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (job_card_no, item_name, f"{process} (Subcontract)", new_wip, changed_by or "System"))

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": f"Subcontracting complete. Moved to {new_wip}"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quality_check_bp.route("/api/wip/rollback", methods=["POST"])
def rollback_wip_stage():
    try:
        data = request.json or {}
        job_card_no = data.get("job_card_no")
        item_name = data.get("item_name")
        current_stage = data.get("current_stage")
        target_stage = data.get("target_stage")
        changed_by = data.get("changed_by", "")
        if not changed_by or changed_by.strip().lower() in ("not assigned", "system", ""):
            changed_by = session.get("username") or session.get(
                "full_name") or "System"

        if not job_card_no or not item_name or not current_stage or not target_stage:
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400

        role = (session.get("role") or "").strip().lower()
        if role not in ("admin", "supervisor") and not is_gaurang_special_user():
            return jsonify({"success": False, "error": "You do not have permission to rollback WIP stage."}), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        if role == "supervisor" and not is_gaurang_special_user() and not supervisor_has_process_access(
            cursor, session.get("user_id"), current_stage
        ):
            cursor.close()
            conn.close()
            return jsonify({
                "success": False,
                "error": f"You do not have rights to rollback from: {current_stage}"
            }), 403

        cursor.execute("""
            SELECT id, process_name
            FROM job_card_process_days
            WHERE job_card_no = %s
            ORDER BY id
        """, (job_card_no,))
        rows = cursor.fetchall()

        current_idx = None
        target_idx = None

        for i, r in enumerate(rows):
            pname = (r["process_name"] or "").strip().lower()
            if pname == current_stage.strip().lower():
                current_idx = i
            if pname == target_stage.strip().lower():
                target_idx = i

        if current_idx is None or target_idx is None:
            cursor.close()
            conn.close()
            return jsonify({
                "success": False,
                "error": "Current or target stage not found"
            }), 404

        if target_idx >= current_idx:
            cursor.close()
            conn.close()
            return jsonify({
                "success": False,
                "error": "Rollback target must be before current stage"
            }), 400

        # Reset stages strictly AFTER the target stage — these genuinely
        # haven't started yet, so a full reset is correct for them.
        rollback_ids = [r["id"] for r in rows[target_idx + 1:]]

        if rollback_ids:
            placeholders = ",".join(["%s"] * len(rollback_ids))
            cursor.execute(f"""
                UPDATE job_card_process_days
                SET in_time = NULL,
                    out_time = NULL,
                    is_completed = 0,
                    actual_days = NULL,
                    end_date = NULL
                WHERE id IN ({placeholders})
            """, rollback_ids)

        # Re-open the target stage WITHOUT touching its original in_time —
        # this preserves the real duration it had been running before it
        # was first completed (e.g. the original 8 days), instead of
        # restarting the clock at "now".
        target_id = rows[target_idx]["id"]
        cursor.execute("""
            UPDATE job_card_process_days
            SET out_time = NULL,
                is_completed = 0,
                actual_days = NULL
            WHERE id = %s
        """, (target_id,))

        cursor.execute("""
            UPDATE job_card_items
            SET wip_status = %s,
                wip_stage_days = 0
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
        """, (target_stage, job_card_no, item_name))

        cursor.execute("""
            INSERT INTO audit_trail
            (job_card_no, item_name, old_stage, new_stage, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (job_card_no, item_name, current_stage, target_stage, changed_by))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"Rolled back from {current_stage} to {target_stage}"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@quality_check_bp.route("/api/revoke/list/<path:job_card_no>", methods=["GET"])
def get_revoke_list(job_card_no):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, item_name, from_process, to_process,
                   revoke_qty, passed_qty, rejected_qty,
                   remarks, status, created_at, completed_at, completed_by
            FROM revoke_log
            WHERE job_card_no = %s
            ORDER BY created_at DESC
        """, (job_card_no,))
        rows = cursor.fetchall()

        for r in rows:
            r["created_at"] = _fmt(r["created_at"])
            r["completed_at"] = _fmt(r["completed_at"])

            cursor.execute("""
                SELECT id, process_name, process_order, lead_days,
                       in_time, out_time, actual_days,
                       is_completed, is_final, merged_to_main
                FROM revoke_process_days
                WHERE revoke_id = %s
                ORDER BY process_order ASC
            """, (r["id"],))
            rp_rows = cursor.fetchall()
            for rp in rp_rows:
                rp["in_time"] = _fmt(rp["in_time"])
                rp["out_time"] = _fmt(rp["out_time"])
            r["rework_stages"] = rp_rows

        cursor.close()
        conn.close()

        return jsonify({"success": True, "data": rows})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quality_check_bp.route("/api/revoke/advance-rework", methods=["POST"])
def advance_rework_stage():
    try:
        data = request.json
        rework_stage_id = data.get("rework_stage_id")
        revoke_id = data.get("revoke_id")

        if not rework_stage_id or not revoke_id:
            return jsonify({"success": False, "error": "Missing fields"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM revoke_process_days WHERE id = %s
        """, (rework_stage_id,))
        stage = cursor.fetchone()

        if not stage:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Rework stage not found"}), 404

        if stage["is_completed"]:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Already completed"}), 400

        cursor.execute("""
            UPDATE revoke_process_days
            SET is_completed = 1,
                out_time     = NOW(),
                actual_days  = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
            WHERE id = %s
        """, (rework_stage_id,))

        cursor.execute("""
            SELECT * FROM revoke_process_days
            WHERE revoke_id = %s AND process_order = %s
        """, (revoke_id, stage["process_order"] + 1))
        next_stage = cursor.fetchone()

        msg = f"Rework stage '{stage['process_name']}' completed"

        if next_stage:
            cursor.execute("""
                UPDATE revoke_process_days
                SET in_time = NOW()
                WHERE id = %s
            """, (next_stage["id"],))
            msg += f" → moved to '{next_stage['process_name']}'"
        else:
            cursor.execute("""
                UPDATE revoke_process_days
                SET merged_to_main = 1
                WHERE revoke_id = %s
            """, (revoke_id,))
            msg += " — rework complete, ready to merge into main flow"

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": msg})

    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quality_check_bp.route("/api/revoke/merge", methods=["POST"])
def merge_revoke():
    try:
        data = request.json
        revoke_id = data.get("revoke_id")
        passed_qty = int(data.get("passed_qty") or 0)
        rejected_qty = int(data.get("rejected_qty") or 0)

        if not revoke_id:
            return jsonify({"success": False, "error": "revoke_id required"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM revoke_log WHERE id = %s", (revoke_id,))
        revoke = cursor.fetchone()
        if not revoke:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Revoke not found"}), 404

        if revoke["status"] == "Completed":
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Already completed"}), 400

        job_card_no = revoke["job_card_no"]
        item_name = revoke["item_name"]

        cursor.execute("""
            SELECT COUNT(*) AS total,
                   SUM(is_completed) AS done
            FROM revoke_process_days
            WHERE revoke_id = %s
        """, (revoke_id,))
        rp = cursor.fetchone()
        if rp["total"] > 0 and int(rp["done"] or 0) < int(rp["total"]):
            cursor.close()
            conn.close()
            return jsonify({
                "success": False,
                "error": "Complete all rework stages before merging"
            }), 400

        cursor.execute("""
            UPDATE revoke_log
            SET status       = 'Completed',
                passed_qty   = %s,
                rejected_qty = %s,
                completed_at = NOW()
            WHERE id = %s
        """, (passed_qty, rejected_qty, revoke_id))

        cursor.execute("""
            UPDATE job_card_items
            SET merged_qty   = COALESCE(merged_qty,  0) + %s,
                rejected_qty = COALESCE(rejected_qty, 0) + %s,
                revoked_qty  = GREATEST(0, COALESCE(revoked_qty, 0) - %s)
            WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
        """, (
            passed_qty, rejected_qty,
            revoke["revoke_qty"],
            job_card_no, item_name.strip()
        ))

        cursor.execute("""
            UPDATE revoke_process_days
            SET merged_to_main = 1
            WHERE revoke_id = %s
        """, (revoke_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"{passed_qty} qty merged into main flow"
                       + (f", {rejected_qty} permanently rejected" if rejected_qty else "")
                       })

    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@quality_check_bp.route("/api/wip/remove_process", methods=["POST"])
def remove_process():
    conn = None
    cursor = None
    try:
        data = request.json or {}
        job_card_no = (data.get("job_card_no") or "").strip()
        item_name = (data.get("item_name") or "").strip()
        process_name = (data.get("process_name") or "").strip()

        # Only Gaurang (user_id=5) can remove processes
        if not is_gaurang_special_user():
            return jsonify({
                "success": False,
                "error": "You do not have permission to remove processes."
            }), 403

        if not job_card_no or not process_name:
            return jsonify({
                "success": False,
                "error": "job_card_no and process_name are required."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        actual_job_card_no = _resolve_job_card_no(cursor, job_card_no)
        if not actual_job_card_no:
            return jsonify({
                "success": False,
                "error": f"Job Card not found: {job_card_no}"
            }), 404
        job_card_no = actual_job_card_no

        # Fetch full process sequence ordered by id
        cursor.execute("""
            SELECT id, process_name, is_completed, in_time, out_time
            FROM job_card_process_days
            WHERE job_card_no = %s
            ORDER BY id
        """, (job_card_no,))
        all_processes = cursor.fetchall()

        # Find the process to remove
        target = None
        target_idx = None
        for idx, row in enumerate(all_processes):
            if _match_processes(row["process_name"], process_name):
                target = row
                target_idx = idx
                break

        if not target:
            return jsonify({
                "success": False,
                "error": f"Process '{process_name}' not found in job card timeline."
            }), 404

        # Fetch current wip_status
        cursor.execute("""
            SELECT wip_status FROM job_card_items
            WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
            LIMIT 1
        """, (job_card_no, item_name))
        item_row = cursor.fetchone()
        current_wip = (item_row.get("wip_status") or "") if item_row else ""

        is_current_wip = _match_processes(current_wip, process_name)

        # PAGE3_REMOVE_PROCESS_MASTER_SYNC_START
        # New rule:
        # If the removed process exists in Page2 Process Master routing for this child_code,
        # remove it from item_processes also. This makes the change apply to all job cards
        # of the same child_code when they are opened/synced.
        #
        # If the process is not part of item_processes, like Quality Check / Assembly / Store,
        # keep it as a job-card-specific exception.
        removed_from_process_master = False

        try:
            removed_process_name = (target.get("process_name") or "").strip()
            removed_process_key = _norm_process_key(removed_process_name)

            cursor.execute("""
                SELECT
                    TRIM(jc.child_code) AS child_code,
                    ji.item_name
                FROM job_cards jc
                JOIN job_card_items ji
                  ON ji.job_card_no = jc.job_card_no
                WHERE (
                    jc.job_card_no = %s
                    OR (
                        TRIM(jc.job_card_no) REGEXP '^[0-9]+$'
                        AND CAST(TRIM(jc.job_card_no) AS UNSIGNED) = CAST(%s AS UNSIGNED)
                    )
                )
                  AND COALESCE(ji.is_deleted, 0) = 0
                ORDER BY ji.id
                LIMIT 1
            """, (job_card_no, job_card_no,))
            item_row_for_master_remove = cursor.fetchone()

            item_code_for_master_remove = ""
            if item_row_for_master_remove:
                item_code_for_master_remove = (
                    item_row_for_master_remove.get("child_code") or "").strip()
                item_name_for_master_remove = (
                    item_row_for_master_remove.get("item_name") or "").strip()

                if not item_code_for_master_remove and item_name_for_master_remove:
                    cursor.execute("""
                        SELECT item_code
                        FROM items
                        WHERE TRIM(item_description) = TRIM(%s)
                        ORDER BY item_code
                        LIMIT 1
                    """, (item_name_for_master_remove,))
                    found_item_for_master_remove = cursor.fetchone()
                    if found_item_for_master_remove:
                        item_code_for_master_remove = (
                            found_item_for_master_remove.get("item_code") or ""
                        ).strip()

            process_id_for_master_remove = None
            if removed_process_name:
                cursor.execute("""
                    SELECT id
                    FROM processes
                    WHERE LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                    ORDER BY id
                    LIMIT 1
                """, (removed_process_name,))
                process_row_for_master_remove = cursor.fetchone()
                if process_row_for_master_remove:
                    process_id_for_master_remove = process_row_for_master_remove.get(
                        "id")

            if item_code_for_master_remove and process_id_for_master_remove:
                cursor.execute("""
                    DELETE FROM item_processes
                    WHERE item_code = %s
                      AND process_id = %s
                """, (item_code_for_master_remove, process_id_for_master_remove))

                removed_from_process_master = cursor.rowcount > 0

                if removed_from_process_master:
                    _resequence_item_processes(
                        cursor, item_code_for_master_remove)

                    # Remove old job-card exceptions for this same child_code + process.
                    # This avoids old exceptions blocking the process if it is added again later.
                    try:
                        _ensure_job_card_process_exclusions_table(cursor)
                        cursor.execute("""
                            DELETE e
                            FROM job_card_process_exclusions e
                            JOIN job_cards jc
                              ON jc.job_card_no = e.job_card_no
                            WHERE TRIM(jc.child_code) = TRIM(%s)
                              AND e.process_name_norm = %s
                        """, (item_code_for_master_remove, removed_process_key))
                    except Exception as ex:
                        print("Warning: old process exclusions cleanup failed:", ex)

                    print(
                        "Page3 process removed from Process Master:",
                        job_card_no,
                        item_code_for_master_remove,
                        removed_process_name
                    )

        except Exception as ex:
            print("Warning: process master remove failed:", ex)

        if not removed_from_process_master:
            # Process not found in item_processes.
            # Keep old behavior: remove only from this job card as exception.
            try:
                _ensure_job_card_process_exclusions_table(cursor)
                removed_process_name = (
                    target.get("process_name") or "").strip()
                removed_process_key = _norm_process_key(removed_process_name)

                try:
                    removed_by = (
                        session.get("username")
                        or session.get("user")
                        or session.get("full_name")
                        or "system"
                    )
                except Exception:
                    removed_by = "system"

                if removed_process_name and removed_process_key:
                    cursor.execute("""
                        INSERT INTO job_card_process_exclusions
                        (
                            job_card_no,
                            process_name,
                            process_name_norm,
                            removed_by,
                            removed_at
                        )
                        VALUES (%s, %s, %s, %s, NOW())
                        ON DUPLICATE KEY UPDATE
                            process_name = VALUES(process_name),
                            removed_by = VALUES(removed_by),
                            removed_at = NOW()
                    """, (
                        job_card_no,
                        removed_process_name,
                        removed_process_key,
                        removed_by
                    ))
            except Exception as ex:
                print("Warning: process exclusion save failed:", ex)
        # PAGE3_REMOVE_PROCESS_MASTER_SYNC_END

        # Delete the process from timeline
        cursor.execute("""
            DELETE FROM job_card_process_days
            WHERE id = %s
        """, (target["id"],))

        # If removed process was current WIP → move to next process
        if is_current_wip:
            remaining = [
                p for p in all_processes if p["id"] != target["id"]
            ]
            # Find next process after removed one
            next_process = None
            for p in remaining:
                if p["id"] > target["id"]:
                    next_process = p
                    break
            # If no next, take previous
            if not next_process and remaining:
                next_process = remaining[-1]

            if next_process:
                new_wip = next_process["process_name"]

                # Open next process — set in_time if not set
                cursor.execute("""
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, NOW()),
                        out_time = NULL,
                        is_completed = 0,
                        actual_days = NULL,
                        end_date = NULL
                    WHERE id = %s
                """, (next_process["id"],))

                # Update wip_status
                cursor.execute("""
                    UPDATE job_card_items
                    SET wip_status = %s, wip_stage_days = 0
                    WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
                """, (new_wip, job_card_no, item_name))

        # If removed process was first (Drawing) and had in_time set
        # → pass in_time to next process
        elif target_idx == 0 and target.get("in_time"):
            remaining = [
                p for p in all_processes if p["id"] != target["id"]
            ]
            if remaining:
                first_remaining = remaining[0]
                cursor.execute("""
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, %s)
                    WHERE id = %s
                """, (target["in_time"], first_remaining["id"]))

        # Audit trail
        changed_by = session.get("full_name") or session.get(
            "username") or "Gaurang"
        cursor.execute("""
            INSERT INTO audit_trail
            (job_card_no, item_name, old_stage, new_stage, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (job_card_no, item_name, process_name, "Removed", changed_by))

        conn.commit()
        return jsonify({
            "success": True,
            "message": f"Process '{process_name}' removed successfully."
        })

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ── Dashboard API: Overdue -C Parent Status ────────────────────────────────
@quality_check_bp.route("/api/dashboard/overdue-c-parent-status", methods=["GET"])
def overdue_c_parent_status_api():
    """
    Fast Python-map version for overdue -C dashboard status.
    Avoids one heavy CTE query and repeated text joins.
    """
    from collections import defaultdict
    from datetime import date, datetime

    def norm_text(value):
        return " ".join(str(value or "").strip().split()).lower()

    def norm_so(value):
        value = str(value or "").strip()
        if value == "" or value == "-":
            return "__BLANK_SO__"
        return value.lower()

    def to_int(value):
        if value is None:
            return 0
        try:
            return int(value)
        except Exception:
            try:
                return int(float(value))
            except Exception:
                return 0

    def dt_text(value):
        if not value:
            return None
        if isinstance(value, (datetime, date)):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1) Direct -C child to immediate parent map from BOM
        cursor.execute("""
            SELECT
                bl.bom_no,
                bl.child_code AS c_item_code,
                ci.item_description AS c_item_description,
                bl.parent_code AS parent_item_code,
                pi.item_description AS parent_item_description,
                CAST(CONCAT(bl.parent_code, ' > ', bl.child_code) AS CHAR(2000)) AS path_text
            FROM bom_links bl
            JOIN items ci ON ci.item_code = bl.child_code
            JOIN items pi ON pi.item_code = bl.parent_code
            WHERE
                UPPER(TRIM(ci.item_description)) LIKE '%- C'
                OR UPPER(TRIM(ci.item_description)) LIKE '%-C'
        """)
        parent_map = defaultdict(list)
        for r in cursor.fetchall():
            parent_map[norm_text(r.get("c_item_description"))].append(r)

        # 2) Only overdue -C job cards
        cursor.execute("""
            SELECT
                jci.job_card_no AS c_job_card_no,
                jc.so_no AS c_so_no,
                jci.item_name AS c_item_description,
                jci.wip_status AS c_wip_status,
                jpd.process_name AS overdue_process,
                COALESCE(jpd.days, 0) AS lead_days,
                COALESCE(
                    jpd.actual_days,
                    CASE
                        WHEN jpd.in_time IS NOT NULL
                            THEN DATEDIFF(CURDATE(), DATE(jpd.in_time)) + 1
                        ELSE 0
                    END
                ) AS actual_days,
                COALESCE(
                    jpd.actual_days,
                    CASE
                        WHEN jpd.in_time IS NOT NULL
                            THEN DATEDIFF(CURDATE(), DATE(jpd.in_time)) + 1
                        ELSE 0
                    END
                ) - COALESCE(jpd.days, 0) AS overdue_days
            FROM job_card_items jci
            JOIN job_cards jc ON jc.job_card_no = jci.job_card_no
            JOIN job_card_process_days jpd ON jpd.job_card_no = jci.job_card_no
            WHERE
                (
                    UPPER(TRIM(jci.item_name)) LIKE '%- C'
                    OR UPPER(TRIM(jci.item_name)) LIKE '%-C'
                )
              AND COALESCE(jci.is_deleted, 0) = 0
              AND COALESCE(jpd.is_completed, 0) = 0
              AND jpd.out_time IS NULL
              AND COALESCE(jpd.days, 0) > 0
              AND COALESCE(
                    jpd.actual_days,
                    CASE
                        WHEN jpd.in_time IS NOT NULL
                            THEN DATEDIFF(CURDATE(), DATE(jpd.in_time)) + 1
                        ELSE 0
                    END
                  ) > COALESCE(jpd.days, 0)
        """)
        overdue_rows = cursor.fetchall()

        # 3) All parent job cards in small lookup map
        cursor.execute("""
            SELECT
                jc.so_no,
                jci.job_card_no,
                jci.item_name,
                jci.wip_status
            FROM job_card_items jci
            JOIN job_cards jc ON jc.job_card_no = jci.job_card_no
            WHERE COALESCE(jci.is_deleted, 0) = 0
        """)
        parent_job_map = defaultdict(list)
        for r in cursor.fetchall():
            key = (norm_so(r.get("so_no")), norm_text(r.get("item_name")))
            parent_job_map[key].append(r)

        # 4) Parent started status calculated once
        cursor.execute("""
            SELECT
                job_card_no,
                SUM(
                    CASE
                        WHEN in_time IS NOT NULL
                          OR out_time IS NOT NULL
                          OR COALESCE(is_completed, 0) = 1
                        THEN 1
                        ELSE 0
                    END
                ) AS parent_started_process_count,
                MIN(
                    CASE
                        WHEN in_time IS NOT NULL THEN in_time
                        ELSE NULL
                    END
                ) AS parent_first_started_at
            FROM job_card_process_days
            GROUP BY job_card_no
        """)
        parent_started_map = {
            r["job_card_no"]: r
            for r in cursor.fetchall()
        }

        rows = []

        for oc in overdue_rows:
            c_desc_key = norm_text(oc.get("c_item_description"))
            c_so_key = norm_so(oc.get("c_so_no"))

            ipm_list = parent_map.get(c_desc_key, [])

            bom_no_set = set()
            path_set = set()
            parent_item_set = set()
            parent_jc_set = set()
            parent_wip_set = set()
            started_parent_set = set()
            first_started_at = None

            for ipm in ipm_list:
                if ipm.get("bom_no"):
                    bom_no_set.add(str(ipm.get("bom_no")))
                if ipm.get("path_text"):
                    path_set.add(str(ipm.get("path_text")))
                if ipm.get("parent_item_description"):
                    parent_item_set.add(
                        str(ipm.get("parent_item_description")))

                parent_key = (c_so_key, norm_text(
                    ipm.get("parent_item_description")))
                parent_jobs = parent_job_map.get(parent_key, [])

                for pj in parent_jobs:
                    parent_jc = pj.get("job_card_no")
                    if not parent_jc:
                        continue

                    parent_jc_set.add(parent_jc)

                    if pj.get("wip_status"):
                        parent_wip_set.add(str(pj.get("wip_status")))

                    ps = parent_started_map.get(parent_jc) or {}
                    started_count = to_int(
                        ps.get("parent_started_process_count"))

                    if started_count > 0:
                        started_parent_set.add(parent_jc)

                    ps_first = ps.get("parent_first_started_at")
                    if ps_first:
                        if first_started_at is None or ps_first < first_started_at:
                            first_started_at = ps_first

            parent_job_card_found_count = len(parent_jc_set)
            parent_started_count = len(started_parent_set)

            if parent_started_count > 0:
                dashboard_status = "PARENT STARTED - VIOLATION"
            elif parent_job_card_found_count == 0:
                dashboard_status = "PARENT JOB CARD NOT FOUND"
            else:
                dashboard_status = "PARENT NOT STARTED"

            overdue_days = to_int(oc.get("overdue_days"))

            rows.append({
                "dashboard_status": dashboard_status,
                "c_job_card_no": oc.get("c_job_card_no"),
                "c_so_no": oc.get("c_so_no"),
                "c_item_description": oc.get("c_item_description"),
                "c_wip_status": oc.get("c_wip_status"),
                "overdue_process": oc.get("overdue_process"),
                "lead_days": to_int(oc.get("lead_days")),
                "actual_days": to_int(oc.get("actual_days")),
                "overdue_days": overdue_days,
                "overdue_status": f"+{overdue_days}d overdue",
                "bom_no_list": ", ".join(sorted(bom_no_set)),
                "path_list": " || ".join(sorted(path_set)),
                "parent_items": " || ".join(sorted(parent_item_set)),
                "parent_job_cards": ", ".join(sorted(parent_jc_set)),
                "parent_wip_statuses": ", ".join(sorted(parent_wip_set)),
                "parent_first_started_at": dt_text(first_started_at),
                "parent_started_count": parent_started_count
            })

        status_order = {
            "PARENT STARTED - VIOLATION": 1,
            "PARENT JOB CARD NOT FOUND": 2,
            "PARENT NOT STARTED": 3
        }

        rows.sort(key=lambda r: (
            status_order.get(r.get("dashboard_status"), 4),
            -to_int(r.get("overdue_days")),
            str(r.get("c_job_card_no") or "")
        ))

        summary = {
            "PARENT STARTED - VIOLATION": {
                "distinct_c_job_cards": 0,
                "started_parent_job_cards": 0
            },
            "PARENT JOB CARD NOT FOUND": {
                "distinct_c_job_cards": 0,
                "started_parent_job_cards": 0
            },
            "PARENT NOT STARTED": {
                "distinct_c_job_cards": 0,
                "started_parent_job_cards": 0
            }
        }

        for row in rows:
            status = row.get("dashboard_status") or "UNKNOWN"

            if status not in summary:
                summary[status] = {
                    "distinct_c_job_cards": 0,
                    "started_parent_job_cards": 0
                }

            summary[status]["distinct_c_job_cards"] += 1
            summary[status]["started_parent_job_cards"] += int(
                row.get("parent_started_count") or 0)

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "total_overdue_c_job_cards": len(rows),
            "summary": summary,
            "records": rows
        })

    except Exception as e:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@quality_check_bp.route("/api/wip/check-c-child-gate/<job_card_no>", methods=["GET"])
def check_c_child_gate_api(job_card_no):
    """
    Read-only check:
    Before an upper-level item process starts,
    all childest -C item job cards under same SO must be fully completed.
    """
    conn = None
    cursor = None

    try:
        job_card_no = (job_card_no or "").strip()

        if not job_card_no:
            return jsonify({
                "success": False,
                "error": "Job card number is required"
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SET SESSION group_concat_max_len = 100000")

        cursor.execute("""
            WITH RECURSIVE upper_item AS (
                SELECT
                    jc.so_no AS upper_so_no,
                    jci.job_card_no AS upper_job_card_no,
                    jci.item_name AS upper_item_description,
                    i.item_code AS upper_item_code
                FROM job_card_items jci
                JOIN job_cards jc
                    ON jc.job_card_no = jci.job_card_no
                JOIN items i
                    ON (TRIM(i.item_description) COLLATE utf8mb4_unicode_ci)
                     = (TRIM(jci.item_name) COLLATE utf8mb4_unicode_ci)
                WHERE jci.job_card_no = %s
            ),

            bom_descendants AS (
                SELECT
                    ui.upper_so_no,
                    ui.upper_job_card_no,
                    ui.upper_item_code,
                    ui.upper_item_description,
                    bl.bom_no,
                    bl.parent_code,
                    bl.child_code,
                    ci.item_description AS child_description,
                    bl.make_buy,
                    1 AS level_no,
                    CAST(CONCAT(bl.parent_code, ' > ', bl.child_code) AS CHAR(2000)) AS path_text
                FROM upper_item ui
                JOIN bom_links bl
                    ON bl.parent_code = ui.upper_item_code
                JOIN items ci
                    ON ci.item_code = bl.child_code

                UNION ALL

                SELECT
                    bd.upper_so_no,
                    bd.upper_job_card_no,
                    bd.upper_item_code,
                    bd.upper_item_description,
                    bl2.bom_no,
                    bl2.parent_code,
                    bl2.child_code,
                    ci2.item_description AS child_description,
                    bl2.make_buy,
                    bd.level_no + 1 AS level_no,
                    CAST(CONCAT(bd.path_text, ' > ', bl2.child_code) AS CHAR(2000)) AS path_text
                FROM bom_descendants bd
                JOIN bom_links bl2
                    ON bl2.parent_code = bd.child_code
                JOIN items ci2
                    ON ci2.item_code = bl2.child_code
                WHERE bd.level_no < 10
            ),

            c_items AS (
                SELECT DISTINCT
                    upper_so_no,
                    upper_job_card_no,
                    upper_item_code,
                    upper_item_description,
                    bom_no,
                    parent_code,
                    child_code AS c_item_code,
                    child_description AS c_item_description,
                    level_no,
                    path_text
                FROM bom_descendants
                WHERE make_buy = 'A'
                  AND TRIM(child_description) REGEXP '[[:space:]]-[[:space:]]*C$'
            ),

            c_job_cards AS (
                SELECT
                    jc.so_no,
                    jci.job_card_no,
                    jci.item_name,
                    jci.wip_status
                FROM job_card_items jci
                JOIN job_cards jc
                    ON jc.job_card_no = jci.job_card_no
            )

            SELECT
                ci.upper_job_card_no,
                ci.upper_so_no,
                ci.upper_item_code,
                ci.upper_item_description,

                ci.bom_no,
                ci.level_no,
                ci.path_text,

                ci.c_item_code,
                ci.c_item_description,

                cj.job_card_no AS c_job_card_no,
                cj.wip_status AS c_wip_status,

                (
                    SELECT COUNT(*)
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                ) AS c_total_processes,

                (
                    SELECT COUNT(*)
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                      AND COALESCE(jpd.is_completed, 0) = 1
                      AND jpd.out_time IS NOT NULL
                ) AS c_completed_processes,

                (
                    SELECT COUNT(*)
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                      AND (
                          COALESCE(jpd.is_completed, 0) = 0
                          OR jpd.out_time IS NULL
                      )
                ) AS c_pending_processes,

                (
                    SELECT GROUP_CONCAT(
                        CONCAT(
                            jpd.process_name,
                            ' | completed=', COALESCE(jpd.is_completed, 0),
                            ' | in=', COALESCE(DATE_FORMAT(jpd.in_time, '%Y-%m-%d %H:%i'), 'NULL'),
                            ' | out=', COALESCE(DATE_FORMAT(jpd.out_time, '%Y-%m-%d %H:%i'), 'NULL')
                        )
                        ORDER BY jpd.id
                        SEPARATOR ' || '
                    )
                    FROM job_card_process_days jpd
                    WHERE jpd.job_card_no = cj.job_card_no
                ) AS c_process_status,

                CASE
                    WHEN cj.job_card_no IS NULL THEN 'CHILD -C JOB CARD NOT FOUND'
                    WHEN (
                        SELECT COUNT(*)
                        FROM job_card_process_days jpd
                        WHERE jpd.job_card_no = cj.job_card_no
                    ) = 0 THEN 'CHILD -C HAS NO PROCESS ROWS'
                    WHEN (
                        SELECT COUNT(*)
                        FROM job_card_process_days jpd
                        WHERE jpd.job_card_no = cj.job_card_no
                          AND (
                              COALESCE(jpd.is_completed, 0) = 0
                              OR jpd.out_time IS NULL
                          )
                    ) = 0 THEN 'CHILD -C COMPLETED - UPPER CAN START'
                    ELSE 'CHILD -C PENDING - BLOCK UPPER'
                END AS gate_status

            FROM c_items ci
            LEFT JOIN c_job_cards cj
                ON (TRIM(cj.item_name) COLLATE utf8mb4_unicode_ci)
                 = (TRIM(ci.c_item_description) COLLATE utf8mb4_unicode_ci)
               AND (COALESCE(NULLIF(TRIM(cj.so_no), ''), '__BLANK_SO__') COLLATE utf8mb4_unicode_ci)
                 = (COALESCE(NULLIF(TRIM(ci.upper_so_no), ''), '__BLANK_SO__') COLLATE utf8mb4_unicode_ci)
            ORDER BY
                ci.level_no DESC,
                ci.c_item_description,
                cj.job_card_no
        """, (job_card_no,))

        rows = cursor.fetchall()

        # Deduplicate child -C rows for clean API response.
        # Same child -C can repeat when BOM/process joins return multiple rows.
        unique_rows = []
        seen_keys = set()

        for r in rows:
            key = (
                r.get("c_job_card_no") or "",
                r.get("c_item_code") or "",
                r.get("c_item_name") or "",
                r.get("gate_status") or ""
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_rows.append(r)

        rows = unique_rows

        blocking_rows = [
            r for r in rows
            if r.get("gate_status") in (
                "CHILD -C PENDING - BLOCK UPPER",
                "CHILD -C JOB CARD NOT FOUND",
                "CHILD -C HAS NO PROCESS ROWS"
            )
        ]

        upper_item_name = ""

        if rows:
            upper_item_name = (
                rows[0].get("upper_item_description") or ""
            ).strip()

        override_exists = False

        if upper_item_name:
            override_exists = _child_c_gate_override_exists(
                cursor,
                job_card_no,
                upper_item_name
            )

        can_start_upper = (
            len(blocking_rows) == 0
            or override_exists
        )

        # CHILD_C_RELEASE_CLOCK_V1
        # A process held because of Child-C begins counting only
        # after the Child-C gate becomes clear.
        if can_start_upper and upper_item_name:
            cursor.execute(
                """
                SELECT
                    wip_status,
                    COALESCE(rm_hold_reason, '') AS rm_hold_reason
                FROM job_card_items
                WHERE job_card_no = %s
                  AND TRIM(item_name) = TRIM(%s)
                LIMIT 1
                """,
                (
                    job_card_no,
                    upper_item_name,
                ),
            )

            current_item = cursor.fetchone() or {}

            current_wip = str(
                current_item.get("wip_status") or ""
            ).strip()

            rm_reason = str(
                current_item.get("rm_hold_reason") or ""
            ).strip().lower()

            current_wip_key = current_wip.lower()

            clock_allowed = (
                bool(current_wip)
                and current_wip_key not in (
                    "pending",
                    "store",
                    "completed",
                    "complete",
                )
                and not (
                    current_wip_key == "raw material"
                    and rm_reason == "shortage"
                )
            )

            if clock_allowed:
                cursor.execute(
                    """
                    SELECT id
                    FROM job_card_process_days
                    WHERE job_card_no = %s
                      AND LOWER(TRIM(process_name))
                          = LOWER(TRIM(%s))
                      AND in_time IS NULL
                      AND out_time IS NULL
                      AND COALESCE(is_completed, 0) = 0
                    ORDER BY id
                    LIMIT 1
                    """,
                    (
                        job_card_no,
                        current_wip,
                    ),
                )

                waiting_process = cursor.fetchone()

                if waiting_process:
                    cursor.execute(
                        """
                        UPDATE job_card_process_days
                        SET in_time = NOW(),
                            actual_days = NULL,
                            end_date = NULL
                        WHERE id = %s
                          AND in_time IS NULL
                          AND out_time IS NULL
                          AND COALESCE(is_completed, 0) = 0
                        """,
                        (
                            waiting_process["id"],
                        ),
                    )

                    if cursor.rowcount == 1:
                        cursor.execute(
                            """
                            UPDATE job_card_items
                            SET wip_stage_days = 0
                            WHERE job_card_no = %s
                              AND TRIM(item_name) = TRIM(%s)
                            """,
                            (
                                job_card_no,
                                upper_item_name,
                            ),
                        )

                        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "upper_job_card_no": job_card_no,
            "upper_item_name": upper_item_name,
            "can_start_upper": can_start_upper,
            "override_exists": override_exists,
            "blocking_count": len(blocking_rows),
            "total_child_c_items": len(rows),
            "blocking_rows": blocking_rows,
            "all_rows": rows
        })

    except Exception as e:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@quality_check_bp.route("/api/operator/job_cards", methods=["GET"])
def operator_job_cards():
    """Returns job cards for operator's assigned processes."""
    conn = None
    cursor = None
    try:
        role = (session.get("role") or "").strip().lower()
        user_id = session.get("user_id")

        if role != "operator" and not is_gaurang_special_user():
            return jsonify({"success": False, "error": "Access denied"}), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get operator's assigned processes
        cursor.execute("""
            SELECT process_name FROM supervisor_process_access
            WHERE user_id = %s
        """, (user_id,))
        assigned = [r["process_name"] for r in cursor.fetchall()]

        if not assigned:
            return jsonify({
                "success": True,
                "job_cards": [],
                "assigned_processes": [],
                "message": "No processes assigned to this operator."
            })

        # Build WHERE clause for assigned processes
        fmt = ",".join(["%s"] * len(assigned))

        cursor.execute(f"""
            SELECT
                jc.job_card_no,
                jc.so_no,
                jc.parent_code,
                jc.child_code,
                jci.item_name,
                jci.wip_status,
                jci.so_qty,
                jci.job_card_qty,
                jci.actual_qty,
                jci.rejected_qty,
                jci.hold_qty,
                COALESCE(jci.pending_qty, 0) AS pending_qty,
                jci.delivery_date,
                jci.remaining_days,
                jci.part,
                jci.material,
                jc.final_status
            FROM job_cards jc
            JOIN job_card_items jci ON jci.job_card_no = jc.job_card_no
            WHERE LOWER(TRIM(jci.wip_status)) IN ({fmt})
            AND COALESCE(jci.is_deleted, 0) = 0
            AND jc.final_status != 'Completed'
            ORDER BY
                CASE WHEN COALESCE(jci.pending_qty, 0) > 0 THEN 0 ELSE 1 END ASC,
                jci.delivery_date ASC,
                jc.job_card_no ASC
        """, [p.lower() for p in assigned])

        items = cursor.fetchall()

        result = []
        for item in items:
            # Format delivery date
            if item.get("delivery_date") and hasattr(item["delivery_date"], "strftime"):
                item["delivery_date"] = item["delivery_date"].strftime(
                    "%Y-%m-%d")

            # Get process timeline for this JC
            cursor.execute("""
                SELECT
                    jpd.process_name,
                    jpd.in_time,
                    jpd.out_time,
                    jpd.actual_days,
                    COALESCE(pdd.default_days, jpd.days, 0) AS lead_days,
                    COALESCE(jpd.is_completed, 0) AS is_completed
                FROM job_card_process_days jpd
                LEFT JOIN process_default_days pdd
                    ON LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(pdd.process_name))
                WHERE jpd.job_card_no = %s
                ORDER BY jpd.id
            """, (item["job_card_no"],))
            processes = cursor.fetchall()

            # Find current process index
            current_idx = None
            prev_process = None
            next_process = None

            for idx, proc in enumerate(processes):
                if proc["process_name"].lower().strip() == item["wip_status"].lower().strip():
                    current_idx = idx
                    prev_process = processes[idx -
                                             1]["process_name"] if idx > 0 else None
                    next_process = processes[idx + 1]["process_name"] if idx + \
                        1 < len(processes) else "Store"
                    break

            # Calculate days in current process
            days_in_stage = 0
            lead_days = 0
            if current_idx is not None:
                proc = processes[current_idx]
                lead_days = int(proc.get("lead_days") or 0)
                if proc.get("in_time"):
                    from datetime import datetime
                    in_time = proc["in_time"]
                    if hasattr(in_time, "date"):
                        days_in_stage = (datetime.now() - in_time).days
                    days_in_stage = max(0, days_in_stage)

            status = "On Time"
            if days_in_stage > lead_days > 0:
                status = "Overdue"

            pending_qty = int(item.get("pending_qty") or 0)
            hold_qty_val = int(item.get("hold_qty") or 0)
            is_partial = pending_qty > 0 or hold_qty_val > 0

            result.append({
                "job_card_no": item["job_card_no"],
                "so_no": item["so_no"] or "",
                "parent_code": item.get("parent_code") or "",
                "child_code": item.get("child_code") or "",
                "item_name": item["item_name"],
                "wip_status": item["wip_status"],
                "so_qty": int(item.get("so_qty") or 0),
                "job_card_qty": int(item.get("job_card_qty") or 0),
                "actual_qty": int(item.get("actual_qty") or 0),
                "rejected_qty": int(item.get("rejected_qty") or 0),
                "hold_qty": int(item.get("hold_qty") or 0),
                "pending_qty": pending_qty,
                "delivery_date": item["delivery_date"],
                "remaining_days": item["remaining_days"],
                "part": item["part"] or "",
                "material": item["material"] or "",
                "final_status": item.get("final_status") or "Pending",
                "current_process": item["wip_status"],
                "prev_process": prev_process,
                "next_process": next_process,
                "days_in_stage": days_in_stage,
                "lead_days": lead_days,
                "status": status,
                "is_partial": is_partial,
            })

        return jsonify({
            "success": True,
            "job_cards": result,
            "assigned_processes": assigned,
            "total": len(result)
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
