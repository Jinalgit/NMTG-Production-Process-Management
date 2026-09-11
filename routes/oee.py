import json

from flask import Blueprint, Response, session

from db import get_connection


oee_bp = Blueprint("oee", __name__)


def _utf8_jsonify(data):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        content_type="application/json; charset=utf-8",
    )


@oee_bp.route("/api/oee/master-data", methods=["GET"])
def oee_master_data():
    """Read-only OEE master data endpoint."""

    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()
        user_id = session.get("user_id")

        if role not in ("operator", "supervisor", "admin"):
            return _utf8_jsonify({
                "success": False,
                "error": "OEE access denied."
            }), 403

        if not user_id:
            return _utf8_jsonify({
                "success": False,
                "error": "Logged-in user session is missing the user ID."
            }), 403

        conn = get_connection()
        conn.set_charset_collation(
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id, machine_no, machine_name, machine_category, "
            "zone, zone_supervisor_name "
            "FROM oee_machines "
            "WHERE is_active = 1 "
            "ORDER BY FIELD(zone, 'A', 'B', 'C', 'D', 'E'), "
            "machine_category, machine_no"
        )
        machines = cursor.fetchall()

        cursor.execute(
            "SELECT id, loss_code, loss_name, loss_category, display_order "
            "FROM oee_loss_types "
            "WHERE is_active = 1 "
            "ORDER BY display_order"
        )
        loss_types = cursor.fetchall()

        username = (session.get("username") or "").strip()
        full_name = (session.get("full_name") or "").strip()
        display_name = full_name or username or f"User {user_id}"

        return _utf8_jsonify({
            "success": True,
            "operator": {
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "display_name": display_name,
                "role": role,
            },
            "machines": machines,
            "loss_types": loss_types,
            "counts": {
                "machines": len(machines),
                "loss_types": len(loss_types),
            },
        })

    except Exception as error:
        return _utf8_jsonify({
            "success": False,
            "error": str(error),
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()



@oee_bp.route("/api/oee/context/<path:job_card_no>", methods=["GET"])
def oee_job_context(job_card_no):
    conn = None
    cursor = None

    try:
        role = (session.get("role") or "").strip().lower()
        user_id = session.get("user_id")

        if role not in ("operator", "supervisor", "admin"):
            return _utf8_jsonify({
                "success": False,
                "error": "OEE access denied.",
            }), 403

        if not user_id:
            return _utf8_jsonify({
                "success": False,
                "error": "Logged-in user session is missing the user ID.",
            }), 403

        job_card_no = (job_card_no or "").strip()

        if not job_card_no:
            return _utf8_jsonify({
                "success": False,
                "error": "Job Card No. is required.",
            }), 400

        conn = get_connection()
        conn.set_charset_collation(
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
         )
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                ji.id AS job_card_item_id,
                ji.job_card_no,
                ji.item_name,
                ji.wip_status AS current_process,
                COALESCE(ji.job_card_qty, 0) AS job_card_qty,
                COALESCE(ji.actual_qty, 0) AS ok_qty,
                COALESCE(ji.rejected_qty, 0) AS rejected_qty,
                COALESCE(ji.hold_qty, 0) AS hold_qty,
                COALESCE(ji.pending_qty, 0) AS pending_qty,
                jc.so_no,
                jc.child_code
            FROM job_card_items ji
            JOIN job_cards jc
              ON jc.job_card_no = ji.job_card_no
            WHERE ji.job_card_no = %s
              AND COALESCE(ji.is_deleted, 0) = 0
            ORDER BY ji.id
        """, (job_card_no,))

        items = cursor.fetchall()

        if not items:
            return _utf8_jsonify({
                "success": False,
                "error": f"Job Card not found: {job_card_no}",
            }), 404

        assigned_processes = []

        if role == "operator":
            cursor.execute("""
                SELECT process_name
                FROM supervisor_process_access
                WHERE user_id = %s
                ORDER BY process_name
            """, (user_id,))

            assigned_processes = [
                r["process_name"]
                for r in cursor.fetchall()
            ]

        username = (session.get("username") or "").strip()
        full_name = (session.get("full_name") or "").strip()

        return _utf8_jsonify({
            "success": True,
            "operator": {
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "role": role,
                "assigned_processes": assigned_processes,
            },
            "job_card_no": job_card_no,
            "items": items,
            "count": len(items),
        })

    except Exception as error:
        return _utf8_jsonify({
            "success": False,
            "error": str(error),
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# OEE_READ_ONLY_RESULTS_API_V1
def _oee_results_json_safe(value):
    from decimal import Decimal

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {
            key: _oee_results_json_safe(val)
            for key, val in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _oee_results_json_safe(val)
            for val in value
        ]

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    return value


@oee_bp.route("/api/oee/results", methods=["GET"])
def oee_results():
    from datetime import datetime
    from flask import request

    conn = None
    cursor = None

    try:
        role = (
            session.get("role") or ""
        ).strip().lower()

        user_id = session.get("user_id")

        if role not in (
            "admin",
            "supervisor",
            "operator",
        ):
            return _utf8_jsonify({
                "success": False,
                "error": "OEE access denied.",
            }), 403

        if not user_id:
            return _utf8_jsonify({
                "success": False,
                "error": (
                    "Logged-in user session is "
                    "missing the user ID."
                ),
            }), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        base_where = [
            "oe.record_status = 'active'"
        ]
        base_params = []

        # Operator:
        # only their own OEE history.
        if role == "operator":
            base_where.append(
                "oe.operator_user_id = %s"
            )
            base_params.append(user_id)

        # Supervisor:
        # only supervisors assigned to CNC/VMC
        # processes can access OEE.
        # They see only their assigned CNC/VMC
        # process records.
        elif role == "supervisor":
            cursor.execute(
                "SELECT process_name "
                "FROM supervisor_process_access "
                "WHERE user_id = %s "
                "ORDER BY process_name",
                (user_id,),
            )

            assigned_rows = cursor.fetchall()

            assigned_oee_processes = []

            for row in assigned_rows:
                process_name = str(
                    row.get("process_name") or ""
                ).strip()

                process_key = (
                    " ".join(
                        process_name.lower().split()
                    )
                )

                if (
                    process_key.startswith(
                        "cnc machining"
                    )
                    or process_key.startswith(
                        "vmc machining"
                    )
                ):
                    assigned_oee_processes.append(
                        process_key
                    )

            assigned_oee_processes = sorted(
                set(assigned_oee_processes)
            )

            if not assigned_oee_processes:
                return _utf8_jsonify({
                    "success": False,
                    "error": (
                        "OEE access is available only "
                        "to CNC/VMC supervisors."
                    ),
                }), 403

            placeholders = ", ".join(
                ["%s"] * len(
                    assigned_oee_processes
                )
            )

            base_where.append(
                "LOWER(TRIM(oe.process_name)) "
                f"IN ({placeholders})"
            )

            base_params.extend(
                assigned_oee_processes
            )

        base_where_sql = " AND ".join(
            base_where
        )

        # ----------------------------------
        # Filter options
        # ----------------------------------
        cursor.execute(
            "SELECT DISTINCT "
            "oe.machine_id, "
            "oe.machine_no, "
            "oe.machine_name, "
            "oe.machine_category, "
            "oe.zone, "
            "COALESCE(m.zone_supervisor_name, '') "
            "AS zone_supervisor_name "
            "FROM oee_entries oe "
            "LEFT JOIN oee_machines m "
            "ON m.id = oe.machine_id "
            f"WHERE {base_where_sql} "
            "ORDER BY "
            "oe.machine_category, "
            "oe.machine_no",
            tuple(base_params),
        )

        machine_options = cursor.fetchall()

        cursor.execute(
            "SELECT DISTINCT "
            "oe.process_name "
            "FROM oee_entries oe "
            f"WHERE {base_where_sql} "
            "ORDER BY oe.process_name",
            tuple(base_params),
        )

        process_options = [
            row["process_name"]
            for row in cursor.fetchall()
            if row.get("process_name")
        ]

        cursor.execute(
            "SELECT DISTINCT "
            "oe.operator_user_id, "
            "oe.operator_name "
            "FROM oee_entries oe "
            f"WHERE {base_where_sql} "
            "ORDER BY oe.operator_name",
            tuple(base_params),
        )

        operator_options = cursor.fetchall()

        # ----------------------------------
        # User filters
        # ----------------------------------
        where = list(base_where)
        params = list(base_params)

        from_date = (
            request.args.get(
                "from_date", ""
            ).strip()
        )

        to_date = (
            request.args.get(
                "to_date", ""
            ).strip()
        )

        machine_id = (
            request.args.get(
                "machine_id", ""
            ).strip()
        )

        process_name = (
            request.args.get(
                "process_name", ""
            ).strip()
        )

        operator_filter = (
            request.args.get(
                "operator_user_id", ""
            ).strip()
        )

        search = (
            request.args.get(
                "search", ""
            ).strip()
        )

        for label, value in (
            ("From Date", from_date),
            ("To Date", to_date),
        ):
            if value:
                try:
                    datetime.strptime(
                        value,
                        "%Y-%m-%d",
                    )
                except ValueError:
                    return _utf8_jsonify({
                        "success": False,
                        "error": (
                            f"{label} must be "
                            "YYYY-MM-DD."
                        ),
                    }), 400

        if from_date:
            where.append(
                "oe.entry_date >= %s"
            )
            params.append(from_date)

        if to_date:
            where.append(
                "oe.entry_date <= %s"
            )
            params.append(to_date)

        if machine_id:
            try:
                machine_id_int = int(
                    machine_id
                )
            except ValueError:
                return _utf8_jsonify({
                    "success": False,
                    "error": (
                        "Invalid OEE machine filter."
                    ),
                }), 400

            where.append(
                "oe.machine_id = %s"
            )
            params.append(machine_id_int)

        if process_name:
            where.append(
                "LOWER(TRIM(oe.process_name)) "
                "= LOWER(TRIM(%s))"
            )
            params.append(process_name)

        if (
            operator_filter
            and role != "operator"
        ):
            try:
                operator_filter_int = int(
                    operator_filter
                )
            except ValueError:
                return _utf8_jsonify({
                    "success": False,
                    "error": (
                        "Invalid OEE operator filter."
                    ),
                }), 400

            where.append(
                "oe.operator_user_id = %s"
            )
            params.append(
                operator_filter_int
            )

        if search:
            like = f"%{search}%"

            where.append(
                "("
                "oe.job_card_no LIKE %s "
                "OR oe.item_name LIKE %s "
                "OR oe.operator_name LIKE %s "
                "OR oe.machine_no LIKE %s "
                "OR oe.machine_name LIKE %s "
                "OR oe.process_name LIKE %s"
                ")"
            )

            params.extend([
                like,
                like,
                like,
                like,
                like,
                like,
            ])

        where_sql = " AND ".join(where)

        # ----------------------------------
        # Pagination
        # ----------------------------------
        try:
            page = max(
                int(
                    request.args.get(
                        "page", 1
                    )
                ),
                1,
            )
        except ValueError:
            page = 1

        try:
            per_page = int(
                request.args.get(
                    "per_page", 50
                )
            )
        except ValueError:
            per_page = 50

        per_page = min(
            max(per_page, 1),
            200,
        )

        offset = (
            page - 1
        ) * per_page

        # ----------------------------------
        # Count
        # ----------------------------------
        cursor.execute(
            "SELECT COUNT(*) AS total "
            "FROM oee_entries oe "
            f"WHERE {where_sql}",
            tuple(params),
        )

        total = int(
            (
                cursor.fetchone()
                or {}
            ).get("total")
            or 0
        )

        # ----------------------------------
        # Stored OEE summary
        # No recalculation.
        # ----------------------------------
        cursor.execute(
            "SELECT "
            "COUNT(*) AS entry_count, "
            "AVG(oe.detailed_ar_ratio) "
            "AS avg_ar_ratio, "
            "AVG(oe.detailed_pr_ratio) "
            "AS avg_pr_ratio, "
            "AVG(oe.detailed_qr_ratio) "
            "AS avg_qr_ratio, "
            "AVG(oe.detailed_oee_ratio) "
            "AS avg_oee_ratio, "
            "AVG(oe.plan_vs_actual) "
            "AS avg_plan_vs_actual "
            "FROM oee_entries oe "
            f"WHERE {where_sql}",
            tuple(params),
        )

        summary = (
            cursor.fetchone()
            or {}
        )

        # ----------------------------------
        # OEE rows
        # ----------------------------------
        row_sql = (
            "SELECT "
            "oe.id AS oee_entry_id, "
            "oe.operator_completion_id, "
            "oe.entry_date, "
            "oe.shift_name, "
            "oe.job_card_no, "
            "oe.item_name, "
            "oe.process_name, "
            "oe.operator_user_id, "
            "oe.operator_name, "
            "oe.machine_id, "
            "oe.machine_no, "
            "oe.machine_name, "
            "oe.machine_category, "
            "oe.zone, "
            "COALESCE(m.zone_supervisor_name, '') "
            "AS zone_supervisor_name, "
            "oe.start_time, "
            "oe.end_time, "
            "oe.cycle_minutes, "
            "oe.cycle_seconds, "
            "oe.load_unload_minutes, "
            "oe.load_unload_seconds, "
            "oe.ok_qty, "
            "oe.rejected_qty, "
            "oe.hold_qty, "
            "oe.planned_minutes, "
            "oe.run_minutes, "
            "oe.total_loss_minutes, "
            "oe.ideal_cycle_minutes, "
            "oe.target_qty, "
            "oe.total_qty, "
            "oe.plan_vs_actual, "
            "oe.available_time_minutes, "
            "oe.ar_loss_minutes, "
            "oe.utilization_minutes, "
            "oe.pr_loss_minutes, "
            "oe.after_pr_minutes, "
            "oe.detailed_ar_ratio, "
            "oe.detailed_pr_ratio, "
            "oe.detailed_qr_ratio, "
            "oe.detailed_oee_ratio, "
            "oe.remarks, "
            "oe.created_at "
            "FROM oee_entries oe "
            "LEFT JOIN oee_machines m "
            "ON m.id = oe.machine_id "
            f"WHERE {where_sql} "
            "ORDER BY "
            "oe.entry_date DESC, "
            "oe.id DESC "
            "LIMIT %s OFFSET %s"
        )

        row_params = list(params)
        row_params.extend([
            per_page,
            offset,
        ])

        cursor.execute(
            row_sql,
            tuple(row_params),
        )

        rows = cursor.fetchall()

        return _utf8_jsonify(
            _oee_results_json_safe({
                "success": True,
                "access": {
                    "role": role,
                    "user_id": user_id,
                    "read_only": True,
                },
                "summary": summary,
                "data": rows,
                "total": total,
                "page": page,
                "per_page": per_page,
                "filters": {
                    "machines": machine_options,
                    "processes": process_options,
                    "operators": operator_options,
                },
            })
        )

    except Exception as exc:
        return _utf8_jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()



# OEE_REPORT_MACHINE_SUPERVISOR_V97
#
# OEE reporting now resolves Zone Supervisor from:
#
# oee_entries.machine_id
# -> oee_machines.zone_supervisor_name
#
# No new OEE table or oee_entries column required.
# OEE_REPORT_MACHINE_SUPERVISOR_V97_END
