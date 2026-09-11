"""
OEE Summary — reads from oee_entries + oee_entry_losses.

Access:
    Admin, Supervisor, Operator (Operator sees table only, no export)

Data source:
    oee_entries          — one row per completed job card entry
    oee_entry_losses     — per-entry loss breakdown (A1..A27)

All OEE metrics are stored pre-computed on each oee_entries row.
For group aggregates we SUM the time and quantity fields and recompute
the group ratio; we never average pre-computed ratios (which would be
mathematically wrong).

Routes:
    GET  /oee-machine-summary                              — page
    GET  /api/oee-machine-summary/kpi                      — KPI strip totals
    GET  /api/oee-machine-summary/machine-wise             — machine table
    GET  /api/oee-machine-summary/operator-wise            — operator table
    GET  /api/oee-machine-summary/drill-down               — entries + top losses
    GET  /api/oee-machine-summary/filters                  — dropdowns

Read-only.
"""

import json
from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from db import get_connection


oee_machine_summary_bp = Blueprint("oee_machine_summary", __name__)


# ============================================================
# HELPERS
# ============================================================

def _jsonify(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type="application/json; charset=utf-8",
    )


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _ratio(numerator, denominator):
    d = _f(denominator)
    return _f(numerator) / d if d else 0.0


def _pct(x):
    return round(_f(x) * 100.0, 1)


def _access_role():
    role = (session.get("role") or "").strip().lower()
    if role not in ("admin", "supervisor", "operator"):
        raise PermissionError(
            "OEE Summary is available to Admin, Supervisor and Operator only."
        )
    return role


def _can_export(role):
    return role in ("admin", "supervisor")


# ---- date helpers ------------------------------------------------

def _today():
    return date.today()


def _resolve_preset(preset):
    t = _today()
    p = (preset or "").strip().lower()

    if p == "today":
        return t, t
    if p == "yesterday":
        y = t - timedelta(days=1)
        return y, y
    if p == "this_week":
        start = t - timedelta(days=t.weekday())
        return start, t
    if p == "last_week":
        this_start = t - timedelta(days=t.weekday())
        last_end   = this_start - timedelta(days=1)
        last_start = last_end - timedelta(days=6)
        return last_start, last_end
    if p == "this_month":
        return t.replace(day=1), t
    if p == "last_month":
        first_this = t.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start, last_month_end
    return None, None


def _parse_dates():
    fmt = "%Y-%m-%d"
    fd_s = (request.args.get("from_date") or "").strip()
    td_s = (request.args.get("to_date")   or "").strip()

    fd = td = None
    try:
        if fd_s:
            fd = datetime.strptime(fd_s, fmt).date()
    except ValueError:
        fd = None
    try:
        if td_s:
            td = datetime.strptime(td_s, fmt).date()
    except ValueError:
        td = None

    if not fd and not td:
        p_fd, p_td = _resolve_preset(request.args.get("preset"))
        if p_fd:
            fd, td = p_fd, p_td

    if fd and not td:
        td = fd
    if td and not fd:
        fd = td

    if not fd or not td:
        t = _today()
        fd = t.replace(day=1)
        td = t

    if fd > td:
        fd, td = td, fd

    return fd, td


def _optional_filters():
    zone = (request.args.get("zone") or "").strip() or None

    mid_s = (request.args.get("machine_id") or "").strip()
    machine_id = None
    if mid_s:
        try:
            machine_id = int(mid_s)
        except ValueError:
            machine_id = None

    oid_s = (request.args.get("operator_master_id") or "").strip()
    operator_master_id = None
    if oid_s:
        try:
            operator_master_id = int(oid_s)
        except ValueError:
            operator_master_id = None

    return zone, machine_id, operator_master_id


def _shift_display(name):
    if not name:
        return ""
    s = str(name).strip()
    if any(s.lower().endswith(sfx) for sfx in ("st", "nd", "rd", "th")):
        return s
    lower = s.lower()
    if lower.startswith("shift "):
        s = s[6:].strip()
    if s.isdigit():
        n = int(s)
        suffix = "th"
        if n % 100 not in (11, 12, 13):
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"
    return name


def _oee_from_sums(planned, ar_loss, pr_loss, run, ok, rej, hold, target_qty=None):
    """
    Recompute AR / PR / QR / OEE from group-level sums.
    Aggregating ratios directly (averaging AR% across rows) is incorrect;
    aggregating the time/qty components and dividing here is correct.
    """
    planned  = _f(planned)
    ar_loss  = _f(ar_loss)
    pr_loss  = _f(pr_loss)
    run      = _f(run)
    ok_v     = _f(ok)
    rej_v    = _f(rej)
    hold_v   = _f(hold)
    total_qty = ok_v + rej_v + hold_v

    utilization = max(planned - ar_loss, 0.0)
    after_pr    = max(utilization - pr_loss, 0.0)

    ar  = _ratio(utilization, planned)
    pr  = _ratio(run, after_pr)
    qr  = _ratio(ok_v, total_qty) if total_qty else 1.0
    oee = ar * pr * qr

    plan_vs_actual = None
    tq = _f(target_qty) if target_qty is not None else 0.0
    if tq > 0:
        plan_vs_actual = total_qty / tq

    return {
        "planned_minutes":     round(planned, 2),
        "utilization_minutes": round(utilization, 2),
        "after_pr_minutes":    round(after_pr, 2),
        "run_minutes":         round(run, 2),
        "ar_loss_minutes":     round(ar_loss, 2),
        "pr_loss_minutes":     round(pr_loss, 2),
        "ok_qty":              int(ok_v),
        "rejected_qty":        int(rej_v),
        "hold_qty":            int(hold_v),
        "total_qty":           int(total_qty),
        "target_qty":          round(tq, 2) if target_qty is not None else None,
        "plan_vs_actual":      round(plan_vs_actual, 4) if plan_vs_actual is not None else None,
        "planned_hours":       round(planned / 60.0, 2),
        "run_hours":           round(run / 60.0, 2),
        "ar":                  ar,
        "pr":                  pr,
        "qr":                  qr,
        "oee":                 oee,
        "ar_pct":              _pct(ar),
        "pr_pct":              _pct(pr),
        "qr_pct":              _pct(qr),
        "oee_pct":             _pct(oee),
    }


# ============================================================
# PAGE ROUTE
# ============================================================

@oee_machine_summary_bp.route("/oee-machine-summary")
def oee_machine_summary_page():
    role = (session.get("role") or "").strip().lower()
    if role not in ("admin", "supervisor", "operator"):
        return redirect(url_for("auth.login"))

    return render_template(
        "oee_machine_summary.html",
        active_page="oee_machine_summary",
        can_export=_can_export(role),
    )


# ============================================================
# API — FILTER DROPDOWNS
# ============================================================

@oee_machine_summary_bp.route("/api/oee-machine-summary/filters")
def api_oee_machine_summary_filters():
    try:
        _access_role()

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)

        cur.execute(
            """
            SELECT DISTINCT zone
            FROM oee_machines
            WHERE is_active = 1
              AND zone IS NOT NULL
              AND TRIM(zone) <> ''
            ORDER BY zone
            """
        )
        zones = [r["zone"] for r in cur.fetchall()]

        cur.execute(
            """
            SELECT id, machine_no, machine_name, zone, machine_category
            FROM oee_machines
            WHERE is_active = 1
            ORDER BY machine_no
            """
        )
        machines = cur.fetchall()

        cur.execute(
            """
            SELECT id, employee_no, operator_name
            FROM oee_operator_master
            WHERE is_active = 1
            ORDER BY CAST(employee_no AS UNSIGNED), employee_no
            """
        )
        operators = cur.fetchall()

        cur.close()
        conn.close()

        return _jsonify({
            "zones":     zones,
            "machines":  machines,
            "operators": operators,
        })

    except PermissionError as exc:
        return _jsonify({"error": str(exc)}, 403)
    except Exception as exc:
        import traceback
        return _jsonify({"error": str(exc), "trace": traceback.format_exc()}, 500)


# ============================================================
# API — KPI STRIP
# ============================================================

