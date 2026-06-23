"""
Process Master CRUD routes for Demo 2.
"""

from flask import Blueprint, jsonify, request
from mysql.connector import Error
from db import get_connection

process_master_bp = Blueprint("process_master", __name__)

PROCESS_COUNT = 25
PROCESS_COLUMNS = [f"p{i}" for i in range(1, PROCESS_COUNT + 1)]
PROCESS_COLUMNS_SQL = ",".join(PROCESS_COLUMNS)
PROCESS_ASSIGNMENTS_SQL = ",".join(f"{col}=%s" for col in PROCESS_COLUMNS)
PROCESS_PLACEHOLDERS_SQL = ",".join(["%s"] * PROCESS_COUNT)


@process_master_bp.route("/api/process_master", methods=["GET"])
def get_process_master():
    try:
        search = request.args.get("search",    "").strip()
        page = int(request.args.get("page",     1))
        per_page = int(request.args.get("per_page", 50))
        offset = (page - 1) * per_page

        where = ["1=1"]
        params = []

        if search:
            search_columns = ["model_name", "material",
                              "size", "part_name", *PROCESS_COLUMNS]
            # Space-insensitive match: strip spaces from both the column
            # value and the search term before comparing, so "MODEL:N7515ZZ"
            # matches "Model: N7515ZZ" regardless of spacing differences.
            where.append(
                "(" + " OR ".join(
                    f"REPLACE({col}, ' ', '') LIKE %s" for col in search_columns
                ) + ")")
            s_nospace = f"%{search.replace(' ', '')}%"
            params += [s_nospace] * len(search_columns)

            # Also try stripping common component prefixes and search again
            import re
            STRIP_PREFIXES = [
                r"^front nut of ", r"^rear nut of ", r"^outer ring of ",
                r"^inner ring of ", r"^inner race of ", r"^outer race of ",
                r"^washer of ", r"^shaft of ", r"^flange of ", r"^nut of ",
                r"^ring of ", r"^cage assembly of ", r"^cage of ",
                r"^e8 cover of ", r"^e1 cover of ", r"^assembly of ",
            ]
            stripped = search.lower().strip()
            for prefix in STRIP_PREFIXES:
                stripped = re.sub(prefix, "", stripped).strip()
            # Also strip suffixes like " - Front Nut", " - Rear Nut" etc.
            STRIP_SUFFIXES = [
                r" - front nut$", r" - rear nut$", r" - outer ring$",
                r" - inner ring$", r" - washer$", r" - outer race$",
                r" - inner race$", r" - cage$",
            ]
            for suffix in STRIP_SUFFIXES:
                stripped = re.sub(suffix, "", stripped).strip()
                # Strip duplicate size like "- 60x90x66" at end
                stripped = re.sub(r'\s*-\s*\d+x\d+x?\d*\s*$',
                                  '', stripped).strip()
            if stripped != search.lower().strip():
                where[-1] = where[-1][:-1] + " OR " + " OR ".join(
                    f"{col} LIKE %s" for col in ["model_name", "size"]
                ) + ")"
                params += [f"%{stripped}%", f"%{stripped}%"]

        where_sql = " AND ".join(where)

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            f"SELECT COUNT(*) AS cnt FROM process_master WHERE {where_sql}",
            params
        )
        total = cursor.fetchone()["cnt"]

        cursor.execute(
            f"""SELECT * FROM process_master
                WHERE {where_sql}
                ORDER BY model_name
                LIMIT %s OFFSET %s""",
            params + [per_page, offset]
        )
        records = cursor.fetchall()
        for r in records:
            if r.get("created_at"):
                r["created_at"] = r["created_at"].strftime("%Y-%m-%d")

        cursor.close()
        conn.close()
        return jsonify({
            "success":    True,
            "records":    records,
            "total":      total,
            "page":       page,
            "per_page":   per_page,
        })
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@process_master_bp.route("/api/process_master", methods=["POST"])
def add_process_master():
    try:
        data = request.json
        procs = [data.get(col, None) or None for col in PROCESS_COLUMNS]
        num_ops = sum(1 for p in procs if p)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            INSERT INTO process_master
            (model_name, material, part_name, size, {PROCESS_COLUMNS_SQL}, num_operations)
            VALUES (%s,%s,%s,%s,{PROCESS_PLACEHOLDERS_SQL},%s)
        """, (data.get("model_name"), data.get("material"), data.get("part_name") or "", data.get("size") or "", *procs, num_ops))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Item added!"})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@process_master_bp.route("/api/process_master/<int:id>", methods=["PUT"])
def update_process_master(id):
    try:
        data = request.json
        procs = [data.get(col, None) or None for col in PROCESS_COLUMNS]
        num_ops = sum(1 for p in procs if p)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"""
            UPDATE process_master
            SET model_name=%s, material=%s, part_name=%s, size=%s,
                {PROCESS_ASSIGNMENTS_SQL},
                num_operations=%s
            WHERE id=%s
        """, (data.get("model_name"), data.get("material"), data.get("part_name") or "", data.get("size") or "", *procs, num_ops, id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Record updated!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@process_master_bp.route("/api/process_master/<int:id>", methods=["DELETE"])
def delete_process_master(id):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM process_master WHERE id=%s", (id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Item deleted!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@process_master_bp.route("/api/process_master/upload_preview", methods=["POST"])
def upload_preview_process_master():
    """
    Read uploaded Excel/CSV file and return preview data.
    Checks each row against existing records to flag duplicates.
    Supports p1-p25 and flexible column name matching.
    """
    try:
        import openpyxl  # type: ignore
        import io
        import csv

        file = request.files.get("file")
        if not file:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        filename = file.filename.lower()

        # ── Read file into rows ──────────────────────────────────────────────
        if filename.endswith(".csv"):
            content = file.read().decode("utf-8-sig")
            reader = csv.reader(io.StringIO(content))
            rows = [tuple(r) for r in reader]
        else:
            wb = openpyxl.load_workbook(
                io.BytesIO(file.read()), data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))

        if not rows:
            return jsonify({"success": False, "error": "File is empty"}), 400

        # ── Detect header row (first row containing model/item keyword) ──────
        header_idx = 0
        for i, row in enumerate(rows[:5]):
            joined = " ".join(str(c).lower() for c in row if c)
            if "model" in joined or "item" in joined:
                header_idx = i
                break

        headers = [str(c).strip().lower()
                   if c else "" for c in rows[header_idx]]
        data_rows = rows[header_idx + 1:]

        # ── Flexible column finder ────────────────────────────────────────────
        def find_col(keywords):
            for kw in keywords:
                for i, h in enumerate(headers):
                    if kw in h:
                        return i
            return None

        # model_name: match "model_name", "model name", "item name", "model"
        col_name = find_col(["model_name", "model name", "item name", "model"])
        # material
        col_mat = find_col(["material"])
        # size
        col_size = find_col(["size"])
        # part_name
        col_part = find_col(["part_name", "part name", "part"])

        if col_name is None:
            return jsonify({
                "success": False,
                "error": f"Cannot find Model/Item Name column. Headers found: {headers}"
            }), 400

        # ── Find p1–p12 columns ───────────────────────────────────────────────
        p_col_indices = []
        for n in range(1, PROCESS_COUNT + 1):
            idx = find_col([f"p{n}"])
            p_col_indices.append(idx)   # None if not found

        # ── Fetch existing model names from DB ────────────────────────────────
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, model_name FROM process_master")
        existing = {r["model_name"].strip().lower(): r["id"]
                    for r in cursor.fetchall()}
        cursor.close()
        conn.close()

        # ── Build preview rows ────────────────────────────────────────────────
        preview = []
        for row in data_rows:
            name = str(row[col_name]).strip(
            ) if col_name is not None and row[col_name] else ""
            if not name or name.lower() in ("none", "nan", ""):
                continue

            mat = str(row[col_mat]).strip() if col_mat is not None and col_mat < len(
                row) and row[col_mat] else ""
            size = str(row[col_size]).strip() if col_size is not None and col_size < len(
                row) and row[col_size] else ""
            part = str(row[col_part]).strip() if col_part is not None and col_part < len(
                row) and row[col_part] else ""

            # Extract p1–p12 values
            procs = []
            for idx in p_col_indices:
                if idx is not None and idx < len(row) and row[idx]:
                    v = str(row[idx]).strip()
                    procs.append(v if v.lower() not in (
                        "none", "nan", "") else "")
                else:
                    procs.append("")

            is_dup = name.strip().lower() in existing

            entry = {
                "model_name":     name,
                "material":       mat,
                "size":           size,
                "part_name":      part,
                "num_operations": sum(1 for p in procs if p),
                "is_duplicate":   is_dup,
                "existing_id":    existing.get(name.strip().lower()),
            }
            # Add p1–p12
            for i, v in enumerate(procs, 1):
                entry[f"p{i}"] = v

            preview.append(entry)

        new_count = sum(1 for r in preview if not r["is_duplicate"])
        dup_count = sum(1 for r in preview if r["is_duplicate"])

        return jsonify({
            "success":   True,
            "preview":   preview,
            "new_count": new_count,
            "dup_count": dup_count,
        })

    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@process_master_bp.route("/api/process_master/upload_confirm", methods=["POST"])
def upload_confirm_process_master():
    """Save preview data to database. Updates duplicates, inserts new."""
    try:
        rows = request.json.get("rows", [])
        if not rows:
            return jsonify({"success": False, "error": "No data to save"}), 400

        conn = get_connection()
        cursor = conn.cursor()
        inserted = updated = errors = 0

        for r in rows:
            procs = [r.get(col) or None for col in PROCESS_COLUMNS]
            num_ops = sum(1 for p in procs if p)
            try:
                if r.get("is_duplicate") and r.get("existing_id"):
                    cursor.execute(f"""
                        UPDATE process_master
                        SET material=%s,size=%s,{PROCESS_ASSIGNMENTS_SQL},num_operations=%s
                        WHERE id=%s
                    """, (r.get("material"), r.get("size") or "", *procs, num_ops, r["existing_id"]))
                    updated += 1
                else:
                    cursor.execute(f"""
                        INSERT INTO process_master
                        (model_name,material,part_name,size,{PROCESS_COLUMNS_SQL},num_operations)
                        VALUES (%s,%s,%s,%s,{PROCESS_PLACEHOLDERS_SQL},%s)
                    """, (r.get("model_name"), r.get("material"), r.get("part_name") or "", r.get("size") or "", *procs, num_ops))
                    inserted += 1
            except Exception:
                errors += 1

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "message": f"{inserted} new records added, {updated} updated, {errors} errors.",
            "inserted": inserted, "updated": updated, "errors": errors,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
