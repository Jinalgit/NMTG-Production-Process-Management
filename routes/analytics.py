"""
Analytics API routes for Demo 2.
All endpoints support from_date / to_date query params.
When a single date is passed (from=to), shows that day's data.
Default: last 30 days.
"""

from datetime import date, timedelta

from flask import Blueprint, jsonify, request

from db import get_connection

analytics_bp = Blueprint("analytics", __name__)


def _get_date_range():
    """Extract date range. No selected dates means full JMS data."""
    from_date = (request.args.get("from_date") or "").strip()
    to_date = (request.args.get("to_date") or "").strip()

    if not from_date:
        from_date = "1900-01-01"

    if not to_date:
        to_date = "9999-12-31"

    return from_date, to_date


# ── 1. KPI Summary ────────────────────────────────────────────────────────────
# ANALYTICS_STARTED_WIP_ONLY_V2
@analytics_bp.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
    try:
        from_date, to_date = _get_date_range()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Total job cards created in date range
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM job_cards
            WHERE DATE(created_at) BETWEEN %s AND %s
        """, (from_date, to_date))
        total_jc = cursor.fetchone()["total"]

        # Active job cards - same completion rule as Data View
        cursor.execute("""
        SELECT COUNT(DISTINCT jci.job_card_no) AS total
        FROM job_card_items jci
        JOIN job_cards jc ON jc.job_card_no = jci.job_card_no
        WHERE (jci.is_deleted IS NULL OR jci.is_deleted = 0)
          AND DATE(jc.created_at) BETWEEN %s AND %s
          AND EXISTS (
              SELECT 1
              FROM job_card_process_days current_pd
              WHERE current_pd.job_card_no = jci.job_card_no
                AND LOWER(TRIM(current_pd.process_name)) = LOWER(TRIM(jci.wip_status))
                AND current_pd.in_time IS NOT NULL
                AND current_pd.out_time IS NULL
                AND COALESCE(current_pd.is_completed, 0) = 0
          )
          AND NOT EXISTS (
              SELECT 1
              FROM job_card_process_days jcpd
              WHERE jcpd.job_card_no = jci.job_card_no
                AND LOWER(TRIM(jcpd.process_name)) = 'store'
                AND jcpd.is_completed = 1
          )
        """, (from_date, to_date))
        active_jc = cursor.fetchone()["total"]

        # Completed in date range (reached Store)
        cursor.execute("""
            SELECT COUNT(DISTINCT jcpd.job_card_no) AS total
            FROM job_card_process_days jcpd
            WHERE LOWER(TRIM(jcpd.process_name)) = 'store'
              AND jcpd.is_completed = 1
              AND DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) BETWEEN %s AND %s
        """, (from_date, to_date))
        completed = cursor.fetchone()["total"]

        # Overdue in date range (delivery_date in range and not completed)
        cursor.execute("""
            SELECT COUNT(DISTINCT jci.job_card_no) AS total
            FROM job_card_items jci
            WHERE jci.delivery_date < CURDATE()
              AND jci.delivery_date BETWEEN %s AND %s
              AND LOWER(TRIM(jci.wip_status)) NOT IN ('store', 'completed')
              AND (jci.is_deleted IS NULL OR jci.is_deleted = 0)
          AND EXISTS (
              SELECT 1
              FROM job_card_process_days current_pd
              WHERE current_pd.job_card_no = jci.job_card_no
                AND LOWER(TRIM(current_pd.process_name)) = LOWER(TRIM(jci.wip_status))
                AND current_pd.in_time IS NOT NULL
                AND current_pd.out_time IS NULL
                AND COALESCE(current_pd.is_completed, 0) = 0
          )
        """, (from_date, to_date))
        overdue = cursor.fetchone()["total"]

        # Stages completed in date range (for activity count)
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM job_card_process_days
            WHERE is_completed = 1
              AND out_time IS NOT NULL
              AND DATE(CONVERT_TZ(out_time, '+00:00', '+05:30')) BETWEEN %s AND %s
        """, (from_date, to_date))
        stages_completed = cursor.fetchone()["total"]

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "total_job_cards": total_jc,
            "active_job_cards": active_jc,
            "completed_this_month": completed,
            "overdue_job_cards": overdue,
            "stages_completed": stages_completed,
            "avg_completion_days": 0,
            "on_time_pct": 0,
            "on_time_count": 0,
            "total_delivered": 0,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── 2. WIP Flow ───────────────────────────────────────────────────────────────
