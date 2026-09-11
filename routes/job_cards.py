"""Job card API routes for Demo 2.
Job card numbers have NO prefix — stored as plain numbers/slash format.
"""


import json
import logging
import math
import re
import traceback
import uuid
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request, session
from mysql.connector import Error

from db import get_connection

_IST = timedelta(hours=5, minutes=30)
def _to_ist(dt): return dt + _IST if dt else dt


# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

job_cards_bp = Blueprint("job_cards", __name__)

PROCESS_COUNT = 25
PROCESS_COLUMNS = [f"p{i}" for i in range(1, PROCESS_COUNT + 1)]
PROCESS_COLUMNS_SQL = ",".join(PROCESS_COLUMNS)
PROCESS_ASSIGNMENTS_SQL = ",".join(f"{col}=%s" for col in PROCESS_COLUMNS)
PROCESS_PLACEHOLDERS_SQL = ",".join(["%s"] * PROCESS_COUNT)
FIXED_PROCESS_FLOW = ["Drawing", "Raw Material", "Cutting"]
FINAL_PROCESS_PREFIX = ["Drawing", "Raw Material", "Cutting"]
FINAL_PROCESS_SUFFIX = ["Quality Check", "Store"]
KNOWN_PROCESS_NAMES = [
    "CNC Machining 1st Side",
    "CNC Machining 2nd Side",
    "Drilling & Tapping",
    "Heat Treatment",
    "Raw Material",
    "Rough Turning",
    "CNC Machining",
    "VMC Machining",
    "Sub Contract",
    "Normalising",
    "ID Grinding",
    "OD Grinding",
    "Blackening",
    "Inspection",
    "Broaching",
    "Assembly",
    "Grinding",
    "Slitting",
    "Drawing",
    "Cutting",
    "Turning",
    "Milling",
    "Forging",
    "Store",
    "VMC",
]


def normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    value = str(value).replace("\u00a0", " ").strip()
    if value.lower() in ("", "none", "nan", "nat", "-"):
        return ""
    value = re.sub(r"\s+", " ", value)
    if re.fullmatch(r"\d+\.0", value):
        return value[:-2]
    return value


def normalize_key(value):
    value = normalize_text(value).lower()
    value = (
        value.replace("ø", "dia")
        .replace("Ø", "dia")
        .replace("ø", "dia")
        .replace("Ø", "dia")
    )
    return re.sub(r"[^a-z0-9]+", "", value)


def _label_key(value):
    return normalize_key(str(value).rstrip(":"))


def _is_likely_code(value):
    value = normalize_text(value)
    return bool(re.fullmatch(r"[A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*", value, flags=re.IGNORECASE))


def _is_ignored_raw_value(value):
    value = normalize_text(value)
    value_lower = value.lower()
    key = normalize_key(value)
    if not value or value in (":", "::"):
        return True
    if key in {
        "itemdesc",
        "itemdescription",
        "itemname",
        "witemdesc",
        "witemdescription",
        "witemname",
        "itemcode",
        "childcode",
        "jobcardno",
        "jobcard",
        "process",
        "processdescription",
        "processdescritption",
        "page",
        "pageno",
        "date",
        "size",
        "material",
        "materail",
        "drgno",
        "rev",
    }:
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?", value):
        return True
    if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", value):
        return True
    if re.fullmatch(r"page\s*[-:]?\s*\d+", value_lower):
        return True
    ignored_fragments = (
        "nmtg mechtrans",
        "company",
        "page no",
        "job card",
        "process description",
        "process descritption",
    )
    return any(fragment in value.lower() for fragment in ignored_fragments)


def extract_item_desc_from_raw_job_card(flat_cells):
    cells = [normalize_text(cell) for cell in flat_cells]
    label_keys = {"itemdesc", "itemdescription", "itemname",
                  "witemdesc", "witemdescription", "witemname"}

    for idx, cell in enumerate(cells):
        if not cell:
            continue
        label_match = re.match(
            r"^\s*(w?item\s*(?:desc(?:ription)?|name))\s*:?\s*(.*)$",
            cell,
            flags=re.IGNORECASE,
        )
        if label_match:
            value = normalize_text(label_match.group(2))
            if not _is_likely_code(value) and not _is_ignored_raw_value(value):
                return value
            candidates = []
            for candidate in cells[idx + 1: idx + 10]:
                candidate = normalize_text(candidate)
                if not candidate or _is_ignored_raw_value(candidate):
                    continue
                candidates.append(candidate)
            for candidate in candidates:
                if not _is_likely_code(candidate):
                    return candidate
            continue

        if _label_key(cell) not in label_keys:
            continue

        candidates = []
        for candidate in cells[idx + 1: idx + 10]:
            candidate = normalize_text(candidate)
            if not candidate or _is_ignored_raw_value(candidate):
                continue
            candidates.append(candidate)

        for candidate in candidates:
            if not _is_likely_code(candidate):
                return candidate

    text = "\n".join(cells)
    match = re.search(
        r"\bW?Item\s+Desc(?:ription)?\s*:?\s*([^\r\n]+)",
        text,
        flags=re.IGNORECASE,
    )
    return normalize_text(match.group(1)) if match else ""


def extract_child_code_from_raw_job_card(flat_cells):
    cells = [normalize_text(cell) for cell in flat_cells]
    label_keys = {"itemcode", "childcode", "itemname", "witemcode"}

    for idx, cell in enumerate(cells):
        inline = re.match(
            r"^\s*(?:w?item\s*(?:code|name)|child\s*code)\s*:?\s*([A-Z0-9/-]+)",
            cell,
            flags=re.IGNORECASE,
        )
        if inline and _is_likely_code(inline.group(1)):
            return normalize_text(inline.group(1))

        if _label_key(cell) not in label_keys:
            continue
        for candidate in cells[idx + 1: idx + 8]:
            if _is_likely_code(candidate):
                return normalize_text(candidate)

    for cell in cells:
        match = re.search(
            r"\b[A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*\b", cell, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(0))
    return ""


def extract_size_from_item_desc(item_desc):
    item_desc = normalize_text(item_desc)
    if not item_desc:
        return ""

    patterns = [
        r"(M\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?\s*P?)\b",
        r"(\d+(?:[./]\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*[xX]\s*\d+(?:\.\d+)?)?(?:\s*[A-Za-z]+)?)\s*$",
        r"-\s*([A-Za-z]?\d+(?:[./]\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*[xX]\s*\d+(?:\.\d+)?)?(?:\s*[A-Za-z]+)?)\s*$",
    ]
    for pattern in patterns:
        match = re.search(pattern, item_desc, flags=re.IGNORECASE)
        if match:
            return normalize_text(match.group(1))
    return ""


def extract_part_name_from_item_desc(item_desc):
    item_desc = normalize_text(item_desc)
    if not item_desc:
        return ""
    part = re.split(r"\s+of\s+", item_desc, maxsplit=1, flags=re.IGNORECASE)[0]
    part = re.split(r"\s+-\s+", part, maxsplit=1)[0]
    return normalize_text(part)


def _canonical_process_name(value, allow_contains=True):
    value = normalize_text(value)
    if _is_ignored_raw_value(value):
        return ""
    value_key = normalize_key(value)
    if not value_key:
        return ""

    for process in sorted(KNOWN_PROCESS_NAMES, key=len, reverse=True):
        process_key = normalize_key(process)
        if value_key == process_key or (allow_contains and process_key in value_key):
            return process
    return ""


def _is_valid_bm_process_value(value):
    value = normalize_text(value)
    if _is_ignored_raw_value(value):
        return False
    if len(value) > 100:
        return False
    if not re.search(r"[A-Za-z]", value):
        return False
    return True


def _dedupe_processes(processes):
    result = []
    seen = set()
    for process in processes:
        process = normalize_text(process)
        key = normalize_key(process)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(process)
    return result


def _sequence_process_key(process):
    key = normalize_key(process)
    aliases = {
        "rm": "rawmaterial",
        "rawmat": "rawmaterial",
        "rawmaterial": "rawmaterial",
        "qualitycheck": "qc",
        "quality": "qc",
        "qc": "qc",
    }
    return aliases.get(key, key)


def build_final_process_sequence(processes):
    """
    Build the saved stage timeline:
    Drawing, Raw Material, Cutting, [actual processes], QC, Assembly, Store.
    """
    prefix = list(FINAL_PROCESS_PREFIX)
    suffix = list(FINAL_PROCESS_SUFFIX)
    prefix_keys = {_sequence_process_key(process) for process in prefix}
    suffix_keys = {_sequence_process_key(process) for process in suffix}
    seen = set(prefix_keys)
    middle = []
    max_middle = max(0, PROCESS_COUNT - len(prefix) - len(suffix))

    for process in processes or []:
        name = normalize_text(process)
        key = _sequence_process_key(name)
        if not name or not key:
            continue
        if key in prefix_keys or key in suffix_keys or key in seen:
            continue
        middle.append(name)
        seen.add(key)
        if len(middle) >= max_middle:
            break

    return (prefix + middle + suffix)[:PROCESS_COUNT]


def extract_processes_from_column_bm_or_raw(rows):
    """
    Robust process extraction for ERP job card CSV print layout.

    This does NOT depend on fixed BM/BF column.
    It detects process name from the Process Description section row-wise.
    """

    BAD_PROCESS_KEYS = {
        "mcno",
        "mchno",
        "machineno",
        "shift",
        "operator",
        "date",
        "checkedby",
        "issueqty",
        "okqty",
        "okayqty",
        "o.k.qty",
        "rejqty",
        "rwqty",
        "r/wqty",
        "hrs",
        "hour",
        "hours",
        "remark",
        "remarks",
        "sign",
        "signature",
        "no",
        "no.",
        "process",
        "processdescription",
        "processdescritption",
        "subcontractor",
        "chnno",
        "specialtool",
        "inspectionstatus",
        "prepareby",
        "prodincharge",
        "qcincharge",
        "receivedby",
        "postingby",
        "costing",
    }

    PROCESS_LABEL_KEYS = {
        "processdescription",
        "processdescritption",
    }

    def is_bad_process_value(value):
        value = normalize_text(value)
        key = normalize_key(value)

        if not value:
            return True

        if key in BAD_PROCESS_KEYS:
            return True

        if value in (":", "::", "-", "_"):
            return True

        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return True

        if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", value):
            return True

        bad_fragments = (
            "o.k. qty",
            "ok qty",
            "r/w qty",
            "rej qty",
            "m/c. no",
            "machine no",
            "process descritption",
            "process description",
            "inspection status",
            "prepare by",
            "prod. incharge",
            "q.c incharge",
            "received by",
            "posting by",
        )

        return any(fragment in value.lower() for fragment in bad_fragments)

    def exact_known_process(value):
        value = normalize_text(value)

        if is_bad_process_value(value):
            return ""

        value_key = normalize_key(value)

        for process in sorted(KNOWN_PROCESS_NAMES, key=len, reverse=True):
            if value_key == normalize_key(process):
                return process

        return ""

    def process_candidate(value, allow_unknown=False):
        value = normalize_text(value)

        if is_bad_process_value(value):
            return ""

        known = exact_known_process(value)
        if known:
            return known

        if allow_unknown:
            if len(value) <= 80 and re.search(r"[A-Za-z]", value):
                return value

        return ""

    extracted = []

    # 1. Best method: detect process from the Process Description section.
    for row in rows:
        cleaned_row = [normalize_text(cell) for cell in row]

        for idx, cell in enumerate(cleaned_row):
            if normalize_key(cell) not in PROCESS_LABEL_KEYS:
                continue

            # After "Process Description", find process sequence number,
            # then next valid text is the process name.
            scan_end = min(len(cleaned_row), idx + 30)

            for pos in range(idx + 1, scan_end):
                current = normalize_text(cleaned_row[pos])

                if not re.fullmatch(r"\d+", current):
                    continue

                for candidate_pos in range(pos + 1, min(pos + 8, len(cleaned_row))):
                    candidate = process_candidate(
                        cleaned_row[candidate_pos],
                        allow_unknown=True
                    )

                    if candidate:
                        extracted.append(candidate)
                        break

                break

    # Preserve repeated operations because the same process may
    # legitimately occur at different sequence steps.
    if extracted:
        return extracted

    # 2. Fallback: scan all cells for exact known process names only.
    # This prevents wrong values like M/c. No. from becoming process.
    for row in rows:
        for cell in row:
            candidate = exact_known_process(cell)
            if candidate:
                extracted.append(candidate)

    return _dedupe_processes(extracted)


def build_process_flow_from_csv(csv_processes):
    canonical_processes = [
        _canonical_process_name(
            process, allow_contains=False) or normalize_text(process)
        for process in csv_processes
    ]
    return build_final_process_sequence(canonical_processes)


