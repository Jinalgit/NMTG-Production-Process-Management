"""
Step 1 of the polish plan: empty-state handling in the OEE Dashboard.

Adds:
- Small centered "no data" / "only 1 X" hint cards inside each chart body when data is thin.
- An "AR only" tag on the Loss Category donut when only one category has values.
- CSS for the mini empty-state cards so they match ERPNext restraint.

Touches only templates/oee_dashboard.html.
"""

from pathlib import Path
import re, sys

tpl = Path(r"D:\Het\demo2\templates\oee_dashboard.html")
raw = tpl.read_text(encoding="utf-8")

# ---------- 1) Inject CSS for mini empty state (add if missing) ----------
CSS_BLOCK = """
  /* Empty-state mini card that sits inside a chart body */
  .od-empty-mini {
    height: 100%;
    min-height: 200px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    color: #8d97a1;
    font-size: 12px;
    text-align: center;
  }
  .od-empty-mini .fa { font-size: 22px; color: #c8d0d8; margin-bottom: 2px; }
  .od-empty-mini .hint { font-size: 11px; color: #a9b1b9; }
  .od-tag-corner {
    position: absolute; top: 10px; right: 10px;
    background: #fff4e6; color: #b7791f; border: 1px solid #ffd8a8;
    padding: 2px 8px; border-radius: 3px; font-size: 10px; font-weight: 600;
    letter-spacing: 0.03em;
  }
  .od-card { position: relative; }
"""
if ".od-empty-mini" not in raw:
    m = re.search(r"(\.od-canvas-wrap[^{]*\{[^}]*\})", raw)  # if a canvas class exists, insert nearby
    if m:
        raw = raw[:m.end()] + CSS_BLOCK + raw[m.end():]
    else:
        raw = raw.replace(".od-chart { min-height: 260px; }", ".od-chart { min-height: 260px; }\n" + CSS_BLOCK, 1)
    print("[OK] CSS block for empty-state added")
else:
    print("[SKIP] empty-state CSS already present")

# ---------- 2) Inject a shared helper `emptyMini` and update chart renderers ----------
HELPER_JS = """
  // ---- empty-state helper (added by Step 1) ----
  function emptyMini(id, msg, hint, icon) {
    var el = document.getElementById(id);
    if (!el) return;
    el.innerHTML =
      '<div class="od-empty-mini">' +
        '<i class="fa fa-' + (icon || "inbox") + '"></i>' +
        '<div>' + msg + '</div>' +
        (hint ? '<div class="hint">' + hint + '</div>' : '') +
      '</div>';
  }
  function cornerTag(id, text) {
    var el = document.getElementById(id);
    if (!el || !el.parentElement) return;
    var card = el.closest('.od-card');
    if (!card) return;
    // remove any prior tag
    var prev = card.querySelector('.od-tag-corner');
    if (prev) prev.remove();
    var t = document.createElement('div');
    t.className = 'od-tag-corner';
    t.textContent = text;
    card.appendChild(t);
  }
  function clearCornerTag(id) {
    var el = document.getElementById(id);
    if (!el) return;
    var card = el.closest('.od-card');
    if (!card) return;
    var prev = card.querySelector('.od-tag-corner');
    if (prev) prev.remove();
  }
"""
if "function emptyMini(" not in raw:
    # Insert right after `function destroy(id)` block
    anchor = "function destroy(id){"
    idx = raw.find(anchor)
    if idx == -1:
        print("ABORT — could not find `function destroy(id){` anchor.")
        sys.exit(0)
    # find end of that function
    brace = raw.find("}", idx)
    if brace == -1:
        print("ABORT — could not close destroy() function.")
        sys.exit(0)
    raw = raw[:brace+1] + "\n" + HELPER_JS + raw[brace+1:]
    print("[OK] emptyMini + cornerTag helpers injected")
else:
    print("[SKIP] emptyMini helper already present")

# ---------- 3) Guard each chart renderer with data-thickness checks ----------
def swap(pattern, replacement, label, flags=0):
    global raw
    new, n = re.subn(pattern, replacement, raw, flags=flags | re.DOTALL)
    if n:
        raw = new
        print(f"[OK] {label} (x{n})")
    else:
        print(f"[SKIP] {label}")

