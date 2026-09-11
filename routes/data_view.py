"""
Data View API routes â€" Demo 2
All filtering, sorting, pagination and stats done in SQL.
JS only renders what the backend returns.
"""

from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session

from auth_utils import api_required
from db import get_connection
from permission_utils import (
    PAGE5_BASE_FIELDS,
    PAGE5_PPC,
    PROCESS_FIELDS,
    can_user_edit_field,
    can_user_view_field,
    ensure_permission_tables,
    has_process_access,
    is_gaurang_special_user,
    seed_default_permissions,
)

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt


data_view_bp = Blueprint("data_view", __name__)

PROCESS_COUNT = 25
PROCESS_COLUMNS = [f"p{i}" for i in range(1, PROCESS_COUNT + 1)]
PROCESS_COLUMNS_SQL = ", ".join(f"pm.{col}" for col in PROCESS_COLUMNS)

_PAGE5_SCHEMA_READY = False


def can_see_page5_priority(cursor, role, user_id):
    return can_user_view_field(cursor, role, user_id, PAGE5_PPC, "is_priority")


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
            delivery_dt = datetime.strptime(
                delivery_date[:10], "%Y-%m-%d").date()
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
    for col, defn in [
        ("is_deleted", "TINYINT(1) DEFAULT 0"),
        ("deleted_by", "VARCHAR(100) NULL"),
        ("deleted_at", "DATETIME NULL"),
        ("delete_reason", "TEXT NULL"),
    ]:
        if not col_exists(cursor, "job_card_items", col):
            cursor.execute(
                f"ALTER TABLE job_card_items ADD COLUMN {col} {defn}")


def ensure_job_card_number_update_cascade(cursor):
    """Allow a Job Card No rename to propagate to every dependent table."""
    foreign_keys = (
        ("job_card_items", "job_card_items_ibfk_1"),
        ("job_card_process_days", "job_card_process_days_ibfk_1"),
        ("quality_checks", "quality_checks_ibfk_1"),
    )
    for table_name, constraint_name in foreign_keys:
        cursor.execute("""
            SELECT update_rule
            FROM information_schema.referential_constraints
            WHERE constraint_schema = DATABASE()
              AND table_name = %s
              AND constraint_name = %s
        """, (table_name, constraint_name))
        constraint = cursor.fetchone()
        if not constraint or str(constraint.get("update_rule", constraint[0] if isinstance(constraint, tuple) else "")).upper() == "CASCADE":
            continue

        cursor.execute(
            f"ALTER TABLE `{table_name}` DROP FOREIGN KEY `{constraint_name}`")
        cursor.execute(f"""
            ALTER TABLE `{table_name}`
            ADD CONSTRAINT `{constraint_name}`
            FOREIGN KEY (`job_card_no`)
            REFERENCES `job_cards` (`job_card_no`)
            ON UPDATE CASCADE
        """)


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


