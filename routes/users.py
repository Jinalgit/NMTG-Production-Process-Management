from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash
from db import get_connection

users_bp = Blueprint("users", __name__)

ALLOWED_ROLES = {"admin", "supervisor", "operator"}


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
                u["created_at"] = u["created_at"].strftime("%Y-%m-%d %H:%M")

        cursor.close()
        conn.close()

        return jsonify({"success": True, "users": users})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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
