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

        # INCOMING_MATERIAL_RECEIPT_GATE_V1
        #
        # Downstream CNC/VMC operator may complete ONLY the
        # immediate previous NON-CNC/VMC process after physically
        # receiving the full JC quantity.
        #
        # Existing sequence / child gates still run afterwards.
        incoming_receipt = bool(
            data.get("incoming_receipt")
        )

        if incoming_receipt:

            if role != "operator":
                return jsonify({
                    "success": False,
                    "error": (
                        "Incoming material receipt is available "
                        "only to operators."
                    )
                }), 403


            old_stage_norm = str(
                old_stage or ""
            ).strip().lower()

            requested_stage_norm = str(
                requested_stage or ""
            ).strip().lower()


            # Previous CNC/VMC stages must use normal OEE
            # completion and cannot be bypassed by receipt.
            if (
                old_stage_norm.startswith("cnc machining")
                or old_stage_norm.startswith("vmc machining")
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        f"'{old_stage}' is itself a CNC/VMC process. "
                        "Complete its OEE before stage advancement."
                    )
                }), 400


            if not (
                requested_stage_norm.startswith("cnc machining")
                or requested_stage_norm.startswith("vmc machining")
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        "Incoming receipt can advance only into "
                        "a CNC/VMC machining process."
                    )
                }), 400


            # Generic stage-skip validation below already requires
            # new_idx == old_idx + 1. Check again here explicitly
            # because this is a special operator receipt action.
            if (
                new_idx is None
                or new_idx != old_idx + 1
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        "Incoming material receipt is allowed only "
                        "for the immediate next process."
                    )
                }), 400


            # Operator must actually be assigned to the CNC/VMC
            # process they are receiving.
            cursor.execute("""
                SELECT process_name
                FROM supervisor_process_access
                WHERE user_id = %s
            """, (
                session.get("user_id"),
            ))

            operator_assigned_processes = {
                str(
                    row.get("process_name")
                    or ""
                ).strip().lower()
                for row in cursor.fetchall()
            }


            if (
                requested_stage_norm
                not in operator_assigned_processes
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        "You are not assigned to the incoming "
                        f"process '{requested_stage}'."
                    )
                }), 403


            try:
                received_qty = int(
                    data.get("received_qty")
                )
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": (
                        "Received Qty must be a whole number."
                    )
                }), 400


            required_receipt_qty = int(
                item_row.get("job_card_qty")
                or 0
            )

            if required_receipt_qty <= 0:
                required_receipt_qty = int(
                    item_row.get("so_qty")
                    or 0
                )


            if required_receipt_qty <= 0:
                return jsonify({
                    "success": False,
                    "error": (
                        "JC quantity is zero. Supervisor review "
                        "is required before material receipt."
                    )
                }), 400


            if received_qty != required_receipt_qty:
                return jsonify({
                    "success": False,
                    "error": (
                        f"Received Qty ({received_qty}) must match "
                        f"full JC Qty ({required_receipt_qty}) "
                        "before the previous process can be completed."
                    )
                }), 400


            current_rejected = int(
                item_row.get("rejected_qty")
                or 0
            )

            current_hold = int(
                item_row.get("hold_qty")
                or 0
            )

            current_pending = int(
                item_row.get("pending_qty")
                or 0
            )


            if (
                current_rejected > 0
                or current_hold > 0
                or current_pending > 0
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        "Automatic previous-process completion is "
                        "blocked because Reject, Hold or Pending "
                        "quantity exists. Supervisor review required."
                    ),
                    "rejected_qty": current_rejected,
                    "hold_qty": current_hold,
                    "pending_qty": current_pending,
                }), 400


            receipt_note = (
                f"Material received by downstream operator. "
                f"Received Qty {received_qty}/"
                f"{required_receipt_qty}. "
                f"Previous process '{old_stage}' completed "
                f"for incoming '{requested_stage}'."
            )

            if stage_remark:
                stage_remark = (
                    stage_remark
                    + " | "
                    + receipt_note
                )
            else:
                stage_remark = receipt_note

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

        # MACHINE_OEE_OPERATION_COMPLETE_V1_PREP
        #
        # machine_oee_completion=True means:
        #
        # - Machine Session / Machine Run are the OEE authority.
        # - Existing /api/wip/update remains the Traceability authority.
        # - Old JC-wise oee_entries MUST NOT be created.
        #
        machine_oee_completion = bool(
            data.get(
                "machine_oee_completion"
            )
        )

        machine_oee_run = None
        machine_oee_run_id = None


        if machine_oee_completion:

            if role != "operator":

                return jsonify({
                    "success": False,
                    "error": (
                        "Machine OEE completion "
                        "requires Operator login."
                    )
                }), 403


            zone_login = (
                _get_oee_zone_login_v1(
                    cursor
                )
            )


            if not zone_login:

                return jsonify({
                    "success": False,
                    "error": (
                        "Machine-wise completion "
                        "requires a Zone OEE login."
                    )
                }), 403


            try:
                machine_oee_run_id = int(
                    data.get(
                        "machine_run_id"
                    )
                    or 0
                )
            except (TypeError, ValueError):
                machine_oee_run_id = 0


            if machine_oee_run_id <= 0:

                return jsonify({
                    "success": False,
                    "error": (
                        "Valid Machine Run is required."
                    )
                }), 400


            cursor.execute("""
                SELECT
                    e.id,
                    e.id                    AS session_id,
                    e.machine_id,

                    e.job_card_no,
                    e.job_card_item_id,
                    e.process_name,
                    e.entry_state           AS run_status,

                    e.operator_user_id,
                    e.operator_name,

                    e.ok_qty,
                    e.rejected_qty,
                    e.hold_qty,

                    e.created_at            AS started_at,

                    e.machine_no,
                    e.machine_name,
                    e.machine_category,
                    e.zone

                FROM oee_entries e

                WHERE e.id = %s
                  AND e.activity_type IS NULL

                LIMIT 1

                FOR UPDATE
            """, (
                machine_oee_run_id,
            ))


            machine_oee_run = (
                cursor.fetchone()
            )


            if not machine_oee_run:

                return jsonify({
                    "success": False,
                    "error": "Machine Run not found."
                }), 404


            run_status = str(
                machine_oee_run.get(
                    "run_status"
                )
                or ""
            ).strip().upper()


            if run_status != "RUNNING":

                return jsonify({
                    "success": False,
                    "error": (
                        f"Machine Run is already "
                        f"{run_status or 'closed'}."
                    )
                }), 409


            if (
                str(
                    machine_oee_run.get(
                        "job_card_no"
                    )
                    or ""
                ).strip()
                != str(
                    job_card_no
                    or ""
                ).strip()
            ):

                return jsonify({
                    "success": False,
                    "error": (
                        "Machine Run Job Card "
                        "does not match Traceability."
                    )
                }), 409


            run_item_id = (
                machine_oee_run.get(
                    "job_card_item_id"
                )
            )


            current_item_id = (
                item_row.get(
                    "job_card_item_id"
                )
            )


            if (
                run_item_id
                and current_item_id
                and int(run_item_id)
                    != int(current_item_id)
            ):

                return jsonify({
                    "success": False,
                    "error": (
                        "Machine Run item does not "
                        "match the current JC item."
                    )
                }), 409


            if not _match_processes(
                machine_oee_run.get(
                    "process_name"
                ),
                old_stage,
            ):

                return jsonify({
                    "success": False,
                    "error": (
                        "Machine Run process does not "
                        "match current Traceability process."
                    )
                }), 409


            login_zone = str(
                zone_login.get("zone")
                or ""
            ).strip().upper()


            machine_zone = str(
                machine_oee_run.get("zone")
                or ""
            ).strip().upper()


            if login_zone != machine_zone:

                return jsonify({
                    "success": False,
                    "error": (
                        f"This login is for Zone "
                        f"{login_zone}. "
                        f"{machine_oee_run.get('machine_no')} "
                        f"belongs to Zone "
                        f"{machine_zone or '-'}."
                    )
                }), 403


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
        #
        # Machine-wise architecture:
        # do not create old JC-wise OEE entry.
        #
        if machine_oee_completion:
            oee_required = False

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

        # A terminal -C completion OR a missing-store terminal
        # completion has no next process row (new_process is None).
        # Guard against both, not just -C.
        if not is_terminal_without_next_process:
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


        # MACHINE_OEE_OPERATION_COMPLETE_V1_FINALIZE
        #
        # Existing WIP engine has now performed all:
        # - route checks
        # - child gates
        # - quantity logic
        # - process movement
        # - operator completion log
        # - audit trail
        #
        # Only after those succeed do we close the machine run.
        #
        if machine_oee_completion:
            cursor.execute("""
                UPDATE oee_entries

                SET
                    ok_qty = %s,
                    rejected_qty = %s,
                    hold_qty = %s,

                    entry_state   = 'COMPLETED',
                    record_status = 'active',

                    updated_at = CURRENT_TIMESTAMP

                WHERE id = %s
                  AND activity_type IS NULL
                  AND UPPER(TRIM(entry_state)) IN ('RUNNING','HANDOVER_PENDING')
            """, (
                submitted_ok,
                submitted_rej,
                submitted_hold,
                machine_oee_run_id,
            ))


            if cursor.rowcount != 1:

                raise RuntimeError(
                    "OEE entry could not be "
                    "closed safely."
                )

            # 2-table consolidation:
            # finalize the entry (compute planned, run min, ratios, etc.)
            from .oee_persistence import finalize_completed_entry
            finalize_completed_entry(
                cursor, machine_oee_run_id
            )


            #
            # IMPORTANT:
            # oee_machine_sessions stays OPEN.
            #
            # The next JC on the same machine/shift
            # continues contributing to the same
            # machine-wise OEE.
            #


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
            "machine_oee_completion":
                machine_oee_completion,

            "machine_run_id": (
                machine_oee_run_id
                if machine_oee_completion
                else None
            ),

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
    # MACHINE_OEE_WIP_JSON_SAFETY_V2
    #
    # _update_wip_from_saved_timeline() already handles its normal
    # database / validation errors as JSON.
    #
    # This outer protection catches anything that escapes from it
    # so API callers never receive Flask's HTML 500 page.
    try:
        return _update_wip_from_saved_timeline()

    except Exception as error:

        return jsonify({
            "success": False,
            "error": (
                "WIP update failed: "
                f"{type(error).__name__}: {error}"
            )
        }), 500


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
    """
    Returns operator job cards.

    Default:
        Same current-process behaviour as before.

    include_incoming=1:
        Also shows JCs whose immediate NEXT process is one of
        this operator's assigned CNC/VMC processes.

    This API does NOT complete or move any process.
    """

    conn = None
    cursor = None

    try:
        role = (
            session.get("role")
            or ""
        ).strip().lower()

        user_id = session.get("user_id")

        if (
            role != "operator"
            and not is_gaurang_special_user()
        ):
            return jsonify({
                "success": False,
                "error": "Access denied"
            }), 403


        # ==============================================
        # Incoming mode is opt-in.
        #
        # Existing Page 3 currently does not send this,
        # so live behaviour remains unchanged for now.
        # ==============================================

        include_incoming = (
            (
                request.args.get(
                    "include_incoming"
                )
                or ""
            ).strip()
            == "1"
        )


        # PERFORMANCE:
        # Optional targeted JC lookup.
        #
        # When present, evaluate only this JC instead of
        # loading every active JC into the operator queue.
        requested_job_card_no = (
            request.args.get(
                "job_card_no"
            )
            or ""
        ).strip()


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # ==============================================
        # ASSIGNED PROCESSES
        # ==============================================

        cursor.execute("""
            SELECT process_name
            FROM supervisor_process_access
            WHERE user_id = %s
        """, (
            user_id,
        ))

        assigned = [
            r["process_name"]
            for r in cursor.fetchall()
        ]


        if not assigned:

            return jsonify({
                "success": True,
                "job_cards": [],
                "assigned_processes": [],
                "current_total": 0,
                "incoming_total": 0,
                "message":
                    "No processes assigned to this operator."
            })


        assigned_norm = [
            str(
                process or ""
            ).strip().lower()
            for process in assigned
        ]


        has_cnc_vmc_assignment = any(
            p.startswith("cnc machining")
            or
            p.startswith("vmc machining")
            for p in assigned_norm
        )


        # ==============================================
        # LOAD CANDIDATE JCs
        # ==============================================

        if (
            include_incoming
            and has_cnc_vmc_assignment
        ):

            # Need all active JCs because their current WIP
            # may still belong to the previous department.

            cursor.execute("""
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

                    COALESCE(
                        jci.pending_qty,
                        0
                    ) AS pending_qty,

                    jci.delivery_date,
                    jci.remaining_days,
                    jci.part,
                    jci.material,

                    jc.final_status

                FROM job_cards jc

                JOIN job_card_items jci
                  ON jci.job_card_no =
                     jc.job_card_no

                WHERE
                    COALESCE(
                        jci.is_deleted,
                        0
                    ) = 0

                  AND jc.final_status
                      != 'Completed'

                  AND jci.wip_status
                      IS NOT NULL

                  AND TRIM(
                        jci.wip_status
                      ) != ''

                  AND (
                        %s = ''
                        OR jc.job_card_no = %s
                      )

                ORDER BY
                    CASE
                        WHEN COALESCE(
                            jci.pending_qty,
                            0
                        ) > 0
                        THEN 0
                        ELSE 1
                    END,

                    jci.delivery_date,
                    jc.job_card_no
            """, (
                requested_job_card_no,
                requested_job_card_no,
            ))

        else:

            # ==========================================
            # ORIGINAL CURRENT-WIP BEHAVIOUR
            # ==========================================

            fmt = ",".join(
                ["%s"] * len(assigned)
            )

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

                    COALESCE(
                        jci.pending_qty,
                        0
                    ) AS pending_qty,

                    jci.delivery_date,
                    jci.remaining_days,
                    jci.part,
                    jci.material,

                    jc.final_status

                FROM job_cards jc

                JOIN job_card_items jci
                  ON jci.job_card_no =
                     jc.job_card_no

                WHERE
                    LOWER(
                        TRIM(
                            jci.wip_status
                        )
                    ) IN ({fmt})

                  AND COALESCE(
                        jci.is_deleted,
                        0
                    ) = 0

                  AND jc.final_status
                      != 'Completed'

                  AND (
                        %s = ''
                        OR jc.job_card_no = %s
                      )

                ORDER BY
                    CASE
                        WHEN COALESCE(
                            jci.pending_qty,
                            0
                        ) > 0
                        THEN 0
                        ELSE 1
                    END,

                    jci.delivery_date,
                    jc.job_card_no
            """, (
                *assigned_norm,
                requested_job_card_no,
                requested_job_card_no,
            ))


        items = cursor.fetchall() or []

        result = []

        current_total = 0
        incoming_total = 0


        # ==============================================
        # BUILD QUEUE
        # ==============================================

        for item in items:

            if (
                item.get("delivery_date")
                and hasattr(
                    item["delivery_date"],
                    "strftime"
                )
            ):
                item["delivery_date"] = (
                    item[
                        "delivery_date"
                    ].strftime(
                        "%Y-%m-%d"
                    )
                )


            # ==========================================
            # PROCESS TIMELINE
            # ==========================================

            cursor.execute("""
                SELECT
                    jpd.process_name,
                    jpd.in_time,
                    jpd.out_time,
                    jpd.actual_days,

                    COALESCE(
                        pdd.default_days,
                        jpd.days,
                        0
                    ) AS lead_days,

                    COALESCE(
                        jpd.is_completed,
                        0
                    ) AS is_completed

                FROM job_card_process_days jpd

                LEFT JOIN process_default_days pdd
                  ON LOWER(
                        TRIM(
                            jpd.process_name
                        )
                     )
                   =
                     LOWER(
                        TRIM(
                            pdd.process_name
                        )
                     )

                WHERE
                    jpd.job_card_no = %s

                ORDER BY
                    jpd.id
            """, (
                item["job_card_no"],
            ))

            processes = (
                cursor.fetchall()
                or []
            )


            current_idx = None
            prev_process = None
            next_process = None

            current_wip_norm = str(
                item.get("wip_status")
                or ""
            ).strip().lower()


            for idx, proc in enumerate(
                processes
            ):

                process_norm = str(
                    proc.get("process_name")
                    or ""
                ).strip().lower()

                if (
                    process_norm
                    == current_wip_norm
                ):

                    current_idx = idx

                    prev_process = (
                        processes[
                            idx - 1
                        ]["process_name"]
                        if idx > 0
                        else None
                    )

                    next_process = (
                        processes[
                            idx + 1
                        ]["process_name"]
                        if (
                            idx + 1
                            < len(processes)
                        )
                        else "Store"
                    )

                    break


            if current_idx is None:
                continue


            next_process_norm = str(
                next_process
                or ""
            ).strip().lower()


            # ==========================================
            # CURRENT OPERATOR PROCESS
            # ==========================================

            is_current_assigned = (
                current_wip_norm
                in assigned_norm
            )


            # ==========================================
            # INCOMING CNC/VMC PROCESS
            #
            # Example:
            #
            # Current WIP:
            # Rough Turning
            #
            # Immediate next:
            # CNC Machining 1st Side
            #
            # CNC operator can see it as INCOMING.
            # ==========================================

            next_is_cnc_vmc = (
                next_process_norm.startswith(
                    "cnc machining"
                )
                or
                next_process_norm.startswith(
                    "vmc machining"
                )
            )


            is_incoming = (
                include_incoming
                and not is_current_assigned
                and next_is_cnc_vmc
                and (
                    next_process_norm
                    in assigned_norm
                )
            )


            if (
                not is_current_assigned
                and not is_incoming
            ):
                continue


            # ==========================================
            # CURRENT STAGE AGE
            # ==========================================

            proc = processes[
                current_idx
            ]

            days_in_stage = 0

            lead_days = int(
                proc.get("lead_days")
                or 0
            )


            if proc.get("in_time"):

                from datetime import datetime

                in_time = proc["in_time"]

                if hasattr(
                    in_time,
                    "date"
                ):
                    days_in_stage = (
                        datetime.now()
                        - in_time
                    ).days

                days_in_stage = max(
                    0,
                    days_in_stage
                )


            status = "On Time"

            if (
                days_in_stage
                > lead_days
                > 0
            ):
                status = "Overdue"


            pending_qty = int(
                item.get("pending_qty")
                or 0
            )

            hold_qty_val = int(
                item.get("hold_qty")
                or 0
            )

            is_partial = (
                pending_qty > 0
                or hold_qty_val > 0
            )


            if is_partial:
                available_qty = (
                    pending_qty
                    + hold_qty_val
                )
            else:
                available_qty = int(
                    item.get("job_card_qty")
                    or item.get("so_qty")
                    or 0
                )


            if is_incoming:

                queue_type = "incoming"
                incoming_total += 1

            else:

                queue_type = "current"
                current_total += 1


            result.append({

                "job_card_no":
                    item["job_card_no"],

                "so_no":
                    item.get("so_no")
                    or "",

                "parent_code":
                    item.get("parent_code")
                    or "",

                "child_code":
                    item.get("child_code")
                    or "",

                "item_name":
                    item["item_name"],

                "wip_status":
                    item["wip_status"],

                "so_qty":
                    int(
                        item.get("so_qty")
                        or 0
                    ),

                "job_card_qty":
                    int(
                        item.get("job_card_qty")
                        or 0
                    ),

                "actual_qty":
                    int(
                        item.get("actual_qty")
                        or 0
                    ),

                "rejected_qty":
                    int(
                        item.get("rejected_qty")
                        or 0
                    ),

                "hold_qty":
                    int(
                        item.get("hold_qty")
                        or 0
                    ),

                "pending_qty":
                    pending_qty,

                "available_qty":
                    available_qty,

                "delivery_date":
                    item["delivery_date"],

                "remaining_days":
                    item["remaining_days"],

                "part":
                    item.get("part")
                    or "",

                "material":
                    item.get("material")
                    or "",

                "final_status":
                    item.get("final_status")
                    or "Pending",

                "current_process":
                    item["wip_status"],

                "prev_process":
                    prev_process,

                "next_process":
                    next_process,

                "days_in_stage":
                    days_in_stage,

                "lead_days":
                    lead_days,

                "status":
                    status,

                "is_partial":
                    is_partial,


                # ======================================
                # NEW FIELDS
                # ======================================

                "queue_type":
                    queue_type,

                "is_incoming":
                    bool(
                        is_incoming
                    ),

                "incoming_for_process":
                    (
                        next_process
                        if is_incoming
                        else ""
                    ),

                "previous_process_to_complete":
                    (
                        item["wip_status"]
                        if is_incoming
                        else ""
                    ),

                "received_qty_default":
                    int(
                        item.get(
                            "job_card_qty"
                        )
                        or 0
                    ),
            })


        return jsonify({

            "success": True,

            "job_cards":
                result,

            "assigned_processes":
                assigned,

            "total":
                len(result),

            "current_total":
                current_total,

            "incoming_total":
                incoming_total,

            "include_incoming":
                include_incoming,
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

# MACHINE_OEE_WORKSPACE_V1
@quality_check_bp.route(
    "/api/oee-machine/workspace",
    methods=["POST"]
)
def oee_machine_workspace_v1():
    """
    Open / resume one machine-wise OEE workspace (2-table model).
    - No more oee_machine_sessions INSERT.
    - Pending JC check reads oee_entries directly.
    - machine_session is a synthetic dict (id=None) to keep the
      frontend contract intact.
    """
    from datetime import datetime as _dt

    conn = None
    cursor = None
    try:
        role = (session.get("role") or "").strip().lower()
        if role not in ("operator", "admin", "supervisor") and not is_gaurang_special_user():
            return jsonify({"success": False, "error": "Access denied."}), 403

        data = request.json or {}

        try:
            machine_id = int(data.get("machine_id"))
        except (TypeError, ValueError):
            machine_id = 0
        if machine_id <= 0:
            return jsonify({"success": False, "error": "Please select a valid machine."}), 400

        shift_name = str(data.get("shift_name") or "").strip()
        if not shift_name:
            return jsonify({"success": False, "error": "Shift is required."}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # ----- verify machine -----
        cursor.execute("""
            SELECT id, machine_no, machine_name, machine_category, zone, is_active
            FROM oee_machines WHERE id = %s LIMIT 1
        """, (machine_id,))
        machine = cursor.fetchone()
        if not machine:
            return jsonify({"success": False, "error": "Machine not found."}), 404
        if not int(machine.get("is_active") or 0):
            return jsonify({"success": False, "error": "Selected machine is inactive."}), 400

        machine_category = str(machine.get("machine_category") or "").strip().upper()
        if machine_category not in ("CNC", "VMC"):
            return jsonify({
                "success": False,
                "error": "Machine-wise OEE is currently available only for CNC/VMC machines."
            }), 400

        # ----- STEP 1: pending JC across all shifts (oee_entries) -----
        cursor.execute("""
            SELECT
                e.id                        AS run_id,
                e.id                        AS session_id,
                e.machine_id,
                e.job_card_no,
                NULL                        AS job_card_item_id,
                NULL                        AS process_day_id,
                e.process_name,
                e.entry_state               AS run_status,
                e.operator_user_id,
                e.operator_name,
                e.created_at                AS started_at,
                e.updated_at                AS ended_at,
                CAST(e.start_time AS CHAR)  AS oee_start_time,
                CAST(e.end_time   AS CHAR)  AS oee_end_time,
                e.cycle_minutes,
                e.cycle_seconds,
                e.load_unload_minutes,
                e.load_unload_seconds,
                e.ok_qty,
                e.rejected_qty,
                e.hold_qty,
                e.remarks,
                e.entry_date                AS session_date,
                e.shift_name,
                'OPEN'                      AS session_status
            FROM oee_entries e
            WHERE e.machine_id = %s
              AND e.activity_type IS NULL
              AND e.record_status = 'active'
              AND UPPER(TRIM(e.entry_state)) IN ('RUNNING', 'HANDOVER_PENDING')
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT 1
        """, (machine_id,))
        pending_run = cursor.fetchone()

        if pending_run:
            for key in ("started_at", "ended_at", "session_date"):
                value = pending_run.get(key)
                if value is not None and hasattr(value, "isoformat"):
                    pending_run[key] = value.isoformat()
            return jsonify({
                "success": True,
                "machine": {
                    "id": machine["id"],
                    "machine_no": machine.get("machine_no") or "",
                    "machine_name": machine.get("machine_name") or "",
                    "machine_category": machine_category,
                    "zone": machine.get("zone") or "",
                },
                "requires_previous_resolution": True,
                "pending_run": pending_run,
                "machine_session": None,
                "message": (
                    "This machine already has an unfinished Job Card. "
                    "Resolve it before starting another JC."
                ),
            })

        # ----- STEP 2: synthetic machine_session (no DB row) -----
        requested_date = str(data.get("session_date") or "").strip()
        if requested_date:
            cursor.execute("SELECT DATE(%s) AS session_date", (requested_date,))
            parsed_date_row = cursor.fetchone() or {}
            session_date = parsed_date_row.get("session_date")
            if not session_date:
                return jsonify({"success": False, "error": "Invalid session date."}), 400
        else:
            cursor.execute("SELECT CURDATE() AS session_date")
            session_date = (cursor.fetchone() or {}).get("session_date")

        opened_by_user_id = session.get("user_id")
        opened_by_name = (
            session.get("full_name") or session.get("username") or "Operator"
        )

        machine_session = {
            "id": None,
            "machine_id": machine_id,
            "session_date": (
                session_date.isoformat()
                if hasattr(session_date, "isoformat")
                else str(session_date)
            ),
            "shift_name": shift_name,
            "session_status": "OPEN",
            "opened_by_user_id": opened_by_user_id,
            "opened_by_name": opened_by_name,
            "started_at": _dt.now().isoformat(),
            "closed_at": None,
        }

        return jsonify({
            "success": True,
            "machine": {
                "id": machine["id"],
                "machine_no": machine.get("machine_no") or "",
                "machine_name": machine.get("machine_name") or "",
                "machine_category": machine_category,
                "zone": machine.get("zone") or "",
            },
            "requires_previous_resolution": False,
            "pending_run": None,
            "machine_session": machine_session,
            "session_created": False,
            "message": "Machine OEE workspace ready.",
        })

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# CNC_VMC_MACHINE_SELECTION_V1
@quality_check_bp.route(
    "/api/oee-machine/machine-selection",
    methods=["GET"]
)
def oee_machine_selection_v1():
    """
    Page 3 CNC/VMC operator machine selection.

    Important:
    - Operator is NOT linked to any Zone.
    - Zone belongs to machine master only.
    - CNC/VMC operators can select from current
      active CNC/VMC machines grouped by Zone A-E.
    """

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()


        # ----------------------------------------------------
        # ONLY OPERATOR VIEW
        # ----------------------------------------------------

        if role != "operator":

            return jsonify({
                "success": True,
                "is_cnc_vmc_operator": False,
                "zones": [],
                "machines": []
            })


        user_id = session.get(
            "user_id"
        )


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # ----------------------------------------------------
        # FALLBACK USER RESOLUTION
        # ----------------------------------------------------

        if not user_id:

            username = str(
                session.get("username")
                or session.get("user")
                or ""
            ).strip()


            if username:

                cursor.execute("""
                    SELECT id
                    FROM users
                    WHERE username = %s
                    LIMIT 1
                """, (
                    username,
                ))


                user_row = (
                    cursor.fetchone()
                    or {}
                )


                user_id = (
                    user_row.get("id")
                )


        if not user_id:

            return jsonify({
                "success": False,
                "error": "Logged-in operator could not be resolved."
            }), 401


        # ----------------------------------------------------
        # DETECT CNC / VMC OPERATOR
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                process_name

            FROM supervisor_process_access

            WHERE user_id = %s

              AND (
                    LOWER(
                        TRIM(process_name)
                    ) LIKE 'cnc machining%%'

                    OR

                    LOWER(
                        TRIM(process_name)
                    ) LIKE 'vmc machining%%'
                  )

            ORDER BY process_name
        """, (
            user_id,
        ))


        cnc_vmc_assignments = (
            cursor.fetchall()
            or []
        )


        is_cnc_vmc_operator = bool(
            cnc_vmc_assignments
        )


        # ----------------------------------------------------
        # NORMAL OPERATOR
        # ----------------------------------------------------

        if not is_cnc_vmc_operator:

            return jsonify({
                "success": True,
                "is_cnc_vmc_operator": False,
                "zones": [],
                "machines": []
            })


        # ----------------------------------------------------
        # LOAD MACHINES
        #
        # NO OPERATOR-ZONE FILTER.
        #
        # Machine master is authority for Zone.
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                machine_no,
                machine_name,
                machine_category,
                zone

            FROM oee_machines

            WHERE is_active = 1

              AND UPPER(
                    TRIM(machine_category)
                  ) IN (
                    'CNC',
                    'VMC'
                  )

            ORDER BY
                FIELD(
                    UPPER(TRIM(zone)),
                    'A',
                    'B',
                    'C',
                    'D',
                    'E'
                ),
                machine_no
        """)


        machine_rows = (
            cursor.fetchall()
            or []
        )


        # ----------------------------------------------------
        # GROUP A-E
        # ----------------------------------------------------

        zones = []


        for zone_name in (
            "A",
            "B",
            "C",
            "D",
            "E",
        ):

            zone_machines = []


            for row in machine_rows:

                row_zone = str(
                    row.get("zone")
                    or ""
                ).strip().upper()


                if row_zone != zone_name:
                    continue


                zone_machines.append({
                    "id":
                        row.get("id"),

                    "machine_no":
                        row.get("machine_no")
                        or "",

                    "machine_name":
                        row.get("machine_name")
                        or "",

                    "machine_category":
                        row.get("machine_category")
                        or "",

                    "zone":
                        zone_name,
                })


            zones.append({
                "zone":
                    zone_name,

                "machine_count":
                    len(zone_machines),

                "machines":
                    zone_machines,
            })


        return jsonify({
            "success": True,

            "is_cnc_vmc_operator":
                True,

            "process_assignments": [
                row.get("process_name")
                for row
                in cnc_vmc_assignments
            ],

            "total_machines":
                len(machine_rows),

            "zones":
                zones,
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

# MACHINE_OEE_OPERATOR_PAGE_V1
@quality_check_bp.route(
    "/oee-machine/operator",
    methods=["GET"]
)
def machine_oee_operator_page_v1():
    """
    Dedicated CNC/VMC Machine OEE operator page.

    Step 1 only:
      - validate logged-in CNC/VMC operator
      - validate selected machine
      - lock machine context into page
      - NO JC start
      - NO OEE save
      - NO stage movement
    """

    from flask import render_template

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()


        if role != "operator":

            return (
                "This page is available only "
                "for CNC/VMC operators.",
                403
            )


        raw_machine_id = str(
            request.args.get("machine_id")
            or ""
        ).strip()


        try:
            machine_id = int(
                raw_machine_id
            )
        except (TypeError, ValueError):
            machine_id = 0


        if machine_id <= 0:

            # Zone login: auto-select the first active machine in their zone
            from flask import redirect, url_for as _url_for
            _zconn = get_connection()
            _zcursor = _zconn.cursor(dictionary=True)
            try:
                _zone = _get_oee_zone_login_v1(_zcursor)
                if _zone:
                    _zone_name = (_zone.get("zone") or "").strip().upper()
                    _zcursor.execute(
                        "SELECT id FROM oee_machines"
                        " WHERE UPPER(TRIM(zone)) = %s AND is_active = 1"
                        " ORDER BY machine_no LIMIT 1",
                        (_zone_name,)
                    )
                    _first = _zcursor.fetchone()
                    if _first:
                        return redirect(
                            _url_for(
                                "quality_check.machine_oee_operator_page_v1",
                                machine_id=_first["id"]
                            )
                        )
            finally:
                _zcursor.close()
                _zconn.close()

            return (
                "Invalid machine selection.",
                400
            )


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # ----------------------------------------------------
        # RESOLVE LOGGED-IN USER
        # ----------------------------------------------------

        user_id = session.get(
            "user_id"
        )


        if not user_id:

            username = str(
                session.get("username")
                or session.get("user")
                or ""
            ).strip()


            if username:

                cursor.execute("""
                    SELECT
                        id,
                        username

                    FROM users

                    WHERE username = %s
                    LIMIT 1
                """, (
                    username,
                ))


                user_row = (
                    cursor.fetchone()
                    or {}
                )


                user_id = (
                    user_row.get("id")
                )


        if not user_id:

            return (
                "Logged-in operator could not "
                "be resolved.",
                401
            )


        # ----------------------------------------------------
        # CONFIRM THIS IS CNC/VMC OPERATOR
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                process_name

            FROM supervisor_process_access

            WHERE user_id = %s

              AND (
                    LOWER(
                        TRIM(process_name)
                    ) LIKE 'cnc machining%%'

                    OR

                    LOWER(
                        TRIM(process_name)
                    ) LIKE 'vmc machining%%'
                  )

            LIMIT 1
        """, (
            user_id,
        ))


        cnc_vmc_access = (
            cursor.fetchone()
        )


        # OEE_ZONE_MACHINE_PAGE_ACCESS_V1
        zone_login = (
            _get_oee_zone_login_v1(
                cursor
            )
        )


        if (
            not cnc_vmc_access
            and not zone_login
        ):

            return (
                "This operator is not assigned "
                "to CNC/VMC processes.",
                403
            )


        # ----------------------------------------------------
        # VALIDATE SELECTED MACHINE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                machine_no,
                machine_name,
                machine_category,
                zone,
                zone_supervisor_name,
                is_active

            FROM oee_machines

            WHERE id = %s
            LIMIT 1
        """, (
            machine_id,
        ))


        machine = (
            cursor.fetchone()
        )


        if not machine:

            return (
                "Machine not found.",
                404
            )


        if not int(
            machine.get("is_active")
            or 0
        ):

            return (
                "Selected machine is inactive.",
                400
            )


        category = str(
            machine.get(
                "machine_category"
            )
            or ""
        ).strip().upper()


        if category not in (
            "CNC",
            "VMC",
        ):

            return (
                "Selected machine is not "
                "a CNC/VMC machine.",
                400
            )


        # Shared Zone login may access ONLY machines
        # currently mapped to that Zone.
        if zone_login:

            machine_zone = str(
                machine.get("zone")
                or ""
            ).strip().upper()


            login_zone = str(
                zone_login.get("zone")
                or ""
            ).strip().upper()


            if machine_zone != login_zone:

                return (
                    f"This login is for Zone {login_zone}. "
                    f"{machine.get('machine_no')} belongs "
                    f"to Zone {machine_zone or '-'}."
                    ,
                    403
                )


        machine["machine_category"] = (
            category
        )


        operator_name = str(
            session.get("full_name")
            or session.get("username")
            or session.get("user")
            or "Operator"
        ).strip()


        # SINGLE_PAGE_ZONE_MACHINES_V60
        zone_machines_list = []

        if zone_login:
            _zone = str(
                machine.get("zone") or ""
            ).strip().upper()

            cursor.execute("""
                SELECT
                    id,
                    machine_no,
                    machine_name,
                    machine_category

                FROM oee_machines

                WHERE UPPER(TRIM(zone)) = %s
                  AND machine_category IN ('CNC','VMC')
                  AND is_active = 1

                ORDER BY machine_no
            """, (_zone,))

            zone_machines_list = cursor.fetchall()

        else:
            zone_machines_list = [{
                "id":               machine.get("id"),
                "machine_no":       machine.get("machine_no"),
                "machine_name":     machine.get("machine_name"),
                "machine_category": machine.get("machine_category"),
            }]

        return render_template(
            "oee_machine_operator.html",
            machine=machine,
            operator_name=operator_name,
            zone_login=zone_login,
            zone_machines=zone_machines_list,
            active_page="oee_page",
        )


    except Exception as e:

        return (
            f"Unable to open Machine OEE page: {e}",
            500
        )


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()



# OEE_SELECTED_MACHINE_SUPERVISOR_UI_V98
# Selected Machine OEE page now carries
# oee_machines.zone_supervisor_name to the UI.
# MACHINE_OEE_PENDING_CHECK_V1
@quality_check_bp.route(
    "/api/oee-machine/pending/<int:machine_id>",
    methods=["GET"]
)
def machine_oee_pending_check_v1(machine_id):
    """
    Check whether selected CNC/VMC machine already has
    unfinished machine-wise JC work.

    IMPORTANT:
    - read-only
    - does not create a session
    - does not start a JC
    - checks RUNNING / HANDOVER_PENDING across shifts
    """

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()


        if role != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # ----------------------------------------------------
        # VALIDATE MACHINE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                machine_no,
                machine_name,
                machine_category,
                zone,
                is_active

            FROM oee_machines

            WHERE id = %s

            LIMIT 1
        """, (
            machine_id,
        ))


        machine = cursor.fetchone()


        if not machine:

            return jsonify({
                "success": False,
                "error": "Machine not found."
            }), 404


        if not int(
            machine.get("is_active")
            or 0
        ):

            return jsonify({
                "success": False,
                "error": "Selected machine is inactive."
            }), 400


        category = str(
            machine.get("machine_category")
            or ""
        ).strip().upper()


        if category not in (
            "CNC",
            "VMC",
        ):

            return jsonify({
                "success": False,
                "error": "Selected machine is not CNC/VMC."
            }), 400


        # ----------------------------------------------------
        # PENDING MACHINE RUN
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                e.id                     AS run_id,
                e.id                     AS session_id,
                e.machine_id,

                e.job_card_no,
                e.job_card_item_id,
                e.process_day_id,
                e.process_name,

                e.entry_state            AS run_status,

                e.operator_user_id,
                e.operator_name,

                e.created_at             AS started_at,
                e.updated_at             AS ended_at,

                CAST(e.start_time AS CHAR) AS oee_start_time,
                CAST(e.end_time AS CHAR)   AS oee_end_time,

                e.cycle_minutes,
                e.cycle_seconds,

                e.load_unload_minutes,
                e.load_unload_seconds,

                e.ok_qty,
                e.rejected_qty,
                e.hold_qty,

                e.remarks,

                e.entry_date             AS session_date,
                e.shift_name,
                'OPEN'                   AS session_status

            FROM oee_entries e

            WHERE e.machine_id = %s
              AND e.activity_type IS NULL
              AND UPPER(TRIM(e.entry_state)) IN (
                    'RUNNING',
                    'HANDOVER_PENDING'
                  )

            ORDER BY
                e.created_at DESC,
                e.id DESC
        """, (
            machine_id,
        ))


        pending_rows = (
            cursor.fetchall()
            or []
        )


        for row in pending_rows:

            for key in (
                "started_at",
                "ended_at",
                "session_date",
            ):

                value = row.get(key)

                if (
                    value is not None
                    and hasattr(
                        value,
                        "isoformat"
                    )
                ):

                    row[key] = (
                        value.isoformat()
                    )


        return jsonify({
            "success": True,

            "machine": {
                "id":
                    machine.get("id"),

                "machine_no":
                    machine.get("machine_no")
                    or "",

                "machine_name":
                    machine.get("machine_name")
                    or "",

                "machine_category":
                    category,

                "zone":
                    machine.get("zone")
                    or "",
            },

            "has_pending_run":
                bool(pending_rows),

            "pending_count":
                len(pending_rows),

            "pending_run":
                pending_rows[0]
                if pending_rows
                else None,

            "pending_runs":
                pending_rows,
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

# MACHINE_OEE_START_RUN_V1
@quality_check_bp.route(
    "/api/oee-machine/start-run",
    methods=["POST"]
)
def machine_oee_start_run_v1():
    """
    Start one JC on one selected CNC/VMC machine.

    Machine-wise rule:
      - one machine can have only one unfinished run
      - one JC cannot run simultaneously on another machine
      - machine session = Machine + Date + Shift
      - start time is server NOW()
      - no stage movement happens here
    """

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()

        if role != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        data = request.json or {}


        # ----------------------------------------------------
        # INPUT
        # ----------------------------------------------------

        try:
            machine_id = int(
                data.get("machine_id")
            )
        except (TypeError, ValueError):
            machine_id = 0


        job_card_no = str(
            data.get("job_card_no")
            or ""
        ).strip()


        item_name = str(
            data.get("item_name")
            or ""
        ).strip()


        shift_name = str(
            data.get("shift_name")
            or ""
        ).strip()


        if machine_id <= 0:

            return jsonify({
                "success": False,
                "error": "Invalid machine."
            }), 400


        if not job_card_no:

            return jsonify({
                "success": False,
                "error": "Job Card is required."
            }), 400


        if not shift_name:

            return jsonify({
                "success": False,
                "error": "Please select Shift."
            }), 400


        if shift_name not in (
            "Shift 1",
            "Shift 2",
        ):

            return jsonify({
                "success": False,
                "error": "Invalid Shift."
            }), 400


        conn = get_connection()

        conn.start_transaction()

        cursor = conn.cursor(
            dictionary=True
        )


        # MACHINE_OEE_DATABASE_GUARD_V37
        #
        # This project uses jms_demo2. Do not allow the OEE
        # Start Job route to silently write into another schema.
        cursor.execute(
            "SELECT DATABASE() AS database_name"
        )


        database_row = (
            cursor.fetchone()
            or {}
        )


        active_database = str(
            database_row.get(
                "database_name"
            )
            or ""
        ).strip()


        if active_database != "jms_demo2":

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "OEE database mismatch. "
                    f"Expected jms_demo2, connected to "
                    f"{active_database or 'NONE'}."
                )
            }), 500


        # ----------------------------------------------------
        # USER
        # ----------------------------------------------------

        user_id = session.get(
            "user_id"
        )


        username = str(
            session.get("username")
            or session.get("user")
            or ""
        ).strip()


        if not user_id and username:

            cursor.execute("""
                SELECT
                    id,
                    username
                FROM users
                WHERE username = %s
                LIMIT 1
            """, (
                username,
            ))

            user_row = (
                cursor.fetchone()
                or {}
            )

            user_id = user_row.get(
                "id"
            )


        if not user_id:

            return jsonify({
                "success": False,
                "error": "Logged-in operator could not be resolved."
            }), 401


        operator_name = str(
            session.get("full_name")
            or username
            or "Operator"
        ).strip()


        # OEE_OPERATOR_MASTER_START_RUN_V24
        #
        # Zone login identifies the workstation.
        # Operator Master identifies the actual human.
        #
        # operator_user_id continues to represent the
        # logged-in JMS account for audit compatibility.

        run_operator_user_id = user_id

        run_operator_master_id = None

        run_operator_employee_no = None


        zone_login = (
            _get_oee_zone_login_v1(
                cursor
            )
        )


        if zone_login:

            requested_master_id = (
                data.get(
                    "operator_master_id"
                )
                or data.get(
                    "actual_operator_master_id"
                )
            )


            requested_employee_no = str(
                data.get(
                    "operator_employee_no"
                )
                or data.get(
                    "employee_no"
                )
                or ""
            ).strip()


            if (
                requested_master_id
                or requested_employee_no
            ):

                master_operator = (
                    _oee_operator_master_resolve_v24(
                        cursor,
                        requested_master_id,
                        requested_employee_no,
                    )
                )


                run_operator_master_id = (
                    master_operator.get(
                        "id"
                    )
                )


                run_operator_employee_no = (
                    master_operator.get(
                        "employee_no"
                    )
                )


                operator_name = (
                    master_operator.get(
                        "operator_name"
                    )
                    or "Operator"
                )


            else:

                # Temporary backward-compatible fallback.
                #
                # This will be removed after the new
                # Operator Code / Operator Name UI is tested.

                try:

                    actual_operator_user_id = int(
                        data.get(
                            "actual_operator_user_id"
                        )
                        or 0
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    actual_operator_user_id = 0


                if actual_operator_user_id <= 0:

                    return jsonify({
                        "success": False,

                        "error": (
                            "Please enter the actual "
                            "machine operator."
                        )
                    }), 400


                cursor.execute(
                    """
                    SELECT
                        u.id,
                        u.username,
                        u.full_name

                    FROM users u

                    LEFT JOIN oee_zone_logins z
                      ON z.user_id = u.id
                     AND z.is_active = 1

                    WHERE u.id = %s
                      AND u.is_active = 1
                      AND LOWER(
                            TRIM(u.role)
                          ) = 'operator'
                      AND z.id IS NULL

                    LIMIT 1
                    """,
                    (
                        actual_operator_user_id,
                    ),
                )


                actual_operator = (
                    cursor.fetchone()
                )


                if not actual_operator:

                    return jsonify({
                        "success": False,

                        "error": (
                            "Selected actual operator "
                            "is invalid or inactive."
                        )
                    }), 400


                run_operator_user_id = (
                    actual_operator.get(
                        "id"
                    )
                )


                operator_name = str(
                    actual_operator.get(
                        "full_name"
                    )
                    or actual_operator.get(
                        "username"
                    )
                    or "Operator"
                ).strip()


        # ----------------------------------------------------
        # LOCK + VALIDATE MACHINE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                machine_no,
                machine_name,
                machine_category,
                zone,
                is_active

            FROM oee_machines

            WHERE id = %s

            LIMIT 1
            FOR UPDATE
        """, (
            machine_id,
        ))


        machine = cursor.fetchone()


        if not machine:

            return jsonify({
                "success": False,
                "error": "Machine not found."
            }), 404


        if not int(
            machine.get("is_active")
            or 0
        ):

            return jsonify({
                "success": False,
                "error": "Selected machine is inactive."
            }), 400


        machine_category = str(
            machine.get("machine_category")
            or ""
        ).strip().upper()


        if machine_category not in (
            "CNC",
            "VMC",
        ):

            return jsonify({
                "success": False,
                "error": "Selected machine is not CNC/VMC."
            }), 400


        # ----------------------------------------------------
        # MACHINE MUST NOT ALREADY HAVE ACTIVE JC
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                job_card_no,
                process_name,
                entry_state AS run_status,
                created_at  AS started_at

            FROM oee_entries

            WHERE machine_id = %s
              AND activity_type IS NULL
              AND UPPER(TRIM(entry_state)) IN (
                    'RUNNING',
                    'HANDOVER_PENDING'
                  )

            ORDER BY id DESC

            LIMIT 1
            FOR UPDATE
        """, (
            machine_id,
        ))


        existing_machine_run = (
            cursor.fetchone()
        )


        if existing_machine_run:

            return jsonify({
                "success": False,

                "error": (
                    f"{machine.get('machine_no') or 'Machine'} "
                    f"already has active JC "
                    f"{existing_machine_run.get('job_card_no')}."
                ),

                "pending_run":
                    existing_machine_run,
            }), 409


        # ----------------------------------------------------
        # JC CURRENT PROCESS
        #
        # Frontend already resolved shortened JC to actual JC.
        # Backend still validates the real current WIP.
        # ----------------------------------------------------

        if item_name:

            cursor.execute("""
                SELECT
                    jci.id AS job_card_item_id,
                    jc.job_card_no,
                    jci.item_name,
                    jci.wip_status

                FROM job_cards jc

                JOIN job_card_items jci
                  ON jci.job_card_no = jc.job_card_no

                WHERE jc.job_card_no = %s
                  AND jci.item_name = %s

                LIMIT 1
                FOR UPDATE
            """, (
                job_card_no,
                item_name,
            ))

        else:

            cursor.execute("""
                SELECT
                    jci.id AS job_card_item_id,
                    jc.job_card_no,
                    jci.item_name,
                    jci.wip_status

                FROM job_cards jc

                JOIN job_card_items jci
                  ON jci.job_card_no = jc.job_card_no

                WHERE jc.job_card_no = %s

                LIMIT 1
                FOR UPDATE
            """, (
                job_card_no,
            ))


        jc_row = cursor.fetchone()


        if not jc_row:

            return jsonify({
                "success": False,
                "error": "Job Card item was not found."
            }), 404


        current_process = str(
            jc_row.get("wip_status")
            or ""
        ).strip()


        current_process_lower = (
            current_process.lower()
        )


        if current_process_lower.startswith(
            "cnc machining"
        ):
            required_category = "CNC"

        elif current_process_lower.startswith(
            "vmc machining"
        ):
            required_category = "VMC"

        else:

            return jsonify({
                "success": False,

                "error": (
                    f"{job_card_no} is currently at "
                    f"{current_process or 'Unknown Process'}, "
                    f"not CNC/VMC."
                )
            }), 400


        if required_category != machine_category:

            return jsonify({
                "success": False,

                "error": (
                    f"{job_card_no} requires a "
                    f"{required_category} machine, "
                    f"but {machine.get('machine_no')} "
                    f"is {machine_category}."
                )
            }), 400


        # ----------------------------------------------------
        # OPERATOR MUST BE ASSIGNED TO THIS EXACT PROCESS
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                1 AS allowed

            FROM supervisor_process_access

            WHERE user_id = %s
              AND LOWER(TRIM(process_name))
                  = LOWER(TRIM(%s))

            LIMIT 1
        """, (
            user_id,
            current_process,
        ))


        if not cursor.fetchone():

            return jsonify({
                "success": False,

                "error": (
                    f"You are not assigned to "
                    f"{current_process}."
                )
            }), 403


        # ----------------------------------------------------
        # SAME JC MUST NOT BE ACTIVE ON ANOTHER MACHINE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                e.id,
                e.machine_id,
                e.job_card_no,
                e.process_name,
                e.entry_state AS run_status,

                m.machine_no,
                m.machine_name

            FROM oee_entries e

            JOIN oee_machines m
              ON m.id = e.machine_id

            WHERE e.job_card_no = %s
              AND e.activity_type IS NULL
              AND UPPER(TRIM(e.entry_state)) IN (
                    'RUNNING',
                    'HANDOVER_PENDING'
                  )

            ORDER BY e.id DESC

            LIMIT 1
            FOR UPDATE
        """, (
            job_card_no,
        ))


        existing_jc_run = (
            cursor.fetchone()
        )


        if existing_jc_run:

            return jsonify({
                "success": False,

                "error": (
                    f"{job_card_no} is already active on "
                    f"{existing_jc_run.get('machine_no')}."
                ),

                "existing_run":
                    existing_jc_run,
            }), 409


        # ----------------------------------------------------
        # START JC — write directly into oee_entries
        # (2-table consolidation: no session, no middleware run)
        # ----------------------------------------------------

        cursor.execute("""
            INSERT INTO oee_entries (
                machine_id,
                operator_user_id,
                operator_master_id,
                operator_employee_no,
                operator_name,

                entry_date,
                shift_name,

                job_card_no,
                job_card_item_id,
                item_name,
                process_name,

                machine_no,
                machine_name,
                machine_category,
                zone,

                cycle_minutes, cycle_seconds,
                load_unload_minutes, load_unload_seconds,
                ok_qty, rejected_qty, hold_qty,

                entry_state,
                record_status
            )
            VALUES (
                %s,
                %s, %s, %s, %s,
                CURDATE(),
                %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                0, 0, 0, 0,
                0, 0, 0,
                'RUNNING',
                'draft'
            )
        """, (
            machine_id,
            run_operator_user_id,
            run_operator_master_id,
            run_operator_employee_no,
            operator_name,
            shift_name,
            job_card_no,
            jc_row.get("job_card_item_id"),
            item_name or jc_row.get("item_name") or "",
            current_process,
            machine.get("machine_no"),
            machine.get("machine_name"),
            machine.get("machine_category"),
            machine.get("zone"),
        ))

        run_id = cursor.lastrowid
        machine_session_id = run_id   # kept as an alias so downstream code doesn't break


        # ----------------------------------------------------
        # READ CREATED ENTRY  (shape kept for JS compatibility)
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id                     AS run_id,
                id                     AS session_id,
                machine_id,
                job_card_no,
                process_name,
                entry_state            AS run_status,

                operator_master_id,
                operator_employee_no,
                operator_name,

                created_at             AS started_at,

                entry_date             AS session_date,
                shift_name,

                machine_no,
                machine_name,
                machine_category,
                zone
            FROM oee_entries
            WHERE id = %s
            LIMIT 1
        """, (
            run_id,
        ))


        created_run = (
            cursor.fetchone()
            or {}
        )


        # MACHINE_OEE_START_PERSISTENCE_GUARD_V37
        #
        # Never return success to the browser unless the inserted
        # run can be read back inside the same transaction.
        # This prevents a false RUNNING UI with an empty run object.
        created_run_id = int(
            created_run.get(
                "run_id"
            )
            or 0
        )


        if (
            created_run_id <= 0
            or created_run_id != int(run_id or 0)
            or str(
                created_run.get(
                    "run_status"
                )
                or ""
            ).strip().upper() != "RUNNING"
        ):

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Machine Run could not be verified after Start Job. "
                    "No running UI was opened."
                )
            }), 500


        conn.commit()


        for key in (
            "started_at",
            "session_date",
        ):

            value = created_run.get(
                key
            )

            if (
                value is not None
                and hasattr(
                    value,
                    "isoformat"
                )
            ):
                created_run[key] = (
                    value.isoformat()
                )


        return jsonify({
            "success": True,

            "run":
                created_run,

            "message": (
                f"{job_card_no} started on "
                f"{machine.get('machine_no')}."
            ),

            "database_name":
                active_database,
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

# MACHINE_OEE_RUN_VOID_V1
@quality_check_bp.route(
    "/api/oee-machine/run/<int:run_id>/void",
    methods=["POST"]
)
def machine_oee_void_run_v1(run_id):
    """
    Void a RUNNING machine run that was started on the wrong JC.
    Only allowed if no production has been saved yet (ok+rej+hold = 0).
    """
    conn = None
    cursor = None

    try:
        role = str(session.get("role") or "").strip().lower()

        if role != "operator":
            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT id, entry_state AS run_status, ok_qty, rejected_qty, hold_qty
            FROM oee_entries
            WHERE id = %s
              AND activity_type IS NULL
            LIMIT 1
            """,
            (run_id,)
        )
        run = cursor.fetchone()

        if not run:
            return jsonify({
                "success": False,
                "error": "Run not found."
            }), 404

        if str(run.get("run_status") or "").strip().upper() != "RUNNING":
            return jsonify({
                "success": False,
                "error": "Only a RUNNING entry can be cancelled."
            }), 409

        total_qty = (
            int(run.get("ok_qty") or 0)
            + int(run.get("rejected_qty") or 0)
            + int(run.get("hold_qty") or 0)
        )

        if total_qty > 0:
            return jsonify({
                "success": False,
                "error": (
                    "Production already recorded on this entry. "
                    "Contact supervisor to correct."
                )
            }), 409

        cursor.execute(
            """
            UPDATE oee_entries
            SET
                entry_state   = 'VOID',
                record_status = 'void',
                updated_at    = CURRENT_TIMESTAMP
            WHERE id = %s
              AND activity_type IS NULL
              AND UPPER(TRIM(entry_state)) = 'RUNNING'
            """,
            (run_id,)
        )
        conn.commit()

        return jsonify({"success": True})

    except Exception as exc:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# MACHINE_OEE_RUN_PRODUCTION_V1
@quality_check_bp.route(
    "/api/oee-machine/run/<int:run_id>/production",
    methods=["POST"]
)
def machine_oee_run_production_v1(run_id):
    """
    Save production details against one RUNNING
    machine-wise OEE JC run.

    Does NOT:
      - complete JC
      - move Traceability stage
      - close machine session
      - calculate final OEE
    """

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()


        if role != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        data = request.json or {}


        def integer_value(name):

            try:
                value = int(
                    data.get(name)
                    or 0
                )
            except (TypeError, ValueError):
                value = -1

            return value


        ok_qty = integer_value(
            "ok_qty"
        )

        rejected_qty = integer_value(
            "rejected_qty"
        )

        hold_qty = integer_value(
            "hold_qty"
        )

        cycle_minutes = integer_value(
            "cycle_minutes"
        )

        cycle_seconds = integer_value(
            "cycle_seconds"
        )

        load_minutes = integer_value(
            "load_unload_minutes"
        )

        load_seconds = integer_value(
            "load_unload_seconds"
        )


        # MACHINE_OEE_MANUAL_RUN_TIME_V30

        def manual_time_value(name, label):

            raw = str(
                data.get(name)
                or ""
            ).strip()

            if not raw:
                return None

            parts = raw.split(":")

            if len(parts) == 2:
                parts.append("00")

            if len(parts) != 3:

                raise ValueError(
                    f"{label} must be HH:MM:SS."
                )

            try:
                hour = int(parts[0])
                minute = int(parts[1])
                second = int(parts[2])

            except (TypeError, ValueError):

                raise ValueError(
                    f"{label} must be HH:MM:SS."
                )

            if (
                hour < 0
                or hour > 23
                or minute < 0
                or minute > 59
                or second < 0
                or second > 59
            ):

                raise ValueError(
                    f"{label} contains an invalid time."
                )

            return (
                f"{hour:02d}:"
                f"{minute:02d}:"
                f"{second:02d}"
            )


        try:

            oee_start_time = (
                manual_time_value(
                    "oee_start_time",
                    "Start Time",
                )
            )

            oee_end_time = (
                manual_time_value(
                    "oee_end_time",
                    "Stop Time",
                )
            )

        except ValueError as time_error:

            return jsonify({
                "success": False,
                "error": str(time_error),
            }), 400


        if bool(oee_start_time) != bool(oee_end_time):

            return jsonify({
                "success": False,
                "error": (
                    "Enter both Start Time "
                    "and Stop Time."
                ),
            }), 400


        values = {
            "OK Qty": ok_qty,
            "Rejected Qty": rejected_qty,
            "Hold Qty": hold_qty,
            "Cycle Minutes": cycle_minutes,
            "Cycle Seconds": cycle_seconds,
            "Load/Unload Minutes": load_minutes,
            "Load/Unload Seconds": load_seconds,
        }


        for label, value in values.items():

            if value < 0:

                return jsonify({
                    "success": False,
                    "error": (
                        f"{label} cannot be negative."
                    )
                }), 400


        if cycle_seconds > 59:

            return jsonify({
                "success": False,
                "error": (
                    "Cycle Time seconds must be 0-59."
                )
            }), 400


        if load_seconds > 59:

            return jsonify({
                "success": False,
                "error": (
                    "Load / Unload seconds must be 0-59."
                )
            }), 400


        conn = get_connection()

        conn.start_transaction()

        cursor = conn.cursor(
            dictionary=True
        )


        # ----------------------------------------------------
        # LOCK RUN
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                e.id,
                e.id            AS session_id,
                e.machine_id,

                e.job_card_no,
                e.job_card_item_id,
                e.process_name,
                e.entry_state   AS run_status,

                e.operator_user_id,

                e.created_at    AS started_at,

                e.cycle_minutes,
                e.cycle_seconds,
                e.load_unload_minutes,
                e.load_unload_seconds,

                e.ok_qty,
                e.rejected_qty,
                e.hold_qty,

                m.machine_no,
                m.machine_name

            FROM oee_entries e

            JOIN oee_machines m
              ON m.id = e.machine_id

            WHERE e.id = %s
              AND e.activity_type IS NULL

            LIMIT 1
            FOR UPDATE
        """, (
            run_id,
        ))


        run = cursor.fetchone()


        if not run:

            return jsonify({
                "success": False,
                "error": "Machine run not found."
            }), 404


        status = str(
            run.get("run_status")
            or ""
        ).strip().upper()


        if status not in (
            "RUNNING",
            "HANDOVER_PENDING",
        ):

            return jsonify({
                "success": False,
                "error": (
                    f"Machine run is already {status}."
                )
            }), 409


        # ----------------------------------------------------
        # REQUIRED JC QTY
        # ----------------------------------------------------

        required_qty = 0


        job_card_item_id = (
            run.get("job_card_item_id")
        )


        if job_card_item_id:

            cursor.execute("""
                SELECT
                    job_card_qty,
                    so_qty

                FROM job_card_items

                WHERE id = %s

                LIMIT 1
            """, (
                job_card_item_id,
            ))


            item = (
                cursor.fetchone()
                or {}
            )


            pending_qty = int(
                item.get("pending_qty")
                or 0
            )
            hold_qty = int(
                item.get("hold_qty")
                or 0
            )
            
            if pending_qty > 0 or hold_qty > 0:
                required_qty = (
                    pending_qty
                    + hold_qty
                )
            else:
                required_qty = int(
                item.get("job_card_qty")
                or item.get("so_qty")
                or 0
            )



        total_entered_qty = (
            ok_qty
            + rejected_qty
            + hold_qty
        )


        if (
            required_qty > 0
            and total_entered_qty
                > required_qty
        ):

            return jsonify({
                "success": False,
                "error": (
                    f"Entered Qty {total_entered_qty} "
                    f"cannot exceed JC Qty {required_qty}."
                )
            }), 400


        # ----------------------------------------------------
        # SAVE ONLY PRODUCTION PROGRESS
        # ----------------------------------------------------

        cursor.execute("""
            UPDATE oee_entries

            SET
                start_time = %s,
                end_time = %s,

                cycle_minutes = %s,
                cycle_seconds = %s,

                load_unload_minutes = %s,
                load_unload_seconds = %s,

                ok_qty = %s,
                rejected_qty = %s,
                hold_qty = %s,

                updated_at = CURRENT_TIMESTAMP

            WHERE id = %s
              AND activity_type IS NULL
        """, (
            oee_start_time,
            oee_end_time,

            cycle_minutes,
            cycle_seconds,

            load_minutes,
            load_seconds,

            ok_qty,
            rejected_qty,
            hold_qty,

            run_id,
        ))


        # -------------------------------------------------
        # Planned Minutes from operator-entered JC times.
        #
        # Multiple JCs in one machine session:
        # planned time = SUM of their entered durations.
        #
        # Cross-midnight is supported.
        # -------------------------------------------------

        # ----------------------------------------------------
        # Per-entry planned_minutes from operator-entered start/end
        # (2-table consolidation — no session aggregate anymore).
        # ----------------------------------------------------
        if (
            oee_start_time
            and oee_end_time
        ):
            cursor.execute("""
                UPDATE oee_entries
                SET
                    planned_minutes = (
                        CASE
                            WHEN TIME_TO_SEC(end_time) >= TIME_TO_SEC(start_time)
                                THEN (TIME_TO_SEC(end_time) - TIME_TO_SEC(start_time)) / 60.0
                            ELSE (86400 - TIME_TO_SEC(start_time) + TIME_TO_SEC(end_time)) / 60.0
                        END
                    ),
                    available_time_minutes = (
                        CASE
                            WHEN TIME_TO_SEC(end_time) >= TIME_TO_SEC(start_time)
                                THEN (TIME_TO_SEC(end_time) - TIME_TO_SEC(start_time)) / 60.0
                            ELSE (86400 - TIME_TO_SEC(start_time) + TIME_TO_SEC(end_time)) / 60.0
                        END
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                  AND start_time IS NOT NULL
                  AND end_time   IS NOT NULL
            """, (
                run_id,
            ))

        conn.commit()


        return jsonify({
            "success": True,

            "run_id":
                run_id,

            "job_card_no":
                run.get("job_card_no"),

            "required_qty":
                required_qty,

            "total_entered_qty":
                total_entered_qty,

            "message":
                "Production progress saved."
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

# MACHINE_OEE_RUN_LOSSES_V1


def _machine_oee_loss_master_row_v1(row):
    """
    Normalize existing oee_loss_types columns without assuming
    one historical column naming convention.
    """

    if not row:
        return None


    def first_value(*keys):

        for key in keys:

            value = row.get(key)

            if (
                value is not None
                and str(value).strip()
            ):
                return value

        return None


    loss_id = row.get("id")


    code = first_value(
        "loss_code",
        "code",
        "loss_type_code",
        "loss_no",
    )


    name = first_value(
        "loss_name",
        "name",
        "loss_type_name",
        "description",
        "loss_name_gujarati",
        "gujarati_name",
    )


    if not code:
        code = f"A{loss_id}"


    if not name:
        name = str(code)


    return {
        "id": loss_id,
        "loss_code": str(code).strip(),
        "loss_name": str(name).strip(),
    }






# OEE_ACTIVITY_RUN_LOSSES_V87
@quality_check_bp.route(
    "/api/oee-machine/activity-run/<int:activity_run_id>/losses",
    methods=["GET", "POST"]
)
def machine_oee_activity_run_losses_v87(activity_run_id):
    """
    Losses for a Tool Room / Development activity entry.
    Consolidated: reads/writes oee_entry_losses only.
    """
    conn = None
    cursor = None
    try:
        if str(session.get("role") or "").strip().lower() != "operator":
            return jsonify({"success": False, "error": "Operator access required."}), 403

        conn = get_connection()
        if request.method == "POST":
            conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        # ---- resolve the activity entry ----
        cursor.execute("""
            SELECT
                e.id,
                e.id                AS session_id,
                e.machine_id,
                e.activity_type     AS activity_group,
                e.item_name         AS activity_name,
                e.entry_state       AS status,
                e.entry_date        AS session_date,
                e.shift_name,
                e.start_time,
                e.end_time,
                e.operator_user_id,
                e.operator_master_id,
                e.operator_employee_no
            FROM oee_entries e
            WHERE e.id = %s
              AND e.activity_type IS NOT NULL
            LIMIT 1
        """, (activity_run_id,))
        run = cursor.fetchone()
        if not run:
            return jsonify({"success": False, "error": "Activity run was not found."}), 404

        expected_codes = {"A" + str(i) for i in range(1, 28)}

        # ---- GET ----
        if request.method == "GET":
            cursor.execute("""
                SELECT
                    id,
                    oee_entry_id            AS activity_run_id,
                    loss_type_id,
                    loss_code_snapshot      AS loss_code,
                    loss_name_snapshot      AS loss_name,
                    loss_category_snapshot  AS loss_category,
                    loss_minutes,
                    remarks
                FROM oee_entry_losses
                WHERE oee_entry_id = %s
                ORDER BY CAST(SUBSTRING(loss_code_snapshot, 2) AS UNSIGNED), id
            """, (activity_run_id,))
            rows = cursor.fetchall() or []
            for row in rows:
                if row.get("loss_minutes") is not None:
                    row["loss_minutes"] = float(row["loss_minutes"])
            return jsonify({
                "success": True,
                "activity_run_id": activity_run_id,
                "losses": rows,
            })

        # ---- POST validation ----
        status = str(run.get("status") or "").strip().upper()
        if status != "RUNNING":
            return jsonify({
                "success": False,
                "error": "Activity is " + status + ". Losses cannot be changed.",
            }), 409

        data = request.get_json(silent=True) or {}
        submitted_losses = data.get("losses")
        if not isinstance(submitted_losses, list):
            return jsonify({"success": False, "error": "OEE losses must be provided."}), 400

        submitted_map = {}
        for item in submitted_losses:
            if not isinstance(item, dict):
                return jsonify({"success": False, "error": "Invalid OEE loss row."}), 400
            code = str(item.get("loss_code") or "").strip().upper()
            if code not in expected_codes:
                return jsonify({"success": False, "error": "Invalid OEE Loss Code: " + code}), 400
            if code in submitted_map:
                return jsonify({"success": False, "error": "Duplicate OEE Loss Code: " + code}), 400
            try:
                minutes = float(item.get("loss_minutes", 0) or 0)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": code + " loss minutes must be numeric."}), 400
            if minutes < 0:
                return jsonify({"success": False, "error": code + " loss minutes cannot be negative."}), 400
            submitted_map[code] = minutes

        if set(submitted_map) != expected_codes:
            return jsonify({
                "success": False,
                "error": "OEE Loss Entry must contain exactly A1 to A27.",
            }), 400

        cursor.execute("""
            SELECT id, loss_code, loss_name, loss_category
            FROM oee_loss_types
            WHERE is_active = 1
        """)
        master_rows = cursor.fetchall() or []
        master = {str(r.get("loss_code") or "").strip().upper(): r for r in master_rows}
        if set(master) != expected_codes:
            return jsonify({
                "success": False,
                "error": "Active OEE Loss Master must contain exactly A1 to A27.",
            }), 400

        # Replace saved grid for this activity
        cursor.execute(
            "DELETE FROM oee_entry_losses WHERE oee_entry_id = %s",
            (activity_run_id,),
        )

        for code in sorted(expected_codes, key=lambda v: int(v[1:])):
            minutes = float(submitted_map.get(code, 0) or 0)
            if minutes <= 0:
                continue
            master_row = master[code]
            cursor.execute("""
                INSERT INTO oee_entry_losses (
                    oee_entry_id, loss_type_id,
                    loss_code_snapshot, loss_name_snapshot, loss_category_snapshot,
                    loss_minutes, remarks
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                activity_run_id,
                master_row.get("id"),
                code,
                master_row.get("loss_name"),
                (master_row.get("loss_category") or "AR").upper(),
                minutes,
                None,
            ))

        cursor.execute("""
            SELECT
                id,
                oee_entry_id            AS activity_run_id,
                loss_type_id,
                loss_code_snapshot      AS loss_code,
                loss_name_snapshot      AS loss_name,
                loss_category_snapshot  AS loss_category,
                loss_minutes
            FROM oee_entry_losses
            WHERE oee_entry_id = %s
            ORDER BY CAST(SUBSTRING(loss_code_snapshot, 2) AS UNSIGNED), id
        """, (activity_run_id,))
        saved_rows = cursor.fetchall() or []
        for row in saved_rows:
            if row.get("loss_minutes") is not None:
                row["loss_minutes"] = float(row["loss_minutes"])

        total_loss_minutes = round(
            sum(float(v or 0) for v in submitted_map.values()),
            2,
        )

        conn.commit()

        return jsonify({
            "success": True,
            "activity_run_id": activity_run_id,
            "total_loss_minutes": total_loss_minutes,
            "losses": saved_rows,
            "message": "Activity OEE losses saved.",
        })

    except Exception as error:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# OEE_ACTIVITY_RUN_COMPLETE_API_V86
@quality_check_bp.route(
    "/api/oee-machine/activity-runs/complete",
    methods=["POST"]
)
def machine_oee_activity_run_complete_v86():

    conn = None
    cursor = None

    try:

        if str(
            session.get("role")
            or ""
        ).strip().lower() != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        try:
            activity_run_id = int(
                data.get(
                    "activity_run_id"
                )
            )

        except (
            TypeError,
            ValueError
        ):

            return jsonify({
                "success": False,
                "error":
                    "Valid activity_run_id is required."
            }), 400


        ended_at = str(
            data.get("ended_at")
            or ""
        ).strip()


        if not ended_at:

            return jsonify({
                "success": False,
                "error":
                    "Stop time is required."
            }), 400


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute(
            """
            SELECT
                e.id,
                e.id                AS session_id,
                e.machine_id,
                NULL                AS activity_master_id,
                e.activity_type     AS activity_group,
                e.item_name         AS activity_code,
                e.item_name         AS activity_name,
                e.remarks,
                e.created_at        AS started_at,
                NULL                AS ended_at,
                e.entry_state       AS status,
                e.start_time        AS start_time,
                e.entry_date        AS entry_date
            FROM oee_entries e
            WHERE e.id = %s
              AND e.activity_type IS NOT NULL
            LIMIT 1
            """,
            (
                activity_run_id,
            )
        )


        run = (
            cursor.fetchone()
            or None
        )


        if not run:

            return jsonify({
                "success": False,
                "error":
                    "Activity run was not found."
            }), 404


        if str(
            run.get("status")
            or ""
        ).strip().upper() != "RUNNING":

            return jsonify({
                "success": False,
                "error":
                    "Activity run is already completed "
                    "or is not in RUNNING status."
            }), 409


        # Compare operator-entered end time to the entry's own start_time+date.
        # Cross-midnight is allowed (valid_time = 1 in that case too).
        cursor.execute(
            """
            SELECT
                CASE
                    WHEN %s IS NULL OR %s IS NULL
                        THEN 0
                    ELSE 1
                END AS valid_time
            """,
            (
                run.get("start_time"),
                ended_at,
            )
        )


        time_check = (
            cursor.fetchone()
            or {}
        )


        if not bool(
            time_check.get(
                "valid_time"
            )
        ):

            return jsonify({
                "success": False,
                "error":
                    "Stop time must be after Start time."
            }), 400


        # Extract HH:MM:SS from the datetime string
        _end_str = str(ended_at or "").strip()
        _end_time_str = None
        try:
            from datetime import datetime as _dt
            _dt_obj = _dt.strptime(_end_str, "%Y-%m-%d %H:%M:%S")
            _end_time_str = _dt_obj.strftime("%H:%M:%S")
        except Exception:
            try:
                _parts = _end_str.split(" ")
                if len(_parts) >= 2:
                    tp = _parts[1].split(":")
                    if len(tp) == 2:
                        tp.append("00")
                    _end_time_str = ":".join(p.zfill(2) for p in tp[:3])
            except Exception:
                _end_time_str = None

        cursor.execute("""
            UPDATE oee_entries
            SET
                end_time      = %s,
                entry_state   = 'COMPLETED',
                record_status = 'active',
                updated_at    = CURRENT_TIMESTAMP
            WHERE id = %s
              AND activity_type IS NOT NULL
              AND UPPER(TRIM(entry_state)) = 'RUNNING'
        """, (
            _end_time_str,
            activity_run_id,
        ))

        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({
                "success": False,
                "error":
                    "Activity could not be completed "
                    "because its status changed.",
            }), 409

        # Compute activity totals (planned + AR loss + utilization)
        cursor.execute("""
            SELECT
                start_time, end_time,
                COALESCE((
                    SELECT SUM(loss_minutes)
                    FROM oee_entry_losses
                    WHERE oee_entry_id = %s
                ), 0) AS total_loss
            FROM oee_entries
            WHERE id = %s
            LIMIT 1
        """, (activity_run_id, activity_run_id))
        row = cursor.fetchone() or {}

        def _sec(v):
            if v is None:
                return None
            if hasattr(v, "hour"):
                return v.hour * 3600 + v.minute * 60 + v.second
            if hasattr(v, "total_seconds"):
                return int(v.total_seconds())
            return None

        s_sec = _sec(row.get("start_time"))
        e_sec = _sec(row.get("end_time"))
        if s_sec is not None and e_sec is not None:
            if e_sec >= s_sec:
                planned = (e_sec - s_sec) / 60.0
            else:
                planned = (86400 - s_sec + e_sec) / 60.0
        else:
            planned = 0.0

        ar_loss = float(row.get("total_loss") or 0)
        utilization = max(planned - ar_loss, 0.0)
        ar_ratio = (utilization / planned) if planned > 0 else 0.0

        cursor.execute("""
            UPDATE oee_entries
            SET
                planned_minutes         = %s,
                available_time_minutes  = %s,
                ar_loss_minutes         = %s,
                utilization_minutes     = %s,
                pr_loss_minutes         = 0,
                after_pr_minutes        = %s,
                total_loss_minutes      = %s,
                detailed_ar_ratio       = %s,
                detailed_pr_ratio       = NULL,
                detailed_qr_ratio       = NULL,
                detailed_oee_ratio      = NULL,
                updated_at              = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (
            round(planned, 2),
            round(planned, 2),
            round(ar_loss, 2),
            round(utilization, 2),
            round(utilization, 2),
            round(ar_loss, 2),
            round(ar_ratio, 8),
            activity_run_id,
        ))

        conn.commit()


        return jsonify({
            "success": True,

            "message":
                "Activity completed successfully.",

            "activity_run": {
                "id":
                    activity_run_id,

                "session_id":
                    run.get("session_id"),

                "machine_id":
                    run.get("machine_id"),

                "activity_group":
                    run.get("activity_group"),

                "activity_code":
                    run.get("activity_code"),

                "activity_name":
                    run.get("activity_name"),

                "remarks":
                    run.get("remarks"),

                "started_at":
                    (
                        run.get(
                            "started_at"
                        ).isoformat(
                            sep=" "
                        )
                        if run.get(
                            "started_at"
                        )
                        else None
                    ),

                "ended_at":
                    ended_at,

                "status":
                    "COMPLETED"
            }
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


# OEE_ACTIVITY_RUN_START_API_V85
@quality_check_bp.route(
    "/api/oee-machine/activity-runs/start",
    methods=["POST"]
)
def machine_oee_activity_run_start_v85():

    conn = None
    cursor = None

    try:

        if str(
            session.get("role")
            or ""
        ).strip().lower() != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        data = (
            request.get_json(
                silent=True
            )
            or {}
        )


        try:
            session_id = int(
                data.get("session_id")
            )

            machine_id = int(
                data.get("machine_id")
            )

            activity_master_id = int(
                data.get(
                    "activity_master_id"
                )
            )

        except (
            TypeError,
            ValueError
        ):

            return jsonify({
                "success": False,
                "error":
                    "Valid session_id, machine_id and "
                    "activity_master_id are required."
            }), 400


        started_at = str(
            data.get("started_at")
            or ""
        ).strip()


        if not started_at:

            return jsonify({
                "success": False,
                "error":
                    "Start time is required."
            }), 400


        remarks = str(
            data.get("remarks")
            or ""
        ).strip()


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # ----------------------------------------
        # Validate selected activity from master.
        # ----------------------------------------
        cursor.execute(
            """
            SELECT
                reference_id
                    AS id,

                reference_group
                    AS activity_group,

                reference_code
                    AS activity_code,

                reference_name
                    AS activity_name,

                COALESCE(
                    remarks_required,
                    0
                ) AS remarks_required

            FROM oee_reference_master

            WHERE
                reference_type = 'ACTIVITY'

                AND reference_id = %s

                AND is_active = 1

            LIMIT 1
            """,
            (
                activity_master_id,
            )
        )


        activity = (
            cursor.fetchone()
            or None
        )


        if not activity:

            return jsonify({
                "success": False,
                "error":
                    "Selected activity is not available."
            }), 400


        activity_group = str(
            activity.get(
                "activity_group"
            )
            or ""
        ).strip().upper()


        if activity_group not in (
            "TOOL_ROOM",
            "DEVELOPMENT"
        ):

            return jsonify({
                "success": False,
                "error":
                    "Only Tool Room or Development "
                    "activities are allowed."
            }), 400


        remarks_required = bool(
            activity.get(
                "remarks_required"
            )
        )


        if (
            remarks_required
            and not remarks
        ):

            return jsonify({
                "success": False,
                "error":
                    "Reason / remarks are required "
                    "for the selected activity."
            }), 400


        # ----------------------------------------
        # Prevent two non-production activities
        # running on the same machine.
        # ----------------------------------------
        cursor.execute(
            """
            SELECT
                id,
                item_name  AS activity_name,
                created_at AS started_at

            FROM oee_entries

            WHERE
                machine_id = %s
                AND activity_type IS NOT NULL
                AND UPPER(TRIM(entry_state)) = 'RUNNING'

            ORDER BY id DESC

            LIMIT 1
            """,
            (
                machine_id,
            )
        )


        existing_run = (
            cursor.fetchone()
            or None
        )


        if existing_run:

            return jsonify({
                "success": False,
                "error":
                    "Another Tool Room / Development "
                    "activity is already running on "
                    "this machine.",
                "running_activity": {
                    "id":
                        existing_run.get("id"),

                    "activity_name":
                        existing_run.get(
                            "activity_name"
                        ),

                    "started_at":
                        (
                            existing_run.get(
                                "started_at"
                            ).isoformat(
                                sep=" "
                            )
                            if existing_run.get(
                                "started_at"
                            )
                            else None
                        )
                }
            }), 409


        # OEE_ACTIVITY_OPERATOR_IDENTITY_V92
        #
        # Use the same operator identity principle as
        # the existing Production machine-run flow.
        #
        # operator_user_id = logged-in JMS / Zone account
        # operator_master_id = actual machine operator

        operator_user_id = (
            session.get("user_id")
            or session.get("id")
        )


        operator_master_id = None
        operator_employee_no = None

        operator_name = str(
            session.get("full_name")
            or session.get("username")
            or "Operator"
        ).strip()


        zone_login = (
            _get_oee_zone_login_v1(
                cursor
            )
        )


        if zone_login:

            requested_master_id = (
                data.get(
                    "operator_master_id"
                )
                or data.get(
                    "actual_operator_master_id"
                )
            )


            requested_employee_no = str(
                data.get(
                    "operator_employee_no"
                )
                or data.get(
                    "employee_no"
                )
                or ""
            ).strip()


            if (
                not requested_master_id
                and not requested_employee_no
            ):

                return jsonify({
                    "success": False,
                    "error":
                        "Please enter the actual machine operator."
                }), 400


            master_operator = (
                _oee_operator_master_resolve_v24(
                    cursor,
                    requested_master_id,
                    requested_employee_no,
                )
            )


            operator_master_id = (
                master_operator.get(
                    "id"
                )
            )


            operator_employee_no = (
                master_operator.get(
                    "employee_no"
                )
            )


            operator_name = (
                master_operator.get(
                    "operator_name"
                )
                or "Operator"
            )


        # ----------------------------------------
        # 2-table consolidation:
        # write activity directly into oee_entries
        # (activity_type = TOOL_ROOM / DEVELOPMENT).
        # ----------------------------------------
        # 2-table: no more oee_machine_sessions.  Take shift/date from
        # the request payload; entry_date defaults to CURDATE() in the
        # INSERT below when the payload does not supply one.
        _payload = request.get_json(silent=True) or {}
        entry_date_val = _payload.get("entry_date") or _payload.get("session_date")
        shift_name_val = str(_payload.get("shift_name") or "").strip() or "Shift 1"

        cursor.execute("""
            SELECT machine_no, machine_name, machine_category, zone
            FROM oee_machines
            WHERE id = %s
            LIMIT 1
        """, (machine_id,))
        m_info = cursor.fetchone() or {}

        _st = str(started_at or "").strip()
        _parts = _st.split(":")
        if len(_parts) == 2:
            _parts.append("00")
        _start_time = ":".join(p.zfill(2) for p in _parts[:3]) if len(_parts) >= 2 else None

        cursor.execute(
            """
            INSERT INTO oee_entries (
                machine_id,
                operator_user_id,
                operator_master_id,
                operator_employee_no,
                operator_name,

                entry_date,
                shift_name,

                job_card_no,
                item_name,
                process_name,

                machine_no,
                machine_name,
                machine_category,
                zone,

                start_time,

                cycle_minutes, cycle_seconds,
                load_unload_minutes, load_unload_seconds,
                ok_qty, rejected_qty, hold_qty,

                activity_type,
                entry_state,
                record_status,

                remarks
            )
            VALUES (
                %s,
                %s, %s, %s, %s,
                COALESCE(%s, CURDATE()),
                %s,
                '',
                %s, %s,
                %s, %s, %s, %s,
                %s,
                0, 0, 0, 0,
                0, 0, 0,
                %s,
                'RUNNING',
                'draft',
                %s
            )
            """,
            (
                machine_id,
                operator_user_id,
                operator_master_id,
                operator_employee_no,
                operator_name,
                entry_date_val,
                shift_name_val,
                activity.get("activity_name"),
                "Activity",
                m_info.get("machine_no"),
                m_info.get("machine_name"),
                m_info.get("machine_category"),
                m_info.get("zone"),
                _start_time,
                activity_group,
                remarks or None,
            ),
        )

        activity_run_id = cursor.lastrowid


        conn.commit()


        return jsonify({
            "success": True,

            "message":
                "Activity started successfully.",

            "activity_run": {
                "id":
                    activity_run_id,

                "session_id":
                    session_id,

                "machine_id":
                    machine_id,

                "activity_master_id":
                    activity_master_id,

                "activity_group":
                    activity_group,

                "activity_code":
                    activity.get(
                        "activity_code"
                    ),

                "activity_name":
                    activity.get(
                        "activity_name"
                    ),

                "remarks":
                    remarks or None,

                "operator_user_id":
                    operator_user_id,

                "operator_master_id":
                    operator_master_id,

                "operator_employee_no":
                    operator_employee_no,

                "operator_name":
                    operator_name,

                "started_at":
                    started_at,

                "status":
                    "RUNNING"
            }
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



# OEE_TOOLING_MASTER_API_V3
@quality_check_bp.route(
    "/api/oee-machine/tooling-master",
    methods=["GET"]
)
def machine_oee_tooling_master_v3():

    conn = None
    cursor = None

    try:

        if str(
            session.get("role")
            or ""
        ).strip().lower() != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                reference_id AS id,
                reference_code AS action_code,
                reference_name AS action_name,
                COALESCE(
                    enables_corner,
                    0
                ) AS enables_corner,
                reference_group AS reason_group,
                sort_order

            FROM oee_reference_master

            WHERE reference_type = 'TOOL_ACTION'
              AND is_active = 1

            ORDER BY
                sort_order,
                reference_id
        """)

        actions = (
            cursor.fetchall()
            or []
        )


        for row in actions:

            row["enables_corner"] = bool(
                row.get(
                    "enables_corner"
                )
            )


        cursor.execute("""
            SELECT
                reference_id AS id,
                reference_code AS corner_code,
                reference_name AS corner_name,
                sort_order

            FROM oee_reference_master

            WHERE reference_type = 'TOOL_CORNER'
              AND is_active = 1

            ORDER BY
                sort_order,
                reference_id
        """)

        corners = (
            cursor.fetchall()
            or []
        )


        cursor.execute("""
            SELECT
                reference_id AS id,
                reference_group AS reason_group,
                reference_code AS reason_code,
                reference_name AS reason_name,
                sort_order

            FROM oee_reference_master

            WHERE reference_type = 'TOOL_REASON'
              AND is_active = 1

            ORDER BY
                reference_group,
                sort_order,
                reference_id
        """)

        reason_rows = (
            cursor.fetchall()
            or []
        )


        reasons = {}


        for row in reason_rows:

            group = str(
                row.get(
                    "reason_group"
                )
                or ""
            ).strip().upper()


            if not group:
                continue


            reasons.setdefault(
                group,
                []
            ).append({
                "id":
                    row.get("id"),

                "reason_code":
                    row.get(
                        "reason_code"
                    )
                    or "",

                "reason_name":
                    row.get(
                        "reason_name"
                    )
                    or "",

                "sort_order":
                    row.get(
                        "sort_order"
                    )
                    or 0,
            })


        return jsonify({
            "success": True,
            "actions": actions,
            "corners": corners,
            "reasons": reasons,
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


# OEE_TOOL_ENTRY_PERSISTENCE_V4

def _ensure_oee_tool_entries_v4(cursor):
    """
    Create the Tool Position transaction table if it does not exist.

    Master tables remain the authority for Action, Corner and Reason.
    This table stores transaction snapshots for historical traceability.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oee_tool_entries (
            id BIGINT NOT NULL AUTO_INCREMENT,

            session_id BIGINT NOT NULL,
            machine_id INT NOT NULL,

            run_id BIGINT NULL,
            activity_run_id BIGINT NULL,

            operator_user_id INT NULL,
            operator_master_id INT NULL,
            operator_employee_no VARCHAR(50) NULL,
            operator_name VARCHAR(255) NULL,

            tool_position INT NOT NULL,
            tool_uid VARCHAR(100) NOT NULL,

            tool_action_master_id INT NOT NULL,
            tool_action_code VARCHAR(50) NOT NULL,
            tool_action_name VARCHAR(100) NOT NULL,

            corner_master_id INT NULL,
            corner_code VARCHAR(20) NULL,
            corner_name VARCHAR(50) NULL,

            change_reason_master_id INT NULL,
            reason_group VARCHAR(50) NULL,
            change_reason_code VARCHAR(50) NULL,
            change_reason_name VARCHAR(100) NULL,

            usage_per_part VARCHAR(100) NULL,

            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL
                DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

            PRIMARY KEY (id),

            UNIQUE KEY uq_oee_tool_run_position (
                run_id,
                tool_position
            ),

            UNIQUE KEY uq_oee_tool_activity_position (
                activity_run_id,
                tool_position
            ),

            INDEX idx_oee_tool_session (
                session_id,
                machine_id
            ),

            INDEX idx_oee_tool_uid (
                tool_uid
            ),

            INDEX idx_oee_tool_action (
                tool_action_master_id
            ),

            INDEX idx_oee_tool_corner (
                corner_master_id
            ),

            INDEX idx_oee_tool_reason (
                change_reason_master_id
            )
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
    """)


def _oee_tool_entry_rows_v4(cursor, run_id=0, activity_run_id=0, machine_loss_entry_id=0):
    if run_id > 0:
        cursor.execute("""
            SELECT
                id,
                session_id,
                machine_id,
                run_id,
                activity_run_id,
                machine_loss_entry_id,

                operator_user_id,
                operator_master_id,
                operator_employee_no,
                operator_name,

                tool_position,
                tool_uid,

                tool_action_master_id,
                tool_action_code,
                tool_action_name,

                corner_master_id,
                corner_code,
                corner_name,

                change_reason_master_id,
                reason_group,
                change_reason_code,
                change_reason_name,

                usage_per_part,

                created_at,
                updated_at

            FROM oee_tool_entries

            WHERE run_id = %s

            ORDER BY
                tool_position,
                id
        """, (
            run_id,
        ))

    elif activity_run_id > 0:
        cursor.execute("""
            SELECT
                id,
                session_id,
                machine_id,
                run_id,
                activity_run_id,
                machine_loss_entry_id,

                operator_user_id,
                operator_master_id,
                operator_employee_no,
                operator_name,

                tool_position,
                tool_uid,

                tool_action_master_id,
                tool_action_code,
                tool_action_name,

                corner_master_id,
                corner_code,
                corner_name,

                change_reason_master_id,
                reason_group,
                change_reason_code,
                change_reason_name,

                usage_per_part,

                created_at,
                updated_at

            FROM oee_tool_entries

            WHERE activity_run_id = %s

            ORDER BY
                tool_position,
                id
        """, (
            activity_run_id,
        ))

    elif machine_loss_entry_id > 0:
        cursor.execute("""
            SELECT
                id,
                session_id,
                machine_id,
                run_id,
                activity_run_id,
                machine_loss_entry_id,

                operator_user_id,
                operator_master_id,
                operator_employee_no,
                operator_name,

                tool_position,
                tool_uid,

                tool_action_master_id,
                tool_action_code,
                tool_action_name,

                corner_master_id,
                corner_code,
                corner_name,

                change_reason_master_id,
                reason_group,
                change_reason_code,
                change_reason_name,

                usage_per_part,

                created_at,
                updated_at

            FROM oee_tool_entries

            WHERE machine_loss_entry_id = %s

            ORDER BY
                tool_position,
                id
        """, (
            machine_loss_entry_id,
        ))

    else:
        return []

    rows = cursor.fetchall() or []

    for row in rows:
        for field in (
            "created_at",
            "updated_at",
        ):
            value = row.get(field)

            if (
                value is not None
                and hasattr(value, "isoformat")
            ):
                row[field] = value.isoformat(
                    sep=" "
                )

    return rows


@quality_check_bp.route(
    "/api/oee-machine/tooling-entries",
    methods=["GET", "POST"]
)
def machine_oee_tooling_entries_v4():
    """
    Read or replace Tool Position rows for one OEE context.

    Supported transaction contexts:
      1. Production machine run: run_id
      2. Tool Room / Development activity: activity_run_id

    Exactly one context ID is required for POST.

    GET without a context is a safe readiness check.
    """

    conn = None
    cursor = None

    try:
        role = str(
            session.get("role")
            or ""
        ).strip().lower()

        if role != "operator":
            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403

        if request.method == "GET":
            data = request.args
        else:
            data = (
                request.get_json(
                    silent=True
                )
                or {}
            )

        def positive_int(value):
            try:
                parsed = int(
                    value
                    or 0
                )
            except (
                TypeError,
                ValueError
            ):
                parsed = 0

            return parsed if parsed > 0 else 0

        run_id = positive_int(
            data.get("run_id")
        )

        activity_run_id = positive_int(
            data.get("activity_run_id")
        )

        machine_loss_entry_id = positive_int(
            data.get("machine_loss_entry_id")
        )

        provided_contexts = sum(
            1
            for value in (
                run_id,
                activity_run_id,
                machine_loss_entry_id,
            )
            if value > 0
        )

        if provided_contexts > 1:
            return jsonify({
                "success": False,
                "error": (
                    "Use exactly one of run_id, "
                    "activity_run_id or "
                    "machine_loss_entry_id."
                )
            }), 400

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        _ensure_oee_tool_entries_v4(
            cursor
        )

        # GET with no context is intentionally a readiness check.
        if (
            request.method == "GET"
            and run_id <= 0
            and activity_run_id <= 0
            and machine_loss_entry_id <= 0
        ):
            conn.commit()

            return jsonify({
                "success": True,
                "ready": True,
                "table": "oee_tool_entries",
                "entries": [],
                "message": (
                    "Tooling persistence backend is ready."
                )
            })

        if (
            run_id <= 0
            and activity_run_id <= 0
            and machine_loss_entry_id <= 0
        ):
            return jsonify({
                "success": False,
                "error": (
                    "run_id, activity_run_id or "
                    "machine_loss_entry_id is required."
                )
            }), 400

        context = None
        context_type = ""

        if run_id > 0:
            cursor.execute("""
                SELECT
                    id,
                    id                     AS session_id,
                    machine_id,
                    entry_state            AS context_status,

                    operator_user_id,
                    operator_master_id,
                    operator_employee_no,
                    operator_name

                FROM oee_entries

                WHERE id = %s
                  AND activity_type IS NULL

                LIMIT 1
            """, (
                run_id,
            ))

            context = (
                cursor.fetchone()
                or None
            )

            context_type = "RUN"

        elif activity_run_id > 0:
            cursor.execute("""
                SELECT
                    id,
                    id                     AS session_id,
                    machine_id,
                    entry_state            AS context_status,

                    operator_user_id,
                    operator_master_id,
                    operator_employee_no,
                    operator_name

                FROM oee_entries

                WHERE id = %s
                  AND activity_type IN ('TOOL_ROOM', 'DEVELOPMENT')

                LIMIT 1
            """, (
                activity_run_id,
            ))

            context = (
                cursor.fetchone()
                or None
            )

            context_type = "ACTIVITY"

        else:
            cursor.execute("""
                SELECT
                    id,
                    id                     AS session_id,
                    machine_id,
                    entry_state            AS context_status,

                    operator_user_id,
                    operator_master_id,
                    operator_employee_no,
                    operator_name

                FROM oee_entries

                WHERE id = %s
                  AND activity_type = 'MACHINE_LOSS'

                LIMIT 1
            """, (
                machine_loss_entry_id,
            ))

            context = (
                cursor.fetchone()
                or None
            )

            context_type = "MACHINE_LOSS"

        if not context:
            return jsonify({
                "success": False,
                "error": (
                    "Tooling transaction context "
                    "was not found."
                )
            }), 404

        login_user_id = positive_int(
            session.get("user_id")
            or session.get("id")
        )

        context_user_id = positive_int(
            context.get(
                "operator_user_id"
            )
        )

        if (
            login_user_id > 0
            and context_user_id > 0
            and login_user_id != context_user_id
        ):
            return jsonify({
                "success": False,
                "error": (
                    "This tooling transaction belongs "
                    "to another operator login."
                )
            }), 403

        if request.method == "GET":
            rows = _oee_tool_entry_rows_v4(
                cursor,
                run_id=run_id,
                activity_run_id=activity_run_id,
                machine_loss_entry_id=machine_loss_entry_id,
            )

            return jsonify({
                "success": True,
                "context_type": context_type,
                "run_id": run_id or None,
                "activity_run_id":
                    activity_run_id or None,
                "machine_loss_entry_id":
                    machine_loss_entry_id or None,
                "entries": rows,
                "count": len(rows),
            })

        context_status = str(
            context.get(
                "context_status"
            )
            or ""
        ).strip().upper()

        if context_type == "RUN":
            allowed_statuses = {
                "RUNNING",
                "HANDOVER_PENDING",
                "COMPLETED",   # last-mile tool save right after JC completion
            }

        elif context_type == "ACTIVITY":
            allowed_statuses = {
                "RUNNING",
                "COMPLETED",   # last-mile tool save right after activity completion
            }

        else:
            # MACHINE_LOSS rows are inserted already COMPLETED.
            allowed_statuses = {
                "COMPLETED",
            }

        if context_status not in allowed_statuses:
            return jsonify({
                "success": False,
                "error": (
                    "Tooling entries cannot be changed "
                    "because the context is "
                    + (
                        context_status
                        or "closed"
                    )
                    + "."
                )
            }), 409

        tool_rows = data.get(
            "tool_rows"
        )

        if not isinstance(
            tool_rows,
            list
        ):
            return jsonify({
                "success": False,
                "error": (
                    "tool_rows must be a list."
                )
            }), 400

        if len(tool_rows) > 50:
            return jsonify({
                "success": False,
                "error": (
                    "Maximum 50 Tool Position rows "
                    "are allowed in one save."
                )
            }), 400

        # DB master remains the authority.
        cursor.execute("""
            SELECT
                reference_id
                    AS id,

                reference_code
                    AS action_code,

                reference_name
                    AS action_name,

                COALESCE(
                    enables_corner,
                    0
                ) AS enables_corner,

                reference_group
                    AS reason_group

            FROM oee_reference_master

            WHERE reference_type = 'TOOL_ACTION'
              AND is_active = 1
        """)

        action_master = {
            int(row["id"]): row
            for row in (
                cursor.fetchall()
                or []
            )
        }

        cursor.execute("""
            SELECT
                reference_id
                    AS id,

                reference_code
                    AS corner_code,

                reference_name
                    AS corner_name

            FROM oee_reference_master

            WHERE reference_type = 'TOOL_CORNER'
              AND is_active = 1
        """)

        corner_master = {
            int(row["id"]): row
            for row in (
                cursor.fetchall()
                or []
            )
        }

        cursor.execute("""
            SELECT
                reference_id
                    AS id,

                reference_group
                    AS reason_group,

                reference_code
                    AS reason_code,

                reference_name
                    AS reason_name,

                parent_reference_id
                    AS tool_action_parent_id

            FROM oee_reference_master

            WHERE reference_type = 'TOOL_REASON'
              AND is_active = 1
        """)

        reason_master = {
            int(row["id"]): row
            for row in (
                cursor.fetchall()
                or []
            )
        }

        prepared = []
        seen_positions = set()

        for index, item in enumerate(
            tool_rows,
            start=1
        ):
            if not isinstance(
                item,
                dict
            ):
                return jsonify({
                    "success": False,
                    "error": (
                        "Invalid Tool Position row."
                    )
                }), 400

            tool_uid = str(
                item.get("tool_uid")
                or ""
            ).strip()

            usage_per_part = str(
                item.get("usage_per_part")
                or ""
            ).strip()

            action_master_id = positive_int(
                item.get(
                    "tool_action_master_id"
                )
            )

            corner_master_id = positive_int(
                item.get(
                    "corner_master_id"
                )
            )

            reason_master_id = positive_int(
                item.get(
                    "change_reason_master_id"
                )
            )

            # Completely blank UI rows are ignored.
            if not any((
                tool_uid,
                usage_per_part,
                action_master_id,
                corner_master_id,
                reason_master_id,
            )):
                continue

            try:
                tool_position = int(
                    item.get(
                        "tool_position"
                    )
                    or index
                )
            except (
                TypeError,
                ValueError
            ):
                tool_position = 0

            if tool_position <= 0:
                return jsonify({
                    "success": False,
                    "error": (
                        "Tool Position must be "
                        "a positive whole number."
                    )
                }), 400

            if tool_position in seen_positions:
                return jsonify({
                    "success": False,
                    "error": (
                        "Duplicate Tool Position: "
                        + str(tool_position)
                    )
                }), 400

            seen_positions.add(
                tool_position
            )

            if not tool_uid:
                return jsonify({
                    "success": False,
                    "error": (
                        "Tool UID is required for "
                        "Tool Position "
                        + str(tool_position)
                        + "."
                    )
                }), 400

            action = action_master.get(
                action_master_id
            )

            if not action:
                return jsonify({
                    "success": False,
                    "error": (
                        "Select a valid Tool Action for "
                        "Tool Position "
                        + str(tool_position)
                        + "."
                    )
                }), 400

            action_code = str(
                action.get(
                    "action_code"
                )
                or ""
            ).strip().upper()

            enables_corner = bool(
                action.get(
                    "enables_corner"
                )
            )

            reason_group = str(
                action.get(
                    "reason_group"
                )
                or ""
            ).strip().upper()

            corner = None
            reason = None

            if enables_corner:
                corner = corner_master.get(
                    corner_master_id
                )

                if not corner:
                    return jsonify({
                        "success": False,
                        "error": (
                            "Select Corner for Tool Position "
                            + str(tool_position)
                            + "."
                        )
                    }), 400

            elif corner_master_id > 0:
                return jsonify({
                    "success": False,
                    "error": (
                        "Corner can be selected only when "
                        "Tool Action allows Corner Change."
                    )
                }), 400

            if reason_group:
                reason = reason_master.get(
                    reason_master_id
                )

                if not reason:
                    return jsonify({
                        "success": False,
                        "error": (
                            "Select Change Reason for "
                            "Tool Position "
                            + str(tool_position)
                            + "."
                        )
                    }), 400

                selected_group = str(
                    reason.get(
                        "reason_group"
                    )
                    or ""
                ).strip().upper()

                if selected_group != reason_group:
                    return jsonify({
                        "success": False,
                        "error": (
                            "Selected Change Reason does not "
                            "match Tool Action for Tool Position "
                            + str(tool_position)
                            + "."
                        )
                    }), 400

            elif reason_master_id > 0:
                return jsonify({
                    "success": False,
                    "error": (
                        "Change Reason is not allowed for "
                        "the selected Tool Action."
                    )
                }), 400

            prepared.append({
                "session_id":
                    context.get(
                        "session_id"
                    ),

                "machine_id":
                    context.get(
                        "machine_id"
                    ),

                "run_id":
                    run_id or None,

                "activity_run_id":
                    activity_run_id or None,

                "machine_loss_entry_id":
                    machine_loss_entry_id or None,

                "operator_user_id":
                    context.get(
                        "operator_user_id"
                    ),

                "operator_master_id":
                    context.get(
                        "operator_master_id"
                    ),

                "operator_employee_no":
                    context.get(
                        "operator_employee_no"
                    ),

                "operator_name":
                    context.get(
                        "operator_name"
                    ),

                "tool_position":
                    tool_position,

                "tool_uid":
                    tool_uid,

                "tool_action_master_id":
                    action_master_id,

                "tool_action_code":
                    action_code,

                "tool_action_name":
                    str(
                        action.get(
                            "action_name"
                        )
                        or ""
                    ).strip(),

                "corner_master_id":
                    (
                        corner_master_id
                        if corner
                        else None
                    ),

                "corner_code":
                    (
                        str(
                            corner.get(
                                "corner_code"
                            )
                            or ""
                        ).strip()
                        if corner
                        else None
                    ),

                "corner_name":
                    (
                        str(
                            corner.get(
                                "corner_name"
                            )
                            or ""
                        ).strip()
                        if corner
                        else None
                    ),

                "change_reason_master_id":
                    (
                        reason_master_id
                        if reason
                        else None
                    ),

                "reason_group":
                    reason_group or None,

                "change_reason_code":
                    (
                        str(
                            reason.get(
                                "reason_code"
                            )
                            or ""
                        ).strip()
                        if reason
                        else None
                    ),

                "change_reason_name":
                    (
                        str(
                            reason.get(
                                "reason_name"
                            )
                            or ""
                        ).strip()
                        if reason
                        else None
                    ),

                "usage_per_part":
                    usage_per_part or None,
            })


        # ================================================================
        # OEE_TOOL_UID_BACKEND_GUARD_V123
        # Every submitted Tool UID must exist in oee_tool_uid AND be
        # linked to an ACTIVE oee_tool_master.  Independent of the
        # V117 / V118 frontend guard, so a direct API caller cannot
        # persist unregistered UIDs.
        # ================================================================
        submitted_uids = sorted({
            row["tool_uid"]
            for row in prepared
            if row.get("tool_uid")
        })

        if submitted_uids:
            uid_placeholders = ",".join(
                ["%s"] * len(submitted_uids)
            )

            cursor.execute(
                "SELECT u.tool_uid "
                "  FROM oee_tool_uid u "
                "  JOIN oee_tool_master m "
                "    ON m.id = u.tool_master_id "
                " WHERE u.tool_uid IN (" + uid_placeholders + ") "
                "   AND COALESCE(m.is_active, 0) = 1",
                submitted_uids,
            )

            found_uids = {
                str(r.get("tool_uid") or "").strip()
                for r in (cursor.fetchall() or [])
            }

            missing_uids = [
                uid
                for uid in submitted_uids
                if uid not in found_uids
            ]

            if missing_uids:
                return jsonify({
                    "success": False,
                    "error": (
                        "Tool UID "
                        + missing_uids[0]
                        + " is not registered."
                    ),
                    "missing_tool_uids": missing_uids,
                }), 400


        # Replace one context atomically.
        conn.commit()
        conn.start_transaction()

        if run_id > 0:
            cursor.execute("""
                DELETE FROM oee_tool_entries
                WHERE run_id = %s
            """, (
                run_id,
            ))

        elif activity_run_id > 0:
            cursor.execute("""
                DELETE FROM oee_tool_entries
                WHERE activity_run_id = %s
            """, (
                activity_run_id,
            ))

        else:
            cursor.execute("""
                DELETE FROM oee_tool_entries
                WHERE machine_loss_entry_id = %s
            """, (
                machine_loss_entry_id,
            ))

        if prepared:
            values = []

            for row in prepared:
                values.append((
                    row["session_id"],
                    row["machine_id"],
                    row["run_id"],
                    row["activity_run_id"],
                    row["machine_loss_entry_id"],

                    row["operator_user_id"],
                    row["operator_master_id"],
                    row["operator_employee_no"],
                    row["operator_name"],

                    row["tool_position"],
                    row["tool_uid"],

                    row["tool_action_master_id"],
                    row["tool_action_code"],
                    row["tool_action_name"],

                    row["corner_master_id"],
                    row["corner_code"],
                    row["corner_name"],

                    row["change_reason_master_id"],
                    row["reason_group"],
                    row["change_reason_code"],
                    row["change_reason_name"],

                    row["usage_per_part"],
                ))

            cursor.executemany("""
                INSERT INTO oee_tool_entries (
                    session_id,
                    machine_id,
                    run_id,
                    activity_run_id,
                    machine_loss_entry_id,

                    operator_user_id,
                    operator_master_id,
                    operator_employee_no,
                    operator_name,

                    tool_position,
                    tool_uid,

                    tool_action_master_id,
                    tool_action_code,
                    tool_action_name,

                    corner_master_id,
                    corner_code,
                    corner_name,

                    change_reason_master_id,
                    reason_group,
                    change_reason_code,
                    change_reason_name,

                    usage_per_part
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s
                )
            """, values)

        conn.commit()

        rows = _oee_tool_entry_rows_v4(
            cursor,
            run_id=run_id,
            activity_run_id=activity_run_id,
            machine_loss_entry_id=machine_loss_entry_id,
        )

        return jsonify({
            "success": True,
            "context_type": context_type,
            "run_id": run_id or None,
            "activity_run_id":
                activity_run_id or None,
            "machine_loss_entry_id":
                machine_loss_entry_id or None,
            "saved_count": len(rows),
            "entries": rows,
            "message": (
                "Tool Position entries saved successfully."
            )
        })

    except ValueError as e:
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 400

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


# OEE_TOOL_ENTRY_PERSISTENCE_V4_END

# OEE_ACTIVITY_MASTER_API_V84

# =========================================================
# OEE_TOOL_UID_LOOKUP_API_V112
#
# READ ONLY Tool Master lookup.
# Used for Supervisor Tool UID registration.
# =========================================================

@quality_check_bp.route(
    "/api/oee-machine/tool-master/lookup",
    methods=["GET"]
)
def machine_oee_tool_master_lookup_v112():

    from flask import (
        jsonify,
        request,
        session as flask_session,
    )

    conn = None
    cursor = None

    try:

        role = str(
            flask_session.get("role")
            or ""
        ).strip().lower()

        user_id = flask_session.get(
            "user_id"
        )

        if (
            role not in (
                "admin",
                "supervisor",
            )
            or not user_id
        ):

            return jsonify({
                "success": False,
                "error":
                    "Admin or Supervisor access required."
            }), 403


        tool_item_code = str(
            request.args.get("code")
            or ""
        ).strip()

        if not tool_item_code:

            return jsonify({
                "success": False,
                "error":
                    "Tool Item Code is required."
            }), 400


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        sql = (
            "SELECT "
            "id, "
            "tool_item_code, "
            "tool_item_name, "
            "uid_prefix "
            "FROM oee_tool_master "
            "WHERE is_active = 1 "
            "AND UPPER(TRIM(tool_item_code)) "
            "= UPPER(TRIM(%s)) "
            "LIMIT 1"
        )


        cursor.execute(
            sql,
            (
                tool_item_code,
            )
        )


        tool = cursor.fetchone()


        if not tool:

            return jsonify({
                "success": False,
                "error":
                    "Tool Item Code not found."
            }), 404


        uid_prefix = str(
            tool.get("uid_prefix")
            or ""
        ).strip()


        if not uid_prefix:

            return jsonify({
                "success": False,
                "error":
                    "UID Prefix is not configured "
                    "for this Tool Item."
            }), 400


        return jsonify({
            "success": True,

            "tool": {
                "id":
                    tool.get("id"),

                "tool_item_code":
                    tool.get("tool_item_code"),

                "tool_item_name":
                    tool.get("tool_item_name"),

                "uid_prefix":
                    uid_prefix,
            }
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


# OEE_TOOL_UID_LOOKUP_API_V112_END

# =========================================================
# OEE_TOOL_UID_REGISTER_PAGE_V115
# =========================================================

@quality_check_bp.route(
    "/oee-tool-uid-register",
    methods=["GET"]
)
def machine_oee_tool_uid_register_page_v115():

    from flask import render_template

    role = str(
        session.get("role")
        or ""
    ).strip().lower()


    if role not in (
        "admin",
        "supervisor",
    ):

        return (
            "This page is available only "
            "for Admin and Supervisor.",
            403
        )


    return render_template(
        "oee_tool_uid_register.html",
        active_page="oee_tool_uid_register",
    )


# OEE_TOOL_UID_REGISTER_PAGE_V115_END


# =========================================================
# OEE_TOOL_MASTER_LIST_API_V126
# Read-only listing of oee_tool_master rows for Admin/Supervisor.
# =========================================================

@quality_check_bp.route(
    "/api/oee-machine/tool-master/list",
    methods=["GET"]
)
def machine_oee_tool_master_list_v126():
    from flask import jsonify, session as flask_session

    role = str(flask_session.get("role") or "").strip().lower()
    user_id = flask_session.get("user_id")

    if role not in ("admin", "supervisor") or not user_id:
        return jsonify({
            "success": False,
            "error": "Admin or Supervisor access required."
        }), 403

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                id,
                tool_item_code,
                tool_item_name,
                uid_prefix,
                is_active,
                created_at
            FROM oee_tool_master
            ORDER BY tool_item_code ASC
        """)
        rows = cursor.fetchall() or []
        for r in rows:
            v = r.get("created_at")
            if v is not None and hasattr(v, "isoformat"):
                r["created_at"] = v.isoformat(sep=" ")

        return jsonify({
            "success": True,
            "count": len(rows),
            "tools": rows,
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

# OEE_TOOL_MASTER_LIST_API_V126_END


# =========================================================
# OEE_TOOL_MASTER_CREATE_API_V127
# Create a new oee_tool_master row (Admin/Supervisor only).
# Unique on tool_item_code and tool_item_name.
# =========================================================

@quality_check_bp.route(
    "/api/oee-machine/tool-master/create",
    methods=["POST"]
)
def machine_oee_tool_master_create_v127():
    from flask import jsonify, request, session as flask_session

    role = str(flask_session.get("role") or "").strip().lower()
    user_id = flask_session.get("user_id")

    if role not in ("admin", "supervisor") or not user_id:
        return jsonify({
            "success": False,
            "error": "Admin or Supervisor access required."
        }), 403

    data = request.get_json(silent=True) or {}

    tool_item_code = str(data.get("tool_item_code") or "").strip()
    tool_item_name = str(data.get("tool_item_name") or "").strip()
    uid_prefix = str(data.get("uid_prefix") or "").strip()

    if not tool_item_code:
        return jsonify({
            "success": False,
            "error": "Tool Item Code is required."
        }), 400
    if not tool_item_name:
        return jsonify({
            "success": False,
            "error": "Tool Item Name is required."
        }), 400
    if not uid_prefix:
        return jsonify({
            "success": False,
            "error": "UID Prefix is required."
        }), 400

    if len(tool_item_code) > 50:
        return jsonify({
            "success": False,
            "error": "Tool Item Code max length is 50."
        }), 400
    if len(tool_item_name) > 255:
        return jsonify({
            "success": False,
            "error": "Tool Item Name max length is 255."
        }), 400
    if len(uid_prefix) > 50:
        return jsonify({
            "success": False,
            "error": "UID Prefix max length is 50."
        }), 400

    raw_active = data.get("is_active")
    if raw_active is None:
        is_active = 1
    else:
        try:
            is_active = 1 if int(raw_active) else 0
        except (TypeError, ValueError):
            is_active = (
                1
                if str(raw_active).strip().lower()
                in ("1", "true", "yes", "on")
                else 0
            )

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id FROM oee_tool_master "
            " WHERE tool_item_code = %s LIMIT 1",
            (tool_item_code,)
        )
        if cursor.fetchone():
            return jsonify({
                "success": False,
                "error": "Tool Item Code already exists."
            }), 400

        cursor.execute(
            "SELECT id FROM oee_tool_master "
            " WHERE tool_item_name = %s LIMIT 1",
            (tool_item_name,)
        )
        if cursor.fetchone():
            return jsonify({
                "success": False,
                "error": "Tool Item Name already exists."
            }), 400

        cursor.execute("""
            INSERT INTO oee_tool_master (
                tool_item_code,
                tool_item_name,
                uid_prefix,
                is_active
            )
            VALUES (%s, %s, %s, %s)
        """, (
            tool_item_code,
            tool_item_name,
            uid_prefix,
            is_active,
        ))
        new_id = cursor.lastrowid
        conn.commit()

        return jsonify({
            "success": True,
            "tool_master_id": new_id,
            "tool_item_code": tool_item_code,
            "tool_item_name": tool_item_name,
            "uid_prefix": uid_prefix,
            "is_active": is_active,
            "message": "Tool Item added to master."
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

# OEE_TOOL_MASTER_CREATE_API_V127_END


# =========================================================
# OEE_TOOL_UID_GENERATE_API_V113
#
# Creates a NEW physical Tool UID.
#
# Format:
# <UID PREFIX>-<YYMM>-<GLOBAL SERIAL>
#
# Example:
# DR-2609-00026
#
# R0 only in this stage.
# =========================================================

@quality_check_bp.route(
    "/api/oee-machine/tool-uid/generate",
    methods=["POST"]
)
def machine_oee_tool_uid_generate_v113():

    from datetime import date, datetime

    from flask import (
        jsonify,
        request,
        session as flask_session,
    )

    conn = None
    cursor = None

    try:

        # ---------------------------------------------
        # ACCESS
        # ---------------------------------------------

        role = str(
            flask_session.get("role")
            or ""
        ).strip().lower()

        user_id = flask_session.get(
            "user_id"
        )

        if (
            role not in (
                "admin",
                "supervisor",
            )
            or not user_id
        ):

            return jsonify({
                "success": False,
                "error":
                    "Admin or Supervisor access required."
            }), 403


        # ---------------------------------------------
        # INPUT
        # ---------------------------------------------

        payload = (
            request.get_json(
                silent=True
            )
            or {}
        )

        tool_item_code = str(
            payload.get(
                "tool_item_code"
            )
            or ""
        ).strip()

        if not tool_item_code:

            return jsonify({
                "success": False,
                "error":
                    "Tool Item Code is required."
            }), 400


        date_text = str(
            payload.get(
                "created_regrind_date"
            )
            or ""
        ).strip()

        if date_text:

            try:

                created_date = (
                    datetime.strptime(
                        date_text,
                        "%Y-%m-%d"
                    ).date()
                )

            except ValueError:

                return jsonify({
                    "success": False,
                    "error":
                        "Created Date must be YYYY-MM-DD."
                }), 400

        else:

            created_date = date.today()


        remark = str(
            payload.get("remark")
            or ""
        ).strip()

        if len(remark) > 500:

            return jsonify({
                "success": False,
                "error":
                    "Remark cannot exceed 500 characters."
            }), 400


        # ---------------------------------------------
        # DB
        # ---------------------------------------------

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        tool_sql = (
            "SELECT "
            "id, "
            "tool_item_code, "
            "tool_item_name, "
            "uid_prefix "
            "FROM oee_tool_master "
            "WHERE is_active = 1 "
            "AND UPPER(TRIM(tool_item_code)) "
            "= UPPER(TRIM(%s)) "
            "LIMIT 1"
        )


        cursor.execute(
            tool_sql,
            (
                tool_item_code,
            )
        )


        tool = cursor.fetchone()


        if not tool:

            return jsonify({
                "success": False,
                "error":
                    "Tool Item Code not found."
            }), 404


        uid_prefix = str(
            tool.get("uid_prefix")
            or ""
        ).strip()


        if not uid_prefix:

            return jsonify({
                "success": False,
                "error":
                    "UID Prefix is not configured "
                    "for this Tool Item."
            }), 400


        tool_master_id = int(
            tool["id"]
        )


        # Finish implicit SELECT transaction.
        conn.commit()


        # ---------------------------------------------
        # GENERATE GLOBAL SERIAL
        # ---------------------------------------------

        conn.start_transaction()


        insert_sql = (
            "INSERT INTO oee_tool_uid "
            "("
            "tool_master_id, "
            "tool_uid, "
            "base_uid, "
            "created_regrind_date, "
            "regrind_cycle, "
            "status, "
            "parent_uid_serial, "
            "remark, "
            "created_by_user_id"
            ") "
            "VALUES "
            "("
            "%s, "
            "NULL, "
            "NULL, "
            "%s, "
            "'R0', "
            "'AVAILABLE', "
            "NULL, "
            "%s, "
            "%s"
            ")"
        )


        cursor.execute(
            insert_sql,
            (
                tool_master_id,
                created_date,
                (
                    remark
                    if remark
                    else None
                ),
                user_id,
            )
        )


        uid_serial = int(
            cursor.lastrowid
            or 0
        )


        if uid_serial <= 0:

            raise RuntimeError(
                "Global UID Serial could not be generated."
            )


        # ---------------------------------------------
        # BUILD UID
        # ---------------------------------------------

        tool_uid = (
            uid_prefix
            + "-"
            + created_date.strftime(
                "%y%m"
            )
            + "-"
            + str(
                uid_serial
            ).zfill(5)
        )


        if len(tool_uid) > 100:

            raise RuntimeError(
                "Generated Tool UID exceeds "
                "100 characters."
            )


        # R0:
        # Base UID = Entry Tool UID
        base_uid = tool_uid


        update_sql = (
            "UPDATE oee_tool_uid "
            "SET "
            "tool_uid = %s, "
            "base_uid = %s "
            "WHERE uid_serial = %s"
        )


        cursor.execute(
            update_sql,
            (
                tool_uid,
                base_uid,
                uid_serial,
            )
        )


        if cursor.rowcount != 1:

            raise RuntimeError(
                "Generated Tool UID could not be saved."
            )


        # ---------------------------------------------
        # VERIFY BEFORE COMMIT
        # ---------------------------------------------

        verify_sql = (
            "SELECT "
            "uid_serial, "
            "tool_master_id, "
            "tool_uid, "
            "base_uid, "
            "created_regrind_date, "
            "regrind_cycle, "
            "status "
            "FROM oee_tool_uid "
            "WHERE uid_serial = %s "
            "LIMIT 1"
        )


        cursor.execute(
            verify_sql,
            (
                uid_serial,
            )
        )


        created = cursor.fetchone()


        if not created:

            raise RuntimeError(
                "Generated Tool UID verification failed."
            )


        if (
            str(
                created.get("tool_uid")
                or ""
            )
            != tool_uid
        ):

            raise RuntimeError(
                "Generated Tool UID verification mismatch."
            )


        conn.commit()


        # ---------------------------------------------
        # RESPONSE
        # ---------------------------------------------

        return jsonify({
            "success": True,

            "tool_uid": {
                "uid_serial":
                    uid_serial,

                "tool_uid":
                    tool_uid,

                "base_uid":
                    base_uid,

                "regrind_cycle":
                    "R0",

                "status":
                    "AVAILABLE",

                "created_regrind_date":
                    created_date.isoformat(),

                "tool_master_id":
                    tool_master_id,

                "tool_item_code":
                    tool.get(
                        "tool_item_code"
                    ),

                "tool_item_name":
                    tool.get(
                        "tool_item_name"
                    ),

                "uid_prefix":
                    uid_prefix,
            }
        })


    except Exception as error:

        if conn:

            try:
                conn.rollback()
            except Exception:
                pass


        return jsonify({
            "success": False,
            "error": str(error),
        }), 500


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# OEE_TOOL_UID_GENERATE_API_V113_END
# =========================================================
# OEE_TOOL_UID_OPERATOR_LOOKUP_V116
#
# Resolves a registered physical Tool UID back to:
# - Tool Item Code
# - Tool Item Name
# - Status
# - Regrind Cycle
#
# READ ONLY
# =========================================================

@quality_check_bp.route(
    "/api/oee-machine/tool-uid/lookup",
    methods=["GET"]
)
def machine_oee_tool_uid_lookup_v116():

    from flask import (
        jsonify,
        request,
        session as flask_session,
    )

    conn = None
    cursor = None

    try:

        role = str(
            flask_session.get("role")
            or ""
        ).strip().lower()


        if role not in (
            "admin",
            "supervisor",
            "operator",
        ):

            return jsonify({
                "success": False,
                "error":
                    "OEE access required."
            }), 403


        tool_uid = str(
            request.args.get("uid")
            or ""
        ).strip()


        if not tool_uid:

            return jsonify({
                "success": False,
                "error":
                    "Tool UID is required."
            }), 400


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        sql = (
            "SELECT "
            "u.uid_serial, "
            "u.tool_uid, "
            "u.base_uid, "
            "u.regrind_cycle, "
            "u.status, "
            "u.created_regrind_date, "
            "m.id AS tool_master_id, "
            "m.tool_item_code, "
            "m.tool_item_name, "
            "m.uid_prefix "
            "FROM oee_tool_uid u "
            "INNER JOIN oee_tool_master m "
            "ON m.id = u.tool_master_id "
            "WHERE "
            "UPPER(TRIM(u.tool_uid)) "
            "= UPPER(TRIM(%s)) "
            "AND m.is_active = 1 "
            "LIMIT 1"
        )


        cursor.execute(
            sql,
            (
                tool_uid,
            )
        )


        row = cursor.fetchone()


        if not row:

            return jsonify({
                "success": False,
                "error":
                    "Tool UID not found."
            }), 404


        return jsonify({
            "success": True,

            "tool": {
                "uid_serial":
                    row.get(
                        "uid_serial"
                    ),

                "tool_uid":
                    row.get(
                        "tool_uid"
                    ),

                "base_uid":
                    row.get(
                        "base_uid"
                    ),

                "regrind_cycle":
                    row.get(
                        "regrind_cycle"
                    ),

                "status":
                    row.get(
                        "status"
                    ),

                "tool_master_id":
                    row.get(
                        "tool_master_id"
                    ),

                "tool_item_code":
                    row.get(
                        "tool_item_code"
                    ),

                "tool_item_name":
                    row.get(
                        "tool_item_name"
                    ),

                "uid_prefix":
                    row.get(
                        "uid_prefix"
                    ),
            }
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


# OEE_TOOL_UID_OPERATOR_LOOKUP_V116_END






@quality_check_bp.route(
    "/api/oee-machine/activity-master",
    methods=["GET"]
)
def machine_oee_activity_master_v84():

    conn = None
    cursor = None

    try:

        if str(
            session.get("role")
            or ""
        ).strip().lower() != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                reference_id AS id,
                reference_group AS activity_group,
                reference_code AS activity_code,
                reference_name AS activity_name,
                COALESCE(
                    remarks_required,
                    0
                ) AS remarks_required,
                sort_order

            FROM oee_reference_master

            WHERE reference_type = 'ACTIVITY'
              AND is_active = 1

            ORDER BY
                FIELD(
                    reference_group,
                    'TOOL_ROOM',
                    'DEVELOPMENT'
                ),
                sort_order,
                reference_id
        """)


        rows = (
            cursor.fetchall()
            or []
        )


        tool_room = []
        development = []


        for row in rows:

            item = {
                "id":
                    row.get("id"),

                "activity_code":
                    row.get("activity_code")
                    or "",

                "activity_name":
                    row.get("activity_name")
                    or "",

                "remarks_required":
                    bool(
                        row.get(
                            "remarks_required"
                        )
                    ),

                "sort_order":
                    row.get("sort_order")
                    or 0,
            }


            group = str(
                row.get("activity_group")
                or ""
            ).strip().upper()


            if group == "TOOL_ROOM":

                tool_room.append(
                    item
                )

            elif group == "DEVELOPMENT":

                development.append(
                    item
                )


        return jsonify({
            "success": True,

            "tool_room":
                tool_room,

            "development":
                development,

            "counts": {
                "tool_room":
                    len(tool_room),

                "development":
                    len(development),
            }
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


@quality_check_bp.route(
    "/api/oee-machine/loss-master",
    methods=["GET"]
)
def machine_oee_loss_master_v1():

    conn = None
    cursor = None

    try:

        if str(
            session.get("role")
            or ""
        ).strip().lower() != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT *
            FROM oee_loss_types
            ORDER BY id
        """)


        rows = (
            cursor.fetchall()
            or []
        )


        losses = []


        for row in rows:

            normalized = (
                _machine_oee_loss_master_row_v1(
                    row
                )
            )


            if not normalized:
                continue


            code = str(
                normalized.get("loss_code")
                or ""
            ).strip().upper()


            if (
                code.startswith("A")
                and code[1:].isdigit()
                and 1 <= int(code[1:]) <= 27
            ):

                normalized["loss_code"] = code

                losses.append(
                    normalized
                )


        losses.sort(
            key=lambda row:
                int(
                    str(
                        row["loss_code"]
                    )[1:]
                )
        )


        return jsonify({
            "success": True,
            "losses": losses
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


# MACHINE_OEE_RUN_LINKED_LOSS_GRID_V40
@quality_check_bp.route(
    "/api/oee-machine/run/<int:run_id>/losses",
    methods=["GET", "POST"]
)
def machine_oee_run_losses_v1(run_id):
    """
    Losses for one production entry (oee_entries id).
    Consolidated: writes/reads oee_entry_losses only.
    """
    conn = None
    cursor = None
    try:
        if str(session.get("role") or "").strip().lower() != "operator":
            return jsonify({"success": False, "error": "Operator access required."}), 403

        conn = get_connection()
        if request.method == "POST":
            conn.start_transaction()

        cursor = conn.cursor(dictionary=True)

        # ---- LOCK the entry ----
        cursor.execute("""
            SELECT
                e.id,
                e.id                AS session_id,
                e.machine_id,
                e.job_card_no,
                e.process_name,
                e.entry_state       AS run_status,
                e.operator_user_id,
                e.operator_master_id,
                e.operator_employee_no,
                e.operator_name,
                e.start_time        AS oee_start_time,
                e.end_time          AS oee_end_time,
                e.entry_date        AS session_date,
                e.shift_name
            FROM oee_entries e
            WHERE e.id = %s
              AND e.activity_type IS NULL
            LIMIT 1
        """, (run_id,))
        run = cursor.fetchone()
        if not run:
            return jsonify({"success": False, "error": "Machine run not found."}), 404

        # ---- GET ----
        if request.method == "GET":
            cursor.execute("""
                SELECT
                    id,
                    oee_entry_id            AS run_id,
                    loss_type_id,
                    loss_code_snapshot      AS loss_code,
                    loss_name_snapshot      AS loss_name,
                    loss_category_snapshot  AS loss_category,
                    loss_minutes,
                    remarks
                FROM oee_entry_losses
                WHERE oee_entry_id = %s
                ORDER BY id
            """, (run_id,))
            rows = cursor.fetchall() or []
            for row in rows:
                if row.get("loss_minutes") is not None:
                    row["loss_minutes"] = float(row["loss_minutes"])
            return jsonify({"success": True, "run_id": run_id, "losses": rows})

        # ---- POST ----
        status = str(run.get("run_status") or "").strip().upper()
        if status not in ("RUNNING", "HANDOVER_PENDING"):
            return jsonify({
                "success": False,
                "error": f"Machine run is {status}. Loss cannot be changed.",
            }), 409

        data = request.get_json(silent=True) or {}
        submitted_losses = data.get("losses")

        expected_codes = {"A" + str(i) for i in range(1, 28)}

        # ==================== V40 BATCH A1..A27 ====================
        if isinstance(submitted_losses, list):
            submitted_map = {}
            for item in submitted_losses:
                if not isinstance(item, dict):
                    return jsonify({"success": False, "error": "Invalid OEE loss row."}), 400
                code = str(item.get("loss_code") or "").strip().upper()
                if code not in expected_codes:
                    return jsonify({"success": False, "error": "Invalid OEE Loss Code: " + code}), 400
                if code in submitted_map:
                    return jsonify({"success": False, "error": "Duplicate OEE Loss Code: " + code}), 400
                try:
                    minutes = float(item.get("loss_minutes", 0) or 0)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "error": code + " loss minutes must be numeric."}), 400
                if minutes < 0:
                    return jsonify({"success": False, "error": code + " loss minutes cannot be negative."}), 400
                submitted_map[code] = minutes

            if set(submitted_map) != expected_codes:
                return jsonify({
                    "success": False,
                    "error": "OEE Loss Entry must contain exactly A1 to A27.",
                }), 400

            cursor.execute("""
                SELECT id, loss_code, loss_name, loss_category
                FROM oee_loss_types
                WHERE is_active = 1
            """)
            master_rows = cursor.fetchall() or []
            master = {str(r.get("loss_code") or "").strip().upper(): r for r in master_rows}
            if set(master) != expected_codes:
                return jsonify({
                    "success": False,
                    "error": "Active OEE Loss Master must contain exactly A1 to A27.",
                }), 400

            # Replace saved grid for this entry
            cursor.execute(
                "DELETE FROM oee_entry_losses WHERE oee_entry_id = %s",
                (run_id,),
            )

            for code in sorted(expected_codes, key=lambda v: int(v[1:])):
                minutes = float(submitted_map.get(code, 0) or 0)
                if minutes <= 0:
                    continue
                master_row = master[code]
                cursor.execute("""
                    INSERT INTO oee_entry_losses (
                        oee_entry_id, loss_type_id,
                        loss_code_snapshot, loss_name_snapshot, loss_category_snapshot,
                        loss_minutes, remarks
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    run_id,
                    master_row.get("id"),
                    code,
                    master_row.get("loss_name"),
                    (master_row.get("loss_category") or "AR").upper(),
                    minutes,
                    None,
                ))

            cursor.execute("""
                SELECT
                    id,
                    oee_entry_id            AS run_id,
                    loss_type_id,
                    loss_code_snapshot      AS loss_code,
                    loss_name_snapshot      AS loss_name,
                    loss_category_snapshot  AS loss_category,
                    loss_minutes
                FROM oee_entry_losses
                WHERE oee_entry_id = %s
                ORDER BY CAST(SUBSTRING(loss_code_snapshot, 2) AS UNSIGNED), id
            """, (run_id,))
            saved_rows = cursor.fetchall() or []
            for row in saved_rows:
                if row.get("loss_minutes") is not None:
                    row["loss_minutes"] = float(row["loss_minutes"])

            total_loss_minutes = round(
                sum(float(v or 0) for v in submitted_map.values()),
                2,
            )

            conn.commit()

            return jsonify({
                "success": True,
                "run_id": run_id,
                "session_id": run_id,
                "total_loss_minutes": total_loss_minutes,
                "losses": saved_rows,
                "message": "Run-linked OEE losses saved.",
            })

        # ==================== LEGACY SINGLE LOSS ====================
        try:
            loss_type_id = int(data.get("loss_type_id") or 0)
        except (TypeError, ValueError):
            loss_type_id = 0
        try:
            loss_minutes = float(data.get("loss_minutes") or 0)
        except (TypeError, ValueError):
            loss_minutes = 0

        if loss_type_id <= 0:
            return jsonify({"success": False, "error": "Select Loss Reason."}), 400
        if loss_minutes <= 0:
            return jsonify({"success": False, "error": "Loss Minutes must be greater than 0."}), 400

        cursor.execute("""
            SELECT id, loss_code, loss_name, loss_category
            FROM oee_loss_types
            WHERE id = %s AND is_active = 1
            LIMIT 1
        """, (loss_type_id,))
        master_row = cursor.fetchone()
        if not master_row:
            return jsonify({"success": False, "error": "Loss Reason not found."}), 404

        loss_code = str(master_row.get("loss_code") or "").strip().upper()
        if loss_code not in expected_codes:
            return jsonify({"success": False, "error": "Invalid OEE loss type."}), 400

        cursor.execute("""
            SELECT id, loss_minutes
            FROM oee_entry_losses
            WHERE oee_entry_id = %s AND loss_type_id = %s
            ORDER BY id LIMIT 1 FOR UPDATE
        """, (run_id, loss_type_id))
        existing = cursor.fetchone()

        if existing:
            new_minutes = float(existing.get("loss_minutes") or 0) + loss_minutes
            cursor.execute(
                "UPDATE oee_entry_losses SET loss_minutes = %s WHERE id = %s",
                (new_minutes, existing["id"]),
            )
            loss_event_id = existing["id"]
        else:
            cursor.execute("""
                INSERT INTO oee_entry_losses (
                    oee_entry_id, loss_type_id,
                    loss_code_snapshot, loss_name_snapshot, loss_category_snapshot,
                    loss_minutes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                run_id,
                loss_type_id,
                loss_code,
                master_row.get("loss_name"),
                (master_row.get("loss_category") or "AR").upper(),
                loss_minutes,
            ))
            loss_event_id = cursor.lastrowid

        conn.commit()

        return jsonify({
            "success": True,
            "loss_event_id": loss_event_id,
            "loss_code": loss_code,
            "message": loss_code + " loss saved.",
        })

    except Exception as error:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@quality_check_bp.route(
    "/api/oee-machine/run/<int:run_id>/losses/<int:event_id>",
    methods=["DELETE"]
)
def machine_oee_delete_run_loss_v1(run_id, event_id):
    """
    Delete one loss row from oee_entry_losses linked to this entry.
    """
    conn = None
    cursor = None
    try:
        if str(session.get("role") or "").strip().lower() != "operator":
            return jsonify({"success": False, "error": "Operator access required."}), 403

        conn = get_connection()
        conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                e.entry_state AS run_status
            FROM oee_entry_losses l
            JOIN oee_entries e ON e.id = l.oee_entry_id
            WHERE l.id = %s
              AND l.oee_entry_id = %s
            LIMIT 1 FOR UPDATE
        """, (event_id, run_id))
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "error": "Loss entry not found."}), 404

        status = str(row.get("run_status") or "").strip().upper()
        if status not in ("RUNNING", "HANDOVER_PENDING"):
            return jsonify({
                "success": False,
                "error": "Completed machine losses cannot be changed.",
            }), 409

        cursor.execute("""
            DELETE FROM oee_entry_losses
            WHERE id = %s
              AND oee_entry_id = %s
        """, (event_id, run_id))

        conn.commit()
        return jsonify({"success": True, "message": "Loss removed."})

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# MACHINE_OEE_LIVE_SESSION_CALC_V1
@quality_check_bp.route(
    "/api/oee-machine/session/<int:session_id>/live-oee",
    methods=["GET"]
)
def machine_oee_live_session_calc_v1(session_id):
    """
    Live per-entry OEE.
    Consolidated: reads oee_entries + oee_entry_losses only.
    """
    from .oee_persistence import OEE_MACHINE_PROFILE_MAP, ALL_OEE_LOSS_CODES

    conn = None
    cursor = None
    try:
        if str(session.get("role") or "").strip().lower() != "operator":
            return jsonify({"success": False, "error": "Operator access required."}), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Load the entry
        cursor.execute("""
            SELECT
                id                   AS session_id,
                id                   AS entry_id,
                machine_id,
                entry_date           AS session_date,
                shift_name,
                machine_no,
                machine_name,
                machine_category,
                zone,
                planned_minutes,
                cycle_minutes, cycle_seconds,
                load_unload_minutes, load_unload_seconds,
                ok_qty, rejected_qty, hold_qty,
                start_time, end_time,
                entry_state
            FROM oee_entries
            WHERE id = %s
              AND activity_type IS NULL
            LIMIT 1
        """, (session_id,))
        entry = cursor.fetchone()

        if not entry:
            return jsonify({"success": False, "error": "Machine OEE session not found."}), 404

        machine_no = " ".join(
            str(entry.get("machine_no") or "").strip().upper().split()
        )
        profile = OEE_MACHINE_PROFILE_MAP.get(machine_no)
        if not profile:
            return jsonify({
                "success": True,
                "calculation_ready": False,
                "machine_no": machine_no,
                "message": f"{machine_no} does not yet have a confirmed Excel formula profile.",
            })

        pr_codes    = set(profile["pr_loss_codes"])
        deduct_code = profile["target_deduct_code"]

        # Losses for this entry
        cursor.execute("""
            SELECT loss_code_snapshot, loss_minutes
            FROM oee_entry_losses
            WHERE oee_entry_id = %s
        """, (session_id,))
        loss_rows = cursor.fetchall()

        loss_by_code = {c: 0.0 for c in ALL_OEE_LOSS_CODES}
        for l in loss_rows:
            code = str(l.get("loss_code_snapshot") or "").strip().upper()
            if code in loss_by_code:
                try:
                    loss_by_code[code] += float(l.get("loss_minutes") or 0)
                except (TypeError, ValueError):
                    pass

        ar_loss = sum(m for c, m in loss_by_code.items() if c not in pr_codes)
        pr_loss = sum(m for c, m in loss_by_code.items() if c in pr_codes)
        target_deduct = loss_by_code.get(deduct_code, 0.0)

        cycle_m = int(entry.get("cycle_minutes") or 0)
        cycle_s = int(entry.get("cycle_seconds") or 0)
        load_m  = int(entry.get("load_unload_minutes") or 0)
        load_s  = int(entry.get("load_unload_seconds") or 0)
        ideal_cycle = cycle_m + cycle_s / 60.0 + load_m + load_s / 60.0

        ok_qty  = int(entry.get("ok_qty") or 0)
        rej_qty = int(entry.get("rejected_qty") or 0)
        hold_qty = int(entry.get("hold_qty") or 0)
        total_qty = ok_qty + rej_qty + hold_qty

        planned = float(entry.get("planned_minutes") or 0)
        run_minutes = ok_qty * ideal_cycle if ok_qty > 0 else 0.0

        utilization = max(planned - ar_loss, 0.0)
        after_pr    = max(utilization - pr_loss, 0.0)

        ar_ratio  = (utilization / planned) if planned > 0 else 0.0
        pr_ratio  = (run_minutes / after_pr) if after_pr > 0 else 0.0
        qr_ratio  = (ok_qty / total_qty) if total_qty > 0 else 1.0
        oee_ratio = ar_ratio * pr_ratio * qr_ratio

        target_qty = ((planned - target_deduct) / ideal_cycle) if ideal_cycle > 0 else 0.0
        plan_vs_actual = (total_qty / target_qty) if target_qty > 0 else 0.0

        return jsonify({
            "success": True,
            "calculation_ready": True,
            "machine_no": machine_no,
            "session_id": session_id,
            "machine_id": entry.get("machine_id"),
            "shift_name": entry.get("shift_name"),
            "planned_minutes": round(planned, 2),
            "ideal_cycle_minutes": round(ideal_cycle, 4),
            "run_minutes": round(run_minutes, 2),
            "ar_loss_minutes": round(ar_loss, 2),
            "pr_loss_minutes": round(pr_loss, 2),
            "utilization_minutes": round(utilization, 2),
            "after_pr_minutes": round(after_pr, 2),
            "target_qty": round(target_qty, 4),
            "total_qty": total_qty,
            "ok_qty": ok_qty,
            "rejected_qty": rej_qty,
            "hold_qty": hold_qty,
            "plan_vs_actual": round(plan_vs_actual, 4),
            "ar_ratio": ar_ratio,
            "pr_ratio": pr_ratio,
            "qr_ratio": qr_ratio,
            "oee_ratio": oee_ratio,
            "ar_pct":  round(ar_ratio  * 100, 2),
            "pr_pct":  round(pr_ratio  * 100, 2),
            "qr_pct":  round(qr_ratio  * 100, 2),
            "oee_pct": round(oee_ratio * 100, 2),
            "plva_pct": round(plan_vs_actual * 100, 2),
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@quality_check_bp.route(
    "/api/oee-machine/typed-kpi-preview",
    methods=["POST"]
)
def machine_oee_typed_kpi_preview_v1():

    from .oee_persistence import (
        OEE_MACHINE_PROFILE_MAP,
    )

    import datetime as _dt

    conn   = None
    cursor = None

    try:

        if str(
            session.get("role") or ""
        ).strip().lower() != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        body = (
            request.get_json(force=True)
            or {}
        )


        machine_id = int(
            body.get("machine_id")
            or 0
        )

        if not machine_id:

            return jsonify({
                "success": False,
                "error": "machine_id is required."
            }), 400


        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)


        cursor.execute("""
            SELECT
                id,
                machine_no,
                machine_name,
                machine_category,
                zone
            FROM oee_machines
            WHERE id = %s
            LIMIT 1
        """, (machine_id,))

        machine = cursor.fetchone()

        if not machine:

            return jsonify({
                "success": False,
                "error": "Machine not found."
            }), 404


        machine_no = " ".join(
            str(
                machine.get("machine_no") or ""
            )
            .strip()
            .upper()
            .split()
        )


        profile = OEE_MACHINE_PROFILE_MAP.get(machine_no)

        if not profile:

            return jsonify({
                "success": True,
                "calculation_ready": False,
                "machine_no": machine_no,
                "message": (
                    f"{machine_no} does not yet "
                    f"have a confirmed Excel formula profile."
                )
            })


        # --- Parse form values ---

        ok_qty       = max(int(body.get("ok_qty")       or 0), 0)
        rejected_qty = max(int(body.get("rejected_qty") or 0), 0)
        hold_qty     = max(int(body.get("hold_qty")     or 0), 0)
        total_qty    = ok_qty + rejected_qty + hold_qty

        cycle_min     = max(int(body.get("cycle_minutes")        or 0), 0)
        cycle_sec     = max(int(body.get("cycle_seconds")        or 0), 0)
        lu_min        = max(int(body.get("load_unload_minutes")  or 0), 0)
        lu_sec        = max(int(body.get("load_unload_seconds")  or 0), 0)

        ideal_cycle_minutes = (
            cycle_min
            + (cycle_sec  / 60.0)
            + lu_min
            + (lu_sec     / 60.0)
        )

        run_minutes = ok_qty * ideal_cycle_minutes


        # --- Planned minutes from start/end time ---

        raw_start = str(
            body.get("oee_start_time") or ""
        ).strip()

        raw_end = str(
            body.get("oee_end_time") or ""
        ).strip()

        planned_minutes = 660.0

        if raw_start and raw_end:

            try:

                t_start = _dt.datetime.strptime(
                    raw_start, "%H:%M:%S"
                )

                t_end = _dt.datetime.strptime(
                    raw_end, "%H:%M:%S"
                )

                diff = t_end - t_start

                if diff.total_seconds() < 0:
                    diff += _dt.timedelta(hours=24)

                planned_minutes = max(
                    diff.total_seconds() / 60.0,
                    0.0
                )

            except ValueError:
                pass


        # --- Losses ---

        raw_losses = body.get("losses") or []

        loss_map = {}

        for item in (raw_losses or []):

            code = str(
                item.get("loss_code") or ""
            ).strip().upper()

            minutes = max(
                float(item.get("loss_minutes") or 0),
                0.0
            )

            if code:
                loss_map[code] = minutes


        ar_codes = tuple(
            profile.get("ar_loss_codes") or ()
        )

        pr_codes = tuple(
            profile.get("pr_loss_codes") or ()
        )

        target_deduct_code = str(
            profile.get("target_deduct_code") or ""
        ).strip().upper()

        ar_loss            = sum(loss_map.get(c, 0.0) for c in ar_codes)
        pr_loss            = sum(loss_map.get(c, 0.0) for c in pr_codes)
        target_deduct_min = float(
    loss_map.get(
        target_deduct_code,
        0.0
    )
    or 0.0
)


        # --- OEE ratios ---

        available_time = planned_minutes
        utilization    = max(available_time - ar_loss, 0.0)
        after_pr       = max(utilization    - pr_loss, 0.0)

        ar_ratio  = utilization / available_time if available_time else 0.0
        pr_ratio  = run_minutes / after_pr        if after_pr       else 0.0
        qr_ratio  = ok_qty      / total_qty       if total_qty      else 0.0
        oee_ratio = ar_ratio * pr_ratio * qr_ratio


        # --- Plan vs Actual ---

        target_qty          = None
        plan_vs_actual      = None
        plan_vs_actual_note = None

        if ideal_cycle_minutes > 0:

            target_minutes = max(
                planned_minutes - target_deduct_min,
                0.0
            )

            target_qty = (
                target_minutes / ideal_cycle_minutes
            )

            if target_qty > 0:

                plan_vs_actual = (
                    total_qty / target_qty
                )

        else:

            plan_vs_actual_note = (
                "Enter Cycle Time and Load/Unload "
                "to calculate Plan vs Actual."
            )


        return jsonify({
            "success":            True,
            "calculation_ready":  True,

            "machine": {
                "id":           machine_id,
                "machine_no":   machine_no,
                "machine_name": machine.get("machine_name"),
                "zone":         machine.get("zone"),
            },

            "formula_profile":       profile.get("name"),
            "planned_minutes":       planned_minutes,
            "run_minutes":           run_minutes,

            "ok_qty":                ok_qty,
            "rejected_qty":          rejected_qty,
            "hold_qty":              hold_qty,
            "total_qty":             total_qty,

            "ar_loss_minutes":       ar_loss,
            "pr_loss_minutes":       pr_loss,
            "utilization_minutes":   utilization,
            "after_pr_minutes":      after_pr,

            "target_qty":            target_qty,
            "plan_vs_actual":        plan_vs_actual,
            "plan_vs_actual_note":   plan_vs_actual_note,
            "target_deduct_code":    target_deduct_code,
            "target_deduct_minutes": target_deduct_min,

            "ar_ratio":              ar_ratio,
            "pr_ratio":              pr_ratio,
            "qr_ratio":              qr_ratio,
            "oee_ratio":             oee_ratio,
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


# MACHINE_OEE_CURRENT_SESSION_KPI_V1
# New route: lookup by machine_id + shift_name + entry_date
# (Identical OEE calculation to machine_oee_live_session_calc_v1;
#  entry point differs -- no session_id needed from the caller.)
@quality_check_bp.route(
    "/api/oee-machine/current-session-kpi/<int:machine_id>",
    methods=["GET"]
)
def machine_oee_current_session_kpi_v1(machine_id):
    """
    Machine OEE KPI for machine + shift + date (2-table model).
    Reads oee_entries (activity_type IS NULL) + oee_entry_losses.
    Machine-level losses attached to MACHINE_LOSS entries are included.
    """
    from .oee_persistence import OEE_MACHINE_PROFILE_MAP
    import datetime as _dt

    conn = None
    cursor = None
    try:
        if str(session.get("role") or "").strip().lower() != "operator":
            return jsonify({"success": False, "error": "Operator access required."}), 403

        shift_name = str(request.args.get("shift_name") or "").strip()
        if not shift_name:
            return jsonify({"success": False, "error": "shift_name query param is required."}), 400

        raw_date = str(request.args.get("entry_date") or "").strip()
        if raw_date:
            try:
                entry_date = _dt.date.fromisoformat(raw_date)
            except ValueError:
                return jsonify({"success": False, "error": "entry_date must be YYYY-MM-DD."}), 400
        else:
            entry_date = _dt.date.today()

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # STEP 1 -- machine info
        cursor.execute("""
            SELECT
                m.id AS machine_id,
                m.machine_no,
                m.machine_name,
                m.machine_category,
                m.zone
            FROM oee_machines m
            WHERE m.id = %s
            LIMIT 1
        """, (machine_id,))
        machine_row = cursor.fetchone()
        if not machine_row:
            return jsonify({"success": False, "error": "Machine not found."}), 404

        # is there any production entry for machine+shift+date?
        cursor.execute("""
            SELECT id
            FROM oee_entries
            WHERE machine_id = %s
              AND entry_date = %s
              AND LOWER(TRIM(shift_name)) = LOWER(TRIM(%s))
              AND activity_type IS NULL
              AND record_status = 'active'
              AND UPPER(TRIM(entry_state)) IN ('RUNNING','HANDOVER_PENDING','COMPLETED')
            ORDER BY id
            LIMIT 1
        """, (machine_id, entry_date, shift_name))
        first_entry = cursor.fetchone()
        if not first_entry:
            return jsonify({
                "success": True,
                "has_session": False,
                "session": None,
                "message": "No OEE runs recorded yet for this machine / shift today.",
            })
        session_id = int(first_entry["id"])  # response-contract compat

        # STEP 2 -- profile
        machine_no = " ".join(str(machine_row.get("machine_no") or "").strip().upper().split())
        profile = OEE_MACHINE_PROFILE_MAP.get(machine_no)
        if not profile:
            return jsonify({
                "success": True,
                "calculation_ready": False,
                "machine_no": machine_no,
                "message": f"{machine_no} does not yet have a confirmed Excel formula profile.",
            })

        # STEP 3 -- aggregate production runs
        cursor.execute("""
            SELECT
                COUNT(*) AS run_count,
                COALESCE(SUM(ok_qty),       0) AS total_ok_qty,
                COALESCE(SUM(rejected_qty), 0) AS total_rejected_qty,
                COALESCE(SUM(hold_qty),     0) AS total_hold_qty,
                COALESCE(SUM(
                    ok_qty * (
                        cycle_minutes + (cycle_seconds / 60.0)
                        + load_unload_minutes + (load_unload_seconds / 60.0)
                    )
                ), 0) AS total_run_minutes,
                COALESCE(MAX(
                    cycle_minutes + (cycle_seconds / 60.0)
                    + load_unload_minutes + (load_unload_seconds / 60.0)
                ), 0) AS single_ideal_cycle_minutes
            FROM oee_entries
            WHERE machine_id = %s
              AND entry_date = %s
              AND LOWER(TRIM(shift_name)) = LOWER(TRIM(%s))
              AND activity_type IS NULL
              AND record_status = 'active'
              AND UPPER(TRIM(entry_state)) IN ('RUNNING','HANDOVER_PENDING','COMPLETED')
        """, (machine_id, entry_date, shift_name))
        totals = cursor.fetchone() or {}

        total_ok       = int(totals.get("total_ok_qty")       or 0)
        total_rejected = int(totals.get("total_rejected_qty") or 0)
        total_hold     = int(totals.get("total_hold_qty")     or 0)
        total_qty      = total_ok + total_rejected + total_hold
        run_minutes    = float(totals.get("total_run_minutes") or 0)

        # STEP 4 -- aggregate losses (production + machine-loss entries)
        cursor.execute("""
            SELECT
                UPPER(TRIM(l.loss_code_snapshot)) AS loss_code,
                COALESCE(SUM(l.loss_minutes), 0) AS loss_minutes
            FROM oee_entry_losses l
            JOIN oee_entries e ON e.id = l.oee_entry_id
            WHERE e.machine_id = %s
              AND e.entry_date = %s
              AND LOWER(TRIM(e.shift_name)) = LOWER(TRIM(%s))
              AND e.record_status = 'active'
              AND (e.activity_type IS NULL OR e.activity_type = 'MACHINE_LOSS')
            GROUP BY UPPER(TRIM(l.loss_code_snapshot))
        """, (machine_id, entry_date, shift_name))
        loss_map = {
            str(r.get("loss_code") or "").strip().upper(): float(r.get("loss_minutes") or 0)
            for r in (cursor.fetchall() or [])
        }

        ar_codes = tuple(profile.get("ar_loss_codes") or ())
        pr_codes = tuple(profile.get("pr_loss_codes") or ())
        ar_loss  = sum(loss_map.get(c, 0.0) for c in ar_codes)
        pr_loss  = sum(loss_map.get(c, 0.0) for c in pr_codes)

        # STEP 5 -- planned/available
        planned_minutes = 660.0
        available_time  = planned_minutes

        # STEP 6 -- Plan vs Actual
        run_count = int(totals.get("run_count") or 0)
        single_ideal_cycle_minutes = float(totals.get("single_ideal_cycle_minutes") or 0)
        target_deduct_code = str(profile.get("target_deduct_code") or "").strip().upper()
        target_deduct_minutes = float(loss_map.get(target_deduct_code, 0.0) or 0)

        target_qty = None
        plan_vs_actual = None
        plan_vs_actual_note = None
        if run_count == 1 and single_ideal_cycle_minutes > 0:
            target_minutes = max(planned_minutes - target_deduct_minutes, 0.0)
            target_qty = target_minutes / single_ideal_cycle_minutes
            if target_qty > 0:
                plan_vs_actual = total_qty / target_qty
        elif run_count > 1:
            plan_vs_actual_note = "Plan vs Actual is not combined across mixed JC cycle times."
        elif single_ideal_cycle_minutes <= 0:
            plan_vs_actual_note = "Enter Cycle Time and Load/Unload then Save Progress."

        # STEP 7 -- AR / PR / QR / OEE
        utilization = max(available_time - ar_loss, 0.0)
        after_pr    = max(utilization    - pr_loss, 0.0)
        ar_ratio = utilization / available_time if available_time else 0.0
        pr_ratio = run_minutes / after_pr       if after_pr       else 0.0
        qr_ratio = total_ok / total_qty         if total_qty      else 0.0
        oee_ratio = ar_ratio * pr_ratio * qr_ratio

        # STEP 8 -- loss detail
        losses = []
        for index in range(1, 28):
            code = f"A{index}"
            minutes = float(loss_map.get(code, 0.0))
            if minutes <= 0:
                continue
            categories = []
            if code in ar_codes:
                categories.append("AR")
            if code in pr_codes:
                categories.append("PR")
            losses.append({"loss_code": code, "loss_minutes": minutes, "categories": categories})

        return jsonify({
            "success": True,
            "calculation_ready": True,
            "session_id":   session_id,
            "session_date": entry_date.isoformat(),
            "shift_name":   shift_name,
            "machine": {
                "id":           machine_id,
                "machine_no":   machine_no,
                "machine_name": machine_row.get("machine_name"),
                "zone":         machine_row.get("zone"),
            },
            "formula_profile":       profile.get("name"),
            "run_count":             run_count,
            "planned_minutes":       planned_minutes,
            "run_minutes":           run_minutes,
            "ok_qty":                total_ok,
            "rejected_qty":          total_rejected,
            "hold_qty":              total_hold,
            "total_qty":             total_qty,
            "ar_loss_minutes":       ar_loss,
            "pr_loss_minutes":       pr_loss,
            "utilization_minutes":   utilization,
            "after_pr_minutes":      after_pr,
            "target_qty":            target_qty,
            "plan_vs_actual":        plan_vs_actual,
            "plan_vs_actual_note":   plan_vs_actual_note,
            "target_deduct_code":    target_deduct_code,
            "target_deduct_minutes": target_deduct_minutes,
            "ar_ratio":              ar_ratio,
            "pr_ratio":              pr_ratio,
            "qr_ratio":              qr_ratio,
            "oee_ratio":             oee_ratio,
            "losses":                losses,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


def _get_oee_zone_login_v1(cursor):
    """
    Return active shared OEE Zone login for current session.

    Zone account represents workstation/PC context,
    NOT the actual machine operator.
    """

    user_id = session.get("user_id")


    if not user_id:

        username = str(
            session.get("username")
            or session.get("user")
            or ""
        ).strip()


        if username:

            cursor.execute("""
                SELECT id

                FROM users

                WHERE username = %s

                LIMIT 1
            """, (
                username,
            ))


            row = (
                cursor.fetchone()
                or {}
            )


            user_id = row.get("id")


    if not user_id:
        return None


    cursor.execute("""
        SELECT
            z.user_id,
            UPPER(TRIM(z.zone)) AS zone,
            u.username,
            u.full_name

        FROM oee_zone_logins z

        JOIN users u
          ON u.id = z.user_id

        WHERE z.user_id = %s
          AND z.is_active = 1
          AND u.is_active = 1

        LIMIT 1
    """, (
        user_id,
    ))


    row = cursor.fetchone()


    if not row:
        return None


    zone = str(
        row.get("zone")
        or ""
    ).strip().upper()


    if zone not in (
        "A",
        "B",
        "C",
        "D",
        "E",
    ):
        return None


    row["zone"] = zone

    return row

# OEE_ZONE_MACHINE_SELECTION_V1
@quality_check_bp.route(
    "/api/oee-machine/zone-workspace",
    methods=["GET"]
)
def oee_zone_machine_workspace_v1():
    """
    Shared Zone login machine selection.

    Example:
        zonea login
        -> Zone A
        -> only active CNC/VMC machines in Zone A

    No individual operator-zone assignment exists.
    """

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()


        if role != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        zone_login = (
            _get_oee_zone_login_v1(
                cursor
            )
        )


        if not zone_login:

            return jsonify({
                "success": True,

                "is_zone_oee_login":
                    False,

                "zone":
                    None,

                "machines":
                    [],
            })


        zone = zone_login["zone"]


        cursor.execute("""
            SELECT
                id,
                machine_no,
                machine_name,
                machine_category,
                zone

            FROM oee_machines

            WHERE is_active = 1

              AND UPPER(TRIM(zone)) = %s

              AND UPPER(
                    TRIM(machine_category)
                  ) IN (
                    'CNC',
                    'VMC'
                  )

            ORDER BY
                machine_no
        """, (
            zone,
        ))


        machines = (
            cursor.fetchall()
            or []
        )


        return jsonify({
            "success": True,

            "is_zone_oee_login":
                True,

            "zone":
                zone,

            "zone_username":
                zone_login.get(
                    "username"
                )
                or "",

            "zone_name":
                zone_login.get(
                    "full_name"
                )
                or f"Zone {zone}",

            "machine_count":
                len(machines),

            "machines":
                machines,
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

# OEE_OPERATOR_MASTER_LOOKUP_V23
@quality_check_bp.route(
    "/api/oee-machine/operator-master",
    methods=["GET"]
)
def oee_operator_master_lookup_v23():

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()


        if role not in (
            "operator",
            "admin",
        ):

            return jsonify({
                "success": False,
                "error": (
                    "Machine OEE access "
                    "is not allowed."
                ),
            }), 403


        employee_no = str(
            request.args.get(
                "employee_no"
            )
            or ""
        ).strip()


        operator_name = " ".join(
            str(
                request.args.get(
                    "operator_name"
                )
                or ""
            )
            .strip()
            .split()
        )


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                id,
                employee_no,
                operator_name

            FROM oee_operator_master

            WHERE is_active = 1

            ORDER BY
                CAST(
                    employee_no AS UNSIGNED
                ),
                employee_no
        """)


        rows = (
            cursor.fetchall()
            or []
        )


        operators = []


        for row in rows:

            code = str(
                row.get(
                    "employee_no"
                )
                or ""
            ).strip()


            name = " ".join(
                str(
                    row.get(
                        "operator_name"
                    )
                    or ""
                )
                .strip()
                .split()
            )


            operators.append({
                "id":
                    row.get("id"),

                "employee_no":
                    code,

                "operator_name":
                    name,

                "display_name":
                    name,
            })


        match = None


        if employee_no:

            match = next(
                (
                    row
                    for row
                    in operators

                    if row.get(
                        "employee_no"
                    )
                    == employee_no
                ),
                None,
            )


        elif operator_name:

            lookup_name = (
                operator_name.casefold()
            )


            match = next(
                (
                    row
                    for row
                    in operators

                    if str(
                        row.get(
                            "operator_name"
                        )
                        or ""
                    )
                    .casefold()
                    == lookup_name
                ),
                None,
            )


        return jsonify({
            "success":
                True,

            "count":
                len(
                    operators
                ),

            "match":
                match,

            "operators":
                operators,
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


# OEE_OPERATOR_MASTER_BRIDGE_V24
def _oee_operator_master_resolve_v24(
    cursor,
    operator_master_id=None,
    employee_no=None,
):

    master_id = 0

    try:

        master_id = int(
            operator_master_id
            or 0
        )

    except (
        TypeError,
        ValueError,
    ):

        master_id = 0


    employee_no = str(
        employee_no
        or ""
    ).strip()


    if master_id > 0:

        cursor.execute(
            """
            SELECT
                id,
                employee_no,
                operator_name

            FROM oee_operator_master

            WHERE id = %s
              AND is_active = 1

            LIMIT 1
            """,
            (
                master_id,
            ),
        )


    elif employee_no:

        cursor.execute(
            """
            SELECT
                id,
                employee_no,
                operator_name

            FROM oee_operator_master

            WHERE employee_no = %s
              AND is_active = 1

            LIMIT 1
            """,
            (
                employee_no,
            ),
        )


    else:

        raise ValueError(
            "Please enter a valid Operator Code or Operator Name."
        )


    row = cursor.fetchone()


    if not row:

        raise ValueError(
            "Selected machine operator is invalid or inactive."
        )


    return {
        "id":
            row.get("id"),

        "employee_no":
            str(
                row.get(
                    "employee_no"
                )
                or ""
            ).strip(),

        "operator_name":
            " ".join(
                str(
                    row.get(
                        "operator_name"
                    )
                    or ""
                )
                .strip()
                .split()
            ),
    }


# OEE_ACTUAL_OPERATOR_OPTIONS_V1
@quality_check_bp.route(
    "/api/oee-machine/actual-operators",
    methods=["GET"]
)
def oee_actual_operator_options_v1():
    """
    Actual human operator selection for shared Zone login.

    Zone login = workstation identity.
    Selected operator = person who actually operated machine.
    """

    conn = None
    cursor = None

    try:

        if str(
            session.get("role")
            or ""
        ).strip().lower() != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        zone_login = (
            _get_oee_zone_login_v1(
                cursor
            )
        )


        # Individual operator login:
        # no extra operator selection needed.
        if not zone_login:

            user_id = session.get(
                "user_id"
            )


            username = str(
                session.get("username")
                or session.get("user")
                or ""
            ).strip()


            if user_id:

                cursor.execute("""
                    SELECT
                        id,
                        username,
                        full_name

                    FROM users

                    WHERE id = %s
                      AND is_active = 1

                    LIMIT 1
                """, (
                    user_id,
                ))


                row = cursor.fetchone()


                return jsonify({
                    "success": True,
                    "is_zone_login": False,
                    "operators": (
                        [row]
                        if row
                        else []
                    )
                })


        # ----------------------------------------------------
        # ZONE LOGIN:
        # list actual active operator accounts,
        # excluding zonea-zonee shared credentials.
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                u.id,
                u.username,
                u.full_name

            FROM users u

            LEFT JOIN oee_zone_logins z
              ON z.user_id = u.id
             AND z.is_active = 1

            WHERE LOWER(TRIM(u.role)) = 'operator'
              AND u.is_active = 1
              AND z.id IS NULL

            ORDER BY
                COALESCE(
                    NULLIF(TRIM(u.full_name), ''),
                    u.username
                ),
                u.username
        """)


        rows = (
            cursor.fetchall()
            or []
        )


        operators = []


        for row in rows:

            username = str(
                row.get("username")
                or ""
            ).strip()


            full_name = str(
                row.get("full_name")
                or ""
            ).strip()


            operators.append({
                "id":
                    row.get("id"),

                "username":
                    username,

                "full_name":
                    full_name,

                "display_name":
                    full_name
                    or username,
            })


        return jsonify({
            "success": True,

            "is_zone_login":
                True,

            "zone":
                zone_login.get("zone"),

            "operators":
                operators,
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

# MACHINE_OEE_RUN_COMPLETION_CONTEXT_V2
@quality_check_bp.route(
    "/api/oee-machine/run/<int:run_id>/completion-context",
    methods=["GET"]
)
def machine_oee_run_completion_context_v2(run_id):
    """
    Read-only completion context.

    Uses Machine Run as authority instead of making the browser
    reconstruct the JC context from machine_id + JC text.
    """

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()


        if role != "operator":

            return jsonify({
                "success": False,
                "error": "Operator access required."
            }), 403


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # ----------------------------------------------------
        # MACHINE RUN
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                e.id                AS run_id,
                e.id                AS session_id,
                e.machine_id,

                e.job_card_no,
                e.job_card_item_id,

                e.process_name,
                e.entry_state       AS run_status,

                e.operator_user_id,
                e.operator_name,

                e.machine_no,
                e.machine_name,
                e.machine_category,
                e.zone

            FROM oee_entries e

            WHERE e.id = %s
              AND e.activity_type IS NULL

            LIMIT 1
        """, (
            run_id,
        ))


        run = cursor.fetchone()


        if not run:

            return jsonify({
                "success": False,
                "error": "Machine Run not found."
            }), 404


        run_status = str(
            run.get("run_status")
            or ""
        ).strip().upper()


        if run_status != "RUNNING":

            return jsonify({
                "success": False,
                "error": (
                    f"Machine Run is {run_status or 'closed'}."
                )
            }), 409


        # ----------------------------------------------------
        # ZONE LOGIN SAFETY
        # ----------------------------------------------------

        zone_login = (
            _get_oee_zone_login_v1(
                cursor
            )
        )


        if zone_login:

            login_zone = str(
                zone_login.get("zone")
                or ""
            ).strip().upper()


            machine_zone = str(
                run.get("zone")
                or ""
            ).strip().upper()


            if login_zone != machine_zone:

                return jsonify({
                    "success": False,
                    "error": (
                        f"This login is for Zone {login_zone}. "
                        f"{run.get('machine_no')} belongs "
                        f"to Zone {machine_zone or '-'}."
                    )
                }), 403


        # ----------------------------------------------------
        # JC ITEM
        # ----------------------------------------------------

        item = None


        if run.get("job_card_item_id"):

            cursor.execute("""
                SELECT
                    id,
                    job_card_no,
                    item_name,
                    wip_status,
                    job_card_qty,
                    so_qty,
                    actual_qty,
                    rejected_qty,
                    hold_qty,
                    pending_qty

                FROM job_card_items

                WHERE id = %s
                  AND job_card_no = %s

                LIMIT 1
            """, (
                run["job_card_item_id"],
                run["job_card_no"],
            ))


            item = cursor.fetchone()


        if not item:

            cursor.execute("""
                SELECT
                    id,
                    job_card_no,
                    item_name,
                    wip_status,
                    job_card_qty,
                    so_qty,
                    actual_qty,
                    rejected_qty,
                    hold_qty,
                    pending_qty

                FROM job_card_items

                WHERE job_card_no = %s
                  AND COALESCE(is_deleted, 0) = 0

                ORDER BY id

                LIMIT 1
            """, (
                run["job_card_no"],
            ))


            item = cursor.fetchone()


        if not item:

            return jsonify({
                "success": False,
                "error": "Job Card item not found."
            }), 404


        current_process = str(
            item.get("wip_status")
            or ""
        ).strip()


        if not _match_processes(
            current_process,
            run.get("process_name"),
        ):

            return jsonify({
                "success": False,
                "error": (
                    f"Traceability is currently at "
                    f"{current_process or 'Unknown'}, while "
                    f"this machine run is for "
                    f"{run.get('process_name') or 'Unknown'}."
                )
            }), 409


        # ----------------------------------------------------
        # SAVED JC PROCESS SEQUENCE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                process_name

            FROM job_card_process_days

            WHERE job_card_no = %s
              AND process_name IS NOT NULL
              AND TRIM(process_name) <> ''

            ORDER BY id
        """, (
            run["job_card_no"],
        ))


        process_rows = (
            cursor.fetchall()
            or []
        )


        current_idx = None


        for idx, row in enumerate(
            process_rows
        ):

            if _match_processes(
                row.get("process_name"),
                current_process,
            ):

                current_idx = idx
                break


        if current_idx is None:

            return jsonify({
                "success": False,
                "error": (
                    f"Current process "
                    f"'{current_process}' was not found "
                    f"in the saved JC timeline."
                )
            }), 409


        if (
            current_idx + 1
            < len(process_rows)
        ):

            next_process = str(
                process_rows[
                    current_idx + 1
                ].get("process_name")
                or ""
            ).strip()

        else:

            next_process = "Store"


        pending_qty = int(
            item.get("pending_qty")
            or 0
        )

        hold_qty = int(
            item.get("hold_qty")
            or 0
        )

        if pending_qty > 0 or hold_qty > 0:
            required_qty = (
                pending_qty
                + hold_qty
            )
        else:
            required_qty = int(
                item.get("job_card_qty")
                or item.get("so_qty")
                or 0
            )


        return jsonify({
            "success": True,

            "card": {
                "job_card_no":
                    run.get("job_card_no"),

                "job_card_item_id":
                    item.get("id"),

                "item_name":
                    item.get("item_name")
                    or "",

                "current_process":
                    current_process,

                "next_process":
                    next_process,

                "job_card_qty":
                    item.get("job_card_qty")
                    or 0,

                "so_qty":
                    item.get("so_qty")
                    or 0,

                "available_qty":
                    required_qty,

                "actual_qty":
                    item.get("actual_qty")
                    or 0,

                "rejected_qty":
                    item.get("rejected_qty")
                    or 0,

                "hold_qty":
                    item.get("hold_qty")
                    or 0,

                "pending_qty":
                    item.get("pending_qty")
                    or 0,
            },

            "run": {
                "run_id":
                    run.get("run_id"),

                "machine_id":
                    run.get("machine_id"),

                "machine_no":
                    run.get("machine_no"),

                "process_name":
                    run.get("process_name"),

                "run_status":
                    run_status,
            }
        })


    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


# ============================================================
# MACHINE_OEE_MACHINE_LEVEL_LOSSES_V13
#
# Machine losses belong to:
# Machine + Date + Shift
#
# A Job Card / Machine Run is NOT required.
#
# run_id = NULL means machine-level loss.
#
# Existing run-linked historical loss rows are NOT deleted
# or modified by this module.
# ============================================================


def _oee_v13_meta_value(row, *keys):

    for key in keys:

        if key in row:
            return row.get(key)

    return None


def _oee_v13_machine_access(
    cursor,
    machine_id,
):

    role = str(
        session.get("role")
        or ""
    ).strip().lower()

    if role not in (
        "operator",
        "admin",
    ):

        raise PermissionError(
            "OEE machine access is not allowed."
        )

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
        (machine_id,),
    )

    machine = cursor.fetchone()

    if not machine:

        raise LookupError(
            "Selected OEE machine was not found."
        )

    category = str(
        machine.get("machine_category")
        or ""
    ).strip().upper()

    if category not in (
        "CNC",
        "VMC",
    ):

        raise PermissionError(
            "Only CNC/VMC machines are allowed."
        )

    zone_login = None

    if "_get_oee_zone_login_v1" in globals():

        zone_login = (
            _get_oee_zone_login_v1(
                cursor
            )
        )

    if zone_login:

        login_zone = str(
            zone_login.get("zone")
            or ""
        ).strip().upper()

        machine_zone = str(
            machine.get("zone")
            or ""
        ).strip().upper()

        if (
            not login_zone
            or login_zone != machine_zone
        ):

            raise PermissionError(
                "Selected machine does not belong "
                "to this Zone login."
            )

    elif role == "operator":

        user_id = session.get("user_id")

        cursor.execute(
            """
            SELECT 1
            FROM supervisor_process_access
            WHERE user_id = %s
              AND (
                    LOWER(process_name)
                        LIKE 'cnc machining%%'
                 OR LOWER(process_name)
                        LIKE 'vmc machining%%'
              )
            LIMIT 1
            """,
            (user_id,),
        )

        if not cursor.fetchone():

            raise PermissionError(
                "Operator does not have CNC/VMC "
                "OEE access."
            )

    from .oee_persistence import (
        get_oee_formula_profile,
    )

    formula_profile = (
        get_oee_formula_profile(
            machine.get("machine_no")
        )
    )

    return (
        machine,
        formula_profile,
        zone_login,
    )


def _oee_v13_operator_identity(
    cursor,
    zone_login,
    actual_operator_user_id=None,
):

    login_user_id = session.get(
        "user_id"
    )

    login_name = (
        session.get("full_name")
        or session.get("username")
        or "Operator"
    )

    if (
        not zone_login
        or not actual_operator_user_id
    ):

        return (
            login_user_id,
            login_name,
        )

    try:

        actual_operator_user_id = int(
            actual_operator_user_id
        )

    except (TypeError, ValueError):

        raise ValueError(
            "Invalid Actual Operator."
        )

    cursor.execute(
        """
        SELECT
            u.id,
            u.username,
            u.full_name
        FROM users u
        LEFT JOIN oee_zone_logins zl
          ON zl.user_id = u.id
         AND zl.is_active = 1
        WHERE u.id = %s
          AND u.is_active = 1
          AND zl.id IS NULL
        LIMIT 1
        """,
        (actual_operator_user_id,),
    )

    operator = cursor.fetchone()

    if not operator:

        raise ValueError(
            "Selected Actual Operator "
            "is not available."
        )

    operator_name = (
        operator.get("full_name")
        or operator.get("username")
        or "Operator"
    )

    return (
        operator.get("id"),
        operator_name,
    )


def _oee_v14_loss_time_text(value):
    if value is None:
        return None

    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")

    match = re.search(
        r"(\d{2}):(\d{2})(?::(\d{2}))?",
        str(value),
    )

    if not match:
        return None

    return (
        match.group(1)
        + ":"
        + match.group(2)
        + ":"
        + (
            match.group(3)
            or "00"
        )
    )


def _oee_v15_parse_entry_date(value):
    raw = str(
        value
        or ""
    ).strip()

    if not raw:
        return date_cls.today()

    try:

        return datetime.strptime(
            raw,
            "%Y-%m-%d",
        ).date()

    except ValueError:

        raise ValueError(
            "Loss Date must use YYYY-MM-DD format."
        )


def _oee_v15_parse_loss_period(
    entry_date,
    start_text,
    stop_text,
):
    start_text = str(
        start_text
        or ""
    ).strip()

    stop_text = str(
        stop_text
        or ""
    ).strip()

    if (
        not start_text
        or not stop_text
    ):
        raise ValueError(
            "Loss Start Time and Loss Stop Time are required."
        )

    # MACHINE_OEE_HMS_SECONDS_V20
    def parse_clock(value):

        for fmt in (
            "%H:%M:%S",
            "%H:%M",
        ):

            try:

                return datetime.strptime(
                    value,
                    fmt,
                ).time()

            except ValueError:
                continue


        raise ValueError(
            "Loss Start/Stop Time must use HH:MM:SS format."
        )


    start_clock = parse_clock(
        start_text
    )


    stop_clock = parse_clock(
        stop_text
    )


    started_at = datetime.combine(
        entry_date,
        start_clock,
    )


    ended_at = datetime.combine(
        entry_date,
        stop_clock,
    )


    if ended_at < started_at:

        ended_at += timedelta(
            days=1
        )


    duration_minutes = round(
        (
            ended_at
            - started_at
        ).total_seconds()
        / 60.0,
        2,
    )


    return (
        started_at,
        ended_at,
        duration_minutes,
    )


@quality_check_bp.route(
    "/api/oee-machine/machine-losses/<int:machine_id>",
    methods=["GET", "POST"],
)
def machine_oee_machine_losses_v13(machine_id):
    """
    Machine-level losses (2-table model).
    Reads/writes oee_entries (activity_type='MACHINE_LOSS')
    plus oee_entry_losses.  Same request/response contract as before.
    """
    conn = None
    cursor = None
    try:
        role = str(session.get("role") or "").strip().lower()
        if role not in ("operator", "admin"):
            return jsonify({"success": False, "error": "Machine OEE access is not allowed."}), 403

        conn = get_connection()
        if request.method == "POST":
            conn.start_transaction()
        cursor = conn.cursor(dictionary=True)

        machine, formula_profile, zone_login = _oee_v13_machine_access(cursor, machine_id)

        expected_codes = {"A" + str(i) for i in range(1, 28)}

        # ==========================================
        # GET
        # ==========================================
        if request.method == "GET":
            shift_name = str(request.args.get("shift_name") or "").strip()
            if shift_name not in ("Shift 1", "Shift 2"):
                return jsonify({"success": False, "error": "Please select a valid Shift."}), 400

            entry_date = _oee_v15_parse_entry_date(
                request.args.get("entry_date") or request.args.get("session_date")
            )

            cursor.execute("""
                SELECT id
                FROM oee_entries
                WHERE machine_id = %s
                  AND entry_date = %s
                  AND shift_name = %s
                  AND activity_type = 'MACHINE_LOSS'
                  AND record_status = 'active'
                ORDER BY id
            """, (machine_id, entry_date, shift_name))
            entry_ids = [r["id"] for r in (cursor.fetchall() or [])]

            if not entry_ids:
                return jsonify({
                    "success": True,
                    "session_id": None,
                    "machine_id": machine_id,
                    "entry_date": entry_date.isoformat(),
                    "shift_name": shift_name,
                    "formula_profile": formula_profile.get("name"),
                    "losses": [],
                })

            fmt = ",".join(["%s"] * len(entry_ids))
            cursor.execute(
                "SELECT "
                "  l.id,"
                "  l.oee_entry_id            AS session_id,"
                "  l.loss_type_id,"
                "  l.loss_code_snapshot      AS loss_code,"
                "  l.loss_name_snapshot      AS loss_name,"
                "  l.loss_category_snapshot  AS loss_category,"
                "  l.loss_minutes,"
                "  l.remarks,"
                "  e.start_time              AS started_at,"
                "  e.end_time                AS ended_at "
                "FROM oee_entry_losses l "
                "JOIN oee_entries e ON e.id = l.oee_entry_id "
                "WHERE l.oee_entry_id IN (" + fmt + ") "
                "ORDER BY CAST(SUBSTRING(l.loss_code_snapshot, 2) AS UNSIGNED), l.id",
                entry_ids,
            )
            losses = cursor.fetchall() or []
            for row in losses:
                if row.get("loss_minutes") is not None:
                    row["loss_minutes"] = float(row["loss_minutes"])

                # OEE_MACHINE_LOSS_TIME_JSON_V120
                # MySQL TIME values are returned by the connector
                # as datetime.timedelta and cannot be passed
                # directly to Flask jsonify().
                for time_key in ("started_at", "ended_at"):
                    time_value = row.get(time_key)

                    if time_value is None:
                        continue

                    if hasattr(time_value, "total_seconds"):
                        total_seconds = int(
                            time_value.total_seconds()
                        )

                        hours = total_seconds // 3600
                        minutes = (
                            total_seconds % 3600
                        ) // 60
                        seconds = total_seconds % 60

                        row[time_key] = (
                            f"{hours:02d}:"
                            f"{minutes:02d}:"
                            f"{seconds:02d}"
                        )

                    elif hasattr(time_value, "strftime"):
                        row[time_key] = (
                            time_value.strftime("%H:%M:%S")
                        )

                    else:
                        row[time_key] = str(time_value)

            return jsonify({
                "success": True,
                "session_id": entry_ids[0],
                "machine_id": machine_id,
                "entry_date": entry_date.isoformat(),
                "shift_name": shift_name,
                "formula_profile": formula_profile.get("name"),
                "losses": losses,
            })

        # ==========================================
        # POST
        # ==========================================
        data = request.get_json(silent=True) or {}

        shift_name = str(data.get("shift_name") or "").strip()
        if shift_name not in ("Shift 1", "Shift 2"):
            return jsonify({"success": False, "error": "Please select a valid Shift before saving losses."}), 400

        entry_date = _oee_v15_parse_entry_date(
            data.get("entry_date") or data.get("session_date")
        )

        loss_started_at, loss_ended_at, loss_period_minutes = _oee_v15_parse_loss_period(
            entry_date,
            data.get("loss_start_time") or data.get("start_time"),
            data.get("loss_stop_time") or data.get("stop_time"),
        )

        operator_master_id = None
        operator_employee_no = None
        requested_master_id = (
            data.get("operator_master_id") or data.get("actual_operator_master_id")
        )
        requested_employee_no = str(
            data.get("operator_employee_no") or data.get("employee_no") or ""
        ).strip()

        if zone_login and (requested_master_id or requested_employee_no):
            master_operator = _oee_operator_master_resolve_v24(
                cursor, requested_master_id, requested_employee_no
            )
            operator_user_id = session.get("user_id")
            operator_master_id = master_operator.get("id")
            operator_employee_no = master_operator.get("employee_no")
            operator_name = master_operator.get("operator_name") or "Operator"
        else:
            operator_user_id, operator_name = _oee_v13_operator_identity(
                cursor, zone_login, data.get("actual_operator_user_id")
            )

        submitted_losses = data.get("losses")
        if not isinstance(submitted_losses, list):
            return jsonify({"success": False, "error": "OEE losses must be provided."}), 400

        cursor.execute("""
            SELECT id, loss_code, loss_name
            FROM oee_loss_types
            WHERE is_active = 1
            ORDER BY display_order, id
        """)
        master_rows = cursor.fetchall() or []
        master = {}
        for row in master_rows:
            code = str(row.get("loss_code") or "").strip().upper()
            if code:
                master[code] = row
        if set(master) != expected_codes:
            return jsonify({"success": False, "error": "Active OEE Loss Master must contain A1 to A27."}), 400

        submitted_map = {}
        for item in submitted_losses:
            if not isinstance(item, dict):
                return jsonify({"success": False, "error": "Invalid OEE loss row."}), 400
            code = str(item.get("loss_code") or "").strip().upper()
            if code not in expected_codes:
                return jsonify({"success": False, "error": "Invalid OEE Loss Code: " + code}), 400
            if code in submitted_map:
                return jsonify({"success": False, "error": "Duplicate OEE Loss Code: " + code}), 400
            try:
                minutes = float(item.get("loss_minutes", 0) or 0)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": code + " loss minutes must be numeric."}), 400
            if minutes < 0:
                return jsonify({"success": False, "error": code + " loss minutes cannot be negative."}), 400
            submitted_map[code] = minutes

        if set(submitted_map) != expected_codes:
            missing = sorted(expected_codes - set(submitted_map))
            return jsonify({
                "success": False,
                "error": "OEE Loss Entry must contain A1 to A27. Missing: " + ", ".join(missing),
            }), 400

        total_loss_minutes = round(sum(submitted_map.values()), 2)
        if total_loss_minutes <= 0:
            return jsonify({
                "success": False,
                "error": "Enter at least one machine loss before saving this loss period.",
            }), 400

        difference_minutes = round(loss_period_minutes - total_loss_minutes, 2)
        time_match = abs(difference_minutes) < 0.01

        # ----- upsert the MACHINE_LOSS entry -----
        start_time_val = loss_started_at.strftime("%H:%M:%S") if loss_started_at else None
        end_time_val   = loss_ended_at.strftime("%H:%M:%S")   if loss_ended_at   else None

        cursor.execute("""
            SELECT id FROM oee_entries
            WHERE machine_id = %s
              AND entry_date = %s
              AND shift_name = %s
              AND activity_type = 'MACHINE_LOSS'
              AND start_time = %s
              AND end_time = %s
              AND record_status = 'active'
            LIMIT 1
        """, (machine_id, entry_date, shift_name, start_time_val, end_time_val))
        existing = cursor.fetchone()

        if existing:
            entry_id = existing["id"]
            cursor.execute("DELETE FROM oee_entry_losses WHERE oee_entry_id = %s", (entry_id,))
        else:
            cursor.execute("""
                SELECT machine_no, machine_name, machine_category, zone
                FROM oee_machines WHERE id = %s LIMIT 1
            """, (machine_id,))
            m_info = cursor.fetchone() or {}

            cursor.execute(
                """
                INSERT INTO oee_entries (
                    machine_id,
                    operator_user_id, operator_master_id, operator_employee_no, operator_name,
                    entry_date, shift_name,
                    item_name, process_name,
                    machine_no, machine_name, machine_category, zone,
                    start_time, end_time,
                    cycle_minutes, cycle_seconds,
                    load_unload_minutes, load_unload_seconds,
                    ok_qty, rejected_qty, hold_qty,
                    job_card_no,
                    activity_type, entry_state, record_status,
                    remarks
                )
                VALUES (
                    %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    0, 0, 0, 0,
                    0, 0, 0,
                    '',
                    'MACHINE_LOSS', 'COMPLETED', 'active',
                    %s
                )
                """,
                (
                    machine_id,
                    operator_user_id, operator_master_id, operator_employee_no, operator_name,
                    entry_date, shift_name,
                    "Machine Loss", "Machine Loss",
                    m_info.get("machine_no"), m_info.get("machine_name"),
                    m_info.get("machine_category"), m_info.get("zone"),
                    start_time_val, end_time_val,
                    None,
                ),
            )
            entry_id = cursor.lastrowid

        # insert A1-A27 losses (non-zero only)
        pr_codes = set(formula_profile.get("pr_loss_codes") or ())
        saved_count = 0
        for code in sorted(expected_codes, key=lambda v: int(v[1:])):
            minutes = float(submitted_map[code] or 0)
            if minutes <= 0:
                continue
            master_row = master[code]
            category = "PR" if code in pr_codes else "AR"
            cursor.execute("""
                INSERT INTO oee_entry_losses (
                    oee_entry_id, loss_type_id,
                    loss_code_snapshot, loss_name_snapshot, loss_category_snapshot,
                    loss_minutes, remarks
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                entry_id,
                master_row.get("id"),
                code,
                master_row.get("loss_name"),
                category,
                minutes,
                None,
            ))
            saved_count += 1

        conn.commit()

        cursor.execute("""
            SELECT
                l.id,
                l.oee_entry_id            AS session_id,
                l.loss_type_id,
                l.loss_code_snapshot      AS loss_code,
                l.loss_name_snapshot      AS loss_name,
                l.loss_category_snapshot  AS loss_category,
                l.loss_minutes,
                l.remarks
            FROM oee_entry_losses l
            WHERE l.oee_entry_id = %s
            ORDER BY CAST(SUBSTRING(l.loss_code_snapshot, 2) AS UNSIGNED), l.id
        """, (entry_id,))
        losses = cursor.fetchall() or []
        for row in losses:
            if row.get("loss_minutes") is not None:
                row["loss_minutes"] = float(row["loss_minutes"])

        if time_match:
            message = "Machine loss period saved. Loss time is fully accounted."
            warning = None
        elif difference_minutes > 0:
            message = "Machine loss period saved with a time warning."
            warning = str(abs(difference_minutes)) + " minute(s) are not yet accounted in A1-A27 losses."
        else:
            message = "Machine loss period saved with a time warning."
            warning = "A1-A27 losses exceed the loss period by " + str(abs(difference_minutes)) + " minute(s)."

        return jsonify({
            "success": True,
            "message": message,
            "warning": warning,
            "time_match": time_match,
            "entry_date": entry_date.isoformat(),
            "loss_start_time": loss_started_at.strftime("%H:%M:%S"),
            "loss_stop_time":  loss_ended_at.strftime("%H:%M:%S"),
            "loss_period_minutes": loss_period_minutes,
            "total_loss_minutes":  total_loss_minutes,
            "difference_minutes":  difference_minutes,
            "session_id": entry_id,
            "machine_id": machine_id,
            "shift_name": shift_name,
            "formula_profile": formula_profile.get("name"),
            "loss_rows_saved": saved_count,
            "losses": losses,
        })

    except PermissionError as error:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 403
    except LookupError as error:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 404
    except ValueError as error:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 400
    except Exception as error:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


@quality_check_bp.route("/oee-machine/summary", methods=["GET"])
def oee_machine_summary_page_v1():
    from flask import render_template, session as flask_session
    import db

    role    = str(flask_session.get("role")    or "").strip().lower()
    user_id = flask_session.get("user_id")

    if role not in ("admin", "supervisor") or not user_id:
        return ("OEE Summary access denied.", 403)

    if role == "supervisor":
        conn   = None
        cursor = None
        try:
            conn   = db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 1
                FROM supervisor_process_access
                WHERE user_id = %s
                  AND (
                    LOWER(TRIM(process_name)) LIKE 'cnc machining%%'
                    OR LOWER(TRIM(process_name)) LIKE 'vmc machining%%'
                  )
                LIMIT 1
                """,
                (user_id,),
            )
            if cursor.fetchone() is None:
                return ("OEE Summary access denied.", 403)
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template(
        "oee_machine_summary.html",
        active_page="oee_machine_summary",
    )


# MACHINE_SHIFT_CAPACITY_V1
@quality_check_bp.route(
    "/api/oee-machine/shift-capacity/<int:machine_id>",
    methods=["GET"]
)
def machine_oee_shift_capacity_v1(machine_id):
    """
    Read-only machine shift capacity (2-table model).
    Reads production and activity entries directly from oee_entries.
    MACHINE_LOSS entries do NOT count toward used capacity.
    """
    from datetime import date as date_cls

    conn = None
    cursor = None

    try:
        role = str(session.get("role") or "").strip().lower()
        if role not in ("operator", "supervisor", "admin"):
            return jsonify({"success": False, "error": "OEE access denied."}), 403

        session_date = str(request.args.get("date") or "").strip()
        shift_name   = str(request.args.get("shift_name") or "").strip()
        shift_start  = str(request.args.get("shift_start") or "").strip()
        shift_end    = str(request.args.get("shift_end") or "").strip()

        if not session_date:
            session_date = date_cls.today().isoformat()
        if not shift_name:
            return jsonify({"success": False, "error": "Shift is required."}), 400
        if not shift_start or not shift_end:
            return jsonify({
                "success": False,
                "error": "Shift start and end time are required."
            }), 400

        def time_to_seconds_v1(value):
            value = str(value or "").strip()
            parts = value.split(":")
            if len(parts) not in (2, 3):
                raise ValueError("Time must be HH:MM or HH:MM:SS.")
            try:
                hour = int(parts[0]); minute = int(parts[1])
                second = int(parts[2]) if len(parts) == 3 else 0
            except (TypeError, ValueError):
                raise ValueError("Invalid shift time.")
            if hour < 0 or hour > 23 or minute < 0 or minute > 59 or second < 0 or second > 59:
                raise ValueError("Invalid shift time.")
            return hour * 3600 + minute * 60 + second

        shift_start_sec = time_to_seconds_v1(shift_start)
        shift_end_sec   = time_to_seconds_v1(shift_end)
        shift_end_abs   = shift_end_sec
        if shift_end_abs <= shift_start_sec:
            shift_end_abs += 86400
        shift_seconds = shift_end_abs - shift_start_sec
        shift_minutes = round(shift_seconds / 60.0, 2)

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # --- Production entries (activity_type IS NULL) ---
        cursor.execute("""
            SELECT
                id, job_card_no,
                CAST(start_time AS CHAR) AS start_time,
                CAST(end_time   AS CHAR) AS end_time
            FROM oee_entries
            WHERE machine_id = %s
              AND entry_date = %s
              AND LOWER(TRIM(shift_name)) = LOWER(TRIM(%s))
              AND activity_type IS NULL
              AND UPPER(TRIM(entry_state)) IN ('RUNNING','HANDOVER_PENDING','COMPLETED')
              AND record_status = 'active'
              AND start_time IS NOT NULL
              AND end_time IS NOT NULL
            ORDER BY id
        """, (machine_id, session_date, shift_name))
        rows = cursor.fetchall() or []

        # --- Activity entries (TOOL_ROOM / DEVELOPMENT) ---
        cursor.execute("""
            SELECT
                id, item_name AS activity_name,
                activity_type AS activity_group,
                CAST(start_time AS CHAR) AS start_time,
                CAST(end_time   AS CHAR) AS end_time
            FROM oee_entries
            WHERE machine_id = %s
              AND entry_date = %s
              AND LOWER(TRIM(shift_name)) = LOWER(TRIM(%s))
              AND activity_type IN ('TOOL_ROOM', 'DEVELOPMENT', 'MACHINE_LOSS')
              AND UPPER(TRIM(entry_state)) IN ('RUNNING','HANDOVER_PENDING','COMPLETED')
              AND record_status = 'active'
              AND start_time IS NOT NULL
              AND end_time IS NOT NULL
            ORDER BY id
        """, (machine_id, session_date, shift_name))
        activity_rows = cursor.fetchall() or []

        intervals = []
        for row in list(rows) + list(activity_rows):
            try:
                run_start = time_to_seconds_v1(row.get("start_time"))
                run_end   = time_to_seconds_v1(row.get("end_time"))
            except ValueError:
                continue
            if run_end <= run_start:
                run_end += 86400
            candidates = (
                (run_start - 86400, run_end - 86400),
                (run_start,          run_end),
                (run_start + 86400,  run_end + 86400),
            )
            for c_start, c_end in candidates:
                clipped_start = max(c_start, shift_start_sec)
                clipped_end   = min(c_end,   shift_end_abs)
                if clipped_end > clipped_start:
                    intervals.append((clipped_start, clipped_end))

        intervals.sort(key=lambda item: (item[0], item[1]))
        merged = []
        for start_sec, end_sec in intervals:
            if not merged:
                merged.append([start_sec, end_sec])
                continue
            previous = merged[-1]
            if start_sec <= previous[1]:
                previous[1] = max(previous[1], end_sec)
            else:
                merged.append([start_sec, end_sec])

        used_seconds = sum(end_sec - start_sec for start_sec, end_sec in merged)
        used_minutes = round(used_seconds / 60.0, 2)
        remaining_minutes = round(max(shift_minutes - used_minutes, 0.0), 2)

        return jsonify({
            "success": True,
            "machine_id": machine_id,
            "date": session_date,
            "shift_name": shift_name,
            "shift_start": shift_start,
            "shift_end": shift_end,
            "shift_minutes": shift_minutes,
            "used_minutes": used_minutes,
            "remaining_minutes": remaining_minutes,
            "completed_run_count": len(rows),
            "completed_activity_count": len(activity_rows),
            "merged_interval_count": len(merged),
        })

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


