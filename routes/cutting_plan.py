"""Cutting Plan backend API for Demo 2.

Backend-first foundation. No frontend is changed here.
The automatic Raw Material -> Cutting hook is intentionally added later,
after these APIs are tested with X-API-Key.
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import date, datetime, time, timedelta

from flask import Blueprint, jsonify, request, render_template, session, redirect, url_for

from db import get_connection
from permission_utils import is_gaurang_special_user

cutting_plan_bp = Blueprint("cutting_plan", __name__)

_TEST_API_KEY = os.environ.get("CUTTING_PLAN_TEST_API_KEY", "NMTG_TEST_123")
_PLANNING_ROLES = {"admin", "supervisor", "ppc"}
_MOVE_TO = {"F", "SC", "U1", "U2"}
# CUTTING_PLAN_LOCAL_SERVER_SYNC_20260903_V1
# Legacy move_to DB column is retained; active workflow does not use it.
_STATUSES = {
    "Draft",
    "Released",
    "Partially Completed",
    "Completed",
    "Cancelled",
}


def _clean(value):
    return str(value or "").strip()


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_api_key_request():
    supplied = _clean(request.headers.get("X-API-Key"))
    return bool(
        supplied
        and _TEST_API_KEY
        and hmac.compare_digest(supplied, _TEST_API_KEY)
    )


def _actor():
    if _is_api_key_request():
        test_id = _as_int(request.headers.get("X-Test-User-Id"), 0)
        return {
            "api_key": True,
            "role": "admin",
            "user_id": test_id or None,
            "name": _clean(request.headers.get("X-Test-User"))
            or "Cutting Plan API Test",
        }

    return {
        "api_key": False,
        "role": _clean(session.get("role")).lower(),
        "user_id": session.get("user_id"),
        "name": _clean(session.get("full_name"))
        or _clean(session.get("username"))
        or "System",
    }


def _planning_access():
    actor = _actor()
    allowed = (
        actor["api_key"]
        or actor["role"] in _PLANNING_ROLES
        or is_gaurang_special_user()
    )
    if allowed:
        return actor, None
    return actor, (
        jsonify(
            {
                "success": False,
                "error": "Admin, Supervisor or PPC access is required.",
            }
        ),
        403,
    )


def _operator_has_cutting_access(cursor, user_id):
    if not user_id:
        return False
    cursor.execute(
        """
        SELECT 1
        FROM supervisor_process_access
        WHERE user_id = %s
          AND LOWER(TRIM(process_name)) = 'cutting'
        LIMIT 1
        """,
        (user_id,),
    )
    return cursor.fetchone() is not None


def _batch_access(cursor):
    actor = _actor()
    if actor["api_key"]:
        return actor, None
    if actor["role"] != "operator":
        return actor, (
            jsonify(
                {
                    "success": False,
                    "error": "Cutting Operator access is required.",
                }
            ),
            403,
        )
    if not _operator_has_cutting_access(cursor, actor["user_id"]):
        return actor, (
            jsonify(
                {
                    "success": False,
                    "error": "You are not assigned to the Cutting process.",
                }
            ),
            403,
        )
    return actor, None


def _ensure_tables(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_plans (
            id BIGINT NOT NULL AUTO_INCREMENT,

            source_type VARCHAR(10) NOT NULL DEFAULT 'MANUAL',
            source_job_card_no VARCHAR(50) NULL,
            source_item_id BIGINT NULL,
            source_process_day_id INT NULL,

            job_card_no VARCHAR(50) NULL,
            item_name VARCHAR(500) NULL,
            so_no VARCHAR(100) NULL,

            planned_date DATE NULL,
            planned_time TIME NULL,
            actual_completed_at DATETIME NULL,
            last_actual_at DATETIME NULL,

            material_spec VARCHAR(255) NULL,
            cut_size VARCHAR(255) NULL,

            planned_qty INT NOT NULL DEFAULT 0,
            completed_qty INT NOT NULL DEFAULT 0,
            remaining_qty INT NOT NULL DEFAULT 0,

            part VARCHAR(255) NULL,
            model_size VARCHAR(500) NULL,
            move_to VARCHAR(2) NULL,
            remarks TEXT NULL,

            status VARCHAR(30) NOT NULL DEFAULT 'Draft',

            released_at DATETIME NULL,
            released_by_id INT NULL,
            released_by_name VARCHAR(100) NULL,

            cancelled_at DATETIME NULL,
            cancelled_by_id INT NULL,
            cancelled_by_name VARCHAR(100) NULL,
            cancel_reason VARCHAR(500) NULL,

            created_by_id INT NULL,
            created_by_name VARCHAR(100) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            updated_by_id INT NULL,
            updated_by_name VARCHAR(100) NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,

            PRIMARY KEY (id),

            UNIQUE KEY uq_cutting_plan_auto_source (
                source_job_card_no,
                source_item_id,
                source_process_day_id
            ),

            INDEX idx_cutting_plan_status (
                status,
                planned_date,
                planned_time
            ),
            INDEX idx_cutting_plan_so (so_no),
            INDEX idx_cutting_plan_job_card (job_card_no)
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_plan_batches (
            id BIGINT NOT NULL AUTO_INCREMENT,
            cutting_plan_id BIGINT NOT NULL,
            batch_no INT NOT NULL,
            cut_qty INT NOT NULL,

            operator_user_id INT NULL,
            operator_name VARCHAR(100) NULL,
            remarks VARCHAR(1000) NULL,
            actual_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            status VARCHAR(20) NOT NULL DEFAULT 'active',
            undone_at DATETIME NULL,
            undone_by_id INT NULL,
            undone_by_name VARCHAR(100) NULL,
            undo_reason VARCHAR(500) NULL,

            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (id),
            UNIQUE KEY uq_cutting_plan_batch_no (
                cutting_plan_id,
                batch_no
            ),
            INDEX idx_cutting_plan_batch_plan (
                cutting_plan_id,
                status,
                batch_no
            )
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cutting_plan_audit (
            id BIGINT NOT NULL AUTO_INCREMENT,
            cutting_plan_id BIGINT NOT NULL,
            action VARCHAR(50) NOT NULL,
            old_status VARCHAR(30) NULL,
            new_status VARCHAR(30) NULL,
            details_json LONGTEXT NULL,
            changed_by_id INT NULL,
            changed_by_name VARCHAR(100) NULL,
            changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            PRIMARY KEY (id),
            INDEX idx_cutting_plan_audit_plan (
                cutting_plan_id,
                changed_at,
                id
            )
        )
        ENGINE=InnoDB
        DEFAULT CHARSET=utf8mb4
        COLLATE=utf8mb4_unicode_ci
        """
    )

    # CUTTING_PLAN_ACTUAL_VARIANCE_V1
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'cutting_plans'
          AND COLUMN_NAME = 'variance_qty'
        """
    )
    if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
        cursor.execute(
            """
            ALTER TABLE cutting_plans
            ADD COLUMN variance_qty INT NOT NULL DEFAULT 0
            AFTER remaining_qty
            """
        )

    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'cutting_plan_batches'
          AND COLUMN_NAME = 'is_final'
        """
    )
    if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
        cursor.execute(
            """
            ALTER TABLE cutting_plan_batches
            ADD COLUMN is_final TINYINT(1) NOT NULL DEFAULT 0
            AFTER cut_qty
            """
        )



