from flask import Blueprint, redirect, render_template, request, session, url_for

from auth_utils import login_required, page_required
from db import get_connection

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/welcome")
@login_required
def welcome():
    is_zone_login = False
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        user_id = session.get("user_id")
        if user_id:
            cursor.execute(
                "SELECT 1 FROM oee_zone_logins"
                " WHERE user_id = %s AND is_active = 1 LIMIT 1",
                (user_id,),
            )
            is_zone_login = cursor.fetchone() is not None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    return render_template("welcome.html", is_zone_login=is_zone_login)


def get_process_master_process_names():
    process_columns = [f"p{i}" for i in range(1, 26)]
    union_sql = " UNION ALL ".join(
        f"SELECT {idx} AS process_order, {col} AS process_name FROM process_master "
        f"WHERE {col} IS NOT NULL AND TRIM({col}) != ''"
        for idx, col in enumerate(process_columns, start=1)
    )

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        f"SELECT process_name FROM ({union_sql}) p ORDER BY process_order, process_name")

    names = []
    seen = set()
    for row in cursor.fetchall():
        name = (row.get("process_name") or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)

    cnc_fifth = "CNC Machining 5th"
    cnc_fourth_key = "CNC Machining 4th".casefold()
    if cnc_fifth.casefold() not in seen:
        insert_at = next(
            (idx + 1 for idx, name in enumerate(names)
             if name.casefold() == cnc_fourth_key),
            len(names),
        )
        names.insert(insert_at, cnc_fifth)

    cursor.close()
    conn.close()
    return names


@pages_bp.route("/")
@page_required("page1")
def index():
    return render_template("page1.html", active_page="page1")


@pages_bp.route("/page2")
@page_required("page2")
def page2():
    return render_template(
        "page2.html",
        active_page="page2",
        process_names=get_process_master_process_names(),
    )


@pages_bp.route("/page2-vue")
@page_required("page2")
def page2_vue():
    return render_template(
        "page2_vue.html",
        active_page="page2",
    )

@pages_bp.route("/page3")
@page_required("page3")
def page3():
    return render_template("page3.html", active_page="page3")


@pages_bp.route("/oee")
@page_required("oee_page")
def oee_page():
    role = (session.get("role") or "").strip().lower()

    # Supervisors may open OEE only when they are assigned
    # to at least one CNC/VMC machining process.
    if role == "supervisor":
        conn = None
        cursor = None

        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT 1
                FROM supervisor_process_access
                WHERE user_id = %s
                  AND (
                    LOWER(TRIM(process_name)) LIKE 'cnc machining%%'
                    OR LOWER(TRIM(process_name)) LIKE 'vmc machining%%'
                  )
                LIMIT 1
                """,
                (session.get("user_id"),),
            )

            if cursor.fetchone() is None:
                return redirect(url_for("pages.page3"))

        finally:
            if cursor:
                cursor.close()

            if conn:
                conn.close()

    return render_template(
        "oee.html",
        active_page="oee_page",
    )


@pages_bp.route("/page4")
@page_required("page4")
def page4():
    return render_template("page4.html", active_page="page4")


@pages_bp.route("/page5")
def page5():
    from db import get_connection
    dispatch_access = False
    if session.get("role") == "supervisor" and session.get("username") != "admin":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM supervisor_process_access
            WHERE user_id = %s AND LOWER(TRIM(process_name)) = 'dispatch'
            LIMIT 1
        """, (session.get("user_id"),))
        dispatch_access = cursor.fetchone() is not None
        cursor.close()
        conn.close()
    return render_template("page5.html", dispatch_access=dispatch_access)

@pages_bp.route("/page5-vue")
def page5_vue():
    dispatch_access = False

    if (
        session.get("role") == "supervisor"
        and session.get("username") != "admin"
    ):
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT 1
            FROM supervisor_process_access
            WHERE user_id = %s
              AND LOWER(TRIM(process_name)) = 'dispatch'
            LIMIT 1
            """,
            (session.get("user_id"),),
        )

        dispatch_access = cursor.fetchone() is not None

        cursor.close()
        conn.close()

    return render_template(
        "page5_vue.html",
        active_page="page5",
        dispatch_access=dispatch_access,
    )



# ============================================================
# CUTTING PLAN PAGE - ADMIN + GAURANG ONLY
# ============================================================

@pages_bp.route("/cutting-plan")
@login_required
def cutting_plan():
    role = (session.get("role") or "").strip().lower()
    username = (session.get("username") or "").strip().lower()

    is_gaurang = (
        str(session.get("user_id")) == "5"
        or username == "gaurang"
    )

    if role != "admin" and not is_gaurang:
        return redirect(url_for("pages.page5"))

    return render_template(
        "cutting_plan.html",
        active_page="cutting_plan"
    )




# REMOVED: operator_dashboard route


# REMOVED: supervisor_dashboard route


# REMOVED: admin_dashboard route


@pages_bp.route("/smart-upload")
@page_required("smart_upload")
def smart_upload():
    return render_template(
        "smart_upload.html",
        active_page="smart_upload"
    )


@pages_bp.route("/user-management")
@page_required("user_management")
def user_management():
    return render_template(
        "user_management.html",
        active_page="user_management"
    )



# USER_MANAGEMENT_VUE_PILOT_V1
@pages_bp.route("/user-management-vue")
@page_required("user_management")
def user_management_vue():
    return render_template(
        "user_management_vue.html",
        active_page="user_management",
    )

@pages_bp.route("/dispatch-tracker")
@page_required("dispatch_tracker")
def dispatch_tracker():
    from flask import session

    from db import get_connection
    dispatch_access = False
    if session.get("role") == "supervisor":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM supervisor_process_access
            WHERE user_id = %s AND LOWER(TRIM(process_name)) = 'dispatch'
            LIMIT 1
        """, (session.get("user_id"),))
        dispatch_access = cursor.fetchone() is not None
        cursor.close()
        conn.close()
    elif session.get("role") == "admin":
        dispatch_access = True
    return render_template("dispatch_tracker.html", active_page="dispatch_tracker", dispatch_access=dispatch_access)
@pages_bp.route('/jc_review')
def jc_review():
    """Job Card Upload Review page."""
    if not session.get('username'):
        return redirect(url_for('auth.login'))
    token = request.args.get('token', '')
    return render_template('jc_review.html', active_page='page1', token=token)


# ============================================================
# ANALYTICS VUE PILOT
# ============================================================

@pages_bp.route("/page4-vue")
@page_required("page4")
def page4_vue():
    return render_template(
        "page4_vue.html",
        active_page="page4",
    )


# ============================================================
# TRACEABILITY VUE PILOT
# Read-only production journey UI.
# Original /page3 remains the operational fallback.
# ============================================================

@pages_bp.route("/page3-vue")
@page_required("page3")
def page3_vue():
    return render_template(
        "page3_vue.html",
        active_page="page3",
    )
