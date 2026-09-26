from .oee_calculations import (
    calculate_confirmed_excel_fields,
)


# OEE_MACHINE_FORMULA_PROFILES_V1

ALL_OEE_LOSS_CODES = tuple(
    f"A{i}"
    for i in range(1, 28)
)


# ------------------------------------------------------------
# P01
# Excel:
#   AR = SUM(A1:A27)
#   PR = A17 + A21 + A22
#   Target deduct = A7
# ------------------------------------------------------------

PROFILE_P01 = {
    "name": "P01",
    "ar_loss_codes": ALL_OEE_LOSS_CODES,
    "pr_loss_codes": (
        "A17",
        "A21",
        "A22",
    ),
    "target_deduct_code": "A7",
}


# ------------------------------------------------------------
# P02
# Excel:
#   AR = SUM(A1:A27)
#   PR = A17 + A21 + A22
#   Target deduct = A8
# ------------------------------------------------------------

PROFILE_P02 = {
    "name": "P02",
    "ar_loss_codes": ALL_OEE_LOSS_CODES,
    "pr_loss_codes": (
        "A17",
        "A21",
        "A22",
    ),
    "target_deduct_code": "A8",
}


# ------------------------------------------------------------
# P06
# Excel:
#   PR = A4 + A6 + A9 + A16
#   AR = all remaining A1-A27
#   Target deduct = A7
# ------------------------------------------------------------

P06_PR_LOSS_CODES = (
    "A4",
    "A6",
    "A9",
    "A16",
)

PROFILE_P06 = {
    "name": "P06",
    "ar_loss_codes": tuple(
        code
        for code in ALL_OEE_LOSS_CODES
        if code not in P06_PR_LOSS_CODES
    ),
    "pr_loss_codes": P06_PR_LOSS_CODES,
    "target_deduct_code": "A7",
}


OEE_MACHINE_PROFILE_MAP = {

    # P01
    "CNC 01": PROFILE_P01,
    "CNC 02": PROFILE_P01,

    # P02
    "CNC 03": PROFILE_P02,
    "CNC 05": PROFILE_P02,
    "CNC 06": PROFILE_P02,
    "CNC 31": PROFILE_P02,

    # P06 - Zone B
    "CNC 15": PROFILE_P06,
    "CNC 17": PROFILE_P06,
    "VMC 01": PROFILE_P06,
    "VMC 02": PROFILE_P06,
    "VMC 03": PROFILE_P06,

    # P06 - Zone C
    "CNC 11": PROFILE_P06,
    "CNC 19": PROFILE_P06,
    "CNC 20": PROFILE_P06,
    "CNC 27": PROFILE_P06,

    # P06 - Zone D
    "CNC 16": PROFILE_P06,
    "CNC 24": PROFILE_P06,
    "CNC 34": PROFILE_P06,
    "VMC 04": PROFILE_P06,
    "VMC 6": PROFILE_P06,

    # P06 - Zone E
    "CNC 10": PROFILE_P06,
    "CNC 13": PROFILE_P06,
    "CNC 22": PROFILE_P06,
    "CNC 23": PROFILE_P06,
    "CNC 25": PROFILE_P06,
    "CNC 26": PROFILE_P06,
    "CNC 28": PROFILE_P06,
    "CNC 29": PROFILE_P06,
    "CNC 33": PROFILE_P06,
}


def get_oee_formula_profile(machine_no):

    key = " ".join(
        str(machine_no or "")
        .strip()
        .upper()
        .split()
    )

    if key == "CNC 32":
        raise ValueError(
            "OEE formula profile for CNC 32 is under review "
            "because its Excel workbook uses a different BI:BQ structure."
        )

    profile = OEE_MACHINE_PROFILE_MAP.get(
        key
    )

    if not profile:
        raise ValueError(
            f"No confirmed Excel OEE formula profile for machine {machine_no}."
        )

    return profile


OEE_PROCESS_PREFIXES = (
    "cnc machining",
    "vmc machining",
)


def _clean_text(value):
    return str(value or "").strip()


def _to_nonnegative_int(value, field_name):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} must be a whole number."
        )

    if number < 0:
        raise ValueError(
            f"{field_name} cannot be negative."
        )

    return number


def _to_nonnegative_float(value, field_name):
    if value in (None, ""):
        return 0.0

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{field_name} must be numeric."
        )

    if number < 0:
        raise ValueError(
            f"{field_name} cannot be negative."
        )

    return number