@oee_machine_summary_bp.route("/api/oee-machine-summary/kpi")
def api_oee_machine_summary_kpi():
    try:
        _access_role()

        fd, td = _parse_dates()
        zone, machine_id, _ = _optional_filters()

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)

        where = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
            "e.activity_type IS NULL",
        ]
        params = [str(fd), str(td)]

        if zone:
            where.append("e.zone = %s")
            params.append(zone)
        if machine_id:
            where.append("e.machine_id = %s")
            params.append(machine_id)

        where_sql = " AND ".join(where)

        cur.execute(
            f"""
            SELECT
                COUNT(DISTINCT e.machine_id)             AS active_machines,
                COUNT(e.id)                              AS total_entries,
                COALESCE(SUM(e.planned_minutes), 0)      AS planned_min,
                COALESCE(SUM(e.utilization_minutes), 0)  AS utilization_min,
                COALESCE(SUM(e.after_pr_minutes), 0)     AS after_pr_min,
                COALESCE(SUM(e.run_minutes), 0)          AS run_min,
                COALESCE(SUM(e.ar_loss_minutes), 0)      AS ar_loss_min,
                COALESCE(SUM(e.pr_loss_minutes), 0)      AS pr_loss_min,
                COALESCE(SUM(e.ok_qty), 0)               AS ok_qty,
                COALESCE(SUM(e.rejected_qty), 0)         AS rej_qty,
                COALESCE(SUM(e.hold_qty), 0)             AS hold_qty
            FROM oee_entries e
            WHERE {where_sql}
            """,
            params,
        )
        row = cur.fetchone() or {}

        cur.execute("SELECT COUNT(*) AS c FROM oee_machines WHERE is_active = 1")
        total_machines = _int((cur.fetchone() or {}).get("c"))

        cur.close()
        conn.close()

        block = _oee_from_sums(
            planned=row.get("planned_min"),
            ar_loss=row.get("ar_loss_min"),
            pr_loss=row.get("pr_loss_min"),
            run=row.get("run_min"),
            ok=row.get("ok_qty"),
            rej=row.get("rej_qty"),
            hold=row.get("hold_qty"),
        )

        # ---- activity totals (Tool Room / Development) ----
        act_where = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
            "e.activity_type IS NOT NULL",
        ]
        act_params = [str(fd), str(td)]
        if zone:
            act_where.append("m.zone = %s")
            act_params.append(zone)
        if machine_id:
            act_where.append("e.machine_id = %s")
            act_params.append(machine_id)

        conn2 = get_connection()
        cur2  = conn2.cursor(dictionary=True)
        cur2.execute(
            f"""
            SELECT
                COALESCE(SUM(e.planned_minutes), 0)                     AS act_min,
                COALESCE(SUM(e.ar_loss_minutes + e.pr_loss_minutes), 0) AS act_loss,
                COUNT(e.id)                                              AS act_count
            FROM oee_entries e
            JOIN oee_machines m ON m.id = e.machine_id
            WHERE {' AND '.join(act_where)}
            """,
            act_params,
        )
        act_row = cur2.fetchone() or {}
        cur2.close(); conn2.close()

        loss_hours = (_f(row.get("ar_loss_min")) + _f(row.get("pr_loss_min"))) / 60.0

        kpi = {
            "period":          {"from_date": str(fd), "to_date": str(td)},
            "total_machines":  total_machines,
            "active_machines": _int(row.get("active_machines")),
            "total_sessions":  _int(row.get("total_entries")),   # kept key name for existing UI
            "ok_qty":          block["ok_qty"],
            "rejected_qty":    block["rejected_qty"],
            "hold_qty":        block["hold_qty"],
            "total_qty":       block["total_qty"],
            "planned_hours":   block["planned_hours"],
            "run_hours":       block["run_hours"],
            "loss_hours":      round(loss_hours, 2),
            "ar_pct":          block["ar_pct"],
            "pr_pct":          block["pr_pct"],
            "qr_pct":          block["qr_pct"],
            "oee_pct":         block["oee_pct"],
            "activity_min":      round(_f(act_row.get("act_min")), 2),
            "activity_loss_min": round(_f(act_row.get("act_loss")), 2),
            "activity_count":    _int(act_row.get("act_count")),
        }

        return _jsonify(kpi)

    except PermissionError as exc:
        return _jsonify({"error": str(exc)}, 403)
    except Exception as exc:
        import traceback
        return _jsonify({"error": str(exc), "trace": traceback.format_exc()}, 500)


# ============================================================
# API — MACHINE-WISE
# ============================================================

@oee_machine_summary_bp.route("/api/oee-machine-summary/machine-wise")
def api_oee_machine_summary_machine_wise():
    try:
        _access_role()

        fd, td = _parse_dates()
        zone, machine_id, _ = _optional_filters()

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)

        where_m  = ["m.is_active = 1"]
        params_m = []
        if zone:
            where_m.append("m.zone = %s")
            params_m.append(zone)
        if machine_id:
            where_m.append("m.id = %s")
            params_m.append(machine_id)

        cur.execute(
            f"""
            SELECT
                m.id                                     AS machine_id,
                m.machine_no                             AS machine_no,
                m.machine_name                           AS machine_name,
                m.machine_category                       AS machine_category,
                m.zone                                   AS zone,
                COUNT(e.id)                              AS entry_count,
                COALESCE(SUM(e.ok_qty), 0)               AS ok_qty,
                COALESCE(SUM(e.rejected_qty), 0)         AS rejected_qty,
                COALESCE(SUM(e.hold_qty), 0)             AS hold_qty,
                COALESCE(SUM(e.planned_minutes), 0)      AS planned_min,
                COALESCE(SUM(e.utilization_minutes), 0)  AS utilization_min,
                COALESCE(SUM(e.after_pr_minutes), 0)     AS after_pr_min,
                COALESCE(SUM(e.run_minutes), 0)          AS run_min,
                COALESCE(SUM(e.ar_loss_minutes), 0)      AS ar_loss_min,
                COALESCE(SUM(e.pr_loss_minutes), 0)      AS pr_loss_min,
                COALESCE(SUM(e.target_qty), 0)           AS target_qty
            FROM oee_machines m
            LEFT JOIN oee_entries e
                ON e.machine_id = m.id
               AND e.record_status = 'active'
               AND e.activity_type IS NULL
               AND e.entry_date BETWEEN %s AND %s
            WHERE {' AND '.join(where_m)}
            GROUP BY
                m.id, m.machine_no, m.machine_name,
                m.machine_category, m.zone
            ORDER BY m.machine_no
            """,
            [str(fd), str(td)] + params_m,
        )
        rows = cur.fetchall()

# ---- activity aggregation per machine ----
        act_where = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
            "e.activity_type IS NOT NULL",
        ]
        act_params = [str(fd), str(td)]
        if zone:
            act_where.append("m.zone = %s")
            act_params.append(zone)
        if machine_id:
            act_where.append("e.machine_id = %s")
            act_params.append(machine_id)

        cur.execute(
            f"""
            SELECT
                e.machine_id                                             AS machine_id,
                COALESCE(SUM(e.planned_minutes), 0)                     AS act_min,
                COALESCE(SUM(e.ar_loss_minutes + e.pr_loss_minutes), 0) AS act_loss,
                COUNT(e.id)                                              AS act_count
            FROM oee_entries e
            JOIN oee_machines m ON m.id = e.machine_id
            WHERE {' AND '.join(act_where)}
            GROUP BY e.machine_id
            """,
            act_params,
        )
        act_by_machine = {a["machine_id"]: a for a in cur.fetchall()}

        cur.close()
        conn.close()

        machines = []
        for r in rows:
            blk = _oee_from_sums(
                planned=r["planned_min"],
                ar_loss=r["ar_loss_min"],
                pr_loss=r["pr_loss_min"],
                run=r["run_min"],
                ok=r["ok_qty"],
                rej=r["rejected_qty"],
                hold=r["hold_qty"],
                target_qty=r["target_qty"],
            )
            blk["machine_id"]       = r["machine_id"]
            blk["machine_no"]       = r["machine_no"]
            blk["machine_name"]     = r["machine_name"]
            blk["machine_category"] = r["machine_category"]
            blk["zone"]             = r["zone"]
            blk["session_count"]    = _int(r["entry_count"])   # UI key kept
            act = act_by_machine.get(r["machine_id"], {})
            blk["activity_min"]      = round(_f(act.get("act_min", 0)), 2)
            blk["activity_loss_min"] = round(_f(act.get("act_loss", 0)), 2)
            blk["activity_count"]    = _int(act.get("act_count", 0))
            machines.append(blk)

        return _jsonify({
            "period":   {"from_date": str(fd), "to_date": str(td)},
            "machines": machines,
        })

    except PermissionError as exc:
        return _jsonify({"error": str(exc)}, 403)
    except Exception as exc:
        import traceback
        return _jsonify({"error": str(exc), "trace": traceback.format_exc()}, 500)


# ============================================================
# API — OPERATOR-WISE
# ============================================================

