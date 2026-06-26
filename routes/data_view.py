"""
Data View API routes â€" Demo 2
All filtering, sorting, pagination and stats done in SQL.
JS only renders what the backend returns.
"""

from datetime import date, datetime, timedelta

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt

from flask import Blueprint, jsonify, request, session
from db import get_connection
from auth_utils import api_required
from permission_utils import (
    PAGE5_BASE_FIELDS,
    PAGE5_PPC,
    PROCESS_FIELDS,
    can_user_edit_field,
    ensure_permission_tables,
    has_process_access,
    seed_default_permissions,
)

data_view_bp = Blueprint("data_view", __name__)

PROCESS_COUNT = 25
PROCESS_COLUMNS = [f"p{i}" for i in range(1, PROCESS_COUNT + 1)]
PROCESS_COLUMNS_SQL = ", ".join(f"pm.{col}" for col in PROCESS_COLUMNS)


def safe_int(val, default=1):
    try:
        return max(1, int(val))
    except:
        return default


def col_exists(cursor, table, col):
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (table, col))
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row.get("COUNT(*)", 0)) > 0


def calculate_remaining_days_from_delivery(delivery_date):
    """Calculate remaining_days only from delivery date."""
    if not delivery_date:
        return 0
    try:
        if isinstance(delivery_date, str):
            delivery_dt = datetime.strptime(delivery_date[:10], "%Y-%m-%d").date()
        elif hasattr(delivery_date, "date") and not isinstance(delivery_date, date):
            delivery_dt = delivery_date.date()
        else:
            delivery_dt = delivery_date
        return (delivery_dt - date.today()).days
    except Exception:
        return 0


def ensure_extra_cols(cursor):
    for col, defn in [
        ("work_order_no",  "VARCHAR(50)"),
        ("work_order_date", "DATE"),
    ]:
        if not col_exists(cursor, "job_cards", col):
            cursor.execute(f"ALTER TABLE job_cards ADD COLUMN {col} {defn}")
    for col, defn in [
        ("is_subcontract", "TINYINT(1) DEFAULT 0"),
        ("vendor_name", "VARCHAR(255)"),
    ]:
        if not col_exists(cursor, "job_card_process_days", col):
            cursor.execute(
                f"ALTER TABLE job_card_process_days ADD COLUMN {col} {defn}")


SUPERVISOR_UPDATE_IDENTIFIERS = {
    "job_card_no",
    "item_id",
    "original_item_name",
    "process_name",
    "current_process",
}


def parse_optional_int(value, field_label):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_label} must be a number")


