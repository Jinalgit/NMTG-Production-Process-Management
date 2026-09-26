"""
Downloads Anime.js locally and rewrites the OEE Dashboard template
to use it. All previous CSS @keyframes are removed.

Anime.js is a small (17 KB) purpose-built library for SVG animation.
Its restart-on-call behavior is exactly what we need for the "animate
on every Apply/Refresh" requirement.
"""

from pathlib import Path
import urllib.request, ssl, sys

# ============================================================
# 1) Download Anime.js to Flask static/vendor
# ============================================================
static_dir = Path(r"D:\Het\demo2\static\vendor")
static_dir.mkdir(parents=True, exist_ok=True)

ctx = ssl.create_default_context()
url_candidates = [
    "https://unpkg.com/animejs@3.2.1/lib/anime.min.js",
    "https://cdn.jsdelivr.net/npm/animejs@3.2.1/lib/anime.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/animejs/3.2.1/anime.min.js",
    "https://unpkg.com/animejs@3.2.2/lib/anime.min.js",
    "https://cdn.jsdelivr.net/npm/animejs@3.2.2/lib/anime.min.js",
]
anime_path = static_dir / "anime.min.js"

def _dl(url, dst):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=25) as r:
            data = r.read()
        if len(data) < 5000:
            print(f"  [SKIP] too small ({len(data)} bytes)")
            return False
        dst.write_bytes(data)
        print(f"  [OK] {len(data)} bytes -> {dst.name}")
        return True
    except Exception as e:
        print(f"  [FAIL] {url.split('/')[-1]}: {type(e).__name__}")
        return False

print("=== Anime.js download ===")
got = False
for u in url_candidates:
    print("Trying:", u)
    if _dl(u, anime_path):
        got = True
        break

if not got:
    print("ABORT — could not download Anime.js. Tell me and I attach the file directly.")
    sys.exit(0)

# ============================================================
# 2) Rewrite the template
# ============================================================
tpl_path = Path(r"D:\Het\demo2\templates\oee_dashboard.html")

