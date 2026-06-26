from datetime import timedelta

from flask import Blueprint, jsonify, request, session

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt
from werkzeug.security import generate_password_hash
from db import get_connection
from permission_utils import (
    PAGE3_TRACEABILITY,
    PAGE5_BASE_FIELDS,
    PAGE5_PPC,
    PROCESS_FIELDS,
    ensure_permission_tables,
    seed_default_permissions,
)

users_bp = Blueprint("users", __name__)

ALLOWED_ROLES = {"admin", "supervisor", "operator"}
PAGE_PERMISSION_MASTER = [
    {"page_name": PAGE3_TRACEABILITY, "label": "Traceability"},
    {"page_name": PAGE5_PPC, "label": "Page 5 PPC"},
]
FIELD_PERMISSION_MASTER = [
    *[
        {"page_name": PAGE5_PPC, "field_name": field, "label": field.replace("_", " ").title()}
        for field in sorted(PAGE5_BASE_FIELDS | PROCESS_FIELDS)
    ],
    *[
        {"page_name": PAGE3_TRACEABILITY, "field_name": field, "label": field.replace("_", " ").title()}
        for field in sorted(PROCESS_FIELDS)
    ],
]


@users_bp.route("/api/users/create", methods=["POST"])
def create_user():
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    data = request.json
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    role = (data.get("role") or "").strip().lower()

    if not username or not password or not role:
        return jsonify({"success": False, "error": "Username, password, and role are required"}), 400

    if role not in ALLOWED_ROLES:
        return jsonify({"success": False, "error": f"Role must be one of: {', '.join(ALLOWED_ROLES)}"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id FROM users WHERE BINARY username = %s", (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": f"Username '{username}' already exists"}), 400

        password_hash = generate_password_hash(password)

        cursor.execute("""
            INSERT INTO users (username, password_hash, role, full_name, is_active)
            VALUES (%s, %s, %s, %s, 1)
        """, (username, password_hash, role, full_name or None))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": f"User '{username}' created successfully"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@users_bp.route("/api/users", methods=["GET"])
def list_users():
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, username, full_name, role, is_active, created_at
            FROM users
            ORDER BY created_at DESC
        """)
        users = cursor.fetchall()

        for u in users:
            if u.get("created_at"):
                u["created_at"] = _to_ist(u["created_at"]).strftime("%Y-%m-%d %H:%M")

        cursor.close()
        conn.close()

        return jsonify({"success": True, "users": users})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@users_bp.route("/api/user-management/users", methods=["GET"])
def user_management_users():
    return list_users()


@users_bp.route("/api/user-management/permission-master", methods=["GET"])
def permission_master():
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_permission_tables(cursor)
        seed_default_permissions(cursor)
        conn.commit()

        cursor.execute("""
            SELECT process_name
            FROM process_default_days
            WHERE process_name IS NOT NULL AND TRIM(process_name) != ''
            ORDER BY id
        """)
        processes = [r["process_name"] for r in cursor.fetchall()]

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "processes": processes,
            "pages": PAGE_PERMISSION_MASTER,
            "fields": FIELD_PERMISSION_MASTER,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@users_bp.route("/api/user-management/permissions/<int:user_id>", methods=["GET"])
def get_user_permissions(user_id):
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_permission_tables(cursor)
        seed_default_permissions(cursor)
        conn.commit()

        cursor.execute("SELECT id, username, role, is_active FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "User not found"}), 404

        cursor.execute("""
            SELECT process_name
            FROM supervisor_process_access
            WHERE user_id = %s
            ORDER BY process_name
        """, (user_id,))
        processes = [r["process_name"] for r in cursor.fetchall()]

        cursor.execute("""
            SELECT page_name, field_name, can_view, can_edit
            FROM user_field_permissions
            WHERE user_id = %s
            ORDER BY page_name, field_name
        """, (user_id,))
        fields = cursor.fetchall()

        cursor.execute("""
            SELECT page_name, can_access
            FROM user_page_permissions
            WHERE user_id = %s
            ORDER BY page_name
        """, (user_id,))
        pages = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "user": user,
            "processes": processes,
            "fields": fields,
            "pages": pages,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@users_bp.route("/api/user-management/save-permissions", methods=["POST"])
def save_user_permissions():
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    data = request.json or {}
    user_id = data.get("user_id")
    processes = data.get("processes") or []
    fields = data.get("fields") or []
    pages = data.get("pages") or []

    if not user_id:
        return jsonify({"success": False, "error": "User is required"}), 400

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_permission_tables(cursor)

        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            return jsonify({"success": False, "error": "User not found"}), 404

        cursor.execute("DELETE FROM supervisor_process_access WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM user_field_permissions WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM user_page_permissions WHERE user_id = %s", (user_id,))

        for process_name in processes:
            process_name = (process_name or "").strip()
            if process_name:
                cursor.execute("""
                    INSERT INTO supervisor_process_access (user_id, process_name)
                    VALUES (%s, %s)
                """, (user_id, process_name))

        for field in fields:
            page_name = (field.get("page_name") or "").strip()
            field_name = (field.get("field_name") or "").strip()
            if page_name and field_name:
                cursor.execute("""
                    INSERT INTO user_field_permissions
                        (user_id, page_name, field_name, can_view, can_edit)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    user_id,
                    page_name,
                    field_name,
                    1 if field.get("can_view", 1) else 0,
                    1 if field.get("can_edit") else 0,
                ))

        for page in pages:
            page_name = (page.get("page_name") or "").strip()
            if page_name:
                cursor.execute("""
                    INSERT INTO user_page_permissions (user_id, page_name, can_access)
                    VALUES (%s, %s, %s)
                """, (user_id, page_name, 1 if page.get("can_access", 1) else 0))

        conn.commit()
        return jsonify({"success": True, "message": "Permissions saved"})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@users_bp.route("/api/users/<int:user_id>/toggle-active", methods=["POST"])
def toggle_user_active(user_id):
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    if session.get("user_id") == user_id:
        return jsonify({"success": False, "error": "You cannot deactivate your own account"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT is_active, username FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "User not found"}), 404

        new_status = 0 if user["is_active"] == 1 else 1

        cursor.execute(
            "UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        action = "activated" if new_status == 1 else "deactivated"
        return jsonify({"success": True, "message": f"User '{user['username']}' {action}", "is_active": new_status})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@users_bp.route("/api/users/<int:user_id>/update-role", methods=["POST"])
def update_user_role(user_id):
    if session.get("role") != "admin":
        return jsonify({"success": False, "error": "Admin access required"}), 403

    if session.get("user_id") == user_id:
        return jsonify({"success": False, "error": "You cannot change your own role"}), 400

    data = request.json
    role = (data.get("role") or "").strip().lower()

    if role not in ALLOWED_ROLES:
        return jsonify({"success": False, "error": f"Role must be one of: {', '.join(ALLOWED_ROLES)}"}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "User not found"}), 404

        cursor.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True, "message": f"Role updated to '{role}' for '{user['username']}'"})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
