"""
BOM Tree & Process Master routes.
Replaces the old flat process_master CRUD with a normalized
tree-based system (items, bom_links, item_processes, processes).
"""

import json

from flask import Blueprint, jsonify, request, session
from mysql.connector import Error

from db import get_connection


def _clean_cutting_size(value):
    """
    Convert imported cutting size text like:
    'CUTTING SIZE - 23mm / nan' -> '23 mm'
    '23mm' -> '23 mm'
    'nan' / blank -> None
    """
    import re

    if value is None:
        return None

    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "null", "-"):
        return None

    # Remove / nan part
    s = re.sub(r"/\s*nan\s*$", "", s, flags=re.IGNORECASE).strip()

    # Extract number before mm
    m = re.search(r"(\d+(?:\.\d+)?)\s*mm", s, flags=re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"{num} mm"

    # Extract number after CUTTING SIZE -
    m = re.search(r"CUTTING\s*SIZE\s*-\s*(\d+(?:\.\d+)?)", s, flags=re.IGNORECASE)
    if m:
        num = m.group(1)
        return f"{num} mm"

    return s


process_master_bp = Blueprint("process_master", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────

def _item_row_to_dict(row):
    """Convert a dict-cursor item row, appending its process routing."""
    if row.get("created_at"):
        row["created_at"] = row["created_at"].strftime("%Y-%m-%d")
    if row.get("updated_at"):
        row["updated_at"] = row["updated_at"].strftime("%Y-%m-%d")
    return row


def _get_processes_for_items(cursor, item_codes):
    """Return {item_code: [{step_no, process_name}, ...]} for a list of codes."""
    if not item_codes:
        return {}
    placeholders = ",".join(["%s"] * len(item_codes))
    cursor.execute(f"""
        SELECT ip.item_code, ip.step_no, p.process_name
        FROM item_processes ip
        JOIN processes p ON p.id = ip.process_id
        WHERE ip.item_code IN ({placeholders})
        ORDER BY ip.item_code, ip.step_no
    """, tuple(item_codes))
    result = {}
    for r in cursor.fetchall():
        code = r["item_code"]
        if code not in result:
            result[code] = []
        result[code].append({
            "step_no": r["step_no"],
            "process_name": r["process_name"],
        })
    return result


def _get_child_counts(cursor, item_codes):
    """Return {item_code: child_count} for a list of parent codes."""
    if not item_codes:
        return {}
    placeholders = ",".join(["%s"] * len(item_codes))
    cursor.execute(f"""
        SELECT parent_code, COUNT(*) AS cnt
        FROM bom_links
        WHERE parent_code IN ({placeholders})
        GROUP BY parent_code
    """, tuple(item_codes))
    return {r["parent_code"]: r["cnt"] for r in cursor.fetchall()}


def _enrich_items(cursor, items):
    """Add processes and child_count to a list of item dicts."""
    codes = [i["item_code"] for i in items]
    proc_map = _get_processes_for_items(cursor, codes)
    child_map = _get_child_counts(cursor, codes)
    for item in items:
        code = item["item_code"]
        item["processes"] = proc_map.get(code, [])
        item["child_count"] = child_map.get(code, 0)
    return items


def _json_default(value):
    """Make date/time and decimal values safe for JSON change logs."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _ensure_change_log_table(cursor):
    """Create the process master audit table without touching existing data."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_master_change_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            item_code VARCHAR(30) NOT NULL,
            action_type VARCHAR(50) NOT NULL,
            old_data JSON NULL,
            new_data JSON NULL,
            change_remark TEXT NOT NULL,
            changed_by VARCHAR(100) NULL,
            changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_pmcl_item_changed (item_code, changed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)


def _get_item_snapshot(cursor, item_code):
    """Return item fields with ordered process routing for audit logging."""
    cursor.execute("SELECT * FROM items WHERE item_code = %s", (item_code,))
    item = cursor.fetchone()
    if not item:
        return None
    _item_row_to_dict(item)
    _enrich_items(cursor, [item])
    return item


def _parse_json_column(value):
    if value is None or isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


# ── ROOTS (top-level assemblies) ──────────────────────────────────────────

@process_master_bp.route("/api/bom/roots", methods=["GET"])
def get_roots():
    """Return top-level assemblies (items that are parents but never children)."""
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 200))
        offset = (page - 1) * per_page

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT COUNT(DISTINCT bl.parent_code) AS cnt
            FROM bom_links bl
            WHERE bl.parent_code NOT IN (SELECT DISTINCT child_code FROM bom_links)
        """)
        total = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT i.*
            FROM items i
            WHERE i.item_code IN (
                SELECT DISTINCT bl.parent_code
                FROM bom_links bl
                WHERE bl.parent_code NOT IN (SELECT DISTINCT child_code FROM bom_links)
            )
            ORDER BY i.item_code
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        items = [_item_row_to_dict(r) for r in cursor.fetchall()]
        _enrich_items(cursor, items)

        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        })
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── CHILDREN (lazy-load on expand) ───────────────────────────────────────

@process_master_bp.route("/api/bom/tree/children/<item_code>", methods=["GET"])
def get_children(item_code):
    """Return direct children of a parent item."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT i.*, bl.sr_no, bl.make_buy, bl.quantity, bl.uom, bl.id AS link_id, bl.bom_no AS bom_no
            FROM bom_links bl
            JOIN items i ON i.item_code = bl.child_code
            WHERE bl.parent_code = %s
            ORDER BY bl.sr_no, i.item_code
        """, (item_code,))
        children = [_item_row_to_dict(r) for r in cursor.fetchall()]
        _enrich_items(cursor, children)

        cursor.close()
        conn.close()
        return jsonify({"success": True, "children": children})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── SEARCH ────────────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/search", methods=["GET"])
def search_items():
    """Search items by code, description, material, or process name."""
    try:
        q = request.args.get("q", "").strip()
        limit = int(request.args.get("limit", 100))
        if not q:
            return jsonify({"success": True, "items": [], "total": 0})

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        search_term = f"%{q}%"
        # Search across item fields + process names
        cursor.execute("""
            SELECT DISTINCT i.*
            FROM items i
            LEFT JOIN item_processes ip ON ip.item_code = i.item_code
            LEFT JOIN processes p ON p.id = ip.process_id
            WHERE i.item_code LIKE %s
               OR i.item_description LIKE %s
               OR i.material LIKE %s
               OR i.part_name LIKE %s
               OR p.process_name LIKE %s
            ORDER BY i.item_code
            LIMIT %s
        """, (search_term, search_term, search_term, search_term, search_term, limit))
        items = [_item_row_to_dict(r) for r in cursor.fetchall()]
        _enrich_items(cursor, items)

        # Also find which root assemblies contain these items
        if items:
            codes = [i["item_code"] for i in items]
            placeholders = ",".join(["%s"] * len(codes))
            cursor.execute(f"""
                WITH RECURSIVE ancestors AS (
                    SELECT child_code AS item, parent_code AS ancestor
                    FROM bom_links
                    WHERE child_code IN ({placeholders})
                    UNION
                    SELECT a.item, bl.parent_code
                    FROM ancestors a
                    JOIN bom_links bl ON bl.child_code = a.ancestor
                )
                SELECT DISTINCT a.ancestor
                FROM ancestors a
                WHERE a.ancestor NOT IN (SELECT DISTINCT child_code FROM bom_links)
                LIMIT 200
            """, tuple(codes))
            root_codes = [r["ancestor"] for r in cursor.fetchall()]
        else:
            root_codes = []

        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "items": items,
            "total": len(items),
            "root_codes": root_codes,
        })
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── ITEM DETAIL ───────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/item/<item_code>", methods=["GET"])
def get_item(item_code):
    """Return full detail for a single item including processes and parents."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM items WHERE item_code = %s", (item_code,))
        item = cursor.fetchone()
        if not item:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Item not found"}), 404

        _item_row_to_dict(item)
        _enrich_items(cursor, [item])

        # Get parent assemblies this item belongs to
        cursor.execute("""
            SELECT i.item_code, i.item_description, bl.sr_no, bl.make_buy, bl.quantity, bl.uom
            FROM bom_links bl
            JOIN items i ON i.item_code = bl.parent_code
            WHERE bl.child_code = %s
            ORDER BY i.item_code
        """, (item_code,))
        item["parents"] = cursor.fetchall()

        cursor.close()
        conn.close()
        return jsonify({"success": True, "item": item})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── ADD ITEM ──────────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/item", methods=["POST"])