@oee_machine_summary_bp.route("/api/oee-machine-summary/operator-wise")
def api_oee_machine_summary_operator_wise():
    try:
        _access_role()

        fd, td = _parse_dates()
        zone, machine_id, operator_master_id = _optional_filters()

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)

        where_op  = ["o.is_active = 1"]
        params_op = []
        if operator_master_id:
            where_op.append("o.id = %s")
            params_op.append(operator_master_id)

        # entry-side filters (applied inside the LEFT JOIN condition)
        join_where = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
            "e.activity_type IS NULL",
        ]
        join_params = [str(fd), str(td)]

        if zone:
            join_where.append("e.zone = %s")
            join_params.append(zone)
        if machine_id:
            join_where.append("e.machine_id = %s")
            join_params.append(machine_id)

        cur.execute(
            f"""
            SELECT
                o.id                                     AS operator_master_id,
                o.employee_no                            AS employee_no,
                o.operator_name                          AS operator_name,
                COUNT(e.id)                              AS entry_count,
                COUNT(DISTINCT CONCAT(e.entry_date, '|', e.shift_name))
                                                         AS shift_count,
                COALESCE(SUM(e.ok_qty), 0)               AS ok_qty,
                COALESCE(SUM(e.rejected_qty), 0)         AS rejected_qty,
                COALESCE(SUM(e.hold_qty), 0)             AS hold_qty,
                COALESCE(SUM(e.planned_minutes), 0)      AS planned_min,
                COALESCE(SUM(e.utilization_minutes), 0)  AS utilization_min,
                COALESCE(SUM(e.after_pr_minutes), 0)     AS after_pr_min,
                COALESCE(SUM(e.run_minutes), 0)          AS run_min,
                COALESCE(SUM(e.ar_loss_minutes), 0)      AS ar_loss_min,
                COALESCE(SUM(e.pr_loss_minutes), 0)      AS pr_loss_min,
                COALESCE(SUM(e.target_qty), 0)           AS target_qty
            FROM oee_operator_master o
            LEFT JOIN oee_entries e
                ON e.operator_master_id = o.id
               AND {' AND '.join(join_where)}
            WHERE {' AND '.join(where_op)}
            GROUP BY o.id, o.employee_no, o.operator_name
            ORDER BY CAST(o.employee_no AS UNSIGNED), o.employee_no
            """,
            join_params + params_op,
        )
        rows = cur.fetchall()

# ---- activity aggregation per operator ----
        act_where = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
            "e.activity_type IS NOT NULL",
            "e.operator_master_id IS NOT NULL",
        ]
        act_params = [str(fd), str(td)]
        if zone:
            act_where.append("e.zone = %s")
            act_params.append(zone)
        if machine_id:
            act_where.append("e.machine_id = %s")
            act_params.append(machine_id)
        if operator_master_id:
            act_where.append("e.operator_master_id = %s")
            act_params.append(operator_master_id)

        cur.execute(
            f"""
            SELECT
                e.operator_master_id                                     AS operator_master_id,
                COALESCE(SUM(e.planned_minutes), 0)                     AS act_min,
                COALESCE(SUM(e.ar_loss_minutes + e.pr_loss_minutes), 0) AS act_loss,
                COUNT(e.id)                                              AS act_count
            FROM oee_entries e
            WHERE {' AND '.join(act_where)}
            GROUP BY e.operator_master_id
            """,
            act_params,
        )
        act_by_op = {a["operator_master_id"]: a for a in cur.fetchall()}

        cur.close()
        conn.close()

        operators = []
        for r in rows:
            blk = _oee_from_sums(
                planned=r["planned_min"],
                ar_loss=r["ar_loss_min"],
                pr_loss=r["pr_loss_min"],
                run=r["run_min"],
                ok=r["ok_qty"],
                rej=r["rejected_qty"],
                hold=r["hold_qty"],
                target_qty=r["target_qty"],
            )
            blk["operator_master_id"] = r["operator_master_id"]
            blk["employee_no"]        = r["employee_no"]
            blk["operator_name"]      = r["operator_name"]
            blk["session_count"]      = _int(r["shift_count"])     # UI key kept
            blk["entry_count"]        = _int(r["entry_count"])
            act = act_by_op.get(r["operator_master_id"], {})
            blk["activity_min"]       = round(_f(act.get("act_min", 0)), 2)
            blk["activity_loss_min"]  = round(_f(act.get("act_loss", 0)), 2)
            blk["activity_count"]     = _int(act.get("act_count", 0))
            operators.append(blk)

        return _jsonify({
            "period":    {"from_date": str(fd), "to_date": str(td)},
            "operators": operators,
        })

    except PermissionError as exc:
        return _jsonify({"error": str(exc)}, 403)
    except Exception as exc:
        import traceback
        return _jsonify({"error": str(exc), "trace": traceback.format_exc()}, 500)


# ============================================================
# API — DRILL-DOWN (individual entries + top losses)
# ============================================================

@oee_machine_summary_bp.route("/api/oee-machine-summary/drill-down")
def api_oee_machine_summary_drill_down():
    try:
        _access_role()

        fd, td = _parse_dates()
        kind = (request.args.get("kind") or "").strip().lower()
        id_s = (request.args.get("id")   or "").strip()

        if kind not in ("machine", "operator"):
            return _jsonify({"error": "kind must be 'machine' or 'operator'"}, 400)

        try:
            row_id = int(id_s)
        except ValueError:
            return _jsonify({"error": "id must be an integer"}, 400)

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)

        # ---- entry rows ----
        base_sql = """
            SELECT
                e.id                    AS entry_id,
                e.entry_date            AS entry_date,
                e.shift_name            AS shift_name,
                e.job_card_no           AS job_card_no,
                e.item_name             AS item_name,
                e.process_name          AS process_name,
                e.operator_name         AS operator_name,
                e.employee_no_col       AS employee_no,
                e.machine_no            AS machine_no,
                e.machine_name          AS machine_name,
                e.start_time            AS start_time,
                e.end_time              AS end_time,
                e.ok_qty                AS ok_qty,
                e.rejected_qty          AS rejected_qty,
                e.hold_qty              AS hold_qty,
                e.planned_minutes       AS planned_min,
                e.utilization_minutes   AS utilization_min,
                e.after_pr_minutes      AS after_pr_min,
                e.run_minutes           AS run_min,
                e.ar_loss_minutes       AS ar_loss_min,
                e.pr_loss_minutes       AS pr_loss_min,
                e.target_qty            AS target_qty,
                e.plan_vs_actual        AS plan_vs_actual,
                e.detailed_ar_ratio     AS ar_ratio,
                e.detailed_pr_ratio     AS pr_ratio,
                e.detailed_qr_ratio     AS qr_ratio,
                e.detailed_oee_ratio    AS oee_ratio
            FROM (
                SELECT
                    id, entry_date, shift_name, job_card_no, item_name,
                    process_name, operator_name,
                    operator_employee_no AS employee_no_col,
                    machine_no, machine_name,
                    start_time, end_time,
                    ok_qty, rejected_qty, hold_qty,
                    planned_minutes, utilization_minutes, after_pr_minutes,
                    run_minutes, ar_loss_minutes, pr_loss_minutes,
                    target_qty, plan_vs_actual,
                    detailed_ar_ratio, detailed_pr_ratio,
                    detailed_qr_ratio, detailed_oee_ratio,
                    machine_id, operator_master_id, record_status,
                    activity_type
                FROM oee_entries
            ) e
            WHERE e.record_status = 'active'
              AND e.activity_type IS NULL
              AND e.entry_date BETWEEN %s AND %s
        """
        if kind == "machine":
            base_sql += " AND e.machine_id = %s "
        else:
            base_sql += " AND e.operator_master_id = %s "
        base_sql += " ORDER BY e.entry_date DESC, e.shift_name, e.start_time, e.id"

        cur.execute(base_sql, [str(fd), str(td), row_id])
        raw_entries = cur.fetchall()

        entries = []
        for r in raw_entries:
            entry_date_str = str(r["entry_date"]) if r["entry_date"] else ""
            op_name        = r["operator_name"] or ""
            entries.append({
                "entry_id":            r["entry_id"],
                "entry_date":          entry_date_str,
                "session_date":        entry_date_str,   # UI-compat alias
                "shift_name":          _shift_display(r["shift_name"]),
                "job_card_no":         r["job_card_no"],
                "item_name":           r["item_name"] or "",
                "process_name":        r["process_name"] or "",
                "operator_name":       op_name,
                "opened_by_name":      op_name,          # UI-compat alias
                "employee_no":         r["employee_no"] or "",
                "machine_no":          r["machine_no"] or "",
                "machine_name":        r["machine_name"] or "",
                "start_time":          str(r["start_time"]) if r["start_time"] else "",
                "end_time":            str(r["end_time"]) if r["end_time"] else "",
                "ok_qty":              _int(r["ok_qty"]),
                "rejected_qty":        _int(r["rejected_qty"]),
                "hold_qty":            _int(r["hold_qty"]),
                "planned_minutes":     round(_f(r["planned_min"]), 2),
                "utilization_minutes": round(_f(r["utilization_min"]), 2),
                "after_pr_minutes":    round(_f(r["after_pr_min"]), 2),
                "run_minutes":         round(_f(r["run_min"]), 2),
                "ar_loss_minutes":     round(_f(r["ar_loss_min"]), 2),
                "pr_loss_minutes":     round(_f(r["pr_loss_min"]), 2),
                "target_qty":          round(_f(r["target_qty"]), 2),
                "plan_vs_actual":      round(_f(r["plan_vs_actual"]), 4) if r["plan_vs_actual"] is not None else None,
                "ar_pct":              _pct(r["ar_ratio"]),
                "pr_pct":              _pct(r["pr_ratio"]),
                "qr_pct":              _pct(r["qr_ratio"]),
                "oee_pct":             _pct(r["oee_ratio"]),
            })

        # ---- top losses (aggregated across the entries visible in this drill-down) ----
        loss_sql = """
            SELECT
                l.loss_code_snapshot     AS loss_code,
                MAX(l.loss_name_snapshot) AS loss_name,
                MAX(l.loss_category_snapshot) AS loss_category,
                SUM(l.loss_minutes)      AS total_min
            FROM oee_entry_losses l
            JOIN oee_entries e ON e.id = l.oee_entry_id
            WHERE e.record_status = 'active'
              AND e.activity_type IS NULL
              AND e.entry_date BETWEEN %s AND %s
        """
        if kind == "machine":
            loss_sql += " AND e.machine_id = %s "
        else:
            loss_sql += " AND e.operator_master_id = %s "
        loss_sql += """
            GROUP BY l.loss_code_snapshot
            HAVING SUM(l.loss_minutes) > 0
            ORDER BY SUM(l.loss_minutes) DESC
            LIMIT 10
        """
        cur.execute(loss_sql, [str(fd), str(td), row_id])
        top_losses = [
            {
                "loss_code":     r["loss_code"],
                "loss_name":     r["loss_name"],
                "loss_category": r["loss_category"] or "AR",
                "total_min":     round(_f(r["total_min"]), 2),
            }
            for r in cur.fetchall()
        ]

