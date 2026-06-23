from flask import Blueprint, render_template
from auth_utils import page_required
from db import get_connection

pages_bp = Blueprint("pages", __name__)


def get_process_master_process_names():
    process_columns = [f"p{i}" for i in range(1, 26)]
    union_sql = " UNION ALL ".join(
        f"SELECT {idx} AS process_order, {col} AS process_name FROM process_master "
        f"WHERE {col} IS NOT NULL AND TRIM({col}) != ''"
        for idx, col in enumerate(process_columns, start=1)
    )

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT process_name FROM ({union_sql}) p ORDER BY process_order, process_name")

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
            (idx + 1 for idx, name in enumerate(names) if name.casefold() == cnc_fourth_key),
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


@pages_bp.route("/page3")
@page_required("page3")
def page3():
    return render_template("page3.html", active_page="page3")


@pages_bp.route("/page4")
@page_required("page4")
def page4():
    return render_template("page4.html", active_page="page4")


@pages_bp.route("/page5")
@page_required("page5")
def page5():
    return render_template("page5.html", active_page="page5")


@pages_bp.route("/operator-dashboard")
@page_required("operator_dashboard")
def operator_dashboard():
    return render_template(
        "operator_dashboard.html",
        active_page="operator_dashboard"
    )
@pages_bp.route("/supervisor-dashboard")
@page_required("supervisor_dashboard")
def supervisor_dashboard():
    return render_template(
        "supervisor_dashboard.html",
        active_page="supervisor_dashboard"
    )


@pages_bp.route("/admin-dashboard")
@page_required("admin_dashboard")
def admin_dashboard():
    return render_template(
        "admin_dashboard.html",
        active_page="admin_dashboard"
    )
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