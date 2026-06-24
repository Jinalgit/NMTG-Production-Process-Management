"""
Quality Check / Tracibility routes for Demo 2.
Includes WIP status tracking, in/out time recording, and audit trail.
"""

import re
from datetime import date as date_cls, datetime

from flask import Blueprint, jsonify, request, session
from mysql.connector import Error
from db import get_connection

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
    pm_row = _fetch_process_master_row(cursor, job_card_no, item_name)
    processes = _processes_from_pm_row(pm_row)
    if processes:
        return processes, "process_master", pm_row
    return _fetch_process_day_sequence(cursor, job_card_no), "job_card_process_days", None


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
            delivery_date = datetime.strptime(delivery_date[:10], "%Y-%m-%d").date()
        elif hasattr(delivery_date, "date") and not isinstance(delivery_date, date_cls):
            delivery_date = delivery_date.date()
        return (delivery_date - date_cls.today()).days
    except Exception:
        return 0


def _pending_previous_stage_error(cursor, job_card_no, processes, new_idx, old_idx, new_stage):
    if new_idx is None or not _has_column(cursor, "job_card_process_days", "in_time"):
        return None

    cursor.execute(
        """
        SELECT process_name, in_time, out_time
        FROM job_card_process_days
        WHERE job_card_no = %s
        ORDER BY id
        """,
        (job_card_no,),
    )
    pd_rows = cursor.fetchall()

    for idx, proc in enumerate(processes[:new_idx]):
        if old_idx is not None and idx == old_idx:
            continue
        pd_row = _find_pd_row(proc, pd_rows)
        if not pd_row or (pd_row.get("in_time") is None and pd_row.get("out_time") is None):
            return (
                f"Stage skip not allowed. Complete '{proc}' "
                f"before moving to '{new_stage}'."
            )
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
            LIMIT 1
            """,
            (search_value, search_value),
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
            if delivery and hasattr(delivery, "strftime"):
                delivery = delivery.strftime("%Y-%m-%d")

            enriched_items.append(
                {
                    "id": item.get("id"),
                    "job_card_no": actual_job_card_no,
                    "item_name": item_name,
                    "material": item.get("material") or (pm.get("material") if pm else "") or "",
                    "so_qty": item.get("so_qty"),
                    "job_card_qty": item.get("job_card_qty"),
                    "actual_qty": item.get("actual_qty") or 0,
                    "wip_status": item.get("wip_status") or "Pending",
                    "wip_stage_days": item.get("wip_stage_days") or 0,
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
            ("is_subcontract", "TINYINT(1) DEFAULT 0"),
            ("vendor_name", "VARCHAR(255)"),
        ]:
            if not _has_column(cursor, "job_card_process_days", col):
                cursor.execute(
                    f"ALTER TABLE job_card_process_days ADD COLUMN {col} {defn}"
                )

        has_time_cols = _has_column(cursor, "job_card_process_days", "in_time")

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
            processes = ei.get("processes") or []

            # Fallback: if process_master exact match not found, use saved process rows
            if not processes and pd_rows:
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
        cursor.execute("SELECT name FROM supervisors ORDER BY name")
        supervisors = [r["name"] for r in cursor.fetchall()]

        # ── Current logged-in user's process access (supervisors only) ─────────
        # Used by the frontend to block the stage-change modal entirely before
        # it opens, instead of letting the user click through and only failing
        # at the final confirm step.
        my_accessible_processes = None
        if session.get("role") == "supervisor":
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


@quality_check_bp.route("/api/page3/kanban_summary", methods=["GET"])
def page3_kanban_summary():
    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()
        user_id = session.get("user_id")

        if role not in ["admin", "supervisor"]:
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
        if role == "supervisor":
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


@quality_check_bp.route("/api/wip/update", methods=["POST"])
def update_wip():
    conn = None
    cursor = None

    try:
        data = request.json or {}
        print("WIP UPDATE PAYLOAD:", data)

        job_card_no = data.get("job_card_no")
        item_name = data.get("item_name")
        new_stage = data.get("new_stage")
        changed_by = data.get("changed_by")
        revoke_qty = int(data.get("revoke_qty") or 0)
        revoke_remarks = (data.get("revoke_remarks") or "").strip()
        actual_qty = data.get("actual_qty")
        try:
            actual_qty = int(actual_qty) if actual_qty not in [None, ""] else None
        except Exception:
            actual_qty = None
        print("ACTUAL QTY RECEIVED:", actual_qty)

        if not all([job_card_no, item_name, new_stage, changed_by]):
            return jsonify({"success": False, "error": "All fields required"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        actual_job_card_no = _resolve_job_card_no(cursor, job_card_no)
        if not actual_job_card_no:
            return jsonify({"success": False, "error": f"Job Card not found: {job_card_no}"}), 404
        job_card_no = actual_job_card_no

        cursor.execute(
            """
            SELECT wip_status, total_days, delivery_date
            FROM job_card_items
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
            """,
            (job_card_no, item_name.strip()),
        )
        row = cursor.fetchone()

        if not row:
            return jsonify({
                "success": False,
                "error": f"Item not found in job card {job_card_no}"
            }), 404

        old_stage = row["wip_status"] or "Pending"
        total = row["total_days"] or 0

        if _is_store_stage(old_stage):
            return jsonify({
                "success": False,
                "error": "Item is already in Store. No further movement allowed."
            }), 400

        # ── Supervisor process-access check ────────────────────────────────────
        # Supervisors can only move a job card OUT of a process they manage.
        # Admins bypass this check entirely.
        if session.get("role") == "supervisor":
            cursor.execute("""
                SELECT 1 FROM supervisor_process_access
                WHERE user_id = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                LIMIT 1
            """, (session.get("user_id"), old_stage))
            has_access = cursor.fetchone()
            if not has_access:
                return jsonify({
                    "success": False,
                    "error": f"You do not have permission to move items out of '{old_stage}'."
                }), 403

        cursor.execute(
            """
            SELECT pm.*
            FROM process_master pm
            JOIN job_card_items ji
              ON REPLACE(LOWER(TRIM(pm.model_name)), ' ', '') = REPLACE(LOWER(TRIM(ji.item_name)), ' ', '')
            WHERE ji.job_card_no = %s
              AND TRIM(ji.item_name) = TRIM(%s)
              AND (
                  ji.size IS NULL OR ji.size = ''
                  OR REPLACE(LOWER(TRIM(pm.size)), ' ', '') = REPLACE(LOWER(TRIM(ji.size)), ' ', '')
              )
            ORDER BY
              CASE WHEN REPLACE(LOWER(TRIM(pm.size)), ' ', '') = REPLACE(LOWER(TRIM(ji.size)), ' ', '') THEN 0 ELSE 1 END,
              pm.num_operations DESC
            LIMIT 1
            """,
            (job_card_no, item_name.strip()),
        )
        pm_row = cursor.fetchone()

        if pm_row:
            procs = [
                pm_row[f"p{i}"]
                for i in range(1, PROCESS_COUNT + 1)
                if pm_row.get(f"p{i}")
            ]

            old_idx = next(
                (i for i, p in enumerate(procs) if _match_processes(p, old_stage)),
                None
            )
            new_idx = next(
                (i for i, p in enumerate(procs) if _match_processes(p, new_stage)),
                None
            )

            if old_idx is not None and new_idx is not None:
                if new_idx != old_idx + 1:
                    return jsonify({
                        "success": False,
                        "error": (
                            f"Stage skip not allowed. Complete '{procs[old_idx]}' "
                            f"before moving to '{new_stage}'."
                        )
                    }), 400

        procs, process_source, pm_row = _fetch_process_sequence(
            cursor, job_card_no, item_name
        )
        validation_error, old_idx, new_idx = _validate_next_stage(
            cursor, job_card_no, procs, old_stage, new_stage
        )
        if validation_error:
            return jsonify({"success": False, "error": validation_error}), 400

        cursor.execute(
            """
            SELECT COALESCE(pdd.default_days, jpd.days, 0) AS stage_days
            FROM job_card_process_days jpd
            LEFT JOIN process_default_days pdd
              ON LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(pdd.process_name))
            WHERE jpd.job_card_no = %s
              AND LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(%s))
            LIMIT 1
            """,
            (job_card_no, old_stage),
        )
        pd_row = cursor.fetchone()

        process_found = pd_row is not None
        stage_days = int(pd_row["stage_days"] or 0) if pd_row else 0
        new_remaining = _remaining_days_from_delivery(row.get("delivery_date"))

        has_time_cols = _has_column(cursor, "job_card_process_days", "in_time")

        if has_time_cols:
            cursor.execute(
                """
                SELECT id, in_time
                FROM job_card_process_days
                WHERE job_card_no = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                ORDER BY id
                LIMIT 1
                """,
                (job_card_no, old_stage),
            )
            old_pd = cursor.fetchone()

            if old_pd and old_pd["in_time"] is None:
                cursor.execute(
                    """
                    SELECT out_time
                    FROM job_card_process_days
                    WHERE job_card_no = %s
                      AND id < %s
                      AND is_completed = 1
                      AND out_time IS NOT NULL
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (job_card_no, old_pd["id"]),
                )
                prev_pd = cursor.fetchone()

                resolved_in = None

                if prev_pd and prev_pd["out_time"] is not None:
                    resolved_in = prev_pd["out_time"]

                if resolved_in is None:
                    cursor.execute(
                        """
                        SELECT job_card_date
                        FROM job_cards
                        WHERE job_card_no = %s
                        LIMIT 1
                        """,
                        (job_card_no,),
                    )
                    jc_row = cursor.fetchone()

                    if jc_row and jc_row["job_card_date"] is not None:
                        resolved_in = jc_row["job_card_date"]

                if resolved_in is not None:
                    cursor.execute(
                        """
                        UPDATE job_card_process_days
                        SET in_time = %s
                        WHERE id = %s
                        """,
                        (resolved_in, old_pd["id"]),
                    )

            cursor.execute(
                """
                UPDATE job_card_process_days
                SET is_completed = 1,
                    end_date     = CURDATE(),
                    out_time     = NOW(),
                    actual_days  = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
                WHERE job_card_no = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                """,
                (job_card_no, old_stage),
            )

            cursor.execute(
                """
                UPDATE job_card_process_days
                SET is_completed = 1,
                    end_date     = CURDATE(),
                    out_time     = NOW(),
                    actual_days  = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
                WHERE job_card_no = %s
                  AND in_time IS NOT NULL
                  AND out_time IS NULL
                  AND LOWER(TRIM(process_name)) <> LOWER(TRIM(%s))
                """,
                (job_card_no, new_stage),
            )

            if _is_store_stage(new_stage):
                cursor.execute(
                    """
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, NOW()),
                        out_time = COALESCE(out_time, NOW()),
                        is_completed = 1,
                        end_date = CURDATE(),
                        actual_days = COALESCE(actual_days, 0)
                    WHERE job_card_no = %s
                      AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                    """,
                    (job_card_no, new_stage),
                )
                cursor.execute(
                    """
                    UPDATE job_cards
                    SET final_status = 'Completed'
                    WHERE job_card_no = %s
                    """,
                    (job_card_no,),
                )
            else:
                cursor.execute(
                    """
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, NOW()),
                        out_time = NULL,
                        is_completed = 0,
                        end_date = NULL,
                        actual_days = NULL
                    WHERE job_card_no = %s
                      AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                    """,
                    (job_card_no, new_stage),
                )

        else:
            cursor.execute(
                """
                UPDATE job_card_process_days
                SET is_completed = 1,
                    end_date = CURDATE()
                WHERE job_card_no = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                """,
                (job_card_no, old_stage),
            )

        cursor.execute(
            """
            UPDATE job_card_items
            SET wip_status = %s,
                remaining_days = %s,
                wip_stage_days = 0,
                actual_qty = COALESCE(%s, actual_qty)
            WHERE job_card_no = %s
              AND TRIM(item_name) = TRIM(%s)
            """,
            (new_stage, new_remaining, actual_qty, job_card_no, item_name.strip()),
        )

        cursor.execute(
            """
            INSERT INTO audit_trail
            (job_card_no, item_name, old_stage, new_stage, changed_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (job_card_no, item_name.strip(), old_stage, new_stage, changed_by),
        )

        if revoke_qty > 0:
            to_process = None

            if pm_row:
                procs = [
                    pm_row[f"p{i}"]
                    for i in range(1, PROCESS_COUNT + 1)
                    if pm_row.get(f"p{i}")
                ]

                old_idx = next(
                    (i for i, p in enumerate(procs)
                     if _match_processes(p, old_stage)),
                    None
                )

                if old_idx is not None and old_idx > 0:
                    to_process = procs[old_idx - 1]

            if to_process:
                cursor.execute(
                    """
                    INSERT INTO revoke_log
                    (job_card_no, item_name, from_process, to_process,
                     revoke_qty, remarks, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'Open')
                    """,
                    (
                        job_card_no,
                        item_name.strip(),
                        old_stage,
                        to_process,
                        revoke_qty,
                        revoke_remarks or None,
                    ),
                )

                new_revoke_id = cursor.lastrowid

                if pm_row:
                    procs = [
                        pm_row[f"p{i}"]
                        for i in range(1, PROCESS_COUNT + 1)
                        if pm_row.get(f"p{i}")
                    ]

                    to_idx = next(
                        (i for i, p in enumerate(procs)
                         if _match_processes(p, to_process)),
                        None
                    )
                    from_idx = next(
                        (i for i, p in enumerate(procs)
                         if _match_processes(p, old_stage)),
                        None
                    )

                    if to_idx is not None and from_idx is not None and to_idx <= from_idx:
                        rework_procs = procs[to_idx:from_idx + 1]

                        for order, rp_name in enumerate(rework_procs, start=1):
                            cursor.execute(
                                """
                                SELECT COALESCE(pdd.default_days, jpd.days, 0) AS rp_days
                                FROM job_card_process_days jpd
                                LEFT JOIN process_default_days pdd
                                  ON LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(pdd.process_name))
                                WHERE jpd.job_card_no = %s
                                  AND LOWER(TRIM(jpd.process_name)) = LOWER(TRIM(%s))
                                LIMIT 1
                                """,
                                (job_card_no, rp_name),
                            )
                            rp_row = cursor.fetchone()
                            rp_days = int(rp_row["rp_days"]
                                          or 0) if rp_row else 0
                            is_final = 1 if order == len(rework_procs) else 0

                            cursor.execute(
                                """
                                INSERT INTO revoke_process_days
                                (revoke_id, job_card_no, item_name, process_name,
                                 process_order, lead_days, in_time, is_final)
                                VALUES (%s, %s, %s, %s, %s, %s,
                                        CASE WHEN %s = 1 THEN NOW() ELSE NULL END,
                                        %s)
                                """,
                                (
                                    new_revoke_id,
                                    job_card_no,
                                    item_name.strip(),
                                    rp_name,
                                    order,
                                    rp_days,
                                    order,
                                    is_final,
                                ),
                            )

        conn.commit()

        return jsonify({
            "success": True,
            "message": f"WIP updated from '{old_stage}' to '{new_stage}'",
            "old_stage": old_stage,
            "new_stage": new_stage,
            "stage_days": stage_days,
            "process_found": process_found,
            "remaining_days": new_remaining,
            "total_days": total,
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


@quality_check_bp.route("/api/quality_check", methods=["POST"])
def save_quality_check():
    try:
        data = request.json
        job_card_no = data.get("job_card_no")
        details = data.get("details", [])

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

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
                r["checked_at"] = r["checked_at"].strftime("%Y-%m-%d %H:%M")
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
        data = request.json
        job_card_no = data.get("job_card_no")
        item_name = data.get("item_name")
        process = data.get("process")
        vendor_name = data.get("vendor_name", "").strip()
        changed_by = data.get("changed_by", "")

        if not all([job_card_no, item_name, process]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        actual_job_card_no = _resolve_job_card_no(cursor, job_card_no)
        if not actual_job_card_no:
            return jsonify({"success": False, "error": f"Job Card not found: {job_card_no}"}), 404
        job_card_no = actual_job_card_no

        for col, defn in [
            ("is_subcontract", "TINYINT(1) DEFAULT 0"),
            ("vendor_name",    "VARCHAR(255)"),
        ]:
            if not _has_column(cursor, "job_card_process_days", col):
                cursor.execute(
                    f"ALTER TABLE job_card_process_days ADD COLUMN {col} {defn}")

        cursor.execute("""
            SELECT remaining_days, wip_status FROM job_card_items
            WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
        """, (job_card_no, item_name.strip()))
        current_item = cursor.fetchone()
        if not current_item:
            return jsonify({
                "success": False,
                "error": f"Item not found in job card {job_card_no}"
            }), 404

        current_wip = current_item.get("wip_status") or "Pending"
        procs, process_source, pm_row = _fetch_process_sequence(
            cursor, job_card_no, item_name
        )
        validation_error, old_idx, sub_idx = _validate_next_stage(
            cursor, job_card_no, procs, current_wip, process
        )
        if validation_error:
            return jsonify({"success": False, "error": validation_error}), 400

        # ── Supervisor process-access check ────────────────────────────────────
        if session.get("role") == "supervisor":
            cursor.execute("""
                SELECT 1 FROM supervisor_process_access
                WHERE user_id = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                LIMIT 1
            """, (session.get("user_id"), current_wip))
            has_access = cursor.fetchone()
            if not has_access:
                return jsonify({
                    "success": False,
                    "error": f"You do not have permission to move items out of '{current_wip}'."
                }), 403

        cursor.execute("""
            UPDATE job_card_process_days
            SET is_completed = 1,
                end_date     = CURDATE(),
                out_time     = NOW(),
                actual_days  = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
            WHERE job_card_no = %s
              AND in_time IS NOT NULL
              AND out_time IS NULL
              AND LOWER(TRIM(process_name)) <> LOWER(TRIM(%s))
        """, (job_card_no, process))

        cursor.execute("""
            UPDATE job_card_process_days
            SET is_subcontract = 1,
                vendor_name    = %s,
                in_time        = COALESCE(in_time, NOW()),
                out_time       = NULL,
                is_completed   = 0,
                actual_days    = NULL
            WHERE job_card_no = %s
              AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
        """, (vendor_name, job_card_no, process))

        cursor.execute("""
            UPDATE job_card_items
            SET wip_status = %s, wip_stage_days = 0
            WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
        """, (process, job_card_no, item_name.strip()))

        cursor.execute("""
            INSERT INTO audit_trail
            (job_card_no, item_name, old_stage, new_stage, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (job_card_no, item_name, current_wip, f"{process} (Subcontract)", changed_by or "System"))

        conn.commit()
        return jsonify({"success": True, "message": f"{process} sent to subcontracting"})

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@quality_check_bp.route("/api/wip/subcontract_complete", methods=["POST"])
def complete_subcontract():
    try:
        data = request.json
        job_card_no = data.get("job_card_no")
        item_name = data.get("item_name")
        process = data.get("process")
        changed_by = data.get("changed_by", "")

        if not all([job_card_no, item_name, process]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # ── Supervisor process-access check ────────────────────────────────────
        if session.get("role") == "supervisor":
            cursor.execute("""
                SELECT 1 FROM supervisor_process_access
                WHERE user_id = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                LIMIT 1
            """, (session.get("user_id"), process))
            has_access = cursor.fetchone()
            if not has_access:
                cursor.close()
                conn.close()
                return jsonify({
                    "success": False,
                    "error": f"You do not have permission to complete subcontracting for '{process}'."
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
                is_subcontract = 0,
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
            cursor.execute("""
                UPDATE job_card_process_days
                SET is_completed = 1,
                    end_date     = CURDATE(),
                    out_time     = NOW(),
                    actual_days  = DATEDIFF(NOW(), COALESCE(in_time, NOW()))
                WHERE job_card_no = %s
                  AND in_time IS NOT NULL
                  AND out_time IS NULL
                  AND LOWER(TRIM(process_name)) <> LOWER(TRIM(%s))
            """, (job_card_no, next_stage))

            if _is_store_stage(next_stage):
                cursor.execute("""
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, NOW()),
                        out_time = COALESCE(out_time, NOW()),
                        is_completed = 1,
                        end_date = CURDATE(),
                        actual_days = COALESCE(actual_days, 0)
                    WHERE job_card_no = %s AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                """, (job_card_no, next_stage))
                cursor.execute(
                    "UPDATE job_cards SET final_status = 'Completed' WHERE job_card_no = %s",
                    (job_card_no,),
                )
            else:
                cursor.execute("""
                    UPDATE job_card_process_days
                    SET in_time = COALESCE(in_time, NOW()),
                        out_time = NULL,
                        is_completed = 0,
                        actual_days = NULL
                    WHERE job_card_no = %s AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                """, (job_card_no, next_stage))

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
        changed_by = data.get("changed_by", "System")

        if not job_card_no or not item_name or not current_stage or not target_stage:
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

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