# ---- activity rows for this machine/operator ----
        if kind == "machine":
            act_scope_sql = "AND e.machine_id = %s"
        else:
            act_scope_sql = "AND e.operator_master_id = %s"
        cur.execute(
            f"""
            SELECT
                e.id                    AS entry_id,
                e.entry_date            AS entry_date,
                e.shift_name            AS shift_name,
                e.activity_type         AS activity_type,
                e.item_name             AS item_name,
                e.operator_name         AS operator_name,
                e.operator_employee_no  AS employee_no,
                e.machine_no            AS machine_no,
                e.machine_name          AS machine_name,
                e.start_time            AS start_time,
                e.end_time              AS end_time,
                e.planned_minutes       AS planned_min,
                e.ar_loss_minutes       AS ar_loss_min,
                e.pr_loss_minutes       AS pr_loss_min,
                e.utilization_minutes   AS utilization_min,
                e.remarks               AS remarks
            FROM oee_entries e
            WHERE e.record_status = 'active'
              AND e.entry_date BETWEEN %s AND %s
              AND e.activity_type IS NOT NULL
              {act_scope_sql}
            ORDER BY e.entry_date DESC, e.shift_name, e.start_time, e.id
            """,
            [str(fd), str(td), row_id],
        )
        activities = []
        for r in cur.fetchall():
            activities.append({
                "entry_id":            r["entry_id"],
                "entry_date":          str(r["entry_date"]) if r["entry_date"] else "",
                "shift_name":          _shift_display(r["shift_name"]),
                "activity_type":       r["activity_type"] or "",
                "activity_name":       r["item_name"] or "",
                "operator_name":       r["operator_name"] or "",
                "employee_no":         r["employee_no"] or "",
                "machine_no":          r["machine_no"] or "",
                "machine_name":        r["machine_name"] or "",
                "start_time":          str(r["start_time"]) if r["start_time"] else "",
                "end_time":            str(r["end_time"]) if r["end_time"] else "",
                "planned_minutes":     round(_f(r["planned_min"]), 2),
                "ar_loss_minutes":     round(_f(r["ar_loss_min"]), 2),
                "pr_loss_minutes":     round(_f(r["pr_loss_min"]), 2),
                "utilization_minutes": round(_f(r["utilization_min"]), 2),
                "remarks":             r["remarks"] or "",
            })

        cur.close()
        conn.close()

        # ---- tool entries linked to the entries in view ----
        conn3 = get_connection()
        cur3  = conn3.cursor(dictionary=True)
        if kind == "machine":
            tool_scope_sql = "AND t.machine_id = %s"
        else:
            tool_scope_sql = "AND t.operator_master_id = %s"
        cur3.execute(
            f"""
            SELECT
                t.id                    AS tool_id,
                t.run_id                AS entry_id,
                t.tool_position,
                t.tool_uid,
                t.tool_action_code,
                t.tool_action_name,
                t.corner_code,
                t.corner_name,
                t.change_reason_code,
                t.change_reason_name,
                t.reason_group,
                t.usage_per_part,
                t.created_at,
                e.job_card_no,
                e.item_name,
                e.entry_date,
                e.shift_name,
                e.machine_no,
                e.machine_name,
                e.operator_name,
                e.operator_employee_no
            FROM oee_tool_entries t
            JOIN oee_entries e ON e.id = t.run_id
            WHERE e.record_status = 'active'
              AND e.entry_date BETWEEN %s AND %s
              {tool_scope_sql}
            ORDER BY e.entry_date DESC, e.shift_name, t.run_id, t.tool_position, t.id
            """,
            [str(fd), str(td), row_id],
        )
        tool_rows = []
        for r in cur3.fetchall():
            tool_rows.append({
                "tool_id":            r["tool_id"],
                "entry_id":           r["entry_id"],
                "job_card_no":        r["job_card_no"] or "",
                "item_name":          r["item_name"] or "",
                "entry_date":         str(r["entry_date"]) if r["entry_date"] else "",
                "shift_name":         _shift_display(r["shift_name"]),
                "machine_no":         r["machine_no"] or "",
                "machine_name":       r["machine_name"] or "",
                "operator_name":      r["operator_name"] or "",
                "employee_no":        r["operator_employee_no"] or "",
                "tool_position":      r["tool_position"],
                "tool_uid":           r["tool_uid"] or "",
                "tool_action_code":   r["tool_action_code"] or "",
                "tool_action_name":   r["tool_action_name"] or "",
                "corner_code":        r["corner_code"] or "",
                "corner_name":        r["corner_name"] or "",
                "change_reason_code": r["change_reason_code"] or "",
                "change_reason_name": r["change_reason_name"] or "",
                "reason_group":       r["reason_group"] or "",
                "usage_per_part":     r["usage_per_part"] or "",
            })
        cur3.close(); conn3.close()

        return _jsonify({
            "kind":       kind,
            "id":         row_id,
            "period":     {"from_date": str(fd), "to_date": str(td)},
            "entries":    entries,
            "sessions":   entries,
            "activities": activities,
            "top_losses": top_losses,
            "tools":      tool_rows,
        })

    except PermissionError as exc:
        return _jsonify({"error": str(exc)}, 403)
    except Exception as exc:
        import traceback
        return _jsonify({"error": str(exc), "trace": traceback.format_exc()}, 500)


# =========================================================================
# APPEND-ONLY: paste this block at the END of
#   D:\Het\demo2\routes\oee_machine_summary.py
#
# Adds one new endpoint:
#   GET /api/oee-machine-summary/export-excel?machine_id=N&from_date=Y&to_date=Y
#
# Returns a per-machine .xlsx file matching the reference workbook layout:
#   - Sheet name  : " <machine_no>-<machine_name>"      e.g. " CNC 02-SMALL HARDINGE"
#   - Row 1       : A1..A27 loss code labels in columns AH..BH
#   - Row 2       : Full header row (columns A..BQ)
#   - Row 3+      : One row per oee_entries record
#   - Columns AH..BH : A1..A27 loss minutes per entry (Gujarati header from oee_loss_types)
#   - Columns BI..BQ : per-entry AVAILABLE TIME, AR LOSS, UTILIZATION, PR LOSS,
#                       AFTER PR LOSS, AR%, PR%, QR%, OEE%
#
# Only Admin and Supervisor can call this endpoint.
# =========================================================================