# Trend: need at least 2 dates
swap(
    r'function renderTrend\(rows\)\{\s*destroy\("ch-trend"\);\s*if \(!rows \|\| !rows\.length\) \{[^}]*\}',
    'function renderTrend(rows){\n'
    '    destroy("ch-trend");\n'
    '    clearCornerTag("ch-trend");\n'
    '    if (!rows || rows.length === 0) { emptyMini("ch-trend", "No production data in this period", "Try a wider date range or clear filters", "clock-o"); return; }\n'
    '    if (rows.length === 1)          { emptyMini("ch-trend", "Only 1 day of data", "Select a longer period to see the trend", "calendar"); return; }',
    "Trend guard"
)

# Loss Category: none / one-only
swap(
    r'function renderLossCat\(d\)\{\s*destroy\("ch-loss-cat"\);\s*var arr = \[d\.AR\|\|0, d\.PR\|\|0, d\.QR\|\|0\];\s*if \(arr\.reduce\([^)]*\) === 0\) \{[^}]*\}',
    'function renderLossCat(d){\n'
    '    destroy("ch-loss-cat");\n'
    '    clearCornerTag("ch-loss-cat");\n'
    '    var arr = [d.AR||0, d.PR||0, d.QR||0];\n'
    '    var tot = arr.reduce(function(a,b){return a+b;},0);\n'
    '    if (tot === 0) { emptyMini("ch-loss-cat", "No losses recorded", "", "check-circle"); return; }\n'
    '    var nonZero = arr.filter(function(x){return x>0;}).length;\n'
    '    if (nonZero === 1) { cornerTag("ch-loss-cat", ["AR","PR","QR"][arr.indexOf(Math.max.apply(null,arr))] + " only"); }',
    "Loss Category guard + AR-only tag"
)

# Machine Ranking: none / one-only
swap(
    r'function renderMachineRank\(rows\)\{\s*destroy\("ch-machine-rank"\);\s*if \(!rows \|\| !rows\.length\) \{[^}]*\}',
    'function renderMachineRank(rows){\n'
    '    destroy("ch-machine-rank");\n'
    '    clearCornerTag("ch-machine-rank");\n'
    '    if (!rows || rows.length === 0) { emptyMini("ch-machine-rank", "No machines in this period", "Try a wider date range", "cog"); return; }\n'
    '    if (rows.length === 1) { emptyMini("ch-machine-rank", "Only 1 machine active", "Broaden filters to compare across machines", "cogs"); return; }',
    "Machine Ranking guard"
)

# Shift Comparison: none / one-only
swap(
    r'function renderShift\(rows\)\{\s*destroy\("ch-shift"\);\s*if \(!rows \|\| !rows\.length\) \{[^}]*\}',
    'function renderShift(rows){\n'
    '    destroy("ch-shift");\n'
    '    clearCornerTag("ch-shift");\n'
    '    if (!rows || rows.length === 0) { emptyMini("ch-shift", "No shift data", "", "clock-o"); return; }\n'
    '    if (rows.length === 1) { emptyMini("ch-shift", "Only " + (rows[0].shift || "Shift 1") + " ran", "Nothing to compare against", "columns"); return; }',
    "Shift guard"
)

# Loss Pareto: none / one-only
swap(
    r'function renderPareto\(rows\)\{\s*destroy\("ch-pareto"\);\s*if \(!rows \|\| !rows\.length\) \{[^}]*\}',
    'function renderPareto(rows){\n'
    '    destroy("ch-pareto");\n'
    '    clearCornerTag("ch-pareto");\n'
    '    if (!rows || rows.length === 0) { emptyMini("ch-pareto", "No loss reasons in this period", "", "check-circle"); return; }\n'
    '    if (rows.length === 1) { emptyMini("ch-pareto", "Only 1 loss reason logged", "Pareto needs 2+ reasons to be useful", "signal"); return; }',
    "Pareto guard"
)

# Operator table: keep existing table empty message (already handled)

# ---------- 4) Write ----------
tpl.write_text(raw, encoding="utf-8")
print("[DONE] Step 1 applied. Hard refresh /oee-dashboard.")
