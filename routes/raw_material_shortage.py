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




# ============================================================
# RM_PURCHASE_WEIGHT_KG_V1
#
# Purchase Weight is calculated from FINAL Purchase Shortage.
#
# Density:
#     7850 kg/m3
#
# Forged/Forging Ring:
#     excluded because Purchase Shortage is in Nos.
#
# Unsupported/ambiguous dimensions:
#     show "-"
# ============================================================

_STEEL_DENSITY = Decimal("7850")
_PI_DECIMAL = Decimal("3.141592653589793")
_SQRT3_OVER_2 = Decimal("0.8660254037844386")


def _purchase_weight_dimension_pair(material):
    text = _clean(material).upper()

    match = re.search(
        r"(?<![A-Z0-9])"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*[X?]\s*"
        r"([0-9]+(?:\.[0-9]+)?)",
        text,
    )

    if not match:
        return None

    try:
        return (
            Decimal(match.group(1)),
            Decimal(match.group(2)),
        )
    except InvalidOperation:
        return None


def _purchase_weight_mm_value(material):
    """
    Finds the last numeric dimension directly followed by MM.

    Example:
        ROUND BAR EN19 95 MM
                        ^^
    Does not accidentally use EN19.
    """
    text = _clean(material).upper()

    values = re.findall(
        r"(?<![A-Z0-9])"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s*MM\b",
        text,
    )

    if not values:
        return None

    try:
        return Decimal(
            values[-1]
        )
    except InvalidOperation:
        return None


def _purchase_weight_named_value(
    material,
    names,
):
    text = _clean(material).upper()

    name_pattern = "|".join(
        re.escape(name)
        for name in names
    )

    match = re.search(
        rf"(?:{name_pattern})"
        r"\s*[:=\-]?\s*"
        r"([0-9]+(?:\.[0-9]+)?)",
        text,
    )

    if not match:
        return None

    try:
        return Decimal(
            match.group(1)
        )
    except InvalidOperation:
        return None