def _audit(cursor, plan_id, action, actor, old_status=None, new_status=None, details=None):
    # CUTTING_PLAN_PM_SYNC_ON_BATCH_V2
    #
    # Final Material + Cut Size become Process Master values
    # only when AUTO batch commitment happens.
    if action in {
        "AUTO_BATCH_CREATED",
        "AUTO_ADDED_TO_EXISTING_BATCH",
    }:

        pm_sync = (
            _sync_cutting_plan_batch_values_to_process_master(
                cursor,
                plan_id,
            )
        )

        if details is None:

            details = {}

        elif isinstance(details, dict):

            details = dict(details)

        else:

            details = {
                "original_details":
                    details
            }

        details[
            "process_master_sync"
        ] = pm_sync

    cursor.execute(
        """
        INSERT INTO cutting_plan_audit (
            cutting_plan_id,
            action,
            old_status,
            new_status,
            details_json,
            changed_by_id,
            changed_by_name,
            changed_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            plan_id,
            action,
            old_status,
            new_status,
            json.dumps(details, ensure_ascii=False, default=str)
            if details is not None
            else None,
            actor.get("user_id"),
            actor.get("name"),
        ),
    )


def _format(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        sign = "-" if total_seconds < 0 else ""
        total_seconds = abs(total_seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"
    return value


def _serialize(row):
    if not row:
        return None
    data = {key: _format(value) for key, value in row.items()}
    if "so_no" in data:
        data["so_display"] = _clean(data.get("so_no")) or "Advance Plan"
    return data


def _validate_move_to(value):
    value = _clean(value).upper()
    if not value:
        return None, None
    if value not in _MOVE_TO:
        return None, "Move To must be one of: F, SC, U1 or U2."
    return value, None


def _get_plan_for_update(cursor, plan_id):
    cursor.execute(
        """
        SELECT *
        FROM cutting_plans
        WHERE id = %s
        LIMIT 1
        FOR UPDATE
        """,
        (plan_id,),
    )
    return cursor.fetchone()


def _release_missing(plan):
    labels = {
        "material_spec": "Material Specification",
        "cut_size": "Cut Size",
        "part": "Part",
        "model_size": "Model & Size",
    }
    missing = [label for field, label in labels.items() if not _clean(plan.get(field))]
    if not plan.get("planned_date"):
        missing.append("Planned Date")
    if _as_int(plan.get("planned_qty"), 0) <= 0:
        missing.append("Planned Quantity")
    return missing


def _resolve_auto_source(cursor, job_card_no, item_id=None, item_name=None):
    params = [job_card_no]
    item_filter = ""
    if item_id:
        item_filter = "AND ji.id = %s"
        params.append(item_id)
    elif _clean(item_name):
        item_filter = "AND TRIM(ji.item_name) = TRIM(%s)"
        params.append(_clean(item_name))

    cursor.execute(
        f"""
        SELECT
            jc.job_card_no,
            jc.so_no,
            jc.job_card_date AS planned_date,
            ji.id AS item_id,
            ji.item_name,

            # CUTTING_PLAN_JC_DETAILS_SOURCE_V1
            NULLIF(
                TRIM(ji.material),
                ''
            ) AS material,

            ji.part,
            ji.job_card_qty,
            ji.so_qty,

            NULLIF(
                TRIM(ji.cutting_size),
                ''
            ) AS cutting_size,

            ji.dia,
            ji.length,
            ji.wip_status
        FROM job_cards jc
        JOIN job_card_items ji ON ji.job_card_no = jc.job_card_no
        WHERE jc.job_card_no = %s
          AND COALESCE(ji.is_deleted, 0) = 0
          {item_filter}
        ORDER BY ji.id
        LIMIT 1
        """,
        tuple(params),
    )
    source = cursor.fetchone()
    if not source:
        return None, "Job Card item was not found."

    # CUTTING_PLAN_UPLOAD_SOURCE_FIX_V2
    # First use the JC timeline if Cutting already exists there.
    cursor.execute(
        """
        SELECT id
        FROM job_card_process_days
        WHERE BINARY job_card_no = BINARY %s
          AND LOWER(TRIM(process_name)) = 'cutting'
        ORDER BY id
        LIMIT 1
        """,
        (job_card_no,),
    )

    process_row = cursor.fetchone()

    if process_row:

        source["cutting_process_day_id"] = (
            process_row["id"]
        )

        return source, None


    # At upload time the timeline may not yet contain Cutting.
    # Therefore eligibility comes from Process Master route.
    cursor.execute(
        """
        SELECT 1
        FROM job_cards jc

        JOIN item_processes ip
          ON BINARY ip.item_code
           = BINARY jc.child_code

        JOIN processes p
          ON p.id = ip.process_id

        WHERE BINARY jc.job_card_no
            = BINARY %s

          AND LOWER(
                TRIM(
                    p.process_name
                )
              ) = 'cutting'

        LIMIT 1
        """,
        (job_card_no,),
    )

    master_cutting = cursor.fetchone()

    if not master_cutting:

        return (
            None,
            "The Job Card does not contain a Cutting process."
        )


    # Cutting is confirmed in Process Master,
    # but its runtime timeline row does not exist yet.
    source["cutting_process_day_id"] = None

    return source, None

# AUTO_CUT_SIZE_MATCH_MATERIAL_V2
def _resolve_cut_size_for_material(cursor, job_card_no, material_description):
    """
    Find cutting_size from the exact BOM row whose child item
    description matches the already-resolved AUTO material.

    No item-code prefix logic.
    No dependency on A/I.
    Primary BOM path only.
    """

    target = " ".join(
        _clean(material_description).split()
    ).casefold()

    if not target:
        return None

    cursor.execute(
        """
        SELECT child_code
        FROM job_cards
        WHERE BINARY job_card_no = BINARY %s
        LIMIT 1
        """,
        (job_card_no,),
    )

    jc = cursor.fetchone()

    if not jc:
        return None

    root_code = _clean(jc.get("child_code"))

    if not root_code:
        return None

    current_level = [root_code]
    visited = set()

    for _level in range(9):

        if not current_level:
            break

        next_level = []

        for parent_code in current_level:

            parent_key = parent_code.casefold()

            if parent_key in visited:
                continue

            visited.add(parent_key)

            cursor.execute(
                """
                SELECT
                    bl.child_code,
                    bl.cutting_size,
                    i.item_description
                FROM bom_links bl
                LEFT JOIN items i
                    ON BINARY i.item_code
                     = BINARY bl.child_code
                WHERE BINARY bl.parent_code
                    = BINARY %s
                  AND COALESCE(bl.is_alternate, 0) = 0
                ORDER BY bl.id
                """,
                (parent_code,),
            )

            for row in cursor.fetchall():

                description = " ".join(
                    _clean(
                        row.get("item_description")
                    ).split()
                ).casefold()

                if description == target:

                    cut_size = _clean(
                        row.get("cutting_size")
                    )

                    if cut_size:
                        return cut_size

                child_code = _clean(
                    row.get("child_code")
                )

                if (
                    child_code
                    and child_code.casefold() not in visited
                ):
                    next_level.append(child_code)

        current_level = next_level

    return None

def _create_or_reuse_auto_plan(cursor, source, actor):
    source_qty = _as_int(source.get("job_card_qty"), 0) or _as_int(source.get("so_qty"), 0)

    # AUTO_MODEL_SIZE_CLEANUP_V1
    item_name = _clean(source.get("item_name"))
    model_size = item_name

    if item_name:
        marker_pos = item_name.lower().find(" of ")

        if marker_pos >= 0:
            cleaned_model_size = item_name[
                marker_pos + len(" of "):
            ].strip()

            if cleaned_model_size:
                model_size = cleaned_model_size
    # CUTTING_PLAN_JC_DETAILS_SOURCE_V1
    # Material and Cutting Size come directly from Job Card details.
    cut_size = _clean(
        source.get("cutting_size")
    )

    key = (
        source["job_card_no"],
        source["item_id"],
        source["cutting_process_day_id"],
    )
    cursor.execute(
        """
        SELECT *
        FROM cutting_plans
        WHERE source_type = 'AUTO'
          AND BINARY source_job_card_no
              = BINARY %s
          AND plan_batch_no IS NULL
          AND status IN ('Draft', 'Cancelled')
        ORDER BY
            CASE
                WHEN source_item_id = %s THEN 0
                ELSE 1
            END,
            id DESC
        LIMIT 1
        FOR UPDATE
        """,
        (
            source["job_card_no"],
            source["item_id"],
        ),
    )
    existing = cursor.fetchone()

    # CUTTING_PLAN_JC_DETAILS_SOURCE_V1
    # No Process Master / BOM Material or Cut Size resolution here.

    if existing:
        old_status = existing["status"]
        new_status = "Draft" if old_status == "Cancelled" else old_status
        cursor.execute(
            """
            UPDATE cutting_plans
            SET source_type = 'AUTO',
                source_item_id = %s,
                source_process_day_id = %s,
                job_card_no = %s,
                item_name = %s,
                so_no = CASE WHEN COALESCE(TRIM(so_no), '') = '' THEN %s ELSE so_no END,
                planned_date = CASE WHEN planned_date IS NULL THEN %s ELSE planned_date END,
                material_spec = %s,
                cut_size = %s,
                planned_qty = CASE WHEN planned_qty <= 0 THEN %s ELSE planned_qty END,
                remaining_qty = CASE WHEN planned_qty <= 0 THEN GREATEST(%s - completed_qty, 0) ELSE remaining_qty END,
                part = CASE WHEN COALESCE(TRIM(part), '') = '' THEN %s ELSE part END,
                model_size = CASE WHEN COALESCE(TRIM(model_size), '') = '' THEN %s ELSE model_size END,
                status = %s,
                cancelled_at = NULL,
                cancelled_by_id = NULL,
                cancelled_by_name = NULL,
                cancel_reason = NULL,
                updated_by_id = %s,
                updated_by_name = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                source["item_id"],
                source["cutting_process_day_id"],
                source["job_card_no"],
                item_name or None,
                _clean(source.get("so_no")) or None,
                source.get("planned_date") or None,
                _clean(source.get("material")) or None,
                cut_size or None,
                source_qty,
                source_qty,
                _clean(source.get("part")) or None,
                model_size or None,
                new_status,
                actor.get("user_id"),
                actor.get("name"),
                existing["id"],
            ),
        )
        _audit(
            cursor,
            existing["id"],
            "AUTO_REACTIVATED" if old_status == "Cancelled" else "AUTO_DUPLICATE_REUSED",
            actor,
            old_status,
            new_status,
            {"source_key": key},
        )
        return existing["id"], False

    cursor.execute(
        """
        INSERT INTO cutting_plans (
            source_type,
            source_job_card_no,
            source_item_id,
            source_process_day_id,
            job_card_no,
            item_name,
            so_no,
            planned_date,
            material_spec,
            cut_size,
            planned_qty,
            completed_qty,
            remaining_qty,
            part,
            model_size,
            status,
            created_by_id,
            created_by_name,
            updated_by_id,
            updated_by_name
        )
        VALUES (
            'AUTO', %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, 0, %s,
            %s, %s, 'Draft',
            %s, %s, %s, %s
        )
        """,
        (
            source["job_card_no"],
            source["item_id"],
            source["cutting_process_day_id"],
            source["job_card_no"],
            item_name or None,
            _clean(source.get("so_no")) or None,
            source.get("planned_date") or None,
            _clean(source.get("material")) or None,
            cut_size or None,
            source_qty,
            source_qty,
            _clean(source.get("part")) or None,
            model_size or None,
            actor.get("user_id"),
            actor.get("name"),
            actor.get("user_id"),
            actor.get("name"),
        ),
    )
    plan_id = cursor.lastrowid
    _audit(
        cursor,
        plan_id,
        "AUTO_CREATED",
        actor,
        None,
        "Draft",
        {"source_key": key},
    )
    return plan_id, True

@cutting_plan_bp.route("/api/cutting-plan/health", methods=["GET"])
def health():
    actor = _actor()
    if not (
        actor["api_key"]
        or actor["role"] in _PLANNING_ROLES
        or actor["role"] == "operator"
        or is_gaurang_special_user()
    ):
        return jsonify({"success": False, "error": "Access denied."}), 403

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()

        counts = {}
        for table in ("cutting_plans", "cutting_plan_batches", "cutting_plan_audit"):
            cursor.execute(f"SELECT COUNT(*) AS total FROM {table}")
            counts[table] = int(cursor.fetchone()["total"] or 0)

        return jsonify(
            {
                "success": True,
                "message": "Cutting Plan backend is ready.",
                "api_key_access": actor["api_key"],
                "tables": counts,
                "statuses": sorted(_STATUSES),
            }
        )
    except Exception as error:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@cutting_plan_bp.route("/api/cutting-plan/manual", methods=["POST"])