@analytics_bp.route("/api/analytics/wip_flow", methods=["GET"])
def analytics_wip_flow():
    try:
        from_date, to_date = _get_date_range()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        FLOW_ORDER = [
            "Drawing", "Raw Material", "Cutting", "Rough Turning", "Turning",
            "CNC Machining", "CNC Machining 1st Side", "CNC Machining 2nd Side",
            "VMC Machining", "Drilling & Tapping", "Milling", "Grinding",
            "ID Grinding", "OD Grinding", "Broaching", "Slitting", "Forging",
            "Normalising", "Heat Treatment", "Blackening", "Sub Contract",
            "Inspection", "Quality Check", "Assembly", "Store"
        ]

        cursor.execute("""
            SELECT jci.wip_status, COUNT(DISTINCT jci.job_card_no) AS count
            FROM job_card_items jci
            JOIN job_cards jc ON jc.job_card_no = jci.job_card_no
            WHERE jci.wip_status IS NOT NULL
              AND TRIM(jci.wip_status) != ''
              AND LOWER(TRIM(jci.wip_status)) NOT IN ('pending', 'completed')
              AND (jci.is_deleted IS NULL OR jci.is_deleted = 0)
              AND DATE(jc.created_at) BETWEEN %s AND %s
          AND EXISTS (
              SELECT 1
              FROM job_card_process_days current_pd
              WHERE current_pd.job_card_no = jci.job_card_no
                AND LOWER(TRIM(current_pd.process_name)) = LOWER(TRIM(jci.wip_status))
                AND current_pd.in_time IS NOT NULL
                AND current_pd.out_time IS NULL
                AND COALESCE(current_pd.is_completed, 0) = 0
          )
            GROUP BY jci.wip_status
            ORDER BY count DESC
        """, (from_date, to_date))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        def sort_key(r):
            try:
                return FLOW_ORDER.index(r["wip_status"])
            except ValueError:
                return 999

        rows.sort(key=sort_key)
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── 3. Daily Activity ─────────────────────────────────────────────────────────
@analytics_bp.route("/api/analytics/daily_activity", methods=["GET"])
def analytics_daily_activity():
    try:
        from_date, to_date = _get_date_range()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                DATE(CONVERT_TZ(out_time, '+00:00', '+05:30')) AS activity_date,
                COUNT(*) AS stages_completed
            FROM job_card_process_days
            WHERE is_completed = 1
              AND out_time IS NOT NULL
              AND DATE(CONVERT_TZ(out_time, '+00:00', '+05:30')) BETWEEN %s AND %s
            GROUP BY activity_date
            ORDER BY activity_date ASC
        """, (from_date, to_date))

        rows = cursor.fetchall()
        for r in rows:
            r["activity_date"] = str(r["activity_date"])

        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── 4. Process Delays ─────────────────────────────────────────────────────────
@analytics_bp.route("/api/analytics/process_delays", methods=["GET"])
def analytics_process_delays():
    try:
        from_date, to_date = _get_date_range()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                jcpd.process_name,
                ROUND(AVG(COALESCE(pdd.default_days, jcpd.days, 0)), 1) AS avg_planned,
                ROUND(AVG(jcpd.actual_days), 1) AS avg_actual,
                COUNT(*) AS count
            FROM job_card_process_days jcpd
            LEFT JOIN process_default_days pdd
                ON LOWER(TRIM(pdd.process_name)) = LOWER(TRIM(jcpd.process_name))
            WHERE jcpd.is_completed = 1
              AND jcpd.actual_days IS NOT NULL
              AND jcpd.actual_days > 0
              AND DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) BETWEEN %s AND %s
            GROUP BY jcpd.process_name
            HAVING count >= 1
            ORDER BY (avg_actual - avg_planned) DESC
            LIMIT 15
        """, (from_date, to_date))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── 5. Overdue Jobs ───────────────────────────────────────────────────────────
