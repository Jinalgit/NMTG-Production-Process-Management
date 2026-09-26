"""
Demo 2 — Flask application entry point.
"""

import os
import time

from flask import Flask
from flask_cors import CORS

# Load .env for local development; production sets env vars through the server config.
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from routes.analytics import analytics_bp
from routes.audit_trail import audit_trail_bp
from routes.auth import auth_bp
from routes.bom import bom_bp
from routes.cutting_plan import cutting_plan_bp
from routes.raw_material_shortage import raw_material_shortage_bp
from routes.data_view import data_view_bp
from routes.job_cards import job_cards_bp
from routes.pages import pages_bp
from routes.oee_dashboard import oee_dashboard_bp
from routes.oee_machine_summary import oee_machine_summary_bp
from routes.process_master import process_master_bp
from routes.quality_check import quality_check_bp
from routes.oee import oee_bp
from routes.system_backup import system_backup_bp
from routes.users import users_bp

app = Flask(__name__)


# LOGIN_ACTIVITY_LAST_SEEN_V1
@app.before_request
def update_login_activity_last_seen():
    """
    Update the current successful login record at most
    once every 5 minutes while the user is using JMS.
    """

    from datetime import datetime, timedelta

    from flask import session

    from db import get_connection

    activity_id = session.get(
        "login_activity_id"
    )

    user_id = session.get(
        "user_id"
    )

    if not activity_id or not user_id:
        return None

    now = (
        datetime.utcnow()
        + timedelta(
            hours=5,
            minutes=30,
        )
    )

    last_touch_text = session.get(
        "_login_activity_last_touch"
    )

    if last_touch_text:
        try:
            last_touch = (
                datetime.fromisoformat(
                    last_touch_text
                )
            )

            if (
                now - last_touch
            ).total_seconds() < 300:
                return None

        except Exception:
            pass

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE user_login_activity
            SET last_seen_at = %s
            WHERE id = %s
              AND user_id = %s
              AND logout_at IS NULL
            """,
            (
                now,
                activity_id,
                user_id,
            ),
        )

        conn.commit()

        session[
            "_login_activity_last_touch"
        ] = now.isoformat()

    except Exception as exc:
        if conn:
            conn.rollback()

        print(
            "[Login Activity] "
            "Last-seen update failed:",
            exc,
        )

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

    return None


# PLANT_HEAD_GLOBAL_READ_ONLY_V1
@app.before_request
def enforce_plant_head_global_read_only():
    """
    Plant Head is a system-wide read-only role.

    Safe/read requests remain available.
    Any request capable of changing system data is blocked
    before it reaches the route handler.
    """
    from flask import jsonify, request, session

    role = (session.get("role") or "").strip().lower()

    if role != "plant_head":
        return None

    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return None

    return jsonify({
        "success": False,
        "error": "Plant Head access is read-only. Changes are not permitted."
    }), 403


app.secret_key = os.environ["FLASK_SECRET_KEY"]
CORS(app)

app.config["TEMPLATES_AUTO_RELOAD"]  = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

app.register_blueprint(pages_bp)
app.register_blueprint(oee_dashboard_bp)
app.register_blueprint(oee_machine_summary_bp)
app.register_blueprint(job_cards_bp)
app.register_blueprint(process_master_bp)
app.register_blueprint(quality_check_bp)
app.register_blueprint(oee_bp)
app.register_blueprint(cutting_plan_bp)
app.register_blueprint(raw_material_shortage_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(data_view_bp)
app.register_blueprint(audit_trail_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(users_bp)
app.register_blueprint(bom_bp)
app.register_blueprint(system_backup_bp)


@app.after_request
def add_no_cache_headers(response):
    if app.debug:
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, "
            "post-check=0, pre-check=0, max-age=0"
        )
        response.headers["Pragma"]  = "no-cache"
        response.headers["Expires"] = "-1"
    return response


@app.context_processor
def inject_version():
    from flask import session
    from db import get_connection

    oee_sidebar_access = False

    role = (
        session.get("role") or ""
    ).strip().lower()

    user_id = session.get("user_id")

    if role in ("admin", "operator"):
        oee_sidebar_access = True

    elif role == "supervisor" and user_id:
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
                    LOWER(TRIM(process_name))
                        LIKE 'cnc machining%%'
                    OR
                    LOWER(TRIM(process_name))
                        LIKE 'vmc machining%%'
                  )
                LIMIT 1
                """,
                (user_id,),
            )

            oee_sidebar_access = (
                cursor.fetchone() is not None
            )

        finally:
            if cursor:
                cursor.close()

            if conn:
                conn.close()

    return {
        "version": int(time.time()),
        "oee_sidebar_access": oee_sidebar_access,
    }


if __name__ == "__main__":
    app.run(
        debug=True,
        use_reloader=True,
        reloader_type="stat",
        extra_files=[
            "templates/page1.html",
            "templates/page2.html",
            "templates/page3.html",
            "templates/page4.html",
            "templates/page5.html",
            "templates/base.html",
            "static/css/base.css",
            "static/css/page1.css",
            "static/css/page2.css",
            "static/css/page3.css",
            "static/css/page5.css",
            "static/js/base.js",
            "static/js/page1.js",
            "static/js/page2.js",
            "static/js/page3.js",
            "static/js/page5.js",
            "static/js/upload.js",
        ],
        port=5000,
    )