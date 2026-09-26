import json

from flask import Blueprint, Response, request, session

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

        if role not in ("operator", "supervisor", "admin", "plant_head"):
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

        if role not in ("operator", "supervisor", "admin", "plant_head"):
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
        "plant_head",
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


# ============================================================
# OEE_AUTO_JC_ITEM_LOOKUP_V1
# Fallback lookup when operator enters an item_code because the
# JC was not found in MES. Returns item description + process
# chain from process_master so the terminal can auto-fill.
# ============================================================
@oee_bp.route("/api/oee/item-lookup", methods=["GET"])
def oee_item_lookup():
    from flask import request
    item_code = (request.args.get("item_code") or "").strip()
    if not item_code:
        return _utf8_jsonify({"found": False, "error": "item_code required"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT item_code, item_description, material, size, part_name "
            "FROM items WHERE item_code = %s LIMIT 1",
            (item_code,),
        )
        item = cursor.fetchone()
        if not item:
            return _utf8_jsonify({
                "found": False,
                "stage": "item",
                "message": f"Item code {item_code} not found",
            })

        cursor.execute(
            "SELECT model_name, part_name, size, material, "
            "p1, p2, p3, p4, p5, p6, p7, p8, p9, p10, "
            "p11, p12, p13, p14, p15, p16, p17, p18, p19, p20, "
            "p21, p22, p23, p24, p25 "
            "FROM process_master WHERE model_name = %s LIMIT 1",
            (item["item_description"],),
        )
        pm = cursor.fetchone()
        if not pm:
            return _utf8_jsonify({
                "found": False,
                "stage": "process_master",
                "message": (
                    f"Item {item_code} exists but has no process routing. "
                    f"Operator can enter processes manually."
                ),
                "item_code": item["item_code"],
                "item_description": item["item_description"],
                "material": item.get("material") or "",
                "size": item.get("size") or "",
                "part_name": item.get("part_name") or "",
            })

        processes = []
        for i in range(1, 26):
            val = (pm.get(f"p{i}") or "").strip()
            if val:
                processes.append(val)

        return _utf8_jsonify({
            "found": True,
            "item_code": item["item_code"],
            "item_description": item["item_description"],
            "material": (pm.get("material") or item.get("material") or ""),
            "size": (pm.get("size") or item.get("size") or ""),
            "part_name": (pm.get("part_name") or item.get("part_name") or ""),
            "processes": processes,
        })
    finally:
        cursor.close()
        conn.close()


# ============================================================
# OEE_AUTO_JC_CREATE_V1
# Creates a temporary Job Card when the operator's JC is not in
# MES. Fills placeholders (MANUAL_OEE), auto-builds the process
# chain, chain-completes preceding stages, sets is_auto_oee=1.
# ============================================================
@oee_bp.route("/api/oee/auto-jc/create", methods=["POST"])
def oee_auto_jc_create():
    from flask import request
    payload = request.get_json(silent=True) or {}

    raw_jc = str(payload.get("job_card_no") or "").strip()
    item_code = str(payload.get("item_code") or "").strip()
    item_description = str(payload.get("item_description") or "").strip()
    material = str(payload.get("material") or "").strip()
    size = str(payload.get("size") or "").strip()
    qty = int(payload.get("qty") or 0)
    current_process = str(payload.get("current_process") or "").strip()
    processes = payload.get("processes") or []
    is_manual = bool(payload.get("is_manual"))
    zone = str(payload.get("zone") or "").strip()
    operator = str(payload.get("operator_username") or session.get("username") or "").strip()

    # ---- Validate ----
    if not raw_jc:
        return _utf8_jsonify({"success": False, "error": "job_card_no required"}), 400
    if not item_description:
        return _utf8_jsonify({"success": False, "error": "item_description required"}), 400
    if qty <= 0:
        return _utf8_jsonify({"success": False, "error": "qty must be > 0"}), 400
    if not isinstance(processes, list) or not processes:
        return _utf8_jsonify({"success": False, "error": "processes required"}), 400
    if not current_process or current_process not in processes:
        return _utf8_jsonify({"success": False, "error": "current_process must be in processes"}), 400

    # ---- Pad JC to 10 digits ----
    digits = "".join(c for c in raw_jc if c.isdigit())
    if not digits:
        return _utf8_jsonify({"success": False, "error": "job_card_no must contain digits"}), 400
    jc_no = digits.zfill(10)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # ---- Duplicate check ----
        cursor.execute("SELECT job_card_no FROM job_cards WHERE job_card_no=%s LIMIT 1", (jc_no,))
        if cursor.fetchone():
            return _utf8_jsonify({
                "success": False,
                "error": f"Job Card {jc_no} already exists. Use normal OEE entry.",
                "existing": True,
                "job_card_no": jc_no,
            }), 409

        # ---- Insert job_cards (parent) ----
        cursor.execute(
            """
            INSERT INTO job_cards
                (job_card_no, so_no, customer_name, work_order_no,
                 parent_code, child_code, so_date, job_card_date,
                 work_order_date, wo_delivery_date, so_delivery_date,
                 assembly_name, final_status, erp_status)
            VALUES (%s, %s, %s, %s, %s, %s, NULL, CURDATE(),
                    NULL, NULL, NULL, %s, 'Pending', 'Open')
            """,
            (jc_no, "MANUAL_OEE", "MANUAL_OEE", "MANUAL_OEE",
             item_code or None, item_code or None, item_description),
        )

        # ---- Build remarks with auto-completed preceding stages ----
        _current_idx_for_remarks = processes.index(current_process)
        _preceding_for_remarks = processes[:_current_idx_for_remarks]
        if _preceding_for_remarks:
            _auto_remarks = "AUTO_OEE | Prev auto-completed: " + ", ".join(_preceding_for_remarks)
        else:
            _auto_remarks = "AUTO_OEE | No preceding stages"

        # ---- Insert job_card_items ----
        cursor.execute(
            """
            INSERT INTO job_card_items
                (job_card_no, item_name, material, size,
                 so_qty, actual_qty, wip_status, is_auto_oee,
                 delivery_date, remarks, hold_qty, pending_qty)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, NULL, %s, 0, 0)
            """,
            (jc_no, item_description, material, size,
             qty, qty, current_process, _auto_remarks),
        )

        # ---- Insert process chain ----
        current_idx = processes.index(current_process)
        for i, pname in enumerate(processes):
            if i < current_idx:
                # Preceding — chain-complete
                cursor.execute(
                    """
                    INSERT INTO job_card_process_days
                        (job_card_no, process_name, days, is_completed,
                         in_time, out_time, end_date)
                    VALUES (%s, %s, 0, 1,
                            DATE_SUB(NOW(), INTERVAL 1 DAY),
                            DATE_SUB(NOW(), INTERVAL 1 HOUR),
                            CURDATE())
                    """,
                    (jc_no, pname),
                )
            elif i == current_idx:
                # Current process — in progress
                cursor.execute(
                    """
                    INSERT INTO job_card_process_days
                        (job_card_no, process_name, days, is_completed, in_time)
                    VALUES (%s, %s, 0, 0, NOW())
                    """,
                    (jc_no, pname),
                )
            else:
                # Upcoming — untouched
                cursor.execute(
                    """
                    INSERT INTO job_card_process_days
                        (job_card_no, process_name, days, is_completed)
                    VALUES (%s, %s, 0, 0)
                    """,
                    (jc_no, pname),
                )

        # ---- Audit trail ----
        cursor.execute(
            """
            INSERT INTO audit_trail
                (job_card_no, item_name, old_stage, new_stage, changed_by, changed_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (jc_no, item_description, "", current_process, operator or "system"),
        )

        # ---- Review queue for manual entries ----
        if is_manual:
            cursor.execute(
                """
                INSERT INTO oee_review_queue
                    (job_card_no, item_code, manual_item_name,
                     manual_processes, zone, created_by, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                """,
                (jc_no, item_code or None, item_description,
                 json.dumps(processes), zone or None, operator or None),
            )

        conn.commit()
        return _utf8_jsonify({
            "success": True,
            "job_card_no": jc_no,
            "message": f"Auto-JC {jc_no} created" + (" (pending review)" if is_manual else ""),
        })
    except Exception as e:
        conn.rollback()
        return _utf8_jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ============================================================
# AUTO_OEE_ENTRY_CRUD_V1_START
# Update / Delete for OEE Entries. See migration:
# - oee_entries: created_at, updated_at, updated_by, deleted_at, deleted_by
# - oee_entry_audit_log table
# ============================================================

from datetime import datetime, timedelta


def _oee_entry_hours_since(created_at):
    if not created_at:
        return 99999.0
    try:
        if isinstance(created_at, str):
            created_at = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
        delta = datetime.now() - created_at
        return delta.total_seconds() / 3600.0
    except Exception:
        return 99999.0


def _oee_entry_can_edit_for(role_str, session_user_id, operator_user_id, created_at):
    role = str(role_str or "").strip().lower()
    if role in ("supervisor", "admin", "plant_head"):
        return True
    if role == "operator":
        try:
            if session_user_id and operator_user_id and int(session_user_id) == int(operator_user_id):
                return _oee_entry_hours_since(created_at) < 24.0
        except (TypeError, ValueError):
            return False
    return False


def _oee_entry_can_delete_for(role_str):
    role = str(role_str or "").strip().lower()
    return role in ("supervisor", "admin")


def _oee_fmt_time_val(v):
    if v is None:
        return None
    if isinstance(v, timedelta):
        total = int(v.total_seconds())
        return "%02d:%02d:%02d" % (total // 3600, (total % 3600) // 60, total % 60)
    return str(v)


def _oee_fmt_dt_val(v):
    if v is None:
        return None
    return str(v)


@oee_bp.route("/api/oee/entry/<int:entry_id>", methods=["GET"])
def oee_entry_get(entry_id):
    """Fetch an OEE entry with its losses. Includes can_edit / can_delete."""
    role = str(session.get("role") or "").strip().lower()
    user_id = session.get("user_id")

    if role not in ("operator", "supervisor", "admin", "plant_head"):
        return _utf8_jsonify({"success": False, "error": "OEE access denied."}), 403

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM oee_entries WHERE id = %s LIMIT 1", (entry_id,))
        entry = cursor.fetchone()
        if not entry:
            return _utf8_jsonify({"success": False, "error": "OEE entry not found."}), 404
        if str(entry.get("record_status") or "").lower() != "active":
            return _utf8_jsonify({"success": False, "error": "OEE entry is not active."}), 410

        cursor.execute(
            """
            SELECT id, loss_type_id,
                   loss_code_snapshot AS loss_code,
                   loss_name_snapshot AS loss_name,
                   loss_category_snapshot AS loss_category,
                   loss_minutes
            FROM oee_entry_losses
            WHERE oee_entry_id = %s
            ORDER BY CAST(SUBSTRING(loss_code_snapshot, 2) AS UNSIGNED)
            """,
            (entry_id,)
        )
        losses = cursor.fetchall() or []

        for k in ("start_time", "end_time"):
            entry[k] = _oee_fmt_time_val(entry.get(k))
        for k in ("entry_date", "created_at", "updated_at", "deleted_at"):
            entry[k] = _oee_fmt_dt_val(entry.get(k))
        for lo in losses:
            try:
                lo["loss_minutes"] = float(lo.get("loss_minutes") or 0.0)
            except (TypeError, ValueError):
                lo["loss_minutes"] = 0.0

        can_edit = _oee_entry_can_edit_for(role, user_id, entry.get("operator_user_id"), entry.get("created_at"))
        can_delete = _oee_entry_can_delete_for(role)

        return _utf8_jsonify({
            "success": True,
            "entry": entry,
            "losses": losses,
            "can_edit": can_edit,
            "can_delete": can_delete
        })
    finally:
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass


@oee_bp.route("/api/oee/entry/update", methods=["POST"])
def oee_entry_update():
    """Update an OEE entry. Recompute derived metrics. Audit each changed field."""
    from routes.oee_calculations import calculate_confirmed_excel_fields
    from routes.oee_persistence import get_oee_formula_profile

    role = str(session.get("role") or "").strip().lower()
    user_id = session.get("user_id")
    user_name = session.get("full_name") or session.get("username") or ""

    if role not in ("operator", "supervisor", "admin", "plant_head"):
        return _utf8_jsonify({"success": False, "error": "OEE access denied."}), 403

    payload = request.get_json(silent=True) or {}
    entry_id = payload.get("entry_id")
    if not entry_id:
        return _utf8_jsonify({"success": False, "error": "entry_id required."}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM oee_entries WHERE id = %s LIMIT 1", (int(entry_id),))
        existing = cursor.fetchone()
        if not existing:
            return _utf8_jsonify({"success": False, "error": "OEE entry not found."}), 404
        if str(existing.get("record_status") or "").lower() != "active":
            return _utf8_jsonify({"success": False, "error": "OEE entry is not active."}), 410

        if not _oee_entry_can_edit_for(role, user_id, existing.get("operator_user_id"), existing.get("created_at")):
            return _utf8_jsonify({
                "success": False,
                "error": "Not authorized. Operators can only edit their own entries within 24 hours."
            }), 403

        EDITABLE_FIELDS = [
            "entry_date", "shift_name",
            "machine_id", "machine_no", "machine_name", "machine_category", "zone",
            "operator_user_id", "operator_name", "operator_employee_no",
            "job_card_no", "item_name", "process_name",
            "start_time", "end_time",
            "cycle_minutes", "cycle_seconds",
            "load_unload_minutes", "load_unload_seconds",
            "ok_qty", "rejected_qty", "hold_qty",
            "remarks"
        ]

        merged = dict(existing)
        for f in EDITABLE_FIELDS:
            if f in payload:
                merged[f] = payload[f]

        provided_losses = payload.get("losses")
        if provided_losses is None:
            cursor.execute(
                """
                SELECT loss_type_id,
                       loss_code_snapshot AS loss_code,
                       loss_name_snapshot AS loss_name,
                       loss_minutes
                FROM oee_entry_losses
                WHERE oee_entry_id = %s
                """,
                (int(entry_id),)
            )
            provided_losses = [
                {
                    "loss_type_id": r["loss_type_id"],
                    "loss_code": r["loss_code"],
                    "loss_name": r["loss_name"],
                    "loss_minutes": float(r["loss_minutes"] or 0.0)
                }
                for r in (cursor.fetchall() or [])
            ]

        machine_no_for_profile = str(merged.get("machine_no") or "").strip()
        try:
            formula_profile = get_oee_formula_profile(machine_no_for_profile)
        except Exception:
            formula_profile = {"pr_loss_codes": set(), "ar_loss_codes": set(), "target_deduct_code": "A1"}

        loss_map = {}
        for lo in provided_losses:
            code = str(lo.get("loss_code") or "").upper().strip()
            try:
                mins = float(lo.get("loss_minutes") or 0.0)
                if mins < 0:
                    mins = 0.0
            except (TypeError, ValueError):
                mins = 0.0
            if code:
                loss_map[code] = mins

        pr_loss_minutes = sum(loss_map.get(c, 0.0) for c in formula_profile.get("pr_loss_codes", []))
        ar_loss_minutes = sum(loss_map.get(c, 0.0) for c in formula_profile.get("ar_loss_codes", []))
        target_deduct_code = formula_profile.get("target_deduct_code") or "A1"
        target_deduct_min = loss_map.get(target_deduct_code, 0.0)

        def _int0(v):
            try:
                return int(v or 0)
            except (TypeError, ValueError):
                return 0

        calculated = calculate_confirmed_excel_fields(
            start_time=_oee_fmt_time_val(merged.get("start_time")) or "",
            end_time=_oee_fmt_time_val(merged.get("end_time")) or "",
            cycle_minutes=_int0(merged.get("cycle_minutes")),
            cycle_seconds=_int0(merged.get("cycle_seconds")),
            load_unload_minutes=_int0(merged.get("load_unload_minutes")),
            load_unload_seconds=_int0(merged.get("load_unload_seconds")),
            production_qty=_int0(merged.get("ok_qty")),
            rejection_qty=_int0(merged.get("rejected_qty")),
            rework_qty=_int0(merged.get("hold_qty")),
            ar_loss_minutes=ar_loss_minutes,
            pr_loss_minutes=pr_loss_minutes,
            target_deduction_minutes=target_deduct_min,
        )

        merged["planned_minutes"] = calculated.get("planned_minutes")
        merged["run_minutes"] = calculated.get("run_minutes")
        merged["total_loss_minutes"] = calculated.get("total_loss_minutes")
        merged["ideal_cycle_minutes"] = calculated.get("ideal_cycle_minutes")
        merged["target_qty"] = calculated.get("target_qty")
        merged["total_qty"] = calculated.get("total_qty")
        merged["plan_vs_actual"] = calculated.get("plan_vs_actual")
        merged["available_time_minutes"] = calculated.get("available_time_minutes")
        merged["ar_loss_minutes"] = calculated.get("ar_loss_minutes")
        merged["utilization_minutes"] = calculated.get("utilization_minutes")
        merged["pr_loss_minutes"] = calculated.get("pr_loss_minutes")
        merged["after_pr_minutes"] = calculated.get("after_pr_loss_minutes")
        merged["detailed_ar_ratio"] = calculated.get("ar_ratio")
        merged["detailed_pr_ratio"] = calculated.get("pr_ratio")
        merged["detailed_qr_ratio"] = calculated.get("qr_ratio")
        merged["detailed_oee_ratio"] = calculated.get("detailed_oee_ratio")

        derived_fields = [
            "planned_minutes", "run_minutes", "total_loss_minutes",
            "ideal_cycle_minutes", "target_qty", "total_qty", "plan_vs_actual",
            "available_time_minutes", "ar_loss_minutes", "utilization_minutes",
            "pr_loss_minutes", "after_pr_minutes",
            "detailed_ar_ratio", "detailed_pr_ratio", "detailed_qr_ratio",
            "detailed_oee_ratio"
        ]
        update_fields = EDITABLE_FIELDS + derived_fields

        set_clauses = [f"{f} = %s" for f in update_fields]
        params = [merged.get(f) for f in update_fields]
        set_clauses.append("updated_at = NOW()")
        set_clauses.append("updated_by = %s")
        params.append(user_id)
        params.append(int(entry_id))

        cursor.execute(
            f"UPDATE oee_entries SET {', '.join(set_clauses)} WHERE id = %s",
            params
        )

        if payload.get("losses") is not None:
            cursor.execute("DELETE FROM oee_entry_losses WHERE oee_entry_id = %s", (int(entry_id),))
            for lo in provided_losses:
                code = str(lo.get("loss_code") or "").upper().strip()
                if not code:
                    continue
                try:
                    mins = float(lo.get("loss_minutes") or 0.0)
                except (TypeError, ValueError):
                    mins = 0.0
                loss_category = "PR" if code in formula_profile.get("pr_loss_codes", []) else "AR"
                cursor.execute(
                    """
                    INSERT INTO oee_entry_losses (
                        oee_entry_id, loss_type_id, loss_code_snapshot,
                        loss_name_snapshot, loss_category_snapshot, loss_minutes
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        int(entry_id),
                        lo.get("loss_type_id"),
                        code,
                        lo.get("loss_name") or code,
                        loss_category,
                        mins
                    )
                )

        for f in EDITABLE_FIELDS:
            old = existing.get(f)
            new = merged.get(f)
            old_s = "" if old is None else str(old)
            new_s = "" if new is None else str(new)
            if old_s != new_s:
                cursor.execute(
                    """
                    INSERT INTO oee_entry_audit_log
                        (oee_entry_id, action, field_name, old_value, new_value,
                         changed_by, changed_by_name, changed_at)
                    VALUES (%s, 'update', %s, %s, %s, %s, %s, NOW())
                    """,
                    (int(entry_id), f, old_s, new_s, user_id, user_name)
                )

        conn.commit()
        return _utf8_jsonify({"success": True, "entry_id": int(entry_id)})
    except Exception as ex:
        try: conn.rollback()
        except Exception: pass
        return _utf8_jsonify({"success": False, "error": f"Update failed: {str(ex)}"}), 500
    finally:
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass


@oee_bp.route("/api/oee/entry/delete", methods=["POST"])
def oee_entry_delete():
    """Soft-delete an OEE entry. Supervisor/admin only. Reason required."""
    role = str(session.get("role") or "").strip().lower()
    user_id = session.get("user_id")
    user_name = session.get("full_name") or session.get("username") or ""

    if not _oee_entry_can_delete_for(role):
        return _utf8_jsonify({
            "success": False,
            "error": "Only supervisor or admin can delete OEE entries."
        }), 403

    payload = request.get_json(silent=True) or {}
    entry_id = payload.get("entry_id")
    reason = str(payload.get("reason") or "").strip()

    if not entry_id:
        return _utf8_jsonify({"success": False, "error": "entry_id required."}), 400
    if not reason:
        return _utf8_jsonify({"success": False, "error": "reason required for deletion."}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, record_status FROM oee_entries WHERE id = %s LIMIT 1",
            (int(entry_id),)
        )
        row = cursor.fetchone()
        if not row:
            return _utf8_jsonify({"success": False, "error": "OEE entry not found."}), 404
        if str(row.get("record_status") or "").lower() != "active":
            return _utf8_jsonify({"success": False, "error": "OEE entry is already deleted."}), 410

        cursor.execute(
            """
            UPDATE oee_entries
            SET record_status = 'deleted',
                deleted_at = NOW(),
                deleted_by = %s
            WHERE id = %s
            """,
            (user_id, int(entry_id))
        )

        cursor.execute(
            """
            INSERT INTO oee_entry_audit_log
                (oee_entry_id, action, reason, changed_by, changed_by_name, changed_at)
            VALUES (%s, 'delete', %s, %s, %s, NOW())
            """,
            (int(entry_id), reason, user_id, user_name)
        )

        conn.commit()
        return _utf8_jsonify({"success": True, "entry_id": int(entry_id)})
    except Exception as ex:
        try: conn.rollback()
        except Exception: pass
        return _utf8_jsonify({"success": False, "error": f"Delete failed: {str(ex)}"}), 500
    finally:
        try: cursor.close()
        except Exception: pass
        try: conn.close()
        except Exception: pass

# AUTO_OEE_ENTRY_CRUD_V1_END