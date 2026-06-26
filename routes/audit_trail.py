"""
Audit Trail API routes for Demo 2.
Returns the full history of WIP stage changes.
"""

from datetime import timedelta

from flask import Blueprint, jsonify
from mysql.connector import Error
from db import get_connection

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt

audit_trail_bp = Blueprint("audit_trail", __name__)


@audit_trail_bp.route("/api/audit_trail", methods=["GET"])
def get_audit_trail():
    """Fetch full audit trail for Data View page."""
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT job_card_no, item_name, old_stage, new_stage,
                   changed_by, changed_at
            FROM audit_trail
            ORDER BY changed_at DESC
        """)
        rows = cursor.fetchall()
        for r in rows:
            if r.get("changed_at"):
                r["changed_at"] = _to_ist(r["changed_at"]).strftime("%Y-%m-%d %H:%M")
        cursor.close(); conn.close()
        return jsonify({"success": True, "data": rows})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@audit_trail_bp.route("/api/audit_trail/<path:job_card_no>", methods=["GET"])
def get_audit_trail_by_jc(job_card_no):
    """Fetch audit trail for a specific job card."""
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT job_card_no, item_name, old_stage, new_stage,
                   changed_by, changed_at
            FROM audit_trail
            WHERE job_card_no = %s
            ORDER BY changed_at DESC
        """, (job_card_no,))
        rows = cursor.fetchall()
        for r in rows:
            if r.get("changed_at"):
                r["changed_at"] = _to_ist(r["changed_at"]).strftime("%Y-%m-%d %H:%M")
        cursor.close(); conn.close()
        return jsonify({"success": True, "data": rows})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500