def add_item():
    """Create a new item with optional process routing."""
    try:
        data = request.json
        item_code = (data.get("item_code") or "").strip()
        if not item_code:
            return jsonify({"success": False, "error": "Item code is required"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Check duplicate
        cursor.execute(
            "SELECT item_code FROM items WHERE item_code = %s", (item_code,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": f"Item '{item_code}' already exists"}), 400

        cursor.execute("""
            INSERT INTO items (item_code, item_description, item_type, make_default, material, size, part_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            item_code,
            data.get("item_description") or None,
            data.get("item_type", "PART"),
            data.get("make_default") or None,
            data.get("material") or None,
            data.get("size") or None,
            data.get("part_name") or None,
        ))

        # Add processes if provided
        processes = data.get("processes", [])
        if processes:
            _save_item_processes(cursor, item_code, processes)

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": f"Item '{item_code}' created!"})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── UPDATE ITEM ───────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/item/<item_code>", methods=["PUT"])
def update_item(item_code):
    """Update item details and process routing."""
    conn = None
    cursor = None
    try:
        data = request.json or {}
        change_remark = (data.get("change_remark") or "").strip()
        if not change_remark:
            return jsonify({"success": False, "error": "Remark / reason for change is required."}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        old_data = _get_item_snapshot(cursor, item_code)
        if not old_data:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Item not found"}), 404

        _ensure_change_log_table(cursor)

        cursor.execute("""
            UPDATE items
            SET item_description = %s,
                item_type = %s,
                make_default = %s,
                material = %s,
                size = %s,
                part_name = %s
            WHERE item_code = %s
        """, (
            data.get("item_description") or None,
            data.get("item_type", "PART"),
            data.get("make_default") or None,
            data.get("material") or None,
            data.get("size") or None,
            data.get("part_name") or None,
            item_code,
        ))

        # Replace processes if provided
        removed_from_existing_jcs = 0
        added_to_existing_jcs = 0
        synced_existing_jcs = 0

        if "processes" in data:

            # PROCESS_MASTER_JC_ROUTE_SYNC_V3_LOCAL

            # -----------------------------------------------
            # Read OLD Process Master route
            # -----------------------------------------------
            cursor.execute("""
                SELECT p.process_name
                FROM item_processes ip
                JOIN processes p
                  ON p.id = ip.process_id
                WHERE ip.item_code = %s
                ORDER BY ip.step_no, ip.id
            """, (item_code,))

            old_processes = [
                (r.get("process_name") or "").strip()
                for r in (cursor.fetchall() or [])
                if (r.get("process_name") or "").strip()
            ]

            old_route_keys = {
                p.casefold()
                for p in old_processes
            }

            # -----------------------------------------------
            # Read NEW submitted Process Master route
            # -----------------------------------------------
            processes = [
                (p or "").strip()
                for p in data.get("processes", [])
                if (p or "").strip()
            ]

            # Save Process Master normally
            _save_item_processes(
                cursor,
                item_code,
                processes
            )

            # -----------------------------------------------
            # Process Master route used for JC sync
            #
            # Assembly must NEVER return to Job Cards.
            # Drawing / RM are JC fixed stages.
            # QC / Store remain terminal JC stages.
            # -----------------------------------------------
            fixed_keys = {
                "drawing",
                "raw material",
            }

            tail_keys = {
                "quality check",
                "store",
            }

            skip_keys = (
                fixed_keys
                | tail_keys
                | {"assembly"}
            )

            pm_middle = []
            pm_seen = set()

            for pname in processes:

                key = pname.casefold()

                if key in skip_keys:
                    continue

                if key in pm_seen:
                    continue

                pm_middle.append(pname)
                pm_seen.add(key)

            new_route_keys = {
                p.casefold()
                for p in pm_middle
            }

            # -----------------------------------------------
            # Default process days
            # -----------------------------------------------
            cursor.execute("""
                SELECT
                    process_name,
                    default_days
                FROM process_default_days
                WHERE process_name IS NOT NULL
                  AND TRIM(process_name) <> ''
            """)

            default_days = {}

            for row in (cursor.fetchall() or []):

                key = (
                    row.get("process_name")
                    or ""
                ).strip().casefold()

                if key:
                    default_days[key] = int(
                        row.get("default_days")
                        or 0
                    )

            # -----------------------------------------------
            # Find existing Job Cards for this PM item
            #
            # Process Master item_code = job_cards.child_code
            # -----------------------------------------------
            cursor.execute("""
                SELECT
                    job_card_no,
                    COALESCE(final_status, '') AS final_status
                FROM job_cards
                WHERE TRIM(
                    COALESCE(child_code, '')
                ) = TRIM(%s)
                ORDER BY id
            """, (item_code,))

            jc_rows = cursor.fetchall() or []

            for jc in jc_rows:

                jc_no = (
                    jc.get("job_card_no")
                    or ""
                ).strip()

                if not jc_no:
                    continue

                # -------------------------------------------
                # Read current JC route
                # -------------------------------------------
                cursor.execute("""
                    SELECT
                        id,
                        process_name,
                        days,
                        COALESCE(
                            is_completed,
                            0
                        ) AS is_completed,
                        lead_date,
                        end_date,
                        in_time,
                        out_time,
                        actual_days,
                        COALESCE(
                            is_subcontract,
                            0
                        ) AS is_subcontract,
                        vendor_name,
                        subcontract_lead_days,
                        subcontract_start_date,
                        subcontract_expected_date
                    FROM job_card_process_days
                    WHERE job_card_no = %s
                    ORDER BY id
                """, (jc_no,))

                all_rows = cursor.fetchall() or []

                if not all_rows:
                    continue

                # -------------------------------------------
                # Completed/current rows stay untouched.
                #
                # Only future rows:
                # completed = 0 AND in_time IS NULL
                # are rebuilt.
                # -------------------------------------------
                protected_keys = set()
                future_rows = []

                for row in all_rows:

                    pname = (
                        row.get("process_name")
                        or ""
                    ).strip()

                    key = pname.casefold()

                    is_future = (
                        int(
                            row.get("is_completed")
                            or 0
                        ) == 0
                        and row.get("in_time") is None
                    )

                    if is_future:
                        future_rows.append(
                            dict(row)
                        )
                    elif key:
                        protected_keys.add(key)

                if not future_rows:
                    continue

                original_future_keys = [
                    (
                        row.get("process_name")
                        or ""
                    ).strip().casefold()
                    for row in future_rows
                    if (
                        row.get("process_name")
                        or ""
                    ).strip()
                ]

                # Map existing pending rows so their
                # days / lead dates etc. can be reused.
                future_map = {}

                for row in future_rows:

                    key = (
                        row.get("process_name")
                        or ""
                    ).strip().casefold()

                    if key and key not in future_map:
                        future_map[key] = row

                desired_rows = []
                desired_seen = set()

                def add_existing(row):

                    pname = (
                        row.get("process_name")
                        or ""
                    ).strip()

                    key = pname.casefold()

                    if not key:
                        return

                    if key == "assembly":
                        return

                    if key in desired_seen:
                        return

                    desired_rows.append(row)
                    desired_seen.add(key)

                def add_process(pname):

                    pname = (
                        pname
                        or ""
                    ).strip()

                    key = pname.casefold()

                    if not key:
                        return

                    if key == "assembly":
                        return

                    # Already completed/current.
                    if key in protected_keys:
                        return

                    if key in desired_seen:
                        return

                    old = future_map.get(key)

                    if old:
                        desired_rows.append(old)

                    else:
                        desired_rows.append({
                            "process_name":
                                pname,

                            "days":
                                default_days.get(
                                    key,
                                    0
                                ),

                            "is_completed":
                                0,

                            "lead_date":
                                None,

                            "end_date":
                                None,

                            "in_time":
                                None,

                            "out_time":
                                None,

                            "actual_days":
                                None,

                            "is_subcontract":
                                0,

                            "vendor_name":
                                None,

                            "subcontract_lead_days":
                                None,

                            "subcontract_start_date":
                                None,

                            "subcontract_expected_date":
                                None,
                        })

                    desired_seen.add(key)

                # -------------------------------------------
                # A. Keep pending Drawing / Raw Material
                # if they exist.
                # -------------------------------------------
                for key in (
                    "drawing",
                    "raw material",
                ):

                    row = future_map.get(key)

                    if row:
                        add_existing(row)

                # -------------------------------------------
                # B. Latest Process Master route
                # -------------------------------------------
                for pname in pm_middle:
                    add_process(pname)

                # -------------------------------------------
                # C. Preserve JC-specific extra pending
                # processes which were never part of the old
                # PM route.
                #
                # But do NOT preserve a process that was
                # removed from Process Master.
                # -------------------------------------------
                for row in future_rows:

                    pname = (
                        row.get("process_name")
                        or ""
                    ).strip()

                    key = pname.casefold()

                    if not key:
                        continue

                    if key in fixed_keys:
                        continue

                    if key in tail_keys:
                        continue

                    if key == "assembly":
                        continue

                    # Old PM process removed from new PM:
                    # do not retain it.
                    if (
                        key in old_route_keys
                        and key not in new_route_keys
                    ):
                        continue

                    if key in new_route_keys:
                        continue

                    add_existing(row)

                # -------------------------------------------
                # D. Quality Check + Store at the end
                # -------------------------------------------
                for key in (
                    "quality check",
                    "store",
                ):

                    row = future_map.get(key)

                    if row:
                        add_existing(row)

                desired_keys = [
                    (
                        row.get("process_name")
                        or ""
                    ).strip().casefold()
                    for row in desired_rows
                    if (
                        row.get("process_name")
                        or ""
                    ).strip()
                ]

                # Already correct
                if desired_keys == original_future_keys:
                    continue

                original_set = set(
                    original_future_keys
                )

                desired_set = set(
                    desired_keys
                )

                removed_here = len(
                    original_set - desired_set
                )

                added_here = len(
                    desired_set - original_set
                )

                # -------------------------------------------
                # Delete ONLY future/not-started route.
                # -------------------------------------------
                cursor.execute("""
                    DELETE
                    FROM job_card_process_days
                    WHERE job_card_no = %s
                      AND COALESCE(
                          is_completed,
                          0
                      ) = 0
                      AND in_time IS NULL
                """, (jc_no,))

                # -------------------------------------------
                # Reinsert future route in latest sequence.
                # IDs now follow the correct Page 3 order.
                # -------------------------------------------
                insert_sql = """
                    INSERT INTO job_card_process_days (
                        job_card_no,
                        process_name,
                        days,
                        is_completed,
                        lead_date,
                        end_date,
                        in_time,
                        out_time,
                        actual_days,
                        is_subcontract,
                        vendor_name,
                        subcontract_lead_days,
                        subcontract_start_date,
                        subcontract_expected_date
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s
                    )
                """

                for row in desired_rows:

                    cursor.execute(
                        insert_sql,
                        (
                            jc_no,

                            row.get(
                                "process_name"
                            ),

                            int(
                                row.get("days")
                                or 0
                            ),

                            int(
                                row.get(
                                    "is_completed"
                                )
                                or 0
                            ),

                            row.get(
                                "lead_date"
                            ),

                            row.get(
                                "end_date"
                            ),

                            row.get(
                                "in_time"
                            ),

                            row.get(
                                "out_time"
                            ),

                            row.get(
                                "actual_days"
                            ),

                            int(
                                row.get(
                                    "is_subcontract"
                                )
                                or 0
                            ),

                            row.get(
                                "vendor_name"
                            ),

                            row.get(
                                "subcontract_lead_days"
                            ),

                            row.get(
                                "subcontract_start_date"
                            ),

                            row.get(
                                "subcontract_expected_date"
                            ),
                        )
                    )

                removed_from_existing_jcs += (
                    removed_here
                )

                added_to_existing_jcs += (
                    added_here
                )

                synced_existing_jcs += 1

        new_data = _get_item_snapshot(cursor, item_code)
        changed_by = (
            session.get("username")
            or session.get("full_name")
            or "System"
        )

        cursor.execute("""
            INSERT INTO process_master_change_log
                (item_code, action_type, old_data, new_data, change_remark, changed_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            item_code,
            "UPDATE_ITEM",
            json.dumps(old_data, default=_json_default),
            json.dumps(new_data, default=_json_default),
            change_remark,
            changed_by,
        ))

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "message": "Item updated!",
            "existing_job_card_process_rows_removed":
                removed_from_existing_jcs,
        })
    except Error as e:
        if conn:
            conn.rollback()
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# ── DELETE ITEM ───────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/item/<item_code>/changes", methods=["GET"])
def get_item_changes(item_code):
    """Return latest process master change log entries for an item."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        _ensure_change_log_table(cursor)
        cursor.execute("""
            SELECT changed_at, changed_by, change_remark, action_type, old_data, new_data
            FROM process_master_change_log
            WHERE item_code = %s
            ORDER BY changed_at DESC, id DESC
            LIMIT 20
        """, (item_code,))
        rows = cursor.fetchall()
        for row in rows:
            if row.get("changed_at"):
                row["changed_at"] = row["changed_at"].strftime(
                    "%Y-%m-%d %H:%M:%S")
            row["old_data"] = _parse_json_column(row.get("old_data"))
            row["new_data"] = _parse_json_column(row.get("new_data"))

        cursor.close()
        conn.close()
        return jsonify({"success": True, "changes": rows})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@process_master_bp.route("/api/bom/item/<item_code>", methods=["DELETE"])
def delete_item(item_code):
    """Delete an item and all its BOM links + processes (CASCADE)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items WHERE item_code = %s", (item_code,))
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Item not found"}), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": f"Item '{item_code}' deleted!"})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── PROCESS HELPERS ───────────────────────────────────────────────────────