import io
from datetime import time as _time, timedelta as _timedelta

from flask import send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


# --------- Excel styling ---------------------------------------------

_EXP_HEADER_FONT   = Font(name="Arial", size=10, bold=True, color="FFFFFF")
_EXP_HEADER_FILL   = PatternFill("solid", fgColor="305496")
_EXP_LOSS_FILL     = PatternFill("solid", fgColor="8FAADC")
_EXP_SUMMARY_FILL  = PatternFill("solid", fgColor="70AD47")
_EXP_BODY_FONT     = Font(name="Arial", size=10)
_EXP_CENTER        = Alignment(horizontal="center", vertical="center", wrap_text=True)
_EXP_LEFT          = Alignment(horizontal="left",   vertical="center")
_EXP_THIN          = Side(border_style="thin", color="B4B4B4")
_EXP_BORDER        = Border(top=_EXP_THIN, bottom=_EXP_THIN, left=_EXP_THIN, right=_EXP_THIN)


# --------- Static column layout (matches reference workbook) ---------

# Base columns 1..33 (A..AG)
_EXP_BASE_HEADERS = [
    ("DATE",              12),
    ("SHIFT",              8),
    ("M/C NO.",            9),
    ("MACHINE",           18),
    ("ZONE SUPERVISOR",   18),
    ("EMPLOYEE NO",       11),
    ("OPERATOR NAME",     25),
    ("JOB CARD NO.",      13),
    ("MODEL",             28),
    ("SIZE",              18),
    ("PARTS",             10),
    ("OPERATION",         12),
    ("CYCLE TIME",        11),
    ("LOAD/UNLOAD",       12),
    ("PRODUCTION QTY",    12),
    ("REJECTION QTY",     12),
    ("REWORK QTY",        11),
    ("START TIME",        11),
    ("END TIME",          11),
    ("PLANNED MIN",       11),
    ("RUN MIN",           10),
    ("LOSS MIN",          10),
    ("IDEAL CT (MIN/PC)", 15),
    ("TAREGET QTY.",      12),
    ("TOTAL QTY",         10),
    ("PLAN VS ACTUAL",    13),
    ("QUALITY %",         10),
    ("AVAILABILITY %",    13),
    ("PERFORMANCE %",     13),
    ("OEE %",              8),
    ("LOSS REASON",       22),
    ("REMARKS",           18),
    ("STATUS",            10),
]

# Summary block columns 61..69 (BI..BQ)
_EXP_SUMMARY_HEADERS = [
    ("AVAILABLE TIME",         13),
    ("TOTAL AR LOSS TIME",     15),
    ("TOTAL UTILIZATION TIME", 17),
    ("TOTAL PR LOSS TIME",     15),
    ("AFTER PR LOSS",          13),
    ("AR",                      8),
    ("PR",                      8),
    ("QR",                      8),
    ("OEE%",                    8),
]

_ALL_LOSS_CODES = [f"A{i}" for i in range(1, 28)]   # A1..A27


# --------- helpers ---------------------------------------------------

def _exp_shift_to_display(name):
    """'Shift 1' / '1' -> '1st', etc."""
    if not name:
        return ""
    s = str(name).strip()
    if any(s.lower().endswith(sfx) for sfx in ("st", "nd", "rd", "th")):
        return s
    lower = s.lower()
    if lower.startswith("shift "):
        s = s[6:].strip()
    if s.isdigit():
        n = int(s)
        if n % 100 in (11, 12, 13):
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix}"
    return name


def _exp_minsec_to_time(minutes, seconds):
    m = int(minutes or 0)
    s = int(seconds or 0)
    h = m // 60
    m = m % 60
    return _time(h, m, s)


def _exp_time_value(v):
    """Coerce DB time/timedelta/str -> datetime.time for Excel."""
    if v is None or v == "":
        return None
    if isinstance(v, _time):
        return v
    if isinstance(v, _timedelta):
        total = int(v.total_seconds())
        h, r = divmod(total, 3600)
        m, s = divmod(r, 60)
        return _time(h % 24, m, s)
    if isinstance(v, str):
        parts = v.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            s = int(parts[2]) if len(parts) > 2 else 0
            return _time(h % 24, m, s)
        except (ValueError, IndexError):
            return None
    return None


def _exp_ratio(v):
    """None-safe float for ratio cells (already stored as fraction 0..1)."""
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# --------- endpoint --------------------------------------------------