@analytics_bp.route("/api/analytics/overdue_jobs", methods=["GET"])
def analytics_overdue_jobs():
    try:
        from_date, to_date = _get_date_range()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                jci.job_card_no,
                jci.item_name,
                jc.customer_name,
                jci.wip_status AS current_stage,
                jci.delivery_date,
                DATEDIFF(CURDATE(), jci.delivery_date) AS days_overdue
            FROM job_card_items jci
            JOIN job_cards jc ON jc.job_card_no = jci.job_card_no
            WHERE jci.delivery_date < CURDATE()
              AND LOWER(TRIM(jci.wip_status)) NOT IN ('store', 'completed')
              AND (jci.is_deleted IS NULL OR jci.is_deleted = 0)
              AND DATE(jc.created_at) BETWEEN %s AND %s
          AND EXISTS (
              SELECT 1
              FROM job_card_process_days current_pd
              WHERE current_pd.job_card_no = jci.job_card_no
                AND LOWER(TRIM(current_pd.process_name)) = LOWER(TRIM(jci.wip_status))
                AND current_pd.in_time IS NOT NULL
                AND current_pd.out_time IS NULL
                AND COALESCE(current_pd.is_completed, 0) = 0
          )
            ORDER BY days_overdue DESC
            LIMIT 20
        """, (from_date, to_date))

        rows = cursor.fetchall()
        for r in rows:
            if r.get("delivery_date"):
                r["delivery_date"] = str(r["delivery_date"])

        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── 6. Supervisor Stages ──────────────────────────────────────────────────────
@analytics_bp.route("/api/analytics/supervisor_stages", methods=["GET"])
def analytics_supervisor_stages():
    try:
        from_date, to_date = _get_date_range()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                changed_by AS supervisor,
                COUNT(*) AS stages_completed,
                COUNT(DISTINCT job_card_no) AS job_cards_handled
            FROM audit_trail
            WHERE new_stage != 'Removed'
              AND DATE(CONVERT_TZ(changed_at, '+00:00', '+05:30')) BETWEEN %s AND %s
              AND changed_by IS NOT NULL
              AND TRIM(changed_by) != ''
              AND LOWER(TRIM(changed_by)) NOT IN (
                  'not assigned', 'notassigned', 'admin', 'system',
                  'system correction', 'rajesh patel'
              )
            GROUP BY changed_by
            ORDER BY stages_completed DESC
            LIMIT 15
        """, (from_date, to_date))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── 7. OTD ────────────────────────────────────────────────────────────────────