def _save_item_processes(cursor, item_code, process_names):
    """Replace all process steps for an item. process_names = ['Cutting', 'Heat Treatment', ...]"""
    cursor.execute(
        "DELETE FROM item_processes WHERE item_code = %s", (item_code,))
    for step_no, pname in enumerate(process_names, 1):
        pname = (pname or "").strip()
        if not pname:
            continue
        # Get or create process
        cursor.execute(
            "SELECT id FROM processes WHERE process_name = %s", (pname,))
        row = cursor.fetchone()
        if row:
            pid = row["id"] if isinstance(row, dict) else row[0]
        else:
            cursor.execute(
                "INSERT INTO processes (process_name) VALUES (%s)", (pname,))
            pid = cursor.lastrowid
        cursor.execute("""
            INSERT INTO item_processes (item_code, step_no, process_id)
            VALUES (%s, %s, %s)
        """, (item_code, step_no, pid))


# ── PROCESS LOOKUP ────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/processes", methods=["GET"])
def get_processes():
    """Return all process names for dropdowns."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, process_name FROM processes ORDER BY process_name")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "processes": rows})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── BOM LINK CRUD ─────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/link", methods=["POST"])
def add_bom_link():
    """Add a parent-child BOM link."""
    try:
        data = request.json
        parent = (data.get("parent_code") or "").strip()
        child = (data.get("child_code") or "").strip()

        if not parent or not child:
            return jsonify({"success": False, "error": "Parent and child codes are required"}), 400
        if parent == child:
            return jsonify({"success": False, "error": "Item cannot be its own child"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify both items exist
        cursor.execute(
            "SELECT item_code FROM items WHERE item_code IN (%s, %s)", (parent, child))
        found = {r["item_code"] for r in cursor.fetchall()}
        if parent not in found:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": f"Parent '{parent}' not found"}), 404
        if child not in found:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": f"Child '{child}' not found"}), 404

        # Check for circular reference: child must not be an ancestor of parent
        cursor.execute("""
            WITH RECURSIVE ancestors AS (
                SELECT parent_code AS ancestor FROM bom_links WHERE child_code = %s
                UNION
                SELECT bl.parent_code FROM ancestors a JOIN bom_links bl ON bl.child_code = a.ancestor
            )
            SELECT 1 FROM ancestors WHERE ancestor = %s LIMIT 1
        """, (parent, child))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Cannot add: this would create a circular reference"}), 400

        # Check duplicate
        cursor.execute(
            "SELECT id FROM bom_links WHERE parent_code = %s AND child_code = %s",
            (parent, child)
        )
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "This link already exists"}), 400

        # Get next sr_no
        cursor.execute(
            "SELECT COALESCE(MAX(sr_no), 0) + 1 AS next_sr FROM bom_links WHERE parent_code = %s",
            (parent,)
        )
        next_sr = cursor.fetchone()["next_sr"]

        cursor.execute("""
            INSERT INTO bom_links (parent_code, child_code, sr_no, make_buy, quantity, uom)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            parent, child, next_sr,
            data.get("make_buy") or None,
            data.get("quantity", 1),
            data.get("uom", "NOS"),
        ))

        conn.commit()
        link_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "BOM link added!", "link_id": link_id})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@process_master_bp.route("/api/bom/link/<int:link_id>", methods=["PUT"])
