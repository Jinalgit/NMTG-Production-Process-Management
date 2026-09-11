import json
import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, Response, request, session, render_template

from db import get_connection


oee_dashboard_bp = Blueprint(
    "oee_dashboard",
    __name__,
)

DEFAULT_SHIFT_MINUTES = 660.0
HIRING_RELIEF_FACTOR = 0.15


# ============================================================
# JSON / BASIC HELPERS
# ============================================================

def _jsonify(data, status=200):
    return Response(
        json.dumps(
            data,
            ensure_ascii=False,
            default=str,
        ),
        status=status,
        content_type="application/json; charset=utf-8",
    )


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            _json_safe(item)
            for item in value
        ]

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    return value


def _f(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _ratio(
    numerator,
    denominator,
):
    denominator = _f(
        denominator
    )

    if not denominator:
        return 0.0

    return (
        _f(numerator)
        / denominator
    )


def _process_key(value):
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .split()
    )


def _iso_date(
    value,
    label,
):
    value = str(
        value or ""
    ).strip()

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d",
        ).date()

    except ValueError as exc:
        raise ValueError(
            f"{label} must be YYYY-MM-DD."
        ) from exc


# ============================================================
# ACCESS
#
# ADMIN:
#   All CNC/VMC OEE
#
# SUPERVISOR:
#   Only assigned CNC/VMC processes
#
# OPERATOR:
#   Dashboard denied
# ============================================================

def _access_scope(cursor):

    role = (
        session.get("role")
        or ""
    ).strip().lower()

    user_id = session.get(
        "user_id"
    )

    if role not in (
        "admin",
        "supervisor",
    ):
        raise PermissionError(
            "OEE Dashboard access is available "
            "only to Admin and CNC/VMC supervisors."
        )

    if not user_id:
        raise PermissionError(
            "Logged-in user session is "
            "missing the user ID."
        )


    where = []
    params = []

    access = {
        "role": role,
        "user_id": user_id,
        "scope": "all_cnc_vmc",
        "processes": [],
    }


    # --------------------------------------------------------
    # SUPERVISOR PROCESS RESTRICTION
    # --------------------------------------------------------

    if role == "supervisor":

        cursor.execute(
            """
            SELECT process_name
            FROM supervisor_process_access
            WHERE user_id = %s
            ORDER BY process_name
            """,
            (user_id,),
        )


        processes = []


        for row in cursor.fetchall():

            key = _process_key(
                row.get(
                    "process_name"
                )
            )


            if (
                key.startswith(
                    "cnc machining"
                )
                or
                key.startswith(
                    "vmc machining"
                )
            ):
                processes.append(
                    key
                )


        processes = sorted(
            set(processes)
        )


        if not processes:

            raise PermissionError(
                "OEE Dashboard access is available "
                "only to supervisors assigned to "
                "CNC/VMC machining processes."
            )


        placeholders = ", ".join(
            ["%s"] * len(
                processes
            )
        )


        where.append(
            "LOWER(TRIM(oe.process_name)) "
            f"IN ({placeholders})"
        )


        params.extend(
            processes
        )


        access[
            "scope"
        ] = (
            "assigned_cnc_vmc_processes"
        )

        access[
            "processes"
        ] = processes


    return (
        role,
        where,
        params,
        access,
    )


# ============================================================
# COMMON DASHBOARD FILTERS
# ============================================================

def _base_filters(cursor):

    (
        role,
        access_where,
        access_params,
        access,
    ) = _access_scope(
        cursor
    )


    where = [
        "oe.record_status = 'active'",
        "oe.machine_category IN ('CNC', 'VMC')",
    ]

    where.extend(
        access_where
    )

    params = list(
        access_params
    )


    # --------------------------------------------------------
    # TEST DATA PROTECTION
    #
    # Excel-validation records created during OEE testing
    # must not pollute the management dashboard.
    #
    # Admin can temporarily call:
    #
    # ?include_test=1
    #
    # during dashboard development if required.
    # --------------------------------------------------------

    include_test = (
        request.args.get(
            "include_test",
            "",
        ).strip()
        == "1"
    )


    if not (
        role == "admin"
        and include_test
    ):

        where.append(
            "COALESCE(oe.remarks, '') "
            "NOT LIKE 'EXCEL_TEST_%'"
        )


    # --------------------------------------------------------
    # MACHINE FILTER
    # --------------------------------------------------------

    machine_id = (
        request.args.get(
            "machine_id",
            "",
        ).strip()
    )


    if machine_id:

        try:
            machine_id = int(
                machine_id
            )

        except ValueError as exc:
            raise ValueError(
                "Invalid machine_id."
            ) from exc


        where.append(
            "oe.machine_id = %s"
        )

        params.append(
            machine_id
        )


    # --------------------------------------------------------
    # SHIFT FILTER
    # --------------------------------------------------------

    shift_name = (
        request.args.get(
            "shift_name",
            "",
        ).strip()
    )


    if shift_name:

        if shift_name not in (
            "1",
            "2",
        ):
            raise ValueError(
                "shift_name must be 1 or 2."
            )


        where.append(
            "TRIM(oe.shift_name) = %s"
        )

        params.append(
            shift_name
        )


    return (
        where,
        params,
        access,
        include_test,
    )


# ============================================================
# REPORT PERIOD
#
# Excel behaviour:
# Latest month based on MAX Date.
#
# API can later also receive:
#
# ?from_date=2026-08-01&to_date=2026-08-20
#
# Existing sidebar date filter can later map to both.
# ============================================================