@analytics_bp.route("/api/analytics/otd", methods=["GET"])
def analytics_otd():
    try:
        from_date, to_date = _get_date_range()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE
                    WHEN DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) <= jci.delivery_date
                    THEN 1 ELSE 0
                END) AS on_time,
                SUM(CASE
                    WHEN DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) > jci.delivery_date
                    THEN 1 ELSE 0
                END) AS delayed_count
            FROM job_card_process_days jcpd
            JOIN job_card_items jci ON jci.job_card_no = jcpd.job_card_no
            WHERE LOWER(TRIM(jcpd.process_name)) = 'store'
              AND jcpd.is_completed = 1
              AND jci.delivery_date IS NOT NULL
              AND jcpd.out_time IS NOT NULL
              AND DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) BETWEEN %s AND %s
        """, (from_date, to_date))
        overall = cursor.fetchone()

        total = int(overall["total"] or 0)
        on_time = int(overall["on_time"] or 0)
        delayed = int(overall["delayed_count"] or 0)
        otd_pct = round(on_time / total * 100, 1) if total > 0 else 0

        cursor.execute("""
            SELECT
                DATE_FORMAT(
                    CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30'),
                    '%Y-%m'
                ) AS month,
                SUM(CASE
                    WHEN DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) <= jci.delivery_date
                    THEN 1 ELSE 0
                END) AS on_time,
                SUM(CASE
                    WHEN DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) > jci.delivery_date
                    THEN 1 ELSE 0
                END) AS delayed_count,
                COUNT(*) AS total
            FROM job_card_process_days jcpd
            JOIN job_card_items jci ON jci.job_card_no = jcpd.job_card_no
            WHERE LOWER(TRIM(jcpd.process_name)) = 'store'
              AND jcpd.is_completed = 1
              AND jci.delivery_date IS NOT NULL
              AND jcpd.out_time IS NOT NULL
              AND DATE(CONVERT_TZ(jcpd.out_time, '+00:00', '+05:30')) BETWEEN %s AND %s
            GROUP BY month
            ORDER BY month ASC
        """, (from_date, to_date))
        monthly = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "overall": {
                "total": total,
                "on_time": on_time,
                "delayed": delayed,
                "otd_pct": otd_pct,
            },
            "monthly": monthly,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── Backward compat ───────────────────────────────────────────────────────────
@analytics_bp.route("/api/analytics/wip_distribution", methods=["GET"])
def wip_distribution():
    return analytics_wip_flow()


@analytics_bp.route("/api/analytics/quality_by_item", methods=["GET"])
def analytics_quality_by_item():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT item_name,
                   SUM(CASE WHEN quality_result='OK' THEN 1 ELSE 0 END) as ok_count,
                   SUM(CASE WHEN quality_result='NOT OK' THEN 1 ELSE 0 END) as not_ok_count,
                   COUNT(*) as total
            FROM quality_check_details
            GROUP BY item_name ORDER BY total DESC LIMIT 10
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/api/analytics/supervisor_performance", methods=["GET"])
def analytics_supervisor_performance():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT supervisor,
                   SUM(CASE WHEN quality_result='OK' THEN 1 ELSE 0 END) as ok_count,
                   SUM(CASE WHEN quality_result='NOT OK' THEN 1 ELSE 0 END) as not_ok_count,
                   COUNT(*) as total
            FROM quality_check_details
            WHERE supervisor IS NOT NULL AND supervisor != ''
            GROUP BY supervisor ORDER BY total DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/api/analytics/daily_checks", methods=["GET"])
def analytics_daily_checks():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT DATE(checked_at) as date, COUNT(*) as count
            FROM quality_checks
            WHERE checked_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
            GROUP BY DATE(checked_at) ORDER BY date ASC
        """)
        rows = cursor.fetchall()
        for r in rows:
            r["date"] = r["date"].strftime("%Y-%m-%d")
        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ── Daily Breakdown (single date) ────────────────────────────────────────────