def update_bom_link(link_id):
    """Update a BOM link (sr_no, make_buy, quantity, uom)."""
    try:
        data = request.json
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE bom_links
            SET sr_no = %s, make_buy = %s, quantity = %s, uom = %s
            WHERE id = %s
        """, (
            data.get("sr_no"),
            data.get("make_buy") or None,
            data.get("quantity", 1),
            data.get("uom", "NOS"),
            link_id,
        ))
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Link not found"}), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "BOM link updated!"})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


@process_master_bp.route("/api/bom/link/<int:link_id>", methods=["DELETE"])
def delete_bom_link(link_id):
    """Delete a BOM link."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM bom_links WHERE id = %s", (link_id,))
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "error": "Link not found"}), 404
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "BOM link removed!"})
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── UPLOAD EXCEL (preview + confirm) ─────────────────────────────────────

@process_master_bp.route("/api/bom/upload_preview", methods=["POST"])
def upload_preview():
    """Parse an uploaded Excel file and return preview data."""
    try:
        import re

        import openpyxl

        file = request.files.get("file")
        if not file:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        def clean_value(val):
            if val is None:
                return ""
            s = str(val).strip()
            s = re.sub(r"\s+", " ", s)
            if s.lower() in ("none", "nan", "nat", "-"):
                return ""
            return s

        def clean_header(val):
            return clean_value(val).lower().replace("_", " ").strip()

        def find_col(headers, keywords):
            cleaned = [clean_header(h) for h in headers]
            for kw in keywords:
                kw_c = clean_header(kw)
                for i, h in enumerate(cleaned):
                    if h == kw_c:
                        return i
            for kw in keywords:
                kw_c = clean_header(kw)
                for i, h in enumerate(cleaned):
                    if kw_c and kw_c in h:
                        return i
            return None

        # Read Excel
        wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        wb.close()

        if len(rows) < 2:
            return jsonify({"success": False, "error": "File appears empty"}), 400

        # Detect header row
        header_idx = None
        for i, row in enumerate(rows[:20]):
            joined = " ".join([clean_header(c) for c in row])
            has_item = any(k in joined for k in [
                           "item code", "child code", "parent", "model"])
            has_proc = any(re.fullmatch(
                r"p\d+", clean_header(c).replace(" ", "")) for c in row)
            if has_item or has_proc:
                header_idx = i
                break

        if header_idx is None:
            return jsonify({"success": False, "error": "Cannot detect header row"}), 400

        headers = [clean_value(c) for c in rows[header_idx]]
        data_rows = rows[header_idx + 1:]

        # Column mapping
        col_code = find_col(
            headers, ["item code", "item_code", "child code", "child_code", "code"])
        col_desc = find_col(headers, [
                            "description", "item description", "item desc", "model name", "model_name"])
        col_type = find_col(headers, ["item type", "type"])
        col_flag = find_col(
            headers, ["a=mk,i=by", "make buy", "mk/by", "make_buy"])
        col_mat = find_col(headers, ["material", "grade"])
        col_size = find_col(headers, ["size", "model size"])
        col_part = find_col(headers, ["part name", "part_name"])
        col_parent = find_col(
            headers, ["parent", "parent code", "parent_code"])
        col_child = find_col(headers, ["child", "child code", "child_code"])
        col_qty = find_col(headers, ["quantity", "qty"])
        col_uom = find_col(headers, ["uom", "unit"])
        col_cutting = find_col(headers, [
            "cutting size",
            "cutting_size",
            "cuttingsize",
            "cut size",
            "cut_size",
            "cutting"
        ])

        # Process columns (P1-P25)
        p_cols = []
        for i, h in enumerate(headers):
            h_c = clean_header(h).replace(" ", "")
            if h_c and h_c[0] == "p" and h_c[1:].isdigit():
                p_cols.append(i)

        # Fetch existing items
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT item_code FROM items")
        existing = {r["item_code"] for r in cursor.fetchall()}
        cursor.close()
        conn.close()

        # Parse rows
        preview = []
        for row in data_rows:
            def cell(idx):
                if idx is None or idx >= len(row):
                    return ""
                return clean_value(row[idx])

            # Determine item code — try dedicated code column, fall back to parent/child
            code = cell(col_code)
            if not code and col_child is not None:
                code = cell(col_child)
            if not code:
                continue

            entry = {
                "item_code": code,
                "item_description": cell(col_desc),
                "item_type": cell(col_type) or "PART",
                "make_buy": cell(col_flag),
                "material": cell(col_mat),
                "size": cell(col_size),
                "part_name": cell(col_part),
                "parent_code": cell(col_parent),
                "quantity": cell(col_qty) or "1",
                "uom": cell(col_uom) or "NOS",
                "cutting_size": cell(col_cutting),
                "is_existing": code in existing,
            }

            # Processes
            procs = []
            for pi in p_cols:
                v = cell(pi)
                if v:
                    procs.append(v)
            entry["processes"] = procs

            preview.append(entry)

        if not preview:
            return jsonify({"success": False, "error": "No valid rows found"}), 400

        new_count = sum(1 for r in preview if not r["is_existing"])
        existing_count = sum(1 for r in preview if r["is_existing"])

        return jsonify({
            "success": True,
            "preview": preview,
            "new_count": new_count,
            "existing_count": existing_count,
            "has_bom": col_parent is not None,
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()}), 500


