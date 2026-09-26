from datetime import datetime, timedelta
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file, session

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt
from werkzeug.security import generate_password_hash

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from db import get_connection
from permission_utils import (
    PAGE3_TRACEABILITY,
    PAGE5_BASE_FIELDS,
    PAGE5_PPC,
    PROCESS_FIELDS,
    ensure_permission_tables,
    is_gaurang_special_user,
    seed_default_permissions,
)

users_bp = Blueprint("users", __name__)

ALLOWED_ROLES = {"admin", "plant_head", "supervisor", "operator"}
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


def has_user_management_access():
    # Special operational access for gaurang user_id=5; excludes user management.
    return session.get("role") == "admin" and not is_gaurang_special_user()



# LOGIN_ACTIVITY_API_V1

def _login_activity_now_ist():
    return (
        datetime.utcnow()
        + timedelta(
            hours=5,
            minutes=30,
        )
    )


def _activity_datetime_display(value):
    if not value:
        return "-"

    return value.strftime(
        "%d-%m-%Y %I:%M:%S %p"
    )


# LOGIN_ACTIVITY_DATE_FILTER_COUNT_V3
def _login_activity_date_filters():
    from_date = (
        request.args.get(
            "from_date",
            "",
        )
        or ""
    ).strip()

    to_date = (
        request.args.get(
            "to_date",
            "",
        )
        or ""
    ).strip()

    for value in (
        from_date,
        to_date,
    ):
        if value:
            datetime.strptime(
                value,
                "%Y-%m-%d",
            )

    if (
        from_date
        and to_date
        and from_date > to_date
    ):
        raise ValueError(
            "From Date cannot be after To Date."
        )

    return from_date, to_date


