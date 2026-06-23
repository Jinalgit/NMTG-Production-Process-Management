"""
Analytics API routes for Demo 2.
Includes WIP distribution and process duration stats.
"""

from flask import Blueprint, jsonify
from db import get_connection

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) as total FROM job_cards")
        total_jc = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM process_master")
        total_items = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM quality_checks")
        total_qc = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT quality_result, COUNT(*) as cnt
            FROM quality_check_details GROUP BY quality_result
        """)
        qr = {r["quality_result"]: r["cnt"] for r in cursor.fetchall()}
        ok = qr.get("OK", 0)
        not_ok = qr.get("NOT OK", 0)
        total = ok + not_ok
        ok_pct = round(ok / total * 100, 1) if total > 0 else 0

        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "total_job_cards": total_jc,
            "total_items": total_items,
            "total_quality_checks": total_qc,
            "ok": ok, "not_ok": not_ok, "ok_pct": ok_pct,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analytics_bp.route("/api/analytics/wip_distribution", methods=["GET"])
def wip_distribution():
    """WIP status distribution across all job card items."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT wip_status, COUNT(*) as count
            FROM job_card_items
            GROUP BY wip_status
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "data": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