def create_manual():
    actor, denied = _planning_access()
    if denied:
        return denied

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({
            "success": False,
            "error": (
                "Valid JSON request body is required. "
                "Send Content-Type: application/json."
            ),
        }), 400

    # --------------------------------------------------------
    # MULTI_ROW_MANUAL_CUTTING_PLAN_V1
    #
    # Backward compatible:
    # Existing single-row JSON still works.
    #
    # New format:
    # {
    #     "rows": [
    #         {...},
    #         {...}
    #     ]
    # }
    # --------------------------------------------------------

    if "rows" in data:
        rows = data.get("rows")

        if not isinstance(rows, list) or not rows:
            return jsonify({
                "success": False,
                "error": (
                    "rows must be a non-empty list."
                ),
            }), 400
    else:
        rows = [data]

    normalized_rows = []

    for index, row in enumerate(rows, start=1):

        if not isinstance(row, dict):
            return jsonify({
                "success": False,
                "error": (
                    f"Row {index}: valid row data is required."
                ),
            }), 400

        # Move To is retired from the active Cutting Plan workflow.
        move_to = None

        planned_qty = _as_int(
            row.get("planned_qty"),
            0,
        )

        if planned_qty <= 0:
            return jsonify({
                "success": False,
                "error": (
                    f"Row {index}: Planned Quantity must "
                    "be greater than zero."
                ),
            }), 400


        # MANUAL_CUTTING_PLAN_DIRECT_RELEASE_V1
        #
        # There is no Draft -> Release planning stage anymore.
        # A manually created Cutting Plan must be complete
        # before it is saved directly as Released.

        required_fields = [
            (
                "planned_date",
                "Planned Date",
                row.get("planned_date")
                or data.get("planned_date"),
            ),
            (
                "material_spec",
                "Material Specification",
                row.get("material_spec"),
            ),
            (
                "cut_size",
                "Cut Size",
                row.get("cut_size"),
            ),
            (
                "part",
                "Part",
                row.get("part"),
            ),
            (
                "model_size",
                "Model & Size",
                row.get("model_size"),
            ),
        ]


        for field_name, label, value in required_fields:

            if not _clean(value):

                return jsonify({
                    "success": False,
                    "error": (
                        f"Row {index}: {label} is required."
                    ),
                }), 400


        normalized_rows.append({
            "job_card_no": (
                _clean(row.get("job_card_no"))
                or None
            ),
            "item_name": (
                _clean(row.get("item_name"))
                or None
            ),
            "so_no": (
                _clean(row.get("so_no"))
                or None
            ),
            "planned_date": (
                row.get("planned_date")
                or data.get("planned_date")
                or None
            ),
            "material_spec": (
                _clean(row.get("material_spec"))
                or None
            ),
            "cut_size": (
                _clean(row.get("cut_size"))
                or None
            ),
            "planned_qty": planned_qty,
            "part": (
                _clean(row.get("part"))
                or None
            ),
            "model_size": (
                _clean(row.get("model_size"))
                or None
            ),
            "move_to": None,
            "remarks": (
                _clean(row.get("remarks"))
                or _clean(data.get("remarks"))
                or None
            ),
        })

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        _ensure_tables(cursor)
        conn.commit()

        created_ids = []
        plan_batch_no = None

        for line_no, row in enumerate(
            normalized_rows,
            start=1,
        ):

            cursor.execute(
                """
                INSERT INTO cutting_plans (
                    plan_batch_no,
                    source_type,
                    job_card_no,
                    item_name,
                    so_no,
                    planned_date,
                    material_spec,
                    cut_size,
                    planned_qty,
                    completed_qty,
                    remaining_qty,
                    part,
                    model_size,
                    move_to,
                    remarks,
                    status,
                    released_at,
                    released_by_id,
                    released_by_name,
                    created_by_id,
                    created_by_name,
                    updated_by_id,
                    updated_by_name
                )
                VALUES (
                    %s,
                    'MANUAL',
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, 0, %s,
                    %s, %s, %s, %s,
                    'Released',
                    NOW(), %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    plan_batch_no,
                    row["job_card_no"],
                    row["item_name"],
                    row["so_no"],
                    row["planned_date"],
                    row["material_spec"],
                    row["cut_size"],
                    row["planned_qty"],
                    row["planned_qty"],
                    row["part"],
                    row["model_size"],
                    row["move_to"],
                    row["remarks"],

                    # released_by
                    actor.get("user_id"),
                    actor.get("name"),

                    # created_by
                    actor.get("user_id"),
                    actor.get("name"),

                    # updated_by
                    actor.get("user_id"),
                    actor.get("name"),
                ),
            )

            plan_id = cursor.lastrowid

            # First row ID becomes the internal batch number.
            if plan_batch_no is None:

                plan_batch_no = plan_id

                cursor.execute(
                    """
                    UPDATE cutting_plans
                    SET plan_batch_no = %s
                    WHERE id = %s
                    """,
                    (
                        plan_batch_no,
                        plan_id,
                    ),
                )

            created_ids.append(plan_id)

            _audit(
                cursor,
                plan_id,
                "MANUAL_CREATED",
                actor,
                None,
                "Released",
                {
                    "plan_batch_no": plan_batch_no,
                    "line_no": line_no,
                    "auto_released": True,
                    "so_display": (
                        row["so_no"]
                        or "Advance Plan"
                    ),
                    "planned_qty": (
                        row["planned_qty"]
                    ),
                },
            )

        conn.commit()

        placeholders = ", ".join(
            ["%s"] * len(created_ids)
        )

        cursor.execute(
            f"""
            SELECT *
            FROM cutting_plans
            WHERE id IN ({placeholders})
            ORDER BY id
            """,
            tuple(created_ids),
        )

        plans = [
            _serialize(row)
            for row in cursor.fetchall()
        ]

        if len(plans) == 1:

            message = (
                "Manual Cutting Plan created."
            )

        else:

            message = (
                f"Manual Cutting Plan created with "
                f"{len(plans)} rows."
            )

        return jsonify({
            "success": True,
            "message": message,
            "plan_batch_no": plan_batch_no,
            "line_count": len(plans),

            # Keep this for existing single-row JS compatibility.
            "plan": plans[0] if plans else None,

            # New multi-row response.
            "plans": plans,
        }), 201

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


@cutting_plan_bp.route("/api/cutting-plan/auto-test", methods=["POST"])
def auto_test():
    actor = _actor()
    if not actor["api_key"]:
        return jsonify(
            {
                "success": False,
                "error": "This temporary test endpoint requires X-API-Key.",
            }
        ), 403

    data = request.get_json(silent=True) or {}
    job_card_no = _clean(data.get("job_card_no"))
    if not job_card_no:
        return jsonify({"success": False, "error": "job_card_no is required."}), 400

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()

        source, error = _resolve_auto_source(
            cursor,
            job_card_no,
            _as_int(data.get("item_id"), 0) or None,
            _clean(data.get("item_name")) or None,
        )
        if error:
            return jsonify({"success": False, "error": error}), 400

        plan_id, created = _create_or_reuse_auto_plan(cursor, source, actor)
        conn.commit()
        cursor.execute("SELECT * FROM cutting_plans WHERE id = %s", (plan_id,))
        return jsonify(
            {
                "success": True,
                "created": created,
                "message": "Automatic Cutting Plan draft created."
                if created
                else "Existing automatic Cutting Plan reused; no duplicate was created.",
                "plan": _serialize(cursor.fetchone()),
            }
        ), 201 if created else 200
    except Exception as error:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# ============================================================
# AUTO CUTTING PLAN - CREATE PHYSICAL BATCH
# ============================================================
# AUTO_CUTTING_PLAN_BATCH_API_V1
#
# Selected AUTO requirements remain individual cutting_plans
# rows but receive one common plan_batch_no.
#
# No additional batch header table is required.
#
# Move To is retired from the active Cutting Plan workflow.
# Cut Size is intentionally NOT validated here yet because
# its AUTO source rule is still under discussion.
# ============================================================

@cutting_plan_bp.route(
    "/api/cutting-plan/auto-batch",
    methods=["POST"],
)
def create_auto_cutting_batch():

    actor, denied = _planning_access()

    if denied:
        return denied


    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "Valid JSON request body is required.",
        }), 400


    raw_plan_ids = data.get("plan_ids")

    if not isinstance(raw_plan_ids, list) or not raw_plan_ids:
        return jsonify({
            "success": False,
            "error": (
                "plan_ids must be a non-empty list "
                "of AUTO Cutting Plan IDs."
            ),
        }), 400


    plan_ids = []

    for raw_id in raw_plan_ids:

        plan_id = _as_int(raw_id, 0)

        if plan_id <= 0:
            return jsonify({
                "success": False,
                "error": (
                    "Every plan_id must be a valid "
                    "positive Cutting Plan ID."
                ),
            }), 400

        if plan_id in plan_ids:
            return jsonify({
                "success": False,
                "error": (
                    f"Duplicate plan_id supplied: {plan_id}"
                ),
            }), 400

        plan_ids.append(plan_id)


    conn = None
    cursor = None

    try:

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        _ensure_tables(cursor)

        conn.commit()

        conn.start_transaction()

        # AUTO_BATCH_CUT_SIZE_REQUIRED_V1
        # A physical AUTO Cutting Plan batch must never
        # be created when any selected row has blank Cut Size.

        cut_size_placeholders = ", ".join(
            ["%s"] * len(plan_ids)
        )

        cursor.execute(
            f"""
            SELECT
                id,
                source_job_card_no,
                job_card_no
            FROM cutting_plans
            WHERE id IN ({cut_size_placeholders})
              AND (
                    cut_size IS NULL
                    OR TRIM(cut_size) = ''
                  )
            LIMIT 1
            """,
            tuple(plan_ids),
        )

        missing_cut_size_plan = cursor.fetchone()

        if missing_cut_size_plan:

            conn.rollback()

            reference = (
                _clean(
                    missing_cut_size_plan.get(
                        "source_job_card_no"
                    )
                )
                or
                _clean(
                    missing_cut_size_plan.get(
                        "job_card_no"
                    )
                )
                or
                f"AUTO #{missing_cut_size_plan['id']}"
            )

            return jsonify({
                "success": False,
                "error": (
                    "Cut Size is required before "
                    f"Create Batch. Check {reference}."
                ),
                "validation_errors": [
                    (
                        "Cut Size is required before "
                        f"Create Batch. Check {reference}."
                    )
                ],
            }), 400



        placeholders = ", ".join(
            ["%s"] * len(plan_ids)
        )


        # Lock every selected requirement so two users cannot
        # create different batches from the same AUTO rows.
        cursor.execute(
            f"""
            SELECT *
            FROM cutting_plans
            WHERE id IN ({placeholders})
            ORDER BY id
            FOR UPDATE
            """,
            tuple(plan_ids),
        )


        plans = cursor.fetchall()


        # ====================================================
        # All requested IDs must exist
        # ====================================================

        found_ids = {
            int(plan["id"])
            for plan in plans
        }

        missing_ids = [
            plan_id
            for plan_id in plan_ids
            if plan_id not in found_ids
        ]

        if missing_ids:

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Cutting Plan ID(s) not found: "
                    + ", ".join(
                        str(value)
                        for value in missing_ids
                    )
                ),
                "missing_plan_ids": missing_ids,
            }), 404


        # ====================================================
        # Validate every selected row
        # ====================================================

        validation_errors = []


        for plan in plans:

            plan_id = int(plan["id"])

            source_type = (
                _clean(
                    plan.get("source_type")
                ).upper()
            )

            status = (
                _clean(
                    plan.get("status")
                )
                or "Draft"
            )


            if source_type != "AUTO":

                validation_errors.append(
                    f"ID {plan_id}: "
                    "only AUTO requirements can be "
                    "added through AUTO Batch."
                )


            if plan.get("plan_batch_no") is not None:

                validation_errors.append(
                    f"ID {plan_id}: already belongs "
                    f"to batch {plan.get('plan_batch_no')}."
                )


            if status != "Draft":

                validation_errors.append(
                    f"ID {plan_id}: status must be "
                    f"Draft, current status is {status}."
                )


            # Move To is retired from the active Cutting Plan workflow.


            if _as_int(
                plan.get("planned_qty"),
                0,
            ) <= 0:

                validation_errors.append(
                    f"ID {plan_id}: Planned Quantity "
                    "must be greater than zero."
                )


        if validation_errors:

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Selected AUTO requirements "
                    "are not ready for batching."
                ),
                "validation_errors": (
                    validation_errors
                ),
            }), 400


        # ====================================================
        # BATCH NUMBER
        #
        # Same design as Manual Cutting Plan:
        # first/lowest underlying Cutting Plan ID becomes the
        # internal plan_batch_no.
        # ====================================================

        plan_batch_no = min(
            int(plan["id"])
            for plan in plans
        )


        # ====================================================
        # Assign one batch + release each selected requirement
        # ====================================================

        for line_no, plan in enumerate(
            plans,
            start=1,
        ):

            plan_id = int(plan["id"])

            old_status = (
                _clean(plan.get("status"))
                or "Draft"
            )


            cursor.execute(
                """
                UPDATE cutting_plans
                SET plan_batch_no = %s,

                    status = 'Released',

                    released_at = COALESCE(
                        released_at,
                        NOW()
                    ),

                    released_by_id = %s,
                    released_by_name = %s,

                    updated_by_id = %s,
                    updated_by_name = %s,
                    updated_at = NOW()

                WHERE id = %s
                """,
                (
                    plan_batch_no,

                    actor.get("user_id"),
                    actor.get("name"),

                    actor.get("user_id"),
                    actor.get("name"),

                    plan_id,
                ),
            )


            _audit(
                cursor,
                plan_id,
                "AUTO_BATCH_CREATED",
                actor,
                old_status,
                "Released",
                {
                    "plan_batch_no": (
                        plan_batch_no
                    ),
                    "line_no": line_no,
                    "batch_size": len(plans),
                    "selected_plan_ids": (
                        sorted(plan_ids)
                    ),
                    "cut_size_validation": (
                        "ON_HOLD"
                    ),
                    "auto_released": True,
                },
            )


        conn.commit()


        # ====================================================
        # Return complete physical batch
        # ====================================================

        cursor.execute(
            """
            SELECT *
            FROM cutting_plans
            WHERE plan_batch_no = %s
            ORDER BY id
            """,
            (
                plan_batch_no,
            ),
        )


        batch_plans = [
            _serialize(row)
            for row in cursor.fetchall()
        ]


        return jsonify({
            "success": True,

            "message": (
                f"AUTO Cutting Plan batch "
                f"{plan_batch_no} created with "
                f"{len(batch_plans)} rows."
            ),

            "plan_batch_no": (
                plan_batch_no
            ),

            "line_count": (
                len(batch_plans)
            ),

            "plan_ids": [
                plan["id"]
                for plan in batch_plans
            ],

            "plans": batch_plans,
        }), 201


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


@cutting_plan_bp.route("/api/cutting-plan/plans", methods=["GET"])
def list_plans():
    actor = _actor()
    if not (
        actor["api_key"]
        or actor["role"] in _PLANNING_ROLES
        or actor["role"] == "operator"
        or is_gaurang_special_user()
    ):
        return jsonify({"success": False, "error": "Access denied."}), 403

    status = _clean(request.args.get("status"))
    if status and status not in _STATUSES:
        return jsonify({"success": False, "error": "Invalid status filter."}), 400

    source_type = _clean(request.args.get("source_type")).upper()
    if source_type and source_type not in {"AUTO", "MANUAL"}:
        return jsonify({"success": False, "error": "source_type must be AUTO or MANUAL."}), 400

    clauses = ["1 = 1"]
    params = []

    # AUTO_PENDING_LIST_FILTER_V1
    #
    # Normal Cutting Plan list = printable/formed plans only.
    # Pending AUTO requirements are loaded separately by the
    # planning workbench using include_pending_auto=1.
    include_pending_auto = (
        _clean(
            request.args.get("include_pending_auto")
        ).lower()
        in {"1", "true", "yes", "on"}
    )

    if not include_pending_auto:
        clauses.append(
            """NOT (
                source_type = 'AUTO'
                AND status = 'Draft'
                AND plan_batch_no IS NULL
            )"""
        )
    if status:
        clauses.append("status = %s")
        params.append(status)
    if source_type:
        clauses.append("source_type = %s")
        params.append(source_type)
    if actor["role"] == "operator" and not actor["api_key"]:
        clauses.append("status IN ('Released', 'Partially Completed')")

    limit = min(max(_as_int(request.args.get("limit"), 100), 1), 500)
    params.append(limit)

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()

        # OPERATOR_CUTTING_PLAN_VISIBILITY_V1
        # Operators may see Cutting Plans only when they are
        # actually assigned to the Cutting process.
        if (
            actor["role"] == "operator"
            and not actor["api_key"]
            and not _operator_has_cutting_access(
                cursor,
                actor.get("user_id"),
            )
        ):
            return jsonify({
                "success": True,
                "plans": [],
                "total": 0,
                "message": (
                    "No Cutting Plans available because this operator "
                    "is not assigned to the Cutting process."
                ),
            })

        cursor.execute(
            f"""
            SELECT *
            FROM cutting_plans
            WHERE {' AND '.join(clauses)}
            ORDER BY planned_date, id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = [_serialize(row) for row in cursor.fetchall()]
        return jsonify({"success": True, "plans": rows, "total": len(rows)})
    except Exception as error:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



# ============================================================
# ============================================================
# CUTTING_PLAN_PM_SYNC_ON_BATCH_V2
#
# IMPORTANT BUSINESS RULE:
#
# Pending-row editing does NOT update Process Master.
#
# PM is updated only when user commits the selected AUTO row by:
#
#   1. Create Batch
#   2. Add to Existing Batch
#
# Material:
#   exact primary Raw Material BOM relation.
#
# Cut Size:
#   exact bom_links.cutting_size.
#
# All changes remain inside caller's existing DB transaction.
# Any unsafe/ambiguous PM target raises an error and therefore
# rolls back the whole batch action.
# ============================================================

def _sync_cutting_plan_batch_values_to_process_master(
    cursor,
    plan_id,
):

    # --------------------------------------------------------
    # LOAD FINAL CUTTING PLAN VALUE
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            cp.id,
            cp.source_type,
            cp.source_item_id,

            COALESCE(
                NULLIF(
                    cp.source_job_card_no,
                    ''
                ),
                cp.job_card_no
            ) AS job_card_no,

            cp.material_spec,
            cp.cut_size,

            jc.child_code,

            ji.material
                AS source_job_card_material

        FROM cutting_plans cp

        JOIN job_cards jc
          ON jc.job_card_no
                COLLATE utf8mb4_unicode_ci
           =
             COALESCE(
                NULLIF(
                    cp.source_job_card_no,
                    ''
                ),
                cp.job_card_no
             )
                COLLATE utf8mb4_unicode_ci

        LEFT JOIN job_card_items ji
          ON ji.id = cp.source_item_id

        WHERE cp.id = %s

        LIMIT 1
        """,
        (plan_id,),
    )


    plan = cursor.fetchone()


    if not plan:

        raise RuntimeError(
            "Cutting Plan was not found during "
            "Process Master synchronization."
        )


    if (
        _clean(
            plan.get("source_type")
        ).upper()
        != "AUTO"
    ):

        return {
            "updated": False,
            "reason": "MANUAL_PLAN",
        }


    item_code = _clean(
        plan.get("child_code")
    )


    if not item_code:

        raise RuntimeError(
            "Process Master update failed: "
            "Job Card Child Code is missing."
        )


    final_material = _clean(
        plan.get("material_spec")
    )

    final_cut_size = _clean(
        plan.get("cut_size")
    )


    if not final_material:

        raise RuntimeError(
            "Process Master update failed: "
            "Material is blank."
        )


    if not final_cut_size:

        raise RuntimeError(
            "Process Master update failed: "
            "Cut Size is blank."
        )


    # --------------------------------------------------------
    # LOAD PRIMARY RAW-MATERIAL BOM ROWS
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            bl.id AS bom_link_id,
            bl.parent_code,
            bl.child_code AS raw_item_code,
            bl.cutting_size,

            ri.item_description
                AS raw_item_description,

            ri.item_type
                AS raw_item_type

        FROM bom_links bl

        JOIN items ri
          ON ri.item_code
                COLLATE utf8mb4_unicode_ci
           =
             bl.child_code
                COLLATE utf8mb4_unicode_ci

        WHERE
            bl.parent_code
                COLLATE utf8mb4_unicode_ci
            =
            %s
                COLLATE utf8mb4_unicode_ci

            AND bl.make_buy = 'I'

            AND COALESCE(
                    bl.is_alternate,
                    0
                ) = 0

        ORDER BY
            bl.id

        FOR UPDATE
        """,
        (item_code,),
    )


    candidates = (
        cursor.fetchall()
        or []
    )


    if not candidates:

        raise RuntimeError(
            "Process Master update failed: "
            f"no primary Raw Material BOM row exists "
            f"for {item_code}."
        )


    # --------------------------------------------------------
    # IDENTIFY EXACT BOM ROW
    # --------------------------------------------------------

    target = None


    if len(candidates) == 1:

        target = candidates[0]


    else:

        source_material = _clean(
            plan.get(
                "source_job_card_material"
            )
        )


        # First preference:
        # original JC material identifies the old BOM row.
        if source_material:

            matches = [
                row
                for row in candidates
                if _clean(
                    row.get(
                        "raw_item_description"
                    )
                ).casefold()
                ==
                source_material.casefold()
            ]


            if len(matches) == 1:

                target = matches[0]


        # Second preference:
        # current CP material already matches one BOM row.
        if target is None:

            matches = [
                row
                for row in candidates
                if _clean(
                    row.get(
                        "raw_item_description"
                    )
                ).casefold()
                ==
                final_material.casefold()
            ]


            if len(matches) == 1:

                target = matches[0]


    if target is None:

        raise RuntimeError(
            "Process Master update blocked: "
            f"multiple primary Raw Material rows exist "
            f"for {item_code}; exact BOM row could not "
            "be identified safely."
        )


    bom_link_id = int(
        target["bom_link_id"]
    )

    old_raw_item_code = _clean(
        target.get(
            "raw_item_code"
        )
    )

    old_material = _clean(
        target.get(
            "raw_item_description"
        )
    )

    old_cut_size = _clean(
        target.get(
            "cutting_size"
        )
    )


    result = {
        "updated": False,
        "job_card_no":
            plan.get("job_card_no"),

        "item_code":
            item_code,

        "bom_link_id":
            bom_link_id,

        "old_raw_item_code":
            old_raw_item_code,

        "new_raw_item_code":
            old_raw_item_code,

        "material": {
            "old": old_material,
            "new": final_material,
            "changed": False,
        },

        "cut_size": {
            "old": old_cut_size,
            "new": final_cut_size,
            "changed": False,
        },
    }


    # --------------------------------------------------------
    # MATERIAL
    #
    # Preferred:
    # If an existing RAW_MATERIAL master item already has the
    # newly entered description, relink ONLY this exact BOM row.
    #
    # Otherwise:
    # rename the existing raw-material item ONLY when that raw
    # item is not shared by other primary BOMs.
    # --------------------------------------------------------

    if (
        final_material.casefold()
        != old_material.casefold()
    ):

        # CUTTING_PLAN_PM_MATERIAL_ITEMTYPE_FIX_V4
        #
        # In existing Process Master data, raw-material BOM
        # children may be stored as items.item_type = 'PART'.
        # Therefore identify material items by the actual BOM
        # child/code family, not by item_type.

        material_code_prefix = (
            old_raw_item_code.rstrip(
                "0123456789"
            )
        )

        if not material_code_prefix:
            raise RuntimeError(
                "Process Master Material update failed: "
                f"invalid material item code "
                f"{old_raw_item_code}."
            )

        cursor.execute(
            """
            SELECT
                item_code

            FROM items

            WHERE
                TRIM(
                    item_description
                )
                COLLATE utf8mb4_unicode_ci
                =
                %s
                COLLATE utf8mb4_unicode_ci

                AND item_code LIKE %s

            ORDER BY
                item_code
            """,
            (
                final_material,
                material_code_prefix + "%",
            ),
        )


        existing_material_items = (
            cursor.fetchall()
            or []
        )


        if len(existing_material_items) == 1:

            # CUTTING_PLAN_PM_EXISTING_ALTERNATE_SWAP_V6
            #
            # The corrected material may already be linked to this same
            # parent as an alternate BOM row. In that case, swap the
            # primary/alternate flags instead of creating a duplicate
            # parent-child combination.

            new_raw_item_code = _clean(
                existing_material_items[0].get(
                    "item_code"
                )
            )

            cursor.execute(
                """
                SELECT
                    id,
                    is_alternate,
                    cutting_size
                FROM bom_links
                WHERE
                    parent_code
                        COLLATE utf8mb4_unicode_ci
                    =
                    %s
                        COLLATE utf8mb4_unicode_ci
                    AND child_code
                        COLLATE utf8mb4_unicode_ci
                    =
                    %s
                        COLLATE utf8mb4_unicode_ci
                LIMIT 1
                FOR UPDATE
                """,
                (
                    item_code,
                    new_raw_item_code,
                ),
            )

            existing_parent_link = cursor.fetchone()

            if (
                existing_parent_link
                and int(existing_parent_link.get("id")) != bom_link_id
            ):
                existing_link_id = int(
                    existing_parent_link.get("id")
                )
                existing_is_alternate = int(
                    existing_parent_link.get("is_alternate") or 0
                )

                if existing_is_alternate != 1:
                    raise RuntimeError(
                        "Process Master Material update blocked: "
                        f"material {new_raw_item_code} is already "
                        f"linked to parent {item_code}, but the "
                        "existing relationship is not an alternate BOM row."
                    )

                cursor.execute(
                    """
                    UPDATE bom_links
                    SET
                        is_alternate = 1,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (bom_link_id,),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Process Master Material update failed: "
                        f"old primary BOM Link {bom_link_id} "
                        "could not be changed to alternate."
                    )

                # CUTTING_PLAN_PM_ALTERNATE_CUTSIZE_FIX_V7
                # Promote only here. The common Cut Size block below
                # updates cutting_size exactly once.
                cursor.execute(
                    """
                    UPDATE bom_links
                    SET
                        is_alternate = 0,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (existing_link_id,),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Process Master Material update failed: "
                        f"existing alternate BOM Link {existing_link_id} "
                        "could not be promoted to primary."
                    )

                result["old_primary_bom_link_id"] = bom_link_id
                result["bom_link_id"] = existing_link_id
                result["existing_alternate_promoted"] = True
                result["new_raw_item_code"] = new_raw_item_code

                bom_link_id = existing_link_id
                old_cut_size = _clean(
                    existing_parent_link.get("cutting_size")
                )
                result["cut_size"]["old"] = old_cut_size

            else:
                cursor.execute(
                    """
                    UPDATE bom_links
                    SET
                        child_code = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        new_raw_item_code,
                        bom_link_id,
                    ),
                )

                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Process Master Material update failed: "
                        f"BOM Link {bom_link_id} could not be relinked."
                    )

                result["new_raw_item_code"] = new_raw_item_code


        elif len(existing_material_items) > 1:

            raise RuntimeError(
                "Process Master Material update blocked: "
                f"more than one RAW_MATERIAL item is named "
                f"'{final_material}'."
            )


        else:

            # Check whether old raw item is shared.
            cursor.execute(
                """
                SELECT
                    COUNT(
                        DISTINCT parent_code
                    ) AS usage_count

                FROM bom_links

                WHERE
                    child_code
                        COLLATE utf8mb4_unicode_ci
                    =
                    %s
                        COLLATE utf8mb4_unicode_ci

                    AND make_buy = 'I'

                    AND COALESCE(
                            is_alternate,
                            0
                        ) = 0
                """,
                (old_raw_item_code,),
            )


            usage_count = int(
                (
                    cursor.fetchone()
                    or {}
                ).get(
                    "usage_count"
                )
                or 0
            )


            if usage_count > 1:

                # CUTTING_PLAN_PM_SHARED_MATERIAL_CLONE_V3
                #
                # Never rename a RAW_MATERIAL item shared by
                # several BOM parents. Create a new material
                # master item and relink ONLY this BOM row.

                old_code = old_raw_item_code

                prefix = old_code.rstrip(
                    "0123456789"
                )

                numeric_part = old_code[
                    len(prefix):
                ]

                if not prefix or not numeric_part.isdigit():
                    raise RuntimeError(
                        "Process Master Material update failed: "
                        f"cannot generate a new Raw Material code "
                        f"from {old_code}."
                    )

                code_width = len(
                    numeric_part
                )

                # Lock/read the source Raw Material master row.
                cursor.execute(
                    """
                    SELECT
                        item_type,
                        make_default,
                        material,
                        size,
                        part_name
                    FROM items
                    WHERE item_code = %s
                    FOR UPDATE
                    """,
                    (old_code,),
                )

                source_raw_item = (
                    cursor.fetchone()
                    or {}
                )

                if not source_raw_item:
                    raise RuntimeError(
                        "Process Master Material update failed: "
                        f"source Raw Material {old_code} "
                        "was not found."
                    )


                # Find highest numeric item code using same prefix.
                cursor.execute(
                    """
                    SELECT item_code
                    FROM items
                    WHERE item_code LIKE %s
                    ORDER BY item_code DESC
                    """,
                    (
                        prefix + "%",
                    ),
                )

                max_no = 0

                for code_row in (
                    cursor.fetchall()
                    or []
                ):

                    existing_code = _clean(
                        code_row.get(
                            "item_code"
                        )
                    )

                    suffix = existing_code[
                        len(prefix):
                    ]

                    if suffix.isdigit():

                        max_no = max(
                            max_no,
                            int(suffix),
                        )


                # Find next free code.
                next_no = max_no + 1

                while True:

                    new_raw_item_code = (
                        prefix
                        + str(next_no).zfill(
                            code_width
                        )
                    )

                    cursor.execute(
                        """
                        SELECT 1
                        FROM items
                        WHERE item_code = %s
                        LIMIT 1
                        """,
                        (
                            new_raw_item_code,
                        ),
                    )

                    if not cursor.fetchone():
                        break

                    next_no += 1


                # Create NEW Raw Material master item.
                cursor.execute(
                    """
                    INSERT INTO items
                    (
                        item_code,
                        item_description,
                        item_type,
                        make_default,
                        material,
                        size,
                        part_name
                    )
                    VALUES
                    (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        new_raw_item_code,
                        final_material,
                        source_raw_item.get(
                            "item_type"
                        ) or "PART",
                        source_raw_item.get(
                            "make_default"
                        ),
                        source_raw_item.get(
                            "material"
                        ),
                        source_raw_item.get(
                            "size"
                        ),
                        source_raw_item.get(
                            "part_name"
                        ),
                    ),
                )


                # Relink ONLY the exact BOM row being corrected.
                cursor.execute(
                    """
                    UPDATE bom_links

                    SET
                        child_code = %s,
                        updated_at = NOW()

                    WHERE id = %s
                    """,
                    (
                        new_raw_item_code,
                        bom_link_id,
                    ),
                )


                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Process Master Material update failed: "
                        f"BOM Link {bom_link_id} "
                        "could not be relinked."
                    )


                result[
                    "new_raw_item_code"
                ] = new_raw_item_code

                result[
                    "material_master_created"
                ] = True


            else:

                # Material belongs only to this BOM parent,
                # therefore renaming the existing Raw Material
                # master item is safe.

                cursor.execute(
                    """
                    UPDATE items

                    SET
                        item_description = %s,
                        updated_at = NOW()

                    WHERE item_code = %s
                    """,
                    (
                        final_material,
                        old_raw_item_code,
                    ),
                )


                if cursor.rowcount != 1:

                    raise RuntimeError(
                        "Process Master Material update failed "
                        f"for Raw Material {old_raw_item_code}."
                    )


        result["material"][
            "changed"
        ] = True

        result["updated"] = True


    # --------------------------------------------------------
    # CUT SIZE
    # Exact BOM link only.
    # --------------------------------------------------------

    if final_cut_size != old_cut_size:

        cursor.execute(
            """
            UPDATE bom_links

            SET
                cutting_size = %s,
                updated_at = NOW()

            WHERE id = %s
            """,
            (
                final_cut_size,
                bom_link_id,
            ),
        )


        if cursor.rowcount != 1:

            raise RuntimeError(
                "Process Master Cut Size update failed "
                f"for BOM Link {bom_link_id}."
            )


        result["cut_size"][
            "changed"
        ] = True

        result["updated"] = True


    return result