@users_bp.route(
    "/api/login-activity/users",
    methods=["GET"],
)
def login_activity_users():

    if not has_user_management_access():
        return jsonify({
            "success": False,
            "error": "Admin access required",
        }), 403

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute("""
            SELECT
                id,
                username,
                full_name,
                role,
                is_active,
                last_login
            FROM users
            ORDER BY
                LOWER(username),
                id
        """)

        rows = cursor.fetchall()

        # LOGIN_ACTIVITY_ONLINE_STATUS_V2
        # A user is considered Online only when an open
        # login session has recent activity.
        online_cutoff = (
            _login_activity_now_ist()
            - timedelta(minutes=10)
        )

        cursor.execute("""
            SELECT
                user_id,
                MAX(last_seen_at) AS last_seen_at
            FROM user_login_activity
            WHERE logout_at IS NULL
              AND last_seen_at >= %s
            GROUP BY user_id
        """, (
            online_cutoff,
        ))

        online_user_ids = {
            row["user_id"]
            for row in cursor.fetchall()
        }

        # LOGIN_ACTIVITY_ONLINE_USERS_ONLY_V5
        # Main page shows only users with a currently
        # active login session.
        rows = [
            row
            for row in rows
            if row["id"] in online_user_ids
        ]

        # Login count follows the selected activity date range.
        try:
            from_date, to_date = (
                _login_activity_date_filters()
            )
        except ValueError as exc:
            return jsonify({
                "success": False,
                "error": str(exc),
            }), 400

        count_conditions = []
        count_params = []

        if from_date:
            count_conditions.append(
                "login_at >= %s"
            )
            count_params.append(
                from_date
            )

        if to_date:
            count_conditions.append(
                "login_at < DATE_ADD(%s, INTERVAL 1 DAY)"
            )
            count_params.append(
                to_date
            )

        count_where = ""

        if count_conditions:
            count_where = (
                "WHERE "
                + " AND ".join(
                    count_conditions
                )
            )

        cursor.execute(
            f"""
            SELECT
                user_id,
                COUNT(*) AS login_count
            FROM user_login_activity
            {count_where}
            GROUP BY user_id
            """,
            tuple(count_params),
        )

        login_counts = {
            row["user_id"]:
                int(
                    row["login_count"]
                    or 0
                )
            for row in cursor.fetchall()
        }

        users = []

        for row in rows:

            login_status = (
                "Online"
                if row["id"] in online_user_ids
                else "Offline"
            )

            users.append({
                "id": row["id"],
                "username": row["username"],
                "full_name": (
                    row["full_name"]
                    or ""
                ),
                "role": row["role"],
                "is_active": bool(
                    row["is_active"]
                ),
                "login_status": login_status,
                "login_count": login_counts.get(
                    row["id"],
                    0,
                ),
                "last_login": (
                    row["last_login"].isoformat()
                    if row["last_login"]
                    else None
                ),
                "last_login_display":
                    _activity_datetime_display(
                        row["last_login"]
                    ),
            })

        return jsonify({
            "success": True,
            "users": users,
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


@users_bp.route(
    "/api/login-activity/users/<int:user_id>",
    methods=["GET"],
)
def login_activity_user_detail(user_id):

    if not has_user_management_access():
        return jsonify({
            "success": False,
            "error": "Admin access required",
        }), 403

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute("""
            SELECT
                id,
                username,
                full_name,
                role,
                is_active,
                last_login
            FROM users
            WHERE id = %s
            LIMIT 1
        """, (
            user_id,
        ))

        user = cursor.fetchone()

        if not user:
            return jsonify({
                "success": False,
                "error": "User not found",
            }), 404

        try:
            from_date, to_date = (
                _login_activity_date_filters()
            )
        except ValueError as exc:
            return jsonify({
                "success": False,
                "error": str(exc),
            }), 400

        detail_conditions = [
            "user_id = %s"
        ]

        detail_params = [
            user_id
        ]

        if from_date:
            detail_conditions.append(
                "login_at >= %s"
            )
            detail_params.append(
                from_date
            )

        if to_date:
            detail_conditions.append(
                "login_at < DATE_ADD(%s, INTERVAL 1 DAY)"
            )
            detail_params.append(
                to_date
            )

        detail_where = (
            " AND ".join(
                detail_conditions
            )
        )

        cursor.execute(
            f"""
            SELECT
                id,
                device_name,
                ip_address,
                login_at,
                last_seen_at,
                logout_at
            FROM user_login_activity
            WHERE {detail_where}
            ORDER BY
                login_at DESC,
                id DESC
            LIMIT 500
            """,
            tuple(detail_params),
        )

        rows = cursor.fetchall()

        now = _login_activity_now_ist()

        activity = []

        for row in rows:

            logout_at = row[
                "logout_at"
            ]

            last_seen_at = row[
                "last_seen_at"
            ]

            if logout_at:
                status = "Logged Out"

            elif last_seen_at:
                age_seconds = (
                    now
                    - last_seen_at
                ).total_seconds()

                if age_seconds <= 600:
                    status = "Active"
                else:
                    status = "Session Ended"

            else:
                status = "Session Ended"

            activity.append({
                "id": row["id"],

                "device_name": (
                    row["device_name"]
                    or "Unknown Device"
                ),

                "ip_address": (
                    row["ip_address"]
                    or "-"
                ),

                "login_at_display":
                    _activity_datetime_display(
                        row["login_at"]
                    ),

                "last_seen_at_display":
                    _activity_datetime_display(
                        row["last_seen_at"]
                    ),

                "logout_at_display":
                    _activity_datetime_display(
                        row["logout_at"]
                    ),

                "status": status,
            })

        return jsonify({
            "success": True,

            "user": {
                "id": user["id"],
                "username":
                    user["username"],
                "full_name":
                    user["full_name"]
                    or "",
                "role":
                    user["role"],
                "is_active":
                    bool(
                        user["is_active"]
                    ),
                "last_login_display":
                    _activity_datetime_display(
                        user["last_login"]
                    ),
            },

            "activity": activity,
        })

    except Exception as exc:
        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()



# LOGIN_ACTIVITY_EXCEL_EXPORT_V4
@users_bp.route(
    "/api/login-activity/export-excel",
    methods=["GET"],
)
def export_login_activity_excel():

    if not has_user_management_access():
        return jsonify({
            "success": False,
            "error": "Admin access required",
        }), 403

    conn = None
    cursor = None

    try:
        try:
            from_date, to_date = (
                _login_activity_date_filters()
            )
        except ValueError as exc:
            return jsonify({
                "success": False,
                "error": str(exc),
            }), 400


        user_id = request.args.get(
            "user_id",
            type=int,
        )

        search = (
            request.args.get(
                "search",
                "",
            )
            or ""
        ).strip()


        conn = get_connection()
        cursor = conn.cursor(
            dictionary=True
        )


        selected_username = None

        if user_id:

            cursor.execute("""
                SELECT
                    id,
                    username
                FROM users
                WHERE id = %s
                LIMIT 1
            """, (
                user_id,
            ))

            selected_user = (
                cursor.fetchone()
            )

            if not selected_user:
                return jsonify({
                    "success": False,
                    "error": "User not found",
                }), 404

            selected_username = (
                selected_user[
                    "username"
                ]
            )


        conditions = []
        params = []


        if user_id:
            conditions.append(
                "ula.user_id = %s"
            )

            params.append(
                user_id
            )


        if from_date:
            conditions.append(
                "ula.login_at >= %s"
            )

            params.append(
                from_date
            )


        if to_date:
            conditions.append(
                "ula.login_at < "
                "DATE_ADD(%s, INTERVAL 1 DAY)"
            )

            params.append(
                to_date
            )


        if search and not user_id:

            search_value = (
                "%"
                + search
                + "%"
            )

            conditions.append("""
                (
                    u.username LIKE %s
                    OR
                    COALESCE(
                        u.full_name,
                        ''
                    ) LIKE %s
                    OR
                    u.role LIKE %s
                )
            """)

            params.extend([
                search_value,
                search_value,
                search_value,
            ])


        where_sql = ""

        if conditions:
            where_sql = (
                "WHERE "
                + " AND ".join(
                    conditions
                )
            )


        cursor.execute(
            f"""
            SELECT
                ula.id,
                u.username,
                u.full_name,
                u.role,

                ula.device_name,
                ula.ip_address,

                ula.login_at,
                ula.last_seen_at,
                ula.logout_at

            FROM user_login_activity ula

            INNER JOIN users u
                ON u.id = ula.user_id

            {where_sql}

            ORDER BY
                ula.login_at DESC,
                ula.id DESC
            """,
            tuple(params),
        )

        rows = cursor.fetchall()


        now = (
            _login_activity_now_ist()
        )


        wb = Workbook()
        ws = wb.active
        ws.title = "Login Activity"


        headers = [
            "User",
            "Full Name",
            "Role",
            "Device Name",
            "IP Address",
            "Login Time",
            "Last Activity",
            "Logout Time",
            "Status",
        ]

        ws.append(headers)


        for cell in ws[1]:

            cell.font = Font(
                bold=True
            )

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )


        for row in rows:

            logout_at = row[
                "logout_at"
            ]

            last_seen_at = row[
                "last_seen_at"
            ]


            if logout_at:

                status = (
                    "Logged Out"
                )

            elif last_seen_at:

                age_seconds = (
                    now
                    - last_seen_at
                ).total_seconds()

                if age_seconds <= 600:
                    status = "Active"
                else:
                    status = (
                        "Session Ended"
                    )

            else:

                status = (
                    "Session Ended"
                )


            role = (
                row["role"]
                or ""
            )

            if role == "plant_head":
                role_display = (
                    "Plant Head"
                )
            else:
                role_display = (
                    role.replace(
                        "_",
                        " ",
                    ).title()
                )


            ws.append([
                row["username"]
                or "",

                row["full_name"]
                or "",

                role_display,

                row["device_name"]
                or "Unknown Device",

                row["ip_address"]
                or "",

                row["login_at"],

                row["last_seen_at"],

                row["logout_at"],

                status,
            ])


        # Excel date formatting
        for row in ws.iter_rows(
            min_row=2,
            min_col=6,
            max_col=8,
        ):

            for cell in row:

                if cell.value:
                    cell.number_format = (
                        "dd-mm-yyyy "
                        "hh:mm:ss AM/PM"
                    )


        ws.freeze_panes = "A2"

        if ws.max_row >= 1:
            ws.auto_filter.ref = (
                ws.dimensions
            )


        widths = {
            "A": 20,
            "B": 28,
            "C": 18,
            "D": 28,
            "E": 18,
            "F": 24,
            "G": 24,
            "H": 24,
            "I": 18,
        }

        for column, width in (
            widths.items()
        ):

            ws.column_dimensions[
                column
            ].width = width


        output = BytesIO()

        wb.save(
            output
        )

        output.seek(0)


        if selected_username:

            safe_name = "".join(
                ch
                if (
                    ch.isalnum()
                    or ch in "-_"
                )
                else "_"
                for ch in selected_username
            )

            filename = (
                "Login_Activity_"
                + safe_name
            )

        else:

            filename = (
                "Login_Activity_All_Users"
            )


        if from_date or to_date:

            filename += "_"

            filename += (
                from_date
                or "Start"
            )

            filename += "_to_"

            filename += (
                to_date
                or "Today"
            )


        filename += ".xlsx"


        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype=(
                "application/"
                "vnd.openxmlformats-"
                "officedocument."
                "spreadsheetml.sheet"
            ),
        )


    except Exception as exc:

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()