def _calculate_purchase_weight_kg(
    material,
    uom,
    purchase_shortage,
):
    """
    Returns:
        weight_kg, calculation_type

    purchase_shortage is the FINAL Purchase Shortage,
    after ERP stock deduction.
    """

    material_text = _clean(
        material
    )

    shortage = _decimal_qty(
        purchase_shortage
    )

    # No material needs purchasing.
    if shortage <= 0:
        return Decimal("0"), "zero"

    # Explicitly excluded.
    if _is_forging_ring(
        material_text
    ):
        return None, "forging_ring"

    # All formulas below require purchase length in MM.
    if _stock_uom_key(uom) != "mm":
        return None, "unsupported_uom"

    text = material_text.upper()

    area_mm2 = None
    calculation_type = ""


    # --------------------------------------------------------
    # PIPE / TUBE / HOLLOW
    # Requires explicit OD and wall thickness.
    # --------------------------------------------------------

    if (
        "PIPE" in text
        or "TUBE" in text
        or "HOLLOW" in text
    ):

        od = _purchase_weight_named_value(
            material_text,
            (
                "OD",
                "O.D.",
                "OUTER DIA",
                "OUTER DIAMETER",
            ),
        )

        thickness = _purchase_weight_named_value(
            material_text,
            (
                "THK",
                "THICK",
                "THICKNESS",
                "WALL",
            ),
        )

        if (
            od is not None
            and thickness is not None
            and od > 0
            and thickness > 0
        ):

            inner_dia = (
                od
                - Decimal("2")
                * thickness
            )

            if inner_dia > 0:

                area_mm2 = (
                    _PI_DECIMAL
                    / Decimal("4")
                    * (
                        od * od
                        - inner_dia * inner_dia
                    )
                )

                calculation_type = "pipe"


    # --------------------------------------------------------
    # HEX BAR
    # Dimension = across flats
    # --------------------------------------------------------

    elif "HEX" in text:

        size = _purchase_weight_named_value(
            material_text,
            (
                "AF",
                "A/F",
                "HEX",
            ),
        )

        if size is None:
            size = _purchase_weight_mm_value(
                material_text
            )

        if (
            size is not None
            and size > 0
        ):

            area_mm2 = (
                _SQRT3_OVER_2
                * size
                * size
            )

            calculation_type = "hex"


    # --------------------------------------------------------
    # SQUARE BAR
    # --------------------------------------------------------

    elif (
        "SQUARE" in text
        or re.search(
            r"\bSQ\b",
            text,
        )
    ):

        pair = _purchase_weight_dimension_pair(
            material_text
        )

        if pair:

            side_a, side_b = pair

            if (
                side_a > 0
                and side_b > 0
            ):
                area_mm2 = (
                    side_a
                    * side_b
                )

        else:

            side = _purchase_weight_named_value(
                material_text,
                (
                    "SQUARE",
                    "SQ",
                ),
            )

            if side is None:
                side = _purchase_weight_mm_value(
                    material_text
                )

            if (
                side is not None
                and side > 0
            ):
                area_mm2 = (
                    side
                    * side
                )

        if area_mm2:
            calculation_type = "square"


    # --------------------------------------------------------
    # FLAT / PLATE / RECTANGULAR
    # Area = width x thickness
    # --------------------------------------------------------

    elif (
        "FLAT" in text
        or "PLATE" in text
        or "RECTANGULAR" in text
        or "RECT BAR" in text
    ):

        pair = _purchase_weight_dimension_pair(
            material_text
        )

        if pair:

            width, thickness = pair

            if (
                width > 0
                and thickness > 0
            ):

                area_mm2 = (
                    width
                    * thickness
                )

                calculation_type = "flat"


    # --------------------------------------------------------
    # ROUND BAR / ROUND / ROD
    #
    # Exact user formula:
    #
    # PI() * (D/1000/2)^2
    #      * (Purchase Shortage/1000)
    #      * 7850
    # --------------------------------------------------------

    elif (
        "ROUND" in text
        or "ROD" in text
    ):

        diameter = _purchase_weight_named_value(
            material_text,
            (
                "DIA",
                "DIAMETER",
                "?",
            ),
        )

        if diameter is None:

            pair = _purchase_weight_dimension_pair(
                material_text
            )

            if pair:
                diameter = pair[0]

        if diameter is None:

            diameter = _purchase_weight_mm_value(
                material_text
            )

        if (
            diameter is not None
            and diameter > 0
        ):

            radius = (
                diameter
                / Decimal("2")
            )

            area_mm2 = (
                _PI_DECIMAL
                * radius
                * radius
            )

            calculation_type = "round"


    # Unknown profile or unreliable dimensions.
    if (
        area_mm2 is None
        or area_mm2 <= 0
    ):
        return None, "unsupported"


    # area mm2 x length mm = volume mm3
    # 1 m3 = 1,000,000,000 mm3

    weight_kg = (
        area_mm2
        * shortage
        * _STEEL_DENSITY
        / Decimal("1000000000")
    )

    return (
        weight_kg,
        calculation_type,
    )


def _format_purchase_weight_kg(
    value,
):
    if value is None:
        return "-"

    value = _decimal_qty(
        value
    )

    return f"{value:,.2f}"



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


# ============================================================
# RM_STAGE_TABS_ERP_STOCK_V1
#
# Read-only ERP Stock display for stage planning tabs.
#
# Raw Material Planning already receives ERP stock through
# _load_raw_material_shortage().
#
# This helper enriches Cutting Pending rows only.
# It does NOT deduct stock from Cutting Required.
# ============================================================