def _report_period(
    cursor,
    base_where,
    base_params,
):

    from_date = _iso_date(
        request.args.get(
            "from_date"
        ),
        "From Date",
    )


    to_date = _iso_date(
        request.args.get(
            "to_date"
        ),
        "To Date",
    )


    # Single-date request
    if (
        from_date
        and not to_date
    ):
        to_date = from_date


    if (
        to_date
        and not from_date
    ):
        from_date = to_date


    if (
        from_date
        and to_date
    ):

        if from_date > to_date:

            raise ValueError(
                "From Date cannot be after To Date."
            )


        return (
            from_date,
            to_date,
            "requested",
        )


    # --------------------------------------------------------
    # Excel default:
    # Start = first day of latest month
    # End   = maximum available entry date
    # --------------------------------------------------------

    cursor.execute(
        f"""
        SELECT
            MAX(
                oe.entry_date
            ) AS max_date

        FROM oee_entries oe

        WHERE {
            " AND ".join(
                base_where
            )
        }
        """,
        tuple(
            base_params
        ),
    )


    max_date = (
        cursor.fetchone()
        or {}
    ).get(
        "max_date"
    )


    if not max_date:

        return (
            None,
            None,
            "latest_month",
        )


    if isinstance(
        max_date,
        datetime,
    ):
        max_date = (
            max_date.date()
        )


    return (
        max_date.replace(
            day=1
        ),
        max_date,
        "latest_month",
    )


# ============================================================
# LOSS AGGREGATION
#
# IMPORTANT:
# Total Dashboard Loss must sum A1-A27 ONCE.
#
# We do NOT use:
# oee_entries.total_loss_minutes
#
# because certain Excel machine profiles contain AR/PR
# overlap. The detailed loss table is the clean source.
# ============================================================

def _loss_cte():

    return """
        WITH loss_by_entry AS (

            SELECT
                oel.oee_entry_id,

                SUM(
                    COALESCE(
                        oel.loss_minutes,
                        0
                    )
                ) AS detailed_loss_minutes,

                SUM(
                    CASE
                        WHEN UPPER(
                            TRIM(
                                oel.loss_code_snapshot
                            )
                        ) = 'A1'

                        THEN COALESCE(
                            oel.loss_minutes,
                            0
                        )

                        ELSE 0
                    END
                ) AS explicit_no_operator_minutes

            FROM oee_entry_losses oel

            GROUP BY
                oel.oee_entry_id
        )
    """


# ============================================================
# ADJUSTED NO-OPERATOR LOSS
#
# Excel methodology:
#
# Explicit A1
# OR
# Planned - Run when operator = NO OPERATOR
#
# capped at Planned Minutes.
# ============================================================

def _adjusted_no_operator_sql():

    return """
        LEAST(

            COALESCE(
                oe.planned_minutes,
                0
            ),

            GREATEST(

                COALESCE(
                    loss_by_entry.explicit_no_operator_minutes,
                    0
                ),

                CASE

                    WHEN LOWER(
                        REPLACE(
                            TRIM(
                                COALESCE(
                                    oe.operator_name,
                                    ''
                                )
                            ),
                            '-',
                            ' '
                        )
                    )
                    IN (
                        'no operator',
                        'operator absent'
                    )

                    THEN GREATEST(

                        COALESCE(
                            oe.planned_minutes,
                            0
                        )
                        -
                        COALESCE(
                            oe.run_minutes,
                            0
                        ),

                        0
                    )

                    ELSE 0

                END
            )
        )
    """


# ============================================================
# EXCEL OVERVIEW FORMULAS
#
# Availability:
#   Run Minutes / Planned Minutes
#
# Plan Achievement:
#   Actual Qty / Target Qty
#
# Performance Used:
#   MIN(MAX(Plan Achievement,0),1)
#
# Quality:
#   Good Qty / Actual Qty
#
# OEE:
#   Availability x Performance Used x Quality
# ============================================================

def _metric_block(
    planned_minutes=0,
    run_minutes=0,
    target_qty=0,
    actual_qty=0,
    good_qty=0,
    rejected_qty=0,
    rework_qty=0,
    detailed_loss_minutes=0,
    no_operator_minutes=0,
):

    planned_minutes = _f(
        planned_minutes
    )

    run_minutes = _f(
        run_minutes
    )

    target_qty = _f(
        target_qty
    )

    actual_qty = _f(
        actual_qty
    )

    good_qty = _f(
        good_qty
    )

    rejected_qty = _f(
        rejected_qty
    )

    rework_qty = _f(
        rework_qty
    )

    detailed_loss_minutes = _f(
        detailed_loss_minutes
    )

    no_operator_minutes = _f(
        no_operator_minutes
    )


    availability = _ratio(
        run_minutes,
        planned_minutes,
    )


    plan_achievement = _ratio(
        actual_qty,
        target_qty,
    )


    performance_used = min(
        max(
            plan_achievement,
            0.0,
        ),
        1.0,
    )


    quality = _ratio(
        good_qty,
        actual_qty,
    )


    oee = (
        availability
        *
        performance_used
        *
        quality
    )


    return {

        "planned_minutes":
            planned_minutes,

        "run_minutes":
            run_minutes,

        "target_qty":
            target_qty,

        "actual_qty":
            actual_qty,

        "good_qty":
            good_qty,

        "rejected_qty":
            rejected_qty,

        "rework_qty":
            rework_qty,

        "detailed_loss_minutes":
            detailed_loss_minutes,

        "total_loss_hours":
            detailed_loss_minutes
            / 60.0,

        "no_operator_minutes":
            no_operator_minutes,

        "no_operator_hours":
            no_operator_minutes
            / 60.0,

        "availability":
            availability,

        "plan_achievement":
            plan_achievement,

        "performance_used":
            performance_used,

        "quality":
            quality,

        "oee":
            oee,

        "production_gap":
            actual_qty
            -
            target_qty,
    }


# ============================================================
# OVERALL KPI CARDS
# ============================================================