@users_bp.route("/api/users/create", methods=["POST"])
def create_user():
    if not has_user_management_access():
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
    if not has_user_management_access():
        return jsonify({"success": False, "error": "Admin access required"}), 403

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, username, full_name, role, is_active, created_at, last_login
            FROM users
            ORDER BY created_at DESC
        """)
        users = cursor.fetchall()

        for u in users:
            if u.get("created_at"):
                u["created_at"] = _to_ist(u["created_at"]).strftime("%Y-%m-%d %H:%M")
            if u.get("last_login"):
                u["last_login"] = _to_ist(u["last_login"]).strftime("%Y-%m-%d %H:%M")

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
    if not has_user_management_access():
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
    if not has_user_management_access():
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
    if not has_user_management_access():
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
    if not has_user_management_access():
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
    if not has_user_management_access():
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

# ── All available processes (from DB) ─────────────────────────────────────────
ALL_PAGES = [
    {"page_name": "page3_traceability",  "label": "Traceability"},
    {"page_name": "page5_ppc",           "label": "Data View PPC"},
    {"page_name": "page4",               "label": "Analytics"},
    {"page_name": "page5",               "label": "Data View"},
    {"page_name": "dispatch_tracker",    "label": "Dispatch Tracker"},
    {"page_name": "bom_summary",         "label": "BOM Summary"},
]

ALL_FIELDS = [
    {"page_name": "page5_ppc",          "field_name": "actual_qty",         "label": "Actual Qty"},
    {"page_name": "page5_ppc",          "field_name": "remarks",            "label": "Remarks"},
    {"page_name": "page5_ppc",          "field_name": "vendor_name",        "label": "Vendor Name"},
    {"page_name": "page5_ppc",          "field_name": "subcontractor_name", "label": "Subcontractor"},
    {"page_name": "page5_ppc",          "field_name": "so_no",              "label": "SO No"},
    {"page_name": "page5_ppc",          "field_name": "customer_name",      "label": "Customer Name"},
    {"page_name": "page5_ppc",          "field_name": "job_card_no",        "label": "Job Card No"},
    {"page_name": "page5_ppc",          "field_name": "item_name",          "label": "Item Name"},
    {"page_name": "page5_ppc",          "field_name": "material",           "label": "Material"},
    {"page_name": "page5_ppc",          "field_name": "so_qty",             "label": "SO Qty"},
    {"page_name": "page5_ppc",          "field_name": "is_priority",        "label": "Is Priority"},
    {"page_name": "page3_traceability", "field_name": "actual_qty",         "label": "Actual Qty"},
    {"page_name": "page3_traceability", "field_name": "remarks",            "label": "Remarks"},
    {"page_name": "page3_traceability", "field_name": "vendor_name",        "label": "Vendor Name"},
]


# ── GET /api/permissions/meta — all available processes, pages, fields ─────────
@users_bp.route("/api/permissions/meta", methods=["GET"])
def get_permissions_meta():
    if not has_user_management_access():
        return jsonify({"success": False, "error": "Admin access required"}), 403
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DISTINCT process_name FROM processes ORDER BY process_name")
        all_processes = [r["process_name"] for r in cursor.fetchall()]

        # Add Dispatch as special process
        if "Dispatch" not in all_processes:
            all_processes.append("Dispatch")

        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "processes": all_processes,
            "pages": ALL_PAGES,
            "fields": ALL_FIELDS,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@users_bp.route("/api/users/<int:user_id>/permissions", methods=["GET", "POST"])
def user_permissions(user_id):
    if not has_user_management_access():
        return jsonify({"success": False, "error": "Admin access required"}), 403

    if request.method == "GET":
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT process_name FROM supervisor_process_access
                WHERE user_id = %s
            """, (user_id,))
            process_access = [r["process_name"] for r in cursor.fetchall()]

            cursor.execute("""
                SELECT page_name FROM user_page_permissions
                WHERE user_id = %s AND can_access = 1
            """, (user_id,))
            page_access = [r["page_name"] for r in cursor.fetchall()]

            cursor.execute("""
                SELECT page_name, field_name FROM user_field_permissions
                WHERE user_id = %s AND can_edit = 1
            """, (user_id,))
            field_access = [{"page_name": r["page_name"], "field_name": r["field_name"]}
                            for r in cursor.fetchall()]

            cursor.close()
            conn.close()
            return jsonify({
                "success": True,
                "process_access": process_access,
                "page_access": page_access,
                "field_access": field_access,
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    # POST
    if session.get("user_id") == user_id:
        return jsonify({"success": False, "error": "Cannot edit your own permissions"}), 400

    data = request.json or {}
    process_access = data.get("process_access", [])
    page_access    = data.get("page_access", [])
    field_access   = data.get("field_access", [])

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("DELETE FROM supervisor_process_access WHERE user_id = %s", (user_id,))
        for proc in process_access:
            if proc:
                cursor.execute("""
                    INSERT IGNORE INTO supervisor_process_access (user_id, process_name)
                    VALUES (%s, %s)
                """, (user_id, proc))

        cursor.execute("DELETE FROM user_page_permissions WHERE user_id = %s", (user_id,))
        for page in page_access:
            if page:
                cursor.execute("""
                    INSERT IGNORE INTO user_page_permissions (user_id, page_name, can_access)
                    VALUES (%s, %s, 1)
                """, (user_id, page))

        cursor.execute("DELETE FROM user_field_permissions WHERE user_id = %s", (user_id,))
        for f in field_access:
            page_name  = f.get("page_name", "")
            field_name = f.get("field_name", "")
            if page_name and field_name:
                cursor.execute("""
                    INSERT IGNORE INTO user_field_permissions
                        (user_id, page_name, field_name, can_view, can_edit)
                    VALUES (%s, %s, %s, 1, 1)
                """, (user_id, page_name, field_name))

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Permissions saved successfully."})
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