@process_master_bp.route("/api/bom/upload_confirm", methods=["POST"])
def upload_confirm():
    """Save uploaded preview data to database."""
    try:
        rows = request.json.get("rows", [])
        if not rows:
            return jsonify({"success": False, "error": "No data to save"}), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        inserted = updated = links_added = errors = 0

        for r in rows:
            code = (r.get("item_code") or "").strip()
            if not code:
                continue
            try:
                # Upsert item
                cursor.execute(
                    "SELECT item_code FROM items WHERE item_code = %s", (code,))
                if cursor.fetchone():
                    cursor.execute("""
                        UPDATE items
                        SET item_description = COALESCE(NULLIF(%s,''), item_description),
                            material = COALESCE(NULLIF(%s,''), material),
                            size = COALESCE(NULLIF(%s,''), size),
                            part_name = COALESCE(NULLIF(%s,''), part_name)
                        WHERE item_code = %s
                    """, (
                        r.get("item_description", ""),
                        r.get("material", ""),
                        r.get("size", ""),
                        r.get("part_name", ""),
                        code,
                    ))
                    updated += 1
                else:
                    item_type = r.get("item_type", "PART")
                    if item_type not in ("ASSEMBLY", "PART", "RAW_MATERIAL"):
                        item_type = "PART"
                    cursor.execute("""
                        INSERT INTO items (item_code, item_description, item_type, make_default, material, size, part_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        code,
                        r.get("item_description") or None,
                        item_type,
                        r.get("make_buy") if r.get(
                            "make_buy") in ("A", "I") else None,
                        r.get("material") or None,
                        r.get("size") or None,
                        r.get("part_name") or None,
                    ))
                    inserted += 1

                # Save processes
                procs = r.get("processes", [])
                if procs:
                    _save_item_processes(cursor, code, procs)

                # Save BOM link if parent provided
                parent = (r.get("parent_code") or "").strip()
                if parent and parent != code:
                    # Ensure parent exists
                    cursor.execute(
                        "SELECT item_code FROM items WHERE item_code = %s", (parent,))
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO items (item_code, item_type) VALUES (%s, 'ASSEMBLY')",
                            (parent,)
                        )
                    # Check link doesn't exist
                    cursor.execute(
                        "SELECT id FROM bom_links WHERE parent_code = %s AND child_code = %s",
                        (parent, code)
                    )
                    if not cursor.fetchone():
                        try:
                            qty = float(r.get("quantity", 1))
                        except (ValueError, TypeError):
                            qty = 1.0
                        cutting_size = _clean_cutting_size(
                            r.get("cutting_size")
                            or r.get("cutting size")
                            or r.get("CUTTING SIZE")
                            or r.get("Cutting Size")
                        )

                        cursor.execute("""
                            INSERT INTO bom_links (parent_code, child_code, make_buy, quantity, uom, cutting_size)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (
                            parent, code,
                            r.get("make_buy") if r.get(
                                "make_buy") in ("A", "I") else None,
                            qty,
                            r.get("uom", "NOS"),
                            cutting_size,
                        ))
                        links_added += 1

            except Exception:
                errors += 1

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "message": f"{inserted} new, {updated} updated, {links_added} links added, {errors} errors.",
            "inserted": inserted,
            "updated": updated,
            "links_added": links_added,
            "errors": errors,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ── STATS ─────────────────────────────────────────────────────────────────

@process_master_bp.route("/api/bom/stats", methods=["GET"])
def get_stats():
    """Return summary counts for the header."""
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS cnt FROM items")
        total_items = cursor.fetchone()["cnt"]

        cursor.execute("""
            SELECT COUNT(DISTINCT parent_code) AS cnt
            FROM bom_links
            WHERE parent_code NOT IN (SELECT DISTINCT child_code FROM bom_links)
        """)
        total_assemblies = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) AS cnt FROM processes")
        total_processes = cursor.fetchone()["cnt"]

        cursor.close()
        conn.close()
        return jsonify({
            "success": True,
            "total_items": total_items,
            "total_assemblies": total_assemblies,
            "total_processes": total_processes,
        })
    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500
# ── BOM Tree (grouped by BOM No) ─────────────────────────────────────────────


