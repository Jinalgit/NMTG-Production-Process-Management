"""
Backup script — run BEFORE the oee_entries migration.

Creates two files inside D:\\Het\\demo2\\backups\\:
  1. pre_oee_entries_migration_<timestamp>.sql       — full DB dump
  2. pre_oee_entries_migration_<timestamp>_code.zip  — full code snapshot

Both are used by restore_pre_migration.py to roll back.

Usage:
    cd D:\\Het\\demo2
    python backup_pre_migration.py
"""

import os
import sys
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR  = os.path.join(PROJECT_DIR, "backups")

# Anything under these gets skipped from the code zip
EXCLUDE_DIRS = {
    ".venv", ".git", "__pycache__", "backups",
    ".ruff_cache", ".vscode", ".vscode-shared",
    "node_modules", ".idea",
}
EXCLUDE_EXTS = {".pyc", ".pyo", ".log"}


# ------------------------------------------------------------
# Load .env (same behaviour as app.py)
# ------------------------------------------------------------
def load_env():
    env_path = os.path.join(PROJECT_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


# ------------------------------------------------------------
# DB dump
# ------------------------------------------------------------
def _sql_value(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float, Decimal)):
        return str(v)
    if isinstance(v, bytes):
        return "0x" + v.hex() if v else "''"
    if isinstance(v, datetime):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    if isinstance(v, timedelta):
        total_sec = int(v.total_seconds())
        h, r = divmod(total_sec, 3600)
        m, s = divmod(r, 60)
        return f"'{h:02d}:{m:02d}:{s:02d}'"
    s = str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\0", "")
    return f"'{s}'"


def dump_database(sql_path):
    import mysql.connector

    conn = mysql.connector.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", 3306)),
        database=os.environ["DB_NAME"],
        user=os.environ.get("DB_USER", "root"),
        password=os.environ["DB_PASSWORD"],
        auth_plugin="mysql_native_password",
        connection_timeout=30,
    )
    cur = conn.cursor()

    cur.execute("SHOW TABLES")
    tables = [t[0] for t in cur.fetchall()]

    total_rows = 0
    with open(sql_path, "w", encoding="utf-8") as f:
        f.write("-- Pre-migration backup\n")
        f.write(f"-- Generated: {datetime.now().isoformat()}\n")
        f.write(f"-- Database:  {os.environ['DB_NAME']}\n")
        f.write(f"-- Tables:    {len(tables)}\n\n")

        f.write("SET FOREIGN_KEY_CHECKS = 0;\n")
        f.write("SET UNIQUE_CHECKS      = 0;\n")
        f.write("SET SQL_MODE           = 'NO_AUTO_VALUE_ON_ZERO';\n\n")

        for tbl in tables:
            print(f"  dumping table: {tbl:40s}", end="", flush=True)

            # DROP + CREATE
            cur.execute(f"SHOW CREATE TABLE `{tbl}`")
            create_stmt = cur.fetchone()[1]
            f.write(f"-- ---------------------------------\n")
            f.write(f"-- Table structure for `{tbl}`\n")
            f.write(f"-- ---------------------------------\n")
            f.write(f"DROP TABLE IF EXISTS `{tbl}`;\n")
            f.write(f"{create_stmt};\n\n")

            # Data
            cur.execute(f"SELECT * FROM `{tbl}`")
            rows = cur.fetchall()

            if rows:
                cols = [d[0] for d in cur.description]
                col_list = ",".join(f"`{c}`" for c in cols)

                f.write(f"-- Data for `{tbl}` ({len(rows)} rows)\n")
                # write in batches of 200
                BATCH = 200
                for i in range(0, len(rows), BATCH):
                    chunk = rows[i:i + BATCH]
                    values_parts = [
                        "(" + ",".join(_sql_value(v) for v in row) + ")"
                        for row in chunk
                    ]
                    f.write(
                        f"INSERT INTO `{tbl}` ({col_list}) VALUES\n"
                        + ",\n".join(values_parts)
                        + ";\n"
                    )
                f.write("\n")

            print(f" -> {len(rows):>7d} rows")
            total_rows += len(rows)

        f.write("SET FOREIGN_KEY_CHECKS = 1;\n")
        f.write("SET UNIQUE_CHECKS      = 1;\n")

    cur.close()
    conn.close()
    return len(tables), total_rows


# ------------------------------------------------------------
# Code ZIP
# ------------------------------------------------------------
def zip_code(zip_path):
    total_files = 0
    total_bytes = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(PROJECT_DIR):
            # prune excluded dirs in-place so os.walk skips them
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext in EXCLUDE_EXTS:
                    continue

                full = os.path.join(root, fn)
                # skip the zip file itself and the SQL dump if already being written
                if os.path.abspath(full) == os.path.abspath(zip_path):
                    continue

                rel = os.path.relpath(full, PROJECT_DIR)
                try:
                    zf.write(full, rel)
                    total_files += 1
                    total_bytes += os.path.getsize(full)
                except (OSError, PermissionError) as e:
                    print(f"  SKIP (locked): {rel}  ({e})")

    return total_files, total_bytes


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------
def main():
    load_env()

    if "DB_PASSWORD" not in os.environ or "DB_NAME" not in os.environ:
        print("ERROR: DB_PASSWORD or DB_NAME not set. Check .env")
        sys.exit(1)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base  = f"pre_oee_entries_migration_{stamp}"
    sql_path = os.path.join(BACKUP_DIR, f"{base}.sql")
    zip_path = os.path.join(BACKUP_DIR, f"{base}_code.zip")

    print("=" * 72)
    print("PRE-MIGRATION BACKUP")
    print("=" * 72)
    print(f"Project:  {PROJECT_DIR}")
    print(f"Database: {os.environ['DB_NAME']}")
    print(f"Stamp:    {stamp}")
    print()

    # ---- DB ----
    print(f"[1/2] Dumping database -> {sql_path}")
    n_tables, n_rows = dump_database(sql_path)
    size_mb = os.path.getsize(sql_path) / (1024 * 1024)
    print(f"      Done.  {n_tables} tables, {n_rows:,} rows, {size_mb:.2f} MB")
    print()

    # ---- Code ----
    print(f"[2/2] Zipping code    -> {zip_path}")
    n_files, n_bytes = zip_code(zip_path)
    size_mb_zip = os.path.getsize(zip_path) / (1024 * 1024)
    src_mb      = n_bytes / (1024 * 1024)
    print(f"      Done.  {n_files:,} files, {src_mb:.2f} MB source -> {size_mb_zip:.2f} MB zipped")
    print()

    print("=" * 72)
    print("BACKUP COMPLETE")
    print("=" * 72)
    print(f"  DB:   {sql_path}")
    print(f"  Code: {zip_path}")
    print()
    print("To roll back at any time, stop Flask and run:")
    print(f"      python restore_pre_migration.py")
    print()


if __name__ == "__main__":
    main()