def _overall(
    cursor,
    where_sql,
    params,
):

    no_operator_sql = (
        _adjusted_no_operator_sql()
    )


    cursor.execute(

        _loss_cte()

        +

        f"""
        SELECT

            COUNT(*) AS entry_count,

            COALESCE(
                SUM(
                    oe.planned_minutes
                ),
                0
            ) AS planned_minutes,

            COALESCE(
                SUM(
                    oe.run_minutes
                ),
                0
            ) AS run_minutes,

            COALESCE(
                SUM(
                    oe.target_qty
                ),
                0
            ) AS target_qty,

            COALESCE(
                SUM(
                    oe.total_qty
                ),
                0
            ) AS actual_qty,

            COALESCE(
                SUM(
                    oe.ok_qty
                ),
                0
            ) AS good_qty,

            COALESCE(
                SUM(
                    oe.rejected_qty
                ),
                0
            ) AS rejected_qty,

            COALESCE(
                SUM(
                    oe.hold_qty
                ),
                0
            ) AS rework_qty,

            COALESCE(
                SUM(
                    COALESCE(
                        loss_by_entry.detailed_loss_minutes,
                        0
                    )
                ),
                0
            ) AS detailed_loss_minutes,

            COALESCE(
                SUM(
                    {no_operator_sql}
                ),
                0
            ) AS no_operator_minutes

        FROM oee_entries oe

        LEFT JOIN loss_by_entry
          ON loss_by_entry.oee_entry_id
             =
             oe.id

        WHERE {where_sql}
        """,

        tuple(
            params
        ),
    )


    row = (
        cursor.fetchone()
        or {}
    )


    result = _metric_block(

        planned_minutes=
            row.get(
                "planned_minutes"
            ),

        run_minutes=
            row.get(
                "run_minutes"
            ),

        target_qty=
            row.get(
                "target_qty"
            ),

        actual_qty=
            row.get(
                "actual_qty"
            ),

        good_qty=
            row.get(
                "good_qty"
            ),

        rejected_qty=
            row.get(
                "rejected_qty"
            ),

        rework_qty=
            row.get(
                "rework_qty"
            ),

        detailed_loss_minutes=
            row.get(
                "detailed_loss_minutes"
            ),

        no_operator_minutes=
            row.get(
                "no_operator_minutes"
            ),
    )


    result[
        "entry_count"
    ] = int(
        row.get(
            "entry_count"
        )
        or 0
    )


    return result


# ============================================================
# MACHINE + DATE + SHIFT AGGREGATION
#
# Used for:
#
# - Day/Night shift summary
# - active days
# - active machines
# - full no-operator offs
# - manpower
# - daily trend
# ============================================================

def _machine_shift_rows(
    cursor,
    where_sql,
    params,
):

    no_operator_sql = (
        _adjusted_no_operator_sql()
    )


    cursor.execute(

        _loss_cte()

        +

        f"""
        SELECT

            oe.entry_date,

            TRIM(
                COALESCE(
                    oe.shift_name,
                    ''
                )
            ) AS shift_name,

            oe.machine_id,

            MAX(
                oe.machine_no
            ) AS machine_no,

            MAX(
                oe.machine_name
            ) AS machine_name,

            COALESCE(
                SUM(
                    oe.planned_minutes
                ),
                0
            ) AS planned_minutes,

            COALESCE(
                SUM(
                    oe.run_minutes
                ),
                0
            ) AS run_minutes,

            COALESCE(
                SUM(
                    oe.target_qty
                ),
                0
            ) AS target_qty,

            COALESCE(
                SUM(
                    oe.total_qty
                ),
                0
            ) AS actual_qty,

            COALESCE(
                SUM(
                    oe.ok_qty
                ),
                0
            ) AS good_qty,

            COALESCE(
                SUM(
                    oe.rejected_qty
                ),
                0
            ) AS rejected_qty,

            COALESCE(
                SUM(
                    oe.hold_qty
                ),
                0
            ) AS rework_qty,

            COALESCE(
                SUM(
                    {no_operator_sql}
                ),
                0
            ) AS no_operator_minutes

        FROM oee_entries oe

        LEFT JOIN loss_by_entry
          ON loss_by_entry.oee_entry_id
             =
             oe.id

        WHERE {where_sql}

        GROUP BY

            oe.entry_date,

            TRIM(
                COALESCE(
                    oe.shift_name,
                    ''
                )
            ),

            oe.machine_id

        ORDER BY

            oe.entry_date,

            shift_name,

            oe.machine_id
        """,

        tuple(
            params
        ),
    )


    return cursor.fetchall()


# ============================================================
# PERIOD DATE LIST
# ============================================================

def _dates(
    from_date,
    to_date,
):

    if (
        not from_date
        or not to_date
    ):
        return []


    days = (
        to_date
        -
        from_date
    ).days + 1


    return [

        from_date
        +
        timedelta(
            days=index
        )

        for index
        in range(
            days
        )
    ]


# ============================================================
# DAY / NIGHT SHIFT SUMMARY
# ============================================================