NEW_TPL = r"""{% extends "base.html" %}
{% block title %}OEE Dashboard{% endblock %}
{% block content %}
<link rel="stylesheet" href="{{ url_for('static', filename='vendor/frappe-charts.min.css') }}">
<style>
  :root {
    --tp: #1f272e;
    --ts: #525f6b;
    --tm: #8d97a1;
    --bd: #e2e6ea;
    --rl: #f5f7fa;
    --rh: #fbfcfd;
    --ac: #2490ef;
    --ac-soft: #eaf4fd;
    --card: #ffffff;
  }
  .od { padding: 18px 22px; font-family: "IBM Plex Sans", "Inter", system-ui, sans-serif; color: var(--tp); background: #f5f7fa; min-height: 100vh; }

  .od-head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 12px; }
  .od-title { font-size: 20px; font-weight: 600; margin: 0; }
  .od-sub { font-size: 12px; color: var(--ts); margin-top: 3px; }

  .od-btn { background: var(--ac); color: #fff; border: none; border-radius: 4px; padding: 8px 13px; font-size: 12px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 7px; transition: background .15s; }
  .od-btn:hover { background: #1a7fd8; }
  .od-btn.ghost { background: #fff; color: var(--tp); border: 1px solid var(--bd); }
  .od-btn.ghost:hover { background: var(--rl); }
  .od-btn .spin { animation: spin .9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .od-presets { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
  .od-preset { padding: 6px 13px; background: #fff; border: 1px solid var(--bd); border-radius: 4px; font-size: 12px; color: var(--ts); cursor: pointer; transition: all .12s; }
  .od-preset:hover { color: var(--tp); border-color: #c8d0d8; }
  .od-preset.active { background: var(--tp); color: #fff; border-color: var(--tp); }

  .od-filters { background: #fff; border: 1px solid var(--bd); border-radius: 4px; padding: 12px 14px; display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; margin-bottom: 10px; }
  .od-fld { display: flex; flex-direction: column; gap: 4px; }
  .od-fld label { font-size: 10px; font-weight: 600; color: var(--ts); text-transform: uppercase; letter-spacing: 0.05em; }
  .od-fld input, .od-fld select { height: 32px; padding: 0 10px; border: 1px solid var(--bd); border-radius: 4px; font-family: inherit; font-size: 12.5px; color: var(--tp); background: #fff; min-width: 130px; transition: border-color .15s; }
  .od-fld input:focus, .od-fld select:focus { border-color: var(--ac); outline: none; }
  .od-filters .sp { flex: 1; }

  .od-chips { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
  .od-chip { background: var(--ac-soft); color: var(--ac); font-size: 11px; font-weight: 500; padding: 4px 10px; border-radius: 4px; display: inline-flex; align-items: center; gap: 8px; }
  .od-chip .x { cursor: pointer; opacity: 0.7; font-weight: 700; }
  .od-chip .x:hover { opacity: 1; }

  .od-tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--bd); margin-bottom: 14px; }
  .od-tab { padding: 10px 16px 9px; background: transparent; border: none; border-bottom: 2px solid transparent; color: var(--ts); font-weight: 500; font-size: 12.5px; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: color .15s, border-color .15s; }
  .od-tab:hover { color: var(--tp); }
  .od-tab.active { color: var(--ac); border-bottom-color: var(--ac); }

  .od-nums { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 12px; }
  .od-num { background: var(--card); border: 1px solid var(--bd); border-radius: 4px; padding: 14px 16px; }
  .od-num-l { font-size: 11px; color: var(--ts); font-weight: 500; margin-bottom: 6px; }
  .od-num-v { font-size: 24px; font-weight: 600; color: var(--tp); font-variant-numeric: tabular-nums; line-height: 1.1; }
  .od-num-v .u { font-size: 13px; font-weight: 500; color: var(--ts); margin-left: 2px; }
  .od-num-d { font-size: 11px; color: var(--tm); margin-top: 4px; }

  .od-grid { display: grid; gap: 12px; margin-bottom: 12px; }
  .od-g21 { grid-template-columns: 2fr 1fr; }
  .od-g11 { grid-template-columns: 1fr 1fr; }
  .od-gfull { grid-template-columns: 1fr; }
  .od-card { background: var(--card); border: 1px solid var(--bd); border-radius: 4px; padding: 14px 16px; }
  .od-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; padding-bottom: 8px; border-bottom: 1px solid var(--bd); }
  .od-card-title { font-size: 12px; font-weight: 600; color: var(--tp); display: inline-flex; align-items: center; gap: 8px; }
  .od-card-title .fa { color: var(--ac); font-size: 12px; }
  .od-card-sub { font-size: 10.5px; color: var(--ts); }
  .od-chart { min-height: 260px; }
  .od-chart.tall { min-height: 300px; }
  .od-chart.short { min-height: 200px; }

  .od-pane { display: none; }
  .od-pane.active { display: block; }
  .od-empty { padding: 40px; text-align: center; color: var(--tm); font-size: 13px; }
  .od-empty .fa { font-size: 26px; display: block; margin-bottom: 10px; color: #c8d0d8; }

  .od-mini { width: 100%; border-collapse: collapse; font-size: 12px; }
  .od-mini th { text-align: left; color: var(--ts); font-weight: 600; text-transform: uppercase; font-size: 10px; padding: 7px 6px; border-bottom: 1px solid var(--bd); }
  .od-mini td { padding: 8px 6px; border-bottom: 1px solid var(--rl); }
  .od-mini td.num { text-align: right; font-family: "IBM Plex Mono", monospace; font-weight: 500; color: var(--tp); font-variant-numeric: tabular-nums; }
  .od-mini tbody tr:hover { background: var(--rl); }

  .od-status { padding: 10px 12px; background: #fff4e6; border: 1px solid #ffd8a8; border-radius: 4px; font-size: 12px; color: #b7791f; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  .od-status.err { background: #fdecec; border-color: #f2c1c1; color: #a12c39; }

  .od-chart .chart-container { background: transparent !important; }
  .od-chart .frappe-chart .title { font-family: "IBM Plex Sans", sans-serif !important; font-size: 12px !important; fill: var(--ts) !important; }
  .od-chart svg text { font-family: "IBM Plex Sans", sans-serif !important; }
  .od-chart .graph-svg-tip { font-size: 11px !important; }

  @media (max-width: 1200px) {
    .od-nums { grid-template-columns: repeat(2, 1fr); }
    .od-g21, .od-g11 { grid-template-columns: 1fr; }
  }
</style>

<div class="od">
  <div class="od-head">
    <div>
      <h1 class="od-title">OEE Dashboard</h1>
      <div class="od-sub" id="od-sub-text">Loading...</div>
    </div>
    <div>
      <button class="od-btn ghost" id="od-refresh"><i class="fa fa-refresh" id="od-refresh-i"></i> Refresh</button>
    </div>
  </div>

  <div class="od-presets">
    <span class="od-preset" data-preset="today">Today</span>
    <span class="od-preset" data-preset="yesterday">Yesterday</span>
    <span class="od-preset" data-preset="this_week">This Week</span>
    <span class="od-preset" data-preset="last_week">Last Week</span>
    <span class="od-preset active" data-preset="this_month">This Month</span>
    <span class="od-preset" data-preset="last_month">Last Month</span>
  </div>

  <div class="od-filters">
    <div class="od-fld"><label>From Date</label><input type="date" id="od-from"></div>
    <div class="od-fld"><label>To Date</label><input type="date" id="od-to"></div>
    <div class="od-fld"><label>Zone</label><select id="od-zone"><option value="">All</option></select></div>
    <div class="od-fld"><label>Machine</label><select id="od-machine"><option value="">All</option></select></div>
    <div class="od-fld"><label>Operator</label><select id="od-operator"><option value="">All</option></select></div>
    <div class="sp"></div>
    <button class="od-btn" id="od-apply"><i class="fa fa-check"></i> Apply</button>
    <button class="od-btn ghost" id="od-reset">Reset</button>
  </div>

  <div class="od-chips" id="od-chips"></div>

  <div class="od-tabs">
    <button class="od-tab active" data-p="prod"><i class="fa fa-cogs"></i> Production (Job Card)</button>
    <button class="od-tab" data-p="ml"><i class="fa fa-exclamation-triangle"></i> Machine Losses (No JC)</button>
    <button class="od-tab" data-p="tr"><i class="fa fa-wrench"></i> Tool Room + Development</button>
    <button class="od-tab" data-p="tool"><i class="fa fa-cube"></i> Tooling Activity</button>
  </div>

  <div id="od-status-bar"></div>

  <div class="od-pane active" data-pane="prod">

    <div class="od-nums">
      <div class="od-num"><div class="od-num-l">Sessions</div><div class="od-num-v" id="n-sessions">0</div><div class="od-num-d">production job-card sessions</div></div>
      <div class="od-num"><div class="od-num-l">Avg OEE</div><div class="od-num-v"><span id="n-oee">0</span><span class="u">%</span></div><div class="od-num-d">across all sessions</div></div>
      <div class="od-num"><div class="od-num-l">OK Produced</div><div class="od-num-v" id="n-ok">0</div><div class="od-num-d" id="n-ok-d">good quantity</div></div>
      <div class="od-num"><div class="od-num-l">Rejected</div><div class="od-num-v" id="n-rej">0</div><div class="od-num-d" id="n-rej-d">rejected quantity</div></div>
    </div>

    <div class="od-grid od-g21">
      <div class="od-card" data-anim-card>
        <div class="od-card-head"><div class="od-card-title"><i class="fa fa-line-chart"></i> OEE Trend</div><div class="od-card-sub">daily average</div></div>
        <div class="od-chart" id="ch-trend"></div>
      </div>
      <div class="od-card" data-anim-card>
        <div class="od-card-head"><div class="od-card-title"><i class="fa fa-pie-chart"></i> Loss Category</div><div class="od-card-sub">total lost min</div></div>
        <div class="od-chart short" id="ch-loss-cat"></div>
      </div>
    </div>

    <div class="od-grid od-g11">
      <div class="od-card" data-anim-card>
        <div class="od-card-head"><div class="od-card-title"><i class="fa fa-bar-chart"></i> Machine OEE Ranking</div><div class="od-card-sub">top 10</div></div>
        <div class="od-chart tall" id="ch-machine-rank"></div>
      </div>
      <div class="od-card" data-anim-card>
        <div class="od-card-head"><div class="od-card-title"><i class="fa fa-columns"></i> Shift Comparison</div><div class="od-card-sub">avg OEE by shift</div></div>
        <div class="od-chart tall" id="ch-shift"></div>
      </div>
    </div>

    <div class="od-grid od-gfull">
      <div class="od-card" data-anim-card>
        <div class="od-card-head"><div class="od-card-title"><i class="fa fa-signal"></i> Loss Pareto - Top 10 Reasons</div><div class="od-card-sub">bars: minutes - line: cumulative %</div></div>
        <div class="od-chart tall" id="ch-pareto"></div>
      </div>
    </div>

    <div class="od-grid od-g11">
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-user"></i> Operator Ranking</div><div class="od-card-sub">top by avg OEE</div></div><div id="op-tbl"></div></div>
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-th"></i> Zone Comparison</div><div class="od-card-sub">avg OEE by zone</div></div><div id="zn-tbl"></div></div>
    </div>
  </div>

  <div class="od-pane" data-pane="ml"><div class="od-card"><div class="od-empty"><i class="fa fa-clock-o"></i>Machine Losses (No JC) charts are coming in the next step.</div></div></div>
  <div class="od-pane" data-pane="tr"><div class="od-card"><div class="od-empty"><i class="fa fa-clock-o"></i>Tool Room + Development charts are coming in the next step.</div></div></div>
  <div class="od-pane" data-pane="tool"><div class="od-card"><div class="od-empty"><i class="fa fa-clock-o"></i>Tooling Activity charts are coming in the next step.</div></div></div>
</div>

<script src="{{ url_for('static', filename='vendor/frappe-charts.min.iife.js') }}"></script>
<script src="{{ url_for('static', filename='vendor/anime.min.js') }}"></script>
<script>
(function () {
  var PAL = {
    blue: "#2490ef", lblue: "#7cd6fd", purple: "#743ee2", green: "#28a745",
    amber: "#ffa00a", red: "#ff5858", teal: "#5e64ff", gray: "#a9a9a9", dark: "#1f272e"
  };
  var charts = {};
  function $(s){return document.querySelector(s);}
  function fmt(n, d){ if (n===null||n===undefined||isNaN(n)) return "-"; return Number(n).toFixed(d===undefined?1:d); }
  function toIso(dt){ return dt.getFullYear()+"-"+String(dt.getMonth()+1).padStart(2,"0")+"-"+String(dt.getDate()).padStart(2,"0"); }

  var today = new Date();
  $("#od-from").value = toIso(new Date(today.getFullYear(), today.getMonth(), 1));
  $("#od-to").value = toIso(today);

  // ================================================================
  // ANIMATION LAYER using Anime.js
  // ================================================================
  function animateChart(containerId) {
    var container = document.getElementById(containerId);
    if (!container || typeof anime === "undefined") return;

    // Card wrapper: fade + subtle rise + micro-scale
    var card = container.closest("[data-anim-card]");
    if (card) {
      anime.remove(card);
      anime({
        targets: card,
        opacity: [0, 1],
        translateY: [8, 0],
        scale: [0.985, 1],
        duration: 500,
        easing: "easeOutQuart"
      });
    }

    var svg = container.querySelector("svg");
    if (!svg) return;

    // BARS
    var bars = Array.prototype.slice.call(svg.querySelectorAll("rect"));
    bars = bars.filter(function(r){
      var h = parseFloat(r.getAttribute("height") || "0");
      return h > 1;
    });
    if (bars.length) {
      bars.forEach(function(r){
        r.style.transformBox = "fill-box";
        r.style.transformOrigin = "center bottom";
      });
      anime.remove(bars);
      anime({
        targets: bars,
        scaleY: [0, 1],
        duration: 650,
        delay: anime.stagger(45, { start: 100 }),
        easing: "easeOutQuart"
      });
    }

    // LINES: stroke-only <path> and <polyline>
    var strokes = [];
    svg.querySelectorAll("path, polyline").forEach(function(el){
      var s = el.getAttribute("stroke");
      var f = el.getAttribute("fill");
      var isStroke = s && s !== "none" && (!f || f === "none" || f === "transparent");
      if (isStroke && el.getTotalLength) strokes.push(el);
    });
    if (strokes.length) {
      anime.remove(strokes);
      anime({
        targets: strokes,
        strokeDashoffset: [anime.setDashoffset, 0],
        duration: 850,
        delay: anime.stagger(70, { start: 150 }),
        easing: "easeOutCubic"
      });
    }

    // PIE SLICES: filled <path>
    var slices = [];
    svg.querySelectorAll("path").forEach(function(el){
      var f = el.getAttribute("fill");
      if (f && f !== "none" && f !== "transparent") slices.push(el);
    });
    if (slices.length) {
      slices.forEach(function(el){
        el.style.transformBox = "fill-box";
        el.style.transformOrigin = "center";
      });
      anime.remove(slices);
      anime({
        targets: slices,
        opacity: [0, 1],
        scale: [0.75, 1],
        duration: 550,
        delay: anime.stagger(90, { start: 100 }),
        easing: "easeOutQuart"
      });
    }

    // DOTS
    var dots = Array.prototype.slice.call(svg.querySelectorAll("circle"));
    if (dots.length) {
      dots.forEach(function(c){
        c.style.transformBox = "fill-box";
        c.style.transformOrigin = "center";
      });
      anime.remove(dots);
      anime({
        targets: dots,
        opacity: [0, 1],
        scale: [0, 1],
        duration: 400,
        delay: anime.stagger(25, { start: 500 }),
        easing: "easeOutBack"
      });
    }
  }

  function afterFrappe(containerId) {
    requestAnimationFrame(function() {
      requestAnimationFrame(function() {
        animateChart(containerId);
      });
    });
  }

  // ================================================================
  // PRESETS / TABS / BUTTONS
  // ================================================================
  document.querySelectorAll(".od-preset").forEach(function(el){
    el.addEventListener("click", function(){
      document.querySelectorAll(".od-preset").forEach(function(x){x.classList.remove("active");});
      el.classList.add("active");
      applyPreset(el.dataset.preset);
      load();
    });
  });
  function applyPreset(p){
    var d0 = new Date(), d1 = new Date();
    if (p==="yesterday"){ d0.setDate(d0.getDate()-1); d1.setDate(d1.getDate()-1); }
    else if (p==="this_week"){ var day=d0.getDay()||7; d0.setDate(d0.getDate()-day+1); }
    else if (p==="last_week"){ var day=d1.getDay()||7; d1.setDate(d1.getDate()-day); d0=new Date(d1); d0.setDate(d0.getDate()-6); }
    else if (p==="this_month"){ d0.setDate(1); }
    else if (p==="last_month"){ d1.setDate(0); d0=new Date(d1); d0.setDate(1); }
    $("#od-from").value = toIso(d0); $("#od-to").value = toIso(d1);
  }

  document.querySelectorAll(".od-tab").forEach(function(t){
    t.addEventListener("click", function(){
      document.querySelectorAll(".od-tab").forEach(function(x){x.classList.remove("active");});
      t.classList.add("active");
      document.querySelectorAll(".od-pane").forEach(function(p){p.classList.remove("active");});
      document.querySelector('.od-pane[data-pane="'+t.dataset.p+'"]').classList.add("active");
    });
  });

  $("#od-apply").addEventListener("click", load);
  $("#od-refresh").addEventListener("click", load);
  $("#od-reset").addEventListener("click", function(){
    document.querySelectorAll(".od-preset").forEach(function(x){x.classList.remove("active");});
    document.querySelector('.od-preset[data-preset="this_month"]').classList.add("active");
    applyPreset("this_month");
    $("#od-zone").value=""; $("#od-machine").value=""; $("#od-operator").value="";
    load();
  });

  function renderChips() {
    var chips = [];
    var z = $("#od-zone").value, m = $("#od-machine").value, o = $("#od-operator").value;
    if (z) chips.push({k:"zone", label:"Zone: "+z});
    if (m) chips.push({k:"machine", label:"Machine: "+m});
    if (o) chips.push({k:"operator", label:"Operator: "+o});
    var cs = $("#od-chips");
    cs.innerHTML = chips.map(function(c){
      return '<span class="od-chip">' + c.label + ' <span class="x" data-k="'+c.k+'">&times;</span></span>';
    }).join("");
    cs.querySelectorAll(".x").forEach(function(x){
      x.addEventListener("click", function(){
        var k = x.dataset.k;
        if (k==="zone") $("#od-zone").value = "";
        if (k==="machine") $("#od-machine").value = "";
        if (k==="operator") $("#od-operator").value = "";
        load();
      });
    });
  }

  function status(msg, isErr) {
    var el = $("#od-status-bar");
    if (!msg) { el.innerHTML = ""; return; }
    el.innerHTML = '<div class="od-status'+(isErr?' err':'')+'"><i class="fa fa-'+(isErr?"exclamation-circle":"info-circle")+'"></i>'+msg+'</div>';
  }

  function load(){
    var btn = $("#od-refresh-i"); if (btn) btn.classList.add("spin");
    var params = new URLSearchParams({
      from_date: $("#od-from").value,
      to_date: $("#od-to").value,
      zone: $("#od-zone").value || "",
      machine: $("#od-machine").value || "",
      operator: $("#od-operator").value || ""
    });
    fetch("/api/oee-dashboard/production?" + params.toString(), {credentials: "same-origin"})
      .then(function(r){ if (!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
      .then(function(d){
        if (!d.success) throw new Error(d.error || "Unknown error");
        renderAll(d);
        status("");
      })
      .catch(function(e){ status("Failed to load: "+e.message, true); })
      .finally(function(){ if (btn) btn.classList.remove("spin"); });
  }

  function renderAll(d){
    $("#od-sub-text").textContent = "Showing " + d.period.from_date + " to " + d.period.to_date;
    fillDropdown("od-zone", d.filter_options.zones);
    fillDropdown("od-machine", d.filter_options.machines);
    fillDropdown("od-operator", d.filter_options.operators);
    renderChips();

    var k = d.kpis;
    $("#n-sessions").textContent = (k.sessions||0).toLocaleString();
    $("#n-oee").textContent      = fmt(k.avg_oee, 1);
    $("#n-ok").textContent       = (k.total_ok||0).toLocaleString();
    $("#n-rej").textContent      = (k.total_reject||0).toLocaleString();
    var rejRate = (k.total_ok + k.total_reject > 0) ? (k.total_reject * 100 / (k.total_ok + k.total_reject)) : 0;
    $("#n-rej-d").textContent    = "reject rate " + fmt(rejRate, 1) + "%";
    $("#n-ok-d").textContent     = "of " + ((k.total_ok||0) + (k.total_reject||0)).toLocaleString() + " total";

    renderTrend(d.oee_trend);
    renderLossCat(d.loss_category);
    renderMachineRank(d.machine_ranking);
    renderShift(d.shift_comparison);
    renderPareto(d.loss_pareto);
    renderOperators(d.operator_ranking);
    renderZones(d.zone_comparison);
  }

  function fillDropdown(id, arr) {
    var sel = document.getElementById(id);
    if (!sel || !arr) return;
    var prev = sel.value;
    sel.innerHTML = '<option value="">All</option>';
    arr.forEach(function(v){ var o=document.createElement("option"); o.value=v; o.textContent=v; sel.appendChild(o); });
    sel.value = prev;
  }

  function clearContainer(id){
    var el = document.getElementById(id);
    if (el) el.innerHTML = "";
  }

  // ================================================================
  // CHART RENDERERS
  // ================================================================
  function renderTrend(rows){
    clearContainer("ch-trend");
    if (!rows || !rows.length) { document.getElementById("ch-trend").innerHTML = '<div class="od-empty">No trend data.</div>'; return; }
    charts.trend = new frappe.Chart("#ch-trend", {
      type: "line", height: 260,
      colors: [PAL.blue, PAL.amber, PAL.purple, PAL.green],
      lineOptions: { hideDots: 0, dotSize: 3, spline: 1, regionFill: 0 },
      axisOptions: { xAxisMode: "tick", yAxisMode: "tick" },
      data: {
        labels: rows.map(function(r){ return r.date.slice(5); }),
        datasets: [
          { name: "OEE",          values: rows.map(function(r){return r.oee;}) },
          { name: "Availability", values: rows.map(function(r){return r.a;}) },
          { name: "Performance",  values: rows.map(function(r){return r.p;}) },
          { name: "Quality",      values: rows.map(function(r){return r.q;}) }
        ],
        yMarkers: [{ label: "50%", value: 50, options: { labelPos: "left" } }]
      },
      tooltipOptions: { formatTooltipY: function(v) { return fmt(v, 1) + "%"; } }
    });
    afterFrappe("ch-trend");
  }

  function renderLossCat(d){
    clearContainer("ch-loss-cat");
    var arr = [d.AR||0, d.PR||0, d.QR||0];
    if (arr.reduce(function(a,b){return a+b;},0) === 0) { document.getElementById("ch-loss-cat").innerHTML = '<div class="od-empty">No losses.</div>'; return; }
    charts.cat = new frappe.Chart("#ch-loss-cat", {
      type: "pie", height: 240,
      colors: [PAL.amber, PAL.purple, PAL.red],
      data: { labels: ["AR","PR","QR"], datasets: [{ values: arr }] },
      tooltipOptions: { formatTooltipY: function(v) { return fmt(v, 1) + " min"; } }
    });
    afterFrappe("ch-loss-cat");
  }

  function renderMachineRank(rows){
    clearContainer("ch-machine-rank");
    if (!rows || !rows.length) { document.getElementById("ch-machine-rank").innerHTML = '<div class="od-empty">No machines.</div>'; return; }
    charts.mrank = new frappe.Chart("#ch-machine-rank", {
      type: "bar", height: 300,
      colors: [PAL.blue],
      barOptions: { spaceRatio: 0.4 },
      axisOptions: { xAxisMode: "tick" },
      data: {
        labels: rows.map(function(r){ return r.machine; }),
        datasets: [{ name: "Avg OEE %", values: rows.map(function(r){ return r.avg_oee; }) }]
      },
      tooltipOptions: { formatTooltipY: function(v){ return fmt(v, 1) + "%"; } }
    });
    afterFrappe("ch-machine-rank");
  }

  function renderShift(rows){
    clearContainer("ch-shift");
    if (!rows || !rows.length) { document.getElementById("ch-shift").innerHTML = '<div class="od-empty">No shift data.</div>'; return; }
    charts.shift = new frappe.Chart("#ch-shift", {
      type: "bar", height: 300,
      colors: [PAL.lblue, PAL.blue, PAL.green, PAL.dark],
      barOptions: { spaceRatio: 0.5, stacked: 0 },
      axisOptions: { xAxisMode: "tick" },
      data: {
        labels: rows.map(function(r){ return r.shift; }),
        datasets: [
          { name: "Availability", values: rows.map(function(r){ return r.a; }) },
          { name: "Performance",  values: rows.map(function(r){ return r.p; }) },
          { name: "Quality",      values: rows.map(function(r){ return r.q; }) },
          { name: "OEE",          values: rows.map(function(r){ return r.oee; }) }
        ]
      },
      tooltipOptions: { formatTooltipY: function(v){ return fmt(v, 1) + "%"; } }
    });
    afterFrappe("ch-shift");
  }

  function renderPareto(rows){
    clearContainer("ch-pareto");
    if (!rows || !rows.length) { document.getElementById("ch-pareto").innerHTML = '<div class="od-empty">No losses.</div>'; return; }
    var total = rows.reduce(function(s,r){return s + (r.total_min||0);}, 0);
    var cum = 0;
    var cumPct = rows.map(function(r){ cum += (r.total_min||0); return total ? +(cum/total*100).toFixed(1) : 0; });
    charts.pareto = new frappe.Chart("#ch-pareto", {
      type: "axis-mixed", height: 300,
      colors: [PAL.amber, PAL.dark],
      barOptions: { spaceRatio: 0.4 },
      lineOptions: { hideDots: 0, dotSize: 3, spline: 0 },
      axisOptions: { xAxisMode: "tick" },
      data: {
        labels: rows.map(function(r){ return (r.code||"") + " " + (r.name||"").slice(0,18); }),
        datasets: [
          { name: "Loss min", chartType: "bar",  values: rows.map(function(r){ return r.total_min; }) },
          { name: "Cumulative %", chartType: "line", values: cumPct }
        ]
      },
      tooltipOptions: { formatTooltipY: function(v){ return fmt(v, 1); } }
    });
    afterFrappe("ch-pareto");
  }

  function renderOperators(rows){
    var html = '<table class="od-mini"><thead><tr><th>#</th><th>Operator</th><th class="num">Sessions</th><th class="num">Avg OEE</th></tr></thead><tbody>';
    rows.forEach(function(r, i){ html += "<tr><td>"+(i+1)+"</td><td>"+r.operator+'</td><td class="num">'+r.sessions+'</td><td class="num">'+fmt(r.avg_oee)+"%</td></tr>"; });
    if (!rows.length) html += '<tr><td colspan="4" style="color:#8d97a1; text-align:center;">No operator data.</td></tr>';
    html += "</tbody></table>";
    $("#op-tbl").innerHTML = html;
  }

  function renderZones(rows){
    var html = '<table class="od-mini"><thead><tr><th>Zone</th><th class="num">Sessions</th><th class="num">Avg OEE</th><th class="num">Losses</th></tr></thead><tbody>';
    rows.forEach(function(r){ html += "<tr><td>"+(r.zone||"-")+'</td><td class="num">'+r.sessions+'</td><td class="num">'+fmt(r.avg_oee)+'%</td><td class="num">'+fmt(r.loss_min,0)+" min</td></tr>"; });
    if (!rows.length) html += '<tr><td colspan="4" style="color:#8d97a1; text-align:center;">No zone data.</td></tr>';
    html += "</tbody></table>";
    $("#zn-tbl").innerHTML = html;
  }

  load();
})();
</script>
{% endblock %}
"""

tpl_path.write_text(NEW_TPL, encoding="utf-8")
print("[OK] Template rewritten - Anime.js drives all chart animations, CSS keyframes removed.")
print("     Hard refresh /oee-dashboard and click Apply/Refresh to verify replay on every render.")