@data_view_bp.route("/api/data/job_cards/filter_options", methods=["GET"])
def data_job_card_filter_options():
    global _PAGE5_SCHEMA_READY
    """
    Returns unique values for Excel-like column header filters on Page 5 PPC tab.
    This endpoint does not change data. It only supplies dropdown checkbox values.
    """
    conn = None
    cursor = None

    try:
        column = (request.args.get("column") or "").strip()
        search = (request.args.get("search") or "").strip()

        allowed_columns = {
            "is_priority": "CASE WHEN COALESCE(ji.is_priority, 0) = 1 THEN 'Yes' ELSE 'No' END",
            "job_card_no": "jc.job_card_no",
            "waiting_for_jc": "''",
            "so_no": "jc.so_no",
            "customer_name": "jc.customer_name",
            "parent_code": "jc.parent_code",
            "child_code": "jc.child_code",
            "work_order_no": "jc.work_order_no",
            "assembly_name": "jc.assembly_name",
            "item_name": "ji.item_name",
            "size": "ji.size",
            "part": "ji.part",
            "material": """COALESCE((
                SELECT i2.item_description 
                FROM bom_links bl2 
                JOIN items i2 ON i2.item_code COLLATE utf8mb4_unicode_ci = bl2.child_code COLLATE utf8mb4_unicode_ci
                WHERE bl2.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                AND bl2.make_buy = 'I'
                AND bl2.is_alternate = 0
                LIMIT 1
            ), NULLIF(ji.material, ''), '')""",

            "so_qty": "ji.so_qty",
            "actual_qty": "ji.actual_qty",

            "wip_status": "ji.wip_status",
            "rm_hold_reason": "COALESCE(ji.rm_hold_reason, '')",
            "remarks": "ji.remarks",
            "vendor_name": "COALESCE(pd_current.vendor_name, '')",

            "wip_stage_days": """
    CASE
        WHEN LOWER(TRIM(ji.wip_status)) = 'raw material'
         AND LOWER(TRIM(COALESCE(ji.rm_hold_reason, ''))) = 'shortage'
        THEN 0
        ELSE COALESCE(
            (
                SELECT GREATEST(0, DATEDIFF(CURDATE(), pd3.in_time))
                FROM job_card_process_days pd3
                WHERE pd3.job_card_no = ji.job_card_no
                  AND LOWER(TRIM(pd3.process_name)) = LOWER(TRIM(ji.wip_status))
                  AND pd3.in_time IS NOT NULL
                  AND pd3.out_time IS NULL
                  AND COALESCE(pd3.is_completed, 0) = 0
                LIMIT 1
            ),
            ji.wip_stage_days,
            0
        )
    END
""",
            "total_days": "COALESCE(ji.total_days, 0)",
            "remaining_days": "DATEDIFF(ji.delivery_date, CURDATE())",
            "days_overdue": """
        CASE
            WHEN ji.delivery_date IS NOT NULL
             AND ji.delivery_date < CURDATE()
             AND jc.final_status != 'Completed'
            THEN DATEDIFF(CURDATE(), ji.delivery_date)
            ELSE 0
        END
    """,

            "final_status": """
        CASE 
            WHEN jc.final_status = 'Completed'
              OR LOWER(TRIM(ji.wip_status)) = 'store'
            THEN 'Completed'
            ELSE jc.final_status
        END
    """,

            "delivery_date": "DATE_FORMAT(ji.delivery_date, '%Y-%m-%d')",
            "so_date": "DATE_FORMAT(jc.so_date, '%Y-%m-%d')",
            "last_audit": """
    COALESCE((
        SELECT at.changed_by
        FROM audit_trail at
        WHERE at.job_card_no = ji.job_card_no
          AND at.item_name   = ji.item_name
        ORDER BY at.changed_at DESC
        LIMIT 1
    ), '')
""",
        }

        if column not in allowed_columns:
            return jsonify({
                "success": False,
                "error": f"Column '{column}' is not allowed for filter options."
            }), 400

        col_expr = allowed_columns[column]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_permission_tables(cursor)
        if column == "is_priority" and not can_see_page5_priority(
            cursor,
            session.get("role"),
            session.get("user_id"),
        ):
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "You do not have permission to view priority"}), 403

        if not _PAGE5_SCHEMA_READY:
            ensure_extra_cols(cursor)
            _PAGE5_SCHEMA_READY = True

        # Waiting For JC is derived from the existing dependency helper.
        if column == "waiting_for_jc":
            cursor.execute("""
                SELECT
                    jc.job_card_no,
                    jc.so_no,
                    jc.child_code
                FROM job_cards jc
                JOIN job_card_items ji
                  ON jc.job_card_no = ji.job_card_no
                WHERE COALESCE(ji.is_deleted, 0) = 0
            """)

            dependency_rows = cursor.fetchall()

            _enrich_page5_dependency_rows(
                cursor,
                dependency_rows
            )

            values = sorted({
                str(row.get("waiting_for_jc") or "").strip()
                for row in dependency_rows
                if str(row.get("waiting_for_jc") or "").strip()
            })

            # Blank option = JC is not waiting for any JC.
            values.append("")

            cursor.close()
            conn.close()

            return jsonify({
                "success": True,
                "column": "waiting_for_jc",
                "values": values
            })

        params = []
        where = ["COALESCE(ji.is_deleted, 0) = 0"]

        if search:
            where.append("""
                (
                    jc.job_card_no LIKE %s OR jc.so_no LIKE %s OR
                    jc.customer_name LIKE %s OR
                    jc.parent_code LIKE %s OR jc.child_code LIKE %s OR
                    ji.item_name LIKE %s OR ji.material LIKE %s OR
                    ji.wip_status LIKE %s
                )
            """)
            s = f"%{search}%"
            params += [s, s, s, s, s, s, s, s]

        where_sql = " AND ".join(where)

        # FILTER_OPTIONS_FAST_PATH_START
        # Fast dropdown values for common PPC columns.
        # Avoid unnecessary job_card_process_days join and avoid material correlated subquery.
        simple_filter_exprs = {
            "is_priority": "CASE WHEN COALESCE(ji.is_priority, 0) = 1 THEN 'Yes' ELSE 'No' END",
            "job_card_no": "jc.job_card_no",
            "so_no": "jc.so_no",
            "customer_name": "jc.customer_name",
            "parent_code": "jc.parent_code",
            "child_code": "jc.child_code",
            "work_order_no": "jc.work_order_no",
            "assembly_name": "jc.assembly_name",
            "item_name": "ji.item_name",
            "size": "ji.size",
            "part": "ji.part",
            "so_qty": "ji.so_qty",
            "actual_qty": "ji.actual_qty",
            "wip_status": "ji.wip_status",
            "remarks": "ji.remarks",
            "total_days": "COALESCE(ji.total_days, 0)",
            "remaining_days": "DATEDIFF(ji.delivery_date, CURDATE())",
            "days_overdue": """
                CASE
                    WHEN ji.delivery_date IS NOT NULL
                     AND ji.delivery_date < CURDATE()
                     AND jc.final_status != 'Completed'
                    THEN DATEDIFF(CURDATE(), ji.delivery_date)
                    ELSE 0
                END
            """,
            "final_status": """
                CASE
                    WHEN jc.final_status = 'Completed'
                      OR LOWER(TRIM(ji.wip_status)) = 'store'
                    THEN 'Completed'
                    ELSE jc.final_status
                END
            """,
            "delivery_date": "DATE_FORMAT(ji.delivery_date, '%Y-%m-%d')",
            "so_date": "DATE_FORMAT(jc.so_date, '%Y-%m-%d')",
        }

        if column in simple_filter_exprs:
            fast_expr = simple_filter_exprs[column]
            cursor.execute(f"""
                SELECT DISTINCT
                    COALESCE(CAST(({fast_expr}) AS CHAR), '') AS value
                FROM job_cards jc
                JOIN job_card_items ji
                    ON jc.job_card_no = ji.job_card_no
                WHERE {where_sql}
                ORDER BY
                    CASE WHEN value = '' THEN 1 ELSE 0 END,
                    value
                LIMIT 500
            """, params)

            values = [r["value"] for r in cursor.fetchall()]
            if column == "wip_status" and "Subcontract" not in values:
                values.append("Subcontract")

            return jsonify({
                "success": True,
                "column": column,
                "values": values
            })

        if column == "material":
            cursor.execute(f"""
                SELECT value
                FROM (
                    SELECT DISTINCT
                        COALESCE(CAST(raw_value AS CHAR), '') AS value
                    FROM (
                        SELECT NULLIF(TRIM(ji.material), '') AS raw_value
                        FROM job_cards jc
                        JOIN job_card_items ji
                            ON jc.job_card_no = ji.job_card_no
                        WHERE {where_sql}
                          AND NULLIF(TRIM(ji.material), '') IS NOT NULL

                        UNION

                        SELECT i2.item_description AS raw_value
                        FROM job_cards jc
                        JOIN job_card_items ji
                            ON jc.job_card_no = ji.job_card_no
                        JOIN bom_links bl2
                            ON bl2.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                           AND bl2.make_buy = 'I'
                           AND bl2.is_alternate = 0
                        JOIN items i2
                            ON i2.item_code COLLATE utf8mb4_unicode_ci = bl2.child_code COLLATE utf8mb4_unicode_ci
                        WHERE {where_sql}
                          AND (ji.material IS NULL OR TRIM(ji.material) = '')
                    ) x
                    WHERE raw_value IS NOT NULL
                ) y
                ORDER BY
                    CASE WHEN y.value = '' THEN 1 ELSE 0 END,
                    y.value
                LIMIT 500
            """, list(params) + list(params))

            values = [r["value"] for r in cursor.fetchall()]
            return jsonify({
                "success": True,
                "column": column,
                "values": values
            })

        if column == "vendor_name":
            cursor.execute("""
                SELECT DISTINCT COALESCE(TRIM(vendor_name), '') AS value
                FROM job_card_process_days
                WHERE vendor_name IS NOT NULL
                ORDER BY
                    CASE WHEN value = '' THEN 1 ELSE 0 END,
                    value
                LIMIT 500
            """)
            values = [r["value"] for r in cursor.fetchall()]
            return jsonify({
                "success": True,
                "column": column,
                "values": values
            })
        # FILTER_OPTIONS_FAST_PATH_END

        cursor.execute(f"""
            SELECT DISTINCT
                COALESCE(CAST(({col_expr}) AS CHAR), '') AS value
            FROM job_cards jc
            JOIN job_card_items ji
                ON jc.job_card_no = ji.job_card_no
            LEFT JOIN job_card_process_days pd_current
                ON pd_current.job_card_no = ji.job_card_no
               AND LOWER(TRIM(pd_current.process_name)) = LOWER(TRIM(ji.wip_status))
            WHERE {where_sql}
            ORDER BY 
                CASE WHEN value = '' THEN 1 ELSE 0 END,
                value
            LIMIT 500
        """, params)

        values = [r["value"] for r in cursor.fetchall()]
        if column == "wip_status" and "Subcontract" not in values:
            values.append("Subcontract")

        return jsonify({
            "success": True,
            "column": column,
            "values": values
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
# â" € Job Cards tab â"                                                            €


# PAGE5_EXPORT_DEPENDENCY_V4
def _enrich_page5_dependency_rows(cursor, rows):
    """
    Exact Page 5 Excel Job Card dependency.

    Rule:
    1. Current JC child_code is the manufactured item.
    2. Find its direct MAKE -C child from bom_links:
           bom_links.parent_code = current JC child_code
    3. Find the Job Card whose child_code equals that BOM child_code
       under the same SO.
    4. If that child JC is incomplete, current JC is BLOCKED.

    Example:
        JC 0000114488
        child_code NAOTR0001165
             -> BOM child NCONS0001415
             -> JC 0000114487
        Therefore 0000114488 waits for 0000114487.

    Export only. No production movement logic is changed.
    """
    from collections import defaultdict
    import re

    if not rows:
        return rows

    def norm_so(value):
        value = str(value or "").strip()
        if value in ("", "-"):
            return "__BLANK_SO__"
        return value.lower()

    def is_completed(final_status, wip_status):
        fs = str(final_status or "").strip().lower()
        ws = str(wip_status or "").strip().lower()

        return (
            fs == "completed"
            or ws in ("store", "completed", "complete")
        )

    # Only required Excel fields.
    for row in rows:
        row["jc_dependency"] = "ACTIVE"
        row["waiting_for_jc"] = ""
        row["activation_condition"] = ""

    # Current manufactured item codes from exported JCs.
    current_item_codes = sorted({
        str(row.get("child_code") or "").strip()
        for row in rows
        if str(row.get("child_code") or "").strip()
    })

    if not current_item_codes:
        return rows

    placeholders = ", ".join(
        ["%s"] * len(current_item_codes)
    )

    # ---------------------------------------------------------
    # 1. Find exact direct -C children for each current item.
    # ---------------------------------------------------------
    cursor.execute(f"""
        SELECT
            bl.parent_code,
            bl.child_code,
            ci.item_description AS child_description
        FROM bom_links bl
        JOIN items ci
          ON ci.item_code COLLATE utf8mb4_unicode_ci
           = bl.child_code COLLATE utf8mb4_unicode_ci
        WHERE bl.parent_code IN ({placeholders})
          AND bl.make_buy = 'A'
          AND COALESCE(bl.is_alternate, 0) = 0
          AND (
                UPPER(TRIM(ci.item_description)) LIKE '%- C'
             OR UPPER(TRIM(ci.item_description)) LIKE '%-C'
          )
    """, current_item_codes)

    parent_to_required_codes = defaultdict(set)

    for link in cursor.fetchall():
        parent_code = str(
            link.get("parent_code") or ""
        ).strip()

        child_code = str(
            link.get("child_code") or ""
        ).strip()

        description = str(
            link.get("child_description") or ""
        ).strip()

        if not parent_code or not child_code:
            continue

        if not (
            re.search(r"\s-\s*C$", description, re.IGNORECASE)
            or description.upper().endswith("-C")
        ):
            continue

        parent_to_required_codes[parent_code].add(child_code)

    if not parent_to_required_codes:
        return rows

    required_codes = sorted({
        code
        for codes in parent_to_required_codes.values()
        for code in codes
    })

    if not required_codes:
        return rows

    child_placeholders = ", ".join(
        ["%s"] * len(required_codes)
    )

    # ---------------------------------------------------------
    # 2. Find actual JCs for those exact required child codes.
    # ---------------------------------------------------------
    cursor.execute(f"""
        SELECT
            jc.job_card_no,
            jc.so_no,
            jc.parent_code,
            jc.child_code,
            jc.final_status,
            ji.item_name,
            ji.wip_status
        FROM job_cards jc
        JOIN job_card_items ji
          ON ji.job_card_no = jc.job_card_no
         AND COALESCE(ji.is_deleted, 0) = 0
        WHERE jc.child_code IN ({child_placeholders})
        ORDER BY jc.job_card_no
    """, required_codes)

    child_job_map = defaultdict(list)

    for child in cursor.fetchall():
        key = (
            norm_so(child.get("so_no")),
            str(child.get("child_code") or "").strip(),
        )

        child_job_map[key].append(child)

    # ---------------------------------------------------------
    # 3. Resolve exact blocker for each exported JC.
    # ---------------------------------------------------------
    for row in rows:
        current_jc = str(
            row.get("job_card_no") or ""
        ).strip()

        current_code = str(
            row.get("child_code") or ""
        ).strip()

        current_so = norm_so(
            row.get("so_no")
        )

        blockers = []

        for required_code in sorted(
            parent_to_required_codes.get(current_code, set())
        ):
            candidates = child_job_map.get(
                (current_so, required_code),
                [],
            )

            for child in candidates:
                child_jc = str(
                    child.get("job_card_no") or ""
                ).strip()

                if not child_jc or child_jc == current_jc:
                    continue

                if is_completed(
                    child.get("final_status"),
                    child.get("wip_status"),
                ):
                    continue

                blockers.append(child_jc)

        blocker_jcs = sorted(set(blockers))

        if not blocker_jcs:
            continue

        row["jc_dependency"] = "BLOCKED"
        row["waiting_for_jc"] = " / ".join(blocker_jcs)

        if len(blocker_jcs) == 1:
            row["activation_condition"] = (
                f"Active after JC {blocker_jcs[0]} completes"
            )
        else:
            row["activation_condition"] = (
                "Active after JCs "
                + ", ".join(blocker_jcs)
                + " complete"
            )

    return rows


@data_view_bp.route("/api/data/job_cards", methods=["GET"])
def data_job_cards():
    global _PAGE5_SCHEMA_READY
    try:
        search = request.args.get("search", "").strip()
        wip = request.args.get("wip", "").strip()
        status = request.args.get("status", "").strip()
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        supervisor_user_id = request.args.get("supervisor_user_id", "").strip()
        sort_col = request.args.get("sort", "jc.created_at")
        sort_dir = "ASC" if request.args.get(
            "order", "desc").lower() == "asc" else "DESC"
        page = safe_int(request.args.get("page", 1))
        per_page = safe_int(request.args.get("per_page", 50))
        offset = (page - 1) * per_page
        role = (session.get("role") or "").strip().lower()
        user_id = session.get("user_id")
        include_dependencies = (
            request.args.get("include_dependencies", "").strip() == "1"
        )

        allowed_sorts = {
            "is_priority": "COALESCE(ji.is_priority, 0)",
            "job_card_no": "jc.job_card_no",
            "so_no": "jc.so_no",
            "customer_name": "jc.customer_name",
            "parent_code": "jc.parent_code",
            "child_code": "jc.child_code",
            "assembly_name": "jc.assembly_name",
            "item_name": "ji.item_name",
            "size": "ji.size",
            "part": "ji.part",
            "material": """COALESCE(
                NULLIF(ji.material, ''),
                (
                    SELECT GROUP_CONCAT(DISTINCT i2.item_description ORDER BY i2.item_description SEPARATOR ' / ')
                    FROM bom_links bl2
                    JOIN items i2
                      ON i2.item_code COLLATE utf8mb4_unicode_ci = bl2.child_code COLLATE utf8mb4_unicode_ci
                    WHERE bl2.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                      AND bl2.make_buy = 'I'
                      AND COALESCE(bl2.is_alternate, 0) = 0
                ),
                ''
            )""",
            "so_qty": "COALESCE(ji.so_qty, 0)",
            "actual_qty": "COALESCE(ji.actual_qty, 0)",
            "wip_status": "ji.wip_status",
            "remarks": "ji.remarks",
            "wip_stage_days": "COALESCE(ji.wip_stage_days, 0)",
            "total_days": "COALESCE(ji.total_days, 0)",
            "remaining_days": "DATEDIFF(ji.delivery_date, CURDATE())",
            "days_overdue": """
                CASE
                    WHEN ji.delivery_date IS NOT NULL
                     AND ji.delivery_date < CURDATE()
                     AND jc.final_status != 'Completed'
                    THEN DATEDIFF(CURDATE(), ji.delivery_date)
                    ELSE 0
                END
            """,
            "final_status": """
                CASE
                    WHEN jc.final_status = 'Completed'
                      OR LOWER(TRIM(ji.wip_status)) = 'store'
                    THEN 'Completed'
                    ELSE jc.final_status
                END
            """,
            "delivery_date": "ji.delivery_date",
            "so_date": "jc.so_date",
            "created_at": "jc.created_at",
            "last_audit": """
                COALESCE((
                    SELECT at.changed_by
                    FROM audit_trail at
                    WHERE at.job_card_no = ji.job_card_no
                      AND at.item_name = ji.item_name
                    ORDER BY at.changed_at DESC
                    LIMIT 1
                ), '')
            """,
            "vendor_name": "pd_current.vendor_name",
        }
        order_expr = allowed_sorts.get(sort_col, "jc.created_at")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_permission_tables(cursor)
        can_see_priority_column = can_see_page5_priority(cursor, role, user_id)
        if not can_see_priority_column and sort_col == "is_priority":
            sort_col = "jc.created_at"
            order_expr = "jc.created_at"
        priority_order_sql = "COALESCE(ji.is_priority, 0) DESC, "

        if not _PAGE5_SCHEMA_READY:
            ensure_extra_cols(cursor)
            ensure_permission_tables(cursor)
            seed_default_permissions(cursor)
            conn.commit()
            _PAGE5_SCHEMA_READY = True

        params = []
        where = ["COALESCE(ji.is_deleted, 0) = 0"]
        excel_filter_columns = {
            "is_priority": "CASE WHEN COALESCE(ji.is_priority, 0) = 1 THEN 'Yes' ELSE 'No' END",
            "job_card_no": "jc.job_card_no",
            "so_no": "jc.so_no",
            "customer_name": "jc.customer_name",
            "parent_code": "jc.parent_code",
            "child_code": "jc.child_code",
            "work_order_no": "jc.work_order_no",
            "assembly_name": "jc.assembly_name",
            "item_name": "ji.item_name",
            "size": "ji.size",
            "part": "ji.part",
            "material": """COALESCE((
                SELECT i2.item_description 
                FROM bom_links bl2 
                JOIN items i2 ON i2.item_code COLLATE utf8mb4_unicode_ci = bl2.child_code COLLATE utf8mb4_unicode_ci
                WHERE bl2.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                AND bl2.make_buy = 'I' 
                AND bl2.is_alternate = 0
                LIMIT 1
            ), NULLIF(ji.material, ''), '')""",

            "so_qty": "ji.so_qty",
            "actual_qty": "ji.actual_qty",

            "wip_status": "ji.wip_status",
            "remarks": "ji.remarks",
            "vendor_name": "COALESCE(pd_current.vendor_name, '')",

            "wip_stage_days": """
    CASE
        WHEN LOWER(TRIM(ji.wip_status)) = 'raw material'
         AND LOWER(TRIM(COALESCE(ji.rm_hold_reason, ''))) = 'shortage'
        THEN 0
        ELSE COALESCE(
            (
                SELECT GREATEST(0, DATEDIFF(CURDATE(), pd3.in_time))
                FROM job_card_process_days pd3
                WHERE pd3.job_card_no = ji.job_card_no
                  AND LOWER(TRIM(pd3.process_name)) = LOWER(TRIM(ji.wip_status))
                  AND pd3.in_time IS NOT NULL
                  AND pd3.out_time IS NULL
                  AND COALESCE(pd3.is_completed, 0) = 0
                LIMIT 1
            ),
            ji.wip_stage_days,
            0
        )
    END
""",
            "total_days": "COALESCE(ji.total_days, 0)",
            "remaining_days": "DATEDIFF(ji.delivery_date, CURDATE())",
            "days_overdue": """
        CASE
            WHEN ji.delivery_date IS NOT NULL
             AND ji.delivery_date < CURDATE()
             AND jc.final_status != 'Completed'
            THEN DATEDIFF(CURDATE(), ji.delivery_date)
            ELSE 0
        END
    """,

            "final_status": """
        CASE 
            WHEN jc.final_status = 'Completed'
              OR LOWER(TRIM(ji.wip_status)) = 'store'
            THEN 'Completed'
            ELSE jc.final_status
        END
    """,

            "delivery_date": "DATE_FORMAT(ji.delivery_date, '%Y-%m-%d')",
            "so_date": "DATE_FORMAT(jc.so_date, '%Y-%m-%d')",
            "last_audit": """
    COALESCE((
        SELECT at.changed_by
        FROM audit_trail at
        WHERE at.job_card_no = ji.job_card_no
          AND at.item_name   = ji.item_name
        ORDER BY at.changed_at DESC
        LIMIT 1
    ), '')
""",
        }

        for filter_key, filter_expr in excel_filter_columns.items():
            if filter_key in ("material", "vendor_name"):
                continue

            selected_values = request.args.getlist(f"xf_{filter_key}")

            if not selected_values:
                continue

            clean_values = []
            include_blank = False
            value_conditions = []

            for value in selected_values:
                value = (value or "").strip()

                if value == "__BLANK__":
                    include_blank = True
                elif filter_key == "wip_status" and value.lower() == "subcontract":
                    value_conditions.append("""
                        COALESCE(pd_current.is_subcontract, 0) = 1
                        OR COALESCE(TRIM(pd_current.vendor_name), '') != ''
                    """)
                elif value != "":
                    clean_values.append(value)

            if clean_values:
                placeholders = ", ".join(["%s"] * len(clean_values))
                value_conditions.append(
                    f"COALESCE(CAST(({filter_expr}) AS CHAR), '') IN ({placeholders})")
                params.extend(clean_values)

            if include_blank:
                value_conditions.append(
                    f"COALESCE(CAST(({filter_expr}) AS CHAR), '') = ''")

            if value_conditions:
                where.append("(" + " OR ".join(value_conditions) + ")")
                # WAITING_FOR_JC_FILTER_START
        waiting_filter_values = [
            str(v or "").strip()
            for v in request.args.getlist("xf_waiting_for_jc")
        ]

        if waiting_filter_values:
            include_blank = "__BLANK__" in waiting_filter_values

            selected_blockers = {
                v
                for v in waiting_filter_values
                if v and v != "__BLANK__"
            }

            cursor.execute("""
                SELECT
                    jc_dep.job_card_no,
                    jc_dep.so_no,
                    jc_dep.child_code
                FROM job_cards jc_dep
                JOIN job_card_items ji_dep
                  ON jc_dep.job_card_no = ji_dep.job_card_no
                WHERE COALESCE(ji_dep.is_deleted, 0) = 0
            """)

            dependency_rows = cursor.fetchall()

            _enrich_page5_dependency_rows(
                cursor,
                dependency_rows
            )

            matching_jcs = []

            for dep_row in dependency_rows:
                waiting_value = str(
                    dep_row.get("waiting_for_jc") or ""
                ).strip()

                matched = waiting_value in selected_blockers

                if include_blank and waiting_value == "":
                    matched = True

                if matched:
                    jc_no = str(
                        dep_row.get("job_card_no") or ""
                    ).strip()

                    if jc_no:
                        matching_jcs.append(jc_no)

            matching_jcs = sorted(set(matching_jcs))

            if matching_jcs:
                placeholders = ", ".join(
                    ["%s"] * len(matching_jcs)
                )

                where.append(
                    f"jc.job_card_no IN ({placeholders})"
                )
                params.extend(matching_jcs)
            else:
                where.append("1 = 0")
        # WAITING_FOR_JC_FILTER_END

        # SPECIAL_FAST_FILTER_MATERIAL_VENDOR_START
        # Special optimized filters for Material and Vendor.

        # Material INCLUDE: xf_material=value
        # Optimized: resolve BOM raw-material parent codes once, then use jc.child_code IN (...)
        material_include = request.args.getlist("xf_material")
        if material_include:
            material_values = []
            include_blank = False

            for value in material_include:
                value = (value or "").strip()
                if value == "__BLANK__":
                    include_blank = True
                elif value != "":
                    material_values.append(value)

            material_parent_codes = []
            if material_values:
                placeholders = ", ".join(["%s"] * len(material_values))
                cursor.execute(f"""
                    SELECT DISTINCT bl_mat.parent_code AS parent_code
                    FROM bom_links bl_mat
                    JOIN items i_mat
                      ON i_mat.item_code COLLATE utf8mb4_unicode_ci = bl_mat.child_code COLLATE utf8mb4_unicode_ci
                    WHERE bl_mat.make_buy = 'I'
                      AND COALESCE(bl_mat.is_alternate, 0) = 0
                      AND i_mat.item_description IN ({placeholders})
                """, material_values)
                material_parent_codes = [
                    r["parent_code"] for r in cursor.fetchall()
                    if r.get("parent_code")
                ]

            material_conditions = []

            if material_values:
                placeholders = ", ".join(["%s"] * len(material_values))
                material_conditions.append(f"""
                    (
                        NULLIF(TRIM(ji.material), '') IS NOT NULL
                        AND TRIM(ji.material) IN ({placeholders})
                    )
                """)
                params.extend(material_values)

            if material_parent_codes:
                placeholders = ", ".join(["%s"] * len(material_parent_codes))
                material_conditions.append(f"""
                    (
                        (ji.material IS NULL OR TRIM(ji.material) = '')
                        AND jc.child_code IN ({placeholders})
                    )
                """)
                params.extend(material_parent_codes)

            if include_blank:
                material_conditions.append("""
                    (
                        (ji.material IS NULL OR TRIM(ji.material) = '')
                        AND NOT EXISTS (
                            SELECT 1
                            FROM bom_links bl_mat_blank
                            WHERE bl_mat_blank.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                              AND bl_mat_blank.make_buy = 'I'
                              AND COALESCE(bl_mat_blank.is_alternate, 0) = 0
                        )
                    )
                """)

            if material_conditions:
                where.append("(" + " OR ".join(material_conditions) + ")")

        # Material EXCLUDE: xfn_material=value
        material_exclude = request.args.getlist("xfn_material")
        if material_exclude:
            material_exclude_values = []
            exclude_blank = False

            for value in material_exclude:
                value = (value or "").strip()
                if value == "__BLANK__":
                    exclude_blank = True
                elif value != "":
                    material_exclude_values.append(value)

            material_exclude_parent_codes = []
            if material_exclude_values:
                placeholders = ", ".join(["%s"] * len(material_exclude_values))
                cursor.execute(f"""
                    SELECT DISTINCT bl_mat.parent_code AS parent_code
                    FROM bom_links bl_mat
                    JOIN items i_mat
                      ON i_mat.item_code COLLATE utf8mb4_unicode_ci = bl_mat.child_code COLLATE utf8mb4_unicode_ci
                    WHERE bl_mat.make_buy = 'I'
                      AND COALESCE(bl_mat.is_alternate, 0) = 0
                      AND i_mat.item_description IN ({placeholders})
                """, material_exclude_values)
                material_exclude_parent_codes = [
                    r["parent_code"] for r in cursor.fetchall()
                    if r.get("parent_code")
                ]

            material_exclude_conditions = []

            if material_exclude_values:
                placeholders = ", ".join(["%s"] * len(material_exclude_values))
                material_exclude_conditions.append(f"""
                    NOT (
                        NULLIF(TRIM(ji.material), '') IS NOT NULL
                        AND TRIM(ji.material) IN ({placeholders})
                    )
                """)
                params.extend(material_exclude_values)

            if material_exclude_parent_codes:
                placeholders = ", ".join(["%s"] * len(material_exclude_parent_codes))
                material_exclude_conditions.append(f"""
                    NOT (
                        (ji.material IS NULL OR TRIM(ji.material) = '')
                        AND jc.child_code IN ({placeholders})
                    )
                """)
                params.extend(material_exclude_parent_codes)

            if exclude_blank:
                material_exclude_conditions.append("""
                    (
                        NULLIF(TRIM(ji.material), '') IS NOT NULL
                        OR EXISTS (
                            SELECT 1
                            FROM bom_links bl_mat_not_blank
                            WHERE bl_mat_not_blank.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                              AND bl_mat_not_blank.make_buy = 'I'
                              AND COALESCE(bl_mat_not_blank.is_alternate, 0) = 0
                        )
                    )
                """)

            if material_exclude_conditions:
                where.append("(" + " AND ".join(material_exclude_conditions) + ")")

        # Vendor INCLUDE: xf_vendor_name=value
        vendor_include = request.args.getlist("xf_vendor_name")
        if vendor_include:
            vendor_conditions = []
            vendor_values = []
            include_blank_vendor = False

            for value in vendor_include:
                value = (value or "").strip()
                if value == "__BLANK__":
                    include_blank_vendor = True
                elif value != "":
                    vendor_values.append(value)

            if vendor_values:
                placeholders = ", ".join(["%s"] * len(vendor_values))
                vendor_conditions.append(f"""
                    EXISTS (
                        SELECT 1
                        FROM job_card_process_days pd_vendor
                        WHERE pd_vendor.job_card_no = ji.job_card_no
                          AND LOWER(TRIM(pd_vendor.process_name)) = LOWER(TRIM(ji.wip_status))
                          AND TRIM(COALESCE(pd_vendor.vendor_name, '')) IN ({placeholders})
                    )
                """)
                params.extend(vendor_values)

            if include_blank_vendor:
                vendor_conditions.append("""
                    NOT EXISTS (
                        SELECT 1
                        FROM job_card_process_days pd_vendor_blank
                        WHERE pd_vendor_blank.job_card_no = ji.job_card_no
                          AND LOWER(TRIM(pd_vendor_blank.process_name)) = LOWER(TRIM(ji.wip_status))
                          AND TRIM(COALESCE(pd_vendor_blank.vendor_name, '')) != ''
                    )
                """)

            if vendor_conditions:
                where.append("(" + " OR ".join(vendor_conditions) + ")")

        # Vendor EXCLUDE: xfn_vendor_name=value
        vendor_exclude = request.args.getlist("xfn_vendor_name")
        if vendor_exclude:
            vendor_exclude_conditions = []
            vendor_exclude_values = []
            exclude_blank_vendor = False

            for value in vendor_exclude:
                value = (value or "").strip()
                if value == "__BLANK__":
                    exclude_blank_vendor = True
                elif value != "":
                    vendor_exclude_values.append(value)

            if vendor_exclude_values:
                placeholders = ", ".join(["%s"] * len(vendor_exclude_values))
                vendor_exclude_conditions.append(f"""
                    NOT EXISTS (
                        SELECT 1
                        FROM job_card_process_days pd_vendor_ex
                        WHERE pd_vendor_ex.job_card_no = ji.job_card_no
                          AND LOWER(TRIM(pd_vendor_ex.process_name)) = LOWER(TRIM(ji.wip_status))
                          AND TRIM(COALESCE(pd_vendor_ex.vendor_name, '')) IN ({placeholders})
                    )
                """)
                params.extend(vendor_exclude_values)

            if exclude_blank_vendor:
                vendor_exclude_conditions.append("""
                    EXISTS (
                        SELECT 1
                        FROM job_card_process_days pd_vendor_not_blank
                        WHERE pd_vendor_not_blank.job_card_no = ji.job_card_no
                          AND LOWER(TRIM(pd_vendor_not_blank.process_name)) = LOWER(TRIM(ji.wip_status))
                          AND TRIM(COALESCE(pd_vendor_not_blank.vendor_name, '')) != ''
                    )
                """)

            if vendor_exclude_conditions:
                where.append("(" + " AND ".join(vendor_exclude_conditions) + ")")
        # SPECIAL_FAST_FILTER_MATERIAL_VENDOR_END

        # Excel-like Last Updated time range filter.
        # Frontend will send time in 24-hour format from <input type="time">:
        # last_audit_time_from=13:00
        # last_audit_time_to=14:00
        last_audit_time_from = (request.args.get(
            "last_audit_time_from") or "").strip()
        last_audit_time_to = (request.args.get(
            "last_audit_time_to") or "").strip()

        latest_audit_changed_at_expr = """
            (
                SELECT at_time.changed_at
                FROM audit_trail at_time
                WHERE at_time.job_card_no = ji.job_card_no
                  AND at_time.item_name   = ji.item_name
                ORDER BY at_time.changed_at DESC
                LIMIT 1
            )
        """

        if last_audit_time_from:
            where.append(f"TIME({latest_audit_changed_at_expr}) >= %s")
            params.append(last_audit_time_from)

        if last_audit_time_to:
            where.append(f"TIME({latest_audit_changed_at_expr}) <= %s")
            params.append(last_audit_time_to)
        color_filter_conditions = {
            "urgent": "COALESCE(ji.is_priority, 0) = 1",
            "active_wip": """
                COALESCE(TRIM(ji.wip_status), '') != ''
                AND LOWER(TRIM(ji.wip_status)) NOT IN ('pending', 'store', 'completed', 'complete')
                AND COALESCE(pd_current.is_subcontract, 0) = 0
                AND COALESCE(TRIM(pd_current.vendor_name), '') = ''
            """,
            "completed": """
                jc.final_status = 'Completed'
                OR LOWER(TRIM(ji.wip_status)) = 'store'
            """,
            "pending": """
                jc.final_status = 'Pending'
                OR LOWER(TRIM(ji.wip_status)) = 'pending'
            """,
            "subcontract": """
                COALESCE(pd_current.is_subcontract, 0) = 1
                OR COALESCE(TRIM(pd_current.vendor_name), '') != ''
            """,
            "overdue": """
                ji.delivery_date IS NOT NULL
                AND ji.delivery_date < CURDATE()
                AND jc.final_status != 'Completed'
            """,
            "normal": """
                COALESCE(ji.is_priority, 0) = 0
                AND NOT (
                    ji.delivery_date IS NOT NULL
                    AND ji.delivery_date < CURDATE()
                    AND jc.final_status != 'Completed'
                )
                AND COALESCE(pd_current.is_subcontract, 0) = 0
                AND COALESCE(TRIM(pd_current.vendor_name), '') = ''
                AND jc.final_status != 'Completed'
                AND LOWER(TRIM(ji.wip_status)) != 'store'
            """,
        }
        selected_colors = [
            color.strip()
            for color in request.args.getlist("xf_color")
            if color and color.strip() in color_filter_conditions
        ]
        if selected_colors:
            where.append("(" + " OR ".join(
                f"({color_filter_conditions[color]})"
                for color in selected_colors
            ) + ")")

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
        if supervisor_user_id:
            if role != "admin" and not is_gaurang_special_user():
                return jsonify({"success": False, "error": "Admin access required for supervisor filter"}), 403
            try:
                selected_supervisor_user_id = int(supervisor_user_id)
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid supervisor selected"}), 400
            where.append("""
                EXISTS (
                    SELECT 1
                    FROM supervisor_process_access spa_filter
                    JOIN users u_filter
                      ON u_filter.id = spa_filter.user_id
                     AND u_filter.role = 'supervisor'
                     AND COALESCE(u_filter.is_active, 1) = 1
                    WHERE spa_filter.user_id = %s
                      AND LOWER(TRIM(spa_filter.process_name)) = LOWER(TRIM(ji.wip_status))
                )
            """)
            params.append(selected_supervisor_user_id)

        filter_date = request.args.get("filter_date", "").strip()

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
            if session.get("role") == "supervisor" and not is_gaurang_special_user():
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
            if session.get("role") == "supervisor" and not is_gaurang_special_user():
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
        if urgent_only == "yes" and can_see_priority_column:
            where.append("ji.is_priority = 1")

        if filter_date:
            where.append("jc.created_at >= %s AND jc.created_at < DATE_ADD(%s, INTERVAL 1 DAY)")
            params.extend([filter_date, filter_date])

        # Vipul Valand (user_id 27): Purchase RM-only restricted view
        if user_id == 27:
            where.append("LOWER(TRIM(ji.wip_status)) = 'raw material'")
            where.append(
                "LOWER(TRIM(COALESCE(ji.rm_hold_reason, ''))) IN ('testing', 'shortage')"
            )

        where_sql = " AND ".join(where)

        # DEFAULT_ALL_RECORDS_FAST_PATH_START
        # Fast path for normal PPC opening:
        # no date filter, no search, no advanced filters, default sorting.
        has_excel_filters = (
            any(
                request.args.getlist(f"xf_{key}")
                or request.args.getlist(f"xfn_{key}")
                for key in excel_filter_columns
            )
            or bool(
                request.args.getlist("xf_waiting_for_jc")
            )
        )
        has_color_filters = bool(request.args.getlist("xf_color"))
        has_time_filter = bool(last_audit_time_from or last_audit_time_to)

        wip_filter_values = request.args.getlist("xf_wip_status") + request.args.getlist("xfn_wip_status")
        has_subcontract_wip_filter = any(
            str(v).strip().lower() == "subcontract" for v in wip_filter_values
        )

        has_vendor_filter = bool(
            request.args.getlist("xf_vendor_name") or request.args.getlist("xfn_vendor_name")
        )

        # Normal Excel filters like JC No, Material, SO, Customer, Item, etc. can use fast path.
        # Heavy/special filters still use old full logic.
        has_unsupported_fast_filter = bool(
            search or wip or status or date_from or date_to or supervisor_user_id
            or filter_date or delivery_from or delivery_to or overdue or subcontracting or urgent_only
            or has_color_filters or has_time_filter or has_subcontract_wip_filter
        )

        # Allow fast path for normal filter-menu sorting also.
        # Only vendor_name sort is excluded because it needs pd_current join.
        fast_sort_supported = sort_col not in ("vendor_name", "pd_current.vendor_name")

        if sort_col in ("", "created_at", "jc.created_at"):
            fast_order_sql = f"{priority_order_sql}jc.created_at DESC"
        else:
            # Filter-menu sorting should be pure A-Z / Z-A.
            # Keep blank values at bottom for both ASC and DESC.
            fast_order_sql = f"""
                CASE
                    WHEN COALESCE(CAST(({order_expr}) AS CHAR), '') = '' THEN 1
                    ELSE 0
                END ASC,
                {order_expr} {sort_dir}
            """

        if not has_unsupported_fast_filter and fast_sort_supported:
            cursor.execute(f"""
                SELECT COUNT(*) AS total
                FROM job_cards jc
                JOIN job_card_items ji ON jc.job_card_no = ji.job_card_no
                WHERE {where_sql}
            """, params)
            total = cursor.fetchone()["total"]

            cursor.execute("""
                SELECT DISTINCT wip_status
                FROM job_card_items
                WHERE wip_status IS NOT NULL
                  AND COALESCE(is_deleted, 0) = 0
                ORDER BY wip_status
            """)
            wip_options = [r["wip_status"] for r in cursor.fetchall()]

            cursor.execute(
                "SELECT DISTINCT final_status FROM job_cards WHERE final_status IS NOT NULL ORDER BY final_status"
            )
            status_options = [r["final_status"] for r in cursor.fetchall()]

            supervisor_options = []
            if role == "admin" or is_gaurang_special_user():
                cursor.execute("""
                    SELECT id, username, COALESCE(full_name, '') AS full_name
                    FROM users
                    WHERE role = 'supervisor'
                      AND COALESCE(is_active, 1) = 1
                    ORDER BY username
                """)
                supervisor_options = cursor.fetchall()

            cursor.execute(f"""
                SELECT
                    ji.id AS item_id,
                    jc.job_card_no,
                    jc.so_no,
                    jc.customer_name,
                    jc.work_order_no,
                    ji.is_priority,
                    jc.parent_code,
                    jc.child_code,
                    jc.assembly_name,
                    jc.so_date,
                    jc.job_card_date,
                    CASE
                        WHEN jc.final_status = 'Completed'
                          OR LOWER(TRIM(ji.wip_status)) = 'store'
                        THEN 'Completed'
                        ELSE jc.final_status
                    END AS final_status,
                    jc.erp_status,
                    ji.item_name,
                    ji.size,
                    COALESCE(NULLIF(ji.material, ''), '') AS material,
                    ji.so_qty,
                    ji.actual_qty,
                    ji.wip_status,
                    COALESCE(ji.rm_hold_reason, '') AS rm_hold_reason,
                    ji.total_days,
                    DATEDIFF(ji.delivery_date, CURDATE()) AS remaining_days,

                    0 AS is_subcontract,

                    '' AS vendor_name,

                    COALESCE(ji.wip_stage_days, 0) AS wip_stage_days,

                    ji.delivery_date,
                    ji.remarks,
                    jc.created_at,

                    CASE
                        WHEN ji.delivery_date IS NOT NULL
                         AND ji.delivery_date < CURDATE()
                         AND jc.final_status != 'Completed'
                        THEN DATEDIFF(CURDATE(), ji.delivery_date)
                        ELSE 0
                    END AS days_overdue,

                    NULL AS last_audit

                FROM (
                    SELECT ji.id AS item_id
                    FROM job_cards jc
                    JOIN job_card_items ji ON jc.job_card_no = ji.job_card_no
                    WHERE {where_sql}
                    ORDER BY {fast_order_sql}
                    LIMIT %s OFFSET %s
                ) page_rows
                JOIN job_card_items ji ON ji.id = page_rows.item_id
                JOIN job_cards jc ON jc.job_card_no = ji.job_card_no
                ORDER BY {fast_order_sql}
            """, params + [per_page, offset])

            rows = cursor.fetchall()

            # PAGE5_BULK_ENRICH_FAST_PATH_START
            # Bulk-fill material, subcontract/vendor, WIP days, and last audit for current page rows.
            # This avoids per-row correlated subqueries and makes response time scale much better.
            if rows:
                from datetime import date

                def _norm_page5_text(value):
                    return " ".join(str(value or "").strip().split()).lower()

                page_job_cards = sorted({
                    str(r.get("job_card_no") or "").strip()
                    for r in rows
                    if str(r.get("job_card_no") or "").strip()
                })

                page_child_codes = sorted({
                    str(r.get("child_code") or "").strip()
                    for r in rows
                    if str(r.get("child_code") or "").strip()
                })

                # Bulk material fallback from BOM raw material.
                raw_material_map = {}
                if page_child_codes:
                    placeholders = ", ".join(["%s"] * len(page_child_codes))
                    cursor.execute(f"""
                        SELECT
                            bl.parent_code,
                            GROUP_CONCAT(DISTINCT i.item_description ORDER BY i.item_description SEPARATOR ' / ') AS material
                        FROM bom_links bl
                        JOIN items i
                          ON i.item_code COLLATE utf8mb4_unicode_ci = bl.child_code COLLATE utf8mb4_unicode_ci
                        WHERE bl.parent_code IN ({placeholders})
                          AND bl.make_buy = 'I'
                          AND COALESCE(bl.is_alternate, 0) = 0
                        GROUP BY bl.parent_code
                    """, page_child_codes)

                    raw_material_map = {
                        str(x.get("parent_code") or "").strip(): x.get("material") or ""
                        for x in cursor.fetchall()
                    }

                # Bulk current process details.
                process_map = {}
                if page_job_cards:
                    placeholders = ", ".join(["%s"] * len(page_job_cards))
                    cursor.execute(f"""
                        SELECT
                            job_card_no,
                            process_name,
                            is_subcontract,
                            vendor_name,
                            in_time,
                            out_time,
                            is_completed
                        FROM job_card_process_days
                        WHERE job_card_no IN ({placeholders})
                    """, page_job_cards)

                    for p in cursor.fetchall():
                        key = (
                            str(p.get("job_card_no") or "").strip(),
                            _norm_page5_text(p.get("process_name"))
                        )
                        if key not in process_map:
                            process_map[key] = p

                # Bulk latest audit.
                audit_map = {}
                if page_job_cards:
                    placeholders = ", ".join(["%s"] * len(page_job_cards))
                    cursor.execute(f"""
                        SELECT
                            job_card_no,
                            item_name,
                            old_stage,
                            new_stage,
                            changed_by,
                            changed_at
                        FROM audit_trail
                        WHERE job_card_no IN ({placeholders})
                        ORDER BY changed_at DESC, id DESC
                    """, page_job_cards)

                    for a in cursor.fetchall():
                        key = (
                            str(a.get("job_card_no") or "").strip(),
                            str(a.get("item_name") or "").strip()
                        )
                        if key in audit_map:
                            continue

                        changed_at = a.get("changed_at")
                        if changed_at and hasattr(changed_at, "strftime"):
                            changed_at_text = changed_at.strftime("%d %b %Y %I:%M %p")
                        else:
                            changed_at_text = str(changed_at or "|")

                        audit_map[key] = (
                            f"{a.get('changed_by') or '|'} | "
                            f"{changed_at_text} | "
                            f"{a.get('old_stage') or '|'} | "
                            f"{a.get('new_stage') or '|'}"
                        )

                today = date.today()

                for r in rows:
                    child_code = str(r.get("child_code") or "").strip()
                    if not str(r.get("material") or "").strip():
                        r["material"] = raw_material_map.get(child_code, "")

                    pd_key = (
                        str(r.get("job_card_no") or "").strip(),
                        _norm_page5_text(r.get("wip_status"))
                    )
                    pd = process_map.get(pd_key)

                    if pd:
                        r["is_subcontract"] = int(pd.get("is_subcontract") or 0)
                        r["vendor_name"] = pd.get("vendor_name") or ""

                        in_time = pd.get("in_time")
                        out_time = pd.get("out_time")
                        is_completed = int(pd.get("is_completed") or 0)

                        if in_time and not out_time and is_completed == 0:
                            in_date = in_time.date() if hasattr(in_time, "date") else None
                            if in_date:
                                is_rm_shortage = (
                                    str(r.get("wip_status") or "").strip().lower() == "raw material"
                                    and str(r.get("rm_hold_reason") or "").strip().lower() == "shortage"
                                )
                                r["wip_stage_days"] = (
                                    0 if is_rm_shortage
                                    else max(0, (today - in_date).days)
                                )

                    audit_key = (
                        str(r.get("job_card_no") or "").strip(),
                        str(r.get("item_name") or "").strip()
                    )
                    r["last_audit"] = audit_map.get(audit_key)
            # PAGE5_BULK_ENRICH_FAST_PATH_END

            for r in rows:
                for f in ("so_date", "job_card_date", "delivery_date"):
                    if r.get(f) and hasattr(r[f], "strftime"):
                        r[f] = r[f].strftime("%Y-%m-%d")
                if r.get("created_at"):
                    r["created_at"] = _to_ist(r["created_at"]).strftime("%Y-%m-%d %H:%M")

            for r in rows:
                r["remaining_days"] = calculate_remaining_days_from_delivery(r.get("delivery_date"))
                r["total_default_days_calc"] = 0
                r["used_process_days_calc"] = 0
                r["can_edit_current_process"] = session.get("role") == "admin" or is_gaurang_special_user()
                r["page5_editable_fields"] = []

            if role == "admin" or is_gaurang_special_user():
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

            if not can_see_priority_column:
                for r in rows:
                    r.pop("is_priority", None)

            cursor.execute("""
                SELECT DISTINCT work_order_no FROM job_cards
                WHERE work_order_no IS NOT NULL AND TRIM(work_order_no) != ''
                ORDER BY work_order_no
            """)
            wo_options = [r["work_order_no"] for r in cursor.fetchall()]

            if include_dependencies:
                _enrich_page5_dependency_rows(cursor, rows)

            cursor.close()
            conn.close()

            return jsonify({
                "success": True,
                "data": rows,
                "total": total,
                "page": page,
                "per_page": per_page,
                "wip_options": wip_options,
                "can_see_priority_column": can_see_priority_column,
            "can_see_rm_status": (
                session.get("role") == "admin"
                or session.get("user_id") in (5, 27)
            ),
                "status_options": status_options,
                "supervisor_options": supervisor_options,
                "wo_options": wo_options,
            })
        # DEFAULT_ALL_RECORDS_FAST_PATH_END

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

        cursor.execute("""
            SELECT DISTINCT wip_status
            FROM job_card_items
            WHERE wip_status IS NOT NULL
              AND COALESCE(is_deleted, 0) = 0
            ORDER BY wip_status
        """)
        wip_options = [r["wip_status"] for r in cursor.fetchall()]

        cursor.execute(
            "SELECT DISTINCT final_status FROM job_cards WHERE final_status IS NOT NULL ORDER BY final_status")
        status_options = [r["final_status"] for r in cursor.fetchall()]

        supervisor_options = []
        if role == "admin" or is_gaurang_special_user():
            cursor.execute("""
                SELECT id, username, COALESCE(full_name, '') AS full_name
                FROM users
                WHERE role = 'supervisor'
                  AND COALESCE(is_active, 1) = 1
                ORDER BY username
            """)
            supervisor_options = cursor.fetchall()

        # Main query — no process_master join (removed: was the source of a
        # 4-second-per-request correlated subquery scanning process_master
        # once per row). next_process is no longer calculated here; it was
        # a minor convenience field not essential to this table view.
        cursor.execute(f"""
            SELECT DISTINCT ji.id AS item_id,
                   jc.job_card_no, jc.so_no, jc.customer_name, jc.work_order_no, ji.is_priority,
                   jc.parent_code, jc.child_code, jc.assembly_name,
                   jc.so_date, jc.job_card_date,
                   CASE WHEN jc.final_status = 'Completed'
                             OR LOWER(TRIM(ji.wip_status)) = 'store'
                        THEN 'Completed' ELSE jc.final_status
                   END AS final_status,
                   jc.erp_status,
                   ji.item_name, ji.size,
                   COALESCE(
                       NULLIF(ji.material, ''),
                       (
                           SELECT GROUP_CONCAT(DISTINCT i2.item_description ORDER BY i2.item_description SEPARATOR ' / ')
                           FROM bom_links bl2
                           JOIN items i2 
                             ON i2.item_code COLLATE utf8mb4_unicode_ci = bl2.child_code COLLATE utf8mb4_unicode_ci
                           WHERE bl2.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                             AND bl2.make_buy = 'I'
                             AND bl2.is_alternate = 0
                       ),
                       ''
                   ) AS material, ji.so_qty, ji.actual_qty,
                   ji.wip_status,
                   COALESCE(ji.rm_hold_reason, '') AS rm_hold_reason,
                   ji.total_days,
                   DATEDIFF(ji.delivery_date, CURDATE()) AS remaining_days,
                   COALESCE(pd_current.is_subcontract, 0) AS is_subcontract,
                   COALESCE(pd_current.vendor_name, '') AS vendor_name,
                   CASE
                       WHEN LOWER(TRIM(ji.wip_status)) = 'raw material'
                        AND LOWER(TRIM(COALESCE(ji.rm_hold_reason, ''))) = 'shortage'
                       THEN 0
                       ELSE COALESCE(
                           (SELECT GREATEST(0, DATEDIFF(CURDATE(), pd3.in_time))
                            FROM job_card_process_days pd3
                            WHERE pd3.job_card_no = ji.job_card_no
                              AND LOWER(TRIM(pd3.process_name)) = LOWER(TRIM(ji.wip_status))
                              AND pd3.in_time IS NOT NULL
                              AND pd3.out_time IS NULL
                            LIMIT 1),
                           ji.wip_stage_days, 0
                       )
                   END AS wip_stage_days,
                   ji.delivery_date, ji.remarks, jc.created_at,
                   CASE
                     WHEN ji.delivery_date IS NOT NULL AND ji.delivery_date < CURDATE()
                          AND jc.final_status != 'Completed'
                     THEN DATEDIFF(CURDATE(), ji.delivery_date)
                     ELSE 0
                   END AS days_overdue,
                   (SELECT CONCAT(
            COALESCE(at.changed_by, '|'), ' • ',
            DATE_FORMAT(at.changed_at, '%d %b %Y %h:%i %p'), ' • ',
            COALESCE(at.old_stage, '|'), ' → ', COALESCE(at.new_stage, '|')
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
            ORDER BY {priority_order_sql}{order_expr} {sort_dir}
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        rows = cursor.fetchall()
        for r in rows:
            for f in ("so_date", "job_card_date", "delivery_date"):
                if r.get(f) and hasattr(r[f], "strftime"):
                    r[f] = r[f].strftime("%Y-%m-%d")
            if r.get("created_at"):
                r["created_at"] = _to_ist(
                    r["created_at"]).strftime("%Y-%m-%d %H:%M")

        for r in rows:
            r["remaining_days"] = calculate_remaining_days_from_delivery(
                r.get("delivery_date"))
            r["total_default_days_calc"] = 0
            r["used_process_days_calc"] = 0
            r["can_edit_current_process"] = session.get(
                "role") == "admin" or is_gaurang_special_user()
            r["page5_editable_fields"] = []

        if role == "admin" or is_gaurang_special_user():
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

        if not can_see_priority_column:
            for r in rows:
                r.pop("is_priority", None)

        cursor.execute("""
            SELECT DISTINCT work_order_no FROM job_cards
            WHERE work_order_no IS NOT NULL AND TRIM(work_order_no) != ''
            ORDER BY work_order_no
        """)
        wo_options = [r["work_order_no"] for r in cursor.fetchall()]

        if include_dependencies:
            _enrich_page5_dependency_rows(cursor, rows)

        cursor.close()
        conn.close()

        return jsonify({
            "success": True, "data": rows,
            "total": total, "page": page, "per_page": per_page,
            "wip_options": wip_options, "status_options": status_options,
            "supervisor_options": supervisor_options,
            "can_see_priority_column": can_see_priority_column,
            "wo_options": wo_options,
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
        ensure_permission_tables(cursor)
        if not can_user_edit_field(cursor, session.get("role"), session.get("user_id"), PAGE5_PPC, "is_priority"):
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "You do not have permission to update priority"}), 403

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


@data_view_bp.route("/api/job_card_item/soft_delete", methods=["POST"])
def soft_delete_job_card_item():
    """
    Hard delete full job card from all connected tables.
    Route name kept same so existing frontend delete button keeps working.
    """
    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()

        if role != "admin" and not is_gaurang_special_user():
            return jsonify({
                "success": False,
                "error": "You do not have permission to delete job cards."
            }), 403

        data = request.json or {}
        item_id = data.get("item_id")
        job_card_no = (data.get("job_card_no") or "").strip()
        item_name = (data.get("item_name") or "").strip()

        if not item_id and not job_card_no:
            return jsonify({
                "success": False,
                "error": "item_id or job_card_no is required"
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        def table_exists(table_name):
            cursor.execute("""
                SELECT COUNT(*) AS cnt
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
            """, (table_name,))
            row = cursor.fetchone()
            return int(row["cnt"] or 0) > 0

        # If only item_id came from frontend, find job_card_no from item row
        if item_id and not job_card_no:
            cursor.execute("""
                SELECT job_card_no
                FROM job_card_items
                WHERE id = %s
                LIMIT 1
            """, (item_id,))
            item = cursor.fetchone()

            if not item:
                return jsonify({
                    "success": False,
                    "error": "Job card item not found"
                }), 404

            job_card_no = (item.get("job_card_no") or "").strip()

        if not job_card_no:
            return jsonify({
                "success": False,
                "error": "Job Card No not found"
            }), 400

        # Confirm parent job card exists
        cursor.execute("""
            SELECT job_card_no
            FROM job_cards
            WHERE job_card_no = %s
            LIMIT 1
        """, (job_card_no,))
        jc = cursor.fetchone()

        if not jc:
            return jsonify({
                "success": False,
                "error": f"Job Card {job_card_no} not found"
            }), 404

        deleted_counts = {}

        # 1) quality_check_details depends on quality_checks
        if table_exists("quality_check_details") and table_exists("quality_checks"):
            cursor.execute("""
                DELETE qcd
                FROM quality_check_details qcd
                JOIN quality_checks qc ON qc.id = qcd.quality_check_id
                WHERE qc.job_card_no = %s
            """, (job_card_no,))
            deleted_counts["quality_check_details"] = cursor.rowcount

        # 2) quality_checks
        if table_exists("quality_checks"):
            cursor.execute("""
                DELETE FROM quality_checks
                WHERE job_card_no = %s
            """, (job_card_no,))
            deleted_counts["quality_checks"] = cursor.rowcount

        # 3) audit_trail
        if table_exists("audit_trail"):
            cursor.execute("""
                DELETE FROM audit_trail
                WHERE job_card_no = %s
            """, (job_card_no,))
            deleted_counts["audit_trail"] = cursor.rowcount

        # 4) stage_qty_log
        if table_exists("stage_qty_log"):
            cursor.execute("""
                DELETE FROM stage_qty_log
                WHERE job_card_no = %s
            """, (job_card_no,))
            deleted_counts["stage_qty_log"] = cursor.rowcount

        # 5) job_card_process_days
        if table_exists("job_card_process_days"):
            cursor.execute("""
                DELETE FROM job_card_process_days
                WHERE job_card_no = %s
            """, (job_card_no,))
            deleted_counts["job_card_process_days"] = cursor.rowcount

        # 6) job_card_items
        if table_exists("job_card_items"):
            cursor.execute("""
                DELETE FROM job_card_items
                WHERE job_card_no = %s
            """, (job_card_no,))
            deleted_counts["job_card_items"] = cursor.rowcount

        # 7) parent job_cards last
        cursor.execute("""
            DELETE FROM job_cards
            WHERE job_card_no = %s
        """, (job_card_no,))
        deleted_counts["job_cards"] = cursor.rowcount

        conn.commit()

        return jsonify({
            "success": True,
            "message": f"Job Card {job_card_no} permanently deleted",
            "deleted_counts": deleted_counts
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
                r["checked_at"] = _to_ist(
                    r["checked_at"]).strftime("%Y-%m-%d %H:%M")

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
                r["changed_at"] = _to_ist(
                    r["changed_at"]).strftime("%Y-%m-%d %H:%M")

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
                r["changed_at"] = _to_ist(
                    r["changed_at"]).strftime("%Y-%m-%d %H:%M")
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
                        WHEN jpd2.in_time IS NULL AND jpd2.out_time IS NULL THEN 'Pending'
                        WHEN jpd2.in_time IS NOT NULL AND jpd2.out_time IS NULL
                             AND COALESCE(jpd2.vendor_name, '') != '' THEN 'Subcontracting'
                        WHEN jpd2.in_time IS NOT NULL AND jpd2.out_time IS NULL THEN 'In Progress'
                        WHEN jpd2.in_time IS NOT NULL
                             AND jpd2.out_time IS NOT NULL
                             AND COALESCE(
                                   jpd2.actual_days,
                                   DATEDIFF(DATE(jpd2.out_time), DATE(jpd2.in_time)),
                                   0
                                 ) > COALESCE(
                                   (SELECT pdd2.default_days
                                    FROM process_default_days pdd2
                                    WHERE LOWER(TRIM(pdd2.process_name)) = LOWER(TRIM(jpd2.process_name))
                                    LIMIT 1),
                                   jpd2.days,
                                   0
                                 )
                        THEN 'Delayed'
                        WHEN jpd2.in_time IS NOT NULL AND jpd2.out_time IS NOT NULL THEN 'On Time'
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
                    THEN CONCAT(DATEDIFF(CURDATE(), DATE(pd.in_time)), 'd')

                    WHEN pd.actual_days IS NOT NULL
                    THEN CONCAT(pd.actual_days, 'd')

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NOT NULL
                    THEN CONCAT(DATEDIFF(DATE(pd.out_time), DATE(pd.in_time)), 'd')

                    ELSE '0d'
                END AS days_taken_display,

                CASE
                    WHEN pd.in_time IS NULL
                         AND pd.out_time IS NULL
                    THEN 'Pending'

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NULL
                    THEN 'In Progress'

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NOT NULL
                         AND COALESCE(
                               pd.actual_days,
                               DATEDIFF(DATE(pd.out_time), DATE(pd.in_time)),
                               0
                             ) > COALESCE(pdd.default_days, pd.days, 0)
                    THEN 'Delayed'

                    WHEN pd.in_time IS NOT NULL
                         AND pd.out_time IS NOT NULL
                    THEN 'On Time'

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
                    "process_in_time_map": {},
                    "process_out_time_map": {},
                    "process_actual_days_map": {},
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
                grouped[jcn]["process_in_time_map"][proc] = r.get(
                    "in_time") or ""
                grouped[jcn]["process_out_time_map"][proc] = r.get(
                    "out_time") or ""
                grouped[jcn]["process_actual_days_map"][proc] = r.get(
                    "actual_days")

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

              AND NOT EXISTS (
              SELECT 1
              FROM bom_links bl_gate
              JOIN items c_item_gate
                ON c_item_gate.item_code COLLATE utf8mb4_unicode_ci = bl_gate.child_code COLLATE utf8mb4_unicode_ci
                   AND TRIM(c_item_gate.item_description) REGEXP '[[:space:]]-[[:space:]]*C$'
              JOIN job_cards c_jc_gate
                ON c_jc_gate.child_code COLLATE utf8mb4_unicode_ci = c_item_gate.item_code COLLATE utf8mb4_unicode_ci
                   AND COALESCE(NULLIF(TRIM(c_jc_gate.so_no), ''), '__BLANK_SO__') COLLATE utf8mb4_unicode_ci
                 = COALESCE(NULLIF(TRIM(jc.so_no), ''), '__BLANK_SO__') COLLATE utf8mb4_unicode_ci
              JOIN job_card_items c_ji_gate
                ON c_ji_gate.job_card_no = c_jc_gate.job_card_no
              WHERE bl_gate.parent_code COLLATE utf8mb4_unicode_ci = jc.child_code COLLATE utf8mb4_unicode_ci
                    AND bl_gate.make_buy = 'A'
                    AND COALESCE(c_ji_gate.is_deleted, 0) = 0
                    AND NOT (
                    c_jc_gate.final_status = 'Completed'
                    OR LOWER(TRIM(c_ji_gate.wip_status)) IN ('store', 'completed', 'complete')
                )
          )

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



def _get_c_gate_blocked_l1_job_cards(cursor):
    """
    Fast version:
    Returns L1 job cards already started while direct -C child job card exists but is not completed.
    Uses simple SELECTs + Python maps instead of one heavy REGEXP/JOIN query.
    """
    import re
    from collections import defaultdict

    def norm_so(value):
        value = str(value or "").strip()
        if value == "" or value == "-":
            return "__BLANK_SO__"
        return value.lower()

    def is_completed(final_status, wip_status):
        fs = str(final_status or "").strip().lower()
        ws = str(wip_status or "").strip().lower()
        return fs == "completed" or ws in ("store", "completed", "complete")

    # 1) Direct -C child mapping from BOM
    cursor.execute("""
        SELECT
            bl.parent_code,
            bl.child_code,
            ci.item_description AS child_description
        FROM bom_links bl
        JOIN items ci
            ON ci.item_code COLLATE utf8mb4_unicode_ci = bl.child_code COLLATE utf8mb4_unicode_ci
        WHERE bl.make_buy = 'A'
          AND (
                UPPER(TRIM(ci.item_description)) LIKE '%- C'
             OR UPPER(TRIM(ci.item_description)) LIKE '%-C'
          )
    """)

    parent_to_c_codes = defaultdict(set)

    for r in cursor.fetchall():
        parent_code = str(r.get("parent_code") or "").strip()
        child_code = str(r.get("child_code") or "").strip()
        desc = str(r.get("child_description") or "").strip()

        if not parent_code or not child_code:
            continue

        if re.search(r"\s-\s*C$", desc, re.IGNORECASE) or desc.upper().endswith("-C"):
            parent_to_c_codes[parent_code].add(child_code)

    if not parent_to_c_codes:
        return set()

    # 2) Started L1 job cards only
    cursor.execute("""
        SELECT DISTINCT
            jc.job_card_no,
            jc.so_no,
            jc.child_code
        FROM job_cards jc
        JOIN job_card_items ji
            ON ji.job_card_no = jc.job_card_no
           AND COALESCE(ji.is_deleted, 0) = 0
        JOIN job_card_process_days pd
            ON pd.job_card_no = jc.job_card_no
           AND pd.in_time IS NOT NULL
        WHERE COALESCE(jc.final_status, '') != 'Completed'
          AND COALESCE(TRIM(jc.child_code), '') != ''
    """)

    started_l1_rows = cursor.fetchall()

    expected_c_codes = set()

    for r in started_l1_rows:
        l1_child_code = str(r.get("child_code") or "").strip()
        expected_c_codes.update(parent_to_c_codes.get(l1_child_code, set()))

    if not expected_c_codes:
        return set()

    # 3) Child -C job cards by child_code and SO
    expected_c_codes = sorted(expected_c_codes)
    placeholders = ", ".join(["%s"] * len(expected_c_codes))

    cursor.execute(f"""
        SELECT
            jc.job_card_no,
            jc.so_no,
            jc.child_code,
            jc.final_status,
            ji.wip_status
        FROM job_cards jc
        JOIN job_card_items ji
            ON ji.job_card_no = jc.job_card_no
           AND COALESCE(ji.is_deleted, 0) = 0
        WHERE jc.child_code IN ({placeholders})
    """, expected_c_codes)

    child_job_map = defaultdict(list)

    for r in cursor.fetchall():
        key = (
            norm_so(r.get("so_no")),
            str(r.get("child_code") or "").strip()
        )
        child_job_map[key].append(r)

    # 4) Find started L1 whose direct -C child exists but is pending
    blocked = set()

    for l1 in started_l1_rows:
        l1_jc = str(l1.get("job_card_no") or "").strip()
        l1_so = norm_so(l1.get("so_no"))
        l1_child_code = str(l1.get("child_code") or "").strip()

        for c_code in parent_to_c_codes.get(l1_child_code, set()):
            child_rows = child_job_map.get((l1_so, c_code), [])

            for c in child_rows:
                if not is_completed(c.get("final_status"), c.get("wip_status")):
                    blocked.add(l1_jc)
                    break

            if l1_jc in blocked:
                break

    return blocked

def _fetch_overdue_processes(cursor):
    role = (session.get("role") or "").strip().lower()
    user_id = session.get("user_id")

    blocked_l1_jcs = _get_c_gate_blocked_l1_job_cards(cursor)

    access_join = ""
    params = []

    if role == "supervisor" and not is_gaurang_special_user():
        access_join = """
            JOIN supervisor_process_access spa
              ON spa.user_id = %s
             AND LOWER(TRIM(spa.process_name)) = LOWER(TRIM(pd.process_name))
        """
        params.append(user_id)

    blocked_sql = ""
    if blocked_l1_jcs:
        blocked_placeholders = ", ".join(["%s"] * len(blocked_l1_jcs))
        blocked_sql = f"AND pd.job_card_no NOT IN ({blocked_placeholders})"
        params.extend(sorted(blocked_l1_jcs))

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
        JOIN job_cards jc
            ON jc.job_card_no = pd.job_card_no
        JOIN job_card_items ji
            ON ji.job_card_no = pd.job_card_no
        LEFT JOIN process_default_days pdd
            ON LOWER(TRIM(pdd.process_name)) = LOWER(TRIM(pd.process_name))
        {access_join}
        WHERE pd.in_time IS NOT NULL
          AND pd.out_time IS NULL
          AND COALESCE(pd.is_completed, 0) = 0
          AND COALESCE(pdd.default_days, pd.days, 0) > 0
          AND DATEDIFF(CURDATE(), pd.in_time) > COALESCE(pdd.default_days, pd.days, 0)
          AND IFNULL(jc.final_status, '') != 'Completed'
          AND COALESCE(ji.is_deleted, 0) = 0
          {blocked_sql}
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
                    ji.job_card_no,
                    CASE
                        WHEN LOWER(TRIM(ji.wip_status)) IN ('store', 'completed')
                             OR EXISTS (
                                 SELECT 1
                                 FROM job_card_process_days jpd
                                 WHERE jpd.job_card_no = ji.job_card_no
                                   AND LOWER(TRIM(jpd.process_name)) = 'store'
                                   AND jpd.is_completed = 1
                             )
                        THEN 1
                        ELSE 0
                    END AS is_completed
                FROM job_card_items ji
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
        if role not in ("admin", "supervisor") and not is_gaurang_special_user():
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

        if role == "supervisor" and not is_gaurang_special_user():
            forbidden = []
            for key in data.keys():
                if key in SUPERVISOR_UPDATE_IDENTIFIERS:
                    continue
                if key == "is_subcontract" and (
                    field_allowed("vendor_name") or field_allowed(
                        "subcontractor_name")
                ):
                    continue
                if key in ("delivery_date", "dd_change_reason"):
                    continue  # these have their own Dispatch check below
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
            or is_gaurang_special_user()
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

        if new_jc_no != original_jc_no:
            ensure_job_card_number_update_cascade(cursor)

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
                    UPDATE audit_trail
                    SET job_card_no = %s
                    WHERE job_card_no = %s
                """, (new_jc_no, original_jc_no))

        item_sets = []
        item_params = []

        if "item_name" in data and field_allowed("item_name"):
            item_sets.append("item_name = %s")
            item_params.append((data.get("item_name") or "").strip())
            updated_fields.append("item_name")
        print(
            f"DEBUG material: role={role}, in_data={'material' in data}, value={data.get('material')}, is_admin={role == 'admin'}, is_gaurang={is_gaurang_special_user()}")
        if "material" in data and (role == "admin" or is_gaurang_special_user() or field_allowed("material")):
            item_sets.append("material = %s")
            item_params.append((data.get("material") or "").strip())
            updated_fields.append("material")
        if "so_qty" in data and field_allowed("so_qty"):
            item_sets.append("so_qty = %s")
            item_params.append(parse_optional_int(
                data.get("so_qty"), "SO Qty") or 0)
            updated_fields.append("so_qty")

        if "actual_qty" in data and field_allowed("actual_qty"):
            if role == "supervisor" and not is_gaurang_special_user() and not has_current_process_access:
                return jsonify({
                    "success": False,
                    "error": f"You do not have rights to update process: {current_process}"
                }), 403
            item_sets.append("actual_qty = %s")
            item_params.append(parse_optional_int(
                data.get("actual_qty"), "Actual Qty"))
            updated_fields.append("actual_qty")
        if "remarks" in data and field_allowed("remarks"):
            if role == "supervisor" and not is_gaurang_special_user() and not has_current_process_access:
                return jsonify({
                    "success": False,
                    "error": f"You do not have rights to update process: {current_process}"
                }), 403
            item_sets.append("remarks = %s")
            item_params.append((data.get("remarks") or "").strip())
            updated_fields.append("remarks")
        if "delivery_date" in data:
            # Only Admin or Dispatch supervisor can change delivery date
            is_dispatch = False
            if role == "admin":
                is_dispatch = True
            elif role == "supervisor":
                cursor.execute("""
                    SELECT 1 FROM supervisor_process_access
                    WHERE user_id = %s
                      AND LOWER(TRIM(process_name)) = 'dispatch'
                    LIMIT 1
                """, (session.get("user_id"),))
                is_dispatch = cursor.fetchone() is not None

            if not is_dispatch:
                return jsonify({
                    "success": False,
                    "error": "Only Dispatch department can change the delivery date."
                }), 403

            new_delivery = (data.get("delivery_date") or "").strip()
            if new_delivery:
                cursor.execute("""
                    SELECT delivery_date FROM job_card_items
                    WHERE job_card_no = %s AND TRIM(item_name) = TRIM(%s)
                    LIMIT 1
                """, (original_jc_no, original_item_name))
                old_dd_row = cursor.fetchone()
                old_delivery = str(
                    old_dd_row["delivery_date"]) if old_dd_row and old_dd_row["delivery_date"] else None
                dd_reason = (data.get("dd_change_reason") or "").strip()

                item_sets.append("delivery_date = %s")
                item_params.append(new_delivery)
                item_sets.append("remaining_days = DATEDIFF(%s, CURDATE())")
                item_params.append(new_delivery)
                updated_fields.append("delivery_date")

                if dd_reason:
                    cursor.execute("""
                        INSERT INTO delivery_date_change_log
                        (job_card_no, change_level, item_name, old_delivery_date,
                         new_delivery_date, changed_by, reason)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        original_jc_no,
                        'JC',
                        original_item_name,
                        old_delivery,
                        new_delivery,
                        session.get("full_name") or session.get(
                            "username") or "System",
                        dd_reason
                    ))
        if item_sets:
            item_params.append(item_row["id"])
            cursor.execute(f"""
                UPDATE job_card_items
                SET {", ".join(item_sets)}
                WHERE id = %s
            """, item_params)

        vendor_name = None
        is_subcontract = None
        if "is_subcontract" in data and (field_allowed("vendor_name") or field_allowed("subcontractor_name")):
            is_subcontract = 1 if str(data.get("is_subcontract")).strip(
            ).lower() in ("1", "true", "yes", "on") else 0
        if "vendor_name" in data and field_allowed("vendor_name"):
            vendor_name = (data.get("vendor_name") or "").strip()
        elif "subcontractor_name" in data and field_allowed("subcontractor_name"):
            vendor_name = (data.get("subcontractor_name") or "").strip()

        if vendor_name is not None or is_subcontract is not None:
            vendor_name = vendor_name or ""
            if is_subcontract is None:
                is_subcontract = 1 if vendor_name else 0
            if is_subcontract and not vendor_name:
                return jsonify({"success": False, "error": "Vendor name is required for subcontracting"}), 400
            process_name = (
                data.get("process_name")
                or data.get("current_process")
                or current_process
                or ""
            ).strip()
            if not process_name:
                return jsonify({"success": False, "error": "Current process is required for vendor update"}), 400
            if role == "supervisor" and not is_gaurang_special_user() and not has_process_access(
                cursor, session.get("user_id"), process_name
            ):
                return jsonify({
                    "success": False,
                    "error": f"You do not have rights to update process: {process_name}"
                }), 403
            cursor.execute("""
                UPDATE job_card_process_days
                SET vendor_name = %s,
                    is_subcontract = %s
                WHERE job_card_no = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
            """, (vendor_name, is_subcontract, target_jc_no, process_name))
            updated_fields.append("is_subcontract")
            updated_fields.append("vendor_name")

        if not updated_fields:
            return jsonify({"success": False, "error": "No editable fields were provided"}), 400

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Delivery date updated successfully." if updated_fields == ["delivery_date"] else "Material updated successfully." if updated_fields == ["material"] else "Job card updated successfully.",
            "updated_fields": sorted(set(updated_fields)),
        })
    except ValueError as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        if conn:
            conn.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ── WIP Summary ───────────────────────────────────────────────────────────────


@data_view_bp.route("/api/wip_summary", methods=["GET"])
def get_wip_summary():
    """
    Returns a matrix of:
      date (DATE(out_time)) × process_name → count of distinct job_card_no
    Only processes with at least 1 completion in the date range are returned.
    Only rows where is_completed = 1 and out_time IS NOT NULL are counted.
    """
    conn = None
    cursor = None
    try:
        from_date = request.args.get("from_date", "")
        to_date = request.args.get("to_date", "")

        # Default: last 30 days
        if not from_date:
            from_date = (date.today() - timedelta(days=30)
                         ).strftime("%Y-%m-%d")
        if not to_date:
            to_date = date.today().strftime("%Y-%m-%d")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch all completions in date range
        cursor.execute("""
            SELECT
                DATE(CONVERT_TZ(out_time, '+00:00', '+05:30')) AS completion_date,
                process_name,
                COUNT(DISTINCT job_card_no) AS job_card_count
            FROM job_card_process_days
            WHERE is_completed = 1
              AND out_time IS NOT NULL
              AND DATE(CONVERT_TZ(out_time, '+00:00', '+05:30')) BETWEEN %s AND %s
            GROUP BY completion_date, process_name
            ORDER BY completion_date ASC, process_name ASC
        """, (from_date, to_date))

        rows = cursor.fetchall()

        # Build matrix
        # dates → set of all unique dates
        # processes → ordered list of processes that appear in results
        dates_set = {}       # date_str → { process_name: count }
        processes_ordered = []
        processes_seen = set()

        for row in rows:
            d = str(row["completion_date"])
            proc = row["process_name"]
            count = row["job_card_count"]

            if d not in dates_set:
                dates_set[d] = {}
            dates_set[d][proc] = count

            if proc not in processes_seen:
                processes_seen.add(proc)
                processes_ordered.append(proc)

        # Sort processes by a standard flow order where possible
        FLOW_ORDER = [
            "Drawing", "Raw Material", "Cutting", "Turning", "Rough Turning",
            "R/Turning", "CNC Machining", "CNC Machining 1st Side",
            "CNC Machining 2nd Side", "VMC Machining", "Drilling & Tapping",
            "Milling", "Grinding", "ID Grinding", "OD Grinding", "Broaching",
            "Slitting", "Forging", "Normalising", "Heat Treatment",
            "Blackening", "Sub Contract", "Inspection",
            "Quality Check", "Assembly", "Store"
        ]

        def process_sort_key(p):
            try:
                return FLOW_ORDER.index(p)
            except ValueError:
                return 999

        processes_ordered.sort(key=process_sort_key)

        # Build final rows list sorted by date
        matrix = []
        for d in sorted(dates_set.keys()):
            row_data = {"date": d}
            for proc in processes_ordered:
                row_data[proc] = dates_set[d].get(proc, 0)
            matrix.append(row_data)

        return jsonify({
            "success": True,
            "from_date": from_date,
            "to_date": to_date,
            "processes": processes_ordered,
            "rows": matrix,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ── WIP Summary Detail ────────────────────────────────────────────────────────


@data_view_bp.route("/api/wip_summary/detail", methods=["GET"])
def get_wip_summary_detail():
    """
    Returns list of job cards that completed a particular process on a given date.
    Pulls from audit_trail (old_stage = process completed).
    """
    conn = None
    cursor = None
    try:
        detail_date = request.args.get("date", "")
        process = request.args.get("process", "")

        if not detail_date or not process:
            return jsonify({"success": False, "error": "date and process are required"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                at.job_card_no,
                jci.item_name,
                at.changed_by,
                DATE_FORMAT(
                    CONVERT_TZ(at.changed_at, '+00:00', '+05:30'),
                    '%d-%m-%Y %h:%i %p'
                ) AS changed_at_ist,
                at.new_stage AS advanced_to
            FROM audit_trail at
            LEFT JOIN job_card_items jci
                ON jci.job_card_no = at.job_card_no
            WHERE LOWER(TRIM(at.old_stage)) = LOWER(TRIM(%s))
              AND DATE(CONVERT_TZ(at.changed_at, '+00:00', '+05:30')) = %s
            ORDER BY at.changed_at ASC
        """, (process, detail_date))

        rows = cursor.fetchall()

        return jsonify({
            "success": True,
            "date": detail_date,
            "process": process,
            "count": len(rows),
            "rows": rows
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# ── Delivery Date Change Notifications ───────────────────────────────────────


@data_view_bp.route("/api/notifications/delivery_changes", methods=["GET"])
def get_delivery_change_notifications():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                id,
                job_card_no,
                COALESCE(change_level, 'JC') AS change_level,
                so_no,
                work_order_no,
                item_name,
                DATE_FORMAT(old_delivery_date, '%d-%m-%Y') AS old_delivery_date,
                DATE_FORMAT(new_delivery_date, '%d-%m-%Y') AS new_delivery_date,
                changed_by,
                reason,
                DATE_FORMAT(
                    CONVERT_TZ(changed_at, '+00:00', '+05:30'),
                    '%d-%m-%Y %h:%i %p'
                ) AS changed_at
            FROM delivery_date_change_log
            ORDER BY changed_at DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()
        return jsonify({"success": True, "records": rows, "count": len(rows)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
    if conn:
        conn.close()

# ── Dispatch Tracker ──────────────────────────────────────────────────────────


@data_view_bp.route("/api/dispatch/tracker", methods=["GET"])
def dispatch_tracker():
    """
    Returns hierarchical data for dispatch tracker:
    Customer → SO No → Work Order No → Job Cards with process rail
    """
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch all active job cards with their details
        cursor.execute("""
            SELECT
                jc.job_card_no,
                jc.so_no,
                jc.work_order_no,
                jc.customer_name,
                jc.parent_code,
                jc.so_date,
                jc.wo_delivery_date,
                jc.so_delivery_date,
                jci.item_name,
                jci.so_qty,
                jci.job_card_qty,
                jci.actual_qty,
                jci.wip_status,
                jci.delivery_date,
                jci.remaining_days,
                jci.id AS item_id
            FROM job_cards jc
            JOIN job_card_items jci ON jci.job_card_no = jc.job_card_no
            WHERE (jci.is_deleted IS NULL OR jci.is_deleted = 0)
            ORDER BY jc.customer_name, jc.so_no, jc.work_order_no, jc.job_card_no
        """)
        rows = cursor.fetchall()

        # DISPATCH_ADVANCE_ALLOCATION_ROWS_V1
        # Active Advance Plan allocations are added as virtual
        # Dispatch Tracker rows. The original Advance Plan JC remains
        # unchanged and continues to appear under "Advance Plan".
        cursor.execute("""
            SELECT
                a.id AS allocation_id,
                a.job_card_item_id AS item_id,
                a.job_card_no,
                a.so_no,
                'Advance Allocation' AS work_order_no,
                COALESCE(
                    (
                        SELECT cm.full_customer_text
                        FROM customer_master cm
                        WHERE
                            # DISPATCH_CUSTOMER_COLLATION_FIX_V2
                            LOWER(TRIM(cm.customer_name)) COLLATE utf8mb4_unicode_ci
                                = LOWER(TRIM(a.customer_name)) COLLATE utf8mb4_unicode_ci
                            OR LOWER(TRIM(cm.full_customer_text)) COLLATE utf8mb4_unicode_ci
                                = LOWER(TRIM(a.customer_name)) COLLATE utf8mb4_unicode_ci
                        ORDER BY cm.id
                        LIMIT 1
                    ),
                    a.customer_name
                ) AS customer_name,
                (SELECT jc2.parent_code FROM job_cards jc2 WHERE jc2.job_card_no COLLATE utf8mb4_unicode_ci
      = a.job_card_no COLLATE utf8mb4_unicode_ci LIMIT 1) AS parent_code,
                NULL AS so_date,
                NULL AS wo_delivery_date,
                NULL AS so_delivery_date,
                jci.item_name,
                a.allocated_qty AS so_qty,
                0 AS actual_qty,
                jci.wip_status,
                jci.delivery_date,
                jci.remaining_days,
                1 AS is_advance_allocation
            FROM advance_plan_so_allocations a
            JOIN job_card_items jci
              ON jci.id = a.job_card_item_id
            WHERE a.status = 'active'
              AND (jci.is_deleted IS NULL OR jci.is_deleted = 0)
            ORDER BY
                a.customer_name,
                a.so_no,
                a.job_card_no,
                a.id
        """)

        allocation_rows = cursor.fetchall()

        # Mark normal JC rows so frontend can distinguish them.
        for row in rows:
            row["is_advance_allocation"] = 0

        # DISPATCH_ADVANCE_REMAINING_QTY_V1
        # Original Advance Plan row:
        # - unassigned      -> original Qty
        # - partially      -> remaining Qty only
        # - fully assigned -> hide original row
        cursor.execute("""
            SELECT
                job_card_item_id,
                COALESCE(SUM(allocated_qty), 0) AS assigned_qty
            FROM advance_plan_so_allocations
            WHERE status = 'active'
            GROUP BY job_card_item_id
        """)

        advance_assigned_map = {
            int(r["job_card_item_id"]): int(r["assigned_qty"] or 0)
            for r in (cursor.fetchall() or [])
        }

        adjusted_rows = []

        for row in rows:
            is_original_advance_plan = (
                str(row.get("customer_name") or "")
                .strip()
                .casefold()
                == "advance plan"
            )

            if not is_original_advance_plan:
                adjusted_rows.append(row)
                continue

            item_id = int(row.get("item_id") or 0)

            total_qty = int(
                row.get("job_card_qty")
                or row.get("so_qty")
                or 0
            )

            assigned_qty = int(
                advance_assigned_map.get(item_id, 0)
            )

            remaining_qty = max(
                total_qty - assigned_qty,
                0
            )

            # Fully assigned:
            # do not show original Advance Plan row.
            if assigned_qty > 0 and remaining_qty == 0:
                continue

            # Partially assigned:
            # original row represents only remaining stock.
            if assigned_qty > 0:
                row["so_qty"] = remaining_qty

            adjusted_rows.append(row)

        rows = adjusted_rows

        rows.extend(allocation_rows)

        # Fetch all process days for these job cards
        jc_nos = list(set(r["job_card_no"] for r in rows))
        processes_map = {}

        if jc_nos:
            fmt = ','.join(['%s'] * len(jc_nos))
            cursor.execute(f"""
                SELECT
                    job_card_no,
                    process_name,
                    is_completed,
                    in_time,
                    out_time,
                    days,
                    actual_days
                FROM job_card_process_days
                WHERE job_card_no IN ({fmt})
                ORDER BY job_card_no, id ASC
            """, jc_nos)
            for pr in cursor.fetchall():
                jc = pr["job_card_no"]
                if jc not in processes_map:
                    processes_map[jc] = []
                processes_map[jc].append({
                    "process_name": pr["process_name"],
                    "is_completed": bool(pr["is_completed"]),
                    "in_progress": bool(pr["in_time"] and not pr["is_completed"]),
                    "days": pr["days"],
                    "actual_days": pr["actual_days"],
                })

        # Build hierarchy
        customers = {}
        today = date.today()

        for row in rows:
            # DISPATCH_CUSTOMER_CANONICAL_MERGE_V1
            cust = row["customer_name"] or "Unknown"

            # Same customer must use one Dispatch branch even when
            # character casing differs between ERP/job card/customer master.
            cust_key = str(cust).strip().casefold()
            so = row["so_no"] or "—"
            wo = row["work_order_no"] or "—"
            jc_no = row["job_card_no"]
            delivery = row["delivery_date"]
            remaining = row["remaining_days"]

            # Delivery status
            if delivery:
                diff = (delivery - today).days
                if diff < 0:
                    delivery_status = "overdue"
                elif diff <= 7:
                    delivery_status = "soon"
                else:
                    delivery_status = "ok"
            else:
                delivery_status = "unknown"
                diff = None

            jc_data = {
                "is_advance_allocation": bool(row.get("is_advance_allocation")),
                # DISPATCH_ADVANCE_PLAN_ITEM_ID_V4
                "item_id": int(row["item_id"]),
                "is_advance_plan": (
                    str(row.get("customer_name") or "")
                    .strip()
                    .lower() == "advance plan"
                ),
                "job_card_no": jc_no,
                # DISPATCH_PARENT_CODE_DATA_V1
                "parent_code": row.get("parent_code") or "",
                "item_name": row["item_name"] or "—",
                "so_qty": int(row["so_qty"] or 0),
                "actual_qty": int(row["actual_qty"] or 0),
                "wip_status": row["wip_status"] or "—",
                "delivery_date": str(delivery) if delivery else None,
                "wo_delivery_date": str(row["wo_delivery_date"]) if row.get("wo_delivery_date") else None,
                "so_delivery_date": str(row["so_delivery_date"]) if row.get("so_delivery_date") else None,
                "remaining_days": int(remaining) if remaining is not None else None,
                "delivery_status": delivery_status,
                "processes": processes_map.get(jc_no, []),
            }

            # Build tree
            if cust_key not in customers:
                customers[cust_key] = {
                    "customer_name": cust,
                    "sos": {}
                }

            if so not in customers[cust_key]["sos"]:
                customers[cust_key]["sos"][so] = {
                    "so_no": so,
                    "so_date": str(row["so_date"]) if row["so_date"] else None,
                    "so_delivery_date": str(row["so_delivery_date"]) if row.get("so_delivery_date") else None,
                    "wos": {}
                }

            if wo not in customers[cust_key]["sos"][so]["wos"]:
                customers[cust_key]["sos"][so]["wos"][wo] = {
                    "work_order_no": wo,
                    "wo_delivery_date": str(row["wo_delivery_date"]) if row.get("wo_delivery_date") else None,
                    "jcs": []
                }

            customers[cust_key]["sos"][so]["wos"][wo]["jcs"].append(jc_data)

        # Convert dicts to lists
        result = []
        for cust_data in customers.values():
            sos = []
            for so_data in cust_data["sos"].values():
                wos = []
                for wo_data in so_data["wos"].values():
                    wos.append({
                        "work_order_no": wo_data["work_order_no"],
                        "wo_delivery_date": wo_data["wo_delivery_date"],
                        "jcs": wo_data["jcs"]
                    })
                sos.append({
                    "so_no": so_data["so_no"],
                    "so_date": so_data["so_date"],
                    "so_delivery_date": so_data["so_delivery_date"],
                    "wos": wos
                })
            result.append({
                "customer_name": cust_data["customer_name"],
                "sos": sos
            })

        cursor.close()
        conn.close()

        return jsonify({"success": True, "data": result})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ── Dispatch: Update WO Delivery Date ────────────────────────────────────────


@data_view_bp.route("/api/dispatch/update_wo_dd", methods=["POST"])
def dispatch_update_wo_dd():
    """
    Updates wo_delivery_date for all job cards under a WO.
    Automatically sets job_card_items.delivery_date = wo_delivery_date - 5 days.
    Logs the change to delivery_date_change_log.
    """
    conn = None
    cursor = None
    try:
        from datetime import datetime
        from datetime import timedelta as td

        data = request.json or {}
        work_order_no = (data.get("work_order_no") or "").strip()
        wo_delivery_date = (data.get("wo_delivery_date") or "").strip()
        reason = (data.get("reason") or "").strip()

        if not work_order_no:
            return jsonify({"success": False, "error": "work_order_no is required"}), 400
        if not wo_delivery_date:
            return jsonify({"success": False, "error": "wo_delivery_date is required"}), 400
        if not reason:
            return jsonify({"success": False, "error": "Reason is required"}), 400

        # Only dispatch or admin
        role = (session.get("role") or "").strip().lower()
        is_dispatch = False
        if role == "admin":
            is_dispatch = True
        else:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT 1 FROM supervisor_process_access
                WHERE user_id = %s AND LOWER(TRIM(process_name)) = 'dispatch'
                LIMIT 1
            """, (session.get("user_id"),))
            is_dispatch = cursor.fetchone() is not None
            cursor.close()
            conn.close()

        if not is_dispatch:
            return jsonify({"success": False, "error": "Only Dispatch department can change delivery dates."}), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Calculate JC DD = WO DD - 5 days
        wo_dd_obj = datetime.strptime(wo_delivery_date, "%Y-%m-%d").date()
        jc_dd_obj = wo_dd_obj - td(days=5)
        jc_delivery_date = jc_dd_obj.strftime("%Y-%m-%d")

        # Get all job cards under this WO
        cursor.execute("""
            SELECT job_card_no FROM job_cards
            WHERE LOWER(TRIM(work_order_no)) = LOWER(TRIM(%s))
        """, (work_order_no,))
        jc_rows = cursor.fetchall()

        if not jc_rows:
            return jsonify({"success": False, "error": f"No job cards found for WO {work_order_no}"}), 404

        changed_by = session.get("full_name") or session.get(
            "username") or "Dispatch"

        for jc in jc_rows:
            jc_no = jc["job_card_no"]

            # Update wo_delivery_date on job_cards
            cursor.execute("""
                UPDATE job_cards
                SET wo_delivery_date = %s
                WHERE job_card_no = %s
            """, (wo_delivery_date, jc_no))

            # Get old delivery date for log
            cursor.execute("""
                SELECT delivery_date, item_name FROM job_card_items
                WHERE job_card_no = %s LIMIT 1
            """, (jc_no,))
            item_row = cursor.fetchone()
            old_dd = str(
                item_row["delivery_date"]) if item_row and item_row["delivery_date"] else None
            item_name = item_row["item_name"] if item_row else ""

            # Update job_card_items delivery_date = WO DD - 5 days
            cursor.execute("""
                UPDATE job_card_items
                SET delivery_date = %s,
                    remaining_days = DATEDIFF(%s, CURDATE())
                WHERE job_card_no = %s
            """, (jc_delivery_date, jc_delivery_date, jc_no))

            # Log the change
            cursor.execute("""
                INSERT INTO delivery_date_change_log
                (job_card_no, change_level, so_no, work_order_no, item_name,
                 old_delivery_date, new_delivery_date, changed_by, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (jc_no, 'WO', None, work_order_no, item_name,
                  old_dd, jc_delivery_date, changed_by, reason))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"WO delivery date updated. {len(jc_rows)} job card(s) updated. JC delivery date set to {jc_delivery_date} (WO DD - 5 days).",
            "wo_delivery_date": wo_delivery_date,
            "jc_delivery_date": jc_delivery_date,
            "updated_jcs": len(jc_rows),
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

# ── Dispatch: Update SO Delivery Date ────────────────────────────────────────


@data_view_bp.route("/api/dispatch/update_so_dd", methods=["POST"])
def dispatch_update_so_dd():
    """
    Updates so_delivery_date for all job cards under an SO.
    Cascades: all WOs get SO DD, all JCs get SO DD - 5 days.
    Logs each change to delivery_date_change_log.
    """
    conn = None
    cursor = None
    try:
        from datetime import datetime
        from datetime import timedelta as td

        data = request.json or {}
        so_no = (data.get("so_no") or "").strip()
        so_delivery_date = (data.get("so_delivery_date") or "").strip()
        reason = (data.get("reason") or "").strip()

        if not so_no:
            return jsonify({"success": False, "error": "so_no is required"}), 400
        if not so_delivery_date:
            return jsonify({"success": False, "error": "so_delivery_date is required"}), 400
        if not reason:
            return jsonify({"success": False, "error": "Reason is required"}), 400

        # Only dispatch or admin
        role = (session.get("role") or "").strip().lower()
        is_dispatch = False
        if role == "admin":
            is_dispatch = True
        else:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT 1 FROM supervisor_process_access
                WHERE user_id = %s AND LOWER(TRIM(process_name)) = 'dispatch'
                LIMIT 1
            """, (session.get("user_id"),))
            is_dispatch = cursor.fetchone() is not None
            cursor.close()
            conn.close()

        if not is_dispatch:
            return jsonify({"success": False, "error": "Only Dispatch department can change delivery dates."}), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Calculate JC DD = SO DD - 5 days
        so_dd_obj = datetime.strptime(so_delivery_date, "%Y-%m-%d").date()
        jc_dd_obj = so_dd_obj - td(days=5)
        jc_delivery_date = jc_dd_obj.strftime("%Y-%m-%d")

        # Get all job cards under this SO
        cursor.execute("""
            SELECT job_card_no, work_order_no FROM job_cards
            WHERE LOWER(TRIM(so_no)) = LOWER(TRIM(%s))
        """, (so_no,))
        jc_rows = cursor.fetchall()

        if not jc_rows:
            return jsonify({"success": False, "error": f"No job cards found for SO {so_no}"}), 404

        changed_by = session.get("full_name") or session.get(
            "username") or "Dispatch"

        for jc in jc_rows:
            jc_no = jc["job_card_no"]

            # Update so_delivery_date only — WO date is independent
            cursor.execute("""
                UPDATE job_cards
                SET so_delivery_date = %s
                WHERE job_card_no = %s
            """, (so_delivery_date, jc_no))

            # Get old delivery date for log
            cursor.execute("""
                SELECT delivery_date, item_name FROM job_card_items
                WHERE job_card_no = %s LIMIT 1
            """, (jc_no,))
            item_row = cursor.fetchone()
            old_dd = str(
                item_row["delivery_date"]) if item_row and item_row["delivery_date"] else None
            item_name = item_row["item_name"] if item_row else ""

            # Log the SO date change
            cursor.execute("""
                INSERT INTO delivery_date_change_log
                (job_card_no, change_level, so_no, work_order_no, item_name,
                 old_delivery_date, new_delivery_date, changed_by, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (jc_no, 'SO', so_no, jc["work_order_no"], item_name,
                  old_dd, so_delivery_date, changed_by, reason))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"SO delivery date updated. {len(jc_rows)} job card(s) updated. JC delivery date set to {jc_delivery_date} (SO DD - 5 days).",
            "so_delivery_date": so_delivery_date,
            "jc_delivery_date": jc_delivery_date,
            "updated_jcs": len(jc_rows),
        })

    except Exception as e:
        if conn:
            conn.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@data_view_bp.route("/api/data/assembly_readiness", methods=["GET"])
def assembly_readiness():
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        filter_date = request.args.get("filter_date", "").strip()
        params = []
        date_filter = ""
        if filter_date:
            date_filter = "AND DATE(jc.created_at) = %s"
            params.append(filter_date)

        # Step 1: Get all unique assemblies (parent_code + so_no + customer_name)
        cursor.execute(f"""
            SELECT 
                jc.parent_code,
                jc.so_no,
                jc.customer_name,
                i.item_description AS assembly_name,
                COUNT(DISTINCT jc.job_card_no) AS total_parts,
                MIN(jci.delivery_date) AS earliest_delivery,
                MAX(jci.delivery_date) AS latest_delivery
            FROM job_cards jc
            JOIN job_card_items jci ON jci.job_card_no = jc.job_card_no
            LEFT JOIN items i ON i.item_code = jc.parent_code
            WHERE jc.parent_code IS NOT NULL
            AND jc.parent_code != ''
            AND COALESCE(jci.is_deleted, 0) = 0
            {date_filter}
            GROUP BY jc.parent_code, jc.so_no, jc.customer_name, i.item_description
            HAVING COUNT(DISTINCT jc.job_card_no) > 1
            ORDER BY jc.parent_code, jc.so_no
        """, params)
        assemblies = cursor.fetchall()

        if not assemblies:
            return jsonify({"success": True, "data": [], "summary": {
                "total": 0, "ready": 0, "in_progress": 0, "not_started": 0
            }})

        # Step 2: Get all job cards for these assemblies
        parent_codes = list(set(a["parent_code"] for a in assemblies))
        fmt = ",".join(["%s"] * len(parent_codes))
        
        cursor.execute(f"""
            SELECT
                jc.parent_code,
                jc.so_no,
                jc.customer_name,
                jc.job_card_no,
                jc.child_code,
                jci.item_name,
                jci.wip_status,
                jci.delivery_date,
                jc.final_status,
                CASE WHEN LOWER(TRIM(jci.wip_status)) = 'store'
                          OR jc.final_status = 'Completed'
                     THEN 1 ELSE 0 END AS is_completed,
                (SELECT COUNT(*) FROM job_card_process_days pd
                 WHERE pd.job_card_no = jc.job_card_no) AS total_processes,
                (SELECT COUNT(*) FROM job_card_process_days pd
                 WHERE pd.job_card_no = jc.job_card_no
                 AND (pd.is_completed = 1 OR pd.in_time IS NOT NULL)) AS completed_processes
            FROM job_cards jc
            JOIN job_card_items jci ON jci.job_card_no = jc.job_card_no
            WHERE jc.parent_code IN ({fmt})
            AND COALESCE(jci.is_deleted, 0) = 0
            ORDER BY jc.parent_code, jc.so_no, jc.job_card_no
        """, parent_codes)
        all_jcs = cursor.fetchall()

        # Format dates
        for jc in all_jcs:
            if jc.get("delivery_date") and hasattr(jc["delivery_date"], "strftime"):
                jc["delivery_date"] = jc["delivery_date"].strftime("%Y-%m-%d")

        # Step 3: Get BOM tree structure from bom_links (up to 4 levels)
        cursor.execute(f"""
            SELECT 
                bl1.parent_code AS l1_parent,
                bl1.child_code AS l1_child,
                bl2.child_code AS l2_child,
                bl3.child_code AS l3_child,
                bl4.child_code AS l4_child
            FROM bom_links bl1
            LEFT JOIN bom_links bl2 ON bl2.parent_code = bl1.child_code AND bl2.make_buy = 'A'
            LEFT JOIN bom_links bl3 ON bl3.parent_code = bl2.child_code AND bl3.make_buy = 'A'
            LEFT JOIN bom_links bl4 ON bl4.parent_code = bl3.child_code AND bl4.make_buy = 'A'
            WHERE bl1.parent_code IN ({fmt})
            AND bl1.make_buy = 'A'
        """, parent_codes)
        bom_rows = cursor.fetchall()

        # Build BOM hierarchy map: parent_code -> [child_codes]
        bom_children = {}
        for row in bom_rows:
            l1p = row["l1_parent"]
            l1c = row["l1_child"]
            l2c = row["l2_child"]
            l3c = row["l3_child"]
            l4c = row["l4_child"]

            if l1p not in bom_children:
                bom_children[l1p] = set()
            bom_children[l1p].add(l1c)

            if l1c and l2c:
                if l1c not in bom_children:
                    bom_children[l1c] = set()
                bom_children[l1c].add(l2c)

            if l2c and l3c:
                if l2c not in bom_children:
                    bom_children[l2c] = set()
                bom_children[l2c].add(l3c)

            if l3c and l4c:
                if l3c not in bom_children:
                    bom_children[l3c] = set()
                bom_children[l3c].add(l4c)

        # Build JC lookup: (child_code, so_no, customer_name) -> jc data
        jc_lookup = {}
        for jc in all_jcs:
            key = (jc["child_code"], jc["so_no"] or "", jc["customer_name"] or "")
            jc_lookup[key] = jc
            # Also index by child_code only as fallback
            if jc["child_code"] not in jc_lookup:
                jc_lookup[jc["child_code"]] = jc

        def get_jc(child_code, so_no, customer_name):
            key = (child_code, so_no or "", customer_name or "")
            return jc_lookup.get(key) or jc_lookup.get(child_code)

        def build_node(child_code, so_no, customer_name, depth=0, _seen=None):
            if _seen is None:
                _seen = set()
            if depth > 4:
                return None
            jc = get_jc(child_code, so_no, customer_name)
            # Skip nodes with no job card
            if not jc:
                return None
            # Skip if already rendered
            jc_no = jc.get("job_card_no")
            if jc_no in _seen:
                return None
            _seen.add(jc_no)
            total_proc = int(jc.get("total_processes") or 0) if jc else 0
            done_proc = int(jc.get("completed_processes") or 0) if jc else 0
            proc_pct = round((done_proc / total_proc) * 100) if total_proc > 0 else 0
            is_completed = bool(jc.get("is_completed")) if jc else False

            node = {
                "child_code": child_code,
                "job_card_no": jc.get("job_card_no") if jc else None,
                "item_name": jc.get("item_name") if jc else child_code,
                "wip_status": jc.get("wip_status") if jc else None,
                "delivery_date": jc.get("delivery_date") if jc else None,
                "is_completed": is_completed,
                "process_pct": proc_pct,
                "children": []
            }

            sub_children = bom_children.get(child_code, set())
            for sub_code in sorted(sub_children):
                sub_node = build_node(sub_code, so_no, customer_name, depth + 1, _seen)
                if sub_node:
                    node["children"].append(sub_node)

            return node

        def get_leaf_pcts(node):
            if not node["children"]:
                return [node["process_pct"]]
            pcts = []
            for child in node["children"]:
                pcts.extend(get_leaf_pcts(child))
            return pcts

        def all_leaves_completed(node):
            if not node["children"]:
                return node["is_completed"]
            return all(all_leaves_completed(c) for c in node["children"])

        # Step 4: Build final result
        result = []
        for asm in assemblies:
            rendered_jcs = set()
            pc = asm["parent_code"]
            so = asm["so_no"] or ""
            cust = asm["customer_name"] or ""

            # Get direct children from BOM
            direct_children = bom_children.get(pc, set())
            if not direct_children:
                # Fallback: use job cards directly
                direct_children = set(
                    jc["child_code"] for jc in all_jcs
                    if jc["parent_code"] == pc
                    and (jc["so_no"] or "") == so
                    and (jc["customer_name"] or "") == cust
                )

            children_nodes = []
            assembly_seen = set()
            for child_code in sorted(direct_children):
                node = build_node(child_code, so, cust, 0, assembly_seen)
                if node:
                    children_nodes.append(node)

            # Calculate overall progress from leaf nodes
            all_pcts = []
            for node in children_nodes:
                all_pcts.extend(get_leaf_pcts(node))
            overall_pct = round(sum(all_pcts) / len(all_pcts)) if all_pcts else 0

            # Check if ready
            is_ready = all(all_leaves_completed(n) for n in children_nodes)
            pending_parts = sum(1 for n in children_nodes if not all_leaves_completed(n))
            completed_parts = len(children_nodes) - pending_parts

            # Format dates
            for f in ("earliest_delivery", "latest_delivery"):
                if asm.get(f) and hasattr(asm[f], "strftime"):
                    asm[f] = asm[f].strftime("%Y-%m-%d")

            result.append({
                "parent_code": pc,
                "so_no": so,
                "customer_name": cust,
                "assembly_name": asm.get("assembly_name") or pc,
                "total_parts": len(children_nodes),
                "completed_parts": completed_parts,
                "pending_parts": pending_parts,
                "earliest_delivery": asm.get("earliest_delivery"),
                "latest_delivery": asm.get("latest_delivery"),
                "overall_pct": overall_pct,
                "is_ready": is_ready,
                "children": children_nodes,
            })

        # Summary
        ready_count = sum(1 for r in result if r["is_ready"])
        in_progress_count = sum(1 for r in result if not r["is_ready"] and r["overall_pct"] > 0)
        not_started_count = sum(1 for r in result if not r["is_ready"] and r["overall_pct"] == 0)

        return jsonify({
            "success": True,
            "data": result,
            "summary": {
                "total": len(result),
                "ready": ready_count,
                "in_progress": in_progress_count,
                "not_started": not_started_count,
            }
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ============================================================
# DISPATCH TRACKER EXCEL EXPORT
# ============================================================
# DISPATCH_EXCEL_EXPORT_V1

@data_view_bp.route(
    "/api/dispatch-tracker/export-excel",
    methods=["GET"]
)
def dispatch_tracker_export_excel():
    from io import BytesIO
    from datetime import datetime

    from flask import send_file

    from openpyxl import Workbook
    from openpyxl.styles import (
        Font,
        PatternFill,
        Alignment,
        Border,
        Side,
    )
    from openpyxl.utils import get_column_letter

    try:
        # Reuse the existing Dispatch Tracker backend.
        # No duplicate Dispatch business logic is created.
        result = dispatch_tracker()

        status_code = 200
        response = result

        if isinstance(result, tuple):
            response = result[0]

            if len(result) > 1:
                status_code = result[1]

        if status_code != 200:
            return result

        if hasattr(response, "get_json"):
            payload = response.get_json() or {}
        elif isinstance(response, dict):
            payload = response
        else:
            payload = {}

        customers = payload.get("customers")

        if customers is None:
            customers = payload.get("data", [])

        if isinstance(customers, dict):
            customer_rows = list(customers.values())
        else:
            customer_rows = customers or []

        # ----------------------------------------------------
        # Workbook
        # ----------------------------------------------------
        wb = Workbook()
        ws = wb.active
        ws.title = "Dispatch Tracker"

        headers = [
            "Customer",
            "SO No",
            "SO Delivery Date",
            "Work Order No",
            "WO Delivery Date",
            "Job Card No",
            "Parent Code",
            "Item Name",
            "SO Qty",
            "Actual Qty",
            "WIP Status",
            "JC Delivery Date",
            "Remaining Days",
            "Type",
        ]

        # Title
        ws.merge_cells(
            start_row=1,
            start_column=1,
            end_row=1,
            end_column=len(headers),
        )

        title_cell = ws.cell(1, 1)
        title_cell.value = "NMTG - Dispatch Tracker"
        # DISPATCH_EXCEL_EXPORT_V2_PARENT_SIMPLE
        title_cell.font = Font(
            bold=True,
            size=14,
        )
        title_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        ws.row_dimensions[1].height = 28

        # Export timestamp
        ws.merge_cells(
            start_row=2,
            start_column=1,
            end_row=2,
            end_column=len(headers),
        )

        ws.cell(2, 1).value = (
            "Exported: "
            + datetime.now().strftime("%d-%m-%Y %I:%M %p")
        )

        ws.cell(2, 1).alignment = Alignment(
            horizontal="right"
        )

        ws.cell(2, 1).font = Font(
            italic=True,
            size=9,
        )

        # Header row
        header_row = 4

        for col, header in enumerate(headers, 1):
            cell = ws.cell(header_row, col)
            cell.value = header
            cell.font = Font(
                bold=True,
            )
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        # ----------------------------------------------------
        # Flatten existing Dispatch hierarchy
        # ----------------------------------------------------
        output_rows = []

        for customer in customer_rows:
            if not isinstance(customer, dict):
                continue

            customer_name = (
                customer.get("customer_name")
                or "Unknown"
            )

            sos = customer.get("sos", [])

            if isinstance(sos, dict):
                so_rows = list(sos.values())
            else:
                so_rows = sos or []

            for so in so_rows:
                if not isinstance(so, dict):
                    continue

                so_no = so.get("so_no") or ""
                so_delivery = (
                    so.get("so_delivery_date") or ""
                )

                wos = so.get("wos", [])

                if isinstance(wos, dict):
                    wo_rows = list(wos.values())
                else:
                    wo_rows = wos or []

                for wo in wo_rows:
                    if not isinstance(wo, dict):
                        continue

                    wo_no = (
                        wo.get("work_order_no") or ""
                    )

                    wo_delivery = (
                        wo.get("wo_delivery_date") or ""
                    )

                    jcs = wo.get("jcs", []) or []

                    for jc in jcs:
                        if not isinstance(jc, dict):
                            continue

                        if jc.get("is_advance_allocation"):
                            record_type = "Advance Allocation"
                        elif jc.get("is_advance_plan"):
                            record_type = "Advance Plan"
                        else:
                            record_type = "Normal"

                        output_rows.append([
                            customer_name,
                            so_no,
                            so_delivery,
                            wo_no,
                            wo_delivery,
                            jc.get("job_card_no") or "",
                            jc.get("parent_code") or "",
                            jc.get("item_name") or "",
                            int(jc.get("so_qty") or 0),
                            int(jc.get("actual_qty") or 0),
                            jc.get("wip_status") or "",
                            jc.get("delivery_date") or "",
                            jc.get("remaining_days"),
                            record_type,
                        ])

        # ----------------------------------------------------
        # Write rows
        # ----------------------------------------------------
        for row in output_rows:
            ws.append(row)

        # Borders / alignment
        thin = Side(
            style="thin",
        )

        for row in ws.iter_rows(
            min_row=header_row,
            max_row=ws.max_row,
            min_col=1,
            max_col=len(headers),
        ):
            for cell in row:
                cell.border = Border(
                    left=thin,
                    right=thin,
                    top=thin,
                    bottom=thin,
                )
                cell.alignment = Alignment(
                    vertical="center",
                    wrap_text=True,
                )

        # Freeze + filter
        ws.freeze_panes = "A5"

        if ws.max_row >= header_row:
            ws.auto_filter.ref = (
                f"A{header_row}:"
                f"{get_column_letter(len(headers))}"
                f"{ws.max_row}"
            )

        # Column widths
        widths = {
            1: 32,   # Customer
            2: 16,   # SO No
            3: 18,   # SO Delivery
            4: 22,   # Work Order
            5: 18,   # WO Delivery
            6: 18,   # Job Card
            7: 20,   # Parent Code
            8: 36,   # Item Name
            9: 12,   # SO Qty
            10: 12,  # Actual Qty
            11: 22,  # WIP Status
            12: 18,  # JC Delivery
            13: 15,  # Remaining Days
            14: 20,  # Type
        }

        for col, width in widths.items():
            ws.column_dimensions[
                get_column_letter(col)
            ].width = width

        # Numeric alignment
        for row_no in range(5, ws.max_row + 1):
            for col_no in (9, 10, 13):
                ws.cell(
                    row_no,
                    col_no
                ).alignment = Alignment(
                    horizontal="center",
                    vertical="center",
                )

        # ----------------------------------------------------
        # Send XLSX
        # ----------------------------------------------------
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        filename = (
            "NMTG_Dispatch_Tracker_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".xlsx"
        )

        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
        )

    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }, 500