@analytics_bp.route("/api/analytics/daily_breakdown", methods=["GET"])
def analytics_daily_breakdown():
    """
    Returns process-wise stage completions for a single date.
    Used when sidebar filter is set to a specific day.
    """
    try:
        target_date = request.args.get("date", "")
        if not target_date:
            target_date = date.today().strftime("%Y-%m-%d")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                process_name,
                COUNT(*) AS completions,
                COUNT(DISTINCT job_card_no) AS job_cards,
                GROUP_CONCAT(DISTINCT
                    CONVERT_TZ(out_time, '+00:00', '+05:30')
                    ORDER BY out_time
                    SEPARATOR ', '
                ) AS times
            FROM job_card_process_days
            WHERE is_completed = 1
              AND out_time IS NOT NULL
              AND DATE(CONVERT_TZ(out_time, '+00:00', '+05:30')) = %s
            GROUP BY process_name
            ORDER BY completions DESC
        """, (target_date,))

        rows = cursor.fetchall()

        # Also get total stages and unique job cards for that day
        cursor.execute("""
            SELECT
                COUNT(*) AS total_stages,
                COUNT(DISTINCT job_card_no) AS total_job_cards,
                COUNT(DISTINCT changed_by) AS active_supervisors
            FROM audit_trail
            WHERE DATE(CONVERT_TZ(changed_at, '+00:00', '+05:30')) = %s
              AND new_stage != 'Removed'
              AND LOWER(TRIM(changed_by)) NOT IN (
                  'not assigned', 'notassigned', 'admin', 'system',
                  'system correction'
              )
        """, (target_date,))
        summary = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "date": target_date,
            "summary": {
                "total_stages": int(summary["total_stages"] or 0),
                "total_job_cards": int(summary["total_job_cards"] or 0),
                "active_supervisors": int(summary["active_supervisors"] or 0),
            },
            "data": rows
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================================
# ANALYTICS_STUDIO_SAFE_QUERY_V3
#
# READ-ONLY ANALYTICS BUILDER
#
# Browser sends only:
#   dataset
#   dimension
#   measures
#   split_by
#   filters
#   date range
#
# Browser never sends SQL.
# All SQL expressions are whitelisted here.
# ============================================================================


ANALYTICS_STUDIO_DATASETS = {

    "job_cards": {

        "label": "Job Cards",

        "description": (
            "Job card, customer, item, WIP and delivery analysis."
        ),

        "from_sql": """
            FROM job_card_items jci
            INNER JOIN job_cards jc
                ON jc.job_card_no = jci.job_card_no
        """,

        "base_where": "1 = 1",

        "date_sql": "DATE(jc.created_at)",

        "dimensions": {

            "date": {
                "label": "Created Date",
                "sql": "DATE(jc.created_at)",
                "type": "date",
            },

            "month": {
                "label": "Created Month",
                "sql": "DATE_FORMAT(jc.created_at, '%Y-%m')",
                "type": "time",
            },

            "customer": {
                "label": "Customer",
                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jc.customer_name), ''), "
                    "'Unknown'"
                    ")"
                ),
                "type": "category",
            },

            "wip_stage": {
                "label": "WIP Stage",
                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jci.wip_status), ''), "
                    "'Unknown'"
                    ")"
                ),
                "type": "category",
            },

            "item": {
                "label": "Item",
                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jci.item_name), ''), "
                    "'Unknown'"
                    ")"
                ),
                "type": "category",
            },

            "material": {
                "label": "Material",
                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jci.material), ''), "
                    "'Unknown'"
                    ")"
                ),
                "type": "category",
            },

            "so_no": {
                "label": "SO No.",
                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jc.so_no), ''), "
                    "'No SO'"
                    ")"
                ),
                "type": "category",
            },

            "work_order": {
                "label": "Work Order",
                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jc.work_order_no), ''), "
                    "'No WO'"
                    ")"
                ),
                "type": "category",
            },

            "parent_code": {
                "label": "Parent Code",
                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jc.parent_code), ''), "
                    "'Unknown'"
                    ")"
                ),
                "type": "category",
            },
        },

        "measures": {

            "job_card_count": {
                "label": "Job Card Count",
                "sql": "COUNT(DISTINCT jci.job_card_no)",
                "format": "integer",
            },

            "item_rows": {
                "label": "Item Rows",
                "sql": "COUNT(*)",
                "format": "integer",
            },

            "planned_qty": {
                "label": "Planned Qty",
                "sql": "SUM(COALESCE(jci.so_qty, 0))",
                "format": "number",
            },

            "overdue_job_cards": {

                "label": "Overdue Job Cards",

                "sql": """
                    COUNT(
                        DISTINCT CASE

                            WHEN jci.delivery_date < CURDATE()

                             AND LOWER(
                                TRIM(
                                    COALESCE(
                                        jci.wip_status,
                                        ''
                                    )
                                )
                             )
                             NOT IN (
                                'store',
                                'completed'
                             )

                            THEN jci.job_card_no

                            ELSE NULL

                        END
                    )
                """,

                "format": "integer",
            },

            "avg_days_overdue": {

                "label": "Avg. Days Overdue",

                "sql": """
                    ROUND(
                        AVG(
                            CASE

                                WHEN jci.delivery_date < CURDATE()

                                 AND LOWER(
                                    TRIM(
                                        COALESCE(
                                            jci.wip_status,
                                            ''
                                        )
                                    )
                                 )
                                 NOT IN (
                                    'store',
                                    'completed'
                                 )

                                THEN DATEDIFF(
                                    CURDATE(),
                                    jci.delivery_date
                                )

                                ELSE NULL

                            END
                        ),
                        1
                    )
                """,

                "format": "decimal",
            },

            "urgent_rows": {

                "label": "Urgent Rows",

                "sql": """
                    SUM(
                        CASE

                            WHEN COALESCE(
                                jci.is_priority,
                                0
                            ) = 1

                            THEN 1

                            ELSE 0

                        END
                    )
                """,

                "format": "integer",
            },
        },
    },


    "process_activity": {

        "label": "Process Activity",

        "description": (
            "Completed manufacturing processes with "
            "planned and actual duration."
        ),

        "from_sql": """
            FROM job_card_process_days jcpd

            LEFT JOIN process_default_days pdd
              ON LOWER(TRIM(pdd.process_name))
               = LOWER(TRIM(jcpd.process_name))
        """,

        "base_where": (
            "jcpd.is_completed = 1 "
            "AND jcpd.out_time IS NOT NULL"
        ),

        "date_sql": (
            "DATE("
            "CONVERT_TZ("
            "jcpd.out_time, "
            "'+00:00', "
            "'+05:30'"
            ")"
            ")"
        ),

        "dimensions": {

            "date": {

                "label": "Completion Date",

                "sql": (
                    "DATE("
                    "CONVERT_TZ("
                    "jcpd.out_time, "
                    "'+00:00', "
                    "'+05:30'"
                    ")"
                    ")"
                ),

                "type": "date",
            },

            "month": {

                "label": "Completion Month",

                "sql": (
                    "DATE_FORMAT("
                    "CONVERT_TZ("
                    "jcpd.out_time, "
                    "'+00:00', "
                    "'+05:30'"
                    "), "
                    "'%Y-%m'"
                    ")"
                ),

                "type": "time",
            },

            "process": {

                "label": "Process",

                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(jcpd.process_name), ''), "
                    "'Unknown'"
                    ")"
                ),

                "type": "category",
            },

            "job_card": {
                "label": "Job Card",
                "sql": "jcpd.job_card_no",
                "type": "category",
            },
        },

        "measures": {

            "completed_stages": {
                "label": "Completed Stages",
                "sql": "COUNT(*)",
                "format": "integer",
            },

            "job_cards": {
                "label": "Job Cards",
                "sql": "COUNT(DISTINCT jcpd.job_card_no)",
                "format": "integer",
            },

            "avg_planned_days": {
                "label": "Avg. Planned Days",
                "sql": (
                    "ROUND("
                    "AVG("
                    "COALESCE("
                    "pdd.default_days, "
                    "jcpd.days, "
                    "0"
                    ")"
                    "), "
                    "1"
                    ")"
                ),
                "format": "decimal",
            },

            "avg_actual_days": {
                "label": "Avg. Actual Days",
                "sql": (
                    "ROUND("
                    "AVG("
                    "COALESCE("
                    "jcpd.actual_days, "
                    "0"
                    ")"
                    "), "
                    "1"
                    ")"
                ),
                "format": "decimal",
            },

            "avg_delay_days": {
                "label": "Avg. Delay Days",
                "sql": (
                    "ROUND("
                    "AVG("
                    "GREATEST("
                    "COALESCE(jcpd.actual_days, 0)"
                    " - "
                    "COALESCE("
                    "pdd.default_days, "
                    "jcpd.days, "
                    "0"
                    "), "
                    "0"
                    ")"
                    "), "
                    "1"
                    ")"
                ),
                "format": "decimal",
            },
        },
    },


    "supervisor_activity": {

        "label": "Supervisor Activity",

        "description": (
            "Stage movement activity recorded "
            "in the JMS audit trail."
        ),

        "from_sql": """
            FROM audit_trail aud
        """,

        "base_where": """
            aud.new_stage <> 'Removed'

            AND aud.changed_by IS NOT NULL

            AND TRIM(aud.changed_by) <> ''

            AND LOWER(
                TRIM(aud.changed_by)
            )
            NOT IN (
                'not assigned',
                'notassigned',
                'admin',
                'system',
                'system correction'
            )
        """,

        "date_sql": (
            "DATE("
            "CONVERT_TZ("
            "aud.changed_at, "
            "'+00:00', "
            "'+05:30'"
            ")"
            ")"
        ),

        "dimensions": {

            "date": {

                "label": "Activity Date",

                "sql": (
                    "DATE("
                    "CONVERT_TZ("
                    "aud.changed_at, "
                    "'+00:00', "
                    "'+05:30'"
                    ")"
                    ")"
                ),

                "type": "date",
            },

            "month": {

                "label": "Activity Month",

                "sql": (
                    "DATE_FORMAT("
                    "CONVERT_TZ("
                    "aud.changed_at, "
                    "'+00:00', "
                    "'+05:30'"
                    "), "
                    "'%Y-%m'"
                    ")"
                ),

                "type": "time",
            },

            "supervisor": {

                "label": "Supervisor",

                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(aud.changed_by), ''), "
                    "'Unknown'"
                    ")"
                ),

                "type": "category",
            },

            "new_stage": {

                "label": "Moved To Process",

                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(aud.new_stage), ''), "
                    "'Unknown'"
                    ")"
                ),

                "type": "category",
            },

            "old_stage": {

                "label": "Previous Process",

                "sql": (
                    "COALESCE("
                    "NULLIF(TRIM(aud.old_stage), ''), "
                    "'Unknown'"
                    ")"
                ),

                "type": "category",
            },

            "job_card": {
                "label": "Job Card",
                "sql": "aud.job_card_no",
                "type": "category",
            },
        },

        "measures": {

            "stage_moves": {
                "label": "Stage Movements",
                "sql": "COUNT(*)",
                "format": "integer",
            },

            "job_cards": {
                "label": "Job Cards Handled",
                "sql": "COUNT(DISTINCT aud.job_card_no)",
                "format": "integer",
            },
        },
    },
}


def _analytics_studio_meta_v3():

    datasets = []


    for dataset_key, dataset in ANALYTICS_STUDIO_DATASETS.items():

        datasets.append({

            "key":
                dataset_key,

            "label":
                dataset["label"],

            "description":
                dataset["description"],

            "dimensions": [

                {
                    "key":
                        key,

                    "label":
                        value["label"],

                    "type":
                        value.get(
                            "type",
                            "category",
                        ),
                }

                for key, value
                in dataset[
                    "dimensions"
                ].items()
            ],

            "measures": [

                {
                    "key":
                        key,

                    "label":
                        value["label"],

                    "format":
                        value.get(
                            "format",
                            "number",
                        ),
                }

                for key, value
                in dataset[
                    "measures"
                ].items()
            ],
        })


    return datasets


@analytics_bp.route(
    "/api/analytics/studio/meta",
    methods=["GET"],
)
def analytics_studio_meta():

    return jsonify({

        "success": True,

        "datasets":
            _analytics_studio_meta_v3(),

        "chart_types": [

            {
                "key": "bar",
                "label": "Bar",
            },

            {
                "key": "line",
                "label": "Line",
            },

            {
                "key": "area",
                "label": "Area",
            },

            {
                "key": "stacked",
                "label": "Stacked Bar",
            },

            {
                "key": "pie",
                "label": "Pie / Doughnut",
            },
        ],
    })


def _analytics_studio_json_value_v3(value):

    if value is None:
        return None


    try:

        from decimal import Decimal


        if isinstance(
            value,
            Decimal,
        ):

            return float(value)

    except Exception:

        pass


    if hasattr(
        value,
        "isoformat",
    ):

        try:

            return value.isoformat()

        except Exception:

            pass


    return value


@analytics_bp.route(
    "/api/analytics/studio/query",
    methods=["POST"],
)
def analytics_studio_query():

    conn = None
    cursor = None


    try:

        payload = request.get_json(silent=True) or {}


        dataset_key = str(
            payload.get(
                "dataset"
            ) or ""
        ).strip()


        dimension_key = str(
            payload.get(
                "dimension"
            ) or ""
        ).strip()


        split_key = str(
            payload.get(
                "split_by"
            ) or ""
        ).strip()


        requested_measures = (
            payload.get(
                "measures"
            )
            or []
        )


        if not isinstance(
            requested_measures,
            list,
        ):

            requested_measures = []


        dataset = ANALYTICS_STUDIO_DATASETS.get(
            dataset_key
        )


        if not dataset:

            return jsonify({
                "success": False,
                "error": (
                    "Invalid Analytics Studio data source."
                ),
            }), 400


        dimensions = dataset["dimensions"]

        measures = dataset["measures"]


        if dimension_key not in dimensions:

            return jsonify({
                "success": False,
                "error": "Invalid Compare By field.",
            }), 400


        clean_measures = []


        for measure_key in requested_measures:

            measure_key = str(
                measure_key or ""
            ).strip()


            if (
                measure_key in measures
                and
                measure_key not in clean_measures
            ):

                clean_measures.append(
                    measure_key
                )


        if not clean_measures:

            return jsonify({
                "success": False,
                "error": (
                    "Select at least one analysis value."
                ),
            }), 400


        if len(clean_measures) > 4:

            return jsonify({
                "success": False,
                "error": (
                    "Maximum 4 values can be "
                    "compared on one chart."
                ),
            }), 400


        if (
            split_key
            and
            split_key not in dimensions
        ):

            return jsonify({
                "success": False,
                "error": "Invalid Split By field.",
            }), 400


        if split_key == dimension_key:

            split_key = ""


        from_date = str(
            payload.get(
                "from_date"
            )
            or "1900-01-01"
        ).strip()


        to_date = str(
            payload.get(
                "to_date"
            )
            or "9999-12-31"
        ).strip()


        dimension_sql = dimensions[
            dimension_key
        ]["sql"]


        select_parts = [
            f"{dimension_sql} AS dimension"
        ]


        group_parts = [
            dimension_sql
        ]


        if split_key:

            split_sql = dimensions[
                split_key
            ]["sql"]


            select_parts.append(
                f"{split_sql} AS split_value"
            )


            group_parts.append(
                split_sql
            )


        for measure_key in clean_measures:

            select_parts.append(
                f"{measures[measure_key]['sql']} "
                f"AS `{measure_key}`"
            )


        sql = f"""
            SELECT
                {", ".join(select_parts)}

            {dataset["from_sql"]}

            WHERE
                {dataset["base_where"]}

              AND
                {dataset["date_sql"]}
                BETWEEN %s AND %s
        """


        params = [
            from_date,
            to_date,
        ]


        user_filters = (
            payload.get(
                "filters"
            )
            or []
        )


        if not isinstance(
            user_filters,
            list,
        ):

            user_filters = []


        for item in user_filters[:4]:

            if not isinstance(
                item,
                dict,
            ):

                continue


            filter_dimension = str(
                item.get(
                    "dimension"
                ) or ""
            ).strip()


            filter_value = str(
                item.get(
                    "value"
                ) or ""
            ).strip()


            if (
                not filter_dimension
                or
                not filter_value
                or
                filter_dimension not in dimensions
            ):

                continue


            filter_sql = dimensions[
                filter_dimension
            ]["sql"]


            sql += (
                " AND LOWER("
                "CAST("
                f"{filter_sql} "
                "AS CHAR"
                ")"
                ") LIKE %s"
            )


            params.append(
                f"%{filter_value.lower()}%"
            )


        sql += (
            " GROUP BY " +
            ", ".join(
                group_parts
            )
        )


        dimension_type = dimensions[
            dimension_key
        ].get(
            "type",
            "category",
        )


        first_measure = clean_measures[0]


        if dimension_type in (
            "date",
            "time",
        ):

            sql += (
                " ORDER BY dimension ASC"
            )

        else:

            sql += (
                " ORDER BY "
                f"`{first_measure}` DESC"
            )


        try:

            limit = int(
                payload.get(
                    "limit"
                )
                or 40
            )

        except Exception:

            limit = 40


        limit = max(
            5,
            min(
                limit,
                200,
            ),
        )


        sql += (
            f" LIMIT {limit}"
        )


        conn = get_connection()


        cursor = conn.cursor(
            dictionary=True
        )


        cursor.execute(
            sql,
            tuple(params),
        )


        rows = cursor.fetchall()


        output_rows = [

            {

                key:
                    _analytics_studio_json_value_v3(
                        value
                    )

                for key, value
                in row.items()
            }

            for row in rows
        ]


        return jsonify({

            "success": True,

            "dataset":
                dataset_key,

            "dataset_label":
                dataset["label"],

            "dimension":
                dimension_key,

            "dimension_label":
                dimensions[
                    dimension_key
                ]["label"],

            "dimension_type":
                dimension_type,

            "split_by":
                split_key,

            "split_label":
                (
                    dimensions[
                        split_key
                    ]["label"]

                    if split_key

                    else ""
                ),

            "measures":
                clean_measures,

            "measure_labels": {

                key:
                    measures[
                        key
                    ]["label"]

                for key
                in clean_measures
            },

            "measure_formats": {

                key:
                    measures[
                        key
                    ].get(
                        "format",
                        "number",
                    )

                for key
                in clean_measures
            },

            "from_date":
                from_date,

            "to_date":
                to_date,

            "rows":
                output_rows,
        })


    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error),
        }), 500


    finally:

        if cursor:

            try:

                cursor.close()

            except Exception:

                pass


        if conn:

            try:

                conn.close()

            except Exception:

                pass