def _shift_summary(
    rows,
    from_date,
    to_date,
):

    report_dates = _dates(
        from_date,
        to_date,
    )


    output = []


    for shift in (
        "1",
        "2",
    ):


        items = [

            row

            for row
            in rows

            if str(
                row.get(
                    "shift_name"
                )
                or ""
            ).strip()
            ==
            shift
        ]


        planned = sum(
            _f(
                row.get(
                    "planned_minutes"
                )
            )
            for row in items
        )


        run = sum(
            _f(
                row.get(
                    "run_minutes"
                )
            )
            for row in items
        )


        target = sum(
            _f(
                row.get(
                    "target_qty"
                )
            )
            for row in items
        )


        actual = sum(
            _f(
                row.get(
                    "actual_qty"
                )
            )
            for row in items
        )


        good = sum(
            _f(
                row.get(
                    "good_qty"
                )
            )
            for row in items
        )


        no_operator = sum(
            _f(
                row.get(
                    "no_operator_minutes"
                )
            )
            for row in items
        )


        planned_dates = {

            row[
                "entry_date"
            ]

            for row
            in items

            if _f(
                row.get(
                    "planned_minutes"
                )
            ) > 0
        }


        active_dates = {

            row[
                "entry_date"
            ]

            for row
            in items

            if _f(
                row.get(
                    "run_minutes"
                )
            ) > 0
        }


        active_machines = {

            row[
                "machine_id"
            ]

            for row
            in items

            if _f(
                row.get(
                    "run_minutes"
                )
            ) > 0
        }


        # ----------------------------------------------------
        # Excel:
        #
        # Full No-Operator Off =
        #
        # Machine/date/shift Run = 0
        # and No-Operator >=95% Planned
        # ----------------------------------------------------

        full_no_operator_offs = sum(

            1

            for row
            in items

            if (

                _f(
                    row.get(
                        "planned_minutes"
                    )
                ) > 0

                and

                _f(
                    row.get(
                        "run_minutes"
                    )
                ) == 0

                and

                _f(
                    row.get(
                        "no_operator_minutes"
                    )
                )
                >=
                (
                    0.95

                    *

                    _f(
                        row.get(
                            "planned_minutes"
                        )
                    )
                )
            )
        )


        availability = _ratio(
            run,
            planned,
        )


        plan_achievement = _ratio(
            actual,
            target,
        )


        performance_used = min(
            max(
                plan_achievement,
                0.0,
            ),
            1.0,
        )


        quality = _ratio(
            good,
            actual,
        )


        oee = (
            availability
            *
            performance_used
            *
            quality
        )


        # ====================================================
        # MANPOWER GAP
        #
        # Excel:
        # Operator Gap =
        # No-Operator Minutes / 660
        # ====================================================

        daily_gap = []


        for current_date in report_dates:

            no_operator_day = sum(

                _f(
                    row.get(
                        "no_operator_minutes"
                    )
                )

                for row
                in items

                if row.get(
                    "entry_date"
                )
                ==
                current_date
            )


            daily_gap.append(
                no_operator_day
                /
                DEFAULT_SHIFT_MINUTES
            )


        impacted = [

            value

            for value
            in daily_gap

            if value > 0
        ]


        average_gap = (

            sum(
                daily_gap
            )
            /
            len(
                report_dates
            )

            if report_dates

            else 0.0
        )


        baseline_relief = math.ceil(

            average_gap

            *

            (
                1.0
                +
                HIRING_RELIEF_FACTOR
            )
        )


        sorted_gap = sorted(
            daily_gap,
            reverse=True,
        )


        # ----------------------------------------------------
        # Exact CURRENT workbook formula:
        #
        # 0 impacted days -> 0
        # 1 impacted day  -> MAX
        # >1 impacted     -> second largest
        #
        # H277/H278 then ROUNDUP this value.
        # ----------------------------------------------------

        if not impacted:

            percentile_gap = 0.0


        elif len(
            impacted
        ) == 1:

            percentile_gap = (

                sorted_gap[0]

                if sorted_gap

                else 0.0
            )


        else:

            percentile_gap = (

                sorted_gap[1]

                if len(
                    sorted_gap
                ) > 1

                else 0.0
            )


        output.append({

            "shift_name":
                shift,

            "shift_label":
                (
                    "DAY SHIFT (1)"
                    if shift == "1"
                    else
                    "NIGHT SHIFT (2)"
                ),

            "planned_days":
                len(
                    planned_dates
                ),

            "active_days":
                len(
                    active_dates
                ),

            "active_machines":
                len(
                    active_machines
                ),

            "planned_hours":
                planned
                / 60.0,

            "running_hours":
                run
                / 60.0,

            "no_operator_hours":
                no_operator
                / 60.0,

            "full_no_operator_offs":
                full_no_operator_offs,

            "target_qty":
                target,

            "actual_qty":
                actual,

            "availability":
                availability,

            "plan_achievement":
                plan_achievement,

            "quality":
                quality,

            "oee":
                oee,

            "manpower": {

                "analysed_days":
                    len(
                        report_dates
                    ),

                "impacted_days":
                    len(
                        impacted
                    ),

                "average_daily_gap":
                    average_gap,

                "baseline_plus_15pct_relief":
                    baseline_relief,

                "percentile_gap":
                    percentile_gap,

                "recommended_hires":
                    math.ceil(
                        percentile_gap
                    ),

                "peak_daily_gap":
                    math.ceil(
                        max(
                            daily_gap,
                            default=0.0,
                        )
                    ),
            },
        })


    return output


# ============================================================
# DAILY OEE vs PLAN ACHIEVEMENT CHART DATA
# ============================================================

def _daily_trend(
    rows,
    from_date,
    to_date,
):

    result = []


    for current_date in _dates(
        from_date,
        to_date,
    ):


        items = [

            row

            for row
            in rows

            if row.get(
                "entry_date"
            )
            ==
            current_date
        ]


        planned = sum(
            _f(
                row.get(
                    "planned_minutes"
                )
            )
            for row in items
        )


        run = sum(
            _f(
                row.get(
                    "run_minutes"
                )
            )
            for row in items
        )


        target = sum(
            _f(
                row.get(
                    "target_qty"
                )
            )
            for row in items
        )


        actual = sum(
            _f(
                row.get(
                    "actual_qty"
                )
            )
            for row in items
        )


        good = sum(
            _f(
                row.get(
                    "good_qty"
                )
            )
            for row in items
        )


        availability = _ratio(
            run,
            planned,
        )


        plan_achievement = _ratio(
            actual,
            target,
        )


        performance_used = min(
            max(
                plan_achievement,
                0.0,
            ),
            1.0,
        )


        quality = _ratio(
            good,
            actual,
        )


        result.append({

            "date":
                current_date,

            "target_qty":
                target,

            "actual_qty":
                actual,

            "production_gap":
                actual
                -
                target,

            "availability":
                availability,

            "plan_achievement":
                plan_achievement,

            "quality":
                quality,

            "oee":
                availability
                *
                performance_used
                *
                quality,
        })


    return result


