"""
Job card API routes for Demo 2.
Job card numbers have NO prefix â€” stored as plain numbers/slash format.
"""

import traceback
import logging
from datetime import date, datetime, timedelta

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt

from flask import Blueprint, jsonify, request
from mysql.connector import Error
from db import get_connection

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

job_cards_bp = Blueprint("job_cards", __name__)

PROCESS_COUNT = 25
PROCESS_COLUMNS = [f"p{i}" for i in range(1, PROCESS_COUNT + 1)]
PROCESS_COLUMNS_SQL = ",".join(PROCESS_COLUMNS)


def safe_int(val, default=0):
    """Safely convert a value to int, tolerating float-formatted strings
    like '2.0' (common when numbers come through pandas/Excel)."""
    try:
        if val in (None, ""):
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default


def remaining_days_from_delivery(delivery_date):
    if not delivery_date:
        return 0
    try:
        if isinstance(delivery_date, str):
            delivery_dt = datetime.strptime(delivery_date[:10], "%Y-%m-%d").date()
        elif hasattr(delivery_date, "date") and not isinstance(delivery_date, date):
            delivery_dt = delivery_date.date()
        else:
            delivery_dt = delivery_date
        return (delivery_dt - date.today()).days
    except Exception:
        return 0


def column_exists(cursor, table, column):
    cursor.execute("""
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
    """, (table, column))
    row = cursor.fetchone()
    return (row[0] if isinstance(row, tuple) else row.get("COUNT(*)", 0)) > 0


def ensure_work_order_columns(cursor):
    if not column_exists(cursor, "job_cards", "work_order_no"):
        cursor.execute("""
            ALTER TABLE job_cards
            ADD COLUMN work_order_no VARCHAR(50) AFTER so_no
        """)
    if not column_exists(cursor, "job_cards", "work_order_date"):
        cursor.execute("""
            ALTER TABLE job_cards
            ADD COLUMN work_order_date DATE AFTER job_card_date
        """)
    if not column_exists(cursor, "job_cards", "customer_name"):
        cursor.execute("""
            ALTER TABLE job_cards
            ADD COLUMN customer_name VARCHAR(255) AFTER so_no
        """)
    if not column_exists(cursor, "job_cards", "parent_code"):
        cursor.execute("""
            ALTER TABLE job_cards
            ADD COLUMN parent_code VARCHAR(50) AFTER work_order_no
        """)
    if not column_exists(cursor, "job_cards", "child_code"):
        cursor.execute("""
            ALTER TABLE job_cards
            ADD COLUMN child_code VARCHAR(100) AFTER work_order_date
        """)


def ensure_advance_stock_column(cursor):
    if not column_exists(cursor, "job_card_items", "advance_stock"):
        cursor.execute("""
            ALTER TABLE job_card_items
            ADD COLUMN advance_stock VARCHAR(100) AFTER job_card_qty
        """)


@job_cards_bp.route("/api/items", methods=["GET"])
def get_items():
    try:
        import re
        search = request.args.get("q", "").strip()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        if not search:
            cursor.close()
            conn.close()
            return jsonify({"success": True, "items": []})

        # ── Fix encoding ───────────────────────────────────────────────────────
        search = search.replace("Ã˜", "Ø").replace("Ã?", "Ø")

        # ── Strip component prefixes ───────────────────────────────────────────
        PREFIXES = [
            "front nut of ", "rear nut of ", "outer ring of ",
            "inner ring of ", "inner race of ", "outer race of ",
            "washer of ", "cage assembly of ", "cage of ",
            "e1 cover of ", "e8 cover of ", "e2 lever of ",
            "shaft of ", "flange of ", "nut of ", "ring of ",
            "assembly of ",
        ]
        SUFFIXES = [
            " - front nut", " - rear nut", " - outer ring",
            " - inner ring", " - washer", " - outer race",
            " - inner race", " - cage",
        ]

        stripped = search.lower().strip()
        for prefix in PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):]
                break
        for suffix in SUFFIXES:
            if stripped.endswith(suffix):
                stripped = stripped[:-len(suffix)]
                break
        # Remove duplicate size like "- 60x90x66" at end
        stripped = re.sub(r'\s*-\s*\d[\dx]+\s*$', '', stripped).strip()

        cursor.execute("""
            SELECT id, model_name, size, part_name, material,
                """ + PROCESS_COLUMNS_SQL + """,
                num_operations
            FROM process_master
            WHERE model_name LIKE %s
               OR model_name LIKE %s
               OR size       LIKE %s
               OR part_name  LIKE %s
            ORDER BY
                CASE
                    WHEN LOWER(TRIM(model_name)) = LOWER(TRIM(%s)) THEN 1
                    WHEN model_name LIKE %s THEN 2
                    WHEN model_name LIKE %s THEN 3
                    ELSE 4
                END,
                model_name
            LIMIT 20
        """, (
            f"%{search}%",      # original search
            f"%{stripped}%",    # stripped search
            f"%{search}%",      # size match
            f"%{search}%",      # part_name match
            search,             # exact match → priority 1
            f"{search}%",       # starts with → priority 2
            f"%{stripped}%",    # stripped → priority 3
        ))

        items = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "items": items})

    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/customer-search", methods=["GET"])
