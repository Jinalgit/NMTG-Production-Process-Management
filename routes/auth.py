from datetime import datetime, timedelta

import hashlib
import os
import socket
import subprocess

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from db import get_connection
from permission_utils import is_gaurang_special_user

auth_bp = Blueprint("auth", __name__)



# LOGIN_ACTIVITY_TRACKING_V1

def _now_ist():
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


# AUTO_DEVICE_NAME_DETECTION_V2

def _short_hostname(value):
    value = (value or "").strip()

    if not value:
        return ""

    if value.lower() in {
        "localhost",
        "localhost.localdomain",
    }:
        return ""

    # Convert FQDN:
    # Lenovo-Laptop.NMTG.COM -> Lenovo-Laptop
    return value.split(".")[0].strip()


def _resolve_device_name(ip_address):
    """
    Resolve the Windows/LAN device name automatically.

    Priority:
    1. Local machine hostname for loopback login
    2. Reverse DNS lookup
    3. FQDN lookup
    4. Windows NetBIOS lookup
    5. Unknown Device
    """

    ip_address = (
        ip_address or ""
    ).strip()

    # IPv4-mapped IPv6
    if ip_address.startswith("::ffff:"):
        ip_address = ip_address[7:]

    # Login from the JMS machine itself.
    if ip_address in {
        "127.0.0.1",
        "::1",
        "",
    }:
        name = _short_hostname(
            socket.gethostname()
        )

        if name:
            return name

        name = _short_hostname(
            os.environ.get(
                "COMPUTERNAME",
                "",
            )
        )

        if name:
            return name

        return "Unknown Device"

    # --------------------------------------------------------
    # Reverse DNS
    # --------------------------------------------------------

    try:
        host = socket.gethostbyaddr(
            ip_address
        )[0]

        name = _short_hostname(host)

        if (
            name
            and name.lower()
            != ip_address.lower()
        ):
            return name

    except Exception:
        pass

    # --------------------------------------------------------
    # FQDN lookup
    # --------------------------------------------------------

    try:
        host = socket.getfqdn(
            ip_address
        )

        name = _short_hostname(host)

        if (
            name
            and name.lower()
            != ip_address.lower()
        ):
            return name

    except Exception:
        pass

    # --------------------------------------------------------
    # Windows NetBIOS fallback
    # --------------------------------------------------------

    try:
        result = subprocess.run(
            [
                "nbtstat",
                "-A",
                ip_address,
            ],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=(
                subprocess.CREATE_NO_WINDOW
                if hasattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                )
                else 0
            ),
        )

        output = (
            result.stdout or ""
        )

        for line in output.splitlines():

            upper_line = line.upper()

            if (
                "<00>" in upper_line
                and "UNIQUE" in upper_line
            ):
                name = (
                    line.split("<00>")[0]
                    .strip()
                )

                if name:
                    return name

    except Exception:
        pass

    return "Unknown Device"


