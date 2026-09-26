# ==== FIRST 200 LINES (imports, blueprint setup) ====
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


# ==== OEE-related routes only ====

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
                    r.id,
                    r.session_id,
                    r.machine_id,

                    r.job_card_no,
                    r.job_card_item_id,
                    r.process_name,
                    r.run_status,

                    r.operator_user_id,
                    r.operator_name,

                    r.ok_qty,
                    r.rejected_qty,
                    r.hold_qty,

                    r.started_at,

                    m.machine_no,
                    m.machine_name,
                    m.machine_category,
                    m.zone

                FROM oee_machine_runs r

                JOIN oee_machines m
                  ON m.id = r.machine_id

                WHERE r.id = %s

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
                UPDATE oee_machine_runs

                SET
                    ok_qty = %s,
                    rejected_qty = %s,
                    hold_qty = %s,

                    run_status = 'COMPLETED',

                    ended_at = NOW(),

                    updated_at =
                        CURRENT_TIMESTAMP

                WHERE id = %s
                  AND UPPER(
                        TRIM(run_status)
                      ) = 'RUNNING'
            """, (
                submitted_ok,
                submitted_rej,
                submitted_hold,
                machine_oee_run_id,
            ))


            if cursor.rowcount != 1:

                raise RuntimeError(
                    "Machine Run could not be "
                    "closed safely."
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
    "/api/oee-machine/workspace",
    methods=["POST"]
)
def oee_machine_workspace_v1():
    """
    Open / resume one machine-wise OEE workspace.

    Workflow:
      1. Operator selects machine.
      2. Server first checks whether that machine already
         has an unfinished JC run.
      3. If unfinished run exists, it MUST be resolved first.
      4. Otherwise open/reuse Machine + Date + Shift session.

    This endpoint does NOT start a new Job Card.
    """

    conn = None
    cursor = None

    try:
        role = (
            session.get("role")
            or ""
        ).strip().lower()

        if (
            role not in (
                "operator",
                "admin",
                "supervisor",
            )
            and not is_gaurang_special_user()
        ):
            return jsonify({
                "success": False,
                "error": "Access denied."
            }), 403


        data = request.json or {}


        # -------------------------------------------------
        # MACHINE
        # -------------------------------------------------

        try:
            machine_id = int(
                data.get("machine_id")
            )
        except (TypeError, ValueError):
            machine_id = 0


        if machine_id <= 0:
            return jsonify({
                "success": False,
                "error": "Please select a valid machine."
            }), 400


        # -------------------------------------------------
        # SHIFT
        #
        # We keep this explicit for now because NMTG shift
        # timings have not been hard-coded into JMS.
        #
        # Later frontend will remember/select it once.
        # -------------------------------------------------

        shift_name = str(
            data.get("shift_name")
            or ""
        ).strip()


        if not shift_name:
            return jsonify({
                "success": False,
                "error": "Shift is required."
            }), 400


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # -------------------------------------------------
        # VERIFY MACHINE
        # -------------------------------------------------

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


        machine_category = str(
            machine.get(
                "machine_category"
            )
            or ""
        ).strip().upper()


        if machine_category not in (
            "CNC",
            "VMC",
        ):
            return jsonify({
                "success": False,
                "error": (
                    "Machine-wise OEE is currently "
                    "available only for CNC/VMC machines."
                )
            }), 400


        # -------------------------------------------------
        # STEP 1:
        # MACHINE HAS AN UNFINISHED JC?
        #
        # IMPORTANT:
        # Check across ALL sessions/shifts first.
        #
        # Example:
        # Shift 1 operator forgot / handed over JC.
        # Shift 2 operator must see that same JC first.
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                r.id AS run_id,
                r.session_id,
                r.machine_id,

                r.job_card_no,
                r.job_card_item_id,
                r.process_day_id,
                r.process_name,

                r.run_status,

                r.operator_user_id,
                r.operator_name,

                r.started_at,
                r.ended_at,

                CAST(r.oee_start_time AS CHAR) AS oee_start_time,

                CAST(r.oee_end_time AS CHAR) AS oee_end_time,

                r.cycle_minutes,
                r.cycle_seconds,

                r.load_unload_minutes,
                r.load_unload_seconds,

                r.ok_qty,
                r.rejected_qty,
                r.hold_qty,

                r.remarks,

                s.session_date,
                s.shift_name,
                s.session_status

            FROM oee_machine_runs r

            JOIN oee_machine_sessions s
              ON s.id = r.session_id

            WHERE r.machine_id = %s

              AND UPPER(
                    TRIM(
                        r.run_status
                    )
                  ) IN (
                    'RUNNING',
                    'HANDOVER_PENDING'
                  )

            ORDER BY
                r.started_at DESC,
                r.id DESC

            LIMIT 1
        """, (
            machine_id,
        ))


        pending_run = cursor.fetchone()


        if pending_run:

            for key in (
                "started_at",
                "ended_at",
                "oee_start_time",
                "oee_end_time",
                "session_date",
            ):
                value = pending_run.get(
                    key
                )

                if (
                    value is not None
                    and hasattr(
                        value,
                        "isoformat"
                    )
                ):
                    pending_run[key] = (
                        value.isoformat()
                    )


            return jsonify({
                "success": True,

                "machine": {
                    "id":
                        machine["id"],

                    "machine_no":
                        machine.get(
                            "machine_no"
                        )
                        or "",

                    "machine_name":
                        machine.get(
                            "machine_name"
                        )
                        or "",

                    "machine_category":
                        machine_category,

                    "zone":
                        machine.get(
                            "zone"
                        )
                        or "",
                },

                "requires_previous_resolution":
                    True,

                "pending_run":
                    pending_run,

                "machine_session":
                    None,

                "message": (
                    "This machine already has an "
                    "unfinished Job Card. Resolve it "
                    "before starting another JC."
                ),
            })


        # -------------------------------------------------
        # STEP 2:
        # OPEN / REUSE CURRENT MACHINE SESSION
        #
        # One official session:
        # Machine + Date + Shift
        # -------------------------------------------------

        requested_date = str(
            data.get("session_date")
            or ""
        ).strip()


        if requested_date:

            cursor.execute(
                "SELECT DATE(%s) AS session_date",
                (
                    requested_date,
                )
            )

            parsed_date_row = (
                cursor.fetchone()
                or {}
            )

            session_date = (
                parsed_date_row.get(
                    "session_date"
                )
            )

            if not session_date:
                return jsonify({
                    "success": False,
                    "error": "Invalid session date."
                }), 400

        else:

            cursor.execute(
                "SELECT CURDATE() AS session_date"
            )

            session_date = (
                cursor.fetchone()
                or {}
            ).get(
                "session_date"
            )


        # Lock/reuse existing session.
        cursor.execute("""
            SELECT
                id,
                machine_id,
                session_date,
                shift_name,
                session_status,

                opened_by_user_id,
                opened_by_name,

                started_at,
                closed_at

            FROM oee_machine_sessions

            WHERE machine_id = %s
              AND session_date = %s
              AND LOWER(TRIM(shift_name))
                  = LOWER(TRIM(%s))

            LIMIT 1
        """, (
            machine_id,
            session_date,
            shift_name,
        ))


        machine_session = (
            cursor.fetchone()
        )


        session_created = False


        if not machine_session:

            opened_by_user_id = (
                session.get("user_id")
            )

            opened_by_name = (
                session.get("full_name")
                or session.get("username")
                or "Operator"
            )


            cursor.execute("""
                INSERT INTO oee_machine_sessions (
                    machine_id,
                    session_date,
                    shift_name,
                    session_status,

                    opened_by_user_id,
                    opened_by_name,

                    started_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    'OPEN',

                    %s,
                    %s,

                    NOW()
                )
            """, (
                machine_id,
                session_date,
                shift_name,

                opened_by_user_id,
                opened_by_name,
            ))


            machine_session_id = (
                cursor.lastrowid
            )


            conn.commit()


            cursor.execute("""
                SELECT
                    id,
                    machine_id,
                    session_date,
                    shift_name,
                    session_status,

                    opened_by_user_id,
                    opened_by_name,

                    started_at,
                    closed_at

                FROM oee_machine_sessions

                WHERE id = %s
                LIMIT 1
            """, (
                machine_session_id,
            ))


            machine_session = (
                cursor.fetchone()
            )

            session_created = True


        # -------------------------------------------------
        # CLOSED SESSION CANNOT TAKE NEW JC
        # -------------------------------------------------

        session_status = str(
            machine_session.get(
                "session_status"
            )
            or ""
        ).strip().upper()


        if session_status != "OPEN":

            return jsonify({
                "success": False,

                "status":
                    "MACHINE_SESSION_CLOSED",

                "error": (
                    f"{machine.get('machine_no') or 'Machine'} "
                    f"{shift_name} session is already "
                    f"{session_status}."
                ),
            }), 400


        # -------------------------------------------------
        # SERIALIZE
        # -------------------------------------------------

        for key in (
            "session_date",
            "started_at",
            "closed_at",
        ):
            value = machine_session.get(
                key
            )

            if (
                value is not None
                and hasattr(
                    value,
                    "isoformat"
                )
            ):
                machine_session[key] = (
                    value.isoformat()
                )


        return jsonify({
            "success": True,

            "machine": {
                "id":
                    machine["id"],

                "machine_no":
                    machine.get(
                        "machine_no"
                    )
                    or "",

                "machine_name":
                    machine.get(
                        "machine_name"
                    )
                    or "",

                "machine_category":
                    machine_category,

                "zone":
                    machine.get(
                        "zone"
                    )
                    or "",
            },

            "requires_previous_resolution":
                False,

            "pending_run":
                None,

            "machine_session":
                machine_session,

            "session_created":
                session_created,

            "message": (
                "Machine OEE workspace ready."
            ),
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
                r.id AS run_id,
                r.session_id,
                r.machine_id,

                r.job_card_no,
                r.job_card_item_id,
                r.process_day_id,
                r.process_name,

                r.run_status,

                r.operator_user_id,
                r.operator_name,

                r.started_at,
                r.ended_at,

                CAST(r.oee_start_time AS CHAR) AS oee_start_time,

                CAST(r.oee_end_time AS CHAR) AS oee_end_time,

                r.cycle_minutes,
                r.cycle_seconds,

                r.load_unload_minutes,
                r.load_unload_seconds,

                r.ok_qty,
                r.rejected_qty,
                r.hold_qty,

                r.remarks,

                s.session_date,
                s.shift_name,
                s.session_status

            FROM oee_machine_runs r

            JOIN oee_machine_sessions s
              ON s.id = r.session_id

            WHERE r.machine_id = %s

              AND UPPER(
                    TRIM(r.run_status)
                  ) IN (
                    'RUNNING',
                    'HANDOVER_PENDING'
                  )

            ORDER BY
                r.started_at DESC,
                r.id DESC
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
                run_status,
                started_at

            FROM oee_machine_runs

            WHERE machine_id = %s

              AND UPPER(
                    TRIM(run_status)
                  ) IN (
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
                r.id,
                r.machine_id,
                r.job_card_no,
                r.process_name,
                r.run_status,

                m.machine_no,
                m.machine_name

            FROM oee_machine_runs r

            JOIN oee_machines m
              ON m.id = r.machine_id

            WHERE r.job_card_no = %s

              AND UPPER(
                    TRIM(r.run_status)
                  ) IN (
                    'RUNNING',
                    'HANDOVER_PENDING'
                  )

            ORDER BY r.id DESC

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
        # OPEN / REUSE MACHINE + DATE + SHIFT SESSION
        #
        # Unique key already protects:
        # machine_id + session_date + shift_name
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                session_status

            FROM oee_machine_sessions

            WHERE machine_id = %s
              AND session_date = CURDATE()
              AND LOWER(TRIM(shift_name))
                  = LOWER(TRIM(%s))

            LIMIT 1
            FOR UPDATE
        """, (
            machine_id,
            shift_name,
        ))


        machine_session = (
            cursor.fetchone()
        )


        if machine_session:

            session_status = str(
                machine_session.get(
                    "session_status"
                )
                or ""
            ).strip().upper()


            if session_status != "OPEN":

                return jsonify({
                    "success": False,

                    "error": (
                        f"{machine.get('machine_no')} "
                        f"{shift_name} OEE session is "
                        f"{session_status}."
                    )
                }), 409


            machine_session_id = (
                machine_session["id"]
            )

        else:

            cursor.execute("""
                INSERT INTO oee_machine_sessions (
                    machine_id,
                    session_date,
                    shift_name,
                    session_status,
                    opened_by_user_id,
                    opened_by_name,
                    started_at
                )
                VALUES (
                    %s,
                    CURDATE(),
                    %s,
                    'OPEN',
                    %s,
                    %s,
                    NOW()
                )
            """, (
                machine_id,
                shift_name,
                user_id,
                operator_name,
            ))


            machine_session_id = (
                cursor.lastrowid
            )


        # ----------------------------------------------------
        # START MACHINE RUN
        # ----------------------------------------------------

        cursor.execute("""
            INSERT INTO oee_machine_runs (
                session_id,
                machine_id,

                operator_user_id,
                operator_master_id,
                operator_employee_no,
                operator_name,

                job_card_no,
                job_card_item_id,

                process_name,
                run_status,

                started_at,

                cycle_minutes,
                cycle_seconds,

                load_unload_minutes,
                load_unload_seconds,

                ok_qty,
                rejected_qty,
                hold_qty
            )
            VALUES (
                %s,
                %s,

                %s,
                %s,
                %s,
                %s,

                %s,
                %s,

                %s,
                'RUNNING',

                NOW(),

                0,
                0,

                0,
                0,

                0,
                0,
                0
            )
            # OEE_MACHINE_RUN_SQL_FIX_V28
        """, (
            machine_session_id,
            machine_id,

            run_operator_user_id,
            run_operator_master_id,
            run_operator_employee_no,
            operator_name,

            job_card_no,
            jc_row.get(
                "job_card_item_id"
            ),

            current_process,
        ))


        run_id = cursor.lastrowid


        # ----------------------------------------------------
        # READ CREATED RUN
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                r.id AS run_id,
                r.session_id,
                r.machine_id,
                r.job_card_no,
                r.process_name,
                r.run_status,

                r.operator_master_id,
                r.operator_employee_no,
                r.operator_name,

                r.started_at,

                s.session_date,
                s.shift_name,

                m.machine_no,
                m.machine_name,
                m.machine_category,
                m.zone

            FROM oee_machine_runs r

            JOIN oee_machine_sessions s
              ON s.id = r.session_id

            JOIN oee_machines m
              ON m.id = r.machine_id

            WHERE r.id = %s

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
            SELECT id, run_status, ok_qty, rejected_qty, hold_qty
            FROM oee_machine_runs
            WHERE id = %s
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
            UPDATE oee_machine_runs
            SET
                run_status  = 'VOID',
                ended_at    = NOW(),
                updated_at  = CURRENT_TIMESTAMP
            WHERE id = %s
              AND UPPER(TRIM(run_status)) = 'RUNNING'
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
                r.id,
                r.session_id,
                r.machine_id,

                r.job_card_no,
                r.job_card_item_id,
                r.process_name,
                r.run_status,

                r.operator_user_id,

                r.started_at,

                r.cycle_minutes,
                r.cycle_seconds,
                r.load_unload_minutes,
                r.load_unload_seconds,

                r.ok_qty,
                r.rejected_qty,
                r.hold_qty,

                m.machine_no,
                m.machine_name

            FROM oee_machine_runs r

            JOIN oee_machines m
              ON m.id = r.machine_id

            WHERE r.id = %s

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
            UPDATE oee_machine_runs

            SET
                oee_start_time = %s,
                oee_end_time = %s,

                cycle_minutes = %s,
                cycle_seconds = %s,

                load_unload_minutes = %s,
                load_unload_seconds = %s,

                ok_qty = %s,
                rejected_qty = %s,
                hold_qty = %s,

                updated_at = CURRENT_TIMESTAMP

            WHERE id = %s
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

        if (
            oee_start_time
            and oee_end_time
        ):

            cursor.execute("""
                SELECT
                    COALESCE(
                        SUM(
                            CASE
                                WHEN
                                    TIME_TO_SEC(
                                        oee_end_time
                                    )
                                    >=
                                    TIME_TO_SEC(
                                        oee_start_time
                                    )

                                THEN
                                    TIME_TO_SEC(
                                        oee_end_time
                                    )
                                    -
                                    TIME_TO_SEC(
                                        oee_start_time
                                    )

                                ELSE
                                    86400
                                    -
                                    TIME_TO_SEC(
                                        oee_start_time
                                    )
                                    +
                                    TIME_TO_SEC(
                                        oee_end_time
                                    )
                            END
                        ) / 60.0,
                        0
                    ) AS planned_minutes

                FROM oee_machine_runs

                WHERE session_id = %s
                  AND oee_start_time IS NOT NULL
                  AND oee_end_time IS NOT NULL
            """, (
                run.get("session_id"),
            ))


            planned_row = (
                cursor.fetchone()
                or {}
            )


            planned_minutes = float(
                planned_row.get(
                    "planned_minutes"
                )
                or 0
            )


            cursor.execute("""
                UPDATE oee_machine_sessions

                SET
                    planned_minutes = %s,
                    updated_at = CURRENT_TIMESTAMP

                WHERE id = %s
            """, (
                planned_minutes,
                run.get("session_id"),
            ))


        # V43_SESSION_RECALC_CALL
        _machine_oee_recalculate_session_v43(
            cursor,
            run.get("session_id"),
        )

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

        if request.method == "POST":
            conn.start_transaction()


        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                r.id,
                r.session_id,
                r.machine_id,
                r.job_card_no,
                r.process_name,
                r.run_status,

                r.operator_user_id,
                r.operator_master_id,
                r.operator_employee_no,
                r.operator_name,

                r.oee_start_time,
                r.oee_end_time,

                s.session_date,
                s.shift_name

            FROM oee_machine_runs r

            JOIN oee_machine_sessions s
              ON s.id = r.session_id

            WHERE r.id = %s

            LIMIT 1
        """, (
            run_id,
        ))


        run = cursor.fetchone()


        if not run:

            return jsonify({
                "success": False,
                "error": "Machine run not found."
            }), 404


        # ----------------------------------------------------
        # GET
        # ----------------------------------------------------

        if request.method == "GET":

            cursor.execute("""
                SELECT
                    id,
                    session_id,
                    run_id,
                    machine_id,

                    loss_type_id,
                    loss_code,
                    loss_name,
                    loss_minutes,

                    started_at,
                    ended_at,
                    remarks,
                    created_at

                FROM oee_machine_loss_events

                WHERE run_id = %s

                ORDER BY id
            """, (
                run_id,
            ))


            rows = cursor.fetchall() or []


            for row in rows:

                if row.get("loss_minutes") is not None:
                    row["loss_minutes"] = float(
                        row["loss_minutes"]
                    )


                for field in (
                    "started_at",
                    "ended_at",
                    "created_at",
                ):

                    value = row.get(field)

                    if (
                        value is not None
                        and hasattr(
                            value,
                            "isoformat"
                        )
                    ):
                        row[field] = (
                            value.isoformat()
                        )


            return jsonify({
                "success": True,
                "run_id": run_id,
                "losses": rows,
            })


        # ----------------------------------------------------
        # POST
        # ----------------------------------------------------

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
                    f"Machine run is {status}. "
                    "Loss cannot be changed."
                )
            }), 409


        data = request.get_json(
            silent=True
        ) or {}


        submitted_losses = data.get(
            "losses"
        )


        # ====================================================
        # V40 BATCH A1-A27 SAVE
        # ====================================================

        if isinstance(
            submitted_losses,
            list,
        ):

            expected_codes = {
                "A" + str(index)
                for index in range(
                    1,
                    28
                )
            }


            submitted_map = {}


            for item in submitted_losses:

                if not isinstance(
                    item,
                    dict,
                ):

                    return jsonify({
                        "success": False,
                        "error": (
                            "Invalid OEE loss row."
                        ),
                    }), 400


                code = str(
                    item.get(
                        "loss_code"
                    )
                    or ""
                ).strip().upper()


                if code not in expected_codes:

                    return jsonify({
                        "success": False,
                        "error": (
                            "Invalid OEE Loss Code: "
                            + code
                        ),
                    }), 400


                if code in submitted_map:

                    return jsonify({
                        "success": False,
                        "error": (
                            "Duplicate OEE Loss Code: "
                            + code
                        ),
                    }), 400


                try:
                    minutes = float(
                        item.get(
                            "loss_minutes",
                            0,
                        )
                        or 0
                    )

                except (
                    TypeError,
                    ValueError,
                ):

                    return jsonify({
                        "success": False,
                        "error": (
                            code
                            + " loss minutes must be numeric."
                        ),
                    }), 400


                if minutes < 0:

                    return jsonify({
                        "success": False,
                        "error": (
                            code
                            + " loss minutes cannot be negative."
                        ),
                    }), 400


                submitted_map[
                    code
                ] = minutes


            if set(
                submitted_map
            ) != expected_codes:

                return jsonify({
                    "success": False,
                    "error": (
                        "OEE Loss Entry must contain "
                        "exactly A1 to A27."
                    ),
                }), 400


            # Master is authority for ID, code and name.
            # Never trust client loss_type_id for mapping.

            cursor.execute("""
                SELECT
                    id,
                    loss_code,
                    loss_name

                FROM oee_loss_types

                WHERE is_active = 1
            """)


            master_rows = (
                cursor.fetchall()
                or []
            )


            master = {
                str(
                    row.get(
                        "loss_code"
                    )
                    or ""
                ).strip().upper():
                    row

                for row in master_rows
            }


            if set(master) != expected_codes:

                return jsonify({
                    "success": False,
                    "error": (
                        "Active OEE Loss Master "
                        "must contain exactly A1 to A27."
                    ),
                }), 400


            entry_date = (
                _oee_v15_parse_entry_date(
                    data.get(
                        "entry_date"
                    )
                    or run.get(
                        "session_date"
                    )
                )
            )


            start_value = (
                data.get(
                    "loss_start_time"
                )
                or data.get(
                    "start_time"
                )
                or run.get(
                    "oee_start_time"
                )
            )


            stop_value = (
                data.get(
                    "loss_stop_time"
                )
                or data.get(
                    "stop_time"
                )
                or run.get(
                    "oee_end_time"
                )
            )


            (
                loss_started_at,
                loss_ended_at,
                loss_period_minutes,
            ) = _oee_v15_parse_loss_period(
                entry_date,
                start_value,
                stop_value,
            )


            # Replace this run's current saved loss grid.
            # This prevents repeated Save Progress from doubling.

            cursor.execute("""
                DELETE FROM oee_machine_loss_events
                WHERE run_id = %s
            """, (
                run_id,
            ))


            for code in sorted(
                expected_codes,
                key=lambda value:
                    int(value[1:]),
            ):

                minutes = float(
                    submitted_map.get(
                        code,
                        0
                    )
                    or 0
                )


                if minutes <= 0:
                    continue


                master_row = master[
                    code
                ]


                values = {
                    "session_id":
                        run.get(
                            "session_id"
                        ),

                    "run_id":
                        run_id,

                    "machine_id":
                        run.get(
                            "machine_id"
                        ),

                    "operator_user_id":
                        run.get(
                            "operator_user_id"
                        )
                        or session.get(
                            "user_id"
                        ),

                    "operator_master_id":
                        run.get(
                            "operator_master_id"
                        ),

                    "operator_employee_no":
                        run.get(
                            "operator_employee_no"
                        ),

                    "operator_name":
                        run.get(
                            "operator_name"
                        ),

                    "loss_type_id":
                        master_row.get(
                            "id"
                        ),

                    "loss_code":
                        code,

                    "loss_name":
                        master_row.get(
                            "loss_name"
                        ),

                    "loss_minutes":
                        minutes,

                    "started_at":
                        loss_started_at,

                    "ended_at":
                        loss_ended_at,

                    "remarks":
                        None,
                }


                loss_id = (
                    _oee_v13_dynamic_insert(
                        cursor,
                        "oee_machine_loss_events",
                        values,
                    )
                )


                if not loss_id:

                    raise RuntimeError(
                        code
                        + " run-linked loss "
                        + "could not be saved."
                    )


            cursor.execute("""
                SELECT
                    id,
                    session_id,
                    run_id,
                    machine_id,

                    loss_type_id,
                    loss_code,
                    loss_name,
                    loss_minutes,

                    started_at,
                    ended_at

                FROM oee_machine_loss_events

                WHERE run_id = %s

                ORDER BY
                    CAST(
                        SUBSTRING(
                            loss_code,
                            2
                        )
                        AS UNSIGNED
                    ),
                    id
            """, (
                run_id,
            ))


            saved_rows = (
                cursor.fetchall()
                or []
            )


            for row in saved_rows:

                if row.get(
                    "loss_minutes"
                ) is not None:

                    row["loss_minutes"] = float(
                        row["loss_minutes"]
                    )


                for field in (
                    "started_at",
                    "ended_at",
                ):

                    value = row.get(
                        field
                    )

                    if (
                        value is not None
                        and hasattr(
                            value,
                            "isoformat"
                        )
                    ):

                        row[field] = (
                            value.isoformat()
                        )


            total_loss_minutes = round(
                sum(
                    float(
                        value
                        or 0
                    )

                    for value
                    in submitted_map.values()
                ),
                2,
            )


            # V43_SESSION_RECALC_CALL
            _machine_oee_recalculate_session_v43(
                cursor,
                run.get("session_id"),
            )

            conn.commit()


            return jsonify({
                "success": True,

                "run_id":
                    run_id,

                "session_id":
                    run.get(
                        "session_id"
                    ),

                "loss_period_minutes":
                    loss_period_minutes,

                "total_loss_minutes":
                    total_loss_minutes,

                "losses":
                    saved_rows,

                "message":
                    "Run-linked OEE losses saved.",
            })


        # ====================================================
        # LEGACY SINGLE LOSS POST
        # Kept for compatibility.
        # ====================================================

        try:
            loss_type_id = int(
                data.get(
                    "loss_type_id"
                )
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            loss_type_id = 0


        try:
            loss_minutes = float(
                data.get(
                    "loss_minutes"
                )
                or 0
            )

        except (
            TypeError,
            ValueError,
        ):
            loss_minutes = 0


        if loss_type_id <= 0:

            return jsonify({
                "success": False,
                "error": "Select Loss Reason."
            }), 400


        if loss_minutes <= 0:

            return jsonify({
                "success": False,
                "error": (
                    "Loss Minutes must be greater than 0."
                )
            }), 400


        cursor.execute("""
            SELECT
                id,
                loss_code,
                loss_name

            FROM oee_loss_types

            WHERE id = %s
              AND is_active = 1

            LIMIT 1
        """, (
            loss_type_id,
        ))


        master_row = cursor.fetchone()


        if not master_row:

            return jsonify({
                "success": False,
                "error": "Loss Reason not found."
            }), 404


        loss_code = str(
            master_row.get(
                "loss_code"
            )
            or ""
        ).strip().upper()


        if loss_code not in {
            "A" + str(index)
            for index in range(
                1,
                28
            )
        }:

            return jsonify({
                "success": False,
                "error": "Invalid OEE loss type."
            }), 400


        cursor.execute("""
            SELECT
                id,
                loss_minutes

            FROM oee_machine_loss_events

            WHERE run_id = %s
              AND loss_type_id = %s

            ORDER BY id

            LIMIT 1

            FOR UPDATE
        """, (
            run_id,
            loss_type_id,
        ))


        existing = cursor.fetchone()


        if existing:

            new_minutes = (
                float(
                    existing.get(
                        "loss_minutes"
                    )
                    or 0
                )
                +
                loss_minutes
            )


            cursor.execute("""
                UPDATE oee_machine_loss_events
                SET loss_minutes = %s
                WHERE id = %s
            """, (
                new_minutes,
                existing["id"],
            ))


            loss_event_id = (
                existing["id"]
            )

        else:

            values = {
                "session_id":
                    run.get(
                        "session_id"
                    ),

                "run_id":
                    run_id,

                "machine_id":
                    run.get(
                        "machine_id"
                    ),

                "operator_user_id":
                    run.get(
                        "operator_user_id"
                    )
                    or session.get(
                        "user_id"
                    ),

                "operator_master_id":
                    run.get(
                        "operator_master_id"
                    ),

                "operator_employee_no":
                    run.get(
                        "operator_employee_no"
                    ),

                "operator_name":
                    run.get(
                        "operator_name"
                    ),

                "loss_type_id":
                    loss_type_id,

                "loss_code":
                    loss_code,

                "loss_name":
                    master_row.get(
                        "loss_name"
                    ),

                "loss_minutes":
                    loss_minutes,
            }


            loss_event_id = (
                _oee_v13_dynamic_insert(
                    cursor,
                    "oee_machine_loss_events",
                    values,
                )
            )


        # V43_SESSION_RECALC_CALL
        _machine_oee_recalculate_session_v43(
            cursor,
            run.get("session_id"),
        )

        conn.commit()


        return jsonify({
            "success": True,
            "loss_event_id":
                loss_event_id,
            "loss_code":
                loss_code,
            "message":
                loss_code
                + " loss saved.",
        })


    except Exception as error:

        if conn:
            conn.rollback()


        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()



@quality_check_bp.route(
    "/api/oee-machine/run/<int:run_id>/losses/<int:event_id>",
    methods=["DELETE"]
)
def machine_oee_delete_run_loss_v1(
    run_id,
    event_id,
):

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

        conn.start_transaction()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                r.run_status

            FROM oee_machine_loss_events l

            JOIN oee_machine_runs r
              ON r.id = l.run_id

            WHERE l.id = %s
              AND l.run_id = %s

            LIMIT 1

            FOR UPDATE
        """, (
            event_id,
            run_id,
        ))


        row = cursor.fetchone()


        if not row:

            return jsonify({
                "success": False,
                "error": "Loss entry not found."
            }), 404


        status = str(
            row.get("run_status")
            or ""
        ).strip().upper()


        if status not in (
            "RUNNING",
            "HANDOVER_PENDING",
        ):

            return jsonify({
                "success": False,
                "error": (
                    "Completed machine losses "
                    "cannot be changed."
                )
            }), 409


        cursor.execute("""
            DELETE FROM oee_machine_loss_events

            WHERE id = %s
              AND run_id = %s
        """, (
            event_id,
            run_id,
        ))


        conn.commit()


        return jsonify({
            "success": True,
            "message": "Loss removed."
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

# MACHINE_OEE_SESSION_METRICS_PERSIST_V43
def _machine_oee_recalculate_session_v43(
    cursor,
    session_id,
):
    """
    Recalculate and persist machine-wise OEE.

    Uses the same confirmed calculation inputs as
    the existing Live Machine OEE calculation.

    This helper does not commit.
    Caller owns the transaction.
    """

    from .oee_persistence import (
        OEE_MACHINE_PROFILE_MAP,
    )


    if not session_id:
        return None


    # -------------------------------------------------
    # SESSION + MACHINE PROFILE
    # -------------------------------------------------

    cursor.execute("""
        SELECT
            s.id AS session_id,
            s.planned_minutes,

            m.machine_no

        FROM oee_machine_sessions s

        JOIN oee_machines m
          ON m.id = s.machine_id

        WHERE s.id = %s

        LIMIT 1
    """, (
        session_id,
    ))


    machine_session = (
        cursor.fetchone()
    )


    if not machine_session:
        return None


    # OEE_MACHINE_NO_NORMALIZE_V43
    # Normalize exactly the same way get_oee_formula_profile() does,
    # so "cnc 01", "CNC01", "CNC  01" all resolve to "CNC 01".
    machine_no = " ".join(
        str(
            machine_session.get("machine_no")
            or ""
        )
        .strip()
        .upper()
        .split()
    )


    profile = (
        OEE_MACHINE_PROFILE_MAP.get(
            machine_no
        )
    )


    if not profile:
        return None


    # -------------------------------------------------
    # PRODUCTION TOTALS
    # -------------------------------------------------

    cursor.execute("""
        SELECT
            COUNT(*) AS run_count,

            COALESCE(
                SUM(ok_qty),
                0
            ) AS total_ok_qty,

            COALESCE(
                SUM(rejected_qty),
                0
            ) AS total_rejected_qty,

            COALESCE(
                SUM(hold_qty),
                0
            ) AS total_hold_qty,

            COALESCE(
                SUM(
                    ok_qty
                    *
                    (
                        cycle_minutes
                        +
                        (cycle_seconds / 60.0)
                        +
                        load_unload_minutes
                        +
                        (
                            load_unload_seconds
                            / 60.0
                        )
                    )
                ),
                0
            ) AS total_run_minutes,

            COALESCE(
                MAX(
                    cycle_minutes
                    +
                    (cycle_seconds / 60.0)
                    +
                    load_unload_minutes
                    +
                    (
                        load_unload_seconds
                        / 60.0
                    )
                ),
                0
            ) AS single_ideal_cycle_minutes

        FROM oee_machine_runs

        WHERE session_id = %s

          AND UPPER(
                TRIM(run_status)
              ) IN (
                'RUNNING',
                'HANDOVER_PENDING',
                'COMPLETED'
              )
    """, (
        session_id,
    ))


    totals = (
        cursor.fetchone()
        or {}
    )


    total_ok = int(
        totals.get(
            "total_ok_qty"
        )
        or 0
    )


    total_rejected = int(
        totals.get(
            "total_rejected_qty"
        )
        or 0
    )


    total_hold = int(
        totals.get(
            "total_hold_qty"
        )
        or 0
    )


    total_qty = (
        total_ok
        + total_rejected
        + total_hold
    )


    run_minutes = float(
        totals.get(
            "total_run_minutes"
        )
        or 0
    )


    run_count = int(
        totals.get(
            "run_count"
        )
        or 0
    )


    single_ideal_cycle_minutes = float(
        totals.get(
            "single_ideal_cycle_minutes"
        )
        or 0
    )


    # -------------------------------------------------
    # A1-A27 SESSION LOSS TOTALS
    # -------------------------------------------------

    cursor.execute("""
        SELECT
            UPPER(
                TRIM(loss_code)
            ) AS loss_code,

            COALESCE(
                SUM(loss_minutes),
                0
            ) AS loss_minutes

        FROM oee_machine_loss_events

        WHERE session_id = %s

        GROUP BY
            UPPER(
                TRIM(loss_code)
            )
    """, (
        session_id,
    ))


    loss_rows = (
        cursor.fetchall()
        or []
    )


    loss_map = {
        str(
            row.get(
                "loss_code"
            )
            or ""
        ).strip().upper():
            float(
                row.get(
                    "loss_minutes"
                )
                or 0
            )

        for row in loss_rows
    }


    ar_codes = tuple(
        profile.get(
            "ar_loss_codes"
        )
        or ()
    )


    pr_codes = tuple(
        profile.get(
            "pr_loss_codes"
        )
        or ()
    )


    ar_loss = sum(
        loss_map.get(
            code,
            0.0
        )
        for code in ar_codes
    )


    pr_loss = sum(
        loss_map.get(
            code,
            0.0
        )
        for code in pr_codes
    )


    # -------------------------------------------------
    # PLANNED MINUTES
    # -------------------------------------------------

    planned_minutes = (
        float(
            machine_session.get(
                "planned_minutes"
            )
        )

        if machine_session.get(
            "planned_minutes"
        ) is not None

        else 660.0
    )


    available_time = (
        planned_minutes
    )


    # -------------------------------------------------
    # TARGET / PLAN VS ACTUAL
    # -------------------------------------------------

    target_deduct_code = str(
        profile.get(
            "target_deduct_code"
        )
        or ""
    ).strip().upper()


    # -------------------------------------------------
    # SESSION TARGET / PLAN VS ACTUAL
    #
    # Machine session may contain multiple runs/JCs
    # with different Ideal Cycle Times.
    #
    # Excel-compatible cumulative method:
    #
    #   Session Target =
    #       SUM(each run Target Qty)
    #
    #   Run Target =
    #       MAX(Run Planned - Run A7/A8, 0)
    #       / Run Ideal Cycle
    #
    # Never average individual JC PVA/OEE values.
    # -------------------------------------------------

    cursor.execute("""
        SELECT
            r.id AS run_id,

            CASE
                WHEN
                    r.oee_start_time IS NULL
                    OR r.oee_end_time IS NULL
                THEN 660.0

                WHEN
                    TIME_TO_SEC(r.oee_end_time)
                    >=
                    TIME_TO_SEC(r.oee_start_time)

                THEN
                    (
                        TIME_TO_SEC(r.oee_end_time)
                        -
                        TIME_TO_SEC(r.oee_start_time)
                    ) / 60.0

                ELSE
                    (
                        86400
                        -
                        TIME_TO_SEC(r.oee_start_time)
                        +
                        TIME_TO_SEC(r.oee_end_time)
                    ) / 60.0
            END AS run_planned_minutes,

            (
                COALESCE(r.cycle_minutes, 0)
                +
                COALESCE(r.cycle_seconds, 0) / 60.0
                +
                COALESCE(r.load_unload_minutes, 0)
                +
                COALESCE(r.load_unload_seconds, 0) / 60.0
            ) AS ideal_cycle_minutes,

            COALESCE(
                SUM(
                    CASE
                        WHEN UPPER(
                            TRIM(le.loss_code)
                        ) = %s

                        THEN COALESCE(
                            le.loss_minutes,
                            0
                        )

                        ELSE 0
                    END
                ),
                0
            ) AS target_deduct_minutes

        FROM oee_machine_runs r

        LEFT JOIN oee_machine_loss_events le
          ON le.run_id = r.id
         AND le.session_id = r.session_id

        WHERE r.session_id = %s

          AND UPPER(
                TRIM(r.run_status)
              ) IN (
                'RUNNING',
                'HANDOVER_PENDING',
                'COMPLETED'
              )

        GROUP BY
            r.id,
            r.oee_start_time,
            r.oee_end_time,
            r.cycle_minutes,
            r.cycle_seconds,
            r.load_unload_minutes,
            r.load_unload_seconds

        ORDER BY r.id
    """, (
        target_deduct_code,
        session_id,
    ))


    target_rows = (
        cursor.fetchall()
        or []
    )


    target_deduct_minutes = sum(
        float(
            row.get("target_deduct_minutes")
            or 0
        )
        for row in target_rows
    )

    target_qty = 0.0
    valid_target_runs = 0


    for target_row in target_rows:

        ideal_cycle = float(
            target_row.get(
                "ideal_cycle_minutes"
            )
            or 0
        )

        if ideal_cycle <= 0:
            continue


        run_planned = float(
            target_row.get(
                "run_planned_minutes"
            )
            or 0
        )


        run_target_deduct = float(
            target_row.get(
                "target_deduct_minutes"
            )
            or 0
        )


        run_target_minutes = max(
            run_planned
            - run_target_deduct,
            0.0
        )


        target_qty += (
            run_target_minutes
            /
            ideal_cycle
        )


        valid_target_runs += 1


    if valid_target_runs <= 0:
        target_qty = None


    plan_vs_actual = None


    if (
        target_qty is not None
        and target_qty > 0
    ):

        plan_vs_actual = (
            total_qty
            /
            target_qty
        )





    if (
        run_count == 1
        and single_ideal_cycle_minutes > 0
    ):

        target_minutes = max(
            planned_minutes
            - target_deduct_minutes,
            0.0
        )


        target_qty = (
            target_minutes
            /
            single_ideal_cycle_minutes
        )


        if target_qty > 0:

            plan_vs_actual = (
                total_qty
                /
                target_qty
            )


    # -------------------------------------------------
    # CONFIRMED EXCEL OEE FORMULAS
    # -------------------------------------------------

    utilization = max(
        available_time
        - ar_loss,
        0.0
    )


    after_pr = max(
        utilization
        - pr_loss,
        0.0
    )


    ar_ratio = (
        utilization
        / available_time

        if available_time
        else 0.0
    )


    pr_ratio = (
        run_minutes
        / after_pr

        if after_pr
        else 0.0
    )


    qr_ratio = (
        total_ok
        / total_qty

        if total_qty
        else 0.0
    )


    oee_ratio = (
        ar_ratio
        * pr_ratio
        * qr_ratio
    )


    # -------------------------------------------------
    # PERSIST MACHINE SESSION RESULT
    # -------------------------------------------------

    cursor.execute("""
        UPDATE oee_machine_sessions

        SET
            total_ok_qty = %s,
            total_rejected_qty = %s,
            total_hold_qty = %s,

            total_run_minutes = %s,

            total_ar_loss_minutes = %s,
            total_pr_loss_minutes = %s,

            utilization_minutes = %s,
            after_pr_minutes = %s,

            target_qty = %s,
            plan_vs_actual = %s,

            ar_ratio = %s,
            pr_ratio = %s,
            qr_ratio = %s,
            oee_ratio = %s,

            updated_at = CURRENT_TIMESTAMP

        WHERE id = %s
    """, (
        total_ok,
        total_rejected,
        total_hold,

        run_minutes,

        ar_loss,
        pr_loss,

        utilization,
        after_pr,

        target_qty,
        plan_vs_actual,

        ar_ratio,
        pr_ratio,
        qr_ratio,
        oee_ratio,

        session_id,
    ))


    return {
        "session_id":
            session_id,

        "total_ok_qty":
            total_ok,

        "total_rejected_qty":
            total_rejected,

        "total_hold_qty":
            total_hold,

        "total_run_minutes":
            run_minutes,

        "total_ar_loss_minutes":
            ar_loss,

        "total_pr_loss_minutes":
            pr_loss,

        "utilization_minutes":
            utilization,

        "after_pr_minutes":
            after_pr,

        "target_qty":
            target_qty,

        "plan_vs_actual":
            plan_vs_actual,

        "ar_ratio":
            ar_ratio,

        "pr_ratio":
            pr_ratio,

        "qr_ratio":
            qr_ratio,

        "oee_ratio":
            oee_ratio,
    }


# MACHINE_OEE_LIVE_SESSION_CALC_V1

@quality_check_bp.route(
    "/api/oee-machine/session/<int:session_id>/live-oee",
    methods=["GET"]
)
def machine_oee_live_session_calc_v1(session_id):
    """
    Live MACHINE-WISE OEE.

    Official calculation level:
        Machine + Date + Shift

    JC runs are aggregated beneath the machine session.
    JC OEEs are NEVER averaged.
    """

    from .oee_persistence import (
        OEE_MACHINE_PROFILE_MAP,
    )

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


        # ----------------------------------------------------
        # SESSION + MACHINE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                s.id AS session_id,
                s.machine_id,
                s.session_date,
                s.shift_name,
                s.session_status,
                s.planned_minutes,

                m.machine_no,
                m.machine_name,
                m.machine_category,
                m.zone

            FROM oee_machine_sessions s

            JOIN oee_machines m
              ON m.id = s.machine_id

            WHERE s.id = %s

            LIMIT 1
        """, (
            session_id,
        ))


        machine_session = (
            cursor.fetchone()
        )


        if not machine_session:

            return jsonify({
                "success": False,
                "error": "Machine OEE session not found."
            }), 404


        # OEE_MACHINE_NO_NORMALIZE_V43 (live-oee route)
        # Normalize exactly as get_oee_formula_profile() does so
        # "cnc 01", "CNC01", "CNC  01" all resolve to "CNC 01".
        machine_no = " ".join(
            str(
                machine_session.get("machine_no")
                or ""
            )
            .strip()
            .upper()
            .split()
        )


        profile = (
            OEE_MACHINE_PROFILE_MAP.get(
                machine_no
            )
        )


        if not profile:

            return jsonify({
                "success": True,

                "calculation_ready":
                    False,

                "machine_no":
                    machine_no,

                "message": (
                    f"{machine_no} does not yet "
                    f"have a confirmed Excel formula profile."
                )
            })


        # ----------------------------------------------------
        # AGGREGATE ALL JC RUNS IN THIS MACHINE SESSION
        #
        # RUN MIN:
        # ? [
        #   OK Qty *
        #   (Cycle Time + Load/Unload)
        # ]
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS run_count,

                COALESCE(
                    SUM(ok_qty),
                    0
                ) AS total_ok_qty,

                COALESCE(
                    SUM(rejected_qty),
                    0
                ) AS total_rejected_qty,

                COALESCE(
                    SUM(hold_qty),
                    0
                ) AS total_hold_qty,

                COALESCE(
                    SUM(
                        ok_qty
                        *
                        (
                            cycle_minutes
                            +
                            (cycle_seconds / 60.0)
                            +
                            load_unload_minutes
                            +
                            (load_unload_seconds / 60.0)
                        )
                    ),
                    0
                ) AS total_run_minutes,

                COALESCE(
                    MAX(
                        cycle_minutes
                        +
                        (cycle_seconds / 60.0)
                        +
                        load_unload_minutes
                        +
                        (load_unload_seconds / 60.0)
                    ),
                    0
                ) AS single_ideal_cycle_minutes

            FROM oee_machine_runs

            WHERE session_id = %s
              AND UPPER(TRIM(run_status))
                    IN (
                        'RUNNING',
                        'HANDOVER_PENDING',
                        'COMPLETED'
                    )
        """, (
            session_id,
        ))


        totals = (
            cursor.fetchone()
            or {}
        )


        total_ok = int(
            totals.get("total_ok_qty")
            or 0
        )

        total_rejected = int(
            totals.get("total_rejected_qty")
            or 0
        )

        total_hold = int(
            totals.get("total_hold_qty")
            or 0
        )

        total_qty = (
            total_ok
            + total_rejected
            + total_hold
        )

        run_minutes = float(
            totals.get("total_run_minutes")
            or 0
        )


        # ----------------------------------------------------
        # AGGREGATE MACHINE SESSION LOSSES BY A-CODE
        # ----------------------------------------------------

        cursor.execute("""
            SELECT
                UPPER(TRIM(loss_code))
                    AS loss_code,

                COALESCE(
                    SUM(loss_minutes),
                    0
                ) AS loss_minutes

            FROM oee_machine_loss_events

            WHERE session_id = %s

            GROUP BY
                UPPER(TRIM(loss_code))
        """, (
            session_id,
        ))


        loss_rows = (
            cursor.fetchall()
            or []
        )


        loss_map = {
            str(
                row.get("loss_code")
                or ""
            ).strip().upper():
                float(
                    row.get("loss_minutes")
                    or 0
                )

            for row in loss_rows
        }


        ar_codes = tuple(
            profile.get(
                "ar_loss_codes"
            )
            or ()
        )

        pr_codes = tuple(
            profile.get(
                "pr_loss_codes"
            )
            or ()
        )


        ar_loss = sum(
            loss_map.get(
                code,
                0.0
            )
            for code in ar_codes
        )


        pr_loss = sum(
            loss_map.get(
                code,
                0.0
            )
            for code in pr_codes
        )


        # ----------------------------------------------------
        # PLANNED / AVAILABLE TIME
        #
        # Existing Excel fallback:
        # blank Start/End => 660 minutes.
        #
        # Until shift-close timing is implemented,
        # machine session uses that confirmed default.
        # ----------------------------------------------------

        planned_minutes = (
            float(
                machine_session.get(
                    "planned_minutes"
                )
            )
            if machine_session.get(
                "planned_minutes"
            ) is not None
            else 660.0
        )


        available_time = (
            planned_minutes
        )


        # MACHINE_OEE_LIVE_KPI_V32
        #
        # Plan vs Actual is valid directly when this
        # machine session contains one JC.
        #
        # Do NOT combine target quantities across mixed
        # JCs because different cycle times require a
        # separately proven Excel aggregation method.

        run_count = int(
            totals.get(
                "run_count"
            )
            or 0
        )


        single_ideal_cycle_minutes = float(
            totals.get(
                "single_ideal_cycle_minutes"
            )
            or 0
        )


        target_deduct_code = str(
            profile.get(
                "target_deduct_code"
            )
            or ""
        ).strip().upper()


        # PLVA_FIX_V1: deduct total AR loss (all AR codes), not just one code
        target_deduct_minutes = float(
    loss_map.get(
        target_deduct_code,
        0.0
    )
    or 0.0
)


        target_qty = None
        plan_vs_actual = None
        plan_vs_actual_note = None


        if (
            run_count == 1
            and single_ideal_cycle_minutes > 0
        ):

            target_minutes = max(
                planned_minutes
                - target_deduct_minutes,
                0.0
            )


            target_qty = (
                target_minutes
                /
                single_ideal_cycle_minutes
            )


            if target_qty > 0:

                plan_vs_actual = (
                    total_qty
                    /
                    target_qty
                )


        elif run_count > 1:

            plan_vs_actual_note = (
                "Plan vs Actual is not combined "
                "across mixed JC cycle times."
            )


        elif single_ideal_cycle_minutes <= 0:

            plan_vs_actual_note = (
                "Enter Cycle Time and Load/Unload "
                "then Save Progress."
            )


        utilization = max(
            available_time
            - ar_loss,
            0.0
        )


        after_pr = max(
            utilization
            - pr_loss,
            0.0
        )


        ar_ratio = (
            utilization
            / available_time

            if available_time
            else 0.0
        )


        pr_ratio = (
            run_minutes
            / after_pr

            if after_pr
            else 0.0
        )


        # Production-confirmed JMS behavior:
        # no produced quantity => QR 0.
        qr_ratio = (
            total_ok
            / total_qty

            if total_qty
            else 0.0
        )


        oee_ratio = (
            ar_ratio
            * pr_ratio
            * qr_ratio
        )


        # ----------------------------------------------------
        # LOSS DETAIL
        # ----------------------------------------------------

        losses = []

        for index in range(
            1,
            28
        ):

            code = f"A{index}"

            minutes = float(
                loss_map.get(
                    code,
                    0.0
                )
            )

            if minutes <= 0:
                continue


            categories = []


            if code in ar_codes:
                categories.append("AR")


            if code in pr_codes:
                categories.append("PR")


            losses.append({
                "loss_code":
                    code,

                "loss_minutes":
                    minutes,

                "categories":
                    categories,
            })


        session_date = (
            machine_session.get(
                "session_date"
            )
        )


        if (
            session_date is not None
            and hasattr(
                session_date,
                "isoformat"
            )
        ):

            session_date = (
                session_date.isoformat()
            )


        return jsonify({
            "success": True,

            "calculation_ready":
                True,

            "session_id":
                session_id,

            "session_date":
                session_date,

            "shift_name":
                machine_session.get(
                    "shift_name"
                ),

            "machine": {
                "id":
                    machine_session.get(
                        "machine_id"
                    ),

                "machine_no":
                    machine_no,

                "machine_name":
                    machine_session.get(
                        "machine_name"
                    ),

                "zone":
                    machine_session.get(
                        "zone"
                    ),
            },

            "formula_profile":
                profile.get("name"),

            "run_count":
                int(
                    totals.get(
                        "run_count"
                    )
                    or 0
                ),

            "planned_minutes":
                planned_minutes,

            "run_minutes":
                run_minutes,

            "ok_qty":
                total_ok,

            "rejected_qty":
                total_rejected,

            "hold_qty":
                total_hold,

            "total_qty":
                total_qty,

            "ar_loss_minutes":
                ar_loss,

            "pr_loss_minutes":
                pr_loss,

            "utilization_minutes":
                utilization,

            "after_pr_minutes":
                after_pr,

            "target_qty":
                target_qty,

            "plan_vs_actual":
                plan_vs_actual,

            "plan_vs_actual_note":
                plan_vs_actual_note,

            "target_deduct_code":
                target_deduct_code,

            "target_deduct_minutes":
                target_deduct_minutes,

            "ar_ratio":
                ar_ratio,

            "pr_ratio":
                pr_ratio,

            "qr_ratio":
                qr_ratio,

            "oee_ratio":
                oee_ratio,

            "losses":
                losses,
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

# MACHINE_OEE_TYPED_KPI_PREVIEW_V1
# Real-time KPI preview as operator types values in the form.
# Pure calculation -- does NOT save to DB.

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
    Return Machine OEE KPI for a given machine + shift + date.

    Query params:
      shift_name   -- required, e.g. "Shift 1"
      entry_date   -- optional YYYY-MM-DD, defaults to today

    Returns the same KPI payload as /session/<id>/live-oee
    so the frontend can display Plan vs Actual, AR, PR, QR, OEE.
    """

    from .oee_persistence import (
        OEE_MACHINE_PROFILE_MAP,
    )

    import datetime as _dt

    conn   = None
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


        shift_name = str(
            request.args.get("shift_name")
            or ""
        ).strip()

        if not shift_name:

            return jsonify({
                "success": False,
                "error": "shift_name query param is required."
            }), 400


        raw_date = str(
            request.args.get("entry_date")
            or ""
        ).strip()

        if raw_date:

            try:
                entry_date = _dt.date.fromisoformat(
                    raw_date
                )
            except ValueError:
                return jsonify({
                    "success": False,
                    "error": (
                        "entry_date must be YYYY-MM-DD."
                    )
                }), 400

        else:
            entry_date = _dt.date.today()


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        # --------------------------------------------------
        # STEP 1 -- find the matching machine session
        # --------------------------------------------------

        cursor.execute("""
            SELECT
                s.id          AS session_id,
                s.machine_id,
                s.session_date,
                s.shift_name,
                s.session_status,
                s.planned_minutes,

                m.machine_no,
                m.machine_name,
                m.machine_category,
                m.zone

            FROM oee_machine_sessions s

            JOIN oee_machines m
              ON m.id = s.machine_id

            WHERE s.machine_id  = %s
              AND LOWER(TRIM(s.shift_name)) = LOWER(TRIM(%s))
              AND s.session_date = %s

            LIMIT 1
        """, (
            machine_id,
            shift_name,
            entry_date,
        ))


        machine_session = (
            cursor.fetchone()
        )


        if not machine_session:

            return jsonify({
                "success": True,
                "has_session": False,
                "session": None,
                "message": (
                    "No OEE runs recorded yet "
                    "for this machine / shift today."
                )
            })


        session_id = int(
            machine_session.get("session_id")
        )


        # --------------------------------------------------
        # STEP 2 -- normalize machine_no + resolve profile
        # (identical to live-oee route)
        # --------------------------------------------------

        machine_no = " ".join(
            str(
                machine_session.get("machine_no")
                or ""
            )
            .strip()
            .upper()
            .split()
        )


        profile = (
            OEE_MACHINE_PROFILE_MAP.get(
                machine_no
            )
        )


        if not profile:

            return jsonify({
                "success": True,

                "calculation_ready":
                    False,

                "machine_no":
                    machine_no,

                "message": (
                    f"{machine_no} does not yet "
                    f"have a confirmed Excel formula profile."
                )
            })


        # --------------------------------------------------
        # STEP 3 -- aggregate JC runs for this session
        # --------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*) AS run_count,

                COALESCE(SUM(ok_qty),       0) AS total_ok_qty,
                COALESCE(SUM(rejected_qty), 0) AS total_rejected_qty,
                COALESCE(SUM(hold_qty),     0) AS total_hold_qty,

                COALESCE(
                    SUM(
                        ok_qty
                        *
                        (
                            cycle_minutes
                            + (cycle_seconds / 60.0)
                            + load_unload_minutes
                            + (load_unload_seconds / 60.0)
                        )
                    ),
                    0
                ) AS total_run_minutes,

                COALESCE(
                    MAX(
                        cycle_minutes
                        + (cycle_seconds / 60.0)
                        + load_unload_minutes
                        + (load_unload_seconds / 60.0)
                    ),
                    0
                ) AS single_ideal_cycle_minutes

            FROM oee_machine_runs

            WHERE session_id = %s
              AND UPPER(TRIM(run_status))
                    IN (
                        'RUNNING',
                        'HANDOVER_PENDING',
                        'COMPLETED'
                    )
        """, (
            session_id,
        ))


        totals = (
            cursor.fetchone()
            or {}
        )


        total_ok       = int(totals.get("total_ok_qty")       or 0)
        total_rejected = int(totals.get("total_rejected_qty") or 0)
        total_hold     = int(totals.get("total_hold_qty")     or 0)
        total_qty      = total_ok + total_rejected + total_hold

        run_minutes = float(totals.get("total_run_minutes") or 0)


        # --------------------------------------------------
        # STEP 4 -- aggregate loss events by A-code
        # --------------------------------------------------

        cursor.execute("""
            SELECT
                UPPER(TRIM(loss_code)) AS loss_code,

                COALESCE(SUM(loss_minutes), 0) AS loss_minutes

            FROM oee_machine_loss_events

            WHERE session_id = %s

            GROUP BY UPPER(TRIM(loss_code))
        """, (
            session_id,
        ))


        loss_map = {
            str(
                row.get("loss_code")
                or ""
            ).strip().upper():
                float(
                    row.get("loss_minutes")
                    or 0
                )

            for row in (
                cursor.fetchall()
                or []
            )
        }


        ar_codes = tuple(profile.get("ar_loss_codes") or ())
        pr_codes = tuple(profile.get("pr_loss_codes") or ())

        ar_loss = sum(loss_map.get(c, 0.0) for c in ar_codes)
        pr_loss = sum(loss_map.get(c, 0.0) for c in pr_codes)


        # --------------------------------------------------
        # STEP 5 -- planned / available time
        # --------------------------------------------------

        planned_minutes = (
            float(
                machine_session.get("planned_minutes")
            )
            if machine_session.get("planned_minutes") is not None
            else 660.0
        )

        available_time = planned_minutes


        # --------------------------------------------------
        # STEP 6 -- Plan vs Actual
        # --------------------------------------------------

        run_count = int(totals.get("run_count") or 0)

        single_ideal_cycle_minutes = float(
            totals.get("single_ideal_cycle_minutes")
            or 0
        )

        target_deduct_code = str(
            profile.get("target_deduct_code") or ""
        ).strip().upper()

        target_deduct_minutes = float(
            loss_map.get(target_deduct_code, 0.0)
            or 0
        )


        target_qty        = None
        plan_vs_actual    = None
        plan_vs_actual_note = None


        if (
            run_count == 1
            and single_ideal_cycle_minutes > 0
        ):

            target_minutes = max(
                planned_minutes - target_deduct_minutes,
                0.0
            )

            target_qty = (
                target_minutes
                / single_ideal_cycle_minutes
            )

            if target_qty > 0:
                plan_vs_actual = (
                    total_qty
                    / target_qty
                )


        elif run_count > 1:

            plan_vs_actual_note = (
                "Plan vs Actual is not combined "
                "across mixed JC cycle times."
            )


        elif single_ideal_cycle_minutes <= 0:

            plan_vs_actual_note = (
                "Enter Cycle Time and Load/Unload "
                "then Save Progress."
            )


        # --------------------------------------------------
        # STEP 7 -- AR / PR / QR / OEE ratios
        # --------------------------------------------------

        utilization = max(available_time - ar_loss, 0.0)
        after_pr    = max(utilization    - pr_loss, 0.0)

        ar_ratio = (
            utilization / available_time
            if available_time else 0.0
        )

        pr_ratio = (
            run_minutes / after_pr
            if after_pr else 0.0
        )

        qr_ratio = (
            total_ok / total_qty
            if total_qty else 0.0
        )

        oee_ratio = ar_ratio * pr_ratio * qr_ratio


        # --------------------------------------------------
        # STEP 8 -- loss detail
        # --------------------------------------------------

        losses = []

        for index in range(1, 28):

            code    = f"A{index}"
            minutes = float(loss_map.get(code, 0.0))

            if minutes <= 0:
                continue

            categories = []

            if code in ar_codes:
                categories.append("AR")

            if code in pr_codes:
                categories.append("PR")

            losses.append({
                "loss_code":   code,
                "loss_minutes": minutes,
                "categories":   categories,
            })


        # --------------------------------------------------
        # STEP 9 -- format session_date for JSON
        # --------------------------------------------------

        sess_date = machine_session.get("session_date")

        if (
            sess_date is not None
            and hasattr(sess_date, "isoformat")
        ):
            sess_date = sess_date.isoformat()


        return jsonify({
            "success": True,

            "calculation_ready": True,

            "session_id":   session_id,
            "session_date": sess_date,
            "shift_name":   machine_session.get("shift_name"),

            "machine": {
                "id":           machine_session.get("machine_id"),
                "machine_no":   machine_no,
                "machine_name": machine_session.get("machine_name"),
                "zone":         machine_session.get("zone"),
            },

            "formula_profile":        profile.get("name"),
            "run_count":              run_count,
            "planned_minutes":        planned_minutes,
            "run_minutes":            run_minutes,

            "ok_qty":                 total_ok,
            "rejected_qty":           total_rejected,
            "hold_qty":               total_hold,
            "total_qty":              total_qty,

            "ar_loss_minutes":        ar_loss,
            "pr_loss_minutes":        pr_loss,
            "utilization_minutes":    utilization,
            "after_pr_minutes":       after_pr,

            "target_qty":             target_qty,
            "plan_vs_actual":         plan_vs_actual,
            "plan_vs_actual_note":    plan_vs_actual_note,
            "target_deduct_code":     target_deduct_code,
            "target_deduct_minutes":  target_deduct_minutes,

            "ar_ratio":               ar_ratio,
            "pr_ratio":               pr_ratio,
            "qr_ratio":               qr_ratio,
            "oee_ratio":              oee_ratio,

            "losses":                 losses,
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


# OEE_ZONE_LOGIN_HELPER_V1
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
                r.id AS run_id,
                r.session_id,
                r.machine_id,

                r.job_card_no,
                r.job_card_item_id,

                r.process_name,
                r.run_status,

                r.operator_user_id,
                r.operator_name,

                m.machine_no,
                m.machine_name,
                m.machine_category,
                m.zone

            FROM oee_machine_runs r

            JOIN oee_machines m
              ON m.id = r.machine_id

            WHERE r.id = %s

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


def _oee_v13_table_columns(cursor, table_name):

    allowed_tables = {
        "oee_machine_sessions",
        "oee_machine_loss_events",
    }

    if table_name not in allowed_tables:
        raise RuntimeError(
            "Invalid OEE table requested."
        )

    cursor.execute(
        "SHOW COLUMNS FROM `"
        + table_name
        + "`"
    )

    rows = cursor.fetchall()

    columns = {}

    for row in rows:

        field = (
            row.get("Field")
            or row.get("field")
        )

        if field:
            columns[str(field)] = row

    return columns


def _oee_v13_meta_value(row, *keys):

    for key in keys:

        if key in row:
            return row.get(key)

    return None


def _oee_v13_dynamic_insert(
    cursor,
    table_name,
    candidate_values,
):

    columns = _oee_v13_table_columns(
        cursor,
        table_name,
    )

    insert_columns = []
    insert_values = []

    for field in columns:

        if field in candidate_values:

            insert_columns.append(field)
            insert_values.append(
                candidate_values[field]
            )

    missing_required = []

    for field, meta in columns.items():

        if field in insert_columns:
            continue

        null_value = str(
            _oee_v13_meta_value(
                meta,
                "Null",
                "null",
            )
            or ""
        ).upper()

        default_value = _oee_v13_meta_value(
            meta,
            "Default",
            "default",
        )

        extra_value = str(
            _oee_v13_meta_value(
                meta,
                "Extra",
                "extra",
            )
            or ""
        ).lower()

        if (
            null_value == "NO"
            and default_value is None
            and "auto_increment" not in extra_value
            and "generated" not in extra_value
        ):

            missing_required.append(field)

    if missing_required:

        raise RuntimeError(
            "OEE table "
            + table_name
            + " has unsupported required column(s): "
            + ", ".join(missing_required)
        )

    if not insert_columns:

        raise RuntimeError(
            "No compatible columns found for "
            + table_name
        )

    safe_columns = [
        "`" + field.replace("`", "") + "`"
        for field in insert_columns
    ]

    placeholders = [
        "%s"
        for _ in insert_columns
    ]

    sql = (
        "INSERT INTO `"
        + table_name
        + "` ("
        + ", ".join(safe_columns)
        + ") VALUES ("
        + ", ".join(placeholders)
        + ")"
    )

    cursor.execute(
        sql,
        tuple(insert_values),
    )

    return cursor.lastrowid


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


def _oee_v13_find_session(
    cursor,
    machine_id,
    shift_name,
):

    cursor.execute(
        """
        SELECT *
        FROM oee_machine_sessions
        WHERE machine_id = %s
          AND session_date = CURDATE()
          AND shift_name = %s
        LIMIT 1
        """,
        (
            machine_id,
            shift_name,
        ),
    )

    return cursor.fetchone()


def _oee_v13_get_or_create_session(
    cursor,
    machine,
    formula_profile,
    shift_name,
    opened_by_user_id,
    opened_by_name,
):

    from datetime import (
        date,
        datetime,
    )

    existing = _oee_v13_find_session(
        cursor,
        machine.get("id"),
        shift_name,
    )

    if existing:

        status = str(
            existing.get("session_status")
            or "OPEN"
        ).strip().upper()

        if status != "OPEN":

            raise ValueError(
                "This machine/shift OEE record "
                "is not open."
            )

        return existing

    now_value = datetime.now()

    profile_name = str(
        formula_profile.get("name")
        or ""
    ).strip()

    values = {
        "machine_id":
            machine.get("id"),

        "session_date":
            date.today(),

        "shift_name":
            shift_name,

        "formula_profile":
            profile_name,

        "session_status":
            "OPEN",

        "opened_by_user_id":
            opened_by_user_id,

        "opened_by_user_name":
            opened_by_name,

        "opened_by_name":
            opened_by_name,

        "opened_by":
            opened_by_name,

        "started_at":
            now_value,

        "opened_at":
            now_value,

        # Keep current confirmed system behaviour.
        # Provisional Shift Start/End V11 is NOT
        # connected to official Planned Minutes yet.
        "planned_minutes":
            660,

        "created_at":
            now_value,

        "updated_at":
            now_value,
    }

    session_id = _oee_v13_dynamic_insert(
        cursor,
        "oee_machine_sessions",
        values,
    )

    if not session_id:

        existing = _oee_v13_find_session(
            cursor,
            machine.get("id"),
            shift_name,
        )

        if existing:
            return existing

        raise RuntimeError(
            "Machine OEE record could not be created."
        )

    cursor.execute(
        """
        SELECT *
        FROM oee_machine_sessions
        WHERE id = %s
        LIMIT 1
        """,
        (session_id,),
    )

    created = cursor.fetchone()

    if not created:

        raise RuntimeError(
            "Created Machine OEE record "
            "could not be loaded."
        )

    return created


def _oee_v13_loss_field_names(cursor):

    columns = _oee_v13_table_columns(
        cursor,
        "oee_machine_loss_events",
    )

    if "run_id" not in columns:

        raise RuntimeError(
            "oee_machine_loss_events.run_id "
            "is required for machine-level losses."
        )

    code_field = None

    for candidate in (
        "loss_code",
        "loss_code_snapshot",
    ):

        if candidate in columns:

            code_field = candidate
            break

    name_field = None

    for candidate in (
        "loss_name",
        "loss_name_snapshot",
    ):

        if candidate in columns:

            name_field = candidate
            break

    if not code_field:

        raise RuntimeError(
            "Loss Code column was not found."
        )

    if not name_field:

        raise RuntimeError(
            "Loss Name column was not found."
        )

    return (
        columns,
        code_field,
        name_field,
    )


# MACHINE_OEE_LOSS_TIME_V14
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


def _oee_v13_read_machine_losses(
    cursor,
    session_id,
):

    (
        columns,
        code_field,
        name_field,
    ) = _oee_v13_loss_field_names(
        cursor
    )

    cursor.execute(
        """
        SELECT *
        FROM oee_machine_loss_events
        WHERE session_id = %s
          AND run_id IS NULL
        ORDER BY id
        """,
        (session_id,),
    )

    rows = cursor.fetchall()

    result = []

    for row in rows:

        result.append({
            "id":
                row.get("id"),

            "event_id":
                row.get("id"),

            "loss_type_id":
                row.get("loss_type_id"),

            "loss_code":
                row.get(code_field),

            "loss_name":
                row.get(name_field),

            "loss_minutes":
                row.get("loss_minutes")
                or 0,

            "loss_start_time":
                _oee_v14_loss_time_text(
                    row.get("started_at")
                ),

            "loss_stop_time":
                _oee_v14_loss_time_text(
                    row.get("ended_at")
                ),
        })

    return result


# MACHINE_OEE_COMMON_LOSS_BLOCK_V15

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


def _oee_v15_find_session_on_date(
    cursor,
    machine_id,
    shift_name,
    entry_date,
):
    cursor.execute(
        """
        SELECT *
        FROM oee_machine_sessions
        WHERE machine_id = %s
          AND session_date = %s
          AND shift_name = %s
        LIMIT 1
        """,
        (
            machine_id,
            entry_date,
            shift_name,
        ),
    )

    return cursor.fetchone()


def _oee_v15_get_or_create_session_on_date(
    cursor,
    machine,
    formula_profile,
    shift_name,
    entry_date,
    opened_by_user_id,
    opened_by_name,
):

    existing = (
        _oee_v15_find_session_on_date(
            cursor,
            machine.get("id"),
            shift_name,
            entry_date,
        )
    )


    if existing:

        status = str(
            existing.get(
                "session_status"
            )
            or "OPEN"
        ).strip().upper()


        if status != "OPEN":

            raise ValueError(
                "This machine/date/shift OEE record is not open."
            )


        return existing


    now_value = datetime.now()


    values = {

        "machine_id":
            machine.get("id"),

        "session_date":
            entry_date,

        "shift_name":
            shift_name,

        "formula_profile":
            str(
                formula_profile.get(
                    "name"
                )
                or ""
            ).strip(),

        "session_status":
            "OPEN",

        "opened_by_user_id":
            opened_by_user_id,

        "opened_by_user_name":
            opened_by_name,

        "opened_by_name":
            opened_by_name,

        "opened_by":
            opened_by_name,

        "started_at":
            now_value,

        "opened_at":
            now_value,

        "planned_minutes":
            660,

        "created_at":
            now_value,

        "updated_at":
            now_value,
    }


    session_id = (
        _oee_v13_dynamic_insert(
            cursor,
            "oee_machine_sessions",
            values,
        )
    )


    if not session_id:

        existing = (
            _oee_v15_find_session_on_date(
                cursor,
                machine.get("id"),
                shift_name,
                entry_date,
            )
        )


        if existing:
            return existing


        raise RuntimeError(
            "Machine OEE record could not be created."
        )


    cursor.execute(
        """
        SELECT *
        FROM oee_machine_sessions
        WHERE id = %s
        LIMIT 1
        """,
        (
            session_id,
        ),
    )


    created = cursor.fetchone()


    if not created:

        raise RuntimeError(
            "Created Machine OEE record could not be loaded."
        )


    return created



@quality_check_bp.route(
    "/api/oee-machine/machine-losses/<int:machine_id>",
    methods=["GET", "POST"],
)
def machine_oee_machine_losses_v13(
    machine_id,
):

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


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        (
            machine,
            formula_profile,
            zone_login,
        ) = _oee_v13_machine_access(
            cursor,
            machine_id,
        )


        # ==================================================
        # GET
        # ==================================================

        if request.method == "GET":

            shift_name = str(
                request.args.get(
                    "shift_name"
                )
                or ""
            ).strip()


            if shift_name not in (
                "Shift 1",
                "Shift 2",
            ):

                return jsonify({
                    "success": False,
                    "error": (
                        "Please select a valid Shift."
                    ),
                }), 400


            entry_date = (
                _oee_v15_parse_entry_date(
                    request.args.get(
                        "entry_date"
                    )
                    or request.args.get(
                        "session_date"
                    )
                )
            )


            machine_session = (
                _oee_v15_find_session_on_date(
                    cursor,
                    machine_id,
                    shift_name,
                    entry_date,
                )
            )


            if not machine_session:

                return jsonify({
                    "success": True,

                    "session_id":
                        None,

                    "machine_id":
                        machine_id,

                    "entry_date":
                        entry_date.isoformat(),

                    "shift_name":
                        shift_name,

                    "formula_profile":
                        formula_profile.get(
                            "name"
                        ),

                    "losses":
                        [],
                })


            losses = (
                _oee_v13_read_machine_losses(
                    cursor,
                    machine_session.get(
                        "id"
                    ),
                )
            )


            return jsonify({
                "success": True,

                "session_id":
                    machine_session.get(
                        "id"
                    ),

                "machine_id":
                    machine_id,

                "entry_date":
                    entry_date.isoformat(),

                "shift_name":
                    shift_name,

                "formula_profile":
                    formula_profile.get(
                        "name"
                    ),

                "losses":
                    losses,
            })


        # ==================================================
        # POST
        # ==================================================

        data = request.get_json(
            silent=True
        ) or {}


        shift_name = str(
            data.get(
                "shift_name"
            )
            or ""
        ).strip()


        if shift_name not in (
            "Shift 1",
            "Shift 2",
        ):

            return jsonify({
                "success": False,
                "error": (
                    "Please select a valid Shift "
                    "before saving losses."
                ),
            }), 400


        entry_date = (
            _oee_v15_parse_entry_date(
                data.get(
                    "entry_date"
                )
                or data.get(
                    "session_date"
                )
            )
        )


        (
            loss_started_at,
            loss_ended_at,
            loss_period_minutes,
        ) = _oee_v15_parse_loss_period(
            entry_date,

            data.get(
                "loss_start_time"
            )
            or data.get(
                "start_time"
            ),

            data.get(
                "loss_stop_time"
            )
            or data.get(
                "stop_time"
            ),
        )


        operator_master_id = None

        operator_employee_no = None


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
            zone_login
            and (
                requested_master_id
                or requested_employee_no
            )
        ):

            master_operator = (
                _oee_operator_master_resolve_v24(
                    cursor,
                    requested_master_id,
                    requested_employee_no,
                )
            )


            operator_user_id = (
                session.get(
                    "user_id"
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


        else:

            (
                operator_user_id,
                operator_name,
            ) = _oee_v13_operator_identity(
                cursor,
                zone_login,

                data.get(
                    "actual_operator_user_id"
                ),
            )


        submitted_losses = data.get(
            "losses"
        )


        if not isinstance(
            submitted_losses,
            list,
        ):

            return jsonify({
                "success": False,
                "error": (
                    "OEE losses must be provided."
                ),
            }), 400


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


        master_rows = (
            cursor.fetchall()
        )


        master = {}


        for row in master_rows:

            code = str(
                row.get(
                    "loss_code"
                )
                or ""
            ).strip().upper()


            if code:

                master[
                    code
                ] = row


        expected_codes = {
            "A"
            + str(index)

            for index
            in range(
                1,
                28
            )
        }


        if set(master) != expected_codes:

            return jsonify({
                "success": False,
                "error": (
                    "Active OEE Loss Master "
                    "must contain A1 to A27."
                ),
            }), 400


        submitted_map = {}


        for item in submitted_losses:

            if not isinstance(
                item,
                dict,
            ):

                return jsonify({
                    "success": False,
                    "error": (
                        "Invalid OEE loss row."
                    ),
                }), 400


            code = str(
                item.get(
                    "loss_code"
                )
                or ""
            ).strip().upper()


            if code not in expected_codes:

                return jsonify({
                    "success": False,
                    "error": (
                        "Invalid OEE Loss Code: "
                        + code
                    ),
                }), 400


            if code in submitted_map:

                return jsonify({
                    "success": False,
                    "error": (
                        "Duplicate OEE Loss Code: "
                        + code
                    ),
                }), 400


            raw_minutes = item.get(
                "loss_minutes",
                0,
            )


            try:

                minutes = float(
                    raw_minutes
                    or 0
                )


            except (
                TypeError,
                ValueError,
            ):

                return jsonify({
                    "success": False,
                    "error": (
                        code
                        + " loss minutes "
                        + "must be numeric."
                    ),
                }), 400


            if minutes < 0:

                return jsonify({
                    "success": False,
                    "error": (
                        code
                        + " loss minutes "
                        + "cannot be negative."
                    ),
                }), 400


            submitted_map[
                code
            ] = minutes


        if set(
            submitted_map
        ) != expected_codes:

            missing = sorted(
                expected_codes
                - set(
                    submitted_map
                )
            )


            return jsonify({
                "success": False,
                "error": (
                    "OEE Loss Entry must contain "
                    "A1 to A27. Missing: "
                    + ", ".join(
                        missing
                    )
                ),
            }), 400


        total_loss_minutes = round(
            sum(
                submitted_map.values()
            ),
            2,
        )


        if total_loss_minutes <= 0:

            return jsonify({
                "success": False,
                "error": (
                    "Enter at least one machine loss "
                    "before saving this loss period."
                ),
            }), 400


        difference_minutes = round(
            loss_period_minutes
            - total_loss_minutes,
            2,
        )


        time_match = (
            abs(
                difference_minutes
            )
            < 0.01
        )


        machine_session = (
            _oee_v15_get_or_create_session_on_date(
                cursor,
                machine,
                formula_profile,
                shift_name,
                entry_date,
                operator_user_id,
                operator_name,
            )
        )


        session_id = (
            machine_session.get(
                "id"
            )
        )


        _oee_v13_loss_field_names(
            cursor
        )


        # Same Start/Stop period:
        # update only that block.
        #
        # Different Start/Stop period:
        # preserve previous loss blocks.

        cursor.execute(
            """
            DELETE FROM oee_machine_loss_events

            WHERE session_id = %s
              AND run_id IS NULL
              AND started_at = %s
              AND ended_at = %s
            """,
            (
                session_id,
                loss_started_at,
                loss_ended_at,
            ),
        )


        now_value = (
            datetime.now()
        )


        pr_codes = set(
            formula_profile.get(
                "pr_loss_codes"
            )
            or ()
        )


        saved_count = 0


        for index in range(
            1,
            28,
        ):

            code = (
                "A"
                + str(index)
            )


            minutes = submitted_map[
                code
            ]


            if minutes <= 0:
                continue


            master_row = master[
                code
            ]


            category = (
                "PR"

                if code
                in pr_codes

                else "AR"
            )


            values = {

                "session_id":
                    session_id,

                "run_id":
                    None,

                "machine_id":
                    machine_id,

                "operator_user_id":
                    operator_user_id,

                "operator_master_id":
                    operator_master_id,

                "operator_employee_no":
                    operator_employee_no,

                "operator_name":
                    operator_name,

                "loss_type_id":
                    master_row.get(
                        "id"
                    ),

                "loss_code":
                    code,

                "loss_code_snapshot":
                    code,

                "loss_name":
                    master_row.get(
                        "loss_name"
                    ),

                "loss_name_snapshot":
                    master_row.get(
                        "loss_name"
                    ),

                "loss_category":
                    category,

                "loss_category_snapshot":
                    category,

                "loss_minutes":
                    minutes,

                "started_at":
                    loss_started_at,

                "ended_at":
                    loss_ended_at,

                "shift_name":
                    shift_name,

                "entry_date":
                    entry_date,

                "remarks":
                    None,

                "created_by_user_id":
                    operator_user_id,

                "created_by_name":
                    operator_name,

                "created_at":
                    now_value,

                "updated_at":
                    now_value,
            }


            _oee_v13_dynamic_insert(
                cursor,
                "oee_machine_loss_events",
                values,
            )


            saved_count += 1


        conn.commit()


        losses = (
            _oee_v13_read_machine_losses(
                cursor,
                session_id,
            )
        )


        if time_match:

            message = (
                "Machine loss period saved. "
                "Loss time is fully accounted."
            )

            warning = None


        elif difference_minutes > 0:

            message = (
                "Machine loss period saved "
                "with a time warning."
            )

            warning = (
                str(
                    abs(
                        difference_minutes
                    )
                )
                + " minute(s) are not yet "
                + "accounted in A1-A27 losses."
            )


        else:

            message = (
                "Machine loss period saved "
                "with a time warning."
            )

            warning = (
                "A1-A27 losses exceed "
                "the loss period by "
                + str(
                    abs(
                        difference_minutes
                    )
                )
                + " minute(s)."
            )


        return jsonify({

            "success":
                True,

            "message":
                message,

            "warning":
                warning,

            "time_match":
                time_match,

            "entry_date":
                entry_date.isoformat(),

            "loss_start_time":
                loss_started_at.strftime(
                    "%H:%M:%S"
                ),

            "loss_stop_time":
                loss_ended_at.strftime(
                    "%H:%M:%S"
                ),

            "loss_period_minutes":
                loss_period_minutes,

            "total_loss_minutes":
                total_loss_minutes,

            "difference_minutes":
                difference_minutes,

            "session_id":
                session_id,

            "machine_id":
                machine_id,

            "shift_name":
                shift_name,

            "formula_profile":
                formula_profile.get(
                    "name"
                ),

            "loss_rows_saved":
                saved_count,

            "losses":
                losses,
        })


    except PermissionError as error:

        if conn:
            conn.rollback()


        return jsonify({
            "success": False,
            "error": str(error),
        }), 403


    except LookupError as error:

        if conn:
            conn.rollback()


        return jsonify({
            "success": False,
            "error": str(error),
        }), 404


    except ValueError as error:

        if conn:
            conn.rollback()


        return jsonify({
            "success": False,
            "error": str(error),
        }), 400


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


# MACHINE_OEE_MACHINE_LEVEL_LOSSES_V13_END

# OEE_MACHINE_SUMMARY_V1_START


@quality_check_bp.route("/api/oee-machine/summary-data", methods=["GET"])
def oee_machine_summary_data_v1():
    from flask import jsonify, request, session as flask_session
    import datetime
    import db

    role    = str(flask_session.get("role")    or "").strip().lower()
    user_id = flask_session.get("user_id")

    if role not in ("admin", "supervisor") or not user_id:
        return jsonify({"success": False, "error": "Access denied."}), 403

    date_str = (request.args.get("date") or "").strip()
    if not date_str:
        date_str = datetime.date.today().isoformat()

    try:
        datetime.date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid date."}), 400

    shift_raw = (request.args.get("shift")    or "All").strip()
    cat_raw   = (request.args.get("category") or "All").strip().upper()

    where_clauses = [
        "m.is_active = 1",
        "UPPER(TRIM(m.machine_category)) IN ('CNC','VMC')",
        "s.session_date = %s",
    ]
    params = [date_str]

    if shift_raw and shift_raw.lower() != "all":
        where_clauses.append("LOWER(TRIM(s.shift_name)) = LOWER(TRIM(%s))")
        params.append(shift_raw)

    if cat_raw and cat_raw != "ALL":
        where_clauses.append("UPPER(TRIM(m.machine_category)) = %s")
        params.append(cat_raw)

    sql = """
        SELECT
            m.id            AS machine_id,
            m.machine_no,
            m.machine_name,
            m.machine_category,
            m.zone,
            s.id            AS session_id,
            s.shift_name,
            s.session_status,
            COALESCE(s.planned_minutes, 480) AS planned_minutes,
            COUNT(r.id)                      AS run_count,
            COALESCE(SUM(r.ok_qty),       0) AS total_ok,
            COALESCE(SUM(r.rejected_qty), 0) AS total_rejected,
            COALESCE(SUM(r.hold_qty),     0) AS total_hold
        FROM oee_machines m
        JOIN oee_machine_sessions s
            ON s.machine_id = m.id
        LEFT JOIN oee_machine_runs r
            ON  r.session_id = s.id
            AND UPPER(TRIM(r.run_status))
                IN ('RUNNING','HANDOVER_PENDING','COMPLETED')
        WHERE {where}
        GROUP BY
            m.id, m.machine_no, m.machine_name,
            m.machine_category, m.zone,
            s.id, s.shift_name, s.session_status, s.planned_minutes
        ORDER BY m.machine_no, s.shift_name
    """.format(where=" AND ".join(where_clauses))

    conn   = None
    cursor = None

    try:
        conn   = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        rows   = cursor.fetchall()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    machines_map   = {}
    machines_order = []

    for row in rows:
        mid = row["machine_id"]
        if mid not in machines_map:
            machines_map[mid] = {
                "machine_id":       mid,
                "machine_no":       row["machine_no"],
                "machine_name":     row["machine_name"],
                "machine_category": row["machine_category"],
                "zone":             row["zone"],
                "sessions":         [],
            }
            machines_order.append(mid)

        machines_map[mid]["sessions"].append({
            "session_id":      row["session_id"],
            "shift_name":      row["shift_name"],
            "session_status":  row["session_status"],
            "planned_minutes": int(row["planned_minutes"] or 480),
            "run_count":       int(row["run_count"]       or 0),
            "total_ok":        int(row["total_ok"]        or 0),
            "total_rejected":  int(row["total_rejected"]  or 0),
            "total_hold":      int(row["total_hold"]      or 0),
        })

    machines_list = [machines_map[mid] for mid in machines_order]

    fleet_sessions = sum(len(m["sessions"])                                for m in machines_list)
    fleet_runs     = sum(s["run_count"]      for m in machines_list for s in m["sessions"])
    fleet_ok       = sum(s["total_ok"]       for m in machines_list for s in m["sessions"])
    fleet_rej      = sum(s["total_rejected"]  for m in machines_list for s in m["sessions"])
    fleet_hold     = sum(s["total_hold"]     for m in machines_list for s in m["sessions"])

    return jsonify({
        "success": True,
        "date":    date_str,
        "machines": machines_list,
        "fleet_totals": {
            "sessions":       fleet_sessions,
            "runs":           fleet_runs,
            "total_ok":       fleet_ok,
            "total_rejected": fleet_rej,
            "total_hold":     fleet_hold,
        },
    })

# OEE_MACHINE_SUMMARY_V1_END


# MACHINE_SHIFT_CAPACITY_V1

@quality_check_bp.route(
    "/api/oee-machine/shift-capacity/<int:machine_id>",
    methods=["GET"]
)
def machine_oee_shift_capacity_v1(machine_id):
    """
    Read-only machine shift capacity.

    Calculation level:
        Machine + Date + Shift

    Used minutes:
        unique occupied minutes from COMPLETED JC
        oee_start_time -> oee_end_time.

    Overlapping/batch JC ranges are counted only once.
    """

    from datetime import date as date_cls

    conn = None
    cursor = None

    try:

        role = str(
            session.get("role")
            or ""
        ).strip().lower()

        if role not in (
            "operator",
            "supervisor",
            "admin",
        ):

            return jsonify({
                "success": False,
                "error": "OEE access denied."
            }), 403


        session_date = str(
            request.args.get("date")
            or ""
        ).strip()

        shift_name = str(
            request.args.get("shift_name")
            or ""
        ).strip()

        shift_start = str(
            request.args.get("shift_start")
            or ""
        ).strip()

        shift_end = str(
            request.args.get("shift_end")
            or ""
        ).strip()


        if not session_date:

            session_date = (
                date_cls.today().isoformat()
            )


        if not shift_name:

            return jsonify({
                "success": False,
                "error": "Shift is required."
            }), 400


        if not shift_start or not shift_end:

            return jsonify({
                "success": False,
                "error": (
                    "Shift start and end time "
                    "are required."
                )
            }), 400


        def time_to_seconds_v1(value):

            value = str(
                value or ""
            ).strip()

            parts = value.split(":")

            if len(parts) not in (
                2,
                3,
            ):
                raise ValueError(
                    "Time must be HH:MM or HH:MM:SS."
                )

            try:
                hour = int(parts[0])
                minute = int(parts[1])

                second = (
                    int(parts[2])
                    if len(parts) == 3
                    else 0
                )

            except (TypeError, ValueError):
                raise ValueError(
                    "Invalid shift time."
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
                    "Invalid shift time."
                )


            return (
                hour * 3600
                + minute * 60
                + second
            )


        shift_start_sec = (
            time_to_seconds_v1(
                shift_start
            )
        )

        shift_end_sec = (
            time_to_seconds_v1(
                shift_end
            )
        )


        shift_end_abs = shift_end_sec

        if shift_end_abs <= shift_start_sec:
            shift_end_abs += 86400


        shift_seconds = (
            shift_end_abs
            - shift_start_sec
        )

        shift_minutes = round(
            shift_seconds / 60.0,
            2
        )


        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute("""
            SELECT
                r.id,
                r.job_card_no,
                CAST(
                    r.oee_start_time AS CHAR
                ) AS oee_start_time,
                CAST(
                    r.oee_end_time AS CHAR
                ) AS oee_end_time

            FROM oee_machine_runs r

            JOIN oee_machine_sessions s
              ON s.id = r.session_id

            WHERE r.machine_id = %s
              AND s.session_date = %s
              AND s.shift_name = %s
              AND r.run_status = 'COMPLETED'
              AND r.oee_start_time IS NOT NULL
              AND r.oee_end_time IS NOT NULL

            ORDER BY r.id
        """, (
            machine_id,
            session_date,
            shift_name,
        ))


        rows = cursor.fetchall()


        intervals = []


        for row in rows:

            run_start = (
                time_to_seconds_v1(
                    row.get(
                        "oee_start_time"
                    )
                )
            )

            run_end = (
                time_to_seconds_v1(
                    row.get(
                        "oee_end_time"
                    )
                )
            )


            if run_end <= run_start:
                run_end += 86400


            # Check equivalent positions on the
            # 24-hour timeline.
            #
            # This allows both normal and
            # cross-midnight shifts to clip
            # correctly.
            candidates = (
                (run_start - 86400, run_end - 86400),
                (run_start, run_end),
                (run_start + 86400, run_end + 86400),
            )


            for candidate_start, candidate_end in candidates:

                clipped_start = max(
                    candidate_start,
                    shift_start_sec
                )

                clipped_end = min(
                    candidate_end,
                    shift_end_abs
                )


                if clipped_end > clipped_start:

                    intervals.append(
                        (
                            clipped_start,
                            clipped_end,
                        )
                    )


        intervals.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )


        merged = []


        for start_sec, end_sec in intervals:

            if not merged:

                merged.append([
                    start_sec,
                    end_sec,
                ])

                continue


            previous = merged[-1]


            if start_sec <= previous[1]:

                previous[1] = max(
                    previous[1],
                    end_sec
                )

            else:

                merged.append([
                    start_sec,
                    end_sec,
                ])


        used_seconds = sum(
            end_sec - start_sec
            for start_sec, end_sec
            in merged
        )


        used_minutes = round(
            used_seconds / 60.0,
            2
        )


        remaining_minutes = round(
            max(
                shift_minutes
                - used_minutes,
                0.0
            ),
            2
        )


        return jsonify({
            "success": True,

            "machine_id":
                machine_id,

            "date":
                session_date,

            "shift_name":
                shift_name,

            "shift_start":
                shift_start,

            "shift_end":
                shift_end,

            "shift_minutes":
                shift_minutes,

            "used_minutes":
                used_minutes,

            "remaining_minutes":
                remaining_minutes,

            "completed_run_count":
                len(rows),

            "merged_interval_count":
                len(merged),
        })


    except ValueError as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 400


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



