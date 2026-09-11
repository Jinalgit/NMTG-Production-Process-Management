"""
Step 7 — Add 'Activity Min' + 'Activity Loss' columns to Machine-wise
and Operator-wise tables in the OEE Summary template.
"""

import os

TARGET = r"D:\Het\demo2\templates\oee_machine_summary.html"

with open(TARGET, encoding="utf-8") as f:
    src = f.read()

results = []


# ============================================================
# 1. Machine-wise <thead> — add 2 new <th>
# ============================================================
old_mw_thead = (
    '          <th>AR Loss</th>\n'
    '          <th>PR Loss</th>\n'
    '          <th>Plan vs Actual</th>'
)
new_mw_thead = (
    '          <th>AR Loss</th>\n'
    '          <th>PR Loss</th>\n'
    '          <th>Activity Min</th>\n'
    '          <th>Activity Loss</th>\n'
    '          <th>Plan vs Actual</th>'
)

# Machine-wise appears first; there's a second identical block for Operator-wise.
# Replace only the FIRST occurrence to hit machine-wise.
if src.count(old_mw_thead) >= 1:
    src = src.replace(old_mw_thead, new_mw_thead, 1)
    results.append(("Machine-wise <thead>", "OK"))
else:
    results.append(("Machine-wise <thead>", "MISS"))


# ============================================================
# 2. Operator-wise <thead> — same 2 new columns
# ============================================================
if src.count(old_mw_thead) >= 1:
    # After the first replace above, the remaining occurrence is Operator-wise
    src = src.replace(old_mw_thead, new_mw_thead, 1)
    results.append(("Operator-wise <thead>", "OK"))
else:
    results.append(("Operator-wise <thead>", "MISS"))


# ============================================================
# 3. Machine-wise row JS — add 2 new <td> before Plan vs Actual
# ============================================================
old_mw_row = (
    '          "<td>" + fmt(m.ar_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + fmt(m.pr_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + (m.plan_vs_actual === null ? "–" : fmtPct(m.plan_vs_actual * 100)) + "</td>" +'
)
new_mw_row = (
    '          "<td>" + fmt(m.ar_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + fmt(m.pr_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + fmt(m.activity_min, 1) + "</td>" +\n'
    '          "<td>" + fmt(m.activity_loss_min, 1) + "</td>" +\n'
    '          "<td>" + (m.plan_vs_actual === null ? "–" : fmtPct(m.plan_vs_actual * 100)) + "</td>" +'
)
if old_mw_row in src:
    src = src.replace(old_mw_row, new_mw_row)
    results.append(("Machine-wise row JS", "OK"))
else:
    results.append(("Machine-wise row JS", "MISS"))


# ============================================================
# 4. Operator-wise row JS — same 2 new <td>
# ============================================================
old_ow_row = (
    '          "<td>" + fmt(o.ar_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + fmt(o.pr_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + (o.plan_vs_actual === null ? "–" : fmtPct(o.plan_vs_actual * 100)) + "</td>" +'
)
new_ow_row = (
    '          "<td>" + fmt(o.ar_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + fmt(o.pr_loss_minutes, 1) + "</td>" +\n'
    '          "<td>" + fmt(o.activity_min, 1) + "</td>" +\n'
    '          "<td>" + fmt(o.activity_loss_min, 1) + "</td>" +\n'
    '          "<td>" + (o.plan_vs_actual === null ? "–" : fmtPct(o.plan_vs_actual * 100)) + "</td>" +'
)
if old_ow_row in src:
    src = src.replace(old_ow_row, new_ow_row)
    results.append(("Operator-wise row JS", "OK"))
else:
    results.append(("Operator-wise row JS", "MISS"))


# ============================================================
# 5. Bump the colspan constants (+2 each)
# ============================================================
old_consts = (
    "  const MACH_COL_COUNT = CAN_EXPORT ? 17 : 16;\n"
    "  const OP_COL_COUNT   = 16;"
)
new_consts = (
    "  const MACH_COL_COUNT = CAN_EXPORT ? 19 : 18;\n"
    "  const OP_COL_COUNT   = 18;"
)
if old_consts in src:
    src = src.replace(old_consts, new_consts)
    results.append(("Colspan constants", "OK"))
else:
    results.append(("Colspan constants", "MISS"))


# ============================================================
# 6. Update the initial "Loading..." <td colspan="..."> for both tables
# ============================================================
if 'colspan="17" class="oees-loading">Loading...</td>' in src:
    src = src.replace(
        'colspan="17" class="oees-loading">Loading...</td>',
        'colspan="19" class="oees-loading">Loading...</td>',
    )
    results.append(("Loading colspan (machine)", "OK"))
else:
    results.append(("Loading colspan (machine)", "MISS"))

if 'colspan="16" class="oees-loading">Loading...</td>' in src:
    src = src.replace(
        'colspan="16" class="oees-loading">Loading...</td>',
        'colspan="18" class="oees-loading">Loading...</td>',
    )
    results.append(("Loading colspan (operator)", "OK"))
else:
    results.append(("Loading colspan (operator)", "MISS"))


with open(TARGET, "w", encoding="utf-8") as f:
    f.write(src)

print("=" * 60)
print("Step 7 patch results")
print("=" * 60)
for name, status in results:
    print(f"  {status:4s}  {name}")
print()
