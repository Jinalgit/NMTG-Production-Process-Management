"""
Step 9 — Excel export includes ACTIVITY rows.

Patches oee_machine_summary.py export endpoint:
  1. Restrict the existing production SELECT to activity_type IS NULL.
  2. Add a second SELECT for activity rows.
  3. Write activity rows to the same sheet after production, prefixed by
     a bold 'ACTIVITIES' separator row.
"""

TARGET = r"D:\Het\demo2\routes\oee_machine_summary.py"

with open(TARGET, encoding="utf-8") as f:
    src = f.read()

results = []

# ============================================================
# Patch A — restrict existing production query to non-activity rows
# ============================================================
old_prod_where = (
    "            FROM oee_entries\n"
    "            WHERE record_status = 'active'\n"
    "              AND machine_id = %s\n"
    "              AND entry_date BETWEEN %s AND %s\n"
    "            ORDER BY entry_date, shift_name, start_time, id"
)
new_prod_where = (
    "            FROM oee_entries\n"
    "            WHERE record_status = 'active'\n"
    "              AND machine_id = %s\n"
    "              AND entry_date BETWEEN %s AND %s\n"
    "              AND activity_type IS NULL\n"
    "            ORDER BY entry_date, shift_name, start_time, id"
)
if old_prod_where in src:
    src = src.replace(old_prod_where, new_prod_where)
    results.append(("Production query filter", "OK"))
else:
    results.append(("Production query filter", "MISS"))

# ============================================================
# Patch B — after production section, fetch + write activity rows
# ============================================================
old_end = (
    "        # ---- serialize to bytes and return ----\n"
    "        buf = io.BytesIO()"
)

