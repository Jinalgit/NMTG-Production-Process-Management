"""
Rewrite machine_oee_live_session_calc_v1 to compute live OEE
directly from a single oee_entries row + oee_entry_losses.

The route path stays /api/oee-machine/session/<id>/live-oee, but the
<id> is now the oee_entries.id (which is what Phase 3a returns as both
run_id and session_id).
"""

import re

TARGET = r"D:\Het\demo2\routes\quality_check.py"

with open(TARGET, encoding="utf-8") as f:
    src = f.read()


NEW_FN = '''def machine_oee_live_session_calc_v1(session_id):
    """
    Live per-entry OEE.
    Consolidated: reads oee_entries + oee_entry_losses only.
    """
    from .oee_persistence import OEE_MACHINE_PROFILE_MAP, ALL_OEE_LOSS_CODES

    conn = None
    cursor = None
    try:
        if str(session.get("role") or "").strip().lower() != "operator":
            return jsonify({"success": False, "error": "Operator access required."}), 403

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Load the entry
        cursor.execute("""
            SELECT
                id                   AS session_id,
                id                   AS entry_id,
                machine_id,
                entry_date           AS session_date,
                shift_name,
                machine_no,
                machine_name,
                machine_category,
                zone,
                planned_minutes,
                cycle_minutes, cycle_seconds,
                load_unload_minutes, load_unload_seconds,
                ok_qty, rejected_qty, hold_qty,
                start_time, end_time,
                entry_state
            FROM oee_entries
            WHERE id = %s
              AND activity_type IS NULL
            LIMIT 1
        """, (session_id,))
        entry = cursor.fetchone()

        if not entry:
            return jsonify({"success": False, "error": "Machine OEE session not found."}), 404

        machine_no = " ".join(
            str(entry.get("machine_no") or "").strip().upper().split()
        )
        profile = OEE_MACHINE_PROFILE_MAP.get(machine_no)
        if not profile:
            return jsonify({
                "success": True,
                "calculation_ready": False,
                "machine_no": machine_no,
                "message": f"{machine_no} does not yet have a confirmed Excel formula profile.",
            })

        pr_codes    = set(profile["pr_loss_codes"])
        deduct_code = profile["target_deduct_code"]

        # Losses for this entry
        cursor.execute("""
            SELECT loss_code_snapshot, loss_minutes
            FROM oee_entry_losses
            WHERE oee_entry_id = %s
        """, (session_id,))
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
        target_deduct = loss_by_code.get(deduct_code, 0.0)

        cycle_m = int(entry.get("cycle_minutes") or 0)
        cycle_s = int(entry.get("cycle_seconds") or 0)
        load_m  = int(entry.get("load_unload_minutes") or 0)
        load_s  = int(entry.get("load_unload_seconds") or 0)
        ideal_cycle = cycle_m + cycle_s / 60.0 + load_m + load_s / 60.0

        ok_qty  = int(entry.get("ok_qty") or 0)
        rej_qty = int(entry.get("rejected_qty") or 0)
        hold_qty = int(entry.get("hold_qty") or 0)
        total_qty = ok_qty + rej_qty + hold_qty

        planned = float(entry.get("planned_minutes") or 0)
        run_minutes = ok_qty * ideal_cycle if ok_qty > 0 else 0.0

        utilization = max(planned - ar_loss, 0.0)
        after_pr    = max(utilization - pr_loss, 0.0)

        ar_ratio  = (utilization / planned) if planned > 0 else 0.0
        pr_ratio  = (run_minutes / after_pr) if after_pr > 0 else 0.0
        qr_ratio  = (ok_qty / total_qty) if total_qty > 0 else 1.0
        oee_ratio = ar_ratio * pr_ratio * qr_ratio

        target_qty = ((planned - target_deduct) / ideal_cycle) if ideal_cycle > 0 else 0.0
        plan_vs_actual = (total_qty / target_qty) if target_qty > 0 else 0.0

        return jsonify({
            "success": True,
            "calculation_ready": True,
            "machine_no": machine_no,
            "session_id": session_id,
            "machine_id": entry.get("machine_id"),
            "shift_name": entry.get("shift_name"),
            "planned_minutes": round(planned, 2),
            "ideal_cycle_minutes": round(ideal_cycle, 4),
            "run_minutes": round(run_minutes, 2),
            "ar_loss_minutes": round(ar_loss, 2),
            "pr_loss_minutes": round(pr_loss, 2),
            "utilization_minutes": round(utilization, 2),
            "after_pr_minutes": round(after_pr, 2),
            "target_qty": round(target_qty, 4),
            "total_qty": total_qty,
            "ok_qty": ok_qty,
            "rejected_qty": rej_qty,
            "hold_qty": hold_qty,
            "plan_vs_actual": round(plan_vs_actual, 4),
            "ar_ratio": ar_ratio,
            "pr_ratio": pr_ratio,
            "qr_ratio": qr_ratio,
            "oee_ratio": oee_ratio,
            "ar_pct":  round(ar_ratio  * 100, 2),
            "pr_pct":  round(pr_ratio  * 100, 2),
            "qr_pct":  round(qr_ratio  * 100, 2),
            "oee_pct": round(oee_ratio * 100, 2),
            "plva_pct": round(plan_vs_actual * 100, 2),
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
'''


# Find function definition and replace up to next @route or def at column 0
m = re.search(
    r"^def machine_oee_live_session_calc_v1\b.*?:\n",
    src,
    re.MULTILINE | re.DOTALL,
)
if not m:
    print("MISS: function header not found")
else:
    tail = src[m.end():]
    m2 = re.search(
        r"^(@quality_check_bp\.route\(|# MACHINE_OEE_[A-Z0-9_]+\n@quality_check_bp\.route\(|def [a-z_])",
        tail,
        re.MULTILINE,
    )
    end = m.end() + m2.start() if m2 else len(src)
    src = src[:m.start()] + NEW_FN.rstrip() + "\n\n\n" + src[end:]
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)
    print("OK — machine_oee_live_session_calc_v1 replaced")