def _attach_active_erp_stock_display(rows):

    if not rows:
        return

    conn = None
    cursor = None

    try:

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute("""
            SELECT
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

        stock_rows = (
            cursor.fetchall()
            or []
        )


        stock_by_material = {}

        for stock_row in stock_rows:

            stock_key = (
                _material_key(
                    stock_row.get(
                        "item_details"
                    )
                ),
                _stock_uom_key(
                    stock_row.get(
                        "uom"
                    )
                ),
            )

            if not stock_key[0]:
                continue

            stock_by_material.setdefault(
                stock_key,
                Decimal("0"),
            )

            stock_by_material[
                stock_key
            ] += _decimal_qty(
                stock_row.get(
                    "current_stock"
                )
            )


        for row in rows:

            if row.get("is_total"):

                row["erp_stock"] = None
                row["erp_stock_display"] = ""

                continue


            stock_key = (
                _material_key(
                    row.get(
                        "material"
                    )
                ),
                _stock_uom_key(
                    row.get(
                        "uom"
                    )
                ),
            )


            if stock_key in stock_by_material:

                stock = (
                    stock_by_material[
                        stock_key
                    ]
                )

                row["erp_stock"] = stock

                row["erp_stock_display"] = (
                    _format_shortage_qty(
                        stock
                    )
                )

                row["stock_matched"] = True

            else:

                row["erp_stock"] = None

                row["erp_stock_display"] = (
                    "Not Matched"
                )

                row["stock_matched"] = False


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
                s.id AS stock_item_id,
                s.item_code,
                s.item_details,
                s.uom,
                s.current_stock,
                s.planning_remark
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

        # RM_PLANNING_INLINE_EDIT_V1
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

            bucket = stock_by_material.setdefault(
                stock_key,
                {
                    "stock": Decimal("0"),
                    "rows": [],
                    "remarks": [],
                },
            )

            bucket["stock"] += _decimal_qty(
                stock_row.get("current_stock")
            )

            bucket["rows"].append(
                stock_row
            )

            remark = _clean(
                stock_row.get("planning_remark")
            )

            if (
                remark
                and remark not in bucket["remarks"]
            ):
                bucket["remarks"].append(
                    remark
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
        # RM_PURCHASE_STAGE_ONLY_V1
        #
        # Purchase shortage counts ONLY current
        # Raw Material-stage JCs.
        #
        # Raw Material -> Cutting:
        # JC disappears from purchase requirement.
        #
        # Cutting is calculated separately in the
        # Cutting Pending tab.
        #
        # If moved back to Raw Material,
        # its RM requirement automatically returns.
        # ========================================================

        for rm_row in grouped.values():

            rm_row["rm_required_qty"] = (
                rm_row.get(
                    "shortage_qty",
                    Decimal("0"),
                )
                or Decimal("0")
            )

            rm_row["cutting_required_qty"] = (
                Decimal("0")
            )

            rm_row["cutting_item_count"] = 0


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

            stock_bucket = stock_by_material.get(
                stock_key
            )

            if stock_bucket:

                erp_stock = (
                    stock_bucket.get("stock")
                    or Decimal("0")
                )

                matched_rows = (
                    stock_bucket.get("rows")
                    or []
                )

                remarks = (
                    stock_bucket.get("remarks")
                    or []
                )

                row["stock_matched"] = True
                row["erp_stock"] = erp_stock

                row["erp_stock_display"] = (
                    _format_shortage_qty(
                        erp_stock
                    )
                )

                row["stock_match_count"] = len(
                    matched_rows
                )

                row["stock_editable"] = (
                    len(matched_rows) == 1
                )

                row["stock_item_id"] = (
                    matched_rows[0].get(
                        "stock_item_id"
                    )
                    if len(matched_rows) == 1
                    else None
                )

                row["planning_remark"] = (
                    remarks[0]
                    if remarks
                    else ""
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
                # No ERP match yet.
                # User may create a manual active-snapshot row
                # directly from Material Planning.
                row["stock_matched"] = False
                row["erp_stock"] = None
                row["erp_stock_display"] = (
                    "Not Matched"
                )

                row["stock_match_count"] = 0
                row["stock_editable"] = True
                row["stock_item_id"] = None
                row["planning_remark"] = ""

                row["shortage_qty"] = (
                    required_qty
                )

            row["shortage_display"] = (
                _format_shortage_qty(
                    row["shortage_qty"]
                )
            )

            # RM_PURCHASE_WEIGHT_KG_V1
            (
                row["purchase_weight_kg"],
                row["purchase_weight_type"],
            ) = _calculate_purchase_weight_kg(
                row.get("material"),
                row.get("uom"),
                row.get("shortage_qty"),
            )

            row["purchase_weight_display"] = (
                _format_purchase_weight_kg(
                    row.get(
                        "purchase_weight_kg"
                    )
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

        # RM_PURCHASE_WEIGHT_KG_V1
        total_purchase_weight_kg = sum(
            (
                row.get("purchase_weight_kg")
                or Decimal("0")
            )
            for row in rows
            if row.get(
                "purchase_weight_kg"
            ) is not None
        )

        # If a normal MM-based material needs purchasing
        # but cannot be calculated safely, do not display
        # a misleading partial total.
        purchase_weight_incomplete = any(
            (
                not _is_forging_ring(
                    row.get("material")
                )
                and _stock_uom_key(
                    row.get("uom")
                ) == "mm"
                and (
                    row.get("shortage_qty")
                    or Decimal("0")
                ) > 0
                and row.get(
                    "purchase_weight_kg"
                ) is None
            )
            for row in rows
        )

        total_purchase_weight_display = (
            "-"
            if purchase_weight_incomplete
            else _format_purchase_weight_kg(
                total_purchase_weight_kg
            )
        )

        total_row = {
            "material": "TOTAL",
            "uom": total_uom,
            "required_qty": None,
            "required_display": "",
            "erp_stock": None,
            "erp_stock_display": "",
            "stock_matched": False,
            "stock_match_count": 0,
            "stock_editable": False,
            "stock_item_id": None,
            "planning_remark": "",
            "shortage_qty": total_shortage_qty,
            "shortage_display": total_shortage_display,

            # RM_PURCHASE_WEIGHT_KG_V1
            "purchase_weight_kg": (
                None
                if purchase_weight_incomplete
                else total_purchase_weight_kg
            ),
            "purchase_weight_display": (
                total_purchase_weight_display
            ),
            "purchase_weight_type": "total",

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


# ============================================================
# RM_CLEAR_ACTIVE_ERP_STOCK_V1
# ============================================================

@raw_material_shortage_bp.route(
    "/raw-material-shortage/clear-stock",
    methods=["POST"],
)
def clear_stock():

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

    conn = None
    cursor = None

    try:

        conn = get_connection()

        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute("""
            SELECT
                id,
                original_filename
            FROM raw_material_stock_uploads
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
            FOR UPDATE
        """)

        active_upload = (
            cursor.fetchone()
        )

        if not active_upload:

            return redirect(
                url_for(
                    "raw_material_shortage.index",
                    stock_clear="success",
                    stock_clear_message=(
                        "ERP Stock is already clear."
                    ),
                )
            )


        if (
            _clean(
                active_upload.get(
                    "original_filename"
                )
            )
            == "ERP Stock Cleared"
        ):

            return redirect(
                url_for(
                    "raw_material_shortage.index",
                    stock_clear="success",
                    stock_clear_message=(
                        "ERP Stock is already clear."
                    ),
                )
            )


        old_upload_id = (
            active_upload["id"]
        )


        # Keep material identity and Purchase Planning remarks.
        # Do NOT keep ERP quantity.
        cursor.execute("""
            SELECT
                item_code,
                item_details,
                uom,
                planning_remark

            FROM raw_material_stock_items

            WHERE upload_id = %s

            ORDER BY id
        """, (
            old_upload_id,
        ))

        old_rows = (
            cursor.fetchall()
            or []
        )


        # Create a new clean active snapshot.
        cursor.execute("""
            INSERT INTO raw_material_stock_uploads (
                original_filename,
                uploaded_by_user_id,
                uploaded_by_name,
                is_active,
                row_count
            )
            VALUES (
                %s,
                %s,
                %s,
                0,
                0
            )
        """, (
            "ERP Stock Cleared",
            session.get("user_id"),
            _clean(
                session.get("username")
                or session.get("full_name")
            ),
        ))

        clear_upload_id = (
            cursor.lastrowid
        )


        if old_rows:

            insert_rows = [
                (
                    clear_upload_id,
                    row.get("item_code"),
                    row.get("item_details"),
                    row.get("uom"),
                    Decimal("0"),
                    row.get("planning_remark"),
                )
                for row in old_rows
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
                    item_group,
                    planning_remark
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NULL,
                    NULL,
                    'Raw Materials',
                    'ERP Stock Cleared',
                    %s
                )
            """, insert_rows)


        # Keep all old snapshots in DB.
        # Only deactivate them.
        cursor.execute("""
            UPDATE raw_material_stock_uploads
            SET is_active = 0
            WHERE is_active = 1
        """)


        cursor.execute("""
            UPDATE raw_material_stock_uploads
            SET
                is_active = 1,
                row_count = %s
            WHERE id = %s
        """, (
            len(old_rows),
            clear_upload_id,
        ))


        if cursor.rowcount != 1:
            raise RuntimeError(
                "Unable to activate cleared ERP stock state."
            )


        conn.commit()


    except Exception as exc:

        if conn:
            conn.rollback()

        return redirect(
            url_for(
                "raw_material_shortage.index",
                stock_clear="error",
                stock_clear_message=str(exc)[:180],
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
            stock_clear="success",
            stock_clear_message=(
                "ERP Stock cleared. "
                "Previous upload history and "
                "Purchase Planning remarks were retained."
            ),
        )
    )


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

        # ========================================================
        # RM_PLANNING_REMARK_CARRY_FORWARD_V1
        #
        # Preserve planning remarks from the currently-active
        # snapshot before creating the replacement snapshot.
        # Manual stock itself is NOT carried forward.
        # ========================================================

        cursor.execute("""
            SELECT
                s.item_code,
                s.item_details,
                s.uom,
                s.planning_remark
            FROM raw_material_stock_items s
            JOIN raw_material_stock_uploads u
              ON u.id = s.upload_id
            WHERE u.is_active = 1
              AND NULLIF(
                    TRIM(s.planning_remark),
                    ''
                  ) IS NOT NULL
        """)

        previous_remark_rows = (
            cursor.fetchall()
            or []
        )

        remark_by_code = {}
        remark_by_key = {}

        for (
            previous_code,
            previous_details,
            previous_uom,
            previous_remark,
        ) in previous_remark_rows:

            previous_code = _clean(
                previous_code
            )

            previous_remark = _clean(
                previous_remark
            )[:1000]

            previous_key = (
                _material_key(
                    previous_details
                ),
                _stock_uom_key(
                    previous_uom
                ),
            )

            if (
                previous_code
                and previous_remark
            ):
                remark_by_code[
                    previous_code
                ] = previous_remark

            if (
                previous_key[0]
                and previous_remark
            ):
                remark_by_key[
                    previous_key
                ] = previous_remark


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

        insert_sql = """
            INSERT INTO raw_material_stock_items (
                upload_id,
                item_code,
                item_details,
                uom,
                current_stock,
                rate,
                stock_value,
                item_category,
                item_group,
                planning_remark
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
        """

        insert_rows = []
        new_codes = set()
        new_keys = set()

        for row in stock_rows:

            item_code = _clean(
                row["item_code"]
            )

            stock_key = (
                _material_key(
                    row["item_details"]
                ),
                _stock_uom_key(
                    row["uom"]
                ),
            )

            planning_remark = None

            if item_code:
                planning_remark = (
                    remark_by_code.get(
                        item_code
                    )
                )

            if not planning_remark:
                planning_remark = (
                    remark_by_key.get(
                        stock_key
                    )
                )

            insert_rows.append(
                (
                    upload_id,
                    item_code,
                    row["item_details"],
                    row["uom"],
                    row["current_stock"],
                    row["rate"],
                    row["stock_value"],
                    row["item_category"],
                    row["item_group"],
                    planning_remark,
                )
            )

            if item_code:
                new_codes.add(
                    item_code
                )

            new_keys.add(
                stock_key
            )

        cursor.executemany(
            insert_sql,
            insert_rows,
        )

        if cursor.rowcount != len(stock_rows):
            raise RuntimeError(
                "ERP stock row count mismatch while saving."
            )


        # Preserve unmatched remarks with a zero-stock
        # planning placeholder.
        #
        # Manual edited stock is intentionally NOT copied
        # into a fresh ERP snapshot.
        carry_rows = []
        carried_keys = set()

        for (
            previous_code,
            previous_details,
            previous_uom,
            previous_remark,
        ) in previous_remark_rows:

            previous_code = _clean(
                previous_code
            )

            previous_details = _clean(
                previous_details
            )

            previous_uom = _clean(
                previous_uom
            )

            previous_remark = _clean(
                previous_remark
            )[:1000]

            previous_key = (
                _material_key(
                    previous_details
                ),
                _stock_uom_key(
                    previous_uom
                ),
            )

            matched_new_snapshot = (
                (
                    previous_code
                    and previous_code in new_codes
                )
                or previous_key in new_keys
            )

            if (
                matched_new_snapshot
                or not previous_key[0]
                or not previous_remark
                or previous_key in carried_keys
            ):
                continue

            carry_rows.append(
                (
                    upload_id,
                    None,
                    previous_details,
                    previous_uom,
                    Decimal("0"),
                    None,
                    None,
                    "Raw Materials",
                    "Manual Planning",
                    previous_remark,
                )
            )

            carried_keys.add(
                previous_key
            )

        if carry_rows:
            cursor.executemany(
                insert_sql,
                carry_rows,
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


# ============================================================
# RM_PLANNING_INLINE_EDIT_V1
# Editable ERP Stock + persistent Material Planning Remark
# ============================================================

@raw_material_shortage_bp.route(
    "/raw-material-shortage/update-planning-row",
    methods=["POST"],
)
def update_planning_row():

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

    material = _clean(
        request.form.get("material")
    )

    uom = _clean(
        request.form.get("uom")
    )

    stock_text = _clean(
        request.form.get("erp_stock")
    ).replace(",", "")

    planning_remark = _clean(
        request.form.get(
            "planning_remark"
        )
    )[:1000]

    if not material or not uom:
        return redirect(
            url_for(
                "raw_material_shortage.index",
                planning_update="error",
                planning_message=(
                    "Material or UOM is missing."
                ),
            )
        )

    try:
        new_stock = Decimal(
            stock_text
        )
    except Exception:
        return redirect(
            url_for(
                "raw_material_shortage.index",
                planning_update="error",
                planning_message=(
                    "ERP Stock must be numeric."
                ),
            )
        )

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(
            dictionary=True
        )

        cursor.execute("""
            SELECT id
            FROM raw_material_stock_uploads
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
            FOR UPDATE
        """)

        active_upload = (
            cursor.fetchone()
        )

        # RM_MANUAL_PLANNING_SNAPSHOT_V1
        #
        # ERP upload is NOT a prerequisite for planning edits.
        # If no active stock snapshot exists, create a manual
        # planning snapshot automatically on the first edit.
        if not active_upload:

            cursor.execute("""
                INSERT INTO raw_material_stock_uploads (
                    original_filename,
                    uploaded_by_user_id,
                    uploaded_by_name,
                    is_active,
                    row_count
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    1,
                    0
                )
            """, (
                "Manual Planning",
                session.get("user_id"),
                _clean(
                    session.get("username")
                    or session.get("full_name")
                ),
            ))

            upload_id = cursor.lastrowid

        else:
            upload_id = active_upload["id"]

        cursor.execute("""
            SELECT
                id,
                item_details,
                uom
            FROM raw_material_stock_items
            WHERE upload_id = %s
        """, (upload_id,))

        active_items = (
            cursor.fetchall()
            or []
        )

        target_key = (
            _material_key(material),
            _stock_uom_key(uom),
        )

        matches = []

        for item in active_items:

            item_key = (
                _material_key(
                    item.get(
                        "item_details"
                    )
                ),
                _stock_uom_key(
                    item.get("uom")
                ),
            )

            if item_key == target_key:
                matches.append(
                    item
                )

        if len(matches) > 1:
            raise RuntimeError(
                "Multiple ERP rows match this material. "
                "Stock edit was not saved."
            )

        remark_value = (
            planning_remark
            if planning_remark
            else None
        )

        if len(matches) == 1:

            stock_item_id = (
                matches[0]["id"]
            )

            cursor.execute("""
                UPDATE raw_material_stock_items
                SET
                    current_stock = %s,
                    stock_value = CASE
                        WHEN rate IS NULL
                            THEN stock_value
                        ELSE rate * %s
                    END,
                    planning_remark = %s
                WHERE id = %s
                  AND upload_id = %s
            """, (
                new_stock,
                new_stock,
                remark_value,
                stock_item_id,
                upload_id,
            ))

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "ERP stock row was not updated."
                )

        else:

            cursor.execute("""
                INSERT INTO raw_material_stock_items (
                    upload_id,
                    item_code,
                    item_details,
                    uom,
                    current_stock,
                    rate,
                    stock_value,
                    item_category,
                    item_group,
                    planning_remark
                )
                VALUES (
                    %s,
                    NULL,
                    %s,
                    %s,
                    %s,
                    NULL,
                    NULL,
                    'Raw Materials',
                    'Manual Planning',
                    %s
                )
            """, (
                upload_id,
                material,
                uom,
                new_stock,
                remark_value,
            ))

            # Keep displayed snapshot row count accurate.
            cursor.execute("""
                UPDATE raw_material_stock_uploads
                SET row_count = (
                    SELECT COUNT(*)
                    FROM raw_material_stock_items
                    WHERE upload_id = %s
                )
                WHERE id = %s
            """, (
                upload_id,
                upload_id,
            ))

        conn.commit()

    except Exception as exc:

        if conn:
            conn.rollback()

        return redirect(
            url_for(
                "raw_material_shortage.index",
                planning_update="error",
                planning_message=str(exc)[:200],
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
            planning_update="success",
            planning_message=(
                f"Saved {material}"
            ),
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

    # RM_STAGE_TABS_ERP_STOCK_V1
    # Display latest ERP stock beside Cutting Required.
    # No stock deduction is performed here.
    _attach_active_erp_stock_display(
        cutting_rows
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

        # RM_CLEAR_ACTIVE_ERP_STOCK_V1
        stock_clear_status=_clean(
            request.args.get("stock_clear")
        ),
        stock_clear_message=_clean(
            request.args.get(
                "stock_clear_message"
            )
        ),
        planning_update_status=_clean(
            request.args.get("planning_update")
        ),
        planning_update_message=_clean(
            request.args.get("planning_message")
        ),
        shortage_date=date.today().strftime(
            "%d.%m.%y"
        ),
    )