new_end = (
    "        # ============================================================\n"
    "        # Activity rows (Tool Room / Development) — appended below\n"
    "        # ============================================================\n"
    "        conn2 = get_connection()\n"
    "        cur2  = conn2.cursor(dictionary=True)\n"
    "        cur2.execute(\n"
    "            \"\"\"\n"
    "            SELECT\n"
    "                id, entry_date, shift_name,\n"
    "                machine_no, machine_name, zone,\n"
    "                operator_employee_no, operator_name,\n"
    "                item_name, activity_type,\n"
    "                start_time, end_time,\n"
    "                planned_minutes, ar_loss_minutes,\n"
    "                utilization_minutes, total_loss_minutes,\n"
    "                remarks\n"
    "            FROM oee_entries\n"
    "            WHERE record_status = 'active'\n"
    "              AND machine_id = %s\n"
    "              AND entry_date BETWEEN %s AND %s\n"
    "              AND activity_type IS NOT NULL\n"
    "            ORDER BY entry_date, shift_name, start_time, id\n"
    "            \"\"\",\n"
    "            (machine_id, str(fd), str(td)),\n"
    "        )\n"
    "        activity_entries = cur2.fetchall()\n"
    "\n"
    "        # activity-losses pivot\n"
    "        act_ids = [a['id'] for a in activity_entries]\n"
    "        act_losses = {aid: {c: 0.0 for c in _ALL_LOSS_CODES} for aid in act_ids}\n"
    "        if act_ids:\n"
    "            ph = ','.join(['%s'] * len(act_ids))\n"
    "            cur2.execute(\n"
    "                f\"SELECT oee_entry_id, loss_code_snapshot, loss_minutes \"\n"
    "                f\"FROM oee_entry_losses WHERE oee_entry_id IN ({ph})\",\n"
    "                act_ids,\n"
    "            )\n"
    "            for lr in cur2.fetchall():\n"
    "                aid  = lr['oee_entry_id']\n"
    "                code = str(lr['loss_code_snapshot'] or '').strip().upper()\n"
    "                if aid in act_losses and code in act_losses[aid]:\n"
    "                    try:\n"
    "                        act_losses[aid][code] += float(lr['loss_minutes'] or 0)\n"
    "                    except (TypeError, ValueError):\n"
    "                        pass\n"
    "        cur2.close(); conn2.close()\n"
    "\n"
    "        # write section header row + activity rows\n"
    "        if activity_entries:\n"
    "            sep_row = ws.max_row + 2\n"
    "            hdr_cell = ws.cell(row=sep_row, column=1, value='ACTIVITIES (Tool Room / Development)')\n"
    "            hdr_cell.font = Font(name='Arial', size=11, bold=True, color='FFFFFF')\n"
    "            hdr_cell.fill = PatternFill('solid', fgColor='C0504D')\n"
    "            hdr_cell.alignment = _EXP_LEFT\n"
    "            ws.merge_cells(start_row=sep_row, start_column=1, end_row=sep_row, end_column=12)\n"
    "\n"
    "            data_row = sep_row + 1\n"
    "            for a in activity_entries:\n"
    "                cycle_time_v = _exp_minsec_to_time(0, 0)\n"
    "                load_time_v  = _exp_minsec_to_time(0, 0)\n"
    "                start_time_v = _exp_time_value(a['start_time'])\n"
    "                end_time_v   = _exp_time_value(a['end_time'])\n"
    "                planned      = float(a['planned_minutes'] or 0)\n"
    "                ar_loss      = float(a['ar_loss_minutes'] or 0)\n"
    "                total_loss   = float(a['total_loss_minutes'] or 0)\n"
    "                util         = float(a['utilization_minutes'] or 0)\n"
    "                ar_ratio     = (util / planned) if planned > 0 else 0.0\n"
    "\n"
    "                base_values = [\n"
    "                    a['entry_date'],\n"
    "                    _exp_shift_to_display(a['shift_name']),\n"
    "                    a['machine_no'],\n"
    "                    a['machine_name'],\n"
    "                    '',\n"
    "                    a['operator_employee_no'] or '',\n"
    "                    a['operator_name'] or '',\n"
    "                    '',\n"
    "                    a['activity_type'] or '',\n"
    "                    '',\n"
    "                    '',\n"
    "                    a['item_name'] or '',\n"
    "                    None,\n"
    "                    None,\n"
    "                    0, 0, 0,\n"
    "                    start_time_v,\n"
    "                    end_time_v,\n"
    "                    planned,\n"
    "                    None,\n"
    "                    total_loss,\n"
    "                    None,\n"
    "                    None,\n"
    "                    0,\n"
    "                    None,\n"
    "                    None,\n"
    "                    ar_ratio,\n"
    "                    None,\n"
    "                    None,\n"
    "                    'Detailed Loss Entered' if total_loss > 0 else '',\n"
    "                    a['remarks'] or '',\n"
    "                    'Completed',\n"
    "                ]\n"
    "                for c_idx, val in enumerate(base_values, start=1):\n"
    "                    cell = ws.cell(row=data_row, column=c_idx, value=val)\n"
    "                    cell.font = _EXP_BODY_FONT\n"
    "                    cell.border = _EXP_BORDER\n"
    "                ws.cell(row=data_row, column=1).number_format  = 'yyyy-mm-dd'\n"
    "                ws.cell(row=data_row, column=18).number_format = 'hh:mm'\n"
    "                ws.cell(row=data_row, column=19).number_format = 'hh:mm'\n"
    "                ws.cell(row=data_row, column=20).number_format = '0.00'\n"
    "                ws.cell(row=data_row, column=22).number_format = '0.00'\n"
    "                ws.cell(row=data_row, column=28).number_format = '0.00%'\n"
    "\n"
    "                # A1..A27 losses\n"
    "                e_losses = act_losses.get(a['id'], {})\n"
    "                col_start_loss = len(_EXP_BASE_HEADERS) + 1\n"
    "                for i, code in enumerate(_ALL_LOSS_CODES):\n"
    "                    col   = col_start_loss + i\n"
    "                    value = e_losses.get(code, 0.0)\n"
    "                    cell  = ws.cell(row=data_row, column=col, value=value if value else None)\n"
    "                    cell.font   = _EXP_BODY_FONT\n"
    "                    cell.border = _EXP_BORDER\n"
    "                    cell.number_format = '0.00'\n"
    "\n"
    "                # summary block: only AR applies\n"
    "                col_start_summary = col_start_loss + len(_ALL_LOSS_CODES)\n"
    "                summary_vals = [planned, ar_loss, util, 0.0, util, ar_ratio, 0.0, 0.0, ar_ratio]\n"
    "                for i, val in enumerate(summary_vals):\n"
    "                    col  = col_start_summary + i\n"
    "                    cell = ws.cell(row=data_row, column=col, value=val)\n"
    "                    cell.font   = _EXP_BODY_FONT\n"
    "                    cell.border = _EXP_BORDER\n"
    "                    cell.number_format = '0.00' if i < 5 else '0.00%'\n"
    "                data_row += 1\n"
    "\n"
    "        # ---- serialize to bytes and return ----\n"
    "        buf = io.BytesIO()"
)

if old_end in src:
    src = src.replace(old_end, new_end)
    results.append(("Activity export section", "OK"))
else:
    results.append(("Activity export section", "MISS"))


with open(TARGET, "w", encoding="utf-8") as f:
    f.write(src)

print("=" * 60)
print("Step 9 patch results")
print("=" * 60)
for name, status in results:
    print(f"  {status:4s}  {name}")
print()