def _automatic_device_id(
    device_name,
    ip_address,
):
    """
    Internal deterministic identifier.

    Device ID is not shown to the user.
    """
    source = (
        (device_name or "")
        .strip()
        .lower()
    )

    if not source:
        source = (
            ip_address
            or "unknown-device"
        )

    return hashlib.sha256(
        source.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()


# LOGIN_ACTIVITY_REAL_IP_V2

def _local_lan_ip():
    """
    Return the LAN IPv4 address of the machine running JMS.

    Used only when Flask receives loopback traffic such as
    127.0.0.1 / ::1 during same-PC LOCAL testing.
    """

    # Route-aware detection first.
    try:
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        try:
            sock.connect(
                ("8.8.8.8", 80)
            )

            ip_address = (
                sock.getsockname()[0]
            )

            if (
                ip_address
                and not ip_address.startswith("127.")
                and ip_address != "0.0.0.0"
            ):
                return ip_address

        finally:
            sock.close()

    except Exception:
        pass


    # Hostname-based fallback.
    try:
        host = socket.gethostname()

        addresses = socket.getaddrinfo(
            host,
            None,
            family=socket.AF_INET,
        )

        for item in addresses:

            ip_address = item[4][0]

            if (
                ip_address
                and not ip_address.startswith("127.")
                and not ip_address.startswith("169.254.")
                and ip_address != "0.0.0.0"
            ):
                return ip_address

    except Exception:
        pass

    return "127.0.0.1"


def _client_ip():
    """
    Return the actual client IP where possible.

    Priority:
    1. X-Forwarded-For when running behind a trusted proxy
    2. Flask remote_addr for normal network clients
    3. This PC's LAN IP when testing through localhost
    """

    forwarded = (
        request.headers.get(
            "X-Forwarded-For"
        )
        or ""
    ).strip()

    if forwarded:

        forwarded_ip = (
            forwarded
            .split(",")[0]
            .strip()
        )

        if forwarded_ip:
            return forwarded_ip


    remote_ip = (
        request.remote_addr
        or ""
    ).strip()


    # IPv4-mapped IPv6.
    if remote_ip.startswith(
        "::ffff:"
    ):
        remote_ip = remote_ip[7:]


    if remote_ip in {
        "",
        "127.0.0.1",
        "::1",
    }:
        return _local_lan_ip()


    return remote_ip


def _record_successful_login(user):
    """
    Records one successful login and updates users.last_login.

    Tracking failure must not prevent a valid JMS login.
    """
    conn = None
    cursor = None

    try:
        now = _now_ist()

        ip_address = _client_ip()

        device_name = _resolve_device_name(
            ip_address
        )

        device_id = _automatic_device_id(
            device_name,
            ip_address,
        )

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE users
            SET last_login = %s
            WHERE id = %s
            """,
            (
                now,
                user["id"],
            ),
        )

        cursor.execute(
            """
            INSERT INTO user_login_activity (
                user_id,
                device_id,
                device_name,
                ip_address,
                login_at,
                last_seen_at,
                logout_at,
                user_agent
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, NULL, %s
            )
            """,
            (
                user["id"],
                device_id,
                device_name,
                ip_address,
                now,
                now,
                request.headers.get(
                    "User-Agent",
                    "",
                ),
            ),
        )

        activity_id = cursor.lastrowid

        conn.commit()

        return activity_id

    except Exception as exc:
        if conn:
            conn.rollback()

        print(
            "[Login Activity] Failed to record login:",
            exc,
        )

        return None

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


def _record_logout():
    activity_id = session.get(
        "login_activity_id"
    )

    user_id = session.get(
        "user_id"
    )

    if not activity_id or not user_id:
        return

    conn = None
    cursor = None

    try:
        now = _now_ist()

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE user_login_activity
            SET
                last_seen_at = %s,
                logout_at = %s
            WHERE id = %s
              AND user_id = %s
              AND logout_at IS NULL
            """,
            (
                now,
                now,
                activity_id,
                user_id,
            ),
        )

        conn.commit()

    except Exception as exc:
        if conn:
            conn.rollback()

        print(
            "[Login Activity] Failed to record logout:",
            exc,
        )

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


def redirect_by_role(role):
    # Special operational access for gaurang user_id=5; excludes user management.
    if is_gaurang_special_user():
        return redirect(url_for("pages.welcome"))

    if role == "admin":
        return redirect(url_for("pages.welcome"))

    if role == "plant_head":
        return redirect(url_for("pages.welcome"))

    if role == "supervisor":
        return redirect(url_for("pages.welcome"))

    if role == "operator":
        return redirect(url_for("pages.welcome"))

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

            activity_id = _record_successful_login(
                user
            )

            if activity_id:
                session["login_activity_id"] = activity_id

            return redirect_by_role(user["role"])

        flash("Invalid username or password")
        return redirect(url_for("auth.login"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    _record_logout()
    session.clear()
    return redirect(url_for("auth.login"))