def customer_search():
    """Return matching customer master values for Page 1."""
    conn = None
    cursor = None
    try:
        query = request.args.get("q", "").strip()
        if len(query) < 2:
            return jsonify([])

        like_query = f"%{query}%"
        starts_with_query = f"{query}%"
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT full_customer_text AS value
            FROM customer_master
            WHERE customer_code LIKE %s
               OR customer_name LIKE %s
               OR full_customer_text LIKE %s
            ORDER BY
                CASE
                    WHEN customer_code LIKE %s THEN 0
                    WHEN customer_name LIKE %s THEN 1
                    ELSE 2
                END,
                full_customer_text
            LIMIT 15
        """, (
            like_query,
            like_query,
            like_query,
            starts_with_query,
            starts_with_query,
        ))
        return jsonify(cursor.fetchall())
    except Error:
        logger.exception("Customer search failed")
        return jsonify({"error": "Unable to search customers"}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@job_cards_bp.route("/api/process_names", methods=["GET"])
def get_process_names():
    """Return all unique process names from process_master p1 to p25."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(f"""
            SELECT {PROCESS_COLUMNS_SQL}
            FROM process_master
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        names = set()
        for row in rows:
            for col in PROCESS_COLUMNS:
                val = row.get(col)
                if val and str(val).strip():
                    names.add(str(val).strip())

        return jsonify({
            "success": True,
            "process_names": sorted(names)
        })

    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/supervisors", methods=["GET"])
def get_supervisors():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM supervisors ORDER BY name")
        supervisors = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "supervisors": supervisors})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/job_card", methods=["POST"])
