"""
Restore script — rolls back to the state before the oee_entries migration.

Finds the most recent backup pair in D:\\Het\\demo2\\backups\\:
    pre_oee_entries_migration_<timestamp>.sql
    pre_oee_entries_migration_<timestamp>_code.zip

Restores BOTH: database (drops current tables, recreates from dump)
              + code (extracts zip over D:\\Het\\demo2, overwriting files)

IMPORTANT: STOP Flask before running this. The app cannot hold files
           open while they are being overwritten.

Usage:
    cd D:\\Het\\demo2
    python restore_pre_migration.py
    python restore_pre_migration.py --yes       (skip confirmation prompt)
"""

import glob
import os
import re
import sys
import zipfile
from datetime import datetime


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR  = os.path.join(PROJECT_DIR, "backups")

PREFIX = "pre_oee_entries_migration_"


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


def find_latest_pair():
    sqls = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{PREFIX}*.sql")))
    if not sqls:
        return None, None, None

    # Extract stamps from each .sql file
    stamps = []
    for p in sqls:
        m = re.match(rf"{re.escape(PREFIX)}(\d{{8}}_\d{{6}})\.sql$", os.path.basename(p))
        if m:
            stamps.append((m.group(1), p))

    if not stamps:
        return None, None, None

    stamps.sort()
    stamp, sql_path = stamps[-1]
    zip_path = os.path.join(BACKUP_DIR, f"{PREFIX}{stamp}_code.zip")
    if not os.path.exists(zip_path):
        return stamp, sql_path, None

    return stamp, sql_path, zip_path


def restore_database(sql_path):
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
    conn.autocommit = True
    cur = conn.cursor()

    with open(sql_path, encoding="utf-8") as f:
        sql = f.read()

    stmt_count = 0
    for result in cur.execute(sql, multi=True):
        # consume every result set so all statements actually run
        try:
            _ = result.fetchall()
        except Exception:
            pass
        stmt_count += 1

    cur.close()
    conn.close()
    return stmt_count


def restore_code(zip_path):
    n_files = 0
    n_bytes = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            zf.extract(info, PROJECT_DIR)
            n_files += 1
            n_bytes += info.file_size
    return n_files, n_bytes


def main():
    load_env()

    if "DB_PASSWORD" not in os.environ or "DB_NAME" not in os.environ:
        print("ERROR: DB_PASSWORD or DB_NAME not set. Check .env")
        sys.exit(1)

    stamp, sql_path, zip_path = find_latest_pair()

    if not stamp:
        print("ERROR: No backup found in", BACKUP_DIR)
        print(f"       Expected files named {PREFIX}*.sql and _code.zip")
        sys.exit(1)

    if not zip_path:
        print(f"WARNING: SQL backup found ({sql_path}) but no matching code zip.")
        print("         Only the database will be restored, code stays as-is.")

    stamp_dt = datetime.strptime(stamp, "%Y%m%d_%H%M%S")

    print("=" * 72)
    print("RESTORE PRE-MIGRATION BACKUP")
    print("=" * 72)
    print(f"Project:      {PROJECT_DIR}")
    print(f"Database:     {os.environ['DB_NAME']}")
    print(f"Backup stamp: {stamp}  ({stamp_dt.strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"  SQL:  {sql_path}")
    print(f"  Code: {zip_path or '(none, code will NOT be restored)'}")
    print()
    print("This will:")
    print("  1. DROP all current tables in the database and recreate them from backup")
    if zip_path:
        print("  2. OVERWRITE code files under D:\\Het\\demo2 with the backup snapshot")
    print()
    print("MAKE SURE FLASK IS STOPPED before continuing.")
    print()

    skip_confirm = "--yes" in sys.argv or "-y" in sys.argv
    if not skip_confirm:
        ans = input('Type "RESTORE" to proceed: ').strip()
        if ans != "RESTORE":
            print("Aborted.")
            sys.exit(0)

    # ---- DB ----
    print()
    print(f"[1/2] Restoring database from {os.path.basename(sql_path)}")
    n_stmts = restore_database(sql_path)
    print(f"      Done.  Executed {n_stmts} statements.")

    # ---- Code ----
    if zip_path:
        print()
        print(f"[2/2] Extracting code from {os.path.basename(zip_path)}")
        n_files, n_bytes = restore_code(zip_path)
        print(f"      Done.  {n_files:,} files restored ({n_bytes/1024/1024:.2f} MB).")

    print()
    print("=" * 72)
    print("RESTORE COMPLETE")
    print("=" * 72)
    print()
    print("You are now back to the pre-migration state.")
    print("Start Flask again to resume.")
    print()


if __name__ == "__main__":
    main()