# ============================================================
# API
#
# GET /api/oee-dashboard/overview
#
# Optional:
#
# ?from_date=2026-08-01
# &to_date=2026-08-20
# &machine_id=17
# &shift_name=1
#
# Admin testing only:
#
# &include_test=1
# ============================================================

@oee_dashboard_bp.route(
    "/api/oee-dashboard/overview",
    methods=["GET"],
)
def oee_dashboard_overview():

    conn = None
    cursor = None


    try:

        conn = get_connection()


        conn.set_charset_collation(
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )


        cursor = conn.cursor(
            dictionary=True
        )


        (
            base_where,
            base_params,
            access,
            include_test,
        ) = _base_filters(
            cursor
        )


        (
            from_date,
            to_date,
            period_mode,
        ) = _report_period(
            cursor,
            base_where,
            base_params,
        )


        # ----------------------------------------------------
        # NO DATA
        # ----------------------------------------------------

        if (
            not from_date
            or not to_date
        ):

            return _jsonify(
                _json_safe({

                    "success": True,

                    "access":
                        access,

                    "report_period": {

                        "from_date":
                            None,

                        "to_date":
                            None,

                        "mode":
                            period_mode,
                    },

                    "overview": {

                        **_metric_block(),

                        "entry_count":
                            0,

                        "recommended_hiring":
                            0,
                    },

                    "shift_summary":
                        [],

                    "daily_trend":
                        [],

                    "filters": {

                        "include_test":
                            include_test,
                    },
                })
            )


        # ----------------------------------------------------
        # APPLY PERIOD
        # ----------------------------------------------------

        where = list(
            base_where
        )


        params = list(
            base_params
        )


        where.extend([
            "oe.entry_date >= %s",
            "oe.entry_date <= %s",
        ])


        params.extend([
            from_date,
            to_date,
        ])


        where_sql = " AND ".join(
            where
        )


        # ----------------------------------------------------
        # OVERVIEW KPI CARDS
        # ----------------------------------------------------

        overview = _overall(
            cursor,
            where_sql,
            params,
        )


        # ----------------------------------------------------
        # DAY / NIGHT + DAILY DATA
        # ----------------------------------------------------

        machine_shift_rows = (
            _machine_shift_rows(
                cursor,
                where_sql,
                params,
            )
        )


        shift_summary = (
            _shift_summary(
                machine_shift_rows,
                from_date,
                to_date,
            )
        )


        daily_trend = (
            _daily_trend(
                machine_shift_rows,
                from_date,
                to_date,
            )
        )


        # ----------------------------------------------------
        # OVERALL RECOMMENDED HIRING
        # Excel B24 = Day Hires + Night Hires
        # ----------------------------------------------------

        overview[
            "recommended_hiring"
        ] = sum(

            int(
                shift.get(
                    "manpower",
                    {}
                ).get(
                    "recommended_hires",
                    0
                )
                or 0
            )

            for shift
            in shift_summary
        )


        # ----------------------------------------------------
        # PERIOD LABEL
        # ----------------------------------------------------

        if (
            from_date.year
            ==
            to_date.year

            and

            from_date.month
            ==
            to_date.month
        ):

            period_label = (
                from_date.strftime(
                    "%B %Y"
                )
            )

        else:

            period_label = (
                f"{from_date.isoformat()} "
                f"to "
                f"{to_date.isoformat()}"
            )


        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        return _jsonify(
            _json_safe({

                "success": True,

                "access":
                    access,

                "report_period": {

                    "from_date":
                        from_date,

                    "to_date":
                        to_date,

                    "mode":
                        period_mode,

                    "label":
                        period_label,
                },

                "overview":
                    overview,

                "shift_summary":
                    shift_summary,

                "daily_trend":
                    daily_trend,

                "filters": {

                    "machine_id":
                        request.args.get(
                            "machine_id",
                            "",
                        ).strip()
                        or None,

                    "shift_name":
                        request.args.get(
                            "shift_name",
                            "",
                        ).strip()
                        or None,

                    "include_test":
                        include_test,
                },

                "excel_reference": {

                    "sheet":
                        "OEE Dashboard",

                    "availability":
                        (
                            "Run Minutes / "
                            "Planned Minutes"
                        ),

                    "plan_achievement":
                        (
                            "Actual Qty / "
                            "Target Qty"
                        ),

                    "performance_used":
                        (
                            "Plan Achievement "
                            "capped at 100%"
                        ),

                    "quality":
                        (
                            "Good Qty / "
                            "Actual Qty"
                        ),

                    "oee":
                        (
                            "Availability x "
                            "Performance Used x "
                            "Quality"
                        ),

                    "full_no_operator_off":
                        (
                            "Machine/date/shift "
                            "Run = 0 and adjusted "
                            "No-Operator >= 95% "
                            "of Planned"
                        ),
                },

                "notes": [

                    (
                        "Dashboard is read-only. "
                        "It does not call or modify "
                        "OEE calculation or "
                        "persistence code."
                    ),

                    (
                        "EXCEL_TEST_ validation "
                        "records are excluded from "
                        "management results by default."
                    ),

                    (
                        "The current Excel H277/H278 "
                        "Recommended Hires formula uses "
                        "the percentile-gap result. "
                        "The workbook methodology sheet "
                        "also mentions baseline +15% "
                        "relief; both values are returned "
                        "per shift without silently "
                        "changing the Excel logic."
                    ),
                ],
            })
        )


    except PermissionError as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            403,
        )


    except ValueError as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            400,
        )


    except Exception as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            500,
        )


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()