def upsert_process_master_from_job_card_csv(item_desc, size, material, part_name, final_processes):
    item_desc = normalize_text(item_desc)
    size = normalize_text(size)
    material = normalize_text(material)
    part_name = normalize_text(part_name)
    final_processes = [normalize_text(
        process) for process in final_processes if normalize_text(process)]

    if not item_desc or not final_processes:
        return None

    procs = (final_processes + [""] * PROCESS_COUNT)[:PROCESS_COUNT]
    procs = [process or None for process in procs]
    num_ops = sum(1 for process in procs if process)
    size_key = normalize_key(size)

    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, model_name, size
            FROM process_master
            WHERE LOWER(TRIM(model_name)) = LOWER(TRIM(%s))
            ORDER BY id
        """, (item_desc,))
        candidates = cursor.fetchall()

        match = None
        if candidates and size_key:
            for candidate in candidates:
                if normalize_key(candidate.get("size")) == size_key:
                    match = candidate
                    break
            if match is None:
                for candidate in candidates:
                    if not normalize_text(candidate.get("size")):
                        match = candidate
                        break
        elif candidates:
            for candidate in candidates:
                if not normalize_text(candidate.get("size")):
                    match = candidate
                    break
            if match is None:
                match = candidates[0]

        if match:
            cursor.execute(f"""
                UPDATE process_master
                SET model_name=%s, material=%s, part_name=%s, size=%s,
                    {PROCESS_ASSIGNMENTS_SQL},
                    num_operations=%s
                WHERE id=%s
            """, (item_desc, material, part_name, size, *procs, num_ops, match["id"]))
            conn.commit()
            return {
                "success": True,
                "action": "updated",
                "id": match["id"],
                "model_name": item_desc,
                "size": size,
                "num_operations": num_ops,
            }

        cursor.execute(f"""
            INSERT INTO process_master
            (model_name, material, part_name, size, {PROCESS_COLUMNS_SQL}, num_operations)
            VALUES (%s,%s,%s,%s,{PROCESS_PLACEHOLDERS_SQL},%s)
        """, (item_desc, material, part_name, size, *procs, num_ops))
        conn.commit()
        return {
            "success": True,
            "action": "inserted",
            "id": cursor.lastrowid,
            "model_name": item_desc,
            "size": size,
            "num_operations": num_ops,
        }
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


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
            delivery_dt = datetime.strptime(
                delivery_date[:10], "%Y-%m-%d").date()
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


def ensure_upload_review_context_columns(cursor):
    if not column_exists(cursor, "job_card_upload_reviews", "so_no"):
        cursor.execute("""
            ALTER TABLE job_card_upload_reviews
            ADD COLUMN so_no VARCHAR(50) NULL AFTER job_card_no
        """)

    if not column_exists(cursor, "job_card_upload_reviews", "customer_name"):
        cursor.execute("""
            ALTER TABLE job_card_upload_reviews
            ADD COLUMN customer_name VARCHAR(255) NULL AFTER so_no
        """)


def ensure_advance_stock_column(cursor):
    if not column_exists(cursor, "job_card_items", "advance_stock"):
        cursor.execute("""
            ALTER TABLE job_card_items
            ADD COLUMN advance_stock VARCHAR(100) AFTER job_card_qty
        """)


# JOB_CARD_PDF_CUTTING_SIZE_PERSIST_LOCAL_SYNC_V1
def ensure_cutting_size_column(cursor):
    """
    Persist Cutting Size extracted directly from the uploaded Job Card PDF.
    This is Job Card source data and is separate from Process Master / BOM.
    """
    if not column_exists(cursor, "job_card_items", "cutting_size"):
        cursor.execute("""
            ALTER TABLE job_card_items
            ADD COLUMN cutting_size VARCHAR(255) NULL
            AFTER length
        """)


def ensure_process_day_timeline_columns(cursor):
    for column, definition in [
        ("lead_date", "DATE NULL"),
        ("in_time", "DATETIME NULL"),
        ("out_time", "DATETIME NULL"),
        ("actual_days", "INT NULL"),
        ("end_date", "DATE NULL"),
        ("is_subcontract", "TINYINT(1) DEFAULT 0"),
        ("vendor_name", "VARCHAR(255) NULL"),
    ]:
        if not column_exists(cursor, "job_card_process_days", column):
            cursor.execute(
                f"ALTER TABLE job_card_process_days ADD COLUMN {column} {definition}")


def _process_day_payload(process_days):
    payload = {}
    for process_name, value in (process_days or {}).items():
        key = _sequence_process_key(process_name)
        if not key or key in payload:
            continue
        if isinstance(value, dict):
            submitted_days = safe_int(value.get("days"), 0)
            lead_date = value.get("lead_date") or None
        else:
            submitted_days = safe_int(value, 0)
            lead_date = None
        payload[key] = {
            "days": submitted_days,
            "lead_date": lead_date,
        }
    return payload


def insert_missing_process_day_rows(cursor, job_card_no, processes, process_days=None, job_card_date=None, use_as_is=False):
    """
    Creates correct process timeline order.

    Fix:
    - Removes wrong stages like M/c. No.
    - Rebuilds timeline in correct order if job card has not started/completed.
    - So CNC Machining replaces M/c. No. position instead of adding after Store.
    """

    ensure_process_day_timeline_columns(cursor)

    BAD_STAGE_KEYS = {
        "mcno",
        "mchno",
        "machineno",
        "shift",
        "operator",
        "date",
        "checkedby",
        "issueqty",
        "okqty",
        "okayqty",
        "rejqty",
        "rwqty",
        "r/wqty",
        "hrs",
        "remark",
        "remarks",
        "sign",
        "signature",
        "no",
        "process",
        "processdescription",
        "processdescritption",
        "subcontractor",
        "chnno",
        "specialtool",
        "inspectionstatus",
        "0",
        "000",
    }

    def is_bad_stage_name(value):
        value = normalize_text(value)
        key = normalize_key(value)

        if not value:
            return True

        if key in BAD_STAGE_KEYS:
            return True

        if value in (":", "::", "-", "_"):
            return True

        if re.fullmatch(r"\d+(?:\.\d+)?", value):
            return True

        bad_fragments = (
            "m/c. no",
            "machine no",
            "o.k. qty",
            "ok qty",
            "rej qty",
            "r/w qty",
            "process description",
            "process descritption",
            "inspection status",
        )

        return any(fragment in value.lower() for fragment in bad_fragments)

    def clean_processes_for_timeline(raw_processes):
        cleaned = []

        for process in raw_processes or []:
            process = normalize_text(process)

            if is_bad_stage_name(process):
                continue

            canonical = _canonical_process_name(process, allow_contains=False)

            if canonical:
                cleaned.append(canonical)
            else:
                cleaned.append(process)

        return _dedupe_processes(cleaned)

    def row_value(row, key, index):
        if isinstance(row, dict):
            return row.get(key)
        return row[index]

    if use_as_is:
        final_processes = [normalize_text(p) for p in (
            processes or []) if normalize_text(p)]
    else:
        cleaned_processes = clean_processes_for_timeline(processes)
        final_processes = build_final_process_sequence(cleaned_processes)

    if not final_processes:
        final_processes = build_final_process_sequence([])

    final_processes = [
        process for process in final_processes
        if not is_bad_stage_name(process)
    ]

    # REMOVE_ASSEMBLY_GLOBAL_V1
    final_processes = [
        process for process in final_processes
        if _sequence_process_key(process)
        != _sequence_process_key("Assembly")
    ]

        # TERMINAL_C_ROUTE_FILTER_START
    # All job-card creation/import paths pass through this function.
    # A -C item must finish after its last real manufacturing process.
    cursor.execute("""
        SELECT item_name
        FROM job_card_items
        WHERE job_card_no = %s
          AND COALESCE(is_deleted, 0) = 0
        ORDER BY id
        LIMIT 1
    """, (job_card_no,))

    timeline_item_row = cursor.fetchone()
    timeline_item_name = (
        row_value(timeline_item_row, "item_name", 0)
        if timeline_item_row
        else ""
    )

    compact_timeline_item_name = re.sub(
        r"\s+",
        "",
        str(timeline_item_name or "").upper()
    )

    if compact_timeline_item_name.endswith("-C"):
        # CHILD_C_NO_ASSEMBLY_STORE_V1
        # -C Job Cards finish after Quality Check.
        # Keep Quality Check in the route.
        # Assembly and Store must not exist as process rows.
        terminal_suffix_keys = {
            _sequence_process_key("Assembly"),
            _sequence_process_key("Store"),
        }

        final_processes = [
            process
            for process in final_processes
            if _sequence_process_key(process)
            not in terminal_suffix_keys
        ]
    # TERMINAL_C_ROUTE_FILTER_END

    cursor.execute("""
        SELECT id, process_name, COALESCE(is_completed, 0) AS is_completed
        FROM job_card_process_days
        WHERE job_card_no = %s
        ORDER BY id
    """, (job_card_no,))

    existing_rows = cursor.fetchall()

    has_completed_stage = any(
        safe_int(row_value(row, "is_completed", 2), 0) == 1
        for row in existing_rows
    )

    # If job card has not started, rebuild full timeline in correct order.
    # This is the important fix for M/c. No. issue.
    if not has_completed_stage:
        cursor.execute("""
            DELETE FROM job_card_process_days
            WHERE job_card_no = %s
        """, (job_card_no,))

        existing_rows = []

    else:
        # If job card already has completed stages, do not destroy completed history.
        # Only remove invalid pending stages like M/c. No.
        for row in existing_rows:
            row_id = row_value(row, "id", 0)
            process_name = row_value(row, "process_name", 1)
            is_completed = safe_int(row_value(row, "is_completed", 2), 0)

            if is_completed == 0 and is_bad_stage_name(process_name):
                cursor.execute("""
                    DELETE FROM job_card_process_days
                    WHERE id = %s
                """, (row_id,))

        cursor.execute("""
            SELECT id, process_name, COALESCE(is_completed, 0) AS is_completed
            FROM job_card_process_days
            WHERE job_card_no = %s
            ORDER BY id
        """, (job_card_no,))

        existing_rows = cursor.fetchall()

    cursor.execute(
        "SELECT process_name, default_days FROM process_default_days")
    default_days = {
        _sequence_process_key(row["process_name"] if isinstance(row, dict) else row[0]): (
            row["default_days"] if isinstance(row, dict) else row[1]
        )
        for row in cursor.fetchall()
    }

    submitted = _process_day_payload(process_days)

    existing_keys = {
        _sequence_process_key(row_value(row, "process_name", 1))
        for row in existing_rows
    }

    for idx, process_name in enumerate(final_processes):
        process_name = normalize_text(process_name)
        key = _sequence_process_key(process_name)

        if not process_name or not key:
            continue

        if key in existing_keys:
            continue

        submitted_value = submitted.get(key, {})
        days = default_days.get(key)

        if days is None:
            days = submitted_value.get("days", 0)

        lead_date = submitted_value.get("lead_date")
        is_first = idx == 0

        cursor.execute("""
            INSERT INTO job_card_process_days
            (job_card_no, process_name, days, lead_date, in_time, out_time,
             is_completed, actual_days, end_date)
            VALUES (
                %s, %s, %s, %s,
                CASE WHEN %s = 1 THEN NOW() ELSE NULL END,
                NULL, 0, NULL, NULL
            )
        """, (
            job_card_no,
            process_name,
            int(days or 0),
            lead_date,
            1 if (
                is_first
                and _initial_process_can_start_now(
                    cursor,
                    job_card_no
                )
            ) else 0,
        ))

        existing_keys.add(key)



# CHILD_C_INITIAL_CLOCK_GUARD_V1
def _initial_process_can_start_now(cursor, job_card_no):
    """
    Do not start the first process while an upper-level Job Card
    is blocked by an incomplete/not-found Child-C Job Card.

    Existing Continue Anyway overrides remain respected.
    """
    from routes.quality_check import (
        _get_pending_c_child_gate_rows,
        _child_c_gate_override_exists,
    )

    cursor.execute(
        """
        SELECT item_name
        FROM job_card_items
        WHERE job_card_no = %s
        ORDER BY id
        """,
        (job_card_no,),
    )

    rows = cursor.fetchall() or []

    if not rows:
        return True

    for row in rows:
        item_name = (
            row.get("item_name")
            if isinstance(row, dict)
            else row[0]
        )

        item_name = str(item_name or "").strip()

        if not item_name:
            continue

        pending_rows = _get_pending_c_child_gate_rows(
            cursor,
            job_card_no,
            item_name,
        )

        override_exists = _child_c_gate_override_exists(
            cursor,
            job_card_no,
            item_name,
        )

        if pending_rows and not override_exists:
            return False

    return True



def fetch_process_master_sequence_for_upload(cursor, item_name, size="", part=""):
    item_name = normalize_text(item_name)
    size = normalize_text(size)
    part = normalize_text(part)
    if not item_name:
        return []

    cursor.execute(
        f"""
        SELECT {PROCESS_COLUMNS_SQL}
        FROM process_master
        WHERE LOWER(TRIM(model_name)) = LOWER(TRIM(%s))
        ORDER BY
          CASE
            WHEN %s <> '' AND LOWER(TRIM(size)) = LOWER(TRIM(%s)) THEN 0
            WHEN %s <> '' AND LOWER(TRIM(part_name)) = LOWER(TRIM(%s)) THEN 1
            ELSE 2
          END,
          id
        LIMIT 1
        """,
        (item_name, size, size, part, part),
    )
    row = cursor.fetchone()
    if not row:
        return []
    if isinstance(row, dict):
        return [row.get(col) for col in PROCESS_COLUMNS if row.get(col)]
    return [value for value in row if value]


def _review_process_key(value):
    """Normalize process names for review comparison without removing duplicates."""
    return _sequence_process_key(normalize_text(value))


@job_cards_bp.route("/api/job_card/review/compare", methods=["POST"])
def review_compare_process_route():
    """
    Read-only comparison between uploaded processes and the approved
    normalized Process Master route.
    """
    conn = None
    cursor = None

    try:
        data = request.json or {}
        item_code = normalize_text(data.get("item_code"))
        uploaded_processes = data.get("uploaded_processes") or []

        if not item_code:
            return jsonify({
                "success": False,
                "status": "ITEM_CODE_REQUIRED",
                "error": "Item code is required."
            }), 400

        if not isinstance(uploaded_processes, list):
            return jsonify({
                "success": False,
                "status": "INVALID_PROCESS_LIST",
                "error": "uploaded_processes must be a list."
            }), 400

        uploaded_processes = [
            normalize_text(process)
            for process in uploaded_processes
            if normalize_text(process)
        ]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT item_code, item_description
            FROM items
            WHERE item_code = %s
            LIMIT 1
        """, (item_code,))
        item = cursor.fetchone()

        if not item:
            return jsonify({
                "success": True,
                "status": "NEW_ITEM_REVIEW_REQUIRED",
                "item_code": item_code,
                "import_allowed": False,
                "uploaded_processes": uploaded_processes,
                "master_processes": [],
                "message": "New item requires Process Master approval."
            })

        cursor.execute("""
            SELECT p.process_name
            FROM item_processes ip
            JOIN processes p ON p.id = ip.process_id
            WHERE ip.item_code = %s
            ORDER BY ip.step_no, ip.id
        """, (item_code,))
        master_processes = [
            row["process_name"] for row in cursor.fetchall()
        ]

        uploaded_keys = [_review_process_key(p) for p in uploaded_processes]
        master_keys = [_review_process_key(p) for p in master_processes]

        missing_processes = []
        extra_processes = []

        remaining_uploaded = list(uploaded_keys)
        for index, key in enumerate(master_keys):
            if key in remaining_uploaded:
                remaining_uploaded.remove(key)
            else:
                missing_processes.append(master_processes[index])

        remaining_master = list(master_keys)
        for index, key in enumerate(uploaded_keys):
            if key in remaining_master:
                remaining_master.remove(key)
            else:
                extra_processes.append(uploaded_processes[index])

        if uploaded_keys == master_keys:
            status = "MATCH"
            import_allowed = True
        elif missing_processes:
            status = "MISSING_PROCESS"
            import_allowed = False
        elif extra_processes:
            status = "EXTRA_PROCESS"
            import_allowed = False
        else:
            status = "ORDER_MISMATCH"
            import_allowed = False

        return jsonify({
            "success": True,
            "status": status,
            "item_code": item_code,
            "item_description": item.get("item_description"),
            "import_allowed": import_allowed,
            "uploaded_processes": uploaded_processes,
            "master_processes": master_processes,
            "missing_processes": missing_processes,
            "extra_processes": extra_processes,
            "message": (
                "Uploaded process route matches Process Master."
                if status == "MATCH"
                else "Uploaded process route requires review."
            )
        })

    except Exception as e:
        logger.exception("Process route comparison failed")
        return jsonify({
            "success": False,
            "status": "ERROR",
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@job_cards_bp.route("/api/job_card/review/update/<int:review_id>", methods=["POST"])
def update_upload_review_processes(review_id):
    """Update uploaded processes of one blocked review record."""
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}
        uploaded_processes = data.get("uploaded_processes")

        if not isinstance(uploaded_processes, list):
            return jsonify({
                "success": False,
                "status": "INVALID_PROCESSES",
                "error": "uploaded_processes must be a list."
            }), 400

        uploaded_processes = [
            normalize_text(process)
            for process in uploaded_processes
            if normalize_text(process)
        ]

        if not uploaded_processes:
            return jsonify({
                "success": False,
                "status": "INVALID_PROCESSES",
                "error": "At least one uploaded process is required."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id
            FROM job_card_upload_reviews
            WHERE id = %s
            LIMIT 1
        """, (review_id,))

        if not cursor.fetchone():
            return jsonify({
                "success": False,
                "status": "REVIEW_NOT_FOUND",
                "error": "Review record was not found."
            }), 404

        edited_by = (
            session.get("username")
            or session.get("full_name")
            or "System"
        )

        cursor.execute("""
            UPDATE job_card_upload_reviews
            SET uploaded_processes = %s,
                is_resolved = 0,
                review_decision = 'RECHECK_REQUIRED',
                review_remark = 'Uploaded process route was edited and requires recheck.',
                reviewed_by = %s,
                reviewed_at = NOW()
            WHERE id = %s
        """, (
            json.dumps(uploaded_processes),
            edited_by,
            review_id,
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "review_id": review_id,
            "uploaded_processes": uploaded_processes,
            "is_resolved": False,
            "message": "Uploaded processes updated. Recheck is required."
        })

    except Exception as e:
        if conn:
            conn.rollback()

        logger.exception("Upload review update failed")

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



@job_cards_bp.route("/api/job_card/review/create_process_master/<int:review_id>", methods=["POST"])
def create_review_item_in_process_master(review_id):
    """
    Create a reviewed new child item and its ordered process route
    in the normalized Process Master tables:
        items
        processes
        item_processes
    """
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        item_description = normalize_text(data.get("item_description"))
        material = normalize_text(data.get("material"))
        size = normalize_text(data.get("size"))
        part_name = normalize_text(data.get("part_name"))

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                bom_no,
                parent_code,
                child_code,
                item_name,
                uploaded_processes,
                review_status
            FROM job_card_upload_reviews
            WHERE id = %s
            LIMIT 1
        """, (review_id,))

        review = cursor.fetchone()

        if not review:
            return jsonify({
                "success": False,
                "status": "REVIEW_NOT_FOUND",
                "error": "Review record was not found."
            }), 404

        item_code = normalize_text(review.get("child_code"))

        if not item_code:
            return jsonify({
                "success": False,
                "status": "ITEM_CODE_REQUIRED",
                "error": "Child item code is missing."
            }), 400

        if not item_description:
            item_description = normalize_text(review.get("item_name"))

        if not item_description:
            return jsonify({
                "success": False,
                "status": "ITEM_DESCRIPTION_REQUIRED",
                "error": "Item description is required."
            }), 400

        uploaded_processes = review.get("uploaded_processes") or []

        if isinstance(uploaded_processes, str):
            try:
                uploaded_processes = json.loads(uploaded_processes)
            except Exception:
                uploaded_processes = []

        uploaded_processes = [
            normalize_text(process)
            for process in uploaded_processes
            if normalize_text(process)
        ]

        if not uploaded_processes:
            return jsonify({
                "success": False,
                "status": "PROCESS_ROUTE_REQUIRED",
                "error": "At least one reviewed process is required."
            }), 400

        cursor.execute("""
            SELECT item_code
            FROM items
            WHERE item_code = %s
            LIMIT 1
        """, (item_code,))

        if cursor.fetchone():
            return jsonify({
                "success": False,
                "status": "ITEM_ALREADY_EXISTS",
                "error": (
                    "This item already exists in Process Master. "
                    "Use the update option instead."
                )
            }), 409

        cursor.execute("""
            INSERT INTO items
            (
                item_code,
                item_description,
                item_type,
                make_default,
                material,
                size,
                part_name
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            item_code,
            item_description,
            "PART",
            1,
            material or None,
            size or None,
            part_name or None,
        ))

        process_ids = []

        for process_name in uploaded_processes:
            cursor.execute("""
                SELECT id
                FROM processes
                WHERE LOWER(TRIM(process_name)) = LOWER(TRIM(%s))
                LIMIT 1
            """, (process_name,))

            process_row = cursor.fetchone()

            if process_row:
                process_id = process_row["id"]
            else:
                cursor.execute("""
                    INSERT INTO processes (process_name)
                    VALUES (%s)
                """, (process_name,))
                process_id = cursor.lastrowid

            process_ids.append(process_id)

        cursor.execute("""
            DELETE FROM item_processes
            WHERE item_code = %s
        """, (item_code,))

        for step_no, process_id in enumerate(process_ids, start=1):
            cursor.execute("""
                INSERT INTO item_processes
                (
                    item_code,
                    process_id,
                    step_no
                )
                VALUES (%s, %s, %s)
            """, (
                item_code,
                process_id,
                step_no,
            ))

        # Create or update BOM ? Parent ? Child relationship.
        bom_no = normalize_text(review.get("bom_no"))
        parent_code = normalize_text(review.get("parent_code"))

        if bom_no and parent_code and item_code:
            cursor.execute("""
                INSERT INTO bom_links
                (
                    bom_no,
                    parent_code,
                    child_code,
                    quantity,
                    uom,
                    is_alternate
                )
                VALUES (%s, %s, %s, 1.000, 'NOS', 0)
                ON DUPLICATE KEY UPDATE
                    bom_no = VALUES(bom_no),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                bom_no,
                parent_code,
                item_code,
            ))

        reviewed_by = (
            session.get("username")
            or session.get("full_name")
            or "System"
        )

        cursor.execute("""
            UPDATE job_card_upload_reviews
            SET
                master_processes = %s,
                review_status = 'MATCH',
                review_decision = 'APPROVED',
                review_remark = (
                    'New item and reviewed process route created '
                    'in Process Master.'
                ),
                is_resolved = 1,
                reviewed_by = %s,
                reviewed_at = NOW()
            WHERE id = %s
        """, (
            json.dumps(uploaded_processes),
            reviewed_by,
            review_id,
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "status": "MATCH",
            "review_id": review_id,
            "item_code": item_code,
            "item_description": item_description,
            "processes": uploaded_processes,
            "process_count": len(uploaded_processes),
            "is_resolved": True,
            "message": (
                "New item and reviewed process route were created "
                "in Process Master."
            )
        })

    except Exception as e:
        if conn:
            conn.rollback()

        logger.exception(
            "Creating reviewed item in Process Master failed"
        )

        return jsonify({
            "success": False,
            "status": "ERROR",
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



@job_cards_bp.route(
    "/api/job_card/review/update_process_master/<int:review_id>",
    methods=["POST"]
)
def update_process_master_from_review(review_id):
    """
    Replace the normalized Process Master route using the reviewed
    uploaded route. Process Master identity is the child item code.
    """
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}
        submitted_processes = data.get("uploaded_processes")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                child_code,
                item_name,
                uploaded_processes
            FROM job_card_upload_reviews
            WHERE id = %s
            LIMIT 1
        """, (review_id,))

        review = cursor.fetchone()

        if not review:
            return jsonify({
                "success": False,
                "status": "REVIEW_NOT_FOUND",
                "error": "Review record was not found."
            }), 404

        item_code = normalize_text(review.get("child_code"))

        if not item_code:
            return jsonify({
                "success": False,
                "status": "ITEM_CODE_REQUIRED",
                "error": "Child item code is missing."
            }), 400

        cursor.execute("""
            SELECT item_code
            FROM items
            WHERE item_code = %s
            LIMIT 1
        """, (item_code,))

        if not cursor.fetchone():
            return jsonify({
                "success": False,
                "status": "ITEM_NOT_FOUND",
                "error": (
                    "Child item does not exist in Process Master. "
                    "Create it as a new item first."
                )
            }), 404

        if isinstance(submitted_processes, list):
            reviewed_processes = submitted_processes
        else:
            reviewed_processes = review.get("uploaded_processes") or []

            if isinstance(reviewed_processes, str):
                try:
                    reviewed_processes = json.loads(reviewed_processes)
                except Exception:
                    reviewed_processes = []

        reviewed_processes = [
            normalize_text(process)
            for process in reviewed_processes
            if normalize_text(process)
        ]

        if not reviewed_processes:
            return jsonify({
                "success": False,
                "status": "PROCESS_ROUTE_REQUIRED",
                "error": "At least one reviewed process is required."
            }), 400

        # First save the edited uploaded route in this review record.
        cursor.execute("""
            UPDATE job_card_upload_reviews
            SET uploaded_processes = %s
            WHERE id = %s
        """, (
            json.dumps(reviewed_processes),
            review_id,
        ))

        process_ids = []

        for process_name in reviewed_processes:
            cursor.execute("""
                SELECT id
                FROM processes
                WHERE LOWER(TRIM(process_name))
                    = LOWER(TRIM(%s))
                LIMIT 1
            """, (process_name,))

            process_row = cursor.fetchone()

            if process_row:
                process_id = process_row["id"]
            else:
                cursor.execute("""
                    INSERT INTO processes (process_name)
                    VALUES (%s)
                """, (process_name,))

                process_id = cursor.lastrowid

            process_ids.append(process_id)

        # Replace existing Process Master route for this Child Code.
        cursor.execute("""
            DELETE FROM item_processes
            WHERE item_code = %s
        """, (item_code,))

        for step_no, process_id in enumerate(process_ids, start=1):
            cursor.execute("""
                INSERT INTO item_processes
                (
                    item_code,
                    process_id,
                    step_no
                )
                VALUES (%s, %s, %s)
            """, (
                item_code,
                process_id,
                step_no,
            ))

        reviewed_by = (
            session.get("username")
            or session.get("full_name")
            or "System"
        )

        # All unresolved records for this Child Code with the same route
        # can now use the newly approved Process Master route.
        route_json = json.dumps(reviewed_processes)

        cursor.execute("""
            UPDATE job_card_upload_reviews
            SET
                master_processes = %s,
                review_status = 'MATCH',
                review_decision = 'APPROVED',
                review_remark = (
                    'Process Master route updated from reviewed '
                    'uploaded route.'
                ),
                is_resolved = 1,
                reviewed_by = %s,
                reviewed_at = NOW()
            WHERE child_code = %s
              AND uploaded_processes = %s
        """, (
            route_json,
            reviewed_by,
            item_code,
            route_json,
        ))

        # Ensure the selected record is approved even if JSON formatting
        # differed in older stored records.
        cursor.execute("""
            UPDATE job_card_upload_reviews
            SET
                uploaded_processes = %s,
                master_processes = %s,
                review_status = 'MATCH',
                review_decision = 'APPROVED',
                review_remark = (
                    'Process Master route updated from reviewed '
                    'uploaded route.'
                ),
                is_resolved = 1,
                reviewed_by = %s,
                reviewed_at = NOW()
            WHERE id = %s
        """, (
            route_json,
            route_json,
            reviewed_by,
            review_id,
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "status": "MATCH",
            "review_id": review_id,
            "item_code": item_code,
            "uploaded_processes": reviewed_processes,
            "master_processes": reviewed_processes,
            "is_resolved": True,
            "message": (
                "Process Master route updated successfully "
                f"for Child Code {item_code}."
            )
        })

    except Exception as error:
        if conn:
            conn.rollback()

        logger.exception(
            "Updating Process Master from review failed"
        )

        return jsonify({
            "success": False,
            "status": "ERROR",
            "error": str(error)
        }), 500

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()


@job_cards_bp.route("/api/job_card/review/recheck/<int:review_id>", methods=["POST"])
def recheck_upload_review(review_id):
    """Recompare one stored review record with the latest Process Master route."""
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT *
            FROM job_card_upload_reviews
            WHERE id = %s
            LIMIT 1
        """, (review_id,))
        review = cursor.fetchone()

        if not review:
            return jsonify({
                "success": False,
                "status": "REVIEW_NOT_FOUND",
                "error": "Review record was not found."
            }), 404

        item_code = normalize_text(review.get("child_code"))
        uploaded_processes = review.get("uploaded_processes") or []

        if isinstance(uploaded_processes, str):
            uploaded_processes = json.loads(uploaded_processes)

        cursor.execute("""
            SELECT item_code
            FROM items
            WHERE item_code = %s
            LIMIT 1
        """, (item_code,))
        item = cursor.fetchone()

        if not item:
            status = "NEW_ITEM_REVIEW_REQUIRED"
            master_processes = []
            message = "New item requires Process Master approval."

        else:
            cursor.execute("""
                SELECT p.process_name
                FROM item_processes ip
                JOIN processes p ON p.id = ip.process_id
                WHERE ip.item_code = %s
                ORDER BY ip.step_no, ip.id
            """, (item_code,))

            master_processes = [
                row["process_name"] for row in cursor.fetchall()
            ]

            uploaded_keys = [
                _review_process_key(process)
                for process in uploaded_processes
            ]
            master_keys = [
                _review_process_key(process)
                for process in master_processes
            ]

            remaining_uploaded = list(uploaded_keys)
            missing_processes = []

            for index, key in enumerate(master_keys):
                if key in remaining_uploaded:
                    remaining_uploaded.remove(key)
                else:
                    missing_processes.append(master_processes[index])

            remaining_master = list(master_keys)
            extra_processes = []

            for index, key in enumerate(uploaded_keys):
                if key in remaining_master:
                    remaining_master.remove(key)
                else:
                    extra_processes.append(uploaded_processes[index])

            if uploaded_keys == master_keys:
                status = "MATCH"
                message = "Uploaded process route matches Process Master."
            elif missing_processes:
                status = "MISSING_PROCESS"
                message = "Uploaded route is missing approved processes."
            elif extra_processes:
                status = "EXTRA_PROCESS"
                message = "Uploaded route contains extra processes."
            else:
                status = "ORDER_MISMATCH"
                message = "Uploaded and Process Master process order differs."

        is_resolved = 1 if status == "MATCH" else 0
        reviewed_by = (
            session.get("username")
            or session.get("full_name")
            or "System"
        )

        cursor.execute("""
            UPDATE job_card_upload_reviews
            SET master_processes = %s,
                review_status = %s,
                is_resolved = %s,
                review_decision = %s,
                review_remark = %s,
                reviewed_by = %s,
                reviewed_at = NOW()
            WHERE id = %s
        """, (
            json.dumps(master_processes),
            status,
            is_resolved,
            "APPROVED" if is_resolved else "RECHECK_REQUIRED",
            message,
            reviewed_by,
            review_id,
        ))

        conn.commit()

        return jsonify({
            "success": True,
            "review_id": review_id,
            "status": status,
            "is_resolved": bool(is_resolved),
            "uploaded_processes": uploaded_processes,
            "master_processes": master_processes,
            "message": message
        })

    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("Review recheck failed")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@job_cards_bp.route("/api/job_card/review/batch/<review_token>", methods=["GET"])
def get_upload_review_batch(review_token):
    """Read-only API to fetch stored review records for one upload batch."""
    conn = None
    cursor = None

    try:
        review_token = normalize_text(review_token)

        if not review_token:
            return jsonify({
                "success": False,
                "error": "Review token is required."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_upload_review_context_columns(cursor)
        conn.commit()

        cursor.execute("""
            SELECT
                id,
                review_token,
                job_card_no,
                so_no,
                customer_name,
                bom_no,
                parent_code,
                child_code,
                item_name,
                source_file,
                uploaded_processes,
                master_processes,
                review_status,
                review_decision,
                review_remark,
                is_resolved,
                reviewed_by,
                reviewed_at,
                created_at
            FROM job_card_upload_reviews
            WHERE review_token = %s
            ORDER BY id
        """, (review_token,))

        rows = cursor.fetchall()

        for row in rows:
            for field in ("uploaded_processes", "master_processes"):
                value = row.get(field)

                if isinstance(value, str):
                    try:
                        row[field] = json.loads(value)
                    except ValueError:
                        row[field] = []

            for field in ("reviewed_at", "created_at"):
                value = row.get(field)
                if value and hasattr(value, "strftime"):
                    row[field] = value.strftime("%Y-%m-%d %H:%M:%S")

        if not rows:
            return jsonify({
                "success": True,
                "status": "REVIEW_BATCH_NOT_FOUND",
                "review_token": review_token,
                "record_count": 0,
                "records": []
            })

        return jsonify({
            "success": True,
            "status": "REVIEW_BATCH_FOUND",
            "review_token": review_token,
            "record_count": len(rows),
            "records": rows
        })

    except Exception as e:
        logger.exception("Fetching upload review batch failed")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@job_cards_bp.route("/api/job_card/review/item/<item_code>", methods=["GET"])
def review_item_process_route(item_code):
    """
    Read-only review API.

    Fetches one item from the normalized Process Master tables together
    with its ordered process sequence. This endpoint does not insert or
    update any database record.
    """
    conn = None
    cursor = None

    try:
        item_code = normalize_text(item_code)

        if not item_code:
            return jsonify({
                "success": False,
                "status": "ITEM_CODE_REQUIRED",
                "error": "Item code is required."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                item_code,
                item_description,
                item_type,
                make_default,
                material,
                size,
                part_name
            FROM items
            WHERE item_code = %s
            LIMIT 1
        """, (item_code,))

        item = cursor.fetchone()

        if not item:
            return jsonify({
                "success": True,
                "status": "NEW_ITEM_REVIEW_REQUIRED",
                "item_code": item_code,
                "item": None,
                "processes": [],
                "process_count": 0,
                "import_allowed": False,
                "message": (
                    f"Item '{item_code}' is new and requires Process Master "
                    "review before job card import."
                )
            })

        cursor.execute("""
            SELECT
                ip.step_no,
                p.process_name
            FROM item_processes ip
            JOIN processes p
                ON p.id = ip.process_id
            WHERE ip.item_code = %s
            ORDER BY ip.step_no, ip.id
        """, (item_code,))

        processes = cursor.fetchall()

        status = "READY" if processes else "PROCESS_ROUTE_NOT_FOUND"

        return jsonify({
            "success": True,
            "status": status,
            "item_code": item_code,
            "item": item,
            "processes": processes,
            "process_count": len(processes),
            "message": (
                "Item and process route found."
                if processes
                else "Item exists, but no process route is configured."
            )
        })

    except Exception as e:
        logger.exception("Review item process route failed")
        return jsonify({
            "success": False,
            "status": "ERROR",
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


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
        search = search.replace("Ø", "Ø").replace("Ã?", "Ø")

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
        cursor.execute(
            "SELECT id, full_name AS name FROM users WHERE role = 'supervisor' ORDER BY full_name")
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
                "Drawing",
                total_days,
                remaining_days,
                delivery_date,
                remarks,
                int(item.get("is_priority", 0))
            ))
            logger.debug(f"Item {idx} inserted successfully")

        # Save individual process days (supports new {days, lead_date} dict format)
        process_days = data.get("process_days", {})
        bom_processes = data.get("bom_processes", [])
        process_sequence = bom_processes if bom_processes else list(
            process_days.keys())
        insert_missing_process_day_rows(
            cursor,
            job_card_no,
            process_sequence,
            process_days,
            job_card_date,
            use_as_is=bool(bom_processes),
        )
        process_days = {}
        for item in items:
            item["first_process"] = "Drawing"

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
                    f"Error inserting process {process_name}: {pe!s}")
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

        if (
            first_proc
            and column_exists(
                cursor,
                "job_card_process_days",
                "in_time"
            )
            and _initial_process_can_start_now(
                cursor,
                job_card_no
            )
        ):
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

# ── Bulk Create Job Cards (multi-child BOM flow) ──────────────────────────────


@job_cards_bp.route("/api/job_card/bulk_create", methods=["POST"])
def bulk_create_job_cards():
    """
    Creates multiple job cards in one shot from the multi-child BOM flow.
    Shared fields apply to all JCs; each row has its own job_card_no, child_code, qty.
    """
    conn = None
    cursor = None
    try:
        data = request.json or {}

        # ── Shared fields ─────────────────────────────────────────────────────
        so_no = (data.get("so_no") or "").strip()
        work_order_no = (data.get("work_order_no") or "").strip()
        parent_code = (data.get("parent_code") or "").strip()
        so_date = data.get("so_date") or None
        job_card_date = data.get("job_card_date") or None
        work_order_date = data.get("work_order_date") or None
        delivery_date = data.get("delivery_date") or None
        customer_name = (data.get("customer_name") or "").strip()
        remarks = (data.get("remarks") or "").strip()
        rows = data.get("rows", [])

        if not rows:
            return jsonify({"success": False, "error": "No rows provided"}), 400
        if not delivery_date:
            return jsonify({"success": False, "error": "Delivery date is required"}), 400

        remaining_days = remaining_days_from_delivery(delivery_date)

        conn = get_connection()
        cursor = conn.cursor()
        ensure_work_order_columns(cursor)
        ensure_advance_stock_column(cursor)

        if not column_exists(cursor, "job_card_items", "is_priority"):
            cursor.execute(
                "ALTER TABLE job_card_items ADD COLUMN is_priority TINYINT(1) DEFAULT 0")

        created = []
        errors = []

        for row in rows:
            job_card_no = str(row.get("job_card_no") or "").strip()
            child_code = (row.get("child_code") or "").strip()
            item_name = (row.get("item_name") or "").strip()
            qty = int(row.get("qty") or 0)
            material = (row.get("material") or "").strip() or None
            size = (row.get("size") or "").strip() or None

            if not job_card_no:
                errors.append(f"Child {child_code}: Job Card No is required")
                continue
            if not item_name:
                errors.append(f"JC {job_card_no}: Item name is missing")
                continue
            if qty <= 0:
                errors.append(
                    f"JC {job_card_no}: Quantity must be greater than 0")
                continue

            try:
                # Insert job_cards header
                cursor.execute("""
                    INSERT INTO job_cards
                    (job_card_no, so_no, customer_name, work_order_no, parent_code,
                     so_date, job_card_date, work_order_date, child_code, final_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (job_card_no, so_no, customer_name, work_order_no, parent_code,
                      so_date, job_card_date, work_order_date, child_code, "Pending"))

                # Insert job_card_items
                cursor.execute("""
                    INSERT INTO job_card_items
                    (job_card_no, item_name, material, so_qty, wip_status,
                     total_days, remaining_days, delivery_date, remarks, is_priority)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (job_card_no, item_name, material, qty,
                      "Drawing", 0, remaining_days, delivery_date, remarks, 0))

                # Build default process sequence
                default_processes = [
                    "Drawing", "Raw Material", "Quality Check", "Store"
                ]
                process_days = {}
                insert_missing_process_day_rows(
                    cursor, job_card_no, default_processes,
                    process_days, job_card_date, use_as_is=True
                )

                created.append(job_card_no)

            except Exception as row_err:
                errors.append(f"JC {job_card_no}: {row_err!s}")
                continue

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "success": True,
            "created": created,
            "created_count": len(created),
            "errors": errors,
            "message": f"{len(created)} job card(s) created successfully." +
                       (f" {len(errors)} failed." if errors else "")
                       })

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            try:
                cursor.close()
            except:
                pass
        if conn:
            try:
                conn.close()
            except:
                pass


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
                r["created_at"] = _to_ist(
                    r["created_at"]).strftime("%Y-%m-%d %H:%M")
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

def parse_job_card_detail_report_format(df, existing):
    raise NotImplementedError


def _upload_preview_job_cards_impl():
    import csv
    import io
    import math
    import os
    import re

    import pandas as pd  # type: ignore

    files = request.files.getlist("files") or request.files.getlist("file")
    files = [file for file in files if file and file.filename]
    if not files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    header_aliases = {
        "job_card_no": ["job card", "job_card", "job_card_no", "jc no", "job card no", "job card no."],
        "so_no": [
            "so no", "so no.", "s.o no", "s.o no.", "s.o. no", "s.o. no.",
            "so_no", "sale order no", "sales order no",
            "sales order", "sale order", "order no", "order number",
        ],
        "customer_name": ["customer name", "customer", "party name"],
        "parent_code": ["parent code", "parent_code", "fg code", "finished goods code", "parent item code"],
        "work_order_no": ["wo no", "wo no.", "work order no", "work_order_no", "work order number"],
        "so_date": ["so date", "so_date"],
        "job_card_date": ["job date", "job_card_date", "jc date", "job card date"],
        "child_code": ["child code", "child_code", "item code", "item_code"],
        "item_name": ["model", "item name", "item_name", "erpnext name", "item desc", "item description"],
        "size": ["size"],
        "material": ["material", "materail"],
        "so_qty": ["so qty", "so_qty", "qty", "quantity", "job quantity", "job qty"],
        "stock": ["stock"],
        "plan_qty": ["plan qty.", "plan qty", "plan_qty", "job card qty"],
        "part": ["part"],
        "dia": ["dia.", "dia"],
        "length": ["length"],
        "wip_status": ["wip status", "wip_status", "status"],
        "total_days": ["total days", "total_days"],
        "delivery_date": ["delivery date", "customer delivery date", "delivery_date"],
    }

    def clean(value):
        if value is None:
            return ""
        if isinstance(value, float) and math.isnan(value):
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass

        value = str(value).replace("\u00a0", " ").strip()
        value = re.sub(r"\s+", " ", value)

        if value.lower() in ("", "none", "nan", "nat", "-"):
            return ""
        if re.fullmatch(r"\d+\.0", value):
            return value[:-2]
        return value

    def clean_date(value):
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")

        value = clean(value)
        if not value:
            return ""

        for fmt in (
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d.%m.%Y",
            "%d-%b-%Y",
            "%d-%B-%Y",
        ):
            try:
                return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue

        try:
            parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
            if not pd.isna(parsed):
                return parsed.strftime("%Y-%m-%d")
        except Exception:
            pass

        return ""

    def normalize_header(value):
        value = clean(value).lower().replace("\u00a0", " ")
        value = re.sub(r"[_\s]+", " ", value)
        value = re.sub(r"\s*:\s*", ": ", value)
        return value.strip().rstrip(":")

    def read_csv_with_reader(raw_bytes):
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
            try:
                text = raw_bytes.decode(encoding)
                rows = list(csv.reader(io.StringIO(text)))
                return pd.DataFrame(rows, dtype=str).fillna("")
            except Exception as exc:
                last_error = exc
        raise ValueError(f"Could not read CSV file: {last_error}")

    def read_uploaded_file_to_dataframe(raw_bytes, uploaded_filename):
        ext = os.path.splitext(uploaded_filename)[1].lower()

        if ext in (".xlsx", ".xls"):
            return pd.read_excel(
                io.BytesIO(raw_bytes),
                sheet_name=0,
                header=0,
                dtype=str,
                keep_default_na=False,
            )

        if ext == ".csv":
            last_error = None
            for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
                try:
                    return pd.read_csv(
                        io.BytesIO(raw_bytes),
                        header=0,
                        dtype=str,
                        keep_default_na=False,
                        encoding=encoding,
                        sep=None,
                        engine="python",
                    )
                except Exception as exc:
                    last_error = exc

            logger.info(
                "Falling back to raw CSV reader after pandas failed: %s", last_error)
            return read_csv_with_reader(raw_bytes)

        raise ValueError(
            "Unsupported file type. Please upload .xlsx, .xls, or .csv.")

    def extract_regex(pattern, text):
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        return clean(match.group(1)) if match else ""

    def alias_set(key):
        return {normalize_header(alias) for alias in header_aliases[key]}

    def find_col(df, key):
        aliases = alias_set(key)
        for col in df.columns:
            if normalize_header(col) in aliases:
                return col
        return None

    def looks_like_label(value):
        normalized = normalize_header(value)
        if not normalized:
            return False

        all_aliases = set()
        for aliases in header_aliases.values():
            all_aliases.update(normalize_header(alias) for alias in aliases)

        extra_labels = {
            "job date",
            "wo no",
            "work order no",
            "bom no",
            "created by",
            "drg no",
            "drawing no",
            "rev",
            "rev.",
            "process descritption",
            "process description",
            "process",
            "item name",
            "witem name",
            "item desc",
            "witem desc",
            "item description",
            "witem description",
            "item code",
            "witem code",
            "material",
            "materail",
            "size",
            "qty",
            "quantity",
            "job quantity",
            "job qty",
            "page",
            "page no",
            "assembly",
            "assembly name",
        }

        return normalized in all_aliases or normalized in extra_labels or normalized.endswith(" no.")

    def is_real_value(value):
        value = clean(value)
        if not value or value in (":", "-", "::"):
            return False
        if looks_like_label(value):
            return False
        return True

    def is_code(value):
        value = clean(value)
        return bool(re.fullmatch(r"[A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*", value, flags=re.IGNORECASE))

    def is_date_value(value):
        value = clean(value)
        if not value:
            return False
        if re.fullmatch(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", value):
            return True
        if re.fullmatch(r"\d{1,2}-[A-Za-z]{3,9}-\d{2,4}", value):
            return True
        return False

    def is_number_value(value):
        value = clean(value)
        return bool(re.fullmatch(r"\d+(?:\.\d+)?", value))

    def is_bad_final_value(value):
        value = clean(value)
        if not value:
            return True
        if looks_like_label(value):
            return True

        bad_keys = {
            "wono",
            "workorderno",
            "itemname",
            "witemname",
            "itemdesc",
            "witemdesc",
            "itemdescription",
            "witemdescription",
            "material",
            "materail",
            "size",
            "process",
            "processdescription",
            "processdescritption",
            "jobcardno",
            "jobcard",
            "bomno",
            "drgno",
            "drawingno",
            "rev",
        }
        return normalize_key(value) in bad_keys

    def is_good_item_desc(value):
        value = clean(value)
        if is_bad_final_value(value):
            return False
        if is_code(value):
            return False
        if is_number_value(value):
            return False
        if is_date_value(value):
            return False

        value_lower = value.lower()
        bad_fragments = (
            "nmtg mechtrans",
            "job card",
            "against work order",
            "work order sub assembly",
            "process description",
            "process descritption",
            "page -",
            "page no",
        )
        if any(fragment in value_lower for fragment in bad_fragments):
            return False

        return True

    def next_real_value(cells, label_index, max_scan=12):
        for value in cells[label_index + 1: label_index + 1 + max_scan]:
            if is_real_value(value):
                return clean(value)
        return ""

    def find_label_value(flat_cells, label_aliases, max_scan=12):
        aliases = {normalize_header(alias) for alias in label_aliases}

        for idx, cell in enumerate(flat_cells):
            raw_cell = clean(cell)
            normalized = normalize_header(raw_cell)
            if not normalized:
                continue

            for alias in aliases:
                if normalized == alias or normalized.startswith(alias + " "):
                    inline = re.split(r"\s*:\s*", raw_cell, maxsplit=1)
                    if len(inline) == 2 and clean(inline[1]) and not looks_like_label(inline[1]):
                        return clean(inline[1])

                    return next_real_value(flat_cells, idx, max_scan=max_scan)

        return ""

    def common_preview_row(values, existing):
        job_card_no = clean(values.get("job_card_no"))
        so_qty = clean(values.get("so_qty"))
        plan_qty = clean(values.get("plan_qty")) or so_qty
        return {
            "job_card_no": job_card_no,
            "bom_no": clean(values.get("bom_no")),
            "so_no": clean(values.get("so_no")),
            "customer_name": clean(values.get("customer_name")),
            "parent_code": clean(values.get("parent_code")),
            "work_order_no": clean(values.get("work_order_no")),
            "so_date": clean_date(values.get("so_date")),
            "job_card_date": clean_date(values.get("job_card_date")),
            "child_code": clean(values.get("child_code")),
            "assembly_name": clean(values.get("assembly_name")),
            "item_name": clean(values.get("item_name")),
            "size": clean(values.get("size")),
            "material": clean(values.get("material")),
            "so_qty": so_qty,
            "stock": clean(values.get("stock")),
            "plan_qty": plan_qty,
            "part": clean(values.get("part")),
            "dia": clean(values.get("dia")),
            "length": clean(values.get("length")),
            "wip_status": clean(values.get("wip_status")) or "Pending",
            "total_days": clean(values.get("total_days")) or "0",
            "delivery_date": clean_date(values.get("delivery_date")),
            "is_duplicate": job_card_no in existing,
        }

    def flatten_dataframe(df):
        flat_cells = [clean(col) for col in df.columns]
        for _, row in df.iterrows():
            for value in row.tolist():
                flat_cells.append(clean(value))
        return [cell for cell in flat_cells if cell]

    def dataframe_to_rows(df):
        rows = [[clean(col) for col in df.columns]]
        for _, row in df.iterrows():
            rows.append([clean(value) for value in row.tolist()])
        return rows

    DYNAMIC_LABEL_ALIASES = {
        "job_card_no": ["job card no", "job card no.", "job card"],
        "so_no": [
            "so no", "so no.", "s.o no", "s.o no.", "s.o. no", "s.o. no.",
            "sales order no", "sale order no",
        ],
        "work_order_no": ["wo no", "wo no.", "work order no", "work order number"],
        "job_card_date": ["job date", "job card date", "date"],
        "child_code": ["child code", "item code", "item_code", "witem code", "w item code"],
        "item_name": [
            "witem desc", "witem description", "witem name",
            "w item desc", "w item description", "w item name",
            "item desc", "item description", "item name", "model",
        ],
        "size": ["size", "size:"],
        "material": ["material", "materail"],
        "qty": ["job quantity", "job qty", "qty", "quantity", "plan qty", "job card qty"],
        "process": ["process description", "process descritption", "process"],
    }
    DYNAMIC_LABEL_KEYS = {
        normalize_key(alias)
        for aliases in DYNAMIC_LABEL_ALIASES.values()
        for alias in aliases
    }
    SO_NO_RE = re.compile(r"\bS\d{3,}\b", re.IGNORECASE)
    WO_NO_RE = re.compile(r"\bW(?:O)?\d{5,}\b", re.IGNORECASE)
    JOB_CARD_LONG_RE = re.compile(r"\b0{3,}\d{4,}\b")
    JOB_CARD_SHORT_RE = re.compile(r"\b\d{1,6}\b")
    ITEM_CODE_RE = re.compile(
        r"\b[A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*\b", re.IGNORECASE)

    def build_flat_cells_from_rows(rows, max_cells=80000):
        flat_cells = []
        for row_idx, row in enumerate(rows or []):
            for col_idx, value in enumerate(row or []):
                value = clean(value)
                if not value:
                    continue
                flat_cells.append({
                    "index": len(flat_cells),
                    "row": row_idx,
                    "col": col_idx,
                    "value": value,
                    "key": normalize_key(value),
                })
                if len(flat_cells) >= max_cells:
                    logger.warning(
                        "Upload parser stopped flat-cell scan at %s cells", max_cells)
                    return flat_cells
        return flat_cells

    def build_flat_cells(df):
        return build_flat_cells_from_rows(dataframe_to_rows(df))

    def cell_text(cell):
        if isinstance(cell, dict):
            return clean(cell.get("value"))
        return clean(cell)

    def build_label_index(flat_cells):
        label_index = {}

        def add(label_key, idx):
            if not label_key:
                return
            positions = label_index.setdefault(label_key, [])
            if not positions or positions[-1] != idx:
                positions.append(idx)

        for idx, cell in enumerate(flat_cells):
            value = cell_text(cell)
            key = normalize_key(value)
            add(key, idx)

            if ":" in value:
                before_colon = value.split(":", 1)[0]
                add(normalize_key(before_colon), idx)

            for label_key in DYNAMIC_LABEL_KEYS:
                if key == label_key or (
                    key.startswith(label_key) and len(key) > len(label_key)
                ):
                    add(label_key, idx)

        return label_index

    def label_pattern(alias):
        tokens = re.findall(r"[A-Za-z0-9]+", alias)
        if not tokens:
            return ""
        return r"\s*".join(re.escape(token) + r"\.?" for token in tokens)

    def inline_value_for_alias(value, aliases):
        value = clean(value)
        if not value:
            return ""

        for alias in sorted(aliases, key=len, reverse=True):
            alias_key = normalize_key(alias)
            if ":" in value:
                left, right = value.split(":", 1)
                if normalize_key(left) == alias_key:
                    return clean(right)

            pattern = label_pattern(alias)
            if not pattern:
                continue
            stripped = re.sub(
                rf"^\s*{pattern}\s*[:\-]?\s*",
                "",
                value,
                count=1,
                flags=re.IGNORECASE,
            )
            if stripped != value and clean(stripped) and not looks_like_label(stripped):
                return clean(stripped)

        return ""

    def label_positions(label_index, aliases):
        positions = []
        seen = set()
        for alias in aliases:
            for idx in label_index.get(normalize_key(alias), []):
                if idx not in seen:
                    seen.add(idx)
                    positions.append(idx)
        return sorted(positions)

    def find_near_label(flat_cells, label_index, aliases, max_scan=30, validator=None):
        positions = label_positions(label_index, aliases)

        for idx in positions:
            label_cell = flat_cells[idx]
            inline = inline_value_for_alias(cell_text(label_cell), aliases)
            if inline and (validator is None or validator(inline)):
                return clean(inline)

            label_row = label_cell.get("row") if isinstance(
                label_cell, dict) else None
            label_col = label_cell.get("col") if isinstance(
                label_cell, dict) else None
            candidates = []

            if label_row is not None and label_col is not None:
                same_row = [
                    cell for cell in flat_cells
                    if cell.get("row") == label_row
                    and cell.get("col", -1) > label_col
                    and cell.get("col", -1) <= label_col + max_scan
                ]
                candidates.extend(same_row)

            candidates.extend(flat_cells[idx + 1: idx + 1 + max_scan])

            seen_candidate_indexes = set()
            for candidate_cell in candidates:
                candidate_idx = candidate_cell.get("index", id(candidate_cell))
                if candidate_idx in seen_candidate_indexes:
                    continue
                seen_candidate_indexes.add(candidate_idx)

                candidate = cell_text(candidate_cell)
                if not candidate or looks_like_label(candidate):
                    continue
                if candidate in (":", "::", "-", "_"):
                    continue
                if validator is None or validator(candidate):
                    return clean(candidate)

        return ""

    def find_first_regex(flat_cells, pattern, exclude_rules=None):
        regex = re.compile(pattern, re.IGNORECASE) if isinstance(
            pattern, str) else pattern
        exclude_rules = exclude_rules or []
        for cell in flat_cells:
            value = cell_text(cell)
            if not value:
                continue
            for match in regex.finditer(value):
                candidate = clean(match.group(
                    1) if match.groups() else match.group(0))
                if not candidate:
                    continue
                if any(rule(candidate) for rule in exclude_rules):
                    continue
                return candidate
        return ""

    def is_so_no_value(value):
        return bool(SO_NO_RE.fullmatch(clean(value)))

    def is_wo_no_value(value):
        return bool(WO_NO_RE.fullmatch(clean(value)))

    def is_job_card_no_value(value, allow_short=True):
        value = clean(value)
        if not value or is_date_value(value):
            return False
        if JOB_CARD_LONG_RE.fullmatch(value):
            return True
        return allow_short and bool(JOB_CARD_SHORT_RE.fullmatch(value))

    def normalize_so_no_value(value, allow_digits=False):
        value = clean(value).upper()
        match = SO_NO_RE.search(value)
        if match:
            return match.group(0).upper()
        if allow_digits and re.fullmatch(r"\d{3,}", value):
            return f"S{value}"
        return ""

    def normalize_wo_no_value(value, allow_digits=False):
        value = clean(value).upper()
        match = WO_NO_RE.search(value)
        if match:
            return match.group(0).upper()
        if allow_digits and re.fullmatch(r"\d{2,}", value):
            return f"WO{value}"
        return ""

    def is_child_code_candidate(value):
        value = clean(value)
        if not is_code(value):
            return False
        if is_so_no_value(value) or is_wo_no_value(value):
            return False
        if looks_like_label(value) or is_number_value(value):
            return False
        return True

    def is_size_like(value):
        value = clean(value)
        if not value:
            return False
        size_patterns = (
            r"\bM\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?\b",
            r"\b(?:[A-Za-z]\s*[xX]\s*)?\d+(?:[./]\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*[xX]\s*\d+(?:\.\d+)?)?\b",
        )
        return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in size_patterns)

    def is_size_only_text(value):
        value = clean(value)
        if not value:
            return False
        return bool(re.fullmatch(
            r"(?:size\s*:?\s*)?(?:M\d+(?:\.\d+)?|[A-Za-z]?\s*[xX]\s*)?\d+(?:[./]\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*[xX]\s*\d+(?:\.\d+)?)?",
            value,
            flags=re.IGNORECASE,
        ))

    def is_good_dynamic_item_name(value):
        value = clean(value)
        key = normalize_key(value)
        if key.startswith((
            "material",
            "materail",
            "size",
            "qty",
            "quantity",
            "jobquantity",
            "jobqty",
            "process",
            "wono",
            "workorderno",
            "sono",
        )):
            return False
        if not is_good_item_desc(value):
            return False
        if is_child_code_candidate(value) or is_so_no_value(value) or is_wo_no_value(value):
            return False
        if is_size_only_text(value):
            return False
        return True

    def clean_size_value(value):
        value = clean(value)
        if not value:
            return ""

        inline = inline_value_for_alias(value, DYNAMIC_LABEL_ALIASES["size"])
        if inline:
            value = inline

        value = re.split(
            r"\b(?:material|materail|forging|forging weight|hrc|hardness|weight|qty|quantity|process|job card)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        value = clean(value.rstrip(":-,;"))

        patterns = (
            r"(M\d+(?:\.\d+)?\s*[xX]\s*\d+(?:\.\d+)?)",
            r"((?:[A-Za-z]\s*[xX]\s*)?\d+(?:[./]\d+)?\s*[xX]\s*\d+(?:\.\d+)?(?:\s*[xX]\s*\d+(?:\.\d+)?)?)",
        )
        for pattern in patterns:
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match:
                return clean(match.group(1))[:100]

        return value[:100] if is_size_like(value) else ""

    def clean_material_value(value):
        value = clean(value)
        if not value:
            return ""

        inline = inline_value_for_alias(
            value, DYNAMIC_LABEL_ALIASES["material"])
        if inline:
            value = inline

        value = re.split(
            r"\b(?:size|forging|forging weight|hrc|hardness|weight|qty|quantity|process|job card)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        value = clean(value.rstrip(":-,;"))

        if not value or is_bad_final_value(value) or is_size_like(value):
            return ""
        return value[:100]

    def clean_qty_value(value):
        value = clean(value)
        if not value:
            return ""
        match = re.search(r"\b\d+(?:\.\d+)?\b", value)
        if not match:
            return ""
        return clean(match.group(0))

    def extract_job_card_no_dynamic(flat_cells, label_index):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["job_card_no"],
            max_scan=20,
            validator=lambda candidate: is_job_card_no_value(
                candidate, allow_short=True),
        )
        if value:
            match = JOB_CARD_LONG_RE.search(
                value) or JOB_CARD_SHORT_RE.search(value)
            return clean(match.group(0)) if match else clean(value)

        value = find_first_regex(flat_cells, JOB_CARD_LONG_RE)
        if value:
            return value

        return find_first_regex(
            flat_cells,
            JOB_CARD_SHORT_RE,
            exclude_rules=[is_so_no_value, is_wo_no_value,
                           is_date_value, looks_like_label],
        )

    def extract_so_no_dynamic(flat_cells, label_index):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["so_no"],
            max_scan=20,
            validator=lambda candidate: bool(
                normalize_so_no_value(candidate, allow_digits=True)),
        )
        if value:
            return normalize_so_no_value(value, allow_digits=True)
        return normalize_so_no_value(find_first_regex(flat_cells, SO_NO_RE))

    def extract_work_order_no_dynamic(flat_cells, label_index):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["work_order_no"],
            max_scan=20,
            validator=lambda candidate: bool(
                normalize_wo_no_value(candidate, allow_digits=True)),
        )
        if value:
            return normalize_wo_no_value(value, allow_digits=True)
        return normalize_wo_no_value(find_first_regex(flat_cells, WO_NO_RE))

    def extract_child_code_dynamic(flat_cells, label_index):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["child_code"],
            max_scan=30,
            validator=is_child_code_candidate,
        )
        if value:
            return clean(value)
        return find_first_regex(
            flat_cells,
            ITEM_CODE_RE,
            exclude_rules=[
                is_so_no_value,
                is_wo_no_value,
                is_number_value,
                looks_like_label,
            ],
        )

    def extract_item_name_dynamic(flat_cells, label_index):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["item_name"],
            max_scan=35,
            validator=is_good_dynamic_item_name,
        )
        if value:
            return clean(value)

        child_code = extract_child_code_dynamic(flat_cells, label_index)
        if child_code:
            child_positions = [
                idx for idx, cell in enumerate(flat_cells)
                if cell_text(cell) == child_code
            ]
            for idx in child_positions:
                for candidate_cell in flat_cells[idx + 1: idx + 35]:
                    candidate = cell_text(candidate_cell)
                    if is_good_dynamic_item_name(candidate):
                        return clean(candidate)

        return ""

    def extract_size_dynamic(flat_cells, label_index, item_name):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["size"],
            max_scan=20,
            validator=lambda candidate: bool(clean_size_value(candidate)),
        )
        size = clean_size_value(value)
        if size:
            return size

        item_name = clean(item_name)
        if "-" in item_name:
            size = clean_size_value(item_name.rsplit("-", 1)[-1])
            if size:
                return size

        size = clean_size_value(extract_size_from_item_desc(item_name))
        return size[:100]

    def extract_material_dynamic(flat_cells, label_index):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["material"],
            max_scan=20,
            validator=lambda candidate: bool(clean_material_value(candidate)),
        )
        if value:
            return clean_material_value(value)
        return ""

    def extract_qty_dynamic(flat_cells, label_index):
        value = find_near_label(
            flat_cells,
            label_index,
            DYNAMIC_LABEL_ALIASES["qty"],
            max_scan=16,
            validator=lambda candidate: bool(clean_qty_value(candidate)),
        )
        return clean_qty_value(value)

    def extract_processes_dynamic(rows_or_flat_cells):
        if not rows_or_flat_cells:
            return []
        first = rows_or_flat_cells[0]
        if isinstance(first, dict):
            rows_by_index = {}
            for cell in rows_or_flat_cells:
                rows_by_index.setdefault(cell.get("row", 0), []).append(cell)
            rows = []
            for row_idx in sorted(rows_by_index):
                row_cells = sorted(
                    rows_by_index[row_idx], key=lambda c: c.get("col", 0))
                rows.append([cell_text(cell) for cell in row_cells])
            return extract_processes_from_column_bm_or_raw(rows)
        return extract_processes_from_column_bm_or_raw(rows_or_flat_cells)

    def is_raw_job_card_print_layout(df):
        flat_cells = flatten_dataframe(df)
        text = "\n".join(flat_cells).lower()

        markers = [
            "job card",
            "against work order",
            "work order sub assembly",
            "wo no",
            "bom no",
            "witem desc",
            "witem name",
            "item desc",
            "item name",
            "process descritption",
            "process description",
        ]

        hit_count = sum(1 for marker in markers if marker in text)

        has_job_card_no = bool(
            re.search(r"job\s*card\s*no\.?", text, flags=re.IGNORECASE))
        has_print_layout_marker = (
            "against work order" in text
            or "work order sub assembly" in text
            or "bom no" in text
            or "wo no" in text
        )

        return has_job_card_no and (hit_count >= 3 or has_print_layout_marker)

    def parse_clean_table_format(df, existing):
        # Clean table parser.
        col_map = {key: find_col(df, key) for key in header_aliases}
        if not col_map["job_card_no"]:
            return []

        if is_raw_job_card_print_layout(df):
            has_real_table_row = False
            for _, row in df.iterrows():
                job_card_no = clean(row[col_map["job_card_no"]])
                item_name = clean(row[col_map["item_name"]]) if col_map.get(
                    "item_name") else ""
                if is_real_value(job_card_no) and is_good_item_desc(item_name):
                    has_real_table_row = True
                    break
            if not has_real_table_row:
                return []

        preview = []
        for _, row in df.iterrows():
            job_card_no = clean(row[col_map["job_card_no"]])
            if not is_real_value(job_card_no):
                continue

            values = {}
            for key, col in col_map.items():
                values[key] = row[col] if col else ""

            item_name = clean(values.get("item_name"))
            if is_bad_final_value(item_name):
                continue

            preview.append(common_preview_row(values, existing))

        return preview

    def sync_process_master_for_raw_job_card(df, preview_rows):
        flat_cells = flatten_dataframe(df)
        raw_rows = dataframe_to_rows(df)

        if not flat_cells:
            return None

        item_desc = ""
        if preview_rows:
            item_desc = clean(preview_rows[0].get("item_name"))

        if not item_desc:
            item_desc = extract_item_desc_from_raw_job_card(flat_cells)

        item_desc = normalize_text(item_desc)

        if not item_desc or is_bad_final_value(item_desc) or is_code(item_desc):
            logger.info(
                "Skipping process master sync: raw job card item_desc is invalid/blank")
            return None

        csv_processes = extract_processes_dynamic(raw_rows)
        if not csv_processes:
            logger.info(
                "Skipping process master sync for %s: no CSV processes found", item_desc)
            return None

        size = ""
        material = ""

        if preview_rows:
            size = clean(preview_rows[0].get("size"))
            material = clean(preview_rows[0].get("material"))

        if not size:
            size = extract_size_from_item_desc(item_desc)

        if is_bad_final_value(material):
            material = ""

        part_name = extract_part_name_from_item_desc(item_desc)
        if is_bad_final_value(part_name):
            part_name = ""

        final_processes = build_process_flow_from_csv(csv_processes)

        logger.info("Detected raw job card CSV process master sync")
        logger.info("item_desc=%s", item_desc)
        logger.info("extracted size=%s", size)
        logger.info("extracted part_name=%s", part_name)
        logger.info("csv_processes=%s", csv_processes)
        logger.info("final_processes=%s", final_processes)

        result = upsert_process_master_from_job_card_csv(
            item_desc=item_desc,
            size=size,
            material=material,
            part_name=part_name,
            final_processes=final_processes,
        )

        if result:
            logger.info(
                "%s process_master id=%s",
                result.get("action", "synced"),
                result.get("id"),
            )

            for row in preview_rows:
                row["item_name"] = item_desc
                if not clean(row.get("size")):
                    row["size"] = size
                if not clean(row.get("part")):
                    row["part"] = part_name
                if is_bad_final_value(row.get("material")):
                    row["material"] = ""
                row["wip_status"] = "Drawing"

        return result

    def find_item_code_and_name(segment):
        """
        ERP print-layout parser.

        Return:
        child_code = item code like NAOTR0000300
        item_name  = item desc like Outer Ring of N7139 - 50 x 78 x 30

        Never return labels like WO No, Item Name, Material.
        """
        cells = [clean(c) for c in segment]

        label_keys = {
            "itemname",
            "witemname",
            "itemdesc",
            "witemdesc",
            "itemdescription",
            "witemdescription",
        }

        for idx, cell in enumerate(cells):
            if _label_key(cell) not in label_keys:
                continue

            child_code = ""

            # First real code after item label is child code.
            for candidate in cells[idx + 1: idx + 20]:
                if is_code(candidate):
                    child_code = clean(candidate)
                    break

            # After child code, first descriptive value is item description.
            start_pos = idx + 1
            if child_code:
                for pos in range(idx + 1, min(idx + 30, len(cells))):
                    if clean(cells[pos]) == child_code:
                        start_pos = pos + 1
                        break

            item_name = ""
            for candidate in cells[start_pos: start_pos + 30]:
                if is_good_item_desc(candidate):
                    item_name = clean(candidate)
                    break

            if child_code or item_name:
                return child_code, item_name

        # Fallback helpers
        child_code = extract_child_code_from_raw_job_card(cells)
        item_name = extract_item_desc_from_raw_job_card(cells)

        if not is_code(child_code):
            child_code = ""

        if not is_good_item_desc(item_name):
            item_name = ""

        return child_code, item_name

    def parse_raw_job_card_print_format(df, existing, raw_bytes=None):
        """
        Pure regex parser for NMTG ERP print-layout job card CSVs.
        No position/column dependency — every field extracted from
        raw text using label+value patterns that work regardless of
        cell order or CSV column count.
        Uses raw_bytes directly to avoid pandas quote-handling issues.
        """

        # ── Build raw text from bytes directly if available ───────────
        # This avoids pandas mishandling of embedded quotes like 2.5""
        if raw_bytes:
            try:
                raw_text = raw_bytes.decode("utf-8", errors="ignore")
            except Exception:
                raw_text = raw_bytes.decode("latin-1", errors="ignore")
        else:
            # Fallback: flatten dataframe
            raw_cells = []
            for col in df.columns:
                raw_cells.append(str(col))
            for _, row in df.iterrows():
                for val in row.tolist():
                    raw_cells.append(str(val) if val is not None else "")
            raw_text = " ".join(raw_cells)

        # ── Normalise escaped quotes ("" → ") ─────────────────────────
        raw_text = raw_text.replace('""', '"')

        # ── Helper: find value after a label in raw text ──────────────
        def find_after_label(pattern, text, group=1):
            m = re.search(pattern, text, re.IGNORECASE)
            return clean(m.group(group)) if m else ""

        # ── Check this is NMTG ERP print layout ──────────────────────
        if "Job Card" not in raw_text:
            return []

        # ── Detect JC type ────────────────────────────────────────────
        jc_type_match = re.search(
            r'Job Card\s*\(\s*([^)]+)\)', raw_text, re.IGNORECASE)
        jc_type = clean(jc_type_match.group(1)) if jc_type_match else ""
        is_for_stock = "stock" in jc_type.lower()

        # ── Extract all JC numbers from file ─────────────────────────
        # Each unique JC No marks one job card record in the file
        jc_pattern = re.compile(
            r'Job Card No\.?\s*[^0-9]*(\d{4,12})', re.IGNORECASE)
        all_jc_matches = list(jc_pattern.finditer(raw_text))
        jc_nos = []
        seen_jc = set()
        for m in all_jc_matches:
            val = clean(m.group(1))
            if val and val not in seen_jc:
                seen_jc.add(val)
                jc_nos.append(val)

        if not jc_nos:
            return []

        # ── For multi-JC files, split raw_text at each JC boundary ───
        # Build segments: each segment covers one JC No occurrence
        boundaries = [m.start() for m in all_jc_matches
                      if clean(m.group(1)) in jc_nos]
        # Dedupe boundaries keeping first occurrence per JC
        seen_pos = {}
        unique_boundaries = []
        for m in all_jc_matches:
            val = clean(m.group(1))
            if val not in seen_pos:
                seen_pos[val] = m.start()
                unique_boundaries.append(m.start())

        segments = []
        for i, start in enumerate(unique_boundaries):
            end = unique_boundaries[i + 1] if i + 1 < len(unique_boundaries) else len(raw_text)
            segments.append((jc_nos[i], raw_text[start:end]))

        preview = []

        for jc_no, seg in segments:

            # ── WO No ─────────────────────────────────────────────────
            work_order_no = find_after_label(
                r'WO No\.?\s*[^W]*?(W[O]?\d{5,})', seg)

            # ── SO No ─────────────────────────────────────────────────
            so_no = find_after_label(
                r'SO No\.?\s*[^S]*?(S\d{3,})', seg)

            # ── Job date ──────────────────────────────────────────────
            job_date = find_after_label(
                r'Job Date\s*[^0-9]*(\d{1,2}/\d{1,2}/\d{4})', seg)
            job_date = clean_date(job_date)

            # ── Qty ───────────────────────────────────────────────────
            qty_raw = find_after_label(
                r'Job Quantity\s*[^0-9]*(\d+(?:\.\d+)?)', seg)
            qty = clean(qty_raw.split(".")[0]) if qty_raw else ""

            # ── Assembly name ─────────────────────────────────────────
            # Two layout variants:
            # Standard:        ...Job Quantity",":",<qty>,"<ASSEMBLY>"...
            # WO-before-WItem: ...WItem Desc",":  ","<ASSEMBLY>"...
            assembly = ""

            # Try WItem Desc label first (works for both variants)
            witem_match = re.search(
                r'WItem Desc["\s,:-]+([A-Z][^",]{4,100})',
                seg, re.IGNORECASE)
            if witem_match:
                candidate = clean(witem_match.group(1))
                if (candidate and
                    not re.match(r'^(WO|SO|BOM)\s*(No|Number)', candidate, re.IGNORECASE) and
                    not re.fullmatch(r'W[O]?\d+', candidate, re.IGNORECASE) and
                    len(candidate) > 4):
                    assembly = candidate

            # Fallback: after Job Quantity value (standard format)
            if not assembly:
                asm_match = re.search(
                    r'Job Quantity\s*[^0-9]*[\d.]+\s*,\s*"([^"]{5,100})"',
                    seg, re.IGNORECASE)
                if asm_match:
                    candidate = clean(asm_match.group(1))
                    if candidate and not re.match(
                            r'^(WO|SO|BOM)\s*(No|Number)', candidate, re.IGNORECASE):
                        assembly = candidate

            # Fallback: any MODEL: pattern anywhere in segment
            if not assembly:
                model_match = re.search(
                    r'"([A-Z][A-Z\s]+MODEL\s*:[^"]{3,60})"',
                    seg, re.IGNORECASE)
                if model_match:
                    assembly = clean(model_match.group(1))

            # ── Child code — from Item Name label ─────────────────────
            # Pattern: Item Name : <code>
            child_code = find_after_label(
                r'Item Name\s*[^A-Z]*([A-Z]{2,}[A-Z0-9]*\d+[A-Z0-9]*)', seg)

            # ── Item description — quoted string after child code ─────
            item_name = ""
            if child_code:
                # Find child code in segment, then get next quoted
                # descriptive string (5+ chars, has a space, not a label)
                after_code = seg[seg.find(child_code) + len(child_code):]
                # Find all quoted strings after child code
                quoted = re.findall(r'"([^"]{5,120})"', after_code)
                for candidate in quoted:
                    candidate = clean(candidate)
                    if not candidate:
                        continue
                    if is_bad_final_value(candidate):
                        continue
                    if is_code(candidate):
                        continue
                    if is_date_value(candidate):
                        continue
                    if is_number_value(candidate):
                        continue
                    if looks_like_label(candidate):
                        continue
                    # Must have at least one space (real description)
                    if " " not in candidate and "-" not in candidate:
                        continue
                    item_name = candidate
                    break

            # ── Size — always Size:value in same cell ─────────────────
            size = ""
            size_match = re.search(
                r'Size\s*:[\s"]*([^\s,"]{2,}(?:[\s][^\s,"]{1,})*)',
                seg, re.IGNORECASE)
            if size_match:
                size_raw = clean(size_match.group(1))
                # Strip trailing noise like thk TL etc but keep the dims
                size = re.sub(
                    r'\s+(thk|TL|thick|mm)$', '', size_raw,
                    flags=re.IGNORECASE).strip()
                size = size[:100]

            # ── Material ──────────────────────────────────────────────
            material = find_after_label(
                r'Mat(?:erial|erail)\s*[":,\s]+([A-Za-z0-9][A-Za-z0-9 ._/+-]{1,40})',
                seg)
            material = clean_material_value(material) if material else ""

            # ── Part name from item description ───────────────────────
            part_name = extract_part_name_from_item_desc(item_name)
            if is_bad_final_value(part_name):
                part_name = ""

            # ── Skip if no item name ──────────────────────────────────
            if not item_name:
                logger.warning(
                    "Skipping JC %s — item_name could not be extracted",
                    jc_no)
                continue

            # Extract BOM number from ERP print segment
            bom_no = ""
            bom_match = re.search(
                r'BOM\s*No\.?\s*[":,\s]+([A-Za-z0-9_-]+)',
                seg,
                re.IGNORECASE
            )
            if bom_match:
                bom_no = clean(bom_match.group(1))

            parent_code = ""

            if bom_no:
                lookup_conn = None
                lookup_cursor = None

                try:
                    lookup_conn = get_connection()
                    lookup_cursor = lookup_conn.cursor(dictionary=True)




                finally:
                    if lookup_cursor:
                        lookup_cursor.close()
                    if lookup_conn:
                        lookup_conn.close()

            preview.append(common_preview_row({
                "job_card_no":    jc_no,
                "bom_no":         bom_no,
                "parent_code":    parent_code,
                "so_no":          so_no,
                "work_order_no":  work_order_no,
                "so_date":        job_date,
                "job_card_date":  job_date,
                "child_code":     child_code,
                "item_name":      item_name,
                "assembly_name":  assembly,
                "size":           size,
                "material":       material,
                "so_qty":         qty,
                "stock":          "",
                "plan_qty":       qty,
                "part":           part_name,
                "dia":            "",
                "length":         "",
                "wip_status":     "Drawing",
                "total_days":     "0",
                "delivery_date":  "",
            }, existing))

        return preview

        job_indices = label_positions(
            label_index, ["job card no", "job card no."])  # noqa: F821
        if not job_indices:
            job_indices = label_positions(label_index, ["job card"])  # noqa: F821

        if not job_indices:
            if not is_raw_job_card_print_layout(df):
                return []
            job_indices = [0]

        preview = []
        seen_job_cards = set()
        raw_processes = extract_processes_dynamic(raw_rows)  # noqa: F821
        initial_wip_status = "Drawing" if raw_processes else "Pending"
        boundaries = job_indices + [len(flat_cells)]  # noqa: F821

        for pos, start in enumerate(job_indices):
            segment = flat_cells[start:boundaries[pos + 1]]  # noqa: F821
            segment_label_index = build_label_index(segment)

            job_card_no = extract_job_card_no_dynamic(
                segment, segment_label_index)

            if not job_card_no:
                continue

            if job_card_no in seen_job_cards:
                continue

            seen_job_cards.add(job_card_no)

            child_code = extract_child_code_dynamic(
                segment, segment_label_index)
            item_name = extract_item_name_dynamic(segment, segment_label_index)

            extracted_item_desc = extract_item_desc_from_raw_job_card(
                [cell_text(cell) for cell in segment])
            if extracted_item_desc and is_good_item_desc(extracted_item_desc):
                item_name = extracted_item_desc

            if is_bad_final_value(item_name) or is_code(item_name):
                item_name = ""

            job_date_value = find_near_label(
                segment,
                segment_label_index,
                DYNAMIC_LABEL_ALIASES["job_card_date"],
                max_scan=12,
                validator=lambda candidate: bool(clean_date(candidate)),
            )
            job_date = clean_date(job_date_value)
            work_order_no = extract_work_order_no_dynamic(
                segment, segment_label_index)

            # First search inside the Job Card segment.
            so_no = extract_so_no_dynamic(segment, segment_label_index)

            # ERP fallback:
            # SO No may appear before the "Job Card No" section, so it is
            # outside the segment. Search the complete uploaded file.
            if not so_no:
                so_no = extract_so_no_dynamic(flat_cells, label_index)  # noqa: F821

            so_qty = extract_qty_dynamic(segment, segment_label_index)
            size = extract_size_dynamic(
                segment, segment_label_index, item_name)
            material = extract_material_dynamic(segment, segment_label_index)
            part_name = extract_part_name_from_item_desc(item_name)

            if is_bad_final_value(part_name):
                part_name = ""

            final_size = size[:100]

            if not item_name:
                logger.warning(
                    "Skipping raw job card %s because item_name could not be extracted", job_card_no)
                continue

            preview.append(common_preview_row({
                "job_card_no": job_card_no,
                "so_no": so_no,
                "work_order_no": work_order_no,
                "so_date": job_date,
                "job_card_date": job_date,
                "child_code": child_code,
                "item_name": item_name,
                "size": final_size,
                "material": material,
                "so_qty": so_qty,
                "stock": "",
                "plan_qty": so_qty,
                "part": part_name,
                "dia": "",
                "length": "",
                "wip_status": initial_wip_status,
                "total_days": "0",
                "delivery_date": "",
                "uploaded_processes": list(raw_processes),
            }, existing))

        return preview

    def resolve_first_process_for_preview_rows(preview):
        if not preview:
            return preview

        conn = None
        cursor = None
        process_cache = {}

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            for row in preview:
                item_name = clean(row.get("item_name"))
                size = clean(row.get("size"))
                part = clean(row.get("part"))

                if not item_name:
                    row["wip_status"] = row.get("wip_status") or "Pending"
                    continue

                cache_key = (
                    item_name.lower(),
                    size.lower(),
                    part.lower(),
                )

                if cache_key in process_cache:
                    first_process = process_cache[cache_key]
                else:
                    item_like = f"%{item_name}%"

                    cursor.execute("""
                        SELECT p1
                        FROM process_master
                        WHERE LOWER(TRIM(model_name)) = LOWER(TRIM(%s))
                           OR LOWER(TRIM(model_name)) LIKE LOWER(TRIM(%s))
                           OR LOWER(TRIM(%s)) LIKE CONCAT('%', LOWER(TRIM(model_name)), '%')
                           OR (
                                %s <> ''
                                AND LOWER(TRIM(size)) = LOWER(TRIM(%s))
                                AND (
                                    %s = ''
                                    OR LOWER(TRIM(part_name)) = LOWER(TRIM(%s))
                                    OR LOWER(TRIM(%s)) LIKE CONCAT('%', LOWER(TRIM(part_name)), '%')
                                )
                           )
                        ORDER BY
                          CASE
                            WHEN LOWER(TRIM(model_name)) = LOWER(TRIM(%s)) THEN 1
                            WHEN LOWER(TRIM(%s)) LIKE CONCAT('%', LOWER(TRIM(model_name)), '%') THEN 2
                            WHEN %s <> '' AND LOWER(TRIM(size)) = LOWER(TRIM(%s)) THEN 3
                            ELSE 4
                          END
                        LIMIT 1
                    """, (
                        item_name,
                        item_like,
                        item_name,
                        size,
                        size,
                        part,
                        part,
                        part,
                        item_name,
                        item_name,
                        size,
                        size,
                    ))

                    match = cursor.fetchone()

                    if isinstance(match, dict):
                        first_process = clean(match.get("p1"))
                    elif match:
                        first_process = clean(match[0])
                    else:
                        first_process = ""

                    process_cache[cache_key] = first_process

                row["wip_status"] = first_process or "Pending"

        except Exception:
            logger.exception(
                "Failed to resolve first process for upload preview rows")
            for row in preview:
                row["wip_status"] = row.get("wip_status") or "Pending"

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

        return preview

    def normalize_so_key(value):
        key = normalize_key(value).upper()
        if key.startswith("S") and len(key) > 1 and key[1:].isdigit():
            return key[1:]
        return key

    def parse_so_mapping_rows(df):
        """
        Parse SO/customer-parent mapping file.

        Supports both:
        1) Clean table format:
           Customer | S.O No. | Parent Code | Parent Item Description | Size

        2) ERP print-layout format:
           Customer : T0047-The K.C.P. Ltd | S.O No. : S44239 | Item Code, Description & Drg No. ...
        """

        so_regex = re.compile(r"\bS\d{3,}\b", re.IGNORECASE)

        mapping_aliases = {
            "so_no": [
                "so no", "so no.", "s.o no", "s.o no.", "s.o. no", "s.o. no.",
                "so_no", "sale order no", "sales order no",
                "sales order", "sale order", "order no", "order number",
            ],
            "customer_name": [
                "customer name", "customer", "party name", "client name",
            ],
            "parent_code": [
                "parent code", "parent_code", "parent item code", "fg code",
                "finished goods code", "item code",
            ],
            "model": [
                "parent item description", "parent item desc", "model",
                "item description", "item desc", "item name", "description",
                "item code, description & drg no.",
                "item code description drg no",
            ],
            "size": ["size"],
        }

        def mapping_col(key):
            header_aliases_set = {normalize_header(
                alias) for alias in mapping_aliases[key]}
            key_aliases_set = {normalize_key(alias)
                               for alias in mapping_aliases[key]}

            for col in df.columns:
                col_header = normalize_header(col)
                col_key = normalize_key(col)

                if col_header in header_aliases_set:
                    return col

                if col_key in key_aliases_set:
                    return col

            return None

        def is_colon_or_blank(value):
            value = clean(value)
            return not value or value in (":", "::") or re.fullmatch(r":\.*\d*", value or "")

        def first_so_in_cells(cells):
            for cell in cells:
                match = so_regex.search(clean(cell))
                if match:
                    return match.group(0).upper()
            return ""

        def find_label_index(cells, label_keys):
            for idx, cell in enumerate(cells):
                if normalize_key(cell) in label_keys:
                    return idx
            return None

        def next_value_after_label(cells, label_idx, max_scan=10, so_only=False):
            if label_idx is None:
                return ""

            for candidate in cells[label_idx + 1: label_idx + 1 + max_scan]:
                candidate = clean(candidate)

                if is_colon_or_blank(candidate):
                    continue

                if so_only:
                    match = so_regex.search(candidate)
                    if match:
                        return match.group(0).upper()
                    continue

                return candidate

            return ""

        def extract_size_from_cells(cells):
            for cell in cells:
                cell = clean(cell)
                match = re.search(r"\bsize\s*:?\s*(.+)$",
                                  cell, flags=re.IGNORECASE)
                if match:
                    return clean(match.group(1))

            return ""

        def is_bad_mapping_desc(value):
            value = clean(value)
            key = normalize_key(value)

            if not value:
                return True

            if is_colon_or_blank(value):
                return True

            if so_regex.fullmatch(value):
                return True

            if is_code(value):
                return True

            if re.fullmatch(r"\d+(?:\.\d+)?", value):
                return True

            bad_keys = {
                "customer",
                "sono",
                "date",
                "status",
                "customerpono",
                "currency",
                "no",
                "uom",
                "quantity",
                "pendqty",
                "pending",
                "itemcodedescriptiondrgno",
                "nos",
                "drgno",
            }

            if key in bad_keys:
                return True

            return False

        def extract_parent_code_model_size_from_print_row(cells):
            item_label_idx = None

            possible_item_label_keys = {
                "itemcodedescriptiondrgno",
                "itemcode",
                "parentcode",
                "fgcode",
                "finishedgoodscode",
            }

            for idx, cell in enumerate(cells):
                if normalize_key(cell) in possible_item_label_keys:
                    item_label_idx = idx
                    break

            parent_code = ""
            model = ""
            size = extract_size_from_cells(cells)

            search_window = cells[item_label_idx + 1:item_label_idx +
                                  45] if item_label_idx is not None else cells

            for candidate in search_window:
                candidate = clean(candidate)

                if is_code(candidate) and not so_regex.fullmatch(candidate):
                    parent_code = candidate
                    break

            # Fallback for ERP item codes such as NFLCA0000379
            if not parent_code:
                for candidate in search_window:
                    candidate = clean(candidate).upper()

                    if re.fullmatch(r"N[A-Z0-9]{8,20}", candidate):
                        parent_code = candidate
                        break

            parent_found = False if parent_code else True

            for candidate in search_window:
                candidate = clean(candidate)

                if parent_code and candidate == parent_code:
                    parent_found = True
                    continue

                if not parent_found:
                    continue

                if not size:
                    size = extract_size_from_cells([candidate])

                if not model and not is_bad_mapping_desc(candidate):
                    model = candidate

                if model and size:
                    break

            return parent_code, model, size

        rows = []

        # 1) Clean table format support
        col_map = {key: mapping_col(key) for key in mapping_aliases}

        if col_map.get("so_no"):
            for _, row in df.iterrows():
                raw_so = clean(row[col_map["so_no"]]
                               ) if col_map["so_no"] else ""
                match = so_regex.search(raw_so)
                so_no = match.group(0).upper() if match else ""

                if not so_no:
                    continue

                customer_name = clean(row[col_map["customer_name"]]) if col_map.get(
                    "customer_name") else ""
                parent_code = clean(row[col_map["parent_code"]]) if col_map.get(
                    "parent_code") else ""
                model = clean(row[col_map["model"]]
                              ) if col_map.get("model") else ""
                size = clean(row[col_map["size"]]) if col_map.get(
                    "size") else ""

                # ERP print CSV read as a table:
                # the parent item code may appear under the combined
                # "Item Code, Description & Drg No." column.
                if not parent_code and is_code(model):
                    parent_code = model
                    model = ""

                rows.append({
                    "so_no": so_no,
                    "so_key": normalize_so_key(so_no),
                    "customer_name": customer_name,
                    "parent_code": parent_code,
                    "model": model,
                    "size": size,
                })

        # 2) ERP print-layout support
        # Include df.columns also because pandas treats first CSV row as header.
        raw_rows = [[clean(col) for col in df.columns]]
        for _, row in df.iterrows():
            raw_rows.append([clean(value) for value in row.tolist()])

        for cells in raw_rows:
            if not cells:
                continue

            text = " ".join(cells).lower()

            if "pending sales order details" not in text and "s.o no" not in text and "so no" not in text:
                continue

            customer_idx = find_label_index(cells, {"customer"})
            so_idx = find_label_index(cells, {"sono"})

            customer_name = next_value_after_label(
                cells, customer_idx, max_scan=6)
            so_no = next_value_after_label(
                cells, so_idx, max_scan=8, so_only=True)

            if not so_no:
                so_no = first_so_in_cells(cells)

            if not so_no:
                continue

            parent_code, model, size = extract_parent_code_model_size_from_print_row(
                cells)

            # Strong fallback: extract NMTG ERP item code from complete SO row
            if not parent_code:
                full_row_text = " ".join(clean(value) for value in cells).upper()
                code_match = re.search(
                    r"\bN[A-Z]{3,6}\d{6,10}\b",
                    full_row_text
                )
                if code_match:
                    parent_code = code_match.group(0)

            rows.append({
                "so_no": so_no,
                "so_key": normalize_so_key(so_no),
                "customer_name": customer_name,
                "parent_code": parent_code,
                "model": model,
                "size": size,
            })

        # Remove exact duplicate mapping rows
        deduped = []
        seen = set()

        for row in rows:
            key = (
                row.get("so_key", ""),
                row.get("customer_name", ""),
                row.get("parent_code", ""),
                row.get("model", ""),
                row.get("size", ""),
            )

            if key in seen:
                continue

            seen.add(key)
            deduped.append(row)

        return deduped

    def apply_so_mapping(preview_rows, mapping_rows):
        if not mapping_rows:
            # ── Fall back to DB ───────────────────────────────────────────────
            try:
                _db_conn = get_connection()
                _db_cursor = _db_conn.cursor(dictionary=True)
                _db_cursor.execute("""
                    SELECT so_no, so_key, customer_name, parent_code,
                           parent_item_desc AS model, size
                    FROM so_mapping_master
                    ORDER BY updated_at DESC
                """)
                db_rows = _db_cursor.fetchall()
                _db_cursor.close()
                _db_conn.close()
                if db_rows:
                    mapping_rows = [
                        {
                            "so_no":          r["so_no"],
                            "so_key":         r["so_key"],
                            "customer_name":  r["customer_name"] or "",
                            "parent_code":    r["parent_code"] or "",
                            "model":          r["model"] or "",
                            "size":           r["size"] or "",
                        }
                        for r in db_rows
                    ]
                    logger.info("Loaded %d SO mapping rows from DB",
                                len(mapping_rows))
            except Exception as db_exc:
                logger.exception(
                    "Failed to load SO mapping from DB: %s", db_exc)

        if not mapping_rows:
            for row in preview_rows:
                row["warning"] = ""
                if not clean(row.get("so_no")):
                    row["so_no"] = ""
                    row["customer_name"] = "Advance Plan"
                    row["parent_code"] = row.get("parent_code") or ""
                    row["match_status"] = "Advance Plan"
                else:
                    row["customer_name"] = row.get(
                        "customer_name") or "Advance Plan"
                    row["parent_code"] = row.get("parent_code") or ""
                    row["match_status"] = "No mapping file"
            return preview_rows

        mapping_by_so = {}
        for mapping_row in mapping_rows:
            so_key = mapping_row.get("so_key")
            if not so_key:
                continue
            mapping_by_so.setdefault(so_key, []).append(mapping_row)

        def mapping_score(preview_row, mapping_row):
            score = 0

            # Prefer mapping rows that contain a valid parent item code
            if clean(mapping_row.get("parent_code")):
                score += 10

            row_item_key = normalize_key(preview_row.get("item_name"))
            row_size_key = normalize_key(preview_row.get("size"))
            map_model_key = normalize_key(mapping_row.get("model"))
            map_size_key = normalize_key(mapping_row.get("size"))

            if row_size_key and map_size_key and row_size_key == map_size_key:
                score += 2
            if row_item_key and map_model_key:
                if row_item_key == map_model_key:
                    score += 4
                elif row_item_key in map_model_key or map_model_key in row_item_key:
                    score += 3

            return score

        for row in preview_rows:
            so_no = clean(row.get("so_no"))
            row["warning"] = ""

            if not so_no:
                row["so_no"] = ""
                row["customer_name"] = "Advance Plan"
                row["parent_code"] = ""
                row["match_status"] = "Advance Plan"
                continue

            candidates = mapping_by_so.get(normalize_so_key(so_no), [])
            if not candidates:
                row["customer_name"] = "Advance Plan"
                row["parent_code"] = ""
                row["match_status"] = "SO not found"
                row["warning"] = "SO not found in mapping file"
                continue

            if len(candidates) == 1:
                match = candidates[0]
                row["customer_name"] = match.get(
                    "customer_name") or row.get("customer_name") or ""
                row["parent_code"] = match.get("parent_code") or ""
                row["match_status"] = "Matched by SO"
                continue

            scored = sorted(
                ((mapping_score(row, candidate), candidate)
                 for candidate in candidates),
                key=lambda item: item[0],
                reverse=True,
            )
            best_score = scored[0][0]
            best_matches = [
                candidate for score, candidate in scored if score == best_score and score > 0]

            if len(best_matches) == 1:
                match = best_matches[0]
                row["customer_name"] = match.get(
                    "customer_name") or row.get("customer_name") or ""
                row["parent_code"] = match.get("parent_code") or ""
                row["match_status"] = "Matched by item/size"
                continue

            safe_customers = {
                candidate.get("customer_name")
                for candidate in candidates
                if candidate.get("customer_name")
            }
            row["customer_name"] = safe_customers.pop() if len(
                safe_customers) == 1 else "Advance Plan"
            row["parent_code"] = ""
            row["match_status"] = "Ambiguous SO"
            row["warning"] = "Multiple SO rows found; parent code needs review"

        return preview_rows

    # LOCAL_PDF_JOB_CARD_PARSER_V1
    def extract_pdf_job_card_text(raw_bytes):
        """
        Read text-based NMTG ERP Job Card PDFs.
        No OCR is used.
        """
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError(
                "PDF support requires pypdf."
            ) from exc

        try:
            reader = PdfReader(io.BytesIO(raw_bytes))
        except Exception as exc:
            raise ValueError(
                f"Could not read PDF file: {exc}"
            ) from exc

        page_texts = []

        for page in reader.pages:
            try:
                page_text = page.extract_text(
                    extraction_mode="layout"
                ) or ""
            except TypeError:
                page_text = page.extract_text() or ""

            if page_text.strip():
                page_texts.append(page_text)

        pdf_text = "\n".join(page_texts).strip()

        if not pdf_text:
            raise ValueError(
                "PDF contains no readable text. "
                "Image-only/scanned PDF is not supported."
            )

        return pdf_text


    def parse_pdf_job_card_format(raw_bytes, existing):
        """
        Parse NMTG ERP Job Card PDF into the existing LOCAL
        upload-review structure.

        Important:
        - Preview only.
        - Does not update Process Master.
        - uploaded_processes is passed to the existing review mechanism.
        """

        raw_text = extract_pdf_job_card_text(raw_bytes)

        if not re.search(
            r"\bJob\s+Card\b",
            raw_text,
            flags=re.IGNORECASE,
        ):
            return []

        jc_pattern = re.compile(
            r"Job\s*Card\s*No\.?\s*:?\s*(\d{4,12})",
            flags=re.IGNORECASE,
        )

        matches = list(jc_pattern.finditer(raw_text))

        if not matches:
            return []

        def first_match(pattern, source):
            match = re.search(
                pattern,
                source,
                flags=re.IGNORECASE | re.MULTILINE,
            )
            return clean(match.group(1)) if match else ""

        def clean_line(value):
            value = clean(value)
            return re.sub(r"\s{2,}", " ", value).strip()

        preview = []
        seen_jcs = set()

        for index, jc_match in enumerate(matches):
            job_card_no = clean(jc_match.group(1))

            if not job_card_no or job_card_no in seen_jcs:
                continue

            seen_jcs.add(job_card_no)

            segment_start = jc_match.start()
            segment_end = (
                matches[index + 1].start()
                if index + 1 < len(matches)
                else len(raw_text)
            )

            segment = raw_text[
                segment_start:segment_end
            ]

            # --------------------------------------------
            # Header
            # --------------------------------------------

            job_date_raw = first_match(
                r"Job\s*Date\s*:?\s*"
                r"(\d{1,2}/\d{1,2}/\d{4})",
                segment,
            )

            job_date = clean_date(job_date_raw)

            qty_raw = first_match(
                r"Job\s*Quantity\s*:?\s*"
                r"(\d+(?:\.\d+)?)",
                segment,
            )

            qty = clean_qty_value(qty_raw)

            so_no = first_match(
                r"SO\s*No\.?\s*:?\s*"
                r"(S\d{3,})",
                segment,
            ).upper()

            work_order_no = first_match(
                r"WO\s*No\.?\s*:?\s*"
                r"(W(?:O)?\d{5,})",
                segment,
            ).upper()

            created_by = clean_line(
                first_match(
                    r"Created\s*By\s*:?\s*([^\r\n]+)",
                    segment,
                )
            )

            assembly_name = clean_line(
                first_match(
                    r"WItem\s*Desc\s*:?\s*([^\r\n]+)",
                    segment,
                )
            )

            bom_no = first_match(
                r"BOM\s*No\.?\s*:?\s*"
                r"([A-Z0-9/-]+)",
                segment,
            )

            # --------------------------------------------
            # Item
            # --------------------------------------------

            child_code = first_match(
                r"Item\s*Name\s*:?\s*"
                r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)",
                segment,
            )

            item_name = ""

            item_match = re.search(
                r"Item\s*Name\s*:?\s*"
                r"[A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*"
                r"[^\r\n]*[\r\n]+"
                r"\s*([^\r\n]+)",
                segment,
                flags=re.IGNORECASE,
            )

            if item_match:
                candidate = clean_line(
                    item_match.group(1)
                )

                if is_good_dynamic_item_name(candidate):
                    item_name = candidate

            if not item_name and child_code:
                child_pos = segment.find(child_code)

                if child_pos >= 0:
                    after_child = segment[
                        child_pos + len(child_code):
                    ]

                    for source_line in after_child.splitlines():
                        candidate = clean_line(source_line)

                        if not candidate:
                            continue

                        if normalize_key(candidate).startswith(
                            "size"
                        ):
                            break

                        if is_good_dynamic_item_name(candidate):
                            item_name = candidate
                            break

            size = first_match(
                r"\bSIZE\s*:?\s*([^\r\n]+)",
                segment,
            )

            size = clean_size_value(size)

            part_name = extract_part_name_from_item_desc(
                item_name
            )

            if is_bad_final_value(part_name):
                part_name = ""

            # --------------------------------------------
            # Drawing
            # --------------------------------------------

            drawing_no = first_match(
                r"Drg\s*No\.?\s*:?\s*([^,\r\n]+)",
                segment,
            )

            drawing_rev = first_match(
                r"\bRev\.?\s*:?\s*"
                r"([A-Za-z0-9.-]+)",
                segment,
            )

            # --------------------------------------------
            # Item Details / Raw Material block
            # --------------------------------------------

            rm_block = ""

            rm_match = re.search(
                r"Raw\s*Material\s*\.*"
                r"(.*?)"
                r"(?:-+\s*Processes\s*-+|\Z)",
                segment,
                flags=re.IGNORECASE | re.DOTALL,
            )

            if rm_match:
                rm_block = rm_match.group(1)

            raw_material_code = ""
            raw_material_uom = ""
            raw_material_qty = ""
            raw_material_desc = ""
            cutting_size = ""

            rm_lines = [
                clean_line(line)
                for line in rm_block.splitlines()
                if clean_line(line)
            ]

            for line_index, line in enumerate(rm_lines):
                material_row = re.match(
                    r"^"
                    r"([A-Z]{2,}[A-Z0-9/-]*\d[A-Z0-9/-]*)"
                    r"\s+"
                    r"([A-Za-z.]+)"
                    r"\s+"
                    r"(\d+(?:\.\d+)?)"
                    r"$",
                    line,
                    flags=re.IGNORECASE,
                )

                if not material_row:
                    continue

                raw_material_code = clean(
                    material_row.group(1)
                )

                raw_material_uom = clean(
                    material_row.group(2)
                )

                raw_material_qty = clean(
                    material_row.group(3)
                )

                for description_line in rm_lines[
                    line_index + 1:
                    line_index + 5
                ]:
                    if re.search(
                        r"CUTTING\s*SIZE",
                        description_line,
                        flags=re.IGNORECASE,
                    ):
                        continue

                    if description_line:
                        raw_material_desc = (
                            description_line
                        )
                        break

                break

            cutting_size = first_match(
                r"CUTTING\s*SIZE\s*[-:]\s*"
                r"([^\r\n]+)",
                rm_block,
            )

            # Detect the special Item Details "-C" condition.
            pdf_item_details_has_child_c = bool(
                re.search(
                    r"-\s*C(?:\s|$|[,;])",
                    rm_block,
                    flags=re.IGNORECASE,
                )
            )

            # --------------------------------------------
            # ERP process route
            # --------------------------------------------

            uploaded_processes = []

            process_match = re.search(
                r"-+\s*Processes\s*-+"
                r"(.*?)"
                r"(?:"
                r"\n\s*No\.?\s*Process\s+"
                r"(?:Operator|M/c\.?|Sub)"
                r"|\Z"
                r")",
                segment,
                flags=re.IGNORECASE | re.DOTALL,
            )

            if process_match:
                process_block = process_match.group(1)

                for source_line in process_block.splitlines():
                    line = clean_line(source_line)

                    process_row = re.match(
                        r"^(\d+)\s+(.+?)$",
                        line,
                    )

                    if not process_row:
                        continue

                    candidate = clean_line(
                        process_row.group(2)
                    )

                    # Remove anything printed after the
                    # actual process name.
                    known = _canonical_process_name(
                        candidate,
                        allow_contains=True,
                    )

                    if known:
                        uploaded_processes.append(known)
                        continue

                    if (
                        candidate
                        and not looks_like_label(candidate)
                    ):
                        uploaded_processes.append(candidate)

            # Preserve genuine repeated operations.
            uploaded_processes = [
                normalize_text(process)
                for process in uploaded_processes
                if normalize_text(process)
            ]

            if not item_name:
                logger.warning(
                    "Skipping PDF JC %s because item "
                    "description could not be extracted",
                    job_card_no,
                )
                continue

            row = common_preview_row({
                "job_card_no": job_card_no,
                "bom_no": bom_no,
                "so_no": so_no,
                "customer_name": "",
                "parent_code": "",
                "work_order_no": work_order_no,
                "so_date": job_date,
                "job_card_date": job_date,
                "child_code": child_code,
                "assembly_name": assembly_name,
                "item_name": item_name,
                "size": size,
                "material": raw_material_desc,
                "so_qty": qty,
                "stock": "",
                "plan_qty": qty,
                "part": part_name,
                "dia": "",
                "length": "",
                "wip_status": "Drawing",
                "total_days": "0",
                "delivery_date": "",
            }, existing)

            row.update({
                "uploaded_processes":
                    list(uploaded_processes),

                "pdf_item_details_has_child_c":
                    pdf_item_details_has_child_c,

                "erp_created_by":
                    created_by,

                "drawing_no":
                    drawing_no,

                "drawing_rev":
                    drawing_rev,

                "raw_material_code":
                    raw_material_code,

                "raw_material_uom":
                    raw_material_uom,

                "raw_material_qty":
                    raw_material_qty,

                "cutting_size":
                    cutting_size,
            })

            preview.append(row)

        logger.info(
            "Parsed %s Job Card row(s) from PDF",
            len(preview),
        )

        return preview


    def parse_job_card_file(raw_bytes, uploaded_filename, existing):
        ext = os.path.splitext(uploaded_filename)[1].lower()

        # LOCAL_PDF_JOB_CARD_PARSER_V1
        if ext == ".pdf":
            preview = parse_pdf_job_card_format(
                raw_bytes,
                existing,
            )

            if not preview:
                raise ValueError(
                    f"{uploaded_filename}: "
                    "No readable NMTG Job Card found in PDF."
                )

            # Keep the existing LOCAL review mechanism.
            # Do not write/update Process Master here.
            process_master_sync = None

            preview = resolve_first_process_for_preview_rows(
                preview
            )

            for row in preview:
                row["source_file"] = uploaded_filename

                # The PDF parser already supplied the ERP
                # process route. Do not overwrite it.
                row["uploaded_processes"] = list(
                    row.get("uploaded_processes") or []
                )

            return preview, process_master_sync, None

        df = read_uploaded_file_to_dataframe(raw_bytes, uploaded_filename)

        if df.empty and len(df.columns) == 0:
            raise ValueError(f"{uploaded_filename}: File has no readable data")

        process_master_sync = None
        raw_sync_df = None
        preview = []

        preview = parse_clean_table_format(df, existing)
        if not preview:
            preview = parse_raw_job_card_print_format(df, existing, raw_bytes)
            if preview:
                raw_sync_df = df

        if not preview:
            preview = parse_job_card_detail_report_format(df, existing)

        # CSV fallback with raw reader
        if not preview and os.path.splitext(uploaded_filename)[1].lower() == ".csv":
            raw_df = read_csv_with_reader(raw_bytes)

            if is_raw_job_card_print_layout(raw_df):
                preview = parse_raw_job_card_print_format(raw_df, existing, raw_bytes)
                if preview:
                    raw_sync_df = raw_df
            else:
                preview = parse_raw_job_card_print_format(raw_df, existing, raw_bytes)
                if preview:
                    raw_sync_df = raw_df

            if not preview:
                preview = parse_job_card_detail_report_format(raw_df, existing)
                raw_sync_df = None

        # REVIEW_MECHANISM_STEP_1:
        # Upload preview must be read-only.
        # Do not insert or update Process Master while preparing preview.
        process_master_sync = None

        preview = resolve_first_process_for_preview_rows(preview)

        # REVIEW_MECHANISM:
        # Attach uploaded JC processes centrally so every parser branch
        # returns the same uploaded_processes field.
        uploaded_processes = []

        if raw_sync_df is not None:
            process_rows = (
                [list(raw_sync_df.columns)]
                + raw_sync_df.fillna("").values.tolist()
            )
            uploaded_processes = extract_processes_from_column_bm_or_raw(
                process_rows
            )

        for row in preview:
            row["source_file"] = uploaded_filename
            row["uploaded_processes"] = list(uploaded_processes)

        return preview, process_master_sync, df

    # Existing job cards
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT job_card_no FROM job_cards")
    existing = {clean(row["job_card_no"]) for row in cursor.fetchall()}
    cursor.close()
    conn.close()

    all_preview = []
    mapping_rows = []
    process_master_syncs = []
    file_errors = []

    for file in files:
        raw = file.read()
        filename = file.filename or "uploaded file"

        # ── Detect SO mapping file BEFORE attempting job card parse ──────────
        # 222-type files contain "Pending Sales Order Details" marker.
        # Parse them as mapping files immediately — do not attempt job card parse.
        try:
            _df_check = read_uploaded_file_to_dataframe(raw, filename)
            _flat_check = " ".join(
                [clean(col) for col in _df_check.columns] +
                [clean(v) for row in _df_check.head(5).values.tolist()
                 for v in row]
            ).lower()
            _is_so_file = (
                "pending sales order details" in _flat_check
                or (
                    ("s.o no" in _flat_check or "so no" in _flat_check)
                    and "customer" in _flat_check
                    and (
                        "item code" in _flat_check
                        or "parent code" in _flat_check
                    )
                    and "job card no" not in _flat_check
                    and "jobcard no" not in _flat_check
                )
            )
        except Exception:
            _is_so_file = False
            _df_check = None

        if _is_so_file:
            try:
                so_rows = parse_so_mapping_rows(_df_check)
                if so_rows:
                    mapping_rows.extend(so_rows)
                    # ── Upsert into so_mapping_master ─────────────────────────
                    try:
                        _map_conn = get_connection()
                        _map_cursor = _map_conn.cursor()
                        for sr in so_rows:
                            _map_cursor.execute("""
                                INSERT INTO so_mapping_master
                                    (so_no, so_key, customer_name, parent_code,
                                     parent_item_desc, size, source_file)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON DUPLICATE KEY UPDATE
                                    customer_name    = VALUES(customer_name),
                                    parent_code      = VALUES(parent_code),
                                    parent_item_desc = VALUES(parent_item_desc),
                                    size             = VALUES(size),
                                    source_file      = VALUES(source_file),
                                    updated_at       = NOW()
                            """, (
                                sr.get("so_no") or "",
                                sr.get("so_key") or "",
                                sr.get("customer_name") or "",
                                sr.get("parent_code") or "",
                                sr.get("model") or "",
                                (sr.get("size") or "")[:100],
                                filename,
                            ))
                        _map_conn.commit()
                        _map_cursor.close()
                        _map_conn.close()
                        logger.info("Upserted %d SO mapping rows from %s", len(
                            so_rows), filename)
                    except Exception as db_exc:
                        logger.exception(
                            "Failed to upsert SO mapping rows: %s", db_exc)
                        try:
                            _map_conn.rollback()
                            _map_cursor.close()
                            _map_conn.close()
                        except Exception:
                            pass
                else:
                    file_errors.append(
                        f"{filename}: Detected as SO mapping file but no SO rows found")
            except Exception as exc:
                file_errors.append(
                    f"{filename}: SO mapping parse failed: {exc}")
            continue
        # ── Normal job card file ──────────────────────────────────────────────
        try:
            file_preview, process_master_sync, df = parse_job_card_file(
                raw,
                filename,
                existing,
            )
        except Exception as exc:
            file_errors.append(f"{filename}: {exc}")
            continue

        if file_preview:
            # Reliable SO fallback for actual ERP Job Card files.
            # Customer Name and Parent Code are mapped only after SO is available.
            try:
                raw_text_for_so = raw.decode("utf-8", errors="ignore")

                so_match = re.search(
                    r'(?i)S\.?\s*O\.?\s*No\.?'
                    r'[\s\",:;-]*'
                    r'(S\d{3,})',
                    raw_text_for_so
                )

                if not so_match:
                    so_match = re.search(
                        r'\bS\d{3,}\b',
                        raw_text_for_so,
                        flags=re.IGNORECASE
                    )

                extracted_so = (
                    so_match.group(1)
                    if so_match and so_match.lastindex
                    else so_match.group(0)
                    if so_match
                    else ""
                )

                extracted_so = clean(extracted_so).upper()

                if extracted_so:
                    for preview_row in file_preview:
                        if not clean(preview_row.get("so_no")):
                            preview_row["so_no"] = extracted_so

            except Exception:
                logger.exception(
                    "SO fallback extraction failed for %s",
                    filename
                )

            all_preview.extend(file_preview)

            if process_master_sync:
                process_master_syncs.append({
                    "source_file": filename,
                    **process_master_sync,
                })

            continue

        so_rows = parse_so_mapping_rows(df)
        if so_rows:
            mapping_rows.extend(so_rows)
            continue

        file_errors.append(
            f"{filename}: No job card rows or SO mapping rows found")

    if not all_preview:
        if mapping_rows:
            return jsonify({
                "success": True,
                "so_mapping_only": True,
                "so_count": len(mapping_rows),
                "message": f"{len(mapping_rows)} SO records loaded successfully. You can now upload job cards.",
            }), 200
        detail = "; ".join(
            file_errors) if file_errors else "Please check the uploaded file."
        return jsonify({
            "success": False,
            "error": f"No job card numbers found. {detail}",
        }), 400

    all_preview = apply_so_mapping(all_preview, mapping_rows)




    # PARENT_FROM_BOM_CHILD_LOOKUP:

    # BOM + child_code uniquely identifies the immediate parent.

    parent_conn = None

    parent_cursor = None


    try:

        parent_conn = get_connection()

        parent_cursor = parent_conn.cursor(dictionary=True)


        for row in all_preview:

            bom_no = normalize_text(row.get("bom_no"))

            child_code = normalize_text(row.get("child_code"))


            if not bom_no or not child_code:

                continue


            parent_cursor.execute("""

                SELECT parent_code

                FROM bom_links

                WHERE bom_no = %s

                  AND child_code = %s

                LIMIT 1

            """, (bom_no, child_code))


            parent_row = parent_cursor.fetchone()


            if parent_row:

                row["parent_code"] = normalize_text(

                    parent_row.get("parent_code")

                )


    finally:

        if parent_cursor:

            parent_cursor.close()

        if parent_conn:

            parent_conn.close()

    # REVIEW_MECHANISM:
    # Compare every uploaded JC process route with normalized Process Master.
    review_conn = None
    review_cursor = None

    try:
        review_conn = get_connection()
        review_cursor = review_conn.cursor(dictionary=True)

        for row in all_preview:
            item_code = normalize_text(row.get("child_code"))
            uploaded_processes = [
                normalize_text(process)
                for process in (row.get("uploaded_processes") or [])
                if normalize_text(process)
            ]

            row["review_status"] = ""
            row["review_import_allowed"] = False
            row["master_processes"] = []
            row["missing_processes"] = []
            row["extra_processes"] = []

            # REUSE_PREVIOUS_APPROVAL:
            bom_no = normalize_text(row.get("bom_no"))
            parent_code = normalize_text(row.get("parent_code"))

            route_signature = __import__("hashlib").sha256(
                json.dumps(
                    [
                        _review_process_key(process)
                        for process in uploaded_processes
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            if bom_no and parent_code and item_code:
                review_cursor.execute("""
                    SELECT id
                    FROM job_card_upload_reviews
                    WHERE bom_no = %s
                      AND parent_code = %s
                      AND child_code = %s
                      AND route_signature = %s
                      AND is_resolved = 1
                      AND (
                          review_decision = 'APPROVED'
                          OR review_status = 'MATCH'
                      )
                    ORDER BY id DESC
                    LIMIT 1
                """, (
                    bom_no,
                    parent_code,
                    item_code,
                    route_signature,
                ))

                previous_approval = review_cursor.fetchone()

                if previous_approval:
                    row["review_status"] = "REUSED_APPROVAL"
                    row["review_import_allowed"] = True
                    row["review_message"] = (
                        "Previously approved BOM, parent, child and process route reused."
                    )
                    row["reused_review_id"] = previous_approval["id"]
                    continue

            if not item_code:
                row["review_status"] = "ITEM_CODE_REQUIRED"
                row["review_message"] = "Child item code is missing."
                continue

            review_cursor.execute("""
                SELECT item_code, item_description
                FROM items
                WHERE item_code = %s
                LIMIT 1
            """, (item_code,))
            review_item = review_cursor.fetchone()

            if not review_item:
                row["review_status"] = "NEW_ITEM_REVIEW_REQUIRED"
                row["review_message"] = (
                    "New item requires Process Master approval."
                )
                continue

            review_cursor.execute("""
                SELECT p.process_name
                FROM item_processes ip
                JOIN processes p ON p.id = ip.process_id
                WHERE ip.item_code = %s
                ORDER BY ip.step_no, ip.id
            """, (item_code,))

            master_processes = [
                process_row["process_name"]
                for process_row in review_cursor.fetchall()
            ]
            row["master_processes"] = master_processes

            if not master_processes:
                row["review_status"] = "PROCESS_ROUTE_NOT_FOUND"
                row["review_message"] = (
                    "Item exists, but no Process Master route is configured."
                )
                continue

            uploaded_keys = [
                _review_process_key(process)
                for process in uploaded_processes
            ]
            master_keys = [
                _review_process_key(process)
                for process in master_processes
            ]

            remaining_uploaded = list(uploaded_keys)
            missing_processes = []

            for index, key in enumerate(master_keys):
                if key in remaining_uploaded:
                    remaining_uploaded.remove(key)
                else:
                    missing_processes.append(master_processes[index])

            remaining_master = list(master_keys)
            extra_processes = []

            for index, key in enumerate(uploaded_keys):
                if key in remaining_master:
                    remaining_master.remove(key)
                else:
                    extra_processes.append(uploaded_processes[index])

            row["missing_processes"] = missing_processes
            row["extra_processes"] = extra_processes

            if uploaded_keys == master_keys:
                row["review_status"] = "MATCH"
                row["review_import_allowed"] = True
                row["review_message"] = (
                    "Uploaded process route matches Process Master."
                )
            elif missing_processes:
                row["review_status"] = "MISSING_PROCESS"
                row["review_message"] = (
                    "Uploaded process route is missing approved processes."
                )
            elif extra_processes:
                row["review_status"] = "EXTRA_PROCESS"
                row["review_message"] = (
                    "Uploaded process route contains extra processes."
                )
            else:
                row["review_status"] = "ORDER_MISMATCH"
                row["review_message"] = (
                    "Uploaded and Process Master process order differs."
                )

    finally:
        if review_cursor:
            review_cursor.close()
        if review_conn:
            review_conn.close()

    # ALREADY_IMPORTED_JOB_CARD_RULE:
    # Existing Job Card numbers are duplicates. They must not be reviewed again.
    for row in all_preview:
        if row.get("is_duplicate"):
            row["review_status"] = "DUPLICATE"
            row["review_message"] = (
                "Job Card already exists and does not require review again."
            )
            row["master_processes"] = row.get("master_processes") or []

    new_count = sum(1 for row in all_preview if not row["is_duplicate"])
    dup_count = sum(1 for row in all_preview if row["is_duplicate"])

    # REVIEW_MECHANISM:
    # Store preview review records using one token for this upload batch.
    review_token = uuid.uuid4().hex
    store_conn = None
    store_cursor = None

    try:
        store_conn = get_connection()
        store_cursor = store_conn.cursor()
        ensure_upload_review_context_columns(store_cursor)
        store_conn.commit()

        for row in all_preview:
            route_signature = __import__("hashlib").sha256(
                json.dumps(
                    [
                        _review_process_key(process)
                        for process in (row.get("uploaded_processes") or [])
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            store_cursor.execute("""
                INSERT INTO job_card_upload_reviews
                (
                    review_token,
                    job_card_no,
                    so_no,
                    customer_name,
                    bom_no,
                    parent_code,
                    child_code,
                    item_name,
                    source_file,
                    uploaded_processes,
                    master_processes,
                    route_signature,
                    review_status,
                    is_resolved
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, 0
                )
            """, (
                review_token,
                normalize_text(row.get("job_card_no")),
                normalize_text(row.get("so_no")) or None,
                normalize_text(row.get("customer_name")) or None,
                normalize_text(row.get("bom_no")) or None,
                normalize_text(row.get("parent_code")) or None,
                normalize_text(row.get("child_code")) or None,
                normalize_text(row.get("item_name")) or None,
                normalize_text(row.get("source_file")) or None,
                json.dumps(row.get("uploaded_processes") or []),
                json.dumps(row.get("master_processes") or []),
                route_signature,
                normalize_text(row.get("review_status")) or "REVIEW_REQUIRED",
            ))

        # AUTO_RESOLVE_MATCH_REVIEWS:
        # Exact Process Master matches require no manual review.
        store_cursor.execute("""
            UPDATE job_card_upload_reviews
            SET
                review_decision = 'APPROVED',
                is_resolved = 1,
                review_remark = (
                    'Uploaded process route matches Process Master.'
                ),
                reviewed_by = 'System',
                reviewed_at = NOW()
            WHERE review_token = %s
              AND review_status IN (
                  'MATCH',
                  'REUSED_APPROVAL',
                  'DUPLICATE'
              )
        """, (review_token,))

        store_conn.commit()

    except Exception:
        if store_conn:
            store_conn.rollback()
        raise

    finally:
        if store_cursor:
            store_cursor.close()
        if store_conn:
            store_conn.close()

    response = {
        "success": True,
        "review_token": review_token,
        "preview": all_preview,
        "new_count": new_count,
        "dup_count": dup_count,
    }

    if process_master_syncs:
        response["process_master_sync"] = process_master_syncs

    return jsonify(response)


@job_cards_bp.route("/api/job_card/upload_preview", methods=["POST"])
def upload_preview_job_cards():
    """Read uploaded job-card CSV/Excel files and return preview rows."""
    try:
        return _upload_preview_job_cards_impl()

    except Exception as e:
        logger.exception("Upload preview failed")
        return jsonify({"success": False, "error": str(e)}), 500


@job_cards_bp.route("/api/job_card/upload_confirm", methods=["POST"])
def upload_confirm_job_cards():
    """Save previewed job cards to database."""
    try:
        payload = request.json or {}
        rows = payload.get("rows", [])
        review_token = normalize_text(payload.get("review_token"))

        if not rows:
            return jsonify({"success": False, "error": "No data to save"}), 400

        if not review_token:
            return jsonify({
                "success": False,
                "status": "REVIEW_TOKEN_REQUIRED",
                "error": "A valid review token is required before import."
            }), 400

        # REVIEW_MECHANISM_TOKEN_VALIDATION:
        token_conn = None
        token_cursor = None

        try:
            token_conn = get_connection()
            token_cursor = token_conn.cursor(dictionary=True)

            token_cursor.execute("""
                SELECT COUNT(*) AS record_count
                FROM job_card_upload_reviews
                WHERE review_token = %s
            """, (review_token,))

            token_result = token_cursor.fetchone() or {}
            token_record_count = int(token_result.get("record_count") or 0)

            if token_record_count == 0:
                return jsonify({
                    "success": False,
                    "status": "INVALID_REVIEW_TOKEN",
                    "error": "The supplied review token was not found."
                }), 400

            token_mismatch_rows = []

            for row in rows:
                jc_no = normalize_text(row.get("job_card_no"))
                item_code = normalize_text(row.get("child_code"))

                token_cursor.execute("""
                    SELECT
                        id,
                        review_status,
                        is_resolved,
                        uploaded_processes
                    FROM job_card_upload_reviews
                    WHERE review_token = %s
                      AND job_card_no = %s
                      AND COALESCE(child_code, '') = %s
                    LIMIT 1
                """, (
                    review_token,
                    jc_no,
                    item_code
                ))

                token_review_row = token_cursor.fetchone()

                if not token_review_row:
                    token_mismatch_rows.append({
                        "job_card_no": jc_no,
                        "child_code": item_code
                    })
                    continue

                if int(token_review_row.get("is_resolved") or 0) != 1:
                    token_mismatch_rows.append({
                        "job_card_no": jc_no,
                        "child_code": item_code,
                        "review_status": normalize_text(
                            token_review_row.get("review_status")
                        ),
                        "reason": "REVIEW_NOT_RESOLVED"
                    })
                    continue

                submitted_processes = [
                    normalize_text(process)
                    for process in (row.get("uploaded_processes") or [])
                    if normalize_text(process)
                ]

                stored_processes_raw = token_review_row.get(
                    "uploaded_processes"
                )

                if isinstance(stored_processes_raw, str):
                    try:
                        stored_processes = json.loads(stored_processes_raw)
                    except Exception:
                        stored_processes = []
                elif isinstance(stored_processes_raw, list):
                    stored_processes = stored_processes_raw
                else:
                    stored_processes = []

                stored_processes = [
                    normalize_text(process)
                    for process in stored_processes
                    if normalize_text(process)
                ]

                if submitted_processes != stored_processes:
                    token_mismatch_rows.append({
                        "job_card_no": jc_no,
                        "child_code": item_code,
                        "reason": "REVIEWED_PROCESS_ROUTE_CHANGED"
                    })

            if token_mismatch_rows:
                unresolved_rows = [
                    row for row in token_mismatch_rows
                    if row.get("reason") == "REVIEW_NOT_RESOLVED"
                ]

                if unresolved_rows:
                    return jsonify({
                        "success": False,
                        "status": "REVIEW_NOT_RESOLVED",
                        "error": (
                            "One or more submitted rows are still "
                            "pending review resolution."
                        ),
                        "blocked_rows": unresolved_rows
                    }), 400

                changed_route_rows = [
                    row for row in token_mismatch_rows
                    if row.get("reason") == "REVIEWED_PROCESS_ROUTE_CHANGED"
                ]

                if changed_route_rows:
                    return jsonify({
                        "success": False,
                        "status": "REVIEWED_PROCESS_ROUTE_CHANGED",
                        "error": (
                            "One or more submitted process routes differ "
                            "from the reviewed routes."
                        ),
                        "blocked_rows": changed_route_rows
                    }), 400

                return jsonify({
                    "success": False,
                    "status": "REVIEW_TOKEN_ROW_MISMATCH",
                    "error": (
                        "One or more submitted rows do not belong "
                        "to the supplied review token."
                    ),
                    "mismatched_rows": token_mismatch_rows
                }), 400

        finally:
            if token_cursor is not None:
                token_cursor.close()
            if token_conn is not None:
                token_conn.close()

        # REVIEW_MECHANISM_IMPORT_GATE:
        # Revalidate every row directly against Process Master.
        # Never trust review_status or review_import_allowed sent by frontend.
        blocked_rows = []
        review_conn = None
        review_cursor = None

        try:
            review_conn = get_connection()
            review_cursor = review_conn.cursor(dictionary=True)

            for row in rows:
                jc_no = normalize_text(row.get("job_card_no"))
                item_code = normalize_text(row.get("child_code"))
                uploaded_processes = [
                    normalize_text(process)
                    for process in (row.get("uploaded_processes") or [])
                    if normalize_text(process)
                ]

                review_status = ""
                review_message = ""

                if not item_code:
                    review_status = "ITEM_CODE_REQUIRED"
                    review_message = "Child item code is missing."

                else:
                    review_cursor.execute("""
                        SELECT item_code
                        FROM items
                        WHERE item_code = %s
                        LIMIT 1
                    """, (item_code,))
                    review_item = review_cursor.fetchone()

                    if not review_item:
                        review_status = "NEW_ITEM_REVIEW_REQUIRED"
                        review_message = (
                            "New item requires Process Master approval."
                        )

                    else:
                        review_cursor.execute("""
                            SELECT p.process_name
                            FROM item_processes ip
                            JOIN processes p
                                ON p.id = ip.process_id
                            WHERE ip.item_code = %s
                            ORDER BY ip.step_no, ip.id
                        """, (item_code,))

                        master_processes = [
                            process_row["process_name"]
                            for process_row in review_cursor.fetchall()
                        ]

                        if not master_processes:
                            review_status = "PROCESS_ROUTE_NOT_FOUND"
                            review_message = (
                                "Item exists, but no Process Master route "
                                "is configured."
                            )

                        else:
                            uploaded_keys = [
                                _review_process_key(process)
                                for process in uploaded_processes
                            ]
                            master_keys = [
                                _review_process_key(process)
                                for process in master_processes
                            ]

                            remaining_uploaded = list(uploaded_keys)
                            missing_processes = []

                            for index, key in enumerate(master_keys):
                                if key in remaining_uploaded:
                                    remaining_uploaded.remove(key)
                                else:
                                    missing_processes.append(
                                        master_processes[index]
                                    )

                            remaining_master = list(master_keys)
                            extra_processes = []

                            for index, key in enumerate(uploaded_keys):
                                if key in remaining_master:
                                    remaining_master.remove(key)
                                else:
                                    extra_processes.append(
                                        uploaded_processes[index]
                                    )

                            if uploaded_keys == master_keys:
                                review_status = "MATCH"
                                review_message = (
                                    "Uploaded process route matches "
                                    "Process Master."
                                )
                            elif missing_processes:
                                review_status = "MISSING_PROCESS"
                                review_message = (
                                    "Uploaded route is missing: "
                                    + ", ".join(missing_processes)
                                )
                            elif extra_processes:
                                review_status = "EXTRA_PROCESS"
                                review_message = (
                                    "Uploaded route contains extra: "
                                    + ", ".join(extra_processes)
                                )
                            else:
                                review_status = "ORDER_MISMATCH"
                                review_message = (
                                    "Uploaded and Process Master process "
                                    "order differs."
                                )

                if review_status != "MATCH":
                    blocked_rows.append({
                        "job_card_no": jc_no,
                        "child_code": item_code,
                        "review_status": review_status,
                        "review_message": review_message,
                    })

        finally:
            if review_cursor:
                review_cursor.close()
            if review_conn:
                review_conn.close()

        if blocked_rows:
            return jsonify({
                "success": False,
                "status": "IMPORT_BLOCKED_BY_REVIEW",
                "error": (
                    f"{len(blocked_rows)} job card(s) require review "
                    "before import."
                ),
                "blocked_count": len(blocked_rows),
                "blocked_rows": blocked_rows,
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        ensure_work_order_columns(cursor)
        ensure_advance_stock_column(cursor)
        ensure_cutting_size_column(cursor)
        ensure_process_day_timeline_columns(cursor)
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
            job_card_date = r.get("job_card_date") or None
            customer_name = r.get("customer_name") or ""
            parent_code = r.get("parent_code") or ""
            work_order_no = r.get("work_order_no") or ""
            child_code = r.get("child_code") or ""
            size = r.get("size") or ""
            part = r.get("part") or ""
            dia = r.get("dia") or ""
            length = r.get("length") or ""

            # JOB_CARD_PDF_CUTTING_SIZE_PERSIST_LOCAL_SYNC_V1
            cutting_size = normalize_text(
                r.get("cutting_size")
            ) or None

            job_card_qty = safe_int(r.get("plan_qty"), default=None)

            try:
                if r.get("is_duplicate"):
                    cursor.execute("""
                        UPDATE job_cards
                        SET so_no=%s,
                            customer_name=%s,
                            work_order_no=%s,
                            parent_code=%s,
                            so_date=%s,
                            job_card_date=COALESCE(%s, job_card_date),
                            child_code=%s,
                            final_status='Pending'
                        WHERE job_card_no=%s
                    """, (
                        r.get("so_no"), customer_name, work_order_no, parent_code,
                        so_date, job_card_date, child_code, jc_no
                    ))
                    cursor.execute("""
                        UPDATE job_card_items
                        SET item_name=%s, material=%s, so_qty=%s, job_card_qty=%s,
                            wip_status=%s, total_days=%s, remaining_days=%s,
                            delivery_date=%s, advance_stock=%s,
                            size=%s, part=%s, dia=%s, length=%s,
                            cutting_size=%s
                        WHERE job_card_no=%s
                    """, (
                        r.get("item_name"), r.get("material"),
                        safe_int(r.get("so_qty")),
                        job_card_qty,
                        "Drawing",
                        safe_int(r.get("total_days")),
                        remaining_days,
                        delivery_date,
                        r.get("advance_stock") or None,
                        size, part, dia, length,
                        cutting_size,
                        jc_no
                    ))
                    updated += 1
                else:
                    cursor.execute("""
                        INSERT IGNORE INTO job_cards
                        (job_card_no, so_no, customer_name, work_order_no, parent_code,
                         so_date, job_card_date, child_code, assembly_name, final_status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending')
                    """, (
                        jc_no, r.get("so_no"), customer_name, work_order_no,
                        parent_code, so_date, job_card_date, child_code, r.get("assembly_name")
                    ))
                    cursor.execute("""
                        INSERT INTO job_card_items
                        (job_card_no,item_name,material,so_qty,job_card_qty,advance_stock,wip_status,
                         total_days,remaining_days,delivery_date,size,part,dia,length,cutting_size)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        jc_no, r.get("item_name"), r.get("material"),
                        safe_int(r.get("so_qty")),
                        job_card_qty,
                        r.get("advance_stock") or None,
                        "Drawing",
                        safe_int(r.get("total_days")),
                        remaining_days,
                        delivery_date,
                        size, part, dia, length,
                        cutting_size,
                    ))
                    inserted += 1

                # Load the approved Process Master route by child item code.
                cursor.execute("""
                    SELECT p.process_name
                    FROM item_processes ip
                    JOIN processes p
                      ON p.id = ip.process_id
                    WHERE ip.item_code = %s
                    ORDER BY ip.step_no, ip.id
                """, (child_code,))

                master_processes = [
                    row["process_name"] if isinstance(row, dict) else row[0]
                    for row in cursor.fetchall()
                    if (row["process_name"] if isinstance(row, dict) else row[0])
                ]
                insert_missing_process_day_rows(
                    cursor,
                    jc_no,
                    master_processes,
                    {},
                    job_card_date,
                )


                # ====================================================
                # CUTTING_PLAN_CREATE_ON_JC_UPLOAD_V1
                #
                # If this uploaded JC contains Cutting in its approved
                # Process Master route, immediately prepare its Draft
                # Cutting Plan.
                #
                # Raw Material movement is NOT required.
                # ====================================================

                has_cutting_process = any(
                    str(process_name or "").strip().lower()
                    == "cutting"
                    for process_name in master_processes
                )


                if has_cutting_process:

                    _cp_cursor = None

                    try:

                        from flask import session as _cp_session

                        from .cutting_plan import (
                            _resolve_auto_source,
                            _create_or_reuse_auto_plan,
                        )


                        _cp_cursor = conn.cursor(
                            dictionary=True
                        )


                        source, source_error = (
                            _resolve_auto_source(
                                _cp_cursor,
                                jc_no,
                                None,
                                None,
                            )
                        )


                        if source_error:

                            print(
                                "[CUTTING PLAN UPLOAD] "
                                f"JC {jc_no}: "
                                f"{source_error}"
                            )

                        elif source:

                            actor = {
                                "user_id":
                                    _cp_session.get(
                                        "user_id"
                                    ),

                                "name":
                                    (
                                        _cp_session.get(
                                            "full_name"
                                        )
                                        or
                                        _cp_session.get(
                                            "username"
                                        )
                                        or
                                        "Job Card Upload"
                                    ),
                            }


                            _create_or_reuse_auto_plan(
                                _cp_cursor,
                                source,
                                actor,
                            )


                            print(
                                "[CUTTING PLAN UPLOAD] "
                                f"Draft prepared for JC {jc_no}"
                            )


                    except Exception as cp_error:

                        print(
                            "[CUTTING PLAN UPLOAD] "
                            f"JC {jc_no} error: "
                            f"{cp_error}"
                        )


                    finally:

                        if _cp_cursor:

                            _cp_cursor.close()

                # CUTTING_PLAN_CREATE_ON_JC_UPLOAD_V1_END
            except Exception as e:
                print(f"[upload_confirm] Error for JC {jc_no}: {e}")
                errors += 1

        # REVIEW_IMPORT_COMPLETE:
        # Remove successfully imported rows from the review batch.
        # This permanently prevents the same reviewed records from being
        # imported again after refresh or by pressing Import repeatedly.
        imported_review_keys = [
            (
                normalize_text(row.get("job_card_no")),
                normalize_text(row.get("child_code"))
            )
            for row in rows
            if normalize_text(row.get("job_card_no"))
        ]

        for imported_jc_no, imported_child_code in imported_review_keys:
            cursor.execute("""
                DELETE FROM job_card_upload_reviews
                WHERE review_token = %s
                  AND job_card_no = %s
                  AND COALESCE(child_code, '') = %s
                  AND review_status IN ('MATCH', 'REUSED_APPROVAL')
                  AND is_resolved = 1
            """, (
                review_token,
                imported_jc_no,
                imported_child_code
            ))

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


@job_cards_bp.route("/api/so_mapping/status", methods=["GET"])
def get_so_mapping_status():
    """Returns last updated timestamp and count of SO mapping rows."""
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                COUNT(*) AS total_rows,
                MAX(updated_at) AS last_updated,
                MAX(source_file) AS last_file
            FROM so_mapping_master
        """)
        row = cursor.fetchone()
        if row and row["last_updated"]:
            ist = _to_ist(row["last_updated"])
            last_updated_str = ist.strftime("%d-%m-%Y %I:%M %p")
        else:
            last_updated_str = None
        return jsonify({
            "success": True,
            "total_rows": row["total_rows"] if row else 0,
            "last_updated": last_updated_str,
            "last_file": row["last_file"] if row else None,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ADVANCE_PLAN_SO_ALLOCATION_API_V1
# ============================================================
# Advance Plan -> SO / Customer split allocation
# ============================================================


def _advance_plan_item(cursor, item_id, for_update=False):
    sql = """
        SELECT
            id,
            job_card_no,
            item_name,
            size,
            part,
            so_qty,
            job_card_qty,
            advance_stock,
            wip_status
        FROM job_card_items
        WHERE id = %s
          AND (is_deleted IS NULL OR is_deleted = 0)
        LIMIT 1
    """

    if for_update:
        sql += " FOR UPDATE"

    cursor.execute(sql, (item_id,))
    return cursor.fetchone()


def _advance_plan_totals(cursor, item_id, total_qty):
    cursor.execute("""
        SELECT
            COALESCE(SUM(allocated_qty), 0) AS assigned_qty
        FROM advance_plan_so_allocations
        WHERE job_card_item_id = %s
          AND status = 'active'
    """, (item_id,))

    row = cursor.fetchone() or {}

    assigned_qty = int(row.get("assigned_qty") or 0)
    total_qty = int(total_qty or 0)
    remaining_qty = max(total_qty - assigned_qty, 0)

    if remaining_qty == 0 and total_qty > 0:
        allocation_status = "Fully Assigned"
    elif assigned_qty > 0:
        allocation_status = "Partially Assigned"
    else:
        allocation_status = "Unassigned"

    return {
        "total_qty": total_qty,
        "assigned_qty": assigned_qty,
        "remaining_qty": remaining_qty,
        "allocation_status": allocation_status,
    }


def _advance_plan_qty(value):
    try:
        qty = int(value)
    except (TypeError, ValueError):
        return None

    if qty <= 0:
        return None

    return qty



# ADVANCE_PLAN_CUSTOMER_MASTER_ID_V1
def _advance_plan_customer_master(cursor, customer_master_id):
    try:
        customer_master_id = int(customer_master_id)
    except (TypeError, ValueError):
        return None

    if customer_master_id <= 0:
        return None

    cursor.execute("""
        SELECT
            id,
            customer_code,
            customer_name,
            full_customer_text
        FROM customer_master
        WHERE id = %s
        LIMIT 1
    """, (customer_master_id,))

    customer = cursor.fetchone()

    if not customer:
        return None

    customer["canonical_name"] = (
        str(customer.get("full_customer_text") or "").strip()
        or str(customer.get("customer_name") or "").strip()
    )

    return customer


# ------------------------------------------------------------
# Customer autocomplete
# ------------------------------------------------------------

@job_cards_bp.route(
    "/api/advance-plan/customer-search",
    methods=["GET"]
)
def advance_plan_customer_search():
    conn = None
    cursor = None

    try:
        query = request.args.get("q", "").strip()

        if len(query) < 2:
            return jsonify([])

        like_query = f"%{query}%"
        starts_query = f"{query}%"

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                customer_code,
                customer_name,
                full_customer_text
            FROM customer_master
            WHERE customer_name LIKE %s
               OR customer_code LIKE %s
               OR full_customer_text LIKE %s
            ORDER BY
                CASE
                    WHEN customer_name LIKE %s THEN 0
                    WHEN customer_code LIKE %s THEN 1
                    ELSE 2
                END,
                customer_name
            LIMIT 15
        """, (
            like_query,
            like_query,
            like_query,
            starts_query,
            starts_query,
        ))

        return jsonify(cursor.fetchall())

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ------------------------------------------------------------
# Get allocations for one Advance Plan Job Card item
# ------------------------------------------------------------


@job_cards_bp.route(
    "/api/advance-plan/allocations/<int:item_id>",
    methods=["GET"]
)
def advance_plan_get_allocations(item_id):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        item = _advance_plan_item(
            cursor,
            item_id,
            False,
        )

        if not item:
            return jsonify({
                "success": False,
                "error": "Job Card item not found."
            }), 404

        total_qty = int(
            item.get("job_card_qty")
            or item.get("so_qty")
            or 0
        )

        totals = _advance_plan_totals(
            cursor,
            item_id,
            total_qty,
        )

        cursor.execute("""
            SELECT
                id,
                job_card_item_id,
                job_card_no,
                so_no,
                customer_master_id,
                customer_code,
                customer_name,
                allocated_qty,
                status,
                cancelled_at,
                created_at,
                updated_at
            FROM advance_plan_so_allocations
            WHERE job_card_item_id = %s
            ORDER BY
                CASE
                    WHEN status = 'active' THEN 0
                    ELSE 1
                END,
                id DESC
        """, (item_id,))

        allocations = cursor.fetchall() or []

        return jsonify({
            "success": True,
            "item": item,
            **totals,
            "allocations": allocations,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@job_cards_bp.route(
    "/api/advance-plan/allocations",
    methods=["POST"]
)
def advance_plan_create_allocation():
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        item_id = data.get("job_card_item_id")
        so_no = str(data.get("so_no") or "").strip()
        customer_master_id = data.get("customer_master_id")

        qty = _advance_plan_qty(
            data.get("allocated_qty")
        )

        if not item_id:
            return jsonify({
                "success": False,
                "error": "Job Card item is required."
            }), 400

        if not so_no:
            return jsonify({
                "success": False,
                "error": "SO No. is required."
            }), 400

        if not customer_master_id:
            return jsonify({
                "success": False,
                "error": (
                    "Please select a customer from Customer Master."
                )
            }), 400

        if qty is None:
            return jsonify({
                "success": False,
                "error": "Allocation Qty must be greater than 0."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        customer = _advance_plan_customer_master(
            cursor,
            customer_master_id,
        )

        if not customer:
            return jsonify({
                "success": False,
                "error": (
                    "Selected Customer Master record is invalid."
                )
            }), 400

        item = _advance_plan_item(
            cursor,
            item_id,
            True,
        )

        if not item:
            return jsonify({
                "success": False,
                "error": "Job Card item not found."
            }), 404

        total_qty = int(
            item.get("job_card_qty")
            or item.get("so_qty")
            or 0
        )

        totals = _advance_plan_totals(
            cursor,
            item_id,
            total_qty,
        )

        if qty > totals["remaining_qty"]:
            return jsonify({
                "success": False,
                "error": (
                    f"Only {totals['remaining_qty']} Qty "
                    "is available for allocation."
                )
            }), 400

        cursor.execute("""
            INSERT INTO advance_plan_so_allocations (
                job_card_item_id,
                job_card_no,
                so_no,
                customer_master_id,
                customer_code,
                customer_name,
                allocated_qty,
                status
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, 'active'
            )
        """, (
            item["id"],
            item["job_card_no"],
            so_no,
            customer["id"],
            customer["customer_code"],
            customer["canonical_name"],
            qty,
        ))

        allocation_id = cursor.lastrowid

        conn.commit()

        totals = _advance_plan_totals(
            cursor,
            item_id,
            total_qty,
        )

        return jsonify({
            "success": True,
            "allocation_id": allocation_id,
            "customer_master_id": customer["id"],
            "customer_code": customer["customer_code"],
            "customer_name": customer["canonical_name"],
            **totals,
        })

    except Exception as e:
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@job_cards_bp.route(
    "/api/advance-plan/allocations/<int:allocation_id>",
    methods=["PUT"]
)
def advance_plan_update_allocation(allocation_id):
    conn = None
    cursor = None

    try:
        data = request.get_json(silent=True) or {}

        so_no = str(data.get("so_no") or "").strip()
        customer_master_id = data.get("customer_master_id")

        qty = _advance_plan_qty(
            data.get("allocated_qty")
        )

        if not so_no:
            return jsonify({
                "success": False,
                "error": "SO No. is required."
            }), 400

        if not customer_master_id:
            return jsonify({
                "success": False,
                "error": (
                    "Please select a customer from Customer Master."
                )
            }), 400

        if qty is None:
            return jsonify({
                "success": False,
                "error": "Allocation Qty must be greater than 0."
            }), 400

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                job_card_item_id,
                job_card_no,
                allocated_qty,
                status
            FROM advance_plan_so_allocations
            WHERE id = %s
            LIMIT 1
            FOR UPDATE
        """, (allocation_id,))

        allocation = cursor.fetchone()

        if not allocation:
            return jsonify({
                "success": False,
                "error": "Allocation not found."
            }), 404

        if allocation["status"] != "active":
            return jsonify({
                "success": False,
                "error": "Cancelled allocation cannot be edited."
            }), 400

        customer = _advance_plan_customer_master(
            cursor,
            customer_master_id,
        )

        if not customer:
            return jsonify({
                "success": False,
                "error": (
                    "Selected Customer Master record is invalid."
                )
            }), 400

        item_id = allocation["job_card_item_id"]

        item = _advance_plan_item(
            cursor,
            item_id,
            True,
        )

        if not item:
            return jsonify({
                "success": False,
                "error": "Job Card item not found."
            }), 404

        total_qty = int(
            item.get("job_card_qty")
            or item.get("so_qty")
            or 0
        )

        totals = _advance_plan_totals(
            cursor,
            item_id,
            total_qty,
        )

        current_qty = int(
            allocation.get("allocated_qty") or 0
        )

        max_edit_qty = (
            totals["remaining_qty"]
            + current_qty
        )

        if qty > max_edit_qty:
            return jsonify({
                "success": False,
                "error": (
                    f"Maximum allowed Qty for this allocation "
                    f"is {max_edit_qty}."
                )
            }), 400

        cursor.execute("""
            UPDATE advance_plan_so_allocations
            SET
                so_no = %s,
                customer_master_id = %s,
                customer_code = %s,
                customer_name = %s,
                allocated_qty = %s
            WHERE id = %s
              AND status = 'active'
        """, (
            so_no,
            customer["id"],
            customer["customer_code"],
            customer["canonical_name"],
            qty,
            allocation_id,
        ))

        conn.commit()

        totals = _advance_plan_totals(
            cursor,
            item_id,
            total_qty,
        )

        return jsonify({
            "success": True,
            "allocation_id": allocation_id,
            "customer_master_id": customer["id"],
            "customer_code": customer["customer_code"],
            "customer_name": customer["canonical_name"],
            **totals,
        })

    except Exception as e:
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@job_cards_bp.route(
    "/api/advance-plan/allocations/<int:allocation_id>/cancel",
    methods=["POST"]
)
def advance_plan_cancel_allocation(allocation_id):
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                job_card_item_id,
                status
            FROM advance_plan_so_allocations
            WHERE id = %s
            LIMIT 1
        """, (allocation_id,))

        allocation = cursor.fetchone()

        if not allocation:
            conn.rollback()

            return jsonify({
                "success": False,
                "error": "Allocation not found."
            }), 404

        item_id = allocation["job_card_item_id"]

        item = _advance_plan_item(
            cursor,
            item_id,
            True,
        )

        if not item:
            conn.rollback()

            return jsonify({
                "success": False,
                "error": "Job Card item not found."
            }), 404

        if allocation["status"] == "cancelled":
            total_qty = int(
                item.get("job_card_qty")
                or item.get("so_qty")
                or 0
            )

            totals = _advance_plan_totals(
                cursor,
                item_id,
                total_qty,
            )

            conn.rollback()

            return jsonify({
                "success": True,
                "message": "Allocation is already cancelled.",
                **totals,
            })

        cursor.execute("""
            UPDATE advance_plan_so_allocations
            SET
                status = 'cancelled',
                cancelled_at = NOW()
            WHERE id = %s
              AND status = 'active'
        """, (allocation_id,))

        total_qty = int(
            item.get("job_card_qty")
            or item.get("so_qty")
            or 0
        )

        totals = _advance_plan_totals(
            cursor,
            item_id,
            total_qty,
        )

        conn.commit()

        return jsonify({
            "success": True,
            "message": "Allocation cancelled successfully.",
            **totals,
        })

    except Exception as e:
        if conn:
            conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

