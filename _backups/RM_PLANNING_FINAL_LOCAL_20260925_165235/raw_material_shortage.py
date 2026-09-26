import re
import time
from io import BytesIO
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, session, redirect, url_for, send_file, request

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

import xlrd

from db import get_connection
from permission_utils import is_gaurang_special_user


raw_material_shortage_bp = Blueprint(
    "raw_material_shortage",
    __name__,
)


# RAW_MATERIAL_SHORTAGE_BULK_V2


def _clean(value):
    return str(value or "").strip()


def _material_key(value):
    return re.sub(
        r"\s+",
        "",
        _clean(value).lower(),
    )


# RAW_MATERIAL_ERP_STOCK_NET_SHORTAGE_V1
def _stock_uom_key(value):
    value = _clean(value).lower().replace(".", "")

    if value in ("no", "nos", "number", "numbers"):
        return "no"

    if value in ("mm", "millimeter", "millimeters"):
        return "mm"

    return value

def _is_forging_ring(material):
    material = _clean(material).lower()

    return (
        "forged" in material
        and "ring" in material
    ) or (
        "forging" in material
        and "ring" in material
    )


def _number_from_cut_size(value):
    match = re.search(
        r"[0-9]+(?:\.[0-9]+)?",
        _clean(value),
    )

    if not match:
        return None

    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _decimal_qty(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _format_shortage_qty(value):
    try:
        value = Decimal(str(value or 0))
    except Exception:
        return str(value or "0")

    if value == value.to_integral():
        return f"{int(value):,}"

    formatted = f"{value:,.4f}"
    return formatted.rstrip("0").rstrip(".")



# RAW_MATERIAL_STOCK_UPLOAD_V1
def _parse_erp_stock_xls(file_bytes):
    if not file_bytes:
        raise ValueError("Uploaded ERP stock file is empty.")

    try:
        workbook = xlrd.open_workbook(
            file_contents=file_bytes
        )
    except Exception as exc:
        raise ValueError(
            "Unable to read ERP .xls file."
        ) from exc

    if workbook.nsheets <= 0:
        raise ValueError(
            "ERP stock file contains no worksheet."
        )

    sheet = workbook.sheet_by_index(0)

    parsed_rows = []
    item_codes = set()
    layout_found = False

    for row_index in range(sheet.nrows):
        values = sheet.row_values(row_index)

        if len(values) < 21:
            continue

        # ERP repeats these labels on every actual data row.
        if (
            _clean(values[3]).lower() == "itemcode"
            and _clean(values[4]).lower() == "item details"
            and _clean(values[5]).lower() == "uom"
            and _clean(values[6]).lower() == "current stock"
        ):
            layout_found = True

        item_category = _clean(values[11])
        item_group = _clean(values[14])

        item_code = _clean(values[15])
        item_details = _clean(values[16])
        uom = _clean(values[17])

        current_stock = _decimal_qty(values[18])
        rate = _decimal_qty(values[19])
        stock_value = _decimal_qty(values[20])

        if item_category.lower() != "raw materials":
            continue

        if not item_code or not item_details:
            continue

        if item_code in item_codes:
            raise ValueError(
                f"Duplicate ERP ItemCode found: {item_code}"
            )

        item_codes.add(item_code)

        parsed_rows.append({
            "item_code": item_code,
            "item_details": item_details,
            "uom": uom,
            "current_stock": current_stock,
            "rate": rate,
            "stock_value": stock_value,
            "item_category": item_category,
            "item_group": item_group,
        })

    if not layout_found:
        raise ValueError(
            "ERP stock layout was not recognized."
        )

    if not parsed_rows:
        raise ValueError(
            "No Raw Materials stock rows were found."
        )

    return parsed_rows


def _load_active_stock_upload():
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                id,
                original_filename,
                uploaded_by_user_id,
                uploaded_by_name,
                uploaded_at,
                row_count
            FROM raw_material_stock_uploads
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
        """)

        return cursor.fetchone()

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

def _load_raw_material_shortage(cutting_rows=None):
    started = time.perf_counter()

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # ------------------------------------------------------------
        # 1. Fetch current Raw Material-pending JCs ONCE
        # ------------------------------------------------------------

        cursor.execute("""
            SELECT
                ji.job_card_no,
                # RAW_MATERIAL_SHORTAGE_ITEM_COUNT_V1
                ji.item_name AS item_name,
                jc.child_code,
                # RAW_MATERIAL_SHORTAGE_JC_PLAN_TOTAL_V1
                NULLIF(TRIM(jc.so_no), '') AS so_no,
                ji.so_qty AS qty,
                NULLIF(TRIM(ji.material), '') AS jc_material,
                NULLIF(TRIM(ji.cutting_size), '') AS jc_cut_size,

                MAX(jpd.in_time) AS rm_in_time,

                GREATEST(
                    DATEDIFF(
                        CURDATE(),
                        DATE(MAX(jpd.in_time))
                    ),
                    0
                ) AS days_in_stage

            FROM job_card_items ji

            JOIN job_cards jc
                ON BINARY jc.job_card_no
                 = BINARY ji.job_card_no

            JOIN job_card_process_days jpd
                ON BINARY jpd.job_card_no
                 = BINARY ji.job_card_no
               AND LOWER(TRIM(jpd.process_name))
                   = 'raw material'
               AND jpd.in_time IS NOT NULL
               AND jpd.out_time IS NULL
               AND COALESCE(jpd.is_completed, 0) = 0

            WHERE COALESCE(ji.is_deleted, 0) = 0
              AND LOWER(TRIM(ji.wip_status))
                  = 'raw material'

              AND ji.job_card_no <> '0000112671'

            GROUP BY
                ji.id,
                ji.job_card_no,
                ji.item_name,
                jc.child_code,
                jc.so_no,
                ji.so_qty,
                ji.material,
                ji.cutting_size
        """)

        pending_rows = cursor.fetchall() or []

        # RM_CUTTING_COMBINED_REQUIREMENT_V1
        # Do not return when RM Pending is empty.
        # Cutting-only materials must also appear in the
        # combined Material Planning requirement.

        # ============================================================
        # RAW_MATERIAL_ERP_STOCK_NET_SHORTAGE_V1
        # Latest successful ERP stock snapshot
        # ============================================================

        cursor.execute("""
            SELECT
                s.item_code,
                s.item_details,
                s.uom,
                s.current_stock
            FROM raw_material_stock_items s
            WHERE s.upload_id = (
                SELECT id
                FROM raw_material_stock_uploads
                WHERE is_active = 1
                ORDER BY id DESC
                LIMIT 1
            )
        """)

        active_stock_rows = cursor.fetchall() or []

        stock_by_material = {}

        for stock_row in active_stock_rows:
            stock_material_key = _material_key(
                stock_row.get("item_details")
            )

            stock_uom_key = _stock_uom_key(
                stock_row.get("uom")
            )

            if not stock_material_key:
                continue

            stock_key = (
                stock_material_key,
                stock_uom_key,
            )

            stock_by_material.setdefault(
                stock_key,
                Decimal("0"),
            )

            stock_by_material[stock_key] += (
                _decimal_qty(
                    stock_row.get("current_stock")
                )
            )

        # ------------------------------------------------------------
        # 2. Collect only child codes that need historical BOM fallback
        # ------------------------------------------------------------

        fallback_codes = []

        for row in pending_rows:
            if (
                not _clean(row.get("jc_material"))
                or not _clean(row.get("jc_cut_size"))
            ):
                child_code = _clean(
                    row.get("child_code")
                )

                if child_code:
                    fallback_codes.append(
                        child_code
                    )

        fallback_codes = list(
            dict.fromkeys(fallback_codes)
        )

        bom_by_parent = {}

        # ------------------------------------------------------------
        # 3. Fetch all relevant BOM candidates together
        # ------------------------------------------------------------

        if fallback_codes:
            placeholders = ",".join(
                ["%s"] * len(fallback_codes)
            )

            cursor.execute(
                f"""
                SELECT
                    bl.id,
                    bl.parent_code,
                    bl.child_code,
                    NULLIF(
                        TRIM(bl.cutting_size),
                        ''
                    ) AS cutting_size,
                    NULLIF(
                        TRIM(i.item_description),
                        ''
                    ) AS material

                FROM bom_links bl

                LEFT JOIN items i
                    ON BINARY i.item_code
                     = BINARY bl.child_code

                WHERE bl.make_buy = 'I'
                  AND COALESCE(
                        bl.is_alternate,
                        0
                      ) = 0

                  AND BINARY bl.parent_code IN (
                      {placeholders}
                  )

                ORDER BY
                    bl.parent_code,
                    bl.id
                """,
                tuple(fallback_codes),
            )

            for bom in cursor.fetchall() or []:
                parent_code = _clean(
                    bom.get("parent_code")
                )

                bom_by_parent.setdefault(
                    parent_code,
                    [],
                ).append(bom)

        # ------------------------------------------------------------
        # 4. Resolve effective source + calculate in Python
        # ------------------------------------------------------------

        grouped = {}

        for row in pending_rows:

            child_code = _clean(
                row.get("child_code")
            )

            candidates = bom_by_parent.get(
                child_code,
                [],
            )

            jc_material = _clean(
                row.get("jc_material")
            )

            jc_cut_size = _clean(
                row.get("jc_cut_size")
            )

            # Material priority:
            # JC/PDF first -> old BOM fallback
            effective_material = jc_material

            if not effective_material:
                for candidate in candidates:
                    material = _clean(
                        candidate.get("material")
                    )

                    if material:
                        effective_material = material
                        break

            if not effective_material:
                continue

            # Cut Size priority:
            # JC/PDF first -> matching BOM -> first usable BOM
            effective_cut_size = jc_cut_size

            if (
                not effective_cut_size
                and not _is_forging_ring(
                    effective_material
                )
            ):
                material_match_key = _material_key(
                    effective_material
                )

                for candidate in candidates:
                    candidate_material = _clean(
                        candidate.get("material")
                    )

                    candidate_cut = _clean(
                        candidate.get("cutting_size")
                    )

                    if (
                        candidate_cut
                        and _material_key(
                            candidate_material
                        ) == material_match_key
                    ):
                        effective_cut_size = (
                            candidate_cut
                        )
                        break

                if not effective_cut_size:
                    for candidate in candidates:
                        candidate_cut = _clean(
                            candidate.get(
                                "cutting_size"
                            )
                        )

                        if candidate_cut:
                            effective_cut_size = (
                                candidate_cut
                            )
                            break

            qty = _decimal_qty(
                row.get("qty")
            )

            if _is_forging_ring(
                effective_material
            ):
                required_qty = qty
                uom = "No"

            else:
                cut_size = _number_from_cut_size(
                    effective_cut_size
                )

                if cut_size is None:
                    continue

                required_qty = (
                    cut_size + Decimal("2")
                ) * qty

                uom = "mm"

            key = _material_key(
                effective_material
            )

            days = int(
                row.get("days_in_stage")
                or 0
            )

            if key not in grouped:
                grouped[key] = {
                    "material": effective_material,
                    "uom": uom,
                    "shortage_qty": Decimal("0"),
                    # RAW_MATERIAL_SHORTAGE_QTY_COLUMN_V1
                    "input_qty": Decimal("0"),
                    # RAW_MATERIAL_SHORTAGE_JC_PLAN_TOTAL_V1
                    "so_job_cards": set(),
                    "advance_job_cards": set(),
                    # RAW_MATERIAL_SHORTAGE_ITEM_COUNT_V1
                    "item_names": set(),
                    "days_in_stage": days,
                }

            grouped[key]["shortage_qty"] += (
                required_qty
            )

            # RAW_MATERIAL_SHORTAGE_QTY_COLUMN_V1
            # Same Qty used in (Cut Size + 2) x Qty
            grouped[key]["input_qty"] += qty

            # RAW_MATERIAL_SHORTAGE_JC_PLAN_TOTAL_V1
            job_card_no = _clean(
                row.get("job_card_no")
            )

            if job_card_no:
                if _clean(row.get("so_no")):
                    grouped[key]["so_job_cards"].add(
                        job_card_no
                    )
                else:
                    grouped[key]["advance_job_cards"].add(
                        job_card_no
                    )

            # RAW_MATERIAL_SHORTAGE_ITEM_COUNT_V1
            item_name = _clean(row.get("item_name"))
            if item_name:
                grouped[key]["item_names"].add(item_name)

            grouped[key]["days_in_stage"] = max(
                grouped[key]["days_in_stage"],
                days,
            )

        # ========================================================
        # RM_CUTTING_COMBINED_REQUIREMENT_V1
        #
        # Combined Material Planning requirement:
        #
        # RM Pending gross requirement
        # +
        # Cutting Pending requirement
        # =
        # Combined Required
        #
        # ERP stock is deducted only AFTER this combination.
        # ========================================================

        for combined_row in grouped.values():

            combined_row["rm_required_qty"] = (
                combined_row.get(
                    "shortage_qty",
                    Decimal("0"),
                )
                or Decimal("0")
            )

            combined_row["cutting_required_qty"] = (
                Decimal("0")
            )

            combined_row["cutting_item_count"] = 0


        if cutting_rows is None:
            cutting_rows = (
                _load_cutting_pending()
            )


        for cutting_row in (
            cutting_rows
            or []
        ):

            if cutting_row.get("is_total"):
                continue

            cutting_material = _clean(
                cutting_row.get("material")
            )

            if not cutting_material:
                continue

            cutting_uom = _clean(
                cutting_row.get("uom")
            ) or "MM"

            material_key = _material_key(
                cutting_material
            )

            target_key = material_key

            # Do not combine unlike UOMs.
            #
            # Example:
            # RM Forging Ring = No.
            # Cutting material = MM
            #
            # Those must never be mathematically added.
            if target_key in grouped:

                current_uom = _stock_uom_key(
                    grouped[target_key].get(
                        "uom"
                    )
                )

                incoming_uom = _stock_uom_key(
                    cutting_uom
                )

                if (
                    current_uom
                    and incoming_uom
                    and current_uom != incoming_uom
                ):
                    target_key = (
                        material_key
                        + "__cutting__"
                        + incoming_uom
                    )


            if target_key not in grouped:

                grouped[target_key] = {
                    "material": cutting_material,
                    "uom": cutting_uom,

                    # At this stage shortage_qty means
                    # gross requirement before ERP deduction.
                    "shortage_qty": Decimal("0"),

                    "rm_required_qty": Decimal("0"),
                    "cutting_required_qty": Decimal("0"),

                    "input_qty": Decimal("0"),

                    "so_job_cards": set(),
                    "advance_job_cards": set(),

                    # Existing RM calculation uses item_names.
                    "item_names": set(),

                    "cutting_item_count": 0,

                    "days_in_stage": int(
                        cutting_row.get(
                            "days_in_stage"
                        )
                        or 0
                    ),
                }


            cutting_required = _decimal_qty(
                cutting_row.get(
                    "cutting_required"
                )
            )

            grouped[target_key][
                "cutting_required_qty"
            ] += cutting_required

            # Gross combined requirement.
            grouped[target_key][
                "shortage_qty"
            ] += cutting_required


            # Combined Qty (Nos.)
            grouped[target_key][
                "input_qty"
            ] += _decimal_qty(
                cutting_row.get(
                    "input_qty"
                )
            )


            # Combined Items.
            grouped[target_key][
                "cutting_item_count"
            ] += int(
                cutting_row.get(
                    "item_count"
                )
                or 0
            )


            # Combined SO / Advance Plan counts.
            grouped[target_key][
                "so_job_cards"
            ].update(
                cutting_row.get(
                    "so_job_cards",
                    set(),
                )
                or set()
            )

            grouped[target_key][
                "advance_job_cards"
            ].update(
                cutting_row.get(
                    "advance_job_cards",
                    set(),
                )
                or set()
            )


            # Show the oldest / longest live stage age.
            grouped[target_key][
                "days_in_stage"
            ] = max(
                int(
                    grouped[target_key].get(
                        "days_in_stage"
                    )
                    or 0
                ),
                int(
                    cutting_row.get(
                        "days_in_stage"
                    )
                    or 0
                ),
            )

        rows = list(grouped.values())

        rows.sort(
            key=lambda row: (
                -row["days_in_stage"],
                row["material"].lower(),
            )
        )

        for row in rows:

            # ========================================================
            # RAW_MATERIAL_ERP_STOCK_NET_SHORTAGE_V1
            #
            # Existing shortage_qty at this point is the original
            # JMS gross requirement. Preserve it as required_qty.
            # Only now apply the latest ERP stock.
            # ========================================================

            required_qty = (
                row.get("shortage_qty")
                or Decimal("0")
            )

            row["required_qty"] = required_qty
            row["required_display"] = (
                _format_shortage_qty(
                    required_qty
                )
            )

            # RM_CUTTING_COMBINED_REQUIREMENT_V1
            row["rm_required_display"] = (
                _format_shortage_qty(
                    row.get(
                        "rm_required_qty",
                        0,
                    )
                )
            )

            row["cutting_required_display"] = (
                _format_shortage_qty(
                    row.get(
                        "cutting_required_qty",
                        0,
                    )
                )
            )

            stock_key = (
                _material_key(
                    row.get("material")
                ),
                _stock_uom_key(
                    row.get("uom")
                ),
            )

            if stock_key in stock_by_material:
                erp_stock = (
                    stock_by_material[stock_key]
                )

                row["stock_matched"] = True
                row["erp_stock"] = erp_stock
                row["erp_stock_display"] = (
                    _format_shortage_qty(
                        erp_stock
                    )
                )

                final_shortage = (
                    required_qty - erp_stock
                )

                if final_shortage < Decimal("0"):
                    final_shortage = Decimal("0")

                row["shortage_qty"] = (
                    final_shortage
                )

            else:
                # Do not assume zero stock when ERP material
                # could not be matched safely.
                row["stock_matched"] = False
                row["erp_stock"] = None
                row["erp_stock_display"] = (
                    "Not Matched"
                )

                row["shortage_qty"] = (
                    required_qty
                )

            row["shortage_display"] = (
                _format_shortage_qty(
                    row["shortage_qty"]
                )
            )

            # RAW_MATERIAL_SHORTAGE_QTY_COLUMN_V1
            row["input_qty_display"] = (
                _format_shortage_qty(
                    row.get("input_qty", 0)
                )
            )

            # RAW_MATERIAL_SHORTAGE_JC_PLAN_TOTAL_V1
            so_count = len(
                row.get("so_job_cards", set())
            )

            advance_count = len(
                row.get("advance_job_cards", set())
            )

            # RAW_MATERIAL_SHORTAGE_JC_PLAN_DISPLAY_V2
            if so_count > 0 and advance_count > 0:
                row["jc_plan_display"] = (
                    f"{so_count} SO / Advance Plan"
                )
            elif so_count > 0:
                row["jc_plan_display"] = f"{so_count} SO"
            elif advance_count > 0:
                row["jc_plan_display"] = "Advance Plan"
            else:
                row["jc_plan_display"] = ""

            # RAW_MATERIAL_SHORTAGE_ITEM_COUNT_V1
            # RM_CUTTING_COMBINED_REQUIREMENT_V1
            row["item_count"] = (
                len(
                    row.get(
                        "item_names",
                        set(),
                    )
                )
                + int(
                    row.get(
                        "cutting_item_count",
                        0,
                    )
                    or 0
                )
            )
            row["item_count_display"] = str(
                row["item_count"]
            )


        # ========================================================
        # RAW_MATERIAL_SHORTAGE_JC_PLAN_TOTAL_V1
        # TOTAL FIRST ROW
        # ========================================================

        total_input_qty = sum(
            (
                row.get("input_qty")
                or Decimal("0")
            )
            for row in rows
        )

        total_shortage_by_uom = {}
        total_so_job_cards = set()
        total_advance_job_cards = set()

        for row in rows:
            row_uom = row.get("uom") or ""
            total_shortage_by_uom.setdefault(
                row_uom,
                Decimal("0"),
            )

            total_shortage_by_uom[row_uom] += (
                row.get("shortage_qty")
                or Decimal("0")
            )

            total_so_job_cards.update(
                row.get("so_job_cards", set())
            )

            total_advance_job_cards.update(
                row.get("advance_job_cards", set())
            )

        if len(total_shortage_by_uom) == 1:
            total_uom, total_shortage_qty = next(
                iter(total_shortage_by_uom.items())
            )

            total_shortage_display = (
                _format_shortage_qty(
                    total_shortage_qty
                )
            )

        else:
            total_uom = ""
            total_shortage_qty = None
            total_shortage_display = ""

        # RAW_MATERIAL_SHORTAGE_JC_PLAN_DISPLAY_V2
        total_so_count = len(total_so_job_cards)
        total_advance_count = len(total_advance_job_cards)

        if total_so_count > 0 and total_advance_count > 0:
            total_jc_plan_display = (
                f"{total_so_count} SO / Advance Plan"
            )
        elif total_so_count > 0:
            total_jc_plan_display = f"{total_so_count} SO"
        elif total_advance_count > 0:
            total_jc_plan_display = "Advance Plan"
        else:
            total_jc_plan_display = ""

        # RAW_MATERIAL_SHORTAGE_ITEM_TOTAL_V1
        total_item_count = sum(
            int(row.get("item_count") or 0)
            for row in rows
        )

        total_row = {
            "material": "TOTAL",
            "uom": total_uom,
            "required_qty": None,
            "required_display": "",
            "erp_stock": None,
            "erp_stock_display": "",
            "stock_matched": False,
            "shortage_qty": total_shortage_qty,
            "shortage_display": total_shortage_display,
            "input_qty": total_input_qty,
            "input_qty_display": _format_shortage_qty(
                total_input_qty
            ),
            "jc_plan_display": total_jc_plan_display,
            "item_count": total_item_count,
            "item_count_display": str(total_item_count),
            "days_in_stage": "",
            "is_total": True,
        }

        rows.insert(0, total_row)

        elapsed = time.perf_counter() - started

        print(
            "[Raw Material Shortage] "
            f"Pending={len(pending_rows)} "
            f"BOMCodes={len(fallback_codes)} "
            f"Materials={len(rows)} "
            f"Time={elapsed:.3f}s"
        )

        return rows

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()



# ============================================================
# CUTTING_PENDING_LOCAL_MERGE_V1
# Selectively merged from SERVER.
# Does not modify Raw Material / ERP stock calculation.
# ============================================================

# CUTTING_PENDING_LOADER_V1
def _load_cutting_pending():
    started = time.perf_counter()

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                ji.job_card_no,
                ji.item_name AS item_name,
                NULLIF(TRIM(jc.so_no), '') AS so_no,
                jc.child_code,

                COALESCE(
                    ji.job_card_qty,
                    ji.so_qty,
                    0
                ) AS qty,

                NULLIF(
                    TRIM(ji.material),
                    ''
                ) AS jc_material,

                NULLIF(
                    TRIM(ji.cutting_size),
                    ''
                ) AS jc_cut_size,

                MAX(jpd.in_time) AS cutting_in_time,

                GREATEST(
                    DATEDIFF(
                        CURDATE(),
                        DATE(MAX(jpd.in_time))
                    ),
                    0
                ) AS days_in_stage

            FROM job_card_items ji

            JOIN job_cards jc
              ON BINARY jc.job_card_no
               = BINARY ji.job_card_no

            JOIN job_card_process_days jpd
              ON BINARY jpd.job_card_no
               = BINARY ji.job_card_no

             AND LOWER(
                    TRIM(jpd.process_name)
                 ) = 'cutting'

             AND jpd.in_time IS NOT NULL
             AND jpd.out_time IS NULL
             AND COALESCE(
                    jpd.is_completed,
                    0
                 ) = 0

            WHERE COALESCE(
                    ji.is_deleted,
                    0
                  ) = 0

              AND LOWER(
                    TRIM(ji.wip_status)
                  ) = 'cutting'

            GROUP BY
                ji.id,
                ji.job_card_no,
                ji.item_name,
                jc.so_no,
                jc.child_code,
                ji.job_card_qty,
                ji.so_qty,
                ji.material,
                ji.cutting_size
        """)

        pending_rows = cursor.fetchall() or []

        if not pending_rows:
            return []

        fallback_codes = []

        for row in pending_rows:
            if (
                not _clean(row.get("jc_material"))
                or not _clean(row.get("jc_cut_size"))
            ):
                child_code = _clean(
                    row.get("child_code")
                )

                if child_code:
                    fallback_codes.append(
                        child_code
                    )

        fallback_codes = list(
            dict.fromkeys(fallback_codes)
        )

        bom_by_parent = {}

        if fallback_codes:
            placeholders = ",".join(
                ["%s"] * len(fallback_codes)
            )

            cursor.execute(
                f"""
                SELECT
                    bl.id,
                    bl.parent_code,
                    bl.child_code,

                    NULLIF(
                        TRIM(bl.cutting_size),
                        ''
                    ) AS cutting_size,

                    NULLIF(
                        TRIM(i.item_description),
                        ''
                    ) AS material

                FROM bom_links bl

                LEFT JOIN items i
                  ON BINARY i.item_code
                   = BINARY bl.child_code

                WHERE bl.make_buy = 'I'

                  AND COALESCE(
                        bl.is_alternate,
                        0
                      ) = 0

                  AND BINARY bl.parent_code IN (
                      {placeholders}
                  )

                ORDER BY
                    bl.parent_code,
                    bl.id
                """,
                tuple(fallback_codes),
            )

            for bom in cursor.fetchall() or []:
                parent_code = _clean(
                    bom.get("parent_code")
                )

                bom_by_parent.setdefault(
                    parent_code,
                    [],
                ).append(bom)

        grouped = {}

        for row in pending_rows:

            child_code = _clean(
                row.get("child_code")
            )

            candidates = bom_by_parent.get(
                child_code,
                [],
            )

            jc_material = _clean(
                row.get("jc_material")
            )

            jc_cut_size = _clean(
                row.get("jc_cut_size")
            )

            effective_material = jc_material

            if not effective_material:
                for candidate in candidates:
                    material = _clean(
                        candidate.get("material")
                    )

                    if material:
                        effective_material = material
                        break

            if not effective_material:
                continue

            effective_cut_size = jc_cut_size

            if not effective_cut_size:

                material_match_key = _material_key(
                    effective_material
                )

                for candidate in candidates:

                    candidate_material = _clean(
                        candidate.get("material")
                    )

                    candidate_cut = _clean(
                        candidate.get("cutting_size")
                    )

                    if (
                        candidate_cut
                        and _material_key(
                            candidate_material
                        ) == material_match_key
                    ):
                        effective_cut_size = (
                            candidate_cut
                        )
                        break

                if not effective_cut_size:
                    for candidate in candidates:

                        candidate_cut = _clean(
                            candidate.get(
                                "cutting_size"
                            )
                        )

                        if candidate_cut:
                            effective_cut_size = (
                                candidate_cut
                            )
                            break

            qty = _decimal_qty(
                row.get("qty")
            )

            cut_size = _number_from_cut_size(
                effective_cut_size
            )

            # Cutting Pending:
            # Cut Size x JC Qty
            # NO +2 mm allowance.
            if cut_size is None:
                cutting_required = Decimal("0")
            else:
                cutting_required = (
                    cut_size * qty
                )

            key = _material_key(
                effective_material
            )

            days = int(
                row.get("days_in_stage")
                or 0
            )

            if key not in grouped:
                grouped[key] = {
                    "material": effective_material,
                    "uom": "MM",
                    "cutting_required": Decimal("0"),
                    "input_qty": Decimal("0"),
                    "so_job_cards": set(),
                    "advance_job_cards": set(),
                    "item_count": 0,
                    "days_in_stage": days,
                }

            grouped[key][
                "cutting_required"
            ] += cutting_required

            grouped[key][
                "input_qty"
            ] += qty

            job_card_no = _clean(
                row.get("job_card_no")
            )

            so_no = _clean(
                row.get("so_no")
            )

            if job_card_no:
                if so_no:
                    grouped[key][
                        "so_job_cards"
                    ].add(job_card_no)
                else:
                    grouped[key][
                        "advance_job_cards"
                    ].add(job_card_no)

            grouped[key]["item_count"] += 1

            grouped[key][
                "days_in_stage"
            ] = max(
                grouped[key][
                    "days_in_stage"
                ],
                days,
            )

        rows = list(
            grouped.values()
        )

        rows.sort(
            key=lambda row: (
                -row["days_in_stage"],
                row["material"].lower(),
            )
        )

        total_so_job_cards = set()
        total_advance_job_cards = set()

        for row in rows:

            row["cutting_required_display"] = (
                _format_shortage_qty(
                    row.get(
                        "cutting_required",
                        0,
                    )
                )
            )

            row["input_qty_display"] = (
                _format_shortage_qty(
                    row.get(
                        "input_qty",
                        0,
                    )
                )
            )

            row["item_count"] = int(
                row.get(
                    "item_count",
                    0,
                )
                or 0
            )

            row["item_count_display"] = str(
                row["item_count"]
            )

            so_count = len(
                row.get(
                    "so_job_cards",
                    set(),
                )
            )

            advance_count = len(
                row.get(
                    "advance_job_cards",
                    set(),
                )
            )

            if (
                so_count > 0
                and advance_count > 0
            ):
                row["jc_plan_display"] = (
                    f"{so_count} SO / Advance Plan"
                )

            elif so_count > 0:
                row["jc_plan_display"] = (
                    f"{so_count} SO"
                )

            elif advance_count > 0:
                row["jc_plan_display"] = (
                    "Advance Plan"
                )

            else:
                row["jc_plan_display"] = ""

            total_so_job_cards.update(
                row.get(
                    "so_job_cards",
                    set(),
                )
            )

            total_advance_job_cards.update(
                row.get(
                    "advance_job_cards",
                    set(),
                )
            )

        if rows:

            total_required = sum(
                (
                    row.get(
                        "cutting_required",
                        Decimal("0"),
                    )
                    or Decimal("0")
                )
                for row in rows
            )

            total_qty = sum(
                (
                    row.get(
                        "input_qty",
                        Decimal("0"),
                    )
                    or Decimal("0")
                )
                for row in rows
            )

            total_items = sum(
                int(
                    row.get(
                        "item_count",
                        0,
                    )
                    or 0
                )
                for row in rows
            )

            total_days = max(
                int(
                    row.get(
                        "days_in_stage",
                        0,
                    )
                    or 0
                )
                for row in rows
            )

            total_so_count = len(
                total_so_job_cards
            )

            total_advance_count = len(
                total_advance_job_cards
            )

            if (
                total_so_count > 0
                and total_advance_count > 0
            ):
                total_jc_plan_display = (
                    f"{total_so_count} SO / Advance Plan"
                )

            elif total_so_count > 0:
                total_jc_plan_display = (
                    f"{total_so_count} SO"
                )

            elif total_advance_count > 0:
                total_jc_plan_display = (
                    "Advance Plan"
                )

            else:
                total_jc_plan_display = ""

            total_row = {
                "material": "TOTAL",
                "uom": "MM",
                "cutting_required": total_required,
                "cutting_required_display": (
                    _format_shortage_qty(
                        total_required
                    )
                ),
                "input_qty": total_qty,
                "input_qty_display": (
                    _format_shortage_qty(
                        total_qty
                    )
                ),
                "item_count": total_items,
                "item_count_display": str(
                    total_items
                ),
                "jc_plan_display": (
                    total_jc_plan_display
                ),
                "days_in_stage": total_days,
                "is_total": True,
            }

            rows.insert(
                0,
                total_row,
            )

        elapsed = (
            time.perf_counter()
            - started
        )

        print(
            "[Cutting Pending] "
            f"Pending={len(pending_rows)} "
            f"BOMCodes={len(fallback_codes)} "
            f"Materials={len(rows)} "
            f"Time={elapsed:.3f}s"
        )

        return rows

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