@oee_machine_summary_bp.route("/api/oee-machine-summary/export-excel")
def api_oee_machine_summary_export_excel():
    try:
        role = _access_role()
        if not _can_export(role):
            return _jsonify(
                {"error": "Excel export is only available to Admin and Supervisor."},
                403,
            )

        fd, td = _parse_dates()
        mid_s = (request.args.get("machine_id") or "").strip()
        if not mid_s:
            return _jsonify({"error": "machine_id is required"}, 400)
        try:
            machine_id = int(mid_s)
        except ValueError:
            return _jsonify({"error": "machine_id must be an integer"}, 400)

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)

        # ---- machine info ----
        cur.execute(
            """
            SELECT id, machine_no, machine_name, machine_category, zone
            FROM oee_machines
            WHERE id = %s
            LIMIT 1
            """,
            (machine_id,),
        )
        machine = cur.fetchone()
        if not machine:
            cur.close(); conn.close()
            return _jsonify({"error": "Machine not found."}, 404)

        # ---- loss types (Gujarati names for row 2, columns AH..BH) ----
        cur.execute(
            """
            SELECT loss_code, loss_name
            FROM oee_loss_types
            """
        )
        loss_name_by_code = {r["loss_code"]: r["loss_name"] for r in cur.fetchall()}

        # ---- entries ----
        cur.execute(
            """
            SELECT
                id, entry_date, shift_name,
                machine_no, machine_name, zone,
                operator_employee_no, operator_name,
                job_card_no, item_name, process_name,
                cycle_minutes, cycle_seconds,
                load_unload_minutes, load_unload_seconds,
                ok_qty, rejected_qty, hold_qty,
                start_time, end_time,
                planned_minutes, run_minutes, total_loss_minutes,
                ideal_cycle_minutes, target_qty, total_qty, plan_vs_actual,
                detailed_qr_ratio, detailed_ar_ratio,
                detailed_pr_ratio, detailed_oee_ratio,
                remarks,
                available_time_minutes, ar_loss_minutes, utilization_minutes,
                pr_loss_minutes, after_pr_minutes
            FROM oee_entries
            WHERE record_status = 'active'
              AND machine_id = %s
              AND entry_date BETWEEN %s AND %s
              AND activity_type IS NULL
            ORDER BY entry_date, shift_name, start_time, id
            """,
            (machine_id, str(fd), str(td)),
        )
        entries = cur.fetchall()

        # ---- losses per entry (pivot to A1..A27 dict) ----
        entry_ids = [e["id"] for e in entries]
        losses_by_entry = {eid: {c: 0.0 for c in _ALL_LOSS_CODES} for eid in entry_ids}

        if entry_ids:
            placeholders = ",".join(["%s"] * len(entry_ids))
            cur.execute(
                f"""
                SELECT oee_entry_id, loss_code_snapshot, loss_minutes
                FROM oee_entry_losses
                WHERE oee_entry_id IN ({placeholders})
                """,
                entry_ids,
            )
            for lr in cur.fetchall():
                eid  = lr["oee_entry_id"]
                code = str(lr["loss_code_snapshot"] or "").strip().upper()
                if eid in losses_by_entry and code in losses_by_entry[eid]:
                    try:
                        losses_by_entry[eid][code] += float(lr["loss_minutes"] or 0)
                    except (TypeError, ValueError):
                        pass

        cur.close()
        conn.close()

        # ============================================================
        # Build workbook
        # ============================================================
        wb = Workbook()
        ws = wb.active
        sheet_title = f" {machine['machine_no']}-{machine['machine_name']}"[:31]
        ws.title = sheet_title

        # ---- row 1: A1..A27 codes in AH1..BH1 ----
        col_start_loss = len(_EXP_BASE_HEADERS) + 1   # 34 (AH)
        for i, code in enumerate(_ALL_LOSS_CODES):
            cell = ws.cell(row=1, column=col_start_loss + i, value=code)
            cell.font      = _EXP_HEADER_FONT
            cell.fill      = _EXP_LOSS_FILL
            cell.alignment = _EXP_CENTER
            cell.border    = _EXP_BORDER

        # ---- row 2: full header row ----
        # base 1..33
        for i, (label, width) in enumerate(_EXP_BASE_HEADERS, start=1):
            cell = ws.cell(row=2, column=i, value=label)
            cell.font      = _EXP_HEADER_FONT
            cell.fill      = _EXP_HEADER_FILL
            cell.alignment = _EXP_CENTER
            cell.border    = _EXP_BORDER
            ws.column_dimensions[get_column_letter(i)].width = width

        # loss column headers (Gujarati names) 34..60
        for i, code in enumerate(_ALL_LOSS_CODES):
            col = col_start_loss + i
            gujarati = loss_name_by_code.get(code, code)
            cell = ws.cell(row=2, column=col, value=gujarati)
            cell.font      = Font(name="Arial", size=9, bold=True, color="FFFFFF")
            cell.fill      = _EXP_LOSS_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border    = _EXP_BORDER
            ws.column_dimensions[get_column_letter(col)].width = 14

        # summary block 61..69
        col_start_summary = col_start_loss + len(_ALL_LOSS_CODES)   # 61 (BI)
        for i, (label, width) in enumerate(_EXP_SUMMARY_HEADERS):
            col = col_start_summary + i
            cell = ws.cell(row=2, column=col, value=label)
            cell.font      = _EXP_HEADER_FONT
            cell.fill      = _EXP_SUMMARY_FILL
            cell.alignment = _EXP_CENTER
            cell.border    = _EXP_BORDER
            ws.column_dimensions[get_column_letter(col)].width = width

        ws.row_dimensions[1].height = 22
        ws.row_dimensions[2].height = 72
        ws.freeze_panes = "A3"

        # ---- data rows starting at row 3 ----
        for r_idx, e in enumerate(entries, start=3):
            cycle_time_v      = _exp_minsec_to_time(e["cycle_minutes"], e["cycle_seconds"])
            load_time_v       = _exp_minsec_to_time(e["load_unload_minutes"], e["load_unload_seconds"])
            start_time_v      = _exp_time_value(e["start_time"])
            end_time_v        = _exp_time_value(e["end_time"])

            has_any_loss = any(
                (losses_by_entry.get(e["id"], {}).get(c) or 0) > 0
                for c in _ALL_LOSS_CODES
            )
            loss_reason = "Detailed Loss Entered" if has_any_loss else ""
            status_val  = "Completed" if int(e["ok_qty"] or 0) > 0 else "Pending"

            base_values = [
                e["entry_date"],
                _exp_shift_to_display(e["shift_name"]),
                e["machine_no"],
                e["machine_name"],
                "",                                          # Zone Supervisor (not stored)
                e["operator_employee_no"] or "",
                e["operator_name"] or "",
                e["job_card_no"] or "",
                "",                                          # Model
                "",                                          # Size
                "",                                          # Parts
                e["process_name"] or "",
                cycle_time_v,
                load_time_v,
                int(e["ok_qty"] or 0),
                int(e["rejected_qty"] or 0),
                int(e["hold_qty"] or 0),
                start_time_v,
                end_time_v,
                float(e["planned_minutes"] or 0),
                float(e["run_minutes"] or 0) if e["run_minutes"] is not None else None,
                float(e["total_loss_minutes"] or 0),
                float(e["ideal_cycle_minutes"] or 0),
                float(e["target_qty"] or 0) if e["target_qty"] is not None else None,
                int(e["total_qty"] or 0),
                _exp_ratio(e["plan_vs_actual"]),
                _exp_ratio(e["detailed_qr_ratio"]),
                _exp_ratio(e["detailed_ar_ratio"]),
                _exp_ratio(e["detailed_pr_ratio"]),
                _exp_ratio(e["detailed_oee_ratio"]),
                loss_reason,
                e["remarks"] or "",
                status_val,
            ]
            for c_idx, val in enumerate(base_values, start=1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.font = _EXP_BODY_FONT
                cell.border = _EXP_BORDER

            # cell number formats for the base block
            ws.cell(row=r_idx, column=1).number_format  = "yyyy-mm-dd"
            ws.cell(row=r_idx, column=13).number_format = "hh:mm:ss"    # cycle
            ws.cell(row=r_idx, column=14).number_format = "hh:mm:ss"    # load
            ws.cell(row=r_idx, column=18).number_format = "hh:mm"       # start
            ws.cell(row=r_idx, column=19).number_format = "hh:mm"       # end
            ws.cell(row=r_idx, column=20).number_format = "0.00"        # planned
            ws.cell(row=r_idx, column=21).number_format = "0.00"        # run
            ws.cell(row=r_idx, column=22).number_format = "0.00"        # loss
            ws.cell(row=r_idx, column=23).number_format = "0.0000"      # ideal ct
            ws.cell(row=r_idx, column=24).number_format = "0.00"        # target qty
            for pct_col in (26, 27, 28, 29, 30):
                ws.cell(row=r_idx, column=pct_col).number_format = "0.00%"

            # losses A1..A27
            e_losses = losses_by_entry.get(e["id"], {})
            for i, code in enumerate(_ALL_LOSS_CODES):
                col   = col_start_loss + i
                value = e_losses.get(code, 0.0)
                cell  = ws.cell(row=r_idx, column=col, value=value if value else None)
                cell.font   = _EXP_BODY_FONT
                cell.border = _EXP_BORDER
                cell.number_format = "0.00"

            # summary block BI..BQ
            summary_vals = [
                float(e["available_time_minutes"] or 0),
                float(e["ar_loss_minutes"] or 0),
                float(e["utilization_minutes"] or 0),
                float(e["pr_loss_minutes"] or 0),
                float(e["after_pr_minutes"] or 0),
                _exp_ratio(e["detailed_ar_ratio"]),
                _exp_ratio(e["detailed_pr_ratio"]),
                _exp_ratio(e["detailed_qr_ratio"]),
                _exp_ratio(e["detailed_oee_ratio"]),
            ]
            for i, val in enumerate(summary_vals):
                col  = col_start_summary + i
                cell = ws.cell(row=r_idx, column=col, value=val)
                cell.font   = _EXP_BODY_FONT
                cell.border = _EXP_BORDER
                cell.number_format = "0.00" if i < 5 else "0.00%"

        # ============================================================
        # Activity rows (Tool Room / Development) — appended below
        # ============================================================
        conn2 = get_connection()
        cur2  = conn2.cursor(dictionary=True)
        cur2.execute(
            """
            SELECT
                id, entry_date, shift_name,
                machine_no, machine_name, zone,
                operator_employee_no, operator_name,
                item_name, activity_type,
                start_time, end_time,
                planned_minutes, ar_loss_minutes,
                utilization_minutes, total_loss_minutes,
                remarks
            FROM oee_entries
            WHERE record_status = 'active'
              AND machine_id = %s
              AND entry_date BETWEEN %s AND %s
              AND activity_type IS NOT NULL
            ORDER BY entry_date, shift_name, start_time, id
            """,
            (machine_id, str(fd), str(td)),
        )
        activity_entries = cur2.fetchall()

        # activity-losses pivot
        act_ids = [a['id'] for a in activity_entries]
        act_losses = {aid: {c: 0.0 for c in _ALL_LOSS_CODES} for aid in act_ids}
        if act_ids:
            ph = ','.join(['%s'] * len(act_ids))
            cur2.execute(
                f"SELECT oee_entry_id, loss_code_snapshot, loss_minutes "
                f"FROM oee_entry_losses WHERE oee_entry_id IN ({ph})",
                act_ids,
            )
            for lr in cur2.fetchall():
                aid  = lr['oee_entry_id']
                code = str(lr['loss_code_snapshot'] or '').strip().upper()
                if aid in act_losses and code in act_losses[aid]:
                    try:
                        act_losses[aid][code] += float(lr['loss_minutes'] or 0)
                    except (TypeError, ValueError):
                        pass
        cur2.close(); conn2.close()

        # write section header row + activity rows
        if activity_entries:
            sep_row = ws.max_row + 2
            hdr_cell = ws.cell(row=sep_row, column=1, value='ACTIVITIES (Tool Room / Development)')
            hdr_cell.font = Font(name='Arial', size=11, bold=True, color='FFFFFF')
            hdr_cell.fill = PatternFill('solid', fgColor='C0504D')
            hdr_cell.alignment = _EXP_LEFT
            ws.merge_cells(start_row=sep_row, start_column=1, end_row=sep_row, end_column=12)

            data_row = sep_row + 1
            for a in activity_entries:
                cycle_time_v = _exp_minsec_to_time(0, 0)
                load_time_v  = _exp_minsec_to_time(0, 0)
                start_time_v = _exp_time_value(a['start_time'])
                end_time_v   = _exp_time_value(a['end_time'])
                planned      = float(a['planned_minutes'] or 0)
                ar_loss      = float(a['ar_loss_minutes'] or 0)
                total_loss   = float(a['total_loss_minutes'] or 0)
                util         = float(a['utilization_minutes'] or 0)
                ar_ratio     = (util / planned) if planned > 0 else 0.0

                base_values = [
                    a['entry_date'],
                    _exp_shift_to_display(a['shift_name']),
                    a['machine_no'],
                    a['machine_name'],
                    '',
                    a['operator_employee_no'] or '',
                    a['operator_name'] or '',
                    '',
                    a['activity_type'] or '',
                    '',
                    '',
                    a['item_name'] or '',
                    None,
                    None,
                    0, 0, 0,
                    start_time_v,
                    end_time_v,
                    planned,
                    None,
                    total_loss,
                    None,
                    None,
                    0,
                    None,
                    None,
                    ar_ratio,
                    None,
                    None,
                    'Detailed Loss Entered' if total_loss > 0 else '',
                    a['remarks'] or '',
                    'Completed',
                ]
                for c_idx, val in enumerate(base_values, start=1):
                    cell = ws.cell(row=data_row, column=c_idx, value=val)
                    cell.font = _EXP_BODY_FONT
                    cell.border = _EXP_BORDER
                ws.cell(row=data_row, column=1).number_format  = 'yyyy-mm-dd'
                ws.cell(row=data_row, column=18).number_format = 'hh:mm'
                ws.cell(row=data_row, column=19).number_format = 'hh:mm'
                ws.cell(row=data_row, column=20).number_format = '0.00'
                ws.cell(row=data_row, column=22).number_format = '0.00'
                ws.cell(row=data_row, column=28).number_format = '0.00%'

                # A1..A27 losses
                e_losses = act_losses.get(a['id'], {})
                col_start_loss = len(_EXP_BASE_HEADERS) + 1
                for i, code in enumerate(_ALL_LOSS_CODES):
                    col   = col_start_loss + i
                    value = e_losses.get(code, 0.0)
                    cell  = ws.cell(row=data_row, column=col, value=value if value else None)
                    cell.font   = _EXP_BODY_FONT
                    cell.border = _EXP_BORDER
                    cell.number_format = '0.00'

                # summary block: only AR applies
                col_start_summary = col_start_loss + len(_ALL_LOSS_CODES)
                summary_vals = [planned, ar_loss, util, 0.0, util, ar_ratio, 0.0, 0.0, ar_ratio]
                for i, val in enumerate(summary_vals):
                    col  = col_start_summary + i
                    cell = ws.cell(row=data_row, column=col, value=val)
                    cell.font   = _EXP_BODY_FONT
                    cell.border = _EXP_BORDER
                    cell.number_format = '0.00' if i < 5 else '0.00%'
                data_row += 1

        # ---- serialize to bytes and return ----
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        zone_prefix = (machine.get("zone") or "").strip()
        filename    = (
            f"{zone_prefix + ' ' if zone_prefix else ''}"
            f"{machine['machine_no']} {machine['machine_name']}"
            f" {fd}_to_{td}.xlsx"
        ).replace("/", "_")

        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except PermissionError as exc:
        return _jsonify({"error": str(exc)}, 403)
    except Exception as exc:
        import traceback
        return _jsonify({"error": str(exc), "trace": traceback.format_exc()}, 500)


# =========================================================================
# OEE_MACHINE_SUMMARY_FLAT_API_V129
# One-shot endpoint that returns every session / activity / tool entry
# in the current filter, plus a top-losses aggregate.
# Sessions include inline losses[] and tools[] so the drill-down panel
# needs zero extra requests.
# =========================================================================

@oee_machine_summary_bp.route("/api/oee-machine-summary/flat")
def api_oee_machine_summary_flat_v129():
    try:
        _access_role()

        fd, td = _parse_dates()
        zone, machine_id, operator_master_id = _optional_filters()

        conn = get_connection()
        cur  = conn.cursor(dictionary=True)

        # ------- Sessions (production entries) -------
        w = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
            "e.activity_type IS NULL",
        ]
        p = [str(fd), str(td)]
        if zone:               w.append("e.zone = %s");                p.append(zone)
        if machine_id:         w.append("e.machine_id = %s");          p.append(machine_id)
        if operator_master_id: w.append("e.operator_master_id = %s");  p.append(operator_master_id)

        cur.execute(
            "SELECT e.id AS entry_id, e.entry_date, e.shift_name, "
            "  e.machine_no, e.machine_name, e.zone, "
            "  e.operator_name, e.operator_employee_no, "
            "  e.job_card_no, e.item_name, e.process_name, "
            "  e.cycle_minutes, e.cycle_seconds, "
            "  e.load_unload_minutes, e.load_unload_seconds, "
            "  e.start_time, e.end_time, "
            "  e.ok_qty, e.rejected_qty, e.hold_qty, "
            "  e.planned_minutes, e.utilization_minutes, e.after_pr_minutes, "
            "  e.run_minutes, e.ar_loss_minutes, e.pr_loss_minutes, "
            "  e.target_qty, e.plan_vs_actual, e.formula_profile, "
            "  e.detailed_ar_ratio AS ar, e.detailed_pr_ratio AS pr, "
            "  e.detailed_qr_ratio AS qr, e.detailed_oee_ratio AS oee "
            "FROM oee_entries e "
            "WHERE " + " AND ".join(w) + " "
            "ORDER BY e.entry_date DESC, e.shift_name, e.start_time, e.id",
            p,
        )
        raw_sessions = cur.fetchall() or []
        session_ids  = [r["entry_id"] for r in raw_sessions]

        # ------- Activities (Tool Room / Development / Machine Loss) -------
        aw = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
            "e.activity_type IS NOT NULL",
        ]
        ap = [str(fd), str(td)]
        if zone:               aw.append("e.zone = %s");                ap.append(zone)
        if machine_id:         aw.append("e.machine_id = %s");          ap.append(machine_id)
        if operator_master_id: aw.append("e.operator_master_id = %s");  ap.append(operator_master_id)

        cur.execute(
            "SELECT e.id AS entry_id, e.entry_date, e.shift_name, "
            "  e.activity_type, e.item_name AS activity_name, "
            "  e.machine_no, e.machine_name, e.operator_name, "
            "  e.start_time, e.end_time, "
            "  e.planned_minutes, e.utilization_minutes, "
            "  e.ar_loss_minutes, e.pr_loss_minutes, e.remarks "
            "FROM oee_entries e "
            "WHERE " + " AND ".join(aw) + " "
            "ORDER BY e.entry_date DESC, e.shift_name, e.start_time, e.id",
            ap,
        )
        raw_activities = cur.fetchall() or []
        activity_ids   = [r["entry_id"] for r in raw_activities]

        # ------- Losses for every session + activity -------
        all_ids = session_ids + activity_ids
        losses_by_entry = {i: [] for i in all_ids}
        if all_ids:
            ph = ",".join(["%s"] * len(all_ids))
            cur.execute(
                "SELECT oee_entry_id, loss_code_snapshot AS code, "
                "  loss_name_snapshot AS name, loss_category_snapshot AS category, "
                "  loss_minutes AS minutes "
                "FROM oee_entry_losses "
                "WHERE oee_entry_id IN (" + ph + ") "
                "  AND loss_minutes > 0 "
                "ORDER BY CAST(SUBSTRING(loss_code_snapshot, 2) AS UNSIGNED)",
                all_ids,
            )
            for r in cur.fetchall() or []:
                losses_by_entry[r["oee_entry_id"]].append({
                    "code":     r["code"],
                    "name":     r["name"],
                    "category": (r["category"] or "AR").upper(),
                    "minutes":  round(_f(r["minutes"]), 2),
                })

        # ------- Tool entries -------
        tw = [
            "e.record_status = 'active'",
            "e.entry_date BETWEEN %s AND %s",
        ]
        tp = [str(fd), str(td)]
        if zone:               tw.append("e.zone = %s");                tp.append(zone)
        if machine_id:         tw.append("t.machine_id = %s");          tp.append(machine_id)
        if operator_master_id: tw.append("t.operator_master_id = %s");  tp.append(operator_master_id)

        cur.execute(
            "SELECT t.id AS tool_id, t.run_id AS entry_id, t.activity_run_id, "
            "  t.machine_loss_entry_id, t.tool_position, t.tool_uid, "
            "  t.tool_action_code, t.tool_action_name, "
            "  t.corner_code, t.corner_name, "
            "  t.change_reason_code, t.change_reason_name, t.reason_group, "
            "  t.usage_per_part, t.created_at, "
            "  e.entry_date, e.shift_name, e.job_card_no, e.item_name, "
            "  e.machine_no, e.machine_name, e.operator_name, e.operator_employee_no "
            "FROM oee_tool_entries t "
            "JOIN oee_entries e ON e.id = COALESCE(t.run_id, t.activity_run_id, t.machine_loss_entry_id) "
            "WHERE " + " AND ".join(tw) + " "
            "ORDER BY e.entry_date DESC, e.shift_name, t.tool_position, t.id",
            tp,
        )
        raw_tools = cur.fetchall() or []

        # index tools by their parent entry so sessions & activities can carry inline tools
        tools_by_entry = {}
        for t in raw_tools:
            parent = t["entry_id"] or t.get("activity_run_id") or t.get("machine_loss_entry_id")
            if not parent: continue
            tools_by_entry.setdefault(parent, []).append({
                "tool_id":     t["tool_id"],
                "position":    t["tool_position"],
                "uid":         t["tool_uid"] or "",
                "action_code": t["tool_action_code"] or "",
                "action_name": t["tool_action_name"] or "",
                "corner_code": t["corner_code"] or "",
                "corner_name": t["corner_name"] or "",
                "reason_code": t["change_reason_code"] or "",
                "reason_name": t["change_reason_name"] or "",
                "usage":       t["usage_per_part"] or "",
            })

        # ------- Top losses aggregate (over sessions in scope) -------
        top = []
        if session_ids:
            ph = ",".join(["%s"] * len(session_ids))
            cur.execute(
                "SELECT loss_code_snapshot AS code, "
                "  MAX(loss_name_snapshot) AS name, "
                "  MAX(loss_category_snapshot) AS category, "
                "  SUM(loss_minutes) AS total_min "
                "FROM oee_entry_losses "
                "WHERE oee_entry_id IN (" + ph + ") "
                "GROUP BY loss_code_snapshot "
                "HAVING SUM(loss_minutes) > 0 "
                "ORDER BY SUM(loss_minutes) DESC "
                "LIMIT 10",
                session_ids,
            )
            for r in cur.fetchall() or []:
                top.append({
                    "code":      r["code"],
                    "name":      r["name"],
                    "category":  (r["category"] or "AR").upper(),
                    "total_min": round(_f(r["total_min"]), 2),
                })

        cur.close(); conn.close()

        # Build session payload with inline losses + tools
        sessions = []
        total_planned = 0.0
        total_util    = 0.0
        total_ok      = 0
        total_losses  = 0.0
        oee_sum       = 0.0
        oee_cnt       = 0
        for r in raw_sessions:
            d = str(r["entry_date"]) if r["entry_date"] else ""
            planned = _f(r["planned_minutes"])
            util    = _f(r["utilization_minutes"])
            arl     = _f(r["ar_loss_minutes"])
            prl     = _f(r["pr_loss_minutes"])
            total_planned += planned
            total_util    += util
            total_ok      += _int(r["ok_qty"])
            total_losses  += (arl + prl)
            oee_sum       += _f(r["oee"])
            oee_cnt       += 1
            sessions.append({
                "entry_id":            r["entry_id"],
                "entry_date":          d,
                "shift_name":          _shift_display(r["shift_name"]),
                "machine_no":          r["machine_no"] or "",
                "machine_name":        r["machine_name"] or "",
                "zone":                r["zone"] or "",
                "operator_name":       r["operator_name"] or "",
                "employee_no":         r["operator_employee_no"] or "",
                "job_card_no":         r["job_card_no"] or "",
                "item_name":           r["item_name"] or "",
                "process_name":        r["process_name"] or "",
                "cycle_minutes":       _int(r["cycle_minutes"]),
                "cycle_seconds":       _int(r["cycle_seconds"]),
                "load_unload_minutes": _int(r["load_unload_minutes"]),
                "load_unload_seconds": _int(r["load_unload_seconds"]),
                "start_time":          str(r["start_time"]) if r["start_time"] else "",
                "end_time":            str(r["end_time"])   if r["end_time"]   else "",
                "ok_qty":              _int(r["ok_qty"]),
                "rejected_qty":        _int(r["rejected_qty"]),
                "hold_qty":            _int(r["hold_qty"]),
                "planned_minutes":     round(planned, 2),
                "utilization_minutes": round(util, 2),
                "run_minutes":         round(_f(r["run_minutes"]), 2),
                "ar_loss_minutes":     round(arl, 2),
                "pr_loss_minutes":     round(prl, 2),
                "target_qty":          round(_f(r["target_qty"]), 2),
                "plan_vs_actual":      round(_f(r["plan_vs_actual"]), 4) if r["plan_vs_actual"] is not None else None,
                "formula_profile":     r["formula_profile"] or "",
                "ar_pct":              _pct(r["ar"]),
                "pr_pct":              _pct(r["pr"]),
                "qr_pct":              _pct(r["qr"]),
                "oee_pct":             _pct(r["oee"]),
                "losses":              losses_by_entry.get(r["entry_id"], []),
                "tools":               tools_by_entry.get(r["entry_id"], []),
            })

        activities = []
        for r in raw_activities:
            activities.append({
                "entry_id":            r["entry_id"],
                "entry_date":          str(r["entry_date"]) if r["entry_date"] else "",
                "shift_name":          _shift_display(r["shift_name"]),
                "activity_type":       r["activity_type"] or "",
                "activity_name":       r["activity_name"] or "",
                "machine_no":          r["machine_no"] or "",
                "machine_name":        r["machine_name"] or "",
                "operator_name":       r["operator_name"] or "",
                "start_time":          str(r["start_time"]) if r["start_time"] else "",
                "end_time":            str(r["end_time"])   if r["end_time"]   else "",
                "planned_minutes":     round(_f(r["planned_minutes"]), 2),
                "utilization_minutes": round(_f(r["utilization_minutes"]), 2),
                "ar_loss_minutes":     round(_f(r["ar_loss_minutes"]), 2),
                "pr_loss_minutes":     round(_f(r["pr_loss_minutes"]), 2),
                "remarks":             r["remarks"] or "",
                "losses":              losses_by_entry.get(r["entry_id"], []),
                "tools":               tools_by_entry.get(r["entry_id"], []),
            })

        tool_entries = []
        for t in raw_tools:
            tool_entries.append({
                "tool_id":       t["tool_id"],
                "entry_id":      t["entry_id"] or t.get("activity_run_id") or t.get("machine_loss_entry_id"),
                "entry_date":    str(t["entry_date"]) if t["entry_date"] else "",
                "shift_name":    _shift_display(t["shift_name"]),
                "job_card_no":   t["job_card_no"] or "",
                "item_name":     t["item_name"] or "",
                "machine_no":    t["machine_no"] or "",
                "machine_name":  t["machine_name"] or "",
                "operator_name": t["operator_name"] or "",
                "employee_no":   t["operator_employee_no"] or "",
                "position":      t["tool_position"],
                "uid":           t["tool_uid"] or "",
                "action_code":   t["tool_action_code"] or "",
                "action_name":   t["tool_action_name"] or "",
                "corner_code":   t["corner_code"] or "",
                "corner_name":   t["corner_name"] or "",
                "reason_code":   t["change_reason_code"] or "",
                "reason_name":   t["change_reason_name"] or "",
                "usage":         t["usage_per_part"] or "",
            })

        return _jsonify({
            "period":    {"from_date": str(fd), "to_date": str(td)},
            "totals": {
                "session_count":     len(sessions),
                "activity_count":    len(activities),
                "tool_entry_count":  len(tool_entries),
                "total_ok":          total_ok,
                "total_planned":     round(total_planned, 2),
                "total_util":        round(total_util, 2),
                "total_losses_min":  round(total_losses, 2),
                "avg_oee_pct":       round(oee_sum * 100.0 / oee_cnt, 1) if oee_cnt else 0.0,
            },
            "sessions":     sessions,
            "activities":   activities,
            "tool_entries": tool_entries,
            "top_losses":   top,
        })

    except PermissionError as exc:
        return _jsonify({"error": str(exc)}, 403)
    except Exception as exc:
        import traceback
        return _jsonify({"error": str(exc), "trace": traceback.format_exc()}, 500)

# OEE_MACHINE_SUMMARY_FLAT_API_V129_END