# â" € Job Cards tab â"                                                            €
@data_view_bp.route("/api/data/job_cards", methods=["GET"])
def data_job_cards():
    try:
        search = request.args.get("search", "").strip()
        wip = request.args.get("wip", "").strip()
        status = request.args.get("status", "").strip()
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        sort_col = request.args.get("sort", "jc.created_at")
        sort_dir = "ASC" if request.args.get(
            "order", "desc").lower() == "asc" else "DESC"
        page = safe_int(request.args.get("page", 1))
        per_page = safe_int(request.args.get("per_page", 50))
        offset = (page - 1) * per_page

        allowed_sorts = {
            "job_card_no": "jc.job_card_no", "so_no": "jc.so_no",
            "item_name": "ji.item_name", "material": "ji.material",
            "wip_status": "ji.wip_status", "total_days": "ji.total_days",
            "remaining_days": "DATEDIFF(ji.delivery_date, CURDATE())", "delivery_date": "ji.delivery_date",
            "final_status": "jc.final_status", "created_at": "jc.created_at",
            "vendor_name": "pd_current.vendor_name",
        }
        order_expr = allowed_sorts.get(sort_col, "jc.created_at")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_extra_cols(cursor)
        ensure_permission_tables(cursor)
        seed_default_permissions(cursor)
        conn.commit()

        params = []
        where = ["1=1"]

        if search:
            where.append("""(
                jc.job_card_no LIKE %s OR jc.so_no LIKE %s OR
                jc.customer_name LIKE %s OR
                jc.parent_code LIKE %s OR jc.child_code LIKE %s OR
                ji.item_name LIKE %s OR ji.material LIKE %s OR
                ji.wip_status LIKE %s
            )""")
            s = f"%{search}%"
            params += [s, s, s, s, s, s, s, s]

        if wip:
            where.append("ji.wip_status = %s")
            params.append(wip)
        if status:
            if status == "Completed":
                where.append(
                    "(jc.final_status = 'Completed' OR LOWER(TRIM(ji.wip_status)) = 'store')")
            else:
                where.append(
                    "jc.final_status = %s AND LOWER(TRIM(ji.wip_status)) != 'store'")
                params.append(status)
        if date_from:
            where.append("jc.so_date >= %s")
            params.append(date_from)
        if date_to:
            where.append("jc.so_date <= %s")
            params.append(date_to)

        filter_date = request.args.get("filter_date", "").strip()
        if filter_date:
            where.append("DATE(jc.created_at) = %s")
            params.append(filter_date)

        delivery_from = request.args.get("delivery_from", "").strip()
        delivery_to = request.args.get("delivery_to",   "").strip()
        overdue = request.args.get("overdue",        "").strip()
        subcontracting = request.args.get("subcontracting", "").strip()

        if delivery_from:
            where.append("ji.delivery_date >= %s")
            params.append(delivery_from)
        if delivery_to:
            where.append("ji.delivery_date <= %s")
            params.append(delivery_to)
        if overdue == "yes":
            if session.get("role") == "supervisor":
                where.append("""
                    EXISTS (
                        SELECT 1
                        FROM job_card_process_days pdx
                        LEFT JOIN process_default_days pddx
                            ON LOWER(TRIM(pddx.process_name)) = LOWER(TRIM(pdx.process_name))
                        JOIN supervisor_process_access spa
                            ON spa.user_id = %s
                        AND LOWER(TRIM(spa.process_name)) = LOWER(TRIM(pdx.process_name))
                        WHERE pdx.job_card_no = jc.job_card_no
                        AND pdx.in_time IS NOT NULL
                        AND pdx.out_time IS NULL
                        AND COALESCE(pdx.is_completed, 0) = 0
                        AND DATEDIFF(CURDATE(), pdx.in_time) > COALESCE(pddx.default_days, pdx.days, 0)
                    )
                """)
                params.append(session.get("user_id"))
            else:
                where.append("""
                    EXISTS (
                        SELECT 1
                        FROM job_card_process_days pdx
                        LEFT JOIN process_default_days pddx
                            ON LOWER(TRIM(pddx.process_name)) = LOWER(TRIM(pdx.process_name))
                        WHERE pdx.job_card_no = jc.job_card_no
                        AND pdx.in_time IS NOT NULL
                        AND pdx.out_time IS NULL
                        AND COALESCE(pdx.is_completed, 0) = 0
                        AND DATEDIFF(CURDATE(), pdx.in_time) > COALESCE(pddx.default_days, pdx.days, 0)
                    )
                """)

        elif overdue == "critical":
            if session.get("role") == "supervisor":
                where.append("""
                    EXISTS (
                        SELECT 1
                        FROM job_card_process_days pdx
                        LEFT JOIN process_default_days pddx
                            ON LOWER(TRIM(pddx.process_name)) = LOWER(TRIM(pdx.process_name))
                        JOIN supervisor_process_access spa
                            ON spa.user_id = %s
                        AND LOWER(TRIM(spa.process_name)) = LOWER(TRIM(pdx.process_name))
                        WHERE pdx.job_card_no = jc.job_card_no
                        AND pdx.in_time IS NOT NULL
                        AND pdx.out_time IS NULL
                        AND COALESCE(pdx.is_completed, 0) = 0
                        AND DATEDIFF(CURDATE(), pdx.in_time) - COALESCE(pddx.default_days, pdx.days, 0) > 7
                    )
                """)
                params.append(session.get("user_id"))
            else:
                where.append("""
                    EXISTS (
                        SELECT 1
                        FROM job_card_process_days pdx
                        LEFT JOIN process_default_days pddx
                            ON LOWER(TRIM(pddx.process_name)) = LOWER(TRIM(pdx.process_name))
                        WHERE pdx.job_card_no = jc.job_card_no
                        AND pdx.in_time IS NOT NULL
                        AND pdx.out_time IS NULL
                        AND COALESCE(pdx.is_completed, 0) = 0
                        AND DATEDIFF(CURDATE(), pdx.in_time) - COALESCE(pddx.default_days, pdx.days, 0) > 7
                    )
                """)
        if subcontracting == "yes":
            where.append("COALESCE(pd_current.is_subcontract, 0) = 1")
        elif subcontracting == "no":
            where.append("COALESCE(pd_current.is_subcontract, 0) = 0")

        urgent_only = request.args.get("urgent_only", "").strip()
        if urgent_only == "yes":
            where.append("ji.is_priority = 1")

        where_sql = " AND ".join(where)

        # Total count for pagination
        cursor.execute(f"""
            SELECT COUNT(*) as total
            FROM job_cards jc
            JOIN job_card_items ji ON jc.job_card_no = ji.job_card_no
            LEFT JOIN job_card_process_days pd_current
                ON pd_current.job_card_no = ji.job_card_no
               AND LOWER(TRIM(pd_current.process_name)) = LOWER(TRIM(ji.wip_status))
            WHERE {where_sql}
        """, params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT DISTINCT wip_status FROM job_card_items WHERE wip_status IS NOT NULL ORDER BY wip_status")
        wip_options = [r["wip_status"] for r in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT final_status FROM job_cards WHERE final_status IS NOT NULL ORDER BY final_status")
        status_options = [r["final_status"] for r in cursor.fetchall()]

        # Main query — no process_master join (removed: was the source of a
        # 4-second-per-request correlated subquery scanning process_master
        # once per row). next_process is no longer calculated here; it was
        # a minor convenience field not essential to this table view.
        cursor.execute(f"""
            SELECT ji.id AS item_id,
                   jc.job_card_no, jc.so_no, jc.customer_name, jc.work_order_no, ji.is_priority,
                   jc.parent_code, jc.child_code,
                   jc.so_date, jc.job_card_date,
                   CASE WHEN jc.final_status = 'Completed'
                             OR LOWER(TRIM(ji.wip_status)) = 'store'
                        THEN 'Completed' ELSE jc.final_status
                   END AS final_status,
                   jc.erp_status,
                   ji.item_name, ji.material, ji.so_qty, ji.actual_qty,
                   ji.wip_status, ji.total_days,
                   DATEDIFF(ji.delivery_date, CURDATE()) AS remaining_days,
                   COALESCE(pd_current.is_subcontract, 0) AS is_subcontract,
                   COALESCE(pd_current.vendor_name, '') AS vendor_name,
                   COALESCE(
                       (SELECT DATEDIFF(CURDATE(), pd3.in_time)
                        FROM job_card_process_days pd3
                        WHERE pd3.job_card_no = ji.job_card_no
                          AND LOWER(TRIM(pd3.process_name)) = LOWER(TRIM(ji.wip_status))
                          AND pd3.in_time IS NOT NULL
                          AND pd3.out_time IS NULL
                        LIMIT 1),
                       ji.wip_stage_days, 0
                   ) AS wip_stage_days,
                   ji.delivery_date, ji.remarks, jc.created_at,
                   CASE
                     WHEN ji.delivery_date IS NOT NULL AND ji.delivery_date < CURDATE()
                          AND jc.final_status != 'Completed'
                     THEN DATEDIFF(CURDATE(), ji.delivery_date)
                     ELSE 0
                   END AS days_overdue,
                   (SELECT CONCAT(
                               COALESCE(at.changed_by, '?'), ' • ',
                               DATE_FORMAT(CONVERT_TZ(at.changed_at, '+00:00', '+05:30'), '%d %b %Y %H:%i'), ' • ',
                               COALESCE(at.old_stage, '?'), ' → ', COALESCE(at.new_stage, '?')
                           )
                    FROM audit_trail at
                    WHERE at.job_card_no = ji.job_card_no
                      AND at.item_name   = ji.item_name
                    ORDER BY at.changed_at DESC
                    LIMIT 1
                   ) AS last_audit
            FROM job_cards jc
            JOIN job_card_items ji ON jc.job_card_no = ji.job_card_no
            LEFT JOIN job_card_process_days pd_current
                ON pd_current.job_card_no = ji.job_card_no
               AND LOWER(TRIM(pd_current.process_name)) = LOWER(TRIM(ji.wip_status))
            WHERE {where_sql}
            ORDER BY ji.is_priority DESC,{order_expr} {sort_dir}
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cursor.fetchall()
        for r in rows:
            for f in ("so_date", "job_card_date", "delivery_date"):
                if r.get(f) and hasattr(r[f], "strftime"):
                    r[f] = r[f].strftime("%Y-%m-%d")
            if r.get("created_at"):
                r["created_at"] = _to_ist(r["created_at"]).strftime("%Y-%m-%d %H:%M")

        for r in rows:
            r["remaining_days"] = calculate_remaining_days_from_delivery(
                r.get("delivery_date"))
            r["total_default_days_calc"] = 0
            r["used_process_days_calc"] = 0
            r["can_edit_current_process"] = session.get("role") == "admin"
            r["page5_editable_fields"] = []

        role = (session.get("role") or "").strip().lower()
        user_id = session.get("user_id")
        if role == "admin":
            admin_fields = sorted(PAGE5_BASE_FIELDS | PROCESS_FIELDS)
            for r in rows:
                r["page5_editable_fields"] = admin_fields
        elif role == "supervisor" and rows:
            cursor.execute("""
                SELECT process_name
                FROM supervisor_process_access
                WHERE user_id = %s
            """, (user_id,))
            accessible_processes = {
                (r.get("process_name") or "").strip().lower()
                for r in cursor.fetchall()
            }
            base_fields = [
                field for field in sorted(PAGE5_BASE_FIELDS)
                if can_user_edit_field(cursor, role, user_id, PAGE5_PPC, field)
            ]
            process_fields = [
                field for field in sorted(PROCESS_FIELDS)
                if can_user_edit_field(cursor, role, user_id, PAGE5_PPC, field)
            ]
            for r in rows:
                current_process = (r.get("wip_status") or "").strip().lower()
                r["can_edit_current_process"] = current_process in accessible_processes
                r["page5_editable_fields"] = list(base_fields)
                if r["can_edit_current_process"]:
                    r["page5_editable_fields"].extend(process_fields)

        cursor.close()
        conn.close()
        return jsonify({
            "success": True, "data": rows,
            "total": total, "page": page, "per_page": per_page,
            "wip_options": wip_options, "status_options": status_options,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ── Toggle item priority ──────────────────────────────────────────────────────


@data_view_bp.route("/api/job_card_item/priority", methods=["POST"])
def update_item_priority():
    try:
        data = request.json
        item_id = data.get("item_id")
        job_card_no = data.get("job_card_no")
        item_name = data.get("item_name")
        is_priority = 1 if data.get("is_priority") else 0

        if not item_id and (not job_card_no or not item_name):
            return jsonify({"success": False, "error": "item_id or job_card_no and item_name are required"}), 400

        conn = get_connection()
        cursor = conn.cursor()
        if not col_exists(cursor, "job_card_items", "is_priority"):
            cursor.execute(
                "ALTER TABLE job_card_items ADD COLUMN is_priority TINYINT(1) DEFAULT 0")
        if item_id:
            cursor.execute("""
                UPDATE job_card_items
                SET is_priority = %s
                WHERE id = %s
            """, (is_priority, item_id))
        else:
            cursor.execute("""
                UPDATE job_card_items
                SET is_priority = %s
                WHERE job_card_no = %s AND LOWER(TRIM(item_name)) = LOWER(TRIM(%s))
            """, (is_priority, job_card_no, item_name.strip()))
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "No matching job card item found for priority update"}), 404
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": "Priority updated", "is_priority": is_priority})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# â" € Quality Checks tab â"                                                       €
@data_view_bp.route("/api/data/quality_checks", methods=["GET"])
def data_quality_checks():
    try:
        search = request.args.get("search", "").strip()
        result = request.args.get("result", "").strip()
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        sort_col = request.args.get("sort", "qc.checked_at")
        sort_dir = "ASC" if request.args.get(
            "order", "desc").lower() == "asc" else "DESC"
        page = safe_int(request.args.get("page", 1))
        per_page = safe_int(request.args.get("per_page", 50))
        offset = (page-1)*per_page

        allowed_sorts = {
            "job_card_no": "qc.job_card_no", "item_name": "qcd.item_name",
            "quality_result": "qcd.quality_result", "supervisor": "qcd.supervisor",
            "checked_at": "qc.checked_at",
        }
        order_expr = allowed_sorts.get(sort_col, "qc.checked_at")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        params = []
        where = ["1=1"]

        if search:
            where.append(
                "(qc.job_card_no LIKE %s OR qcd.item_name LIKE %s OR qcd.supervisor LIKE %s)")
            s = f"%{search}%"
            params += [s, s, s]
        if result:
            where.append("qcd.quality_result = %s")
            params.append(result)
        if date_from:
            where.append("DATE(qc.checked_at) >= %s")
            params.append(date_from)
        if date_to:
            where.append("DATE(qc.checked_at) <= %s")
            params.append(date_to)

        urgent_only = request.args.get("urgent_only", "").strip()
        if urgent_only == "yes":
            where.append("""EXISTS (
                SELECT 1 FROM job_card_items ji
                WHERE ji.job_card_no = qc.job_card_no
                AND ji.is_priority = 1
            )""")

        where_sql = " AND ".join(where)

        cursor.execute(f"""
            SELECT COUNT(*) as total
            FROM quality_check_details qcd
            JOIN quality_checks qc ON qcd.quality_check_id = qc.id
            WHERE {where_sql}
        """, params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT qc.job_card_no, qc.checked_at,
                   qcd.item_name, qcd.actual_qty,
                   qcd.process_name as completed_process,
                   qcd.quality_result, qcd.supervisor
            FROM quality_check_details qcd
            JOIN quality_checks qc ON qcd.quality_check_id = qc.id
            WHERE {where_sql}
            ORDER BY {order_expr} {sort_dir}
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cursor.fetchall()
        for r in rows:
            if r.get("checked_at"):
                r["checked_at"] = _to_ist(r["checked_at"]).strftime("%Y-%m-%d %H:%M")

        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows, "total": total, "page": page, "per_page": per_page})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# â" € Audit Trail tab â"
@data_view_bp.route("/api/audit_trail", methods=["GET"])
def get_audit_trail():
    try:
        search = request.args.get("search", "").strip()
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        page = safe_int(request.args.get("page", 1))
        per_page = safe_int(request.args.get("per_page", 50))
        offset = (page-1)*per_page

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        params = []
        where = ["1=1"]

        if search:
            where.append(
                "(job_card_no LIKE %s OR item_name LIKE %s OR changed_by LIKE %s OR old_stage LIKE %s OR new_stage LIKE %s)")
            s = f"%{search}%"
            params += [s, s, s, s, s]
        if date_from:
            where.append("DATE(changed_at) >= %s")
            params.append(date_from)
        if date_to:
            where.append("DATE(changed_at) <= %s")
            params.append(date_to)

        where_sql = " AND ".join(where)

        cursor.execute(
            f"SELECT COUNT(*) as total FROM audit_trail WHERE {where_sql}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT job_card_no, item_name, old_stage, new_stage, changed_by, changed_at
            FROM audit_trail WHERE {where_sql}
            ORDER BY changed_at DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cursor.fetchall()
        for r in rows:
            if r.get("changed_at"):
                r["changed_at"] = _to_ist(r["changed_at"]).strftime("%Y-%m-%d %H:%M")

        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows, "total": total, "page": page, "per_page": per_page})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_view_bp.route("/api/audit_trail/<path:job_card_no>", methods=["GET"])
def get_audit_trail_by_jc(job_card_no):
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT job_card_no, item_name, old_stage, new_stage, changed_by, changed_at
            FROM audit_trail WHERE job_card_no=%s ORDER BY changed_at DESC
        """, (job_card_no,))
        rows = cursor.fetchall()
        for r in rows:
            if r.get("changed_at"):
                r["changed_at"] = _to_ist(r["changed_at"]).strftime("%Y-%m-%d %H:%M")
        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_view_bp.route("/api/data/process_report", methods=["GET"])
def data_process_report():
    try:
        from collections import OrderedDict

        search = request.args.get("search", "").strip()
        page = safe_int(request.args.get("page", 1))

        per_page = safe_int(request.args.get("per_page", 30))
        offset = (page - 1) * per_page

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_extra_cols(cursor)

        params = []
        where = ["1=1"]

        if search:
            where.append("""
                (
                    jc.job_card_no LIKE %s
                    OR jc.so_no LIKE %s
                    OR jc.customer_name LIKE %s
                    OR ji.item_name LIKE %s
                    OR ji.material LIKE %s
                    OR ji.wip_status LIKE %s
                    OR pd.process_name LIKE %s
                )
            """)
            s = f"%{search}%"
            params += [s, s, s, s, s, s, s]

        wip_pr = request.args.get("wip",           "").strip()
        proc_status = request.args.get("proc_status",   "").strip()
        delivery_from = request.args.get("delivery_from", "").strip()
        delivery_to = request.args.get("delivery_to",   "").strip()
        overdue = request.args.get("overdue",        "").strip()
        filter_date = request.args.get("filter_date", "").strip()
        if filter_date:
            where.append("DATE(jc.created_at) = %s")
            params.append(filter_date)

        if wip_pr:
            where.append("ji.wip_status = %s")
            params.append(wip_pr)
        if delivery_from:
            where.append("ji.delivery_date >= %s")
            params.append(delivery_from)
        if delivery_to:
            where.append("ji.delivery_date <= %s")
            params.append(delivery_to)
        if overdue == "yes":
            where.append("ji.delivery_date < CURDATE()")
        elif overdue == "critical":
            where.append("DATEDIFF(CURDATE(), ji.delivery_date) > 7")

        urgent_only_pr = request.args.get("urgent_only", "").strip()
        if urgent_only_pr == "yes":
            where.append("ji.is_priority = 1")

        # FIX (Problem 2): When both wip and proc_status are selected together,
        # proc_status must describe the status of THAT SPECIFIC wip process,
        # not "any process on this job card". When proc_status is used alone
        # (no wip filter), it still means "any process has this status",
        # which is the original/expected meaning for that case.
        if proc_status:
            # Subcontracting is "In Progress" + a vendor assigned, not a
            # separate is_completed/in_time state — needs its own condition.
            status_case = """CASE
                        WHEN jpd2.is_completed = 1 THEN 'Completed'
                        WHEN jpd2.in_time IS NOT NULL AND jpd2.out_time IS NULL
                             AND COALESCE(jpd2.vendor_name, '') != '' THEN 'Subcontracting'
                        WHEN jpd2.in_time IS NOT NULL AND jpd2.out_time IS NULL THEN 'In Progress'
                        ELSE 'Pending'
                    END"""
            if wip_pr:
                where.append(f"""EXISTS (
                    SELECT 1 FROM job_card_process_days jpd2
                    WHERE jpd2.job_card_no = ji.job_card_no
                    AND LOWER(TRIM(jpd2.process_name)) = LOWER(TRIM(%s))
                    AND {status_case} = %s
                )""")
                params.append(wip_pr)
                params.append(proc_status)
            else:
                where.append(f"""EXISTS (
                    SELECT 1 FROM job_card_process_days jpd2
                    WHERE jpd2.job_card_no = ji.job_card_no
                    AND {status_case} = %s
                )""")
                params.append(proc_status)

        where_sql = " AND ".join(where)
        cursor.execute(f"""
            SELECT COUNT(DISTINCT jc.job_card_no) AS total
            FROM job_cards jc
            JOIN job_card_items ji
                ON jc.job_card_no = ji.job_card_no
            JOIN job_card_process_days pd
                ON jc.job_card_no = pd.job_card_no
            WHERE {where_sql}
        """, params)

        total = cursor.fetchone()["total"]

        # FIX (Problem 1): wip_options must only list WIP statuses that
        # actually have matching rows in job_card_process_days — i.e. the
        # same JOIN the report itself requires. Otherwise the dropdown can
        # offer a WIP status that always returns "No records found".
        cursor.execute("""
            SELECT DISTINCT ji.wip_status
            FROM job_card_items ji
            JOIN job_card_process_days pd
                ON ji.job_card_no = pd.job_card_no
            WHERE ji.wip_status IS NOT NULL AND ji.wip_status != ''
            ORDER BY ji.wip_status
        """)
        wip_options = [r["wip_status"] for r in cursor.fetchall()]

        cursor.execute(f"""
            SELECT DISTINCT jc.job_card_no
            FROM job_cards jc
            JOIN job_card_items ji
                ON jc.job_card_no = ji.job_card_no
            JOIN job_card_process_days pd
                ON jc.job_card_no = pd.job_card_no
            WHERE {where_sql}
            ORDER BY jc.job_card_no
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        page_job_cards = [r["job_card_no"] for r in cursor.fetchall()]

        if not page_job_cards:
            cursor.close()
            conn.close()
            return jsonify({
                "success": True,
                "process_columns": [],
                "data": [],
                "total": total,
                "page": page,
                "per_page": per_page,
                "wip_options": wip_options
            })
        placeholders = ",".join(["%s"] * len(page_job_cards))
        where_sql = f"{where_sql} AND jc.job_card_no IN ({placeholders})"
        params = params + page_job_cards

        cursor.execute(f"""
            SELECT
                jc.job_card_no,
                jc.so_no,
                jc.so_date,
                jc.job_card_date,
                jc.final_status,
                jc.erp_status,

                ji.item_name,
                ji.material,
                ji.so_qty,
                ji.actual_qty,
                ji.wip_status,
                ji.total_days,
                DATEDIFF(ji.delivery_date, CURDATE()) AS remaining_days,
                ji.delivery_date,
                ji.remarks,
                ji.is_priority,

                pd.id AS process_id,
                pd.process_name,
                COALESCE(pdd.default_days, pd.days, 0) AS lead_days,
                pd.in_time,
                pd.out_time,
                pd.actual_days,
                pd.is_completed,
                COALESCE(pd.vendor_name, '') AS vendor_name,
                COALESCE(pd.is_subcontract, 0) AS is_subcontract,

                CASE
                    WHEN pd.in_time IS NULL THEN 0

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NULL
                    THEN DATEDIFF(CURDATE(), DATE(pd.in_time))

                    WHEN pd.actual_days IS NOT NULL
                    THEN pd.actual_days

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NOT NULL
                    THEN DATEDIFF(DATE(pd.out_time), DATE(pd.in_time))

                    ELSE 0
                END AS days_taken,

                CASE
                    WHEN pd.in_time IS NULL THEN '0d'

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NULL
                    THEN CONCAT(DATEDIFF(CURDATE(), DATE(pd.in_time)))

                    WHEN pd.actual_days IS NOT NULL
                    THEN CONCAT(pd.actual_days, 'd')

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NOT NULL
                    THEN CONCAT(DATEDIFF(DATE(pd.out_time), DATE(pd.in_time)), 'd')

                    ELSE '0d'
                END AS days_taken_display,

                CASE
                    WHEN pd.is_completed = 1 THEN 'Completed'

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NULL
                    THEN 'In Progress'

                    WHEN pd.in_time IS NULL THEN 'Pending'

                    ELSE 'Pending'
                END AS process_status

            FROM job_cards jc
            JOIN job_card_items ji
                ON jc.job_card_no = ji.job_card_no
            JOIN job_card_process_days pd
                ON jc.job_card_no = pd.job_card_no
            LEFT JOIN process_default_days pdd
                ON LOWER(TRIM(pd.process_name)) = LOWER(TRIM(pdd.process_name))
            WHERE {where_sql}
            ORDER BY jc.job_card_no, pd.id
        """, params)

        rows = cursor.fetchall()

        # Date formatting
        for r in rows:
            for f in (
                "so_date",
                "job_card_date",
                "delivery_date",
                "in_time",
                "out_time",
            ):
                if r.get(f) and hasattr(r[f], "strftime"):
                    r[f] = r[f].strftime("%Y-%m-%d")

        # Get process column order from DB default table.
        # This keeps report columns consistent everywhere.
        cursor.execute("""
            SELECT process_name
            FROM process_default_days
            ORDER BY id
        """)
        default_process_cols = [
            r["process_name"] for r in cursor.fetchall()
            if r.get("process_name")
        ]

        grouped = OrderedDict()
        all_process_cols = list(default_process_cols)

        for r in rows:
            jcn = r["job_card_no"]
            proc = (r.get("process_name") or "").strip()

            if proc and proc not in all_process_cols:
                all_process_cols.append(proc)

            if jcn not in grouped:
                base = {
                    "job_card_no": r.get("job_card_no"),
                    "so_no": r.get("so_no") or "",
                    "so_date": r.get("so_date") or "",
                    "job_card_date": r.get("job_card_date") or "",
                    "item_name": r.get("item_name") or "",
                    "material": r.get("material") or "",
                    "so_qty": r.get("so_qty") or 0,
                    "actual_qty": r.get("actual_qty") or 0,
                    "wip_status": r.get("wip_status") or "",
                    "total_days": r.get("total_days") or 0,
                    "remaining_days": r.get("remaining_days") or 0,
                    "delivery_date": r.get("delivery_date") or "",
                    "final_status": r.get("final_status") or "",
                    "erp_status": r.get("erp_status") or "",
                    "remarks": r.get("remarks") or "",
                    "is_priority": r.get("is_priority") or 0,
                    "process_order": [],
                    "process_status_map": {},
                    "process_vendor_map": {},
                    "process_lead_days_map": {},
                }

                # Initialize all known process columns as 0d
                for p in all_process_cols:
                    base[p] = "0d"

                grouped[jcn] = base

            # If new process column discovered after row initialized,
            # add it to all previous rows too.
            for existing in grouped.values():
                if proc and proc not in existing:
                    existing[proc] = "0d"

            if proc:
                if proc not in grouped[jcn]["process_order"]:
                    grouped[jcn]["process_order"].append(proc)
                grouped[jcn][proc] = r.get("days_taken_display") or "0d"
                grouped[jcn]["process_status_map"][proc] = r.get(
                    "process_status") or "Pending"
                grouped[jcn]["process_vendor_map"][proc] = r.get(
                    "vendor_name") or ""
                grouped[jcn]["process_lead_days_map"][proc] = int(
                    r.get("lead_days") or 0)

        for job_data in grouped.values():
            job_data["remaining_days"] = calculate_remaining_days_from_delivery(
                job_data.get("delivery_date"))
            job_data["total_default_days_calc"] = 0
            job_data["used_process_days_calc"] = 0
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "process_columns": all_process_cols,
            "data": list(grouped.values()),
            "total": total,
            "page": page,
            "per_page": per_page,
            "wip_options": wip_options
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_view_bp.route("/api/data/planning_sheet", methods=["GET"])
def data_planning_sheet():
    try:
        from collections import OrderedDict

        search = request.args.get("search", "").strip()
        wip = request.args.get("wip", "").strip()

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        params = []
        where = ["1=1"]

        if search:
            where.append("""
                (
                    jc.job_card_no LIKE %s
                    OR jc.so_no LIKE %s
                    OR jc.customer_name LIKE %s
                    OR ji.item_name LIKE %s
                    OR ji.material LIKE %s
                    OR ji.wip_status LIKE %s
                    OR pd.process_name LIKE %s
                )
            """)
            s = f"%{search}%"
            params += [s, s, s, s, s, s, s]

        if wip:
            where.append("ji.wip_status = %s")
            params.append(wip)

        delivery_from = request.args.get("delivery_from", "").strip()
        delivery_to = request.args.get("delivery_to",   "").strip()
        overdue = request.args.get("overdue",        "").strip()
        filter_date = request.args.get("filter_date", "").strip()
        if filter_date:
            where.append("DATE(jc.created_at) = %s")
            params.append(filter_date)

        if delivery_from:
            where.append("ji.delivery_date >= %s")
            params.append(delivery_from)
        if delivery_to:
            where.append("ji.delivery_date <= %s")
            params.append(delivery_to)
        if overdue == "yes":
            where.append("ji.delivery_date < CURDATE()")
        elif overdue == "critical":
            where.append("DATEDIFF(CURDATE(), ji.delivery_date) > 7")

        urgent_only_ps = request.args.get("urgent_only", "").strip()
        if urgent_only_ps == "yes":
            where.append("ji.is_priority = 1")

        where_sql = " AND ".join(where)

        # Process column order from database default table.
        # This avoids JS/hardcoded process-day columns.
        cursor.execute("""
            SELECT process_name
            FROM process_default_days
            ORDER BY id
        """)
        default_process_cols = [
            r["process_name"] for r in cursor.fetchall()
            if r.get("process_name")
        ]

        cursor.execute(f"""
            SELECT
                jc.job_card_no,
                jc.so_no,
                jc.so_date,
                jc.job_card_date,
                jc.final_status,
                jc.erp_status,

                ji.item_name,
                ji.material,
                ji.so_qty,
                ji.actual_qty,
                ji.wip_status,
                ji.wip_stage_days,
                ji.total_days,
                DATEDIFF(ji.delivery_date, CURDATE()) AS remaining_days,
                ji.delivery_date,
                ji.remarks,
                ji.is_priority,

                pd.id AS process_id,
                pd.process_name,
                COALESCE(pdd.default_days, pd.days, 0) AS lead_days,
                pd.in_time,
                pd.out_time,
                pd.actual_days,
                pd.is_completed,
                COALESCE(pd.is_subcontract, 0) AS is_subcontract,
                COALESCE(pd.vendor_name, '') AS vendor_name,

                CASE
                    WHEN pd.in_time IS NULL THEN 0

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NULL
                    THEN DATEDIFF(CURDATE(), DATE(pd.in_time))

                    WHEN pd.actual_days IS NOT NULL
                    THEN pd.actual_days

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NOT NULL
                    THEN DATEDIFF(DATE(pd.out_time), DATE(pd.in_time))

                    ELSE 0
                END AS days_taken,

                CASE
                    WHEN pd.in_time IS NULL THEN 'Pending'

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NULL
                    THEN 'In Progress'

                    WHEN pd.is_completed = 1 THEN 'Completed'

                    ELSE 'Pending'
                END AS process_status,

                CASE
                    WHEN ji.delivery_date IS NOT NULL
                    THEN DATEDIFF(ji.delivery_date, CURDATE())
                    ELSE NULL
                END AS pend_days

            FROM job_cards jc
            JOIN job_card_items ji
                ON jc.job_card_no = ji.job_card_no
            LEFT JOIN job_card_process_days pd
                ON pd.job_card_no = jc.job_card_no
            LEFT JOIN process_default_days pdd
                ON LOWER(TRIM(pd.process_name)) = LOWER(TRIM(pdd.process_name))
            WHERE {where_sql}
            ORDER BY ji.is_priority DESC, jc.job_card_no, pd.id
        """, params)

        rows = cursor.fetchall()

        all_process_cols = list(default_process_cols)
        grouped = OrderedDict()

        for r in rows:
            jcn = r["job_card_no"]
            proc = (r.get("process_name") or "").strip()

            if proc and proc not in all_process_cols:
                all_process_cols.append(proc)

            if jcn not in grouped:
                delivery = r.get("delivery_date")
                delivery_str = (
                    delivery.strftime("%Y-%m-%d")
                    if hasattr(delivery, "strftime")
                    else (delivery or "")
                )

                so_date = r.get("so_date")
                so_date_str = (
                    so_date.strftime("%Y-%m-%d")
                    if hasattr(so_date, "strftime")
                    else (so_date or "")
                )

                jc_date = r.get("job_card_date")
                jc_date_str = (
                    jc_date.strftime("%Y-%m-%d")
                    if hasattr(jc_date, "strftime")
                    else (jc_date or "")
                )

                base = {
                    "job_card_no": r.get("job_card_no") or "",
                    "so_no": r.get("so_no") or "",
                    "so_date": so_date_str,
                    "job_card_date": jc_date_str,
                    "item_name": r.get("item_name") or "",
                    "material": r.get("material") or "",
                    "so_qty": r.get("so_qty") or 0,
                    "actual_qty": r.get("actual_qty") or 0,
                    "wip_status": r.get("wip_status") or "",
                    "live_stage_days": 0,
                    "next_process": "",
                    "remarks": r.get("remarks") or "",
                    "total_days": r.get("total_days") or 0,
                    "remaining_days": r.get("remaining_days") or 0,
                    "pend_days": r.get("pend_days"),
                    "delivery_date": delivery_str,
                    "final_status": r.get("final_status") or "",
                    "erp_status": r.get("erp_status") or "",
                    "is_priority": r.get("is_priority") or 0,
                    "process_status_map": {},
                    "process_lead_days_map": {},
                    "process_vendor_map": {},
                }

                # Initialize all process columns as numeric 0.
                for p in all_process_cols:
                    base[p] = 0

                grouped[jcn] = base

            # If a new process column is discovered later, add it to previous rows.
            for existing in grouped.values():
                if proc and proc not in existing:
                    existing[proc] = 0

            if proc:
                days_taken = int(r.get("days_taken") or 0)
                grouped[jcn][proc] = days_taken
                grouped[jcn]["process_status_map"][proc] = r.get(
                    "process_status") or "Pending"
                grouped[jcn]["process_lead_days_map"][proc] = int(
                    r.get("lead_days") or 0)
                grouped[jcn]["process_vendor_map"][proc] = r.get(
                    "vendor_name") or ""

                current_wip = (grouped[jcn].get(
                    "wip_status") or "").strip().lower()
                if proc.strip().lower() == current_wip:
                    grouped[jcn]["live_stage_days"] = days_taken

        for job_data in grouped.values():
            job_data["remaining_days"] = calculate_remaining_days_from_delivery(
                job_data.get("delivery_date"))
            job_data["total_default_days_calc"] = 0
            job_data["used_process_days_calc"] = 0

        # Calculate next_process from each job card's actual saved process order.
        actual_order_map = {}

        for r in rows:
            jcn = r["job_card_no"]
            proc = (r.get("process_name") or "").strip()
            if not proc:
                continue
            actual_order_map.setdefault(jcn, [])
            if proc not in actual_order_map[jcn]:
                actual_order_map[jcn].append(proc)

        for jcn, row in grouped.items():
            actual_processes = actual_order_map.get(jcn, [])
            current = (row.get("wip_status") or "").strip().lower()
            next_process = ""

            for idx, proc in enumerate(actual_processes):
                if proc.strip().lower() == current and idx + 1 < len(actual_processes):
                    next_process = actual_processes[idx + 1]
                    break

            row["next_process"] = next_process

        cursor.execute("""
            SELECT DISTINCT wip_status
            FROM job_card_items
            WHERE wip_status IS NOT NULL
            ORDER BY wip_status
        """)
        wip_options = [r["wip_status"] for r in cursor.fetchall()]

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "process_columns": all_process_cols,
            "data": list(grouped.values()),
            "wip_options": wip_options
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_view_bp.route("/api/operator/lead-time-notifications", methods=["GET"])
@api_required("operator_dashboard", allowed_modes=("full",))
def operator_lead_time_notifications():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                jc.job_card_no,
                jc.so_no,
                ji.item_name,
                ji.item_name AS model,
                ji.material,
                ji.wip_status AS process_name,
                COALESCE(pdd.default_days, pd.days, 0) AS lead_days,
                DATEDIFF(CURDATE(), pd.in_time) AS actual_days,
                pd.in_time,
                pd.lead_date,
                'Overdue' AS status
            FROM job_cards jc
            JOIN job_card_items ji
                ON jc.job_card_no = ji.job_card_no
            JOIN job_card_process_days pd
                ON pd.job_card_no = jc.job_card_no
               AND LOWER(TRIM(pd.process_name)) = LOWER(TRIM(ji.wip_status))
            LEFT JOIN process_default_days pdd
                ON LOWER(TRIM(pd.process_name)) = LOWER(TRIM(pdd.process_name))
            WHERE pd.in_time IS NOT NULL
              AND pd.out_time IS NULL
              AND COALESCE(pdd.default_days, pd.days, 0) > 0
              AND DATEDIFF(CURDATE(), pd.in_time) > COALESCE(pdd.default_days, pd.days, 0)
              AND IFNULL(jc.final_status, '') != 'Completed'
            ORDER BY actual_days DESC
            LIMIT 100
        """)

        rows = cursor.fetchall()

        for r in rows:
            if r.get("in_time") and hasattr(r["in_time"], "strftime"):
                r["in_time"] = r["in_time"].strftime("%Y-%m-%d")

            if r.get("lead_date") and hasattr(r["lead_date"], "strftime"):
                r["lead_date"] = r["lead_date"].strftime("%Y-%m-%d")

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "data": rows
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



# Same table/column names + filter logic as
# /api/operator/lead-time-notifications so every dashboard stays consistent.
_OVERDUE_PROCESS_QUERY = """
    SELECT
        jc.job_card_no,
        jc.so_no,
        ji.item_name,
        ji.item_name AS model,
        ji.material,
        ji.wip_status AS process_name,
        COALESCE(pdd.default_days, pd.days, 0) AS lead_days,
        DATEDIFF(CURDATE(), pd.in_time) AS actual_days,
        pd.in_time,
        pd.lead_date,
        'Overdue' AS status
    FROM job_cards jc
    JOIN job_card_items ji
        ON jc.job_card_no = ji.job_card_no
    JOIN job_card_process_days pd
        ON pd.job_card_no = jc.job_card_no
       AND LOWER(TRIM(pd.process_name)) = LOWER(TRIM(ji.wip_status))
    LEFT JOIN process_default_days pdd
        ON LOWER(TRIM(pd.process_name)) = LOWER(TRIM(pdd.process_name))
    WHERE pd.in_time IS NOT NULL
      AND pd.out_time IS NULL
      AND COALESCE(pdd.default_days, pd.days, 0) > 0
      AND DATEDIFF(CURDATE(), pd.in_time) > COALESCE(pdd.default_days, pd.days, 0)
      AND IFNULL(jc.final_status, '') != 'Completed'
    ORDER BY actual_days DESC
    LIMIT 100
"""


def _fetch_overdue_processes(cursor):
    role = (session.get("role") or "").strip().lower()
    user_id = session.get("user_id")

    access_join = ""
    params = []

    if role == "supervisor":
        access_join = """
            JOIN supervisor_process_access spa
              ON spa.user_id = %s
             AND LOWER(TRIM(spa.process_name)) = LOWER(TRIM(pd.process_name))
        """
        params.append(user_id)

    query = f"""
        SELECT
            pd.job_card_no,
            ji.item_name AS model,
            pd.process_name,
            COALESCE(pdd.default_days, pd.days, 0) AS lead_days,
            DATEDIFF(CURDATE(), pd.in_time) AS actual_days,
            DATEDIFF(CURDATE(), pd.in_time) - COALESCE(pdd.default_days, pd.days, 0) AS days_overdue,
            'Overdue' AS status
        FROM job_card_process_days pd
        JOIN job_card_items ji
            ON ji.job_card_no = pd.job_card_no
        LEFT JOIN process_default_days pdd
            ON LOWER(TRIM(pdd.process_name)) = LOWER(TRIM(pd.process_name))
        {access_join}
        WHERE pd.in_time IS NOT NULL
          AND pd.out_time IS NULL
          AND COALESCE(pd.is_completed, 0) = 0
          AND DATEDIFF(CURDATE(), pd.in_time) > COALESCE(pdd.default_days, pd.days, 0)
        ORDER BY actual_days DESC
    """

    cursor.execute(query, params)
    return cursor.fetchall()


def _overdue_summary(rows):
    delays = [(r.get("actual_days") or 0) - (r.get("lead_days") or 0)
              for r in rows]
    total = len(rows)
    critical = sum(1 for d in delays if d > 7)
    avg = round(sum(delays) / total, 1) if total else 0
    mx = max(delays) if delays else 0
    return {
        "total_overdue": total,
        "critical_overdue": critical,
        "avg_delay_days": avg,
        "max_delay_days": mx,
    }



@data_view_bp.route("/api/supervisor/dashboard-summary", methods=["GET"])
@api_required("supervisor_dashboard", allowed_modes=("full",))
def supervisor_dashboard_summary():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        rows = _fetch_overdue_processes(cursor)
        summary = _overdue_summary(rows)

        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "summary": summary,
            "overdue_processes": rows,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# â" € Admin dashboard summary â"                                               €
@data_view_bp.route("/api/admin/dashboard-summary", methods=["GET"])
@api_required("admin_dashboard", allowed_modes=("full",))
def admin_dashboard_summary():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        rows = _fetch_overdue_processes(cursor)
        overdue = _overdue_summary(rows)

        cursor.execute("""
            SELECT
                COUNT(*) AS total_job_cards,
                SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) AS completed_job_cards,
                SUM(CASE WHEN is_completed = 0 THEN 1 ELSE 0 END) AS active_job_cards
            FROM (
                SELECT
                    jc.job_card_no,
                    CASE
                        WHEN jc.final_status = 'Completed'
                             OR EXISTS (
                                 SELECT 1
                                 FROM job_card_process_days jpd
                                 WHERE jpd.job_card_no = jc.job_card_no
                                   AND LOWER(TRIM(jpd.process_name)) = 'store'
                                   AND jpd.is_completed = 1
                             )
                        THEN 1
                        ELSE 0
                    END AS is_completed
                FROM job_cards jc
            ) summary
        """)
        counts = cursor.fetchone() or {}
        total_job_cards = int(counts.get("total_job_cards", 0) or 0)
        completed_job_cards = int(counts.get("completed_job_cards", 0) or 0)
        active_job_cards = int(counts.get("active_job_cards", 0) or 0)

        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "summary": {
                "total_job_cards": total_job_cards,
                "active_job_cards": active_job_cards,
                "completed_job_cards": completed_job_cards,
                "total_overdue": overdue["total_overdue"],
                "critical_overdue": overdue["critical_overdue"],
            },
            "overdue_processes": rows,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@data_view_bp.route("/api/dashboard/stat-detail", methods=["GET"])
def stat_detail():
    try:
        type_ = request.args.get("type", "total")
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        base = """
            SELECT ji.job_card_no, ji.item_name, ji.wip_status,
                   ji.delivery_date,
                   CASE WHEN jc.final_status = 'Completed'
                             OR LOWER(TRIM(ji.wip_status)) = 'store'
                        THEN 'Completed' ELSE jc.final_status
                   END AS final_status
            FROM job_card_items ji
            JOIN job_cards jc ON jc.job_card_no = ji.job_card_no
        """
        if type_ == "completed":
            query = """
                SELECT ji.job_card_no, ji.item_name, ji.wip_status,
                       ji.delivery_date, 'Completed' AS final_status
                FROM job_card_items ji
                JOIN job_cards jc ON jc.job_card_no = ji.job_card_no
                JOIN job_card_process_days jpd ON jpd.job_card_no = ji.job_card_no
                WHERE LOWER(TRIM(jpd.process_name)) = 'store' AND jpd.is_completed = 1
            """
        elif type_ == "active":
            query = base + """
                WHERE ji.wip_status NOT IN ('Store', 'Assembly', 'Pending')
                AND ji.wip_status != ''
            """
        elif type_ == "critical":
            query = base + """
                WHERE ji.delivery_date IS NOT NULL
                AND DATEDIFF(ji.delivery_date, CURDATE()) < -7
            """
        else:
            query = base

        cursor.execute(query + " ORDER BY ji.job_card_no LIMIT 500")
        records = cursor.fetchall()
        for r in records:
            if r.get("delivery_date"):
                r["delivery_date"] = str(r["delivery_date"])
        cursor.close()
        conn.close()
        return jsonify({"success": True, "records": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
# ── Edit Job Card Fields ────────────────────────────────────────────────────


@data_view_bp.route("/api/job_card/update_fields", methods=["POST"])
def update_job_card_fields():
    conn = None
    cursor = None
    try:
        role = (session.get("role") or "").strip().lower()
        if role not in ("admin", "supervisor"):
            return jsonify({"success": False, "error": "You do not have permission to edit these fields."}), 403

        data = request.json or {}
        original_jc_no = (data.get("job_card_no") or "").strip()
        original_item_name = (data.get("original_item_name") or "").strip()
        item_id = data.get("item_id")

        if not original_jc_no:
            return jsonify({"success": False, "error": "Job Card No is required"}), 400
        if not item_id and not original_item_name:
            return jsonify({"success": False, "error": "Item identifier is required"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_extra_cols(cursor)
        ensure_permission_tables(cursor)
        seed_default_permissions(cursor)

        def field_allowed(field_name):
            return can_user_edit_field(
                cursor, role, session.get("user_id"), PAGE5_PPC, field_name
            )

        if "wip_status" in data:
            return jsonify({
                "success": False,
                "error": "Use the stage update action to change WIP status."
            }), 403

        if role == "supervisor":
            forbidden = []
            for key in data.keys():
                if key in SUPERVISOR_UPDATE_IDENTIFIERS:
                    continue
                field_name = "job_card_no" if key == "new_job_card_no" else key
                if not field_allowed(field_name):
                    forbidden.append(field_name)
            if forbidden:
                return jsonify({
                    "success": False,
                    "error": f"Supervisor cannot edit: {', '.join(sorted(set(forbidden)))}"
                }), 403

        if item_id:
            cursor.execute("""
                SELECT id, job_card_no, item_name, wip_status
                FROM job_card_items
                WHERE id = %s AND job_card_no = %s
                LIMIT 1
            """, (item_id, original_jc_no))
        else:
            cursor.execute("""
                SELECT id, job_card_no, item_name, wip_status
                FROM job_card_items
                WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
                LIMIT 1
            """, (original_jc_no, original_item_name))
        item_row = cursor.fetchone()
        if not item_row:
            return jsonify({"success": False, "error": "Job card item not found"}), 404

        current_process = item_row.get("wip_status") or ""
        has_current_process_access = (
            role != "supervisor"
            or has_process_access(cursor, session.get("user_id"), current_process)
        )

        target_jc_no = original_jc_no
        updated_fields = []

        can_edit_job_card_no = field_allowed("job_card_no")
        if "new_job_card_no" in data and can_edit_job_card_no:
            new_jc_no = (data.get("new_job_card_no") or original_jc_no).strip()
            if not new_jc_no:
                return jsonify({"success": False, "error": "New Job Card No is required"}), 400
        else:
            new_jc_no = original_jc_no

        job_card_field_map = {
            "so_no": "so_no",
            "customer_name": "customer_name",
            "work_order_no": "work_order_no",
            "parent_code": "parent_code",
            "child_code": "child_code",
        }
        job_card_sets = []
        job_card_params = []
        if new_jc_no != original_jc_no:
            job_card_sets = ["job_card_no = %s"]
            job_card_params = [new_jc_no]
            updated_fields.append("job_card_no")
        for payload_key, column_name in job_card_field_map.items():
            if payload_key in data and field_allowed(payload_key):
                job_card_sets.append(f"{column_name} = %s")
                job_card_params.append((data.get(payload_key) or "").strip())
                updated_fields.append(payload_key)
        if job_card_sets:
            job_card_params.append(original_jc_no)
            cursor.execute(f"""
                UPDATE job_cards
                SET {", ".join(job_card_sets)}
                WHERE job_card_no = %s
            """, job_card_params)
            target_jc_no = new_jc_no

            if new_jc_no != original_jc_no:
                cursor.execute("""
                    UPDATE job_card_process_days
                    SET job_card_no = %s
                    WHERE job_card_no = %s
                """, (new_jc_no, original_jc_no))
                cursor.execute("""
                    UPDATE audit_trail
                    SET job_card_no = %s
                    WHERE job_card_no = %s
                """, (new_jc_no, original_jc_no))

        item_sets = []
        item_params = []

        if new_jc_no != original_jc_no:
            item_sets.append("job_card_no = %s")
            item_params.append(target_jc_no)
        if "item_name" in data and field_allowed("item_name"):
            item_sets.append("item_name = %s")
            item_params.append((data.get("item_name") or "").strip())
            updated_fields.append("item_name")
        if "material" in data and field_allowed("material"):
            item_sets.append("material = %s")
            item_params.append((data.get("material") or "").strip())
            updated_fields.append("material")
        if "so_qty" in data and field_allowed("so_qty"):
            item_sets.append("so_qty = %s")
            item_params.append(parse_optional_int(data.get("so_qty"), "SO Qty") or 0)
            updated_fields.append("so_qty")

        if "actual_qty" in data and field_allowed("actual_qty"):
            if role == "supervisor" and not has_current_process_access:
                return jsonify({
                    "success": False,
                    "error": f"You do not have rights to update process: {current_process}"
                }), 403
            item_sets.append("actual_qty = %s")
            item_params.append(parse_optional_int(data.get("actual_qty"), "Actual Qty"))
            updated_fields.append("actual_qty")
        if "remarks" in data and field_allowed("remarks"):
            if role == "supervisor" and not has_current_process_access:
                return jsonify({
                    "success": False,
                    "error": f"You do not have rights to update process: {current_process}"
                }), 403
            item_sets.append("remarks = %s")
            item_params.append((data.get("remarks") or "").strip())
            updated_fields.append("remarks")

        if item_sets:
            item_params.append(item_row["id"])
            cursor.execute(f"""
                UPDATE job_card_items
                SET {", ".join(item_sets)}
                WHERE id = %s
            """, item_params)

        vendor_name = None
        if "vendor_name" in data and field_allowed("vendor_name"):
            vendor_name = (data.get("vendor_name") or "").strip()
        elif "subcontractor_name" in data and field_allowed("subcontractor_name"):
            vendor_name = (data.get("subcontractor_name") or "").strip()

        if vendor_name is not None:
            process_name = (
                data.get("process_name")
                or data.get("current_process")
                or current_process
                or ""
            ).strip()
            if not process_name:
                return jsonify({"success": False, "error": "Current process is required for vendor update"}), 400
            if role == "supervisor" and not has_process_access(
                cursor, session.get("user_id"), process_name
            ):
                return jsonify({
                    "success": False,
                    "error": f"You do not have rights to update process: {process_name}"
                }), 403
            cursor.execute("""
                UPDATE job_card_process_days
                SET vendor_name = %s,
                    is_subcontract = CASE WHEN %s = '' THEN 0 ELSE 1 END
                WHERE job_card_no = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
            """, (vendor_name, vendor_name, target_jc_no, process_name))
            updated_fields.append("vendor_name")

        if not updated_fields:
            return jsonify({"success": False, "error": "No editable fields were provided"}), 400

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Job card updated successfully",
            "updated_fields": sorted(set(updated_fields)),
        })
    except ValueError as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
