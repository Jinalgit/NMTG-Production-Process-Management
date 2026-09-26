from datetime import datetime, time


DEFAULT_PLANNED_MINUTES = 660.0

def _to_float(value, default=0.0):
    if value is None or value == "":
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_min_sec(minutes, seconds):
    minutes = _to_float(minutes, 0.0)
    seconds = _to_float(seconds, 0.0)

    if minutes < 0:
        raise ValueError("Minutes cannot be negative.")

    if seconds < 0 or seconds > 59:
        raise ValueError(
            "Seconds must be between 0 and 59."
        )

    return minutes + (seconds / 60.0)


def _time_to_minutes(value):
    if value is None or value == "":
        return None

    if isinstance(value, time):
        return (
            value.hour * 60
            + value.minute
            + value.second / 60.0
        )

    if isinstance(value, datetime):
        return (
            value.hour * 60
            + value.minute
            + value.second / 60.0
        )

    if isinstance(value, str):
        text = value.strip()

        if not text:
            return None

        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                parsed = datetime.strptime(text, fmt)

                return (
                    parsed.hour * 60
                    + parsed.minute
                    + parsed.second / 60.0
                )
            except ValueError:
                continue

        raise ValueError(
            "Time must be HH:MM or HH:MM:SS."
        )

    raise TypeError(
        "Unsupported Start/End Time value."
    )


def planned_minutes(start_time, end_time):
    start = _time_to_minutes(start_time)
    end = _time_to_minutes(end_time)

    # Excel:
    # =IF(OR(R3="",S3=""),660,
    #   ROUND(MOD(S3-R3,1)*1440,2))
    if start is None or end is None:
        return DEFAULT_PLANNED_MINUTES

    difference = (end - start) % 1440.0

    return round(difference, 2)


def calculate_confirmed_excel_fields(
    *,
    start_time,
    end_time,
    cycle_minutes,
    cycle_seconds,
    load_unload_minutes,
    load_unload_seconds,
    production_qty,
    rejection_qty,
    rework_qty,
    ar_loss_minutes,
    pr_loss_minutes,
    target_deduction_minutes,
):
    cycle_time = normalize_min_sec(
        cycle_minutes,
        cycle_seconds,
    )

    load_unload_time = normalize_min_sec(
        load_unload_minutes,
        load_unload_seconds,
    )

    production = _to_float(production_qty, 0.0)
    rejection = _to_float(rejection_qty, 0.0)
    rework = _to_float(rework_qty, 0.0)

    ar_loss = _to_float(ar_loss_minutes, 0.0)
    pr_loss = _to_float(pr_loss_minutes, 0.0)
    target_deduction = _to_float(target_deduction_minutes, 0.0)

    planned = planned_minutes(
        start_time,
        end_time,
    )

    # Excel W - IDEAL CT
    ideal_cycle = cycle_time + load_unload_time

    # Excel U - RUN MIN
    # =IF(O>0,O*W,"")
    if production > 0:
        run_minutes = production * ideal_cycle
    else:
        run_minutes = None

    # Excel X - TARGET QTY
    # Production-confirmed:
    # Excel X - machine-profile Target deduction / Ideal CT
    if ideal_cycle:
        target_qty = (
            planned - target_deduction
        ) / ideal_cycle
    else:
        target_qty = None

    # Excel Y - TOTAL QTY
    total_qty = production + rejection + rework

    # Excel Z - PLAN VS ACTUAL
    # =IFERROR(Total Qty / Target Qty,"")
    if target_qty not in (None, 0):
        plan_vs_actual = total_qty / target_qty
    else:
        plan_vs_actual = None

    # Excel V - LOSS MIN
    total_loss = ar_loss + pr_loss

    # BI - AVAILABLE TIME
    available_time = planned

    # BK - TOTAL UTILIZATION TIME
    # Excel: =MAX(BI-BJ,0)
    utilization_time = max(
        available_time - ar_loss,
        0.0,
    )

    # BM - AFTER PR LOSS
    # Excel: =MAX(BK-BL,0)
    after_pr_loss = max(
        utilization_time - pr_loss,
        0.0,
    )

    # BN - AR %
    # =IFERROR(BK/BI,0)
    if available_time:
        ar_ratio = utilization_time / available_time
    else:
        ar_ratio = 0.0

    # BO - PR %
    # =IFERROR(Run Min/BM,0)
    run_for_pr = (
        run_minutes
        if run_minutes is not None
        else 0.0
    )

    if after_pr_loss:
        pr_ratio = run_for_pr / after_pr_loss
    else:
        pr_ratio = 0.0

    # BP - QR %
    # =IFERROR(
    #   Production/(Production+Rejection+Rework),
    #   1
    # )
    if total_qty:
        qr_ratio = production / total_qty
    else:
        qr_ratio = 1.0

    # BQ - OEE %
    detailed_oee_ratio = (
        ar_ratio
        * pr_ratio
        * qr_ratio
    )

    loss_reason = (
        "Detailed Loss Entered"
        if ar_loss > 0
        else ""
    )

    # AA:AD intentionally excluded from JMS.
    return {
        "cycle_time_minutes": cycle_time,
        "load_unload_minutes": load_unload_time,
        "planned_minutes": planned,
        "run_minutes": run_minutes,
        "total_loss_minutes": total_loss,
        "ideal_cycle_minutes": ideal_cycle,
        "target_qty": target_qty,
        "total_qty": total_qty,
        "plan_vs_actual": plan_vs_actual,

        # BI:BQ authoritative block
        "available_time_minutes": available_time,
        "ar_loss_minutes": ar_loss,
        "utilization_minutes": utilization_time,
        "pr_loss_minutes": pr_loss,
        "after_pr_loss_minutes": after_pr_loss,
        "ar_ratio": ar_ratio,
        "pr_ratio": pr_ratio,
        "qr_ratio": qr_ratio,
        "detailed_oee_ratio": detailed_oee_ratio,

        "loss_reason": loss_reason,
        "excel_status": (
            "Completed"
            if production > 0
            else "Pending"
        ),
    }
