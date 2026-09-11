import os
import subprocess
from datetime import datetime

from flask import Blueprint, Response, jsonify, request

system_backup_bp = Blueprint("system_backup", __name__)

@system_backup_bp.route("/api/system/hidden-db-backup", methods=["POST"])
def hidden_db_backup():
    backup_code = request.headers.get("X-Backup-Code", "").strip()
    expected_code = os.getenv("BACKUP_SECRET_CODE", "").strip()

    if not expected_code:
        return jsonify({"success": False, "error": "BACKUP_SECRET_CODE is not configured in .env"}), 500

    if backup_code != expected_code:
        return jsonify({"success": False, "error": "Invalid backup code"}), 403

    mysql_host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "127.0.0.1")
    mysql_port = os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", "3306")
    mysql_user = os.getenv("MYSQL_USER") or os.getenv("DB_USER", "root")
    mysql_password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", "")
    mysql_db = os.getenv("MYSQL_DB") or os.getenv("DB_NAME", "jms_demo2")

    mysqldump_path = r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"

    cmd = [
        mysqldump_path,
        "--host", mysql_host,
        "--port", str(mysql_port),
        "--user", mysql_user,
        "--single-transaction",
        "--routines",
        "--triggers",
        "--events",
        "--databases", mysql_db
    ]

    env = os.environ.copy()
    env["MYSQL_PWD"] = mysql_password

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )

    if result.returncode != 0:
        return jsonify({
            "success": False,
            "error": result.stderr.decode("utf-8", errors="replace")
        }), 500

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{mysql_db}_backup_{timestamp}.sql"

    return Response(
        result.stdout,
        mimetype="application/sql",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Backup-File": filename
        }
    )
