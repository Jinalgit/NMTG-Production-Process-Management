from flask import Blueprint, jsonify

from auth_utils import api_required
from db import get_connection

   # adjust import to match your project

bom_bp = Blueprint('bom', __name__)


@bom_bp.route('/api/bom/summary', methods=['GET'])
@api_required("page5", allowed_modes=("full", "read"))
def get_bom_summary():
    conn = get_connection()
    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                bl.parent_code,
                bl.child_code,
                bl.make_buy,
                i.item_description,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM item_processes ip
                    WHERE ip.item_code = bl.child_code
                ) THEN 'Yes' ELSE 'No' END AS has_processes
            FROM bom_links bl
            LEFT JOIN items i ON i.item_code = bl.child_code
            ORDER BY bl.parent_code, bl.child_code
        """)

        rows = cursor.fetchall()
        return jsonify({"success": True, "rows": rows}), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/bom/children/<parent_code>
#
# Returns all direct child codes that belong to the given parent code.
# Used by Page 1 to populate the child-code dropdown after user enters
# a parent code.
#
# Response (200):
#   { "children": ["NAVCH0000123", "NAVCH0000124", ...] }
#
# Response (404) – parent code not found in bom_links:
#   { "error": "No children found for parent code NAVDS0000001" }
# ─────────────────────────────────────────────────────────────────────────────
@bom_bp.route('/api/bom/children/<parent_code>', methods=['GET'])
def get_children(parent_code):
    conn = None
    cursor = None

    try:
        parent_code = (parent_code or "").strip()

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                bl.child_code,
                COALESCE(i.item_description, '') AS item_description,
                COALESCE(i.material, '') AS material,
                COALESCE(i.size, '') AS size,
                COALESCE(i.part_name, '') AS part_name,
                bl.quantity,
                bl.make_buy
            FROM bom_links bl
            LEFT JOIN items i 
                ON i.item_code = bl.child_code
            WHERE bl.parent_code = %s
              AND bl.make_buy = 'A'
            ORDER BY 
                COALESCE(bl.sr_no, 999999),
                bl.id,
                bl.child_code
        """, (parent_code,))

        rows = cursor.fetchall()

        if not rows:
            return jsonify({
                "error": f"No children found for parent code {parent_code}"
            }), 404

        children = []

        for row in rows:
            children.append({
                "child_code": row.get("child_code") or "",
                "item_code": row.get("child_code") or "",
                "item_description": row.get("item_description") or "",
                "material": row.get("material") or "",
                "size": row.get("size") or "",
                "part_name": row.get("part_name") or "",
                "quantity": float(row.get("quantity") or 0),
                "make_buy": row.get("make_buy") or "",
            })

        return jsonify({"children": children}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# GET /api/bom/item_details/<child_code>
#
# Returns item master fields + ordered process list for the given child code.
# Used by Page 1 to auto-fill fields and show the editable process list
# after user selects a child code from the dropdown.
#
# Response (200):
#   {
#     "item_code":        "NAVCH0000123",
#     "item_description": "Inner Race 50x125x32",
#     "material":         "52100",
#     "size":             "50x125x32",
#     "part_name":        "Inner Race",
#     "processes": [
#       { "step_no": 1, "process_name": "Drawing" },
#       { "step_no": 2, "process_name": "Raw Material" },
#       ...
#     ]
#   }
#
# Response (404) – child code not in items table:
#   { "error": "Item NAVCH0000123 not found" }
# ─────────────────────────────────────────────────────────────────────────────
@bom_bp.route('/api/bom/item_details/<child_code>', methods=['GET'])
def get_item_details(child_code):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)

        # ── 1. Fetch item master fields ───────────────────────────────────────
        cursor.execute("""
            SELECT
                item_code,
                item_description,
                material,
                size,
                part_name
            FROM items
            WHERE item_code = %s
        """, (child_code.strip(),))

        item = cursor.fetchone()

        if not item:
            return jsonify({
                "error": f"Item {child_code} not found"
            }), 404

        # ── 2. Fetch ordered process list via item_processes + processes ──────
        cursor.execute("""
            SELECT
                ip.step_no,
                p.process_name
            FROM item_processes ip
            JOIN processes p ON p.id = ip.process_id
            WHERE ip.item_code = %s
            ORDER BY ip.step_no ASC
        """, (child_code.strip(),))

        process_rows = cursor.fetchall()

        processes = [
            {
                "step_no":      row['step_no'],
                "process_name": row['process_name']
            }
            for row in process_rows
        ]

        return jsonify({
            "item_code":        item['item_code'],
            "item_description": item['item_description'] or "",
            "material":         item['material'] or "",
            "size":             item['size'] or "",
            "part_name":        item['part_name'] or "",
            "processes":        processes
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()
