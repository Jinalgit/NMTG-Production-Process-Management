"""
Smart Upload Wizard - Step 2
Detects file header, generates signature, checks for saved mapping template.
"""

from flask import Blueprint, jsonify, request
from db import get_connection
import hashlib
import json

smart_upload_bp = Blueprint("smart_upload", __name__)

MANDATORY_FIELDS = ["jc_no", "item_name", "qty"]
ALL_FIELDS = ["jc_no", "item_name", "qty", "so_no", "delivery_date", "status"]


def make_signature(headers):
    """Generate a stable fingerprint from a list of header strings."""
    cleaned = [str(h or "").strip().lower() for h in headers]
    joined = "|".join(cleaned)
    return hashlib.md5(joined.encode("utf-8")).hexdigest()


def read_file_rows(file_storage):
    """Read uploaded file (csv/xlsx) and return list of rows (list of lists)."""
    filename = file_storage.filename.lower()
    if filename.endswith(".csv"):
        import io
        import csv
        content = file_storage.read().decode("utf-8-sig", errors="ignore")
        reader = csv.reader(io.StringIO(content))
        return [list(r) for r in reader]
    else:
        import openpyxl
        import io
        wb = openpyxl.load_workbook(io.BytesIO(
            file_storage.read()), data_only=True)
        ws = wb.active
        return [list(r) for r in ws.iter_rows(values_only=True)]


def detect_header_row(rows, max_scan=10):
    """
    Find the row most likely to be the real header.
    Heuristic: the row with the highest count of short, distinct,
    non-numeric string cells within the first max_scan rows.
    """
    best_idx = 0
    best_score = -1
    for i, row in enumerate(rows[:max_scan]):
        score = 0
        for cell in row:
            s = str(cell or "").strip()
            if s and not s.replace(".", "", 1).isdigit() and len(s) < 40:
                score += 1
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx


@smart_upload_bp.route("/api/smart_upload/detect", methods=["POST"])
def detect_format():
    """
    Step 1: read uploaded file, find header row, generate signature,
    check if we already know this format.
    """
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        rows = read_file_rows(file)
        if not rows:
            return jsonify({"success": False, "error": "File is empty"}), 400

        header_idx = detect_header_row(rows)
        headers = [str(c).strip() if c else "" for c in rows[header_idx]]
        signature = make_signature(headers)

        # preview: header row + next 3 data rows
        preview_rows = rows[header_idx: header_idx + 4]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, template_name, column_mapping
            FROM upload_mapping_templates
            WHERE header_signature = %s
            ORDER BY id DESC LIMIT 1
        """, (signature,))
        existing = cursor.fetchone()
        cursor.close()
        conn.close()

        known_mapping = None
        if existing:
            known_mapping = existing["column_mapping"]
            if isinstance(known_mapping, str):
                known_mapping = json.loads(known_mapping)

        return jsonify({
            "success": True,
            "signature": signature,
            "header_row_index": header_idx,
            "headers": headers,
            "preview_rows": preview_rows,
            "total_rows": len(rows) - header_idx - 1,
            "known_format": existing is not None,
            "known_mapping": known_mapping,
            "mandatory_fields": MANDATORY_FIELDS,
            "all_fields": ALL_FIELDS,
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@smart_upload_bp.route("/api/smart_upload/save_mapping", methods=["POST"])
def save_mapping():
    """
    Save a column mapping as a template tied to this file's header signature.
    Body: { signature, template_name, mapping: {jc_no: "JobCard No", ...} }
    """
    try:
        data = request.json
        signature = data.get("signature")
        template_name = data.get("template_name", "Unnamed Format")
        mapping = data.get("mapping", {})

        if not signature or not mapping:
            return jsonify({"success": False, "error": "Signature and mapping required"}), 400

        missing = [f for f in MANDATORY_FIELDS if not mapping.get(f)]
        if missing:
            return jsonify({"success": False, "error": f"Missing mandatory mapping for: {', '.join(missing)}"}), 400

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_mapping_templates
            (template_name, header_signature, column_mapping)
            VALUES (%s, %s, %s)
        """, (template_name, signature, json.dumps(mapping)))
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({"success": True, "template_id": new_id, "message": "Mapping saved"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@smart_upload_bp.route("/api/smart_upload/parse", methods=["POST"])
def parse_with_mapping():
    """
    Step 3: Re-read the file using the confirmed column mapping,
    return clean preview rows + flag rows missing mandatory data.
    Body (multipart): file, header_row_index, mapping (JSON string)
    """
    try:
        file = request.files.get("file")
        header_row_index = int(request.form.get("header_row_index", 0))
        mapping = json.loads(request.form.get("mapping", "{}"))

        if not file:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        rows = read_file_rows(file)
        headers = [str(c).strip() if c else "" for c in rows[header_row_index]]
        data_rows = rows[header_row_index + 1:]

        # Map field -> column index
        field_to_idx = {}
        for field, col_name in mapping.items():
            if col_name and col_name in headers:
                field_to_idx[field] = headers.index(col_name)

        clean_rows = []
        skipped = 0
        skip_reasons = []

        for row in data_rows:
            entry = {}
            for field in ALL_FIELDS:
                idx = field_to_idx.get(field)
                val = row[idx] if (idx is not None and idx <
                                   len(row)) else None
                entry[field] = str(val).strip() if val is not None else ""

            # Skip fully blank rows
            if not any(entry.values()):
                continue

            missing_mandatory = [
                f for f in MANDATORY_FIELDS if not entry.get(f)]
            if missing_mandatory:
                skipped += 1
                skip_reasons.append(f"Missing {', '.join(missing_mandatory)}")
                continue

            clean_rows.append(entry)

        return jsonify({
            "success": True,
            "clean_rows": clean_rows,
            "ready_count": len(clean_rows),
            "skipped_count": skipped,
            "skip_reasons": skip_reasons[:10],
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500