def save_oee_entry(
    cursor,
    *,
    operator_completion_id,
    job_card_item_id,
    process_day_id,
    machine,
    operator_user_id,
    operator_name,
    entry_date,
    shift_name,
    job_card_no,
    item_name,
    process_name,
    start_time,
    end_time,
    cycle_minutes,
    cycle_seconds,
    load_unload_minutes,
    load_unload_seconds,
    ok_qty,
    rejected_qty,
    hold_qty,
    losses,
    remarks=None,
):
    # Uses caller's existing transaction.
    # AA:AD are excluded.
    # BI:BQ are the authoritative OEE result block.

    if cursor is None:
        raise ValueError(
            "A database cursor is required."
        )

    process_name = _clean_text(process_name)
    normalized_process_name = process_name.lower()

    if not normalized_process_name.startswith(
        OEE_PROCESS_PREFIXES
    ):
        raise ValueError(
            "OEE entry is allowed only for "
            "CNC/VMC machining processes."
        )

    job_card_no = _clean_text(job_card_no)
    item_name = _clean_text(item_name)
    operator_name = _clean_text(operator_name)
    shift_name = _clean_text(shift_name)

    if not job_card_no:
        raise ValueError("Job Card No. is required.")

    if not item_name:
        raise ValueError("Item Name is required.")

    if not operator_name:
        raise ValueError("Operator Name is required.")

    if not entry_date:
        raise ValueError("OEE Date is required.")

    if not shift_name:
        raise ValueError("Shift is required.")

    if not isinstance(machine, dict):
        raise ValueError(
            "Machine master data is required."
        )

    machine_id = machine.get("id")
    machine_no = _clean_text(machine.get("machine_no"))
    machine_name = _clean_text(machine.get("machine_name"))
    machine_category = _clean_text(
        machine.get("machine_category")
    ).upper()
    zone = _clean_text(machine.get("zone")) or None

    if not machine_id:
        raise ValueError(
            "A valid OEE machine is required."
        )

    if not machine_no or not machine_name:
        raise ValueError(
            "Machine master snapshot is incomplete."
        )

    if machine_category not in ("CNC", "VMC"):
        raise ValueError(
            "Machine category must be CNC or VMC."
        )

    formula_profile = get_oee_formula_profile(
        machine_no
    )


    ok_qty = _to_nonnegative_int(ok_qty, "OK Qty")
    rejected_qty = _to_nonnegative_int(
        rejected_qty,
        "Rejected Qty",
    )
    hold_qty = _to_nonnegative_int(
        hold_qty,
        "Hold Qty",
    )

    cycle_minutes = _to_nonnegative_int(
        cycle_minutes,
        "Cycle Time Minutes",
    )
    cycle_seconds = _to_nonnegative_int(
        cycle_seconds,
        "Cycle Time Seconds",
    )
    load_unload_minutes = _to_nonnegative_int(
        load_unload_minutes,
        "Load/Unload Minutes",
    )
    load_unload_seconds = _to_nonnegative_int(
        load_unload_seconds,
        "Load/Unload Seconds",
    )

    if cycle_seconds > 59:
        raise ValueError(
            "Cycle Time Seconds must be between 0 and 59."
        )

    if load_unload_seconds > 59:
        raise ValueError(
            "Load/Unload Seconds must be between 0 and 59."
        )

    if not isinstance(losses, list):
        raise ValueError(
            "OEE losses must be a list."
        )

    loss_map = {}
    prepared_losses = []

    for loss in losses:
        if not isinstance(loss, dict):
            raise ValueError(
                "Each OEE loss row must be an object."
            )

        loss_type_id = loss.get("loss_type_id")
        loss_code = _clean_text(
            loss.get("loss_code")
        ).upper()
        loss_name = _clean_text(
            loss.get("loss_name")
        )
        loss_minutes = _to_nonnegative_float(
            loss.get("loss_minutes"),
            f"{loss_code or 'Loss'} Minutes",
        )

        if not loss_type_id:
            raise ValueError(
                "Loss Type ID is required."
            )

        if not loss_code:
            raise ValueError(
                "Loss Code is required."
            )

        if loss_code in loss_map:
            raise ValueError(
                f"Duplicate OEE loss code: {loss_code}"
            )

        if not loss_name:
            raise ValueError(
                f"Loss Name is required for {loss_code}."
            )

        loss_category = (
            "PR"
            if loss_code
            in formula_profile["pr_loss_codes"]
            else "AR"
        )

        loss_map[loss_code] = loss_minutes

        prepared_losses.append({
            "loss_type_id": loss_type_id,
            "loss_code": loss_code,
            "loss_name": loss_name,
            "loss_category": loss_category,
            "loss_minutes": loss_minutes,
        })

    expected_codes = {
        f"A{index}"
        for index in range(1, 28)
    }

    if set(loss_map) != expected_codes:
        raise ValueError(
            "OEE losses must contain exactly A1-A27."
        )

    # Machine-specific Excel BL formula
    pr_loss_minutes = sum(
        loss_map[code]
        for code
        in formula_profile["pr_loss_codes"]
    )

    # Machine-specific Excel BJ formula
    ar_loss_minutes = sum(
        loss_map[code]
        for code
        in formula_profile["ar_loss_codes"]
    )

    calculated = calculate_confirmed_excel_fields(
        start_time=start_time,
        end_time=end_time,
        cycle_minutes=cycle_minutes,
        cycle_seconds=cycle_seconds,
        load_unload_minutes=load_unload_minutes,
        load_unload_seconds=load_unload_seconds,
        production_qty=ok_qty,
        rejection_qty=rejected_qty,
        rework_qty=hold_qty,
        ar_loss_minutes=ar_loss_minutes,
        pr_loss_minutes=pr_loss_minutes,
        target_deduction_minutes=loss_map[
            formula_profile["target_deduct_code"]
        ],
    )

    total_qty = int(
        calculated["total_qty"]
    )

    cursor.execute(
        """
        INSERT INTO oee_entries (
            operator_completion_id,
            job_card_item_id,
            process_day_id,
            machine_id,
            operator_user_id,
            entry_date,
            shift_name,
            job_card_no,
            item_name,
            process_name,
            operator_name,
            machine_no,
            machine_name,
            machine_category,
            zone,
            start_time,
            end_time,
            cycle_minutes,
            cycle_seconds,
            load_unload_minutes,
            load_unload_seconds,
            ok_qty,
            rejected_qty,
            hold_qty,
            planned_minutes,
            run_minutes,
            total_loss_minutes,
            ideal_cycle_minutes,
            target_qty,
            total_qty,
            plan_vs_actual,
            available_time_minutes,
            ar_loss_minutes,
            utilization_minutes,
            pr_loss_minutes,
            after_pr_minutes,
            detailed_ar_ratio,
            detailed_pr_ratio,
            detailed_qr_ratio,
            detailed_oee_ratio,
            remarks,
            record_status
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s,
            %s, %s, %s, %s,
            %s, %s
        )
        """,
        (
            operator_completion_id,
            job_card_item_id,
            process_day_id,
            machine_id,
            operator_user_id,
            entry_date,
            shift_name,
            job_card_no,
            item_name,
            process_name,
            operator_name,
            machine_no,
            machine_name,
            machine_category,
            zone,
            start_time or None,
            end_time or None,
            cycle_minutes,
            cycle_seconds,
            load_unload_minutes,
            load_unload_seconds,
            ok_qty,
            rejected_qty,
            hold_qty,
            calculated["planned_minutes"],
            calculated["run_minutes"],
            calculated["total_loss_minutes"],
            calculated["ideal_cycle_minutes"],
            calculated["target_qty"],
            total_qty,
            calculated["plan_vs_actual"],
            calculated["available_time_minutes"],
            calculated["ar_loss_minutes"],
            calculated["utilization_minutes"],
            calculated["pr_loss_minutes"],
            calculated["after_pr_loss_minutes"],

            # BI:BQ authoritative ratios
            calculated["ar_ratio"],
            calculated["pr_ratio"],
            calculated["qr_ratio"],
            calculated["detailed_oee_ratio"],

            _clean_text(remarks) or None,
            "active",
        ),
    )

    oee_entry_id = cursor.lastrowid

    if not oee_entry_id:
        raise RuntimeError(
            "OEE entry ID was not created."
        )

    for loss in prepared_losses:
        cursor.execute(
            """
            INSERT INTO oee_entry_losses (
                oee_entry_id,
                loss_type_id,
                loss_code_snapshot,
                loss_name_snapshot,
                loss_category_snapshot,
                loss_minutes
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                oee_entry_id,
                loss["loss_type_id"],
                loss["loss_code"],
                loss["loss_name"],
                loss["loss_category"],
                loss["loss_minutes"],
            ),
        )

    return {
        "oee_entry_id": oee_entry_id,
        "calculated": calculated,
        "loss_rows_saved": len(prepared_losses),
    }

# =========================================================================

# ============================================================
# 2-TABLE CONSOLIDATION — finalize a completed oee_entries row.
# Called by the JC completion flow after entry_state is set to COMPLETED.
# Idempotent: safe to call multiple times.
# ============================================================
def finalize_completed_entry(cursor, entry_id):
    from .oee_calculations import calculate_confirmed_excel_fields

    if not entry_id:
        return None

    # ---- read the entry ----
    cursor.execute("""
        SELECT
            id, machine_id, machine_no,
            cycle_minutes, cycle_seconds,
            load_unload_minutes, load_unload_seconds,
            ok_qty, rejected_qty, hold_qty,
            start_time, end_time,
            entry_state
        FROM oee_entries
        WHERE id = %s
        LIMIT 1
    """, (entry_id,))
    row = cursor.fetchone()
    if not row:
        return None
    if str(row.get("entry_state") or "").strip().upper() != "COMPLETED":
        return None

    # ---- resolve profile ----
    try:
        profile = get_oee_formula_profile(row.get("machine_no") or "")
    except Exception:
        return None
    pr_codes    = set(profile["pr_loss_codes"])
    deduct_code = profile["target_deduct_code"]

    # ---- read losses ----
    cursor.execute("""
        SELECT loss_code_snapshot, loss_minutes
        FROM oee_entry_losses
        WHERE oee_entry_id = %s
    """, (entry_id,))
    loss_rows = cursor.fetchall()

    loss_by_code = {c: 0.0 for c in ALL_OEE_LOSS_CODES}
    for l in loss_rows:
        code = str(l.get("loss_code_snapshot") or "").strip().upper()
        if code in loss_by_code:
            try:
                loss_by_code[code] += float(l.get("loss_minutes") or 0)
            except (TypeError, ValueError):
                pass

    ar_loss = sum(m for c, m in loss_by_code.items() if c not in pr_codes)
    pr_loss = sum(m for c, m in loss_by_code.items() if c in pr_codes)

    # ---- coerce time fields to str for the calc helper ----
    def _tstr(v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if hasattr(v, "hour"):
            return f"{v.hour:02d}:{v.minute:02d}:{v.second:02d}"
        if hasattr(v, "total_seconds"):
            total = int(v.total_seconds())
            h, r = divmod(total, 3600)
            m, s = divmod(r, 60)
            return f"{h % 24:02d}:{m:02d}:{s:02d}"
        return str(v)

    calc = calculate_confirmed_excel_fields(
        start_time               = _tstr(row.get("start_time")),
        end_time                 = _tstr(row.get("end_time")),
        cycle_minutes            = row.get("cycle_minutes") or 0,
        cycle_seconds            = row.get("cycle_seconds") or 0,
        load_unload_minutes      = row.get("load_unload_minutes") or 0,
        load_unload_seconds      = row.get("load_unload_seconds") or 0,
        production_qty           = row.get("ok_qty") or 0,
        rejection_qty            = row.get("rejected_qty") or 0,
        rework_qty               = row.get("hold_qty") or 0,
        ar_loss_minutes          = ar_loss,
        pr_loss_minutes          = pr_loss,
        target_deduction_minutes = loss_by_code.get(deduct_code, 0.0),
    )

    # ---- UPDATE entry with computed fields ----
    cursor.execute("""
        UPDATE oee_entries
        SET
            formula_profile         = %s,
            planned_minutes         = %s,
            run_minutes             = %s,
            total_loss_minutes      = %s,
            ideal_cycle_minutes     = %s,
            target_qty              = %s,
            total_qty               = %s,
            plan_vs_actual          = %s,
            available_time_minutes  = %s,
            ar_loss_minutes         = %s,
            utilization_minutes     = %s,
            pr_loss_minutes         = %s,
            after_pr_minutes        = %s,
            detailed_ar_ratio       = %s,
            detailed_pr_ratio       = %s,
            detailed_qr_ratio       = %s,
            detailed_oee_ratio      = %s,
            updated_at              = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (
        profile["name"],
        calc["planned_minutes"],
        calc["run_minutes"],
        calc["total_loss_minutes"],
        calc["ideal_cycle_minutes"],
        calc["target_qty"],
        int(calc["total_qty"]),
        calc["plan_vs_actual"],
        calc["available_time_minutes"],
        calc["ar_loss_minutes"],
        calc["utilization_minutes"],
        calc["pr_loss_minutes"],
        calc["after_pr_loss_minutes"],
        calc["ar_ratio"],
        calc["pr_ratio"],
        calc["qr_ratio"],
        calc["detailed_oee_ratio"],
        entry_id,
    ))

    return {"oee_entry_id": entry_id, "finalized": True}