# ============================================================
# OEE_DASHBOARD_PAGE_V1
# Standalone dashboard page.
# Does not depend on base.html or existing JMS UI files.
# ============================================================

@oee_dashboard_bp.route(
    "/oee-dashboard",
    methods=["GET"],
)
def oee_dashboard_page():

    role = (
        session.get("role")
        or ""
    ).strip().lower()

    user_id = session.get(
        "user_id"
    )


    if (
        role not in (
            "admin",
            "supervisor",
        )
        or not user_id
    ):
        return Response(
            "OEE Dashboard access denied.",
            status=403,
            content_type="text/plain; charset=utf-8",
        )


    # Supervisor must have at least one
    # CNC/VMC machining process assignment.
    if role == "supervisor":

        conn = None
        cursor = None

        try:

            conn = get_connection()

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT 1

                FROM supervisor_process_access

                WHERE user_id = %s

                  AND (
                        LOWER(TRIM(process_name))
                            LIKE 'cnc machining%%'

                        OR

                        LOWER(TRIM(process_name))
                            LIKE 'vmc machining%%'
                  )

                LIMIT 1
                """,
                (user_id,),
            )


            if cursor.fetchone() is None:

                return Response(
                    (
                        "OEE Dashboard access is "
                        "available only to CNC/VMC "
                        "supervisors."
                    ),
                    status=403,
                    content_type=(
                        "text/plain; charset=utf-8"
                    ),
                )

        finally:

            if cursor:
                cursor.close()

            if conn:
                conn.close()


    return render_template(
        "oee_dashboard.html",
    )



# ============================================================
# OEE_DASHBOARD_REMAINING_CHARTS_V1
# ============================================================


def _dashboard_period_where(cursor):

    (
        base_where,
        base_params,
        access,
        include_test,
    ) = _base_filters(cursor)


    (
        from_date,
        to_date,
        period_mode,
    ) = _report_period(
        cursor,
        base_where,
        base_params,
    )


    if (
        not from_date
        or not to_date
    ):
        return (
            None,
            None,
            None,
            [],
            access,
            period_mode,
        )


    where = list(
        base_where
    )

    params = list(
        base_params
    )


    where.extend([
        "oe.entry_date >= %s",
        "oe.entry_date <= %s",
    ])


    params.extend([
        from_date,
        to_date,
    ])


    return (
        from_date,
        to_date,
        " AND ".join(where),
        params,
        access,
        period_mode,
    )



# ============================================================
# COMPLETE LOSS ANALYSIS
# ============================================================

@oee_dashboard_bp.route(
    "/api/oee-dashboard/losses",
    methods=["GET"],
)
def oee_dashboard_losses():

    conn = None
    cursor = None


    try:

        conn = get_connection()

        conn.set_charset_collation(
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )

        cursor = conn.cursor(
            dictionary=True
        )


        (
            from_date,
            to_date,
            where_sql,
            params,
            access,
            period_mode,
        ) = _dashboard_period_where(
            cursor
        )


        # ----------------------------------------------------
        # LOSS MASTER
        # Always return A1-A27 even when a loss is zero.
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                loss_code,
                loss_name,
                loss_category,
                display_order

            FROM oee_loss_types

            WHERE is_active = 1

            ORDER BY display_order
            """
        )


        master_rows = (
            cursor.fetchall()
        )


        losses = {}


        for row in master_rows:

            code = str(
                row.get(
                    "loss_code"
                )
                or ""
            ).strip().upper()


            losses[code] = {

                "loss_code":
                    code,

                "loss_name":
                    row.get(
                        "loss_name"
                    )
                    or code,

                "classification":
                    row.get(
                        "loss_category"
                    )
                    or "",

                "display_order":
                    int(
                        row.get(
                            "display_order"
                        )
                        or 0
                    ),

                "loss_minutes":
                    0.0,

                "events":
                    0,

                "machine_totals":
                    {},

                "shift_totals":
                    {},

                "categories":
                    set(),

            }


        if (
            not from_date
            or not to_date
        ):

            output = []


            for item in losses.values():

                output.append({

                    "loss_code":
                        item["loss_code"],

                    "loss_name":
                        item["loss_name"],

                    "classification":
                        item["classification"],

                    "display_order":
                        item["display_order"],

                    "loss_minutes":
                        0,

                    "loss_hours":
                        0,

                    "events":
                        0,

                    "machines_affected":
                        0,

                    "top_machine":
                        None,

                    "top_shift":
                        None,

                    "share_of_total":
                        0,

                })


            return _jsonify(
                _json_safe({

                    "success": True,

                    "access":
                        access,

                    "report_period": {
                        "from_date": None,
                        "to_date": None,
                        "mode": period_mode,
                    },

                    "summary": {
                        "total_loss_minutes": 0,
                        "total_loss_hours": 0,
                        "top_loss": None,
                    },

                    "data":
                        output,
                })
            )


        # ----------------------------------------------------
        # Loss details by Code + Machine + Shift
        # ----------------------------------------------------

        cursor.execute(
            f"""
            SELECT

                UPPER(
                    TRIM(
                        oel.loss_code_snapshot
                    )
                ) AS loss_code,

                MAX(
                    oel.loss_name_snapshot
                ) AS loss_name,

                MAX(
                    oel.loss_category_snapshot
                ) AS loss_category,

                oe.machine_id,

                MAX(
                    oe.machine_no
                ) AS machine_no,

                MAX(
                    oe.machine_name
                ) AS machine_name,

                TRIM(
                    COALESCE(
                        oe.shift_name,
                        ''
                    )
                ) AS shift_name,

                COALESCE(
                    SUM(
                        oel.loss_minutes
                    ),
                    0
                ) AS loss_minutes,

                SUM(
                    CASE
                        WHEN COALESCE(
                            oel.loss_minutes,
                            0
                        ) > 0
                        THEN 1
                        ELSE 0
                    END
                ) AS event_count

            FROM oee_entries oe

            JOIN oee_entry_losses oel
              ON oel.oee_entry_id = oe.id

            WHERE {where_sql}

            GROUP BY

                UPPER(
                    TRIM(
                        oel.loss_code_snapshot
                    )
                ),

                oe.machine_id,

                TRIM(
                    COALESCE(
                        oe.shift_name,
                        ''
                    )
                )

            ORDER BY
                loss_code,
                oe.machine_id,
                shift_name
            """,

            tuple(
                params
            ),
        )


        detail_rows = (
            cursor.fetchall()
        )


        for row in detail_rows:

            code = str(
                row.get(
                    "loss_code"
                )
                or ""
            ).strip().upper()


            if code not in losses:

                losses[code] = {

                    "loss_code":
                        code,

                    "loss_name":
                        row.get(
                            "loss_name"
                        )
                        or code,

                    "classification":
                        "",

                    "display_order":
                        999,

                    "loss_minutes":
                        0.0,

                    "events":
                        0,

                    "machine_totals":
                        {},

                    "shift_totals":
                        {},

                    "categories":
                        set(),

                }


            item = losses[
                code
            ]


            minutes = _f(
                row.get(
                    "loss_minutes"
                )
            )


            item[
                "loss_minutes"
            ] += minutes


            item[
                "events"
            ] += int(
                row.get(
                    "event_count"
                )
                or 0
            )


            category = str(
                row.get(
                    "loss_category"
                )
                or ""
            ).strip().upper()


            if category:

                item[
                    "categories"
                ].add(
                    category
                )


            if minutes > 0:

                machine_no = str(
                    row.get(
                        "machine_no"
                    )
                    or ""
                ).strip()


                machine_name = str(
                    row.get(
                        "machine_name"
                    )
                    or ""
                ).strip()


                machine_label = (
                    machine_no
                    +
                    (
                        f" - {machine_name}"
                        if machine_name
                        else ""
                    )
                )


                item[
                    "machine_totals"
                ][machine_label] = (

                    item[
                        "machine_totals"
                    ].get(
                        machine_label,
                        0.0
                    )

                    +

                    minutes
                )


                shift = str(
                    row.get(
                        "shift_name"
                    )
                    or ""
                ).strip()


                if shift:

                    item[
                        "shift_totals"
                    ][shift] = (

                        item[
                            "shift_totals"
                        ].get(
                            shift,
                            0.0
                        )

                        +

                        minutes
                    )


        total_loss_minutes = sum(

            item[
                "loss_minutes"
            ]

            for item
            in losses.values()
        )


        output = []


        for item in sorted(
            losses.values(),
            key=lambda x: (
                x[
                    "display_order"
                ],
                x[
                    "loss_code"
                ],
            ),
        ):


            categories = (
                item[
                    "categories"
                ]
            )


            if len(categories) == 1:

                classification = (
                    next(
                        iter(
                            categories
                        )
                    )
                )


            elif len(categories) > 1:

                classification = (
                    "AR / PR"
                )


            else:

                classification = (
                    item[
                        "classification"
                    ]
                )


            top_machine = None


            if item[
                "machine_totals"
            ]:

                top_machine = max(

                    item[
                        "machine_totals"
                    ].items(),

                    key=lambda pair:
                        pair[1],

                )[0]


            top_shift = None


            if item[
                "shift_totals"
            ]:

                top_shift = max(

                    item[
                        "shift_totals"
                    ].items(),

                    key=lambda pair:
                        pair[1],

                )[0]


            output.append({

                "loss_code":
                    item[
                        "loss_code"
                    ],

                "loss_name":
                    item[
                        "loss_name"
                    ],

                "classification":
                    classification,

                "display_order":
                    item[
                        "display_order"
                    ],

                "loss_minutes":
                    item[
                        "loss_minutes"
                    ],

                "loss_hours":
                    item[
                        "loss_minutes"
                    ]
                    / 60.0,

                "events":
                    item[
                        "events"
                    ],

                "machines_affected":
                    len(
                        item[
                            "machine_totals"
                        ]
                    ),

                "top_machine":
                    top_machine,

                "top_shift":
                    top_shift,

                "share_of_total":
                    (
                        item[
                            "loss_minutes"
                        ]
                        /
                        total_loss_minutes

                        if total_loss_minutes
                        else 0.0
                    ),

            })


        top_loss = None


        if output:

            top_item = max(

                output,

                key=lambda item:
                    item[
                        "loss_minutes"
                    ],
            )


            if (
                top_item[
                    "loss_minutes"
                ]
                > 0
            ):

                top_loss = {

                    "loss_code":
                        top_item[
                            "loss_code"
                        ],

                    "loss_name":
                        top_item[
                            "loss_name"
                        ],

                    "loss_hours":
                        top_item[
                            "loss_hours"
                        ],

                }


        return _jsonify(
            _json_safe({

                "success": True,

                "access":
                    access,

                "report_period": {
                    "from_date":
                        from_date,
                    "to_date":
                        to_date,
                    "mode":
                        period_mode,
                },

                "summary": {

                    "total_loss_minutes":
                        total_loss_minutes,

                    "total_loss_hours":
                        total_loss_minutes
                        / 60.0,

                    "top_loss":
                        top_loss,

                },

                "data":
                    output,

            })
        )


    except PermissionError as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            403,
        )


    except ValueError as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            400,
        )


    except Exception as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            500,
        )


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()