# CUTTING_PLAN_PM_SYNC_ON_BATCH_V2_END



# CUTTING_PLAN_EDIT_API_V1_START
@cutting_plan_bp.route(
    "/api/cutting-plan/<int:plan_id>",
    methods=["PATCH", "PUT"],
)
def edit_cutting_plan(plan_id):
    """
    Edit planning details without moving the Job Card process.

    Allowed for API key, Admin, Supervisor and PPC.
    Editable statuses: Draft, Released and Partially Completed.
    """
    actor, denied = _planning_access()
    if denied:
        return denied

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({
            "success": False,
            "error": "Valid non-empty JSON request body is required.",
        }), 400

    allowed_fields = {
        "job_card_no",
        "item_name",
        "so_no",
        "planned_date",
        "material_spec",
        "cut_size",
        "planned_qty",
        "part",
        "model_size",
        "remarks",
    }

    supplied_fields = [field for field in allowed_fields if field in data]

    if not supplied_fields:
        return jsonify({
            "success": False,
            "error": "No editable Cutting Plan fields were supplied.",
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()
        conn.start_transaction()

        plan = _get_plan_for_update(cursor, plan_id)

        if not plan:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Cutting Plan not found.",
            }), 404

        current_status = _clean(plan.get("status")) or "Draft"

        if current_status in {"Completed", "Cancelled"}:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": (
                    f"{current_status} Cutting Plan cannot be edited "
                    "through the normal planning edit API."
                ),
            }), 409

        updates = {}
        changes = {}

        text_fields = {
            "job_card_no",
            "item_name",
            "so_no",
            "material_spec",
            "cut_size",
            "part",
            "model_size",
            "remarks",
        }

        for field in text_fields:
            if field not in data:
                continue

            new_value = _clean(data.get(field)) or None
            old_value = plan.get(field)

            if new_value != old_value:
                updates[field] = new_value
                changes[field] = {
                    "old": old_value,
                    "new": new_value,
                }

        for field in ("planned_date",):
            if field not in data:
                continue

            new_value = data.get(field) or None
            old_value = plan.get(field)

            old_compare = _format(old_value)
            new_compare = _clean(new_value) or None

            if new_compare != old_compare:
                updates[field] = new_value
                changes[field] = {
                    "old": old_compare,
                    "new": new_compare,
                }

        # Legacy move_to values are intentionally not editable.

        planned_qty = _as_int(plan.get("planned_qty"), 0)
        completed_qty = _as_int(plan.get("completed_qty"), 0)

        if "planned_qty" in data:
            submitted_qty = _as_int(data.get("planned_qty"), 0)

            if submitted_qty <= 0:
                conn.rollback()
                return jsonify({
                    "success": False,
                    "error": "Planned Quantity must be greater than zero.",
                }), 400

            if submitted_qty != planned_qty:
                updates["planned_qty"] = submitted_qty
                changes["planned_qty"] = {
                    "old": planned_qty,
                    "new": submitted_qty,
                }

            planned_qty = submitted_qty

        if not updates:
            conn.rollback()
            return jsonify({
                "success": True,
                "message": "No Cutting Plan values changed.",
                "plan": _serialize(plan),
            })

        remaining_qty = max(planned_qty - completed_qty, 0)
        variance_qty = completed_qty - planned_qty if completed_qty > 0 else 0

        # Planning edits must not complete a Cutting Plan automatically.
        new_status = current_status

        updates["remaining_qty"] = remaining_qty
        updates["variance_qty"] = variance_qty

        if new_status != current_status:
            updates["status"] = new_status
            changes["status"] = {
                "old": current_status,
                "new": new_status,
            }

        updates["updated_by_id"] = actor.get("user_id")
        updates["updated_by_name"] = actor.get("name")

        set_parts = [f"{field} = %s" for field in updates]
        values = list(updates.values())

        set_parts.append("updated_at = NOW()")
        values.append(plan_id)

        cursor.execute(
            f"""
            UPDATE cutting_plans
            SET {", ".join(set_parts)}
            WHERE id = %s
            """,
            tuple(values),
        )

        _audit(
            cursor,
            plan_id,
            "PLAN_UPDATED",
            actor,
            current_status,
            new_status,
            {
                "changes": changes,
                "job_card_process_moved": False,
            },
        )

        conn.commit()

        cursor.execute(
            "SELECT * FROM cutting_plans WHERE id = %s",
            (plan_id,),
        )
        updated_plan = cursor.fetchone()

        return jsonify({
            "success": True,
            "message": "Cutting Plan updated.",
            "plan": _serialize(updated_plan),
            "changed_fields": sorted(changes.keys()),
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
# CUTTING_PLAN_EDIT_API_V1_END


@cutting_plan_bp.route("/api/cutting-plan/<int:plan_id>/release", methods=["POST"])
def release_plan(plan_id):
    actor, denied = _planning_access()
    if denied:
        return denied

    conn = cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()
        plan = _get_plan_for_update(cursor, plan_id)
        if not plan:
            return jsonify({"success": False, "error": "Cutting Plan not found."}), 404
        if plan["status"] in {"Completed", "Cancelled"}:
            return jsonify(
                {
                    "success": False,
                    "error": f"{plan['status']} plan cannot be released.",
                }
            ), 409

        missing = _release_missing(plan)
        if missing:
            return jsonify(
                {
                    "success": False,
                    "error": "Complete these fields before release: " + ", ".join(missing),
                    "missing_fields": missing,
                }
            ), 400

        old_status = plan["status"]
        completed = _as_int(plan.get("completed_qty"), 0)
        new_status = "Partially Completed" if completed else "Released"
        cursor.execute(
            """
            UPDATE cutting_plans
            SET remaining_qty = GREATEST(planned_qty - completed_qty, 0),
                status = %s,
                released_at = COALESCE(released_at, NOW()),
                released_by_id = %s,
                released_by_name = %s,
                updated_by_id = %s,
                updated_by_name = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                new_status,
                actor.get("user_id"),
                actor.get("name"),
                actor.get("user_id"),
                actor.get("name"),
                plan_id,
            ),
        )
        _audit(cursor, plan_id, "PLAN_RELEASED", actor, old_status, new_status)
        conn.commit()
        cursor.execute("SELECT * FROM cutting_plans WHERE id = %s", (plan_id,))
        return jsonify(
            {
                "success": True,
                "message": "Cutting Plan released.",
                "plan": _serialize(cursor.fetchone()),
            }
        )
    except Exception as error:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(error)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()






# ============================================================
# CUTTING PLAN PRINT API
# ============================================================

@cutting_plan_bp.route(
    "/api/cutting-plan/<int:plan_id>/print",
    methods=["GET"]
)
def print_cutting_plan(plan_id):

    conn = cursor = None

    try:

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT *
            FROM cutting_plans
            WHERE id = %s
            """,
            (plan_id,)
        )

        plan = cursor.fetchone()


        if not plan:

            return jsonify({
                "success": False,
                "error": "Cutting Plan not found."
            }), 404



        return jsonify({
            "success": True,
            "plan": _serialize(plan)
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







# ============================================================
# CUTTING PLAN PRINT PAGE
# ============================================================

@cutting_plan_bp.route(
    "/cutting-plan/<int:plan_id>/print",
    methods=["GET"]
)
def cutting_plan_print_page(plan_id):

    conn = cursor = None

    try:

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)


        cursor.execute(
            """
            SELECT *
            FROM cutting_plans
            WHERE id = %s
            """,
            (plan_id,)
        )


        plan = cursor.fetchone()


        if not plan:

            return "Cutting Plan not found", 404


        # BATCHWISE_CUTTING_PLAN_PRINT_V1
        #
        # If this record belongs to a Manual Cutting Plan batch,
        # print every record created in that same batch.
        #
        # Legacy / old records with no plan_batch_no continue
        # printing as a single-record sheet.

        plan_batch_no = plan.get("plan_batch_no")


        if plan_batch_no is not None:

            cursor.execute(
                """
                SELECT *
                FROM cutting_plans
                WHERE plan_batch_no = %s
                ORDER BY id
                """,
                (plan_batch_no,)
            )

            batch_rows = cursor.fetchall()

        else:

            batch_rows = [plan]


        plans = [
            _serialize(row)
            for row in batch_rows
        ]



        return render_template(
            "cutting_plan_print.html",
            plans=plans,
            plan=plans[0] if plans else _serialize(plan)
        )


    except Exception as e:

        return str(e), 500


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()



# CUTTING_PLAN_CANCEL_API_V1_START
@cutting_plan_bp.route(
    "/api/cutting-plan/<int:plan_id>/cancel",
    methods=["POST"],
)
def cancel_cutting_plan(plan_id):
    """Cancel a Draft, Released or Partially Completed Cutting Plan.

    Cancellation keeps all plan and batch history. It does not move the
    Job Card process. A mandatory reason is recorded in both the main plan
    and cutting_plan_audit.
    """
    actor, denied = _planning_access()
    if denied:
        return denied

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "Valid JSON request body is required.",
        }), 400

    cancel_reason = _clean(data.get("cancel_reason"))

    if not cancel_reason:
        return jsonify({
            "success": False,
            "error": "Cancellation reason is required.",
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()
        conn.start_transaction()

        plan = _get_plan_for_update(cursor, plan_id)

        if not plan:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Cutting Plan not found.",
            }), 404

        old_status = _clean(plan.get("status")) or "Draft"

        if old_status == "Cancelled":
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Cutting Plan is already cancelled.",
            }), 409

        if old_status == "Completed":
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Completed Cutting Plan cannot be cancelled.",
            }), 409

        cursor.execute(
            """
            UPDATE cutting_plans
            SET status = 'Cancelled',
                cancelled_at = NOW(),
                cancelled_by_id = %s,
                cancelled_by_name = %s,
                cancel_reason = %s,
                updated_by_id = %s,
                updated_by_name = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                actor.get("user_id"),
                actor.get("name"),
                cancel_reason,
                actor.get("user_id"),
                actor.get("name"),
                plan_id,
            ),
        )

        _audit(
            cursor,
            plan_id,
            "PLAN_CANCELLED",
            actor,
            old_status,
            "Cancelled",
            {
                "cancel_reason": cancel_reason,
                "completed_qty_at_cancellation": _as_int(
                    plan.get("completed_qty"), 0
                ),
                "job_card_process_moved": False,
            },
        )

        conn.commit()

        cursor.execute(
            "SELECT * FROM cutting_plans WHERE id = %s",
            (plan_id,),
        )
        updated_plan = cursor.fetchone()

        return jsonify({
            "success": True,
            "message": "Cutting Plan cancelled. History was preserved.",
            "plan": _serialize(updated_plan),
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
# CUTTING_PLAN_CANCEL_API_V1_END


@cutting_plan_bp.route("/api/cutting-plan/<int:plan_id>/batches", methods=["POST"])
def add_batch(plan_id):
    """
    Record actual cut quantity.

    Rules:
    - Actual Cut Qty may be below, equal to or above Planned Qty.
    - Partial entries remain Partially Completed.
    - complete_plan=true closes the plan even below Planned Qty.
    - Final short or excess quantity requires remarks.
    - Extra quantity is recorded only, without carry-forward or batch merging.
    - The Job Card process is never moved here.
    """
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or not data:
        return jsonify({
            "success": False,
            "error": "Valid non-empty JSON request body is required.",
        }), 400

    cut_qty = _as_int(data.get("cut_qty"), 0)
    if cut_qty <= 0:
        return jsonify({
            "success": False,
            "error": "Cut Quantity must be greater than zero.",
        }), 400

    remarks = _clean(data.get("remarks"))

    complete_value = data.get("complete_plan")
    final_value = data.get("is_final")

    complete_plan = (
        complete_value is True
        or complete_value == 1
        or _clean(complete_value).lower() in {"1", "true", "yes", "on"}
        or final_value is True
        or final_value == 1
        or _clean(final_value).lower() in {"1", "true", "yes", "on"}
    )

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()

        actor, denied = _batch_access(cursor)
        if denied:
            return denied

        conn.start_transaction()

        plan = _get_plan_for_update(cursor, plan_id)
        if not plan:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Cutting Plan not found.",
            }), 404

        if plan["status"] not in {"Released", "Partially Completed"}:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": (
                    "Only Released or Partially Completed plans "
                    "can receive a cutting entry."
                ),
            }), 409

        planned_qty = _as_int(plan.get("planned_qty"), 0)
        previous_actual = _as_int(plan.get("completed_qty"), 0)
        completed_qty = previous_actual + cut_qty
        variance_qty = completed_qty - planned_qty

        # Final batch flag completes the Cutting Plan.
        # Quantity can be below, equal, or above planned quantity.
        finalizing = complete_plan

        if finalizing and variance_qty != 0 and not remarks:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": (
                    "Remarks are required when final Actual Cut Qty "
                    "is different from Planned Qty."
                ),
                "planned_qty": planned_qty,
                "actual_cut_qty": completed_qty,
                "variance_qty": variance_qty,
            }), 400

        cursor.execute(
            """
            SELECT COALESCE(MAX(batch_no), 0) AS last_batch_no
            FROM cutting_plan_batches
            WHERE cutting_plan_id = %s
            FOR UPDATE
            """,
            (plan_id,),
        )

        batch_no = _as_int(
            (cursor.fetchone() or {}).get("last_batch_no"),
            0,
        ) + 1

        cursor.execute(
            """
            INSERT INTO cutting_plan_batches (
                cutting_plan_id,
                batch_no,
                cut_qty,
                is_final,
                operator_user_id,
                operator_name,
                remarks,
                actual_at,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), 'active')
            """,
            (
                plan_id,
                batch_no,
                cut_qty,
                1 if finalizing else 0,
                actor.get("user_id"),
                actor.get("name"),
                remarks or None,
            ),
        )

        batch_id = cursor.lastrowid
        new_status = "Completed" if finalizing else "Partially Completed"
        remaining_qty = (
            0
            if finalizing
            else max(planned_qty - completed_qty, 0)
        )

        cursor.execute(
            """
            UPDATE cutting_plans
            SET completed_qty = %s,
                remaining_qty = %s,
                variance_qty = %s,
                status = %s,
                last_actual_at = NOW(),
                actual_completed_at = CASE
                    WHEN %s = 'Completed' THEN NOW()
                    ELSE NULL
                END,
                updated_by_id = %s,
                updated_by_name = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                completed_qty,
                remaining_qty,
                variance_qty,
                new_status,
                new_status,
                actor.get("user_id"),
                actor.get("name"),
                plan_id,
            ),
        )

        _audit(
            cursor,
            plan_id,
            "BATCH_COMPLETED" if finalizing else "BATCH_RECORDED",
            actor,
            plan["status"],
            new_status,
            {
                "batch_id": batch_id,
                "batch_no": batch_no,
                "cut_qty": cut_qty,
                "completed_qty": completed_qty,
                "planned_qty": planned_qty,
                "remaining_qty": remaining_qty,
                "variance_qty": variance_qty,
                "complete_plan_requested": complete_plan,
                "finalized": finalizing,
                "remarks": remarks or None,
                "extra_quantity_carry_forward": False,
                "batch_merge_performed": False,
                "job_card_process_moved": False,
            },
        )

        conn.commit()

        cursor.execute(
            "SELECT * FROM cutting_plan_batches WHERE id = %s",
            (batch_id,),
        )
        batch = cursor.fetchone()

        cursor.execute(
            "SELECT * FROM cutting_plans WHERE id = %s",
            (plan_id,),
        )
        updated_plan = cursor.fetchone()

        return jsonify({
            "success": True,
            "message": (
                "Cutting Plan completed. Job Card process was not moved."
                if finalizing
                else "Partial cutting quantity recorded. Job Card process was not moved."
            ),
            "batch": _serialize(batch),
            "plan": _serialize(updated_plan),
            "quantity_summary": {
                "planned_qty": planned_qty,
                "actual_cut_qty": completed_qty,
                "variance_qty": variance_qty,
                "result": (
                    "EXCESS"
                    if variance_qty > 0
                    else "SHORT"
                    if variance_qty < 0
                    else "EXACT"
                ),
            },
        }), 201

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