# RAW_MATERIAL_STOCK_UPLOAD_ROUTE_V1
@raw_material_shortage_bp.route(
    "/raw-material-shortage/upload-stock",
    methods=["POST"],
)
def upload_stock():
    role = _clean(
        session.get("role")
    ).lower()

    is_gaurang_special = (
        is_gaurang_special_user()
    )

    if (
        role not in ("admin", "plant_head")
        and not is_gaurang_special
    ):
        return redirect(
            url_for("pages.index")
        )

    uploaded = request.files.get("stock_file")

    if (
        not uploaded
        or not _clean(uploaded.filename)
    ):
        return redirect(
            url_for(
                "raw_material_shortage.index",
                stock_upload="error",
                stock_message="Please select an ERP stock .xls file.",
            )
        )

    original_filename = _clean(
        uploaded.filename
    )[:255]

    if not original_filename.lower().endswith(".xls"):
        return redirect(
            url_for(
                "raw_material_shortage.index",
                stock_upload="error",
                stock_message="Only ERP .xls stock files are supported.",
            )
        )

    try:
        file_bytes = uploaded.read()

        stock_rows = _parse_erp_stock_xls(
            file_bytes
        )

    except Exception as exc:
        return redirect(
            url_for(
                "raw_material_shortage.index",
                stock_upload="error",
                stock_message=str(exc)[:180],
            )
        )

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # New snapshot starts inactive.
        # The old snapshot stays active until every new row is saved.
        cursor.execute("""
            INSERT INTO raw_material_stock_uploads (
                original_filename,
                uploaded_by_user_id,
                uploaded_by_name,
                is_active,
                row_count
            )
            VALUES (%s, %s, %s, 0, 0)
        """, (
            original_filename,
            session.get("user_id"),
            _clean(
                session.get("username")
                or session.get("full_name")
            ),
        ))

        upload_id = cursor.lastrowid

        insert_rows = [
            (
                upload_id,
                row["item_code"],
                row["item_details"],
                row["uom"],
                row["current_stock"],
                row["rate"],
                row["stock_value"],
                row["item_category"],
                row["item_group"],
            )
            for row in stock_rows
        ]

        cursor.executemany("""
            INSERT INTO raw_material_stock_items (
                upload_id,
                item_code,
                item_details,
                uom,
                current_stock,
                rate,
                stock_value,
                item_category,
                item_group
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
        """, insert_rows)

        if cursor.rowcount != len(stock_rows):
            raise RuntimeError(
                "ERP stock row count mismatch while saving."
            )

        # Only after the complete new snapshot exists:
        # deactivate previous snapshots.
        cursor.execute("""
            UPDATE raw_material_stock_uploads
            SET is_active = 0
            WHERE is_active = 1
              AND id <> %s
        """, (upload_id,))

        cursor.execute("""
            UPDATE raw_material_stock_uploads
            SET
                is_active = 1,
                row_count = %s
            WHERE id = %s
        """, (
            len(stock_rows),
            upload_id,
        ))

        if cursor.rowcount != 1:
            raise RuntimeError(
                "Unable to activate the new ERP stock snapshot."
            )

        conn.commit()

    except Exception as exc:
        if conn:
            conn.rollback()

        return redirect(
            url_for(
                "raw_material_shortage.index",
                stock_upload="error",
                stock_message=str(exc)[:180],
            )
        )

    finally:
        if cursor:
            cursor.close()

        if conn:
            conn.close()

    return redirect(
        url_for(
            "raw_material_shortage.index",
            stock_upload="success",
            stock_rows=len(stock_rows),
        )
    )

