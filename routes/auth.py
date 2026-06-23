from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from db import get_connection

auth_bp = Blueprint("auth", __name__)


def redirect_by_role(role):
    if role == "admin":
        return redirect(url_for("pages.admin_dashboard"))

    if role == "supervisor":
        return redirect(url_for("pages.supervisor_dashboard"))

    if role == "operator":
        return redirect(url_for("pages.index"))

    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id") and request.method == "GET":
        return redirect_by_role(session.get("role"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, username, password_hash, role, full_name, is_active
            FROM users
            WHERE BINARY username = %s
            LIMIT 1
        """, (username,))

        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and user["is_active"] == 1 and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            session["show_welcome"] = True

            return redirect_by_role(user["role"])

        flash("Invalid username or password")
        return redirect(url_for("auth.login"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