# CUTTING_PLAN_BATCH_UNDO_API_V1_START
@cutting_plan_bp.route(
    "/api/cutting-plan/<int:plan_id>/batches/<int:batch_id>/undo",
    methods=["POST"],
)
def undo_cutting_batch(plan_id, batch_id):
    """Undo a cutting batch without moving the Job Card process.

    Rules:
    - Operator: only the latest active batch, entered by that same operator.
    - Admin/Supervisor/PPC/API key: any active batch.
    - Undo reason is mandatory.
    - Plan quantities and status are recalculated from active batch history.
    """
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "Valid JSON request body is required.",
        }), 400

    undo_reason = _clean(data.get("undo_reason"))
    if not undo_reason:
        return jsonify({
            "success": False,
            "error": "Undo reason is required.",
        }), 400

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_tables(cursor)
        conn.commit()

        actor = _actor()
        planner_access = (
            actor["api_key"]
            or actor["role"] in _PLANNING_ROLES
            or is_gaurang_special_user()
        )
        operator_access = actor["role"] == "operator"

        if not planner_access and not operator_access:
            return jsonify({
                "success": False,
                "error": (
                    "Admin, Supervisor, PPC or Cutting Operator "
                    "access is required."
                ),
            }), 403

        if operator_access and not _operator_has_cutting_access(
            cursor,
            actor.get("user_id"),
        ):
            return jsonify({
                "success": False,
                "error": "You are not assigned to the Cutting process.",
            }), 403

        conn.start_transaction()

        plan = _get_plan_for_update(cursor, plan_id)
        if not plan:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Cutting Plan not found.",
            }), 404

        if plan.get("status") == "Cancelled":
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "A Cancelled Cutting Plan cannot be corrected.",
            }), 409

        cursor.execute(
            """
            SELECT *
            FROM cutting_plan_batches
            WHERE id = %s
              AND cutting_plan_id = %s
            LIMIT 1
            FOR UPDATE
            """,
            (batch_id, plan_id),
        )
        batch = cursor.fetchone()

        if not batch:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "Cutting batch not found.",
            }), 404

        if _clean(batch.get("status")).lower() != "active":
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "This cutting batch is already undone.",
            }), 409

        if operator_access and not planner_access:
            if int(batch.get("operator_user_id") or 0) != int(
                actor.get("user_id") or 0
            ):
                conn.rollback()
                return jsonify({
                    "success": False,
                    "error": "You can undo only your own cutting batch.",
                }), 403

            cursor.execute(
                """
                SELECT id
                FROM cutting_plan_batches
                WHERE cutting_plan_id = %s
                  AND status = 'active'
                ORDER BY batch_no DESC, id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (plan_id,),
            )
            latest_active = cursor.fetchone()

            if (
                not latest_active
                or int(latest_active.get("id") or 0) != int(batch_id)
            ):
                conn.rollback()
                return jsonify({
                    "success": False,
                    "error": (
                        "An operator can undo only the latest active "
                        "batch of this Cutting Plan."
                    ),
                }), 409

        old_status = plan.get("status") or "Released"

        cursor.execute(
            """
            UPDATE cutting_plan_batches
            SET status = 'undone',
                undone_at = NOW(),
                undone_by_id = %s,
                undone_by_name = %s,
                undo_reason = %s
            WHERE id = %s
              AND cutting_plan_id = %s
              AND status = 'active'
            """,
            (
                actor.get("user_id"),
                actor.get("name"),
                undo_reason,
                batch_id,
                plan_id,
            ),
        )

        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({
                "success": False,
                "error": "The batch status changed before Undo was completed.",
            }), 409

        cursor.execute(
            """
            SELECT
                COALESCE(SUM(cut_qty), 0) AS completed_qty,
                MAX(actual_at) AS last_actual_at,
                MAX(
                    CASE
                        WHEN COALESCE(is_final, 0) = 1 THEN 1
                        ELSE 0
                    END
                ) AS has_final_batch
            FROM cutting_plan_batches
            WHERE cutting_plan_id = %s
              AND status = 'active'
            """,
            (plan_id,),
        )
        totals = cursor.fetchone() or {}

        planned_qty = _as_int(plan.get("planned_qty"), 0)
        completed_qty = _as_int(totals.get("completed_qty"), 0)
        has_final_batch = bool(
            _as_int(totals.get("has_final_batch"), 0)
        )
        variance_qty = (
            completed_qty - planned_qty
            if completed_qty > 0
            else 0
        )

        if has_final_batch:
            new_status = "Completed"
            remaining_qty = 0
        elif completed_qty > 0:
            new_status = "Partially Completed"
            remaining_qty = max(planned_qty - completed_qty, 0)
        else:
            new_status = "Released"
            remaining_qty = planned_qty

        cursor.execute(
            """
            UPDATE cutting_plans
            SET completed_qty = %s,
                remaining_qty = %s,
                variance_qty = %s,
                status = %s,
                last_actual_at = %s,
                actual_completed_at = CASE
                    WHEN %s = 'Completed' THEN %s
                    ELSE NULL
                END,
                updated_by_id = %s,
                updated_by_name = %s,
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                completed_qty,
                remaining_qty,
                variance_qty,
                new_status,
                totals.get("last_actual_at"),
                new_status,
                totals.get("last_actual_at"),
                actor.get("user_id"),
                actor.get("name"),
                plan_id,
            ),
        )

        _audit(
            cursor,
            plan_id,
            "BATCH_UNDONE",
            actor,
            old_status,
            new_status,
            {
                "batch_id": batch_id,
                "batch_no": batch.get("batch_no"),
                "undone_cut_qty": batch.get("cut_qty"),
                "undo_reason": undo_reason,
                "completed_qty": completed_qty,
                "remaining_qty": remaining_qty,
                "variance_qty": variance_qty,
                "has_final_batch": has_final_batch,
                "job_card_process_moved": False,
            },
        )

        conn.commit()

        cursor.execute(
            "SELECT * FROM cutting_plan_batches WHERE id = %s",
            (batch_id,),
        )
        updated_batch = cursor.fetchone()

        cursor.execute(
            "SELECT * FROM cutting_plans WHERE id = %s",
            (plan_id,),
        )
        updated_plan = cursor.fetchone()

        return jsonify({
            "success": True,
            "message": (
                "Cutting batch undone. Job Card process was not moved."
            ),
            "batch": _serialize(updated_batch),
            "plan": _serialize(updated_plan),
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
# CUTTING_PLAN_BATCH_UNDO_API_V1_END



# ============================================================
# AUTO CUTTING PLAN - ADD TO EXISTING PHYSICAL BATCH
# ============================================================
# AUTO_ADD_TO_EXISTING_BATCH_API_V1

@cutting_plan_bp.route(
    "/api/cutting-plan/auto-batch/add-existing",
    methods=["POST"],
)
def add_auto_to_existing_batch():

    actor, denied = _planning_access()

    if denied:
        return denied

    data = request.get_json(silent=True) or {}

    raw_plan_ids = data.get("plan_ids") or []
    target_batch_no = _as_int(
        data.get("plan_batch_no"),
        0,
    )

    if target_batch_no <= 0:
        return jsonify({
            "success": False,
            "error": "Please select a valid existing batch.",
        }), 400

    if not isinstance(raw_plan_ids, list):
        return jsonify({
            "success": False,
            "error": "plan_ids must be a list.",
        }), 400

    plan_ids = []

    for value in raw_plan_ids:
        plan_id = _as_int(value, 0)

        if plan_id > 0 and plan_id not in plan_ids:
            plan_ids.append(plan_id)

    if not plan_ids:
        return jsonify({
            "success": False,
            "error": "Please select at least one pending Cutting Plan.",
        }), 400


    conn = cursor = None

    try:

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        _ensure_tables(cursor)
        conn.commit()

        conn.start_transaction()


        # ----------------------------------------------------
        # LOCK / VALIDATE TARGET EXISTING BATCH
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                id,
                status
            FROM cutting_plans
            WHERE plan_batch_no = %s
            FOR UPDATE
            """,
            (target_batch_no,),
        )

        target_rows = cursor.fetchall()


        if not target_rows:

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    f"Cutting Plan Batch {target_batch_no} "
                    "does not exist."
                ),
            }), 404


        blocked_target = [
            row
            for row in target_rows
            if _clean(row.get("status"))
            in ("Completed", "Cancelled")
        ]


        if blocked_target:

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    f"Batch {target_batch_no} cannot accept "
                    "new Job Cards because it contains a "
                    "Completed or Cancelled plan."
                ),
            }), 400


        # ----------------------------------------------------
        # LOCK SELECTED PENDING AUTO ROWS
        # ----------------------------------------------------

        placeholders = ", ".join(
            ["%s"] * len(plan_ids)
        )

        cursor.execute(
            f"""
            SELECT *
            FROM cutting_plans
            WHERE id IN ({placeholders})
            FOR UPDATE
            """,
            tuple(plan_ids),
        )

        selected_rows = cursor.fetchall()


        found_ids = {
            int(row["id"])
            for row in selected_rows
        }

        missing_ids = [
            plan_id
            for plan_id in plan_ids
            if plan_id not in found_ids
        ]


        if missing_ids:

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Cutting Plan not found: "
                    + ", ".join(
                        str(value)
                        for value in missing_ids
                    )
                ),
            }), 404


        # ----------------------------------------------------
        # VALIDATE EACH ROW
        # ----------------------------------------------------

        validation_errors = []


        for plan in selected_rows:

            reference = (
                _clean(
                    plan.get("source_job_card_no")
                )
                or
                _clean(
                    plan.get("job_card_no")
                )
                or
                f"AUTO #{plan['id']}"
            )


            if _clean(plan.get("source_type")) != "AUTO":

                validation_errors.append(
                    f"{reference}: only AUTO plans can "
                    "be added from Pending Requirements."
                )

                continue


            if _clean(plan.get("status")) != "Draft":

                validation_errors.append(
                    f"{reference}: plan must still be Draft."
                )

                continue


            if plan.get("plan_batch_no") is not None:

                validation_errors.append(
                    f"{reference}: plan already belongs "
                    "to a batch."
                )

                continue


            if not _clean(plan.get("cut_size")):

                validation_errors.append(
                    f"{reference}: Cut Size is required."
                )


            if _as_int(
                plan.get("planned_qty"),
                0,
            ) <= 0:

                validation_errors.append(
                    f"{reference}: Quantity must be "
                    "greater than zero."
                )


            # Move To is retired from the active Cutting Plan workflow.


        if validation_errors:

            conn.rollback()

            return jsonify({
                "success": False,
                "error": validation_errors[0],
                "validation_errors": validation_errors,
            }), 400


        # ----------------------------------------------------
        # ADD TO EXISTING BATCH + RELEASE
        # ----------------------------------------------------

        cursor.execute(
            f"""
            UPDATE cutting_plans
            SET plan_batch_no = %s,
                status = 'Released',
                released_at = COALESCE(
                    released_at,
                    NOW()
                ),
                released_by_id = %s,
                released_by_name = %s,
                updated_by_id = %s,
                updated_by_name = %s,
                updated_at = NOW()
            WHERE id IN ({placeholders})
            """,
            (
                target_batch_no,
                actor.get("user_id"),
                actor.get("name"),
                actor.get("user_id"),
                actor.get("name"),
                *plan_ids,
            ),
        )


        if cursor.rowcount != len(plan_ids):

            conn.rollback()

            return jsonify({
                "success": False,
                "error": (
                    "Not all selected Cutting Plans were "
                    "added. No changes were saved."
                ),
            }), 409


        # ----------------------------------------------------
        # AUDIT
        # ----------------------------------------------------

        for plan in selected_rows:

            _audit(
                cursor,
                plan["id"],
                "AUTO_ADDED_TO_EXISTING_BATCH",
                actor,
                "Draft",
                "Released",
                {
                    "plan_batch_no": target_batch_no,
                    "added_to_existing_batch": True,
                    "job_card_process_moved": False,
                },
            )


        conn.commit()


        cursor.execute(
            f"""
            SELECT *
            FROM cutting_plans
            WHERE id IN ({placeholders})
            ORDER BY id
            """,
            tuple(plan_ids),
        )


        updated_rows = [
            _serialize(row)
            for row in cursor.fetchall()
        ]


        return jsonify({
            "success": True,
            "message": (
                f"{len(updated_rows)} Cutting Plan "
                f"row(s) added to Batch "
                f"{target_batch_no}."
            ),
            "plan_batch_no": target_batch_no,
            "added_plan_ids": plan_ids,
            "plans": updated_rows,
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


# AUTO_ADD_TO_EXISTING_BATCH_API_V1_END



# ============================================================
# PARENT CODE -> CHILD CODES -> JOB CARDS SEARCH
# ============================================================
# ============================================================
# PARENT CODE -> CHILD CODES -> JOB CARDS
# Unified Cutting Plan Search
# ============================================================



# ============================================================
# TODAY'S CUTTING PLAN REQUIREMENTS
# Raw Material -> Cutting Plan
# ============================================================
# CUTTING_PLAN_TODAY_REQUIREMENTS_V1

@cutting_plan_bp.route(
    "/api/cutting-plan/today-requirements",
    methods=["GET"],
)
def cutting_plan_today_requirements():

    actor, denied = _planning_access()

    if denied:
        return denied

    conn = cursor = None

    try:

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        _ensure_tables(cursor)
        conn.commit()


        cursor.execute(
            """
            SELECT
                cp.*,
                jc.child_code AS child_code

            FROM cutting_plans cp

            LEFT JOIN job_cards jc
                ON BINARY jc.job_card_no
                 = BINARY COALESCE(
                       NULLIF(
                           cp.source_job_card_no,
                           ''
                       ),
                       cp.job_card_no
                   )

            WHERE cp.source_type = 'AUTO'

              AND cp.status = 'Draft'

              AND cp.plan_batch_no IS NULL

              AND DATE(cp.created_at) = CURDATE()

            ORDER BY
                cp.created_at ASC,
                cp.id ASC
            """
        )


        plans = []

        for row in cursor.fetchall():

            serialized = _serialize(row)

            serialized["child_code"] = _clean(
                row.get("child_code")
            )

            plans.append(serialized)


        return jsonify({
            "success": True,
            "count": len(plans),
            "plans": plans,
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


# CUTTING_PLAN_TODAY_REQUIREMENTS_V1_END



# ============================================================
# UPLOADED JOB CARDS -> PENDING CUTTING REQUIREMENTS
# ============================================================
# ============================================================
# UPLOADED JOB CARDS -> PENDING CUTTING REQUIREMENTS
#
# IMPORTANT:
# This endpoint is READ ONLY.
# Draft creation happens during Job Card import/upload.
# ============================================================
# ============================================================
# UPLOADED JOB CARDS -> PENDING CUTTING REQUIREMENTS
#
# V5:
# - newest uploaded JC first
# - server-side universal search
# - upload-date filtering
# - pagination
# - read-only pending API
# ============================================================
# CUTTING_PLAN_UPLOADED_PENDING_V5

@cutting_plan_bp.route(
    "/api/cutting-plan/uploaded-requirements",
    methods=["GET"],
)
def cutting_plan_uploaded_requirements():

    actor, denied = _planning_access()

    if denied:
        return denied


    search = _clean(
        request.args.get("search")
    )

    from_date = _clean(
        request.args.get("from_date")
    )

    to_date = _clean(
        request.args.get("to_date")
    )


    limit = _as_int(
        request.args.get("limit"),
        100,
    )

    page = _as_int(
        request.args.get("page"),
        1,
    )


    if limit < 1:
        limit = 100

    if limit > 500:
        limit = 500

    if page < 1:
        page = 1


    offset = (
        page - 1
    ) * limit


    conn = cursor = None

    try:

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        _ensure_tables(cursor)
        conn.commit()


        where_parts = [
            "cp.source_type = 'AUTO'",
            "cp.status = 'Draft'",
            "cp.plan_batch_no IS NULL",

            # CUTTING_PLAN_CURRENT_JC_PENDING_RULE_V1
            #
            # Pending must represent the CURRENT uploaded JC item only.
            """
            EXISTS (
                SELECT 1
                FROM job_card_items current_ji
                WHERE current_ji.id = cp.source_item_id
                  AND BINARY current_ji.job_card_no
                      = BINARY jc.job_card_no
                  AND COALESCE(current_ji.is_deleted, 0) = 0
            )
            """,

            # Only the newest AUTO plan for the current uploaded JC item
            # may represent Pending.
            """
            NOT EXISTS (
                SELECT 1
                FROM cutting_plans newer_cp
                WHERE newer_cp.source_type = 'AUTO'
                  AND newer_cp.source_item_id = cp.source_item_id
                  AND newer_cp.id > cp.id
            )
            """,

            """
            EXISTS (
                SELECT 1
                FROM item_processes ip
                JOIN processes p
                  ON p.id = ip.process_id
                WHERE BINARY ip.item_code
                    = BINARY jc.child_code
                  AND LOWER(
                        TRIM(
                            p.process_name
                        )
                      ) = 'cutting'
            )
            """,
        ]

        params = []


        # ----------------------------------------------------
        # UPLOAD DATE FILTER
        # Uses job_cards.created_at
        # ----------------------------------------------------

        if from_date:

            where_parts.append(
                "DATE(jc.created_at) >= %s"
            )

            params.append(
                from_date
            )


        if to_date:

            where_parts.append(
                "DATE(jc.created_at) <= %s"
            )

            params.append(
                to_date
            )


        # ----------------------------------------------------
        # UNIVERSAL SEARCH
        #
        # JC No.
        # Parent Code
        # Child Code
        # Material
        # Cut Size
        # Part
        # Model & Size
        # SO No.
        # ----------------------------------------------------

        if search:

            like_value = (
                "%"
                + search
                + "%"
            )


            where_parts.append(
                """
                (
                    jc.job_card_no LIKE %s
                    OR jc.parent_code LIKE %s
                    OR jc.child_code LIKE %s
                    OR cp.material_spec LIKE %s
                    OR cp.cut_size LIKE %s
                    OR cp.part LIKE %s
                    OR cp.model_size LIKE %s
                    OR cp.item_name LIKE %s
                    OR cp.so_no LIKE %s
                )
                """
            )


            params.extend(
                [like_value] * 9
            )


        where_sql = (
            "\n AND ".join(
                where_parts
            )
        )


        # ----------------------------------------------------
        # TOTAL MATCHING RECORDS
        # ----------------------------------------------------

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total

            FROM cutting_plans cp

            JOIN job_cards jc
              ON BINARY jc.job_card_no
               = BINARY COALESCE(
                     NULLIF(
                         cp.source_job_card_no,
                         ''
                     ),
                     cp.job_card_no
                 )

            WHERE
                {where_sql}
            """,
            tuple(params),
        )


        total_row = (
            cursor.fetchone()
            or {}
        )


        total = _as_int(
            total_row.get("total"),
            0,
        )


        # ----------------------------------------------------
        # PAGE DATA
        #
        # IMPORTANT:
        # newest uploaded JC first
        # ----------------------------------------------------

        query_params = (
            list(params)
            + [
                limit,
                offset,
            ]
        )


        cursor.execute(
            f"""
            SELECT
                cp.*,

                jc.parent_code,
                jc.child_code,

                jc.created_at
                    AS uploaded_at

            FROM cutting_plans cp

            JOIN job_cards jc
              ON BINARY jc.job_card_no
               = BINARY COALESCE(
                     NULLIF(
                         cp.source_job_card_no,
                         ''
                     ),
                     cp.job_card_no
                 )

            WHERE
                {where_sql}

            ORDER BY
                jc.created_at DESC,
                cp.id DESC

            LIMIT %s
            OFFSET %s
            """,
            tuple(query_params),
        )


        plans = []


        for row in cursor.fetchall():

            plan = _serialize(
                row
            )


            plan["parent_code"] = _clean(
                row.get(
                    "parent_code"
                )
            )


            plan["child_code"] = _clean(
                row.get(
                    "child_code"
                )
            )


            uploaded_at = row.get(
                "uploaded_at"
            )


            if (
                uploaded_at
                and
                hasattr(
                    uploaded_at,
                    "isoformat"
                )
            ):

                plan["uploaded_at"] = (
                    uploaded_at.isoformat()
                )

            else:

                plan["uploaded_at"] = (
                    str(uploaded_at)
                    if uploaded_at
                    else None
                )


            plans.append(
                plan
            )


        total_pages = (
            (
                total
                + limit
                - 1
            )
            // limit
            if total
            else 0
        )


        return jsonify({

            "success": True,

            "count":
                len(plans),

            "total":
                total,

            "page":
                page,

            "limit":
                limit,

            "total_pages":
                total_pages,

            "search":
                search,

            "from_date":
                from_date,

            "to_date":
                to_date,

            "plans":
                plans,
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


# CUTTING_PLAN_UPLOADED_PENDING_V5_END


# ============================================================
# GLOBAL_NMTG_FAVICON_FALLBACK_V1
# Browser fallback /favicon.ico -> existing NMTG favicon
# ============================================================

@cutting_plan_bp.route("/favicon.ico")
def nmtg_favicon_fallback():

    return redirect(
        url_for(
            "static",
            filename="img/nmtg_logo_color_back.svg"
        )
    )

# GLOBAL_NMTG_FAVICON_FALLBACK_V1_END



# ============================================================
# CUTTING_PLAN_HISTORY_API_V1
#
# Read-only list of material already committed/sent to Cutting.
#
# Source of truth:
# existing cutting_plans rows which have already been batched.
#
# NO new DB table.
# NO data modification.
# ============================================================

@cutting_plan_bp.route(
    "/api/cutting-plan/history",
    methods=["GET"],
)
def cutting_plan_history():

    conn = cursor = None

    try:

        search = _clean(
            request.args.get("search")
        )

        from_date = _clean(
            request.args.get("from_date")
        )

        to_date = _clean(
            request.args.get("to_date")
        )

        try:
            page = max(
                int(request.args.get("page", 1)),
                1,
            )
        except Exception:
            page = 1

        try:
            per_page = int(
                request.args.get(
                    "per_page",
                    100,
                )
            )
        except Exception:
            per_page = 100

        per_page = min(
            max(per_page, 1),
            200,
        )

        offset = (
            page - 1
        ) * per_page


        conn = get_connection()
        cursor = conn.cursor(
            dictionary=True
        )


        where = [
            """
            cp.plan_batch_no IS NOT NULL
            """,

            """
            COALESCE(
                cp.status,
                ''
            ) NOT IN (
                'Draft',
                'Cancelled'
            )
            """,
        ]

        params = []


        # ----------------------------------------------------
        # SEARCH
        # ----------------------------------------------------

        if search:

            like_value = (
                "%" + search + "%"
            )

            where.append(
                """
                (
                    CAST(
                        cp.plan_batch_no
                        AS CHAR
                    ) LIKE %s

                    OR COALESCE(
                        cp.source_job_card_no,
                        cp.job_card_no,
                        ''
                    ) LIKE %s

                    OR COALESCE(
                        cp.material_spec,
                        ''
                    ) LIKE %s

                    OR COALESCE(
                        cp.cut_size,
                        ''
                    ) LIKE %s

                    OR COALESCE(
                        cp.part,
                        ''
                    ) LIKE %s

                    OR COALESCE(
                        cp.model_size,
                        ''
                    ) LIKE %s
                )
                """
            )

            params.extend(
                [like_value] * 6
            )


        # ----------------------------------------------------
        # SENT / RELEASE DATE FILTER
        # ----------------------------------------------------

        if from_date:

            where.append(
                """
                DATE(
                    COALESCE(
                        cp.released_at,
                        cp.created_at
                    )
                ) >= %s
                """
            )

            params.append(
                from_date
            )


        if to_date:

            where.append(
                """
                DATE(
                    COALESCE(
                        cp.released_at,
                        cp.created_at
                    )
                ) <= %s
                """
            )

            params.append(
                to_date
            )


        where_sql = (
            " AND ".join(where)
        )


        # ----------------------------------------------------
        # TOTAL
        # ----------------------------------------------------

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total

            FROM cutting_plans cp

            WHERE
                {where_sql}
            """,
            tuple(params),
        )

        total = int(
            (
                cursor.fetchone()
                or {}
            ).get("total")
            or 0
        )


        # ----------------------------------------------------
        # HISTORY ROWS
        # ----------------------------------------------------

        row_params = list(
            params
        )

        row_params.extend(
            [
                per_page,
                offset,
            ]
        )


        cursor.execute(
            f"""
            SELECT
                cp.id AS plan_id,

                cp.plan_batch_no
                    AS batch_no,

                DATE_FORMAT(
                    COALESCE(
                        cp.released_at,
                        cp.created_at
                    ),
                    '%d-%m-%Y'
                ) AS sent_date,

                DATE_FORMAT(
                    COALESCE(
                        cp.released_at,
                        cp.created_at
                    ),
                    '%d-%m-%Y %H:%i'
                ) AS sent_at,

                COALESCE(
                    NULLIF(
                        cp.source_job_card_no,
                        ''
                    ),
                    cp.job_card_no
                ) AS job_card_no,

                cp.material_spec
                    AS material,

                cp.cut_size,

                cp.planned_qty
                    AS qty,

                cp.part,

                cp.model_size,

                cp.status,

                cp.source_type

            FROM cutting_plans cp

            WHERE
                {where_sql}

            ORDER BY
                COALESCE(
                    cp.released_at,
                    cp.created_at
                ) DESC,

                cp.id DESC

            LIMIT %s
            OFFSET %s
            """,
            tuple(row_params),
        )


        rows = (
            cursor.fetchall()
            or []
        )


        return jsonify({
            "success": True,

            "rows": rows,

            "total": total,

            "page": page,

            "per_page": per_page,

            "pages": (
                (
                    total
                    + per_page
                    - 1
                )
                // per_page
            ),
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


# CUTTING_PLAN_HISTORY_API_V1_END