# ============================================================
# MACHINE OEE SCORECARD
# ============================================================

@oee_dashboard_bp.route(
    "/api/oee-dashboard/machines",
    methods=["GET"],
)
def oee_dashboard_machines():

    conn = None
    cursor = None


    try:

        conn = get_connection()

        conn.set_charset_collation(
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )

        cursor = conn.cursor(
            dictionary=True
        )


        (
            from_date,
            to_date,
            where_sql,
            params,
            access,
            period_mode,
        ) = _dashboard_period_where(
            cursor
        )


        if (
            not from_date
            or not to_date
        ):

            return _jsonify({

                "success": True,

                "access":
                    access,

                "report_period": {
                    "from_date": None,
                    "to_date": None,
                    "mode": period_mode,
                },

                "data": [],
                "top_oee": [],
                "top_loss": [],
            })


        no_operator_sql = (
            _adjusted_no_operator_sql()
        )


        cursor.execute(

            _loss_cte()

            +

            f"""
            SELECT

                oe.machine_id,

                MAX(
                    oe.machine_no
                ) AS machine_no,

                MAX(
                    oe.machine_name
                ) AS machine_name,

                MAX(
                    oe.machine_category
                ) AS machine_category,

                MAX(
                    oe.zone
                ) AS zone,

                COUNT(
                    DISTINCT oe.entry_date
                ) AS active_days,

                COUNT(
                    DISTINCT CONCAT(
                        oe.entry_date,
                        '|',
                        TRIM(
                            COALESCE(
                                oe.shift_name,
                                ''
                            )
                        )
                    )
                ) AS active_shifts,

                COALESCE(
                    SUM(
                        oe.planned_minutes
                    ),
                    0
                ) AS planned_minutes,

                COALESCE(
                    SUM(
                        oe.run_minutes
                    ),
                    0
                ) AS run_minutes,

                COALESCE(
                    SUM(
                        oe.target_qty
                    ),
                    0
                ) AS target_qty,

                COALESCE(
                    SUM(
                        oe.total_qty
                    ),
                    0
                ) AS actual_qty,

                COALESCE(
                    SUM(
                        oe.ok_qty
                    ),
                    0
                ) AS good_qty,

                COALESCE(
                    SUM(
                        oe.rejected_qty
                    ),
                    0
                ) AS rejected_qty,

                COALESCE(
                    SUM(
                        oe.hold_qty
                    ),
                    0
                ) AS rework_qty,

                COALESCE(
                    SUM(
                        COALESCE(
                            loss_by_entry.detailed_loss_minutes,
                            0
                        )
                    ),
                    0
                ) AS detailed_loss_minutes,

                COALESCE(
                    SUM(
                        {no_operator_sql}
                    ),
                    0
                ) AS no_operator_minutes

            FROM oee_entries oe

            LEFT JOIN loss_by_entry
              ON loss_by_entry.oee_entry_id
                 =
                 oe.id

            WHERE {where_sql}

            GROUP BY
                oe.machine_id

            ORDER BY
                MAX(oe.machine_no)
            """,

            tuple(
                params
            ),
        )


        rows = (
            cursor.fetchall()
        )


        machines = []


        for row in rows:

            metrics = _metric_block(

                planned_minutes=
                    row.get(
                        "planned_minutes"
                    ),

                run_minutes=
                    row.get(
                        "run_minutes"
                    ),

                target_qty=
                    row.get(
                        "target_qty"
                    ),

                actual_qty=
                    row.get(
                        "actual_qty"
                    ),

                good_qty=
                    row.get(
                        "good_qty"
                    ),

                rejected_qty=
                    row.get(
                        "rejected_qty"
                    ),

                rework_qty=
                    row.get(
                        "rework_qty"
                    ),

                detailed_loss_minutes=
                    row.get(
                        "detailed_loss_minutes"
                    ),

                no_operator_minutes=
                    row.get(
                        "no_operator_minutes"
                    ),
            )


            machines.append({

                "machine_id":
                    row.get(
                        "machine_id"
                    ),

                "machine_no":
                    row.get(
                        "machine_no"
                    ),

                "machine_name":
                    row.get(
                        "machine_name"
                    ),

                "machine_category":
                    row.get(
                        "machine_category"
                    ),

                "zone":
                    row.get(
                        "zone"
                    ),

                "active_days":
                    int(
                        row.get(
                            "active_days"
                        )
                        or 0
                    ),

                "active_shifts":
                    int(
                        row.get(
                            "active_shifts"
                        )
                        or 0
                    ),

                **metrics,

            })


        top_oee = sorted(

            machines,

            key=lambda machine:
                machine[
                    "oee"
                ],

            reverse=True,

        )[:10]


        top_loss = sorted(

            machines,

            key=lambda machine:
                machine[
                    "total_loss_hours"
                ],

            reverse=True,

        )[:10]


        return _jsonify(
            _json_safe({

                "success": True,

                "access":
                    access,

                "report_period": {
                    "from_date":
                        from_date,
                    "to_date":
                        to_date,
                    "mode":
                        period_mode,
                },

                "data":
                    machines,

                "top_oee":
                    top_oee,

                "top_loss":
                    top_loss,

            })
        )


    except PermissionError as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            403,
        )


    except ValueError as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            400,
        )


    except Exception as exc:

        return _jsonify(
            {
                "success": False,
                "error": str(exc),
            },
            500,
        )


    finally:

        if cursor:
            cursor.close()

        if conn:
            conn.close()