def save_job_card():
    """Save a new job card. job_card_no stored as-is (no prefix)."""
    conn = None
    cursor = None
    try:
        logger.debug("=== save_job_card() - Processing request ===")
        data = request.json
        logger.debug(f"Received data: {data}")

        job_card_no = str(data.get("job_card_no", "")).strip()
        so_no = data.get("so_no", "")
        work_order_no = data.get("work_order_no", "")
        parent_code = data.get("parent_code", "") or ""
        so_date = data.get("so_date") or None
        job_card_date = data.get("job_card_date") or None
        work_order_date = data.get("work_order_date") or None
        child_code = data.get("child_code", "") or ""
        final_status = data.get("final_status", "Pending")
        total_days = data.get("total_days", 0)
        items = data.get("items", [])
        delivery_date = data.get("delivery_date") or None
        remarks = data.get("remarks", "") or ""
        customer_name = data.get("customer_name", "") or ""

        logger.debug(
            f"Job Card No: {job_card_no}, SO No: {so_no}, Items: {items}")

        if not job_card_no or not items:
            logger.warning("Missing required fields: job_card_no or items")
            return jsonify({"success": False, "error": "Job Card No and item are required"}), 400
        if not delivery_date:
            logger.warning("Missing required field: delivery_date")
            return jsonify({"success": False, "error": "Final Delivery Date is required"}), 400
        remaining_days = remaining_days_from_delivery(delivery_date)

        conn = get_connection()
        cursor = conn.cursor()
        logger.debug("Database connection established")
        ensure_work_order_columns(cursor)
        ensure_advance_stock_column(cursor)

        if not column_exists(cursor, "job_card_items", "is_priority"):
            cursor.execute(
                "ALTER TABLE job_card_items ADD COLUMN is_priority TINYINT(1) DEFAULT 0")

        # Insert main job card
        logger.debug(f"Inserting job card: {job_card_no}")
        cursor.execute("""
            INSERT INTO job_cards
            (job_card_no, so_no, customer_name, work_order_no, parent_code, so_date, job_card_date, work_order_date, child_code, final_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (job_card_no, so_no, customer_name, work_order_no, parent_code, so_date, job_card_date, work_order_date, child_code, final_status))
        logger.debug("Job card inserted successfully")

        # Insert items
        for idx, item in enumerate(items):
            logger.debug(f"Inserting item {idx}: {item['item_name']}")
            cursor.execute("""
                INSERT INTO job_card_items
(job_card_no, item_name, material, so_qty, advance_stock, wip_status, total_days, remaining_days, delivery_date, remarks, is_priority)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""", (
                job_card_no,
                item["item_name"],
                item.get("material", "") or None,
                item.get("qty", 0),
                item.get("advance_stock", "") or None,
                # ← was hardcoded 'Pending'
                item.get("first_process") or "Pending",
                total_days,
                remaining_days,
                delivery_date,
                remarks,
                int(item.get("is_priority", 0))
            ))
            logger.debug(f"Item {idx} inserted successfully")

        # Save individual process days (supports new {days, lead_date} dict format)
        process_days = data.get("process_days", {})
        logger.debug(
            f"Processing {len(process_days)} process days: {process_days}")

        # Fetch process default days — used as single source of truth for lead days
        _pdd_cursor = conn.cursor(dictionary=True)
        _pdd_cursor.execute(
            "SELECT process_name, default_days FROM process_default_days")
        _pdd_map = {
            (row["process_name"] or "").strip().lower(): row["default_days"]
            for row in _pdd_cursor.fetchall()
        }
        _pdd_cursor.close()

        for process_name, pd_val in process_days.items():
            if not process_name:
                logger.debug("Skipping empty process_name")
                continue

            try:
                if isinstance(pd_val, dict):
                    submitted_days = int(pd_val.get("days") or 0)
                    lead_date = pd_val.get("lead_date") or None
                else:
                    submitted_days = int(pd_val) if pd_val else 0
                    lead_date = None

                # Use process_default_days as source of truth; fall back to submitted value
                norm_name = (process_name or "").strip().lower()
                pdd_days = _pdd_map.get(norm_name)
                days = int(
                    pdd_days) if pdd_days is not None else submitted_days

                logger.debug(
                    f"Inserting process: {process_name}, days: {days}, lead_date: {lead_date}")
                cursor.execute("""
                    INSERT INTO job_card_process_days
                    (job_card_no, process_name, days, lead_date, is_completed)
                    VALUES (%s, %s, %s, %s, 0)
                """, (job_card_no, process_name, days, lead_date))
                logger.debug(f"Process {process_name} inserted successfully")
            except Exception as pe:
                logger.error(
                    f"Error inserting process {process_name}: {str(pe)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise

        # Mark the first process stage as started (set in_time) so its pill
        # is immediately active/clickable on Page 3 for the new job card.
        first_proc = None
        for item in items:
            fp = (item.get("first_process") or "").strip()
            if fp:
                first_proc = fp
                break

        if first_proc and column_exists(cursor, "job_card_process_days", "in_time"):
            cursor.execute("""
                UPDATE job_card_process_days
                SET in_time = COALESCE(in_time, NOW())
                WHERE job_card_no = %s
                  AND LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
            """, (job_card_no, first_proc))

        logger.debug("About to commit transaction")
        conn.commit()
        logger.debug("Transaction committed successfully")

        cursor.close()
        conn.close()
        logger.info(f"Job Card {job_card_no} saved successfully")
        return jsonify({"success": True, "message": f"Job Card {job_card_no} saved!"})

    except Exception as e:
        conn.rollback() if conn else None
        if "Duplicate entry" in str(e) or "1062" in str(e):
            return jsonify({
                "success": False,
                "error": f"Job Card {job_card_no} already exists in the system. Please use a different Job Card number."
            }), 400
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/job_cards", methods=["GET"])
def get_job_cards():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_work_order_columns(cursor)
        cursor.execute("""
            SELECT jc.job_card_no, jc.so_no, jc.final_status,
                   jc.work_order_no, jc.work_order_date,
                   jc.erp_status, jc.created_at,
                   COUNT(ji.id) as item_count
            FROM job_cards jc
            LEFT JOIN job_card_items ji ON jc.job_card_no = ji.job_card_no
            GROUP BY jc.job_card_no
            ORDER BY jc.created_at DESC
        """)
        rows = cursor.fetchall()
        for r in rows:
            if r.get("work_order_date"):
                r["work_order_date"] = r["work_order_date"].strftime(
                    "%Y-%m-%d") if hasattr(r["work_order_date"], "strftime") else r["work_order_date"]
            if r.get("created_at"):
                r["created_at"] = _to_ist(r["created_at"]).strftime("%Y-%m-%d %H:%M")
        cursor.close()
        conn.close()
        return jsonify({"success": True, "job_cards": rows})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/process_default_days", methods=["GET"])
def get_process_default_days():
    """Return all process default days for Page 1 auto-fill."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT process_name, default_days
            FROM process_default_days
            ORDER BY id
        """)
        defaults = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "defaults": defaults})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/job_card/upload_preview", methods=["POST"])
def upload_preview_job_cards():
    """Read uploaded Planning Sheet Excel and return preview.
    Reads columns by header name (case-insensitive) instead of fixed
    positions, so the importer tolerates reordered/added columns.
    """
    try:
        import pandas as pd  # type: ignore
        import io as _io
        file = request.files.get("file")
        if not file:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        raw = file.read()
        df = pd.read_excel(_io.BytesIO(raw), sheet_name=0, header=0)
        if df.shape[0] < 1:
            return jsonify({"success": False, "error": "File has no data rows"}), 400

        # Expected column headers (case-insensitive match)
        REQUIRED_COLS = {
            "so_no": ["so no", "so_no", "so number"],
            "so_date": ["so date", "so_date"],
            "job_card": ["job card", "jc no", "job_card", "job_card_no"],
            "child_code": ["child code", "child_code"],
            "model": ["model", "item name", "item_name"],
            "size": ["size"],
            "qty": ["so qty", "qty", "quantity"],
            "stock": ["stock"],
            "plan_qty": ["plan qty.", "plan qty", "plan_qty"],
            "part": ["part"],
            "dia": ["dia.", "dia"],
            "length": ["length"],
            "wip": ["wip status", "status"],
            "total_days": ["total days", "total_days"],
            "delivery": ["delivery date", "customer delivery date", "delivery_date"],
            "material": ["material"],
        }

        def find_col(possible_names):
            for col in df.columns:
                if str(col).strip().lower() in possible_names:
                    return col
            return None

        col_map = {key: find_col(names)
                   for key, names in REQUIRED_COLS.items()}

        if not col_map["job_card"] or not col_map["model"]:
            return jsonify({
                "success": False,
                "error": "Could not find required columns (Job Card / Model) in the uploaded file."
            }), 400

        def clean(val):
            if val is None:
                return ""
            import math
            if isinstance(val, float) and math.isnan(val):
                return ""
            s = str(val).strip()
            return "" if s.lower() in ("none", "nan", "-", "") else s

        def clean_date(val):
            if val is None:
                return ""
            import math
            if isinstance(val, float) and math.isnan(val):
                return ""
            if hasattr(val, "strftime"):
                return val.strftime("%Y-%m-%d")
            s = clean(val)
            if not s:
                return ""
            # Try common string date formats (e.g. "11/06/2026 00:00")
            from datetime import datetime
            for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return ""  # unparseable date — drop rather than send bad data to MySQL

        # Get existing JC numbers
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT job_card_no FROM job_cards")
        existing = {r["job_card_no"].strip() for r in cursor.fetchall()}
        cursor.close()
        conn.close()

        preview = []
        for i in range(len(df)):
            row = df.iloc[i]
            jc_no = clean(row[col_map["job_card"]]
                          ) if col_map["job_card"] else ""
            if not jc_no:
                continue
            is_dup = jc_no in existing
            preview.append({
                "job_card_no":   jc_no,
                "so_no":         clean(row[col_map["so_no"]]) if col_map["so_no"] else "",
                "so_date":       clean_date(row[col_map["so_date"]]) if col_map["so_date"] else "",
                "child_code":    clean(row[col_map["child_code"]]) if col_map["child_code"] else "",
                "item_name":     clean(row[col_map["model"]]) if col_map["model"] else "",
                "size":          clean(row[col_map["size"]]) if col_map["size"] else "",
                "material":      clean(row[col_map["material"]]) if col_map["material"] else "",
                "so_qty":        clean(row[col_map["qty"]]) if col_map["qty"] else "",
                "stock":         clean(row[col_map["stock"]]) if col_map["stock"] else "",
                "plan_qty":      clean(row[col_map["plan_qty"]]) if col_map["plan_qty"] else "",
                "part":          clean(row[col_map["part"]]) if col_map["part"] else "",
                "dia":           clean(row[col_map["dia"]]) if col_map["dia"] else "",
                "length":        clean(row[col_map["length"]]) if col_map["length"] else "",
                "wip_status":    (clean(row[col_map["wip"]]) if col_map["wip"] else "") or "Pending",
                "total_days":    (clean(row[col_map["total_days"]]) if col_map["total_days"] else "") or "0",
                "delivery_date": clean_date(row[col_map["delivery"]]) if col_map["delivery"] else "",
                "is_duplicate":  is_dup,
            })

        new_count = sum(1 for r in preview if not r["is_duplicate"])
        dup_count = sum(1 for r in preview if r["is_duplicate"])

        return jsonify({
            "success": True, "preview": preview,
            "new_count": new_count, "dup_count": dup_count,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/job_card/upload_confirm", methods=["POST"])
def upload_confirm_job_cards():
    """Save previewed job cards to database."""
    try:
        rows = request.json.get("rows", [])
        if not rows:
            return jsonify({"success": False, "error": "No data to save"}), 400

        conn = get_connection()
        cursor = conn.cursor()
        ensure_work_order_columns(cursor)
        ensure_advance_stock_column(cursor)
        inserted = updated = errors = 0

        for r in rows:
            jc_no = r.get("job_card_no", "").strip()
            if not jc_no:
                continue

            delivery_date = r.get("delivery_date") or None
            if not delivery_date:
                delivery_date = (
                    date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
            remaining_days = remaining_days_from_delivery(delivery_date)

            so_date = r.get("so_date") or None
            child_code = r.get("child_code") or ""
            size = r.get("size") or ""
            part = r.get("part") or ""
            dia = r.get("dia") or ""
            length = r.get("length") or ""
            job_card_qty = safe_int(r.get("plan_qty"), default=None)

            try:
                if r.get("is_duplicate"):
                    cursor.execute("""
                        UPDATE job_cards SET so_no=%s, so_date=%s, child_code=%s, final_status='Pending'
                        WHERE job_card_no=%s
                    """, (r.get("so_no"), so_date, child_code, jc_no))
                    cursor.execute("""
                        UPDATE job_card_items
                        SET item_name=%s, material=%s, so_qty=%s, job_card_qty=%s,
                            wip_status=%s, total_days=%s, remaining_days=%s,
                            delivery_date=%s, advance_stock=%s,
                            size=%s, part=%s, dia=%s, length=%s
                        WHERE job_card_no=%s
                    """, (
                        r.get("item_name"), r.get("material"),
                        safe_int(r.get("so_qty")),
                        job_card_qty,
                        r.get("wip_status", "Pending"),
                        safe_int(r.get("total_days")),
                        remaining_days,
                        delivery_date,
                        r.get("advance_stock") or None,
                        size, part, dia, length,
                        jc_no
                    ))
                    updated += 1
                else:
                    cursor.execute("""
                        INSERT IGNORE INTO job_cards (job_card_no, so_no, so_date, child_code, final_status)
                        VALUES (%s,%s,%s,%s,'Pending')
                    """, (jc_no, r.get("so_no"), so_date, child_code))
                    cursor.execute("""
                        INSERT INTO job_card_items
                        (job_card_no,item_name,material,so_qty,job_card_qty,advance_stock,wip_status,
                         total_days,remaining_days,delivery_date,size,part,dia,length)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        jc_no, r.get("item_name"), r.get("material"),
                        safe_int(r.get("so_qty")),
                        job_card_qty,
                        r.get("advance_stock") or None,
                        r.get("wip_status", "Pending"),
                        safe_int(r.get("total_days")),
                        remaining_days,
                        delivery_date,
                        size, part, dia, length,
                    ))
                    inserted += 1
            except Exception as e:
                print(f"[upload_confirm] Error for JC {jc_no}: {e}")
                errors += 1

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "message": f"{inserted} new job cards added, {updated} updated, {errors} errors.",
            "inserted": inserted, "updated": updated, "errors": errors,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