# RAW_MATERIAL_SHORTAGE_EXCEL_V1
@raw_material_shortage_bp.route(
    "/raw-material-shortage/export-excel"
)
def export_excel():
    role = _clean(
        session.get("role")
    ).lower()

    is_gaurang_special = (
        is_gaurang_special_user()
    )

    if (
        role not in ("admin", "plant_head")
        and not is_gaurang_special
    ):
        return redirect(
            url_for("pages.index")
        )

    shortage_rows = (
        _load_raw_material_shortage()
    )

    shortage_date = date.today().strftime(
        "%d.%m.%y"
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Raw Material Shortage"

    headers = [
        "Raw Material-Pending",
        "UOM",
        # RAW_MATERIAL_SHORTAGE_COLUMN_ORDER_V2
        f"Shortage {shortage_date}",
        "Items",
        "Qty (Nos.)",
        "JC Plan",
        "Days in Stage",
    ]

    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    for row in shortage_rows:
        is_total = bool(row.get("is_total"))

        shortage_qty = row.get("shortage_qty")
        input_qty = row.get("input_qty") or 0

        if is_total and shortage_qty is None:
            shortage_excel = row.get("shortage_display") or ""
        else:
            try:
                shortage_excel = float(
                    shortage_qty or 0
                )
                if shortage_excel.is_integer():
                    shortage_excel = int(
                        shortage_excel
                    )
            except Exception:
                shortage_excel = row.get("shortage_display") or 0

        try:
            input_qty_excel = float(input_qty)
            if input_qty_excel.is_integer():
                input_qty_excel = int(
                    input_qty_excel
                )
        except Exception:
            input_qty_excel = 0

        ws.append([
            row.get("material") or "",
            row.get("uom") or "",
            shortage_excel,
            row.get("item_count", 0),
            input_qty_excel,
            row.get("jc_plan_display") or "",
            (
                ""
                if is_total
                else int(
                    row.get("days_in_stage")
                    or 0
                )
            ),
        ])

    for row in ws.iter_rows(
        min_row=2,
        max_col=7,
    ):
        row[1].alignment = Alignment(
            horizontal="center"
        )

        # Shortage
        row[2].alignment = Alignment(
            horizontal="right"
        )
        row[2].number_format = '#,##0.##'

        # Items
        row[3].alignment = Alignment(
            horizontal="center"
        )

        # Qty
        row[4].alignment = Alignment(
            horizontal="right"
        )
        row[4].number_format = '#,##0.##'

        # JC Plan
        row[5].alignment = Alignment(
            horizontal="center"
        )

        # Days
        row[6].alignment = Alignment(
            horizontal="center"
        )

    if shortage_rows:
        for cell in ws[2]:
            cell.font = Font(bold=True)

    ws.freeze_panes = "A3"
    ws.auto_filter.ref = ws.dimensions

    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 28
    ws.column_dimensions["G"].width = 18

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = (
        "Raw_Material_Shortage_"
        + date.today().strftime("%Y-%m-%d")
        + ".xlsx"
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )


# CUTTING_PENDING_EXCEL_EXPORT_V1
@raw_material_shortage_bp.route(
    "/raw-material-shortage/cutting-pending/export-excel"
)
def export_cutting_pending_excel():

    role = _clean(
        session.get("role")
    ).lower()

    is_gaurang_special = (
        is_gaurang_special_user()
    )

    if (
        role not in ("admin", "plant_head")
        and not is_gaurang_special
    ):
        return redirect(
            url_for("pages.index")
        )

    cutting_rows = (
        _load_cutting_pending()
    )

    report_date = date.today().strftime(
        "%d.%m.%y"
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Cutting Pending"

    headers = [
        "Cutting-Pending",
        "UOM",
        f"Cutting Required {report_date}",
        "Items",
        "Qty (Nos.)",
        "JC Plan",
        "Days in Stage",
    ]

    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(
            bold=True
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

    for row in cutting_rows:

        required = (
            row.get(
                "cutting_required"
            )
            or Decimal("0")
        )

        qty = (
            row.get(
                "input_qty"
            )
            or Decimal("0")
        )

        if required == required.to_integral():
            required_excel = int(
                required
            )
        else:
            required_excel = float(
                required
            )

        if qty == qty.to_integral():
            qty_excel = int(
                qty
            )
        else:
            qty_excel = float(
                qty
            )

        ws.append([
            row.get("material") or "",
            row.get("uom") or "",
            required_excel,
            int(
                row.get(
                    "item_count",
                    0,
                )
                or 0
            ),
            qty_excel,
            row.get(
                "jc_plan_display"
            ) or "",
            int(
                row.get(
                    "days_in_stage",
                    0,
                )
                or 0
            ),
        ])

    for row in ws.iter_rows(
        min_row=2,
        max_col=7,
    ):

        row[1].alignment = Alignment(
            horizontal="center"
        )

        row[2].alignment = Alignment(
            horizontal="right"
        )
        row[2].number_format = '#,##0.##'

        row[3].alignment = Alignment(
            horizontal="center"
        )

        row[4].alignment = Alignment(
            horizontal="right"
        )
        row[4].number_format = '#,##0.##'

        row[5].alignment = Alignment(
            horizontal="center"
        )

        row[6].alignment = Alignment(
            horizontal="center"
        )

    if (
        cutting_rows
        and cutting_rows[0].get(
            "is_total"
        )
    ):
        for cell in ws[2]:
            cell.font = Font(
                bold=True
            )

        ws.freeze_panes = "A3"

    else:
        ws.freeze_panes = "A2"

    ws.auto_filter.ref = ws.dimensions

    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 14
    ws.column_dimensions["F"].width = 28
    ws.column_dimensions["G"].width = 18

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = (
        "Cutting_Pending_"
        + date.today().strftime(
            "%Y-%m-%d"
        )
        + ".xlsx"
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )

@raw_material_shortage_bp.route(
    "/raw-material-shortage"
)
def index():
    role = _clean(
        session.get("role")
    ).lower()

    is_gaurang_special = (
        is_gaurang_special_user()
    )

    if (
        role not in ("admin", "plant_head")
        and not is_gaurang_special
    ):
        return redirect(
            url_for("pages.index")
        )

    # RM_CUTTING_COMBINED_REQUIREMENT_V1
    # Load Cutting once and use the same live rows for
    # both the Cutting tab and combined RM shortage.
    cutting_rows = (
        _load_cutting_pending()
    )

    shortage_rows = (
        _load_raw_material_shortage(
            cutting_rows=cutting_rows
        )
    )

    active_stock_upload = (
        _load_active_stock_upload()
    )

    return render_template(
        "raw_material_shortage.html",
        active_page="raw_material_shortage",
        is_gaurang_special=is_gaurang_special,
        shortage_rows=shortage_rows,
        cutting_rows=cutting_rows,
        cutting_date=date.today().strftime(
            "%d.%m.%y"
        ),
        active_stock_upload=active_stock_upload,
        stock_upload_status=_clean(
            request.args.get("stock_upload")
        ),
        stock_upload_rows=_clean(
            request.args.get("stock_rows")
        ),
        stock_upload_message=_clean(
            request.args.get("stock_message")
        ),
        shortage_date=date.today().strftime(
            "%d.%m.%y"
        ),
    )