@process_master_bp.route("/api/bom/bom_tree", methods=["GET"])
def get_bom_tree():
    """
    Returns BOM Nos with their parent + children.
    Grouped: BOM No → Parent → Children (with qty, uom, make_buy)
    """
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
        offset = (page - 1) * per_page
        q = (request.args.get("q") or "").strip()
        f_make = request.args.get("make")    # 'A' or 'I'
        f_proc = request.args.get("process")  # 'yes' or 'no'

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # ── Build WHERE clause ────────────────────────────────────────────────
        where = ["bl.bom_no IS NOT NULL", "bl.bom_no != ''"]
        params = []

        if q:
            # If query looks like a BOM No (starts with B followed by digits)
            import re
            if re.match(r'^B\d+$', q, re.IGNORECASE):
                where.append("bl.bom_no = %s")
                params.append(q.upper())
            else:
                where.append("""(
                    bl.parent_code LIKE %s OR
                    bl.child_code LIKE %s OR
                    pi.item_description LIKE %s OR
                    ci.item_description LIKE %s
                )""")
                like = f"%{q}%"
                params.extend([like, like, like, like])

        if f_make in ("A", "I"):
            where.append("bl.make_buy = %s")
            params.append(f_make)

        if f_proc == "yes":
            where.append("""EXISTS (
                SELECT 1 FROM item_processes ip WHERE ip.item_code = bl.child_code
            )""")
        elif f_proc == "no":
            where.append("""NOT EXISTS (
                SELECT 1 FROM item_processes ip WHERE ip.item_code = bl.child_code
            )""")

        where_sql = "WHERE " + " AND ".join(where) if where else ""

        # ── Total BOM Nos count ───────────────────────────────────────────────
        cursor.execute(f"""
            SELECT COUNT(DISTINCT bl.bom_no) AS cnt
            FROM bom_links bl
            LEFT JOIN items pi ON pi.item_code = bl.parent_code
            LEFT JOIN items ci ON ci.item_code = bl.child_code
            {where_sql}
        """, params)
        total = cursor.fetchone()["cnt"]

        # ── Fetch BOM Nos for this page ───────────────────────────────────────
        cursor.execute(f"""
            SELECT DISTINCT bl.bom_no
            FROM bom_links bl
            LEFT JOIN items pi ON pi.item_code = bl.parent_code
            LEFT JOIN items ci ON ci.item_code = bl.child_code
            {where_sql}
            ORDER BY bl.bom_no ASC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])
        bom_nos = [r["bom_no"] for r in cursor.fetchall()]

        if not bom_nos:
            cursor.close()
            conn.close()
            return jsonify({"success": True, "total": total, "page": page, "per_page": per_page, "data": []})

        # ── Fetch all links for these BOM Nos ─────────────────────────────────
        fmt = ",".join(["%s"] * len(bom_nos))
        cursor.execute(f"""
            SELECT
                bl.bom_no,
                bl.parent_code,
                bl.child_code,
                bl.make_buy,
                bl.quantity,
                bl.uom,
                bl.cutting_size,
                bl.is_alternate,
                pi.item_description AS parent_desc,
                ci.item_description AS child_desc,
                ci.item_type        AS child_type,
                ci.size             AS child_size,
                ci.part_name        AS child_part,
                ci.material         AS child_material
            FROM bom_links bl
            LEFT JOIN items pi ON pi.item_code = bl.parent_code
            LEFT JOIN items ci ON ci.item_code = bl.child_code
            WHERE bl.bom_no IN ({fmt})
            ORDER BY bl.bom_no ASC, bl.make_buy ASC, bl.child_code ASC
        """, bom_nos)
        rows = cursor.fetchall()

        # ── Group into tree structure ─────────────────────────────────────────
        from collections import OrderedDict
        tree = OrderedDict()

        for row in rows:
            bno = row["bom_no"]
            if bno not in tree:
                tree[bno] = {
                    "bom_no":      bno,
                    "parent_code": row["parent_code"],
                    "parent_desc": row["parent_desc"] or "",
                    "children":    []
                }
            tree[bno]["children"].append({
                "child_code":     row["child_code"],
                "child_desc":     row["child_desc"] or "",
                "child_type":     row["child_type"] or "",
                "child_size":     row["child_size"] or "",
                "child_part":     row["child_part"] or "",
                "child_material": row["child_material"] or "",
                "make_buy":       row["make_buy"] or "",
                "quantity":       str(row["quantity"] or "1"),
                "uom":            row["uom"] or "Nos.",
                "cutting_size":   row.get("cutting_size") or "",
                "is_alternate":   int(row.get("is_alternate") or 0),
            })

        cursor.close()
        conn.close()

        return jsonify({
            "success":  True,
            "total":    total,
            "page":     page,
            "per_page": per_page,
            "data":     list(tree.values()),
        })

    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500
# ── Nested BOM Tree UI API ────────────────────────────────────────────────────


@process_master_bp.route("/api/bom/bom_tree_nested", methods=["GET"])
def get_bom_tree_nested():
    """
    Returns BOM data in UI-friendly nested format:

    BOM No / Parent
    ├── I / BUY ITEMS
    └── A / MAKE ITEMS
        ├── Process Routing
        └── Raw Material / Raw Material Options

    This is a new safe API and does not disturb existing /api/bom/bom_tree.
    """
    conn = None
    cursor = None

    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 50))
        offset = (page - 1) * per_page

        q = (request.args.get("q") or "").strip()
        bom_level = (request.args.get("bom_level") or "top").strip()
        make_buy = (request.args.get("make_buy") or "").strip()
        process_status = (request.args.get("process_status") or "").strip()
        raw_material = (request.args.get("raw_material") or "").strip()
        item_type = (request.args.get("item_type") or "").strip()
        process_name = (request.args.get("process_name") or "").strip()
        material = (request.args.get("material") or "").strip()
        size = (request.args.get("size") or "").strip()
        updated = (request.args.get("updated") or "").strip()

        # Backward compatibility for the previous quick-filter query params.
        legacy_make = request.args.get("make")
        legacy_process = request.args.get("process")
        if not make_buy and legacy_make in ("A", "I"):
            make_buy = legacy_make
        if not process_status and legacy_process == "yes":
            process_status = "has_process"
        elif not process_status and legacy_process == "no":
            process_status = "no_process"

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        where = [
            "bl.bom_no IS NOT NULL",
            "bl.bom_no != ''",
        ]
        params = []

        if bom_level in ("", "top", "all"):
            if bom_level != "all":
                where.append("""
                    bl.parent_code NOT IN (
                        SELECT DISTINCT child_code
                        FROM bom_links
                        WHERE child_code IS NOT NULL
                          AND child_code != ''
                    )
                """)
        elif bom_level == "child":
            where.append("""
                bl.parent_code IN (
                    SELECT DISTINCT child_code
                    FROM bom_links
                    WHERE child_code IS NOT NULL
                      AND child_code != ''
                )
            """)
        elif bom_level == "raw":
            where.append("""
                bl.child_code NOT IN (
                    SELECT DISTINCT parent_code
                    FROM bom_links
                    WHERE parent_code IS NOT NULL
                      AND parent_code != ''
                )
            """)

        if q:
            import re

            if re.match(r"^B\d+$", q, re.IGNORECASE):
                where.append("bl.bom_no = %s")
                params.append(q.upper())
            else:
                where.append("""(
                    bl.parent_code LIKE %s OR
                    bl.child_code LIKE %s OR
                    pi.item_description LIKE %s OR
                    ci.item_description LIKE %s
                )""")
                like = f"%{q}%"
                params.extend([like, like, like, like])

        if make_buy in ("A", "I"):
            where.append("bl.make_buy = %s")
            params.append(make_buy)

        if process_status == "has_process":
            where.append("""EXISTS (
                SELECT 1
                FROM item_processes ip
                WHERE ip.item_code = bl.child_code
            )""")
        elif process_status == "no_process":
            where.append("""NOT EXISTS (
                SELECT 1
                FROM item_processes ip
                WHERE ip.item_code = bl.child_code
            )""")
        elif process_status == "incomplete_process":
            required_processes = [
                "Drawing",
                "Raw Material",
                "Cutting",
                "Quality Check",
                "Assembly",
                "Store",
            ]
            where.append("""EXISTS (
                SELECT 1
                FROM item_processes ip
                WHERE ip.item_code = bl.child_code
            )""")
            missing_clauses = []
            for required in required_processes:
                missing_clauses.append("""NOT EXISTS (
                    SELECT 1
                    FROM item_processes ip_req
                    JOIN processes p_req ON p_req.id = ip_req.process_id
                    WHERE ip_req.item_code = bl.child_code
                      AND LOWER(TRIM(p_req.process_name)) = LOWER(TRIM(%s))
                )""")
                params.append(required)
            where.append("(" + " OR ".join(missing_clauses) + ")")

        if raw_material == "has_raw_material":
            where.append("""bl.make_buy = 'A' AND EXISTS (
                SELECT 1
                FROM bom_links raw_bl
                WHERE raw_bl.parent_code = bl.child_code
            )""")
        elif raw_material == "no_raw_material":
            where.append("""bl.make_buy = 'A' AND NOT EXISTS (
                SELECT 1
                FROM bom_links raw_bl
                WHERE raw_bl.parent_code = bl.child_code
            )""")
        elif raw_material == "multiple_raw_material":
            where.append("""bl.make_buy = 'A' AND (
                SELECT COUNT(*)
                FROM bom_links raw_bl
                WHERE raw_bl.parent_code = bl.child_code
            ) >= 2""")
        elif raw_material == "cutting_missing":
            where.append("""bl.make_buy = 'A' AND EXISTS (
                SELECT 1
                FROM bom_links raw_bl
                WHERE raw_bl.parent_code = bl.child_code
                  AND (raw_bl.cutting_size IS NULL OR TRIM(raw_bl.cutting_size) = '')
            )""")

        if item_type in ("ASSEMBLY", "PART", "RAW_MATERIAL"):
            where.append("(ci.item_type = %s OR pi.item_type = %s)")
            params.extend([item_type, item_type])

        if process_name:
            where.append("""EXISTS (
                SELECT 1
                FROM item_processes ip_proc
                JOIN processes p_proc ON p_proc.id = ip_proc.process_id
                WHERE ip_proc.item_code = bl.child_code
                  AND p_proc.process_name = %s
            )""")
            params.append(process_name)

        if material:
            like = f"%{material}%"
            where.append("""(
                pi.material LIKE %s
                OR ci.material LIKE %s
                OR EXISTS (
                    SELECT 1
                    FROM bom_links raw_bl
                    LEFT JOIN items raw_i ON raw_i.item_code = raw_bl.child_code
                    WHERE raw_bl.parent_code = bl.child_code
                      AND (
                          raw_i.material LIKE %s
                          OR raw_i.item_description LIKE %s
                      )
                )
            )""")
            params.extend([like, like, like, like])

        if size:
            like = f"%{size}%"
            where.append("""(
                pi.size LIKE %s
                OR ci.size LIKE %s
                OR EXISTS (
                    SELECT 1
                    FROM bom_links raw_bl
                    LEFT JOIN items raw_i ON raw_i.item_code = raw_bl.child_code
                    WHERE raw_bl.parent_code = bl.child_code
                      AND raw_i.size LIKE %s
                )
            )""")
            params.extend([like, like, like])

        if updated == "today":
            where.append("(DATE(pi.updated_at) = CURDATE() OR DATE(ci.updated_at) = CURDATE())")
        elif updated == "week":
            where.append("(pi.updated_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) OR ci.updated_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY))")
        elif updated == "month":
            where.append("(pi.updated_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY) OR ci.updated_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY))")
        elif updated == "never":
            where.append("""(
                pi.updated_at IS NULL
                OR ci.updated_at IS NULL
                OR pi.updated_at = pi.created_at
                OR ci.updated_at = ci.created_at
            )""")

        where_sql = "WHERE " + " AND ".join(where)

        # 1) Total BOM count
        cursor.execute(f"""
            SELECT COUNT(DISTINCT bl.bom_no) AS cnt
            FROM bom_links bl
            LEFT JOIN items pi ON pi.item_code = bl.parent_code
            LEFT JOIN items ci ON ci.item_code = bl.child_code
            {where_sql}
        """, params)

        total = cursor.fetchone()["cnt"]

        # 2) BOM numbers for current page
        cursor.execute(f"""
            SELECT DISTINCT bl.bom_no
            FROM bom_links bl
            LEFT JOIN items pi ON pi.item_code = bl.parent_code
            LEFT JOIN items ci ON ci.item_code = bl.child_code
            {where_sql}
            ORDER BY bl.bom_no ASC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        bom_nos = [row["bom_no"] for row in cursor.fetchall()]

        if not bom_nos:
            return jsonify({
                "success": True,
                "total": total,
                "page": page,
                "per_page": per_page,
                "data": [],
            })

        bom_placeholders = ",".join(["%s"] * len(bom_nos))

        # 3) First get root parent details for selected top-level BOM Nos.
        # Important:
        # Some direct Buy rows under the same parent have blank bom_no.
        # So after finding top-level parent_code, fetch children by parent_code,
        # not only by bom_no.
        cursor.execute(f"""
            SELECT DISTINCT
                bl.bom_no AS root_bom_no,
                bl.parent_code,
                pi.item_description AS parent_desc,
                pi.size AS parent_size,
                pi.material AS parent_material,
                pi.part_name AS parent_part,
                pi.item_type AS parent_type
            FROM bom_links bl
            LEFT JOIN items pi ON pi.item_code = bl.parent_code
            WHERE bl.bom_no IN ({bom_placeholders})
            ORDER BY bl.bom_no ASC
        """, bom_nos)

        root_rows = cursor.fetchall()

        root_meta_by_parent = {}
        for row in root_rows:
            parent_code = row.get("parent_code")
            if not parent_code:
                continue

            if parent_code not in root_meta_by_parent:
                root_meta_by_parent[parent_code] = {
                    "bom_no": row.get("root_bom_no") or "",
                    "parent_code": parent_code,
                    "parent_desc": row.get("parent_desc") or "",
                    "parent_size": row.get("parent_size") or "",
                    "parent_material": row.get("parent_material") or "",
                    "parent_part": row.get("parent_part") or "",
                    "parent_type": row.get("parent_type") or "",
                }

        root_parent_codes = list(root_meta_by_parent.keys())

        if not root_parent_codes:
            return jsonify({
                "success": True,
                "total": total,
                "page": page,
                "per_page": per_page,
                "data": [],
            })

        parent_placeholders = ",".join(["%s"] * len(root_parent_codes))

        # 3B) Fetch ALL direct children of the root parent.
        # This includes:
        # - A / Make rows with bom_no
        # - I / Buy rows with blank bom_no
        cursor.execute(f"""
            SELECT
                bl.id AS link_id,
                bl.bom_no AS child_bom_no,
                bl.parent_code,
                bl.child_code,
                bl.make_buy,
                bl.quantity,
                bl.uom,
                bl.cutting_size,
                bl.is_alternate,

                ci.item_description AS child_desc,
                ci.size AS child_size,
                ci.material AS child_material,
                ci.part_name AS child_part,
                ci.item_type AS child_type
            FROM bom_links bl
            LEFT JOIN items ci ON ci.item_code = bl.child_code
            WHERE bl.parent_code IN ({parent_placeholders})
            ORDER BY
                bl.parent_code ASC,
                CASE WHEN bl.make_buy = 'I' THEN 0 ELSE 1 END,
                COALESCE(bl.sr_no, 999999),
                bl.id,
                bl.child_code
        """, root_parent_codes)

        direct_rows = cursor.fetchall()

        make_codes = [
            row["child_code"]
            for row in direct_rows
            if row.get("make_buy") == "A" and row.get("child_code")
        ]

        process_map = _get_processes_for_items(cursor, make_codes)

        # 4) Raw material / child rows under every Make item
        raw_map = {}

        if make_codes:
            make_placeholders = ",".join(["%s"] * len(make_codes))

            cursor.execute(f"""
                SELECT
                    bl.id AS link_id,
                    bl.bom_no,
                    bl.parent_code,
                    bl.child_code,
                    bl.make_buy,
                    bl.quantity,
                    bl.uom,
                    bl.cutting_size,
                    bl.is_alternate,

                    ci.item_description AS child_desc,
                    ci.size AS child_size,
                    ci.material AS child_material,
                    ci.part_name AS child_part,
                    ci.item_type AS child_type
                FROM bom_links bl
                LEFT JOIN items ci ON ci.item_code = bl.child_code
                WHERE bl.parent_code IN ({make_placeholders})
                ORDER BY
                    bl.parent_code,
                    CASE WHEN bl.make_buy = 'I' THEN 0 ELSE 1 END,
                    COALESCE(bl.sr_no, 999999),
                    bl.id,
                    bl.child_code
            """, make_codes)

            for row in cursor.fetchall():
                parent_code = row.get("parent_code")
                raw_map.setdefault(parent_code, []).append({
                    "link_id": row.get("link_id"),
                    "bom_no": row.get("bom_no") or "",
                    "child_code": row.get("child_code") or "",
                    "child_desc": row.get("child_desc") or "",
                    "child_size": row.get("child_size") or "",
                    "child_material": row.get("child_material") or "",
                    "child_part": row.get("child_part") or "",
                    "child_type": row.get("child_type") or "",
                    "make_buy": row.get("make_buy") or "",
                    "quantity": str(row.get("quantity") or "1"),
                    "uom": row.get("uom") or "Nos.",
                    "cutting_size": row.get("cutting_size") or "",
                    "is_alternate": int(row.get("is_alternate") or 0),
                })

        # 5) Build UI-friendly nested structure
        from collections import OrderedDict

        tree = OrderedDict()

        # Create root BOM rows first
        for parent_code, meta in root_meta_by_parent.items():
            root_bom_no = meta.get("bom_no") or parent_code

            tree[root_bom_no] = {
                "bom_no": meta.get("bom_no") or "",
                "parent_code": parent_code,
                "parent_desc": meta.get("parent_desc") or "",
                "parent_size": meta.get("parent_size") or "",
                "parent_material": meta.get("parent_material") or "",
                "parent_part": meta.get("parent_part") or "",
                "parent_type": meta.get("parent_type") or "",
                "buy_items": [],
                "make_items": [],
            }

        for row in direct_rows:
            parent_code = row.get("parent_code") or ""
            meta = root_meta_by_parent.get(parent_code)

            if not meta:
                continue
            if make_buy in ("A", "I") and row.get("make_buy") != make_buy:
                continue

            root_bom_no = meta.get("bom_no") or parent_code

            child_bom_no = row.get("child_bom_no") or ""

            child = {
                "link_id": row.get("link_id"),
                "bom_no": child_bom_no,
                "child_code": row.get("child_code") or "",
                "child_desc": row.get("child_desc") or "",
                "child_size": row.get("child_size") or "",
                "child_material": row.get("child_material") or "",
                "child_part": row.get("child_part") or "",
                "child_type": row.get("child_type") or "",
                "make_buy": row.get("make_buy") or "",
                "quantity": str(row.get("quantity") or "1"),
                "uom": row.get("uom") or "Nos.",
                "cutting_size": row.get("cutting_size") or "",
            }

            if row.get("make_buy") == "A":
                raw_materials = raw_map.get(row.get("child_code"), [])

                # Prefer child BOM No from raw-material BOM if available.
                # Example:
                # NAINR0000304 raw material belongs to B0000017,
                # so show B0000017 under the make item.
                if raw_materials:
                    child["bom_no"] = raw_materials[0].get("bom_no") or child_bom_no

                child["processes"] = process_map.get(row.get("child_code"), [])
                raw_bom_no = ""
                
                for raw in raw_materials:
                    if raw.get("bom_no"):
                        raw_bom_no = raw.get("bom_no")
                        break
                if raw_bom_no:
                    child["bom_no"] = raw_bom_no
                elif child_bom_no:
                    child["bom_no"] = child_bom_no
                child["raw_materials"] = raw_materials
                child["raw_material_title"] = (
                    "RAW MATERIAL OPTIONS"
                    if len(raw_materials) > 1
                    else "RAW MATERIAL"
                    if len(raw_materials) == 1
                    else "NO RAW MATERIAL FOUND"
                )

                tree[root_bom_no]["make_items"].append(child)

            else:
                tree[root_bom_no]["buy_items"].append(child)

        return jsonify({
            "success": True,
            "total": total,
            "page": page,
            "per_page": per_page,
            "data": list(tree.values()),
        })

    except Error as e:
        return jsonify({"success": False, "error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ── BOM Manufacturing Process Flow API ─────────────────────────────────────
# Bottom-up process sequence:
# childest - C item process first, then upper MAKE item processes.

@process_master_bp.route("/api/bom/process_flow/<bom_no>", methods=["GET"])
def get_bom_process_flow(bom_no):
    """
    Return manufacturing process sequence for a BOM No.

    Rule:
    1. Deepest / childest - C MAKE item processes first
    2. Then parent MAKE item processes
    3. Then upper parent MAKE item processes
    4. Root assembly can go to Store / Assembly after all sequence completes
    """
    conn = None
    cursor = None

    try:
        bom_no = (bom_no or "").strip().upper()

        if not bom_no:
            return jsonify({
                "success": False,
                "error": "BOM No is required"
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            WITH RECURSIVE bom_tree AS (
                SELECT
                    bl.bom_no,
                    bl.parent_code,
                    pi.item_description AS parent_description,
                    bl.child_code,
                    ci.item_description AS child_description,
                    bl.make_buy,
                    bl.quantity,
                    bl.uom,
                    bl.cutting_size,
                    1 AS level_no,
                    CAST(CONCAT(bl.parent_code, ' > ', bl.child_code) AS CHAR(2000)) AS path_text
                FROM bom_links bl
                LEFT JOIN items pi
                    ON pi.item_code = bl.parent_code
                LEFT JOIN items ci
                    ON ci.item_code = bl.child_code
                WHERE bl.bom_no = %s

                UNION ALL

                SELECT
                    bl2.bom_no,
                    bl2.parent_code,
                    pi2.item_description AS parent_description,
                    bl2.child_code,
                    ci2.item_description AS child_description,
                    bl2.make_buy,
                    bl2.quantity,
                    bl2.uom,
                    bl2.cutting_size,
                    bt.level_no + 1 AS level_no,
                    CAST(CONCAT(bt.path_text, ' > ', bl2.child_code) AS CHAR(2000)) AS path_text
                FROM bom_tree bt
                JOIN bom_links bl2
                    ON bl2.parent_code = bt.child_code
                LEFT JOIN items pi2
                    ON pi2.item_code = bl2.parent_code
                LEFT JOIN items ci2
                    ON ci2.item_code = bl2.child_code
            ),

            ranked_items AS (
                SELECT
                    bt.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY bt.child_code
                        ORDER BY bt.level_no DESC, LENGTH(bt.path_text) DESC
                    ) AS rn
                FROM bom_tree bt
                WHERE bt.make_buy = 'A'
            ),

            unique_items AS (
                SELECT *
                FROM ranked_items
                WHERE rn = 1
            ),

            process_flow AS (
                SELECT
                    ui.level_no,
                    ui.bom_no,
                    ui.parent_code,
                    ui.parent_description,
                    ui.child_code AS item_code,
                    ui.child_description AS item_description,
                    ui.make_buy,
                    CASE
                        WHEN TRIM(ui.child_description) REGEXP '[[:space:]]-[[:space:]]*C$'
                            THEN 'CHILDEST - C ITEM'
                        ELSE 'UPPER LEVEL ITEM'
                    END AS item_level_type,
                    ip.step_no,
                    p.process_name,
                    ui.path_text
                FROM unique_items ui
                JOIN item_processes ip
                    ON ip.item_code = ui.child_code
                JOIN processes p
                    ON p.id = ip.process_id
            )

            SELECT
                ROW_NUMBER() OVER (
                    ORDER BY
                        level_no DESC,
                        item_code,
                        step_no
                ) AS process_sequence,
                level_no,
                bom_no,
                parent_code,
                parent_description,
                item_code,
                item_description,
                item_level_type,
                step_no,
                process_name,
                path_text
            FROM process_flow
            ORDER BY
                level_no DESC,
                item_code,
                step_no
        """, (bom_no,))

        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "bom_no": bom_no,
            "total_processes": len(rows),
            "process_flow": rows
        })

    except Error as e:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500