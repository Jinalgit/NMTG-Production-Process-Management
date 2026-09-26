from pathlib import Path
import sys

tpl_path = Path(r"D:\Het\demo2\templates\oee_dashboard.html")

NEW_TPL = r"""{% extends "base.html" %}
{% block title %}OEE Dashboard{% endblock %}
{% block content %}
<style>
  :root {
    --tp: #0f2544; --ts: #4a5b70; --tm: #7a8ba1;
    --bd: #e3ecf5; --rl: #f4f8fc; --rh: #fbfdff;
    --ac: #0b5fa5; --ac2: #4facfe;
    --avl-a: #f7b733; --avl-b: #fc4a1a;
    --prf-a: #4facfe; --prf-b: #00c6ff;
    --qty-a: #43e97b; --qty-b: #38b6a0;
    --oee-a: #667eea; --oee-b: #764ba2;
    --live: #22c55e;
  }
  .od { padding: 18px 22px; font-family: "IBM Plex Sans", system-ui, sans-serif; color: var(--tp); background: #f6f9fd; min-height: 100vh; }
  .od-head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 12px; }
  .od-title { font-size: 22px; font-weight: 700; margin: 0; letter-spacing: -0.01em; }
  .od-sub { font-size: 12px; color: var(--ts); margin-top: 4px; display: flex; align-items: center; gap: 6px; }
  .live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--live); box-shadow: 0 0 0 0 rgba(34,197,94,0.55); animation: pulse 2s infinite; }
  @keyframes pulse { 0%{box-shadow: 0 0 0 0 rgba(34,197,94,0.55);} 70%{box-shadow: 0 0 0 8px rgba(34,197,94,0);} 100%{box-shadow: 0 0 0 0 rgba(34,197,94,0);} }

  .od-btn { background: var(--ac); color: #fff; border: none; border-radius: 8px; padding: 9px 14px; font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 7px; transition: transform .12s, box-shadow .12s; box-shadow: 0 2px 6px rgba(11,95,165,0.18); }
  .od-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 10px rgba(11,95,165,0.25); }
  .od-btn.ghost { background: #fff; color: var(--tp); border: 1px solid var(--bd); box-shadow: 0 1px 2px rgba(15,37,68,0.04); }
  .od-btn .spin { animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .od-presets { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
  .od-preset { padding: 6px 14px; background: #fff; border: 1px solid var(--bd); border-radius: 999px; font-size: 12px; color: var(--ts); cursor: pointer; transition: all .15s; }
  .od-preset:hover { border-color: #b3cee4; color: var(--tp); }
  .od-preset.active { background: var(--tp); color: #fff; border-color: var(--tp); }

  .od-filters { background: #fff; border: 1px solid var(--bd); border-radius: 12px; padding: 14px 16px; display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; margin-bottom: 12px; box-shadow: 0 1px 3px rgba(15,37,68,0.03); }
  .od-fld { display: flex; flex-direction: column; gap: 4px; }
  .od-fld label { font-size: 10px; font-weight: 700; color: var(--ts); text-transform: uppercase; letter-spacing: 0.05em; }
  .od-fld input, .od-fld select { height: 34px; padding: 0 10px; border: 1px solid var(--bd); border-radius: 7px; font-family: inherit; font-size: 12.5px; color: var(--tp); background: #fff; min-width: 130px; transition: border-color .15s, box-shadow .15s; }
  .od-fld input:focus, .od-fld select:focus { border-color: var(--ac); box-shadow: 0 0 0 3px rgba(11,95,165,0.10); outline: none; }
  .od-filters .sp { flex: 1; }

  .od-chips { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; min-height: 0; }
  .od-chip { background: #fff; border: 1px solid #cfe0f2; color: var(--ac); font-size: 11px; font-weight: 600; padding: 5px 10px 5px 12px; border-radius: 999px; display: inline-flex; align-items: center; gap: 8px; cursor: default; box-shadow: 0 1px 2px rgba(11,95,165,0.06); }
  .od-chip .x { cursor: pointer; opacity: 0.6; font-weight: 700; transition: opacity .15s; }
  .od-chip .x:hover { opacity: 1; }

  .od-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--bd); margin-bottom: 16px; padding: 0 4px; }
  .od-tab { padding: 11px 18px 10px; background: transparent; border: none; border-bottom: 2px solid transparent; color: var(--ts); font-weight: 600; font-size: 13px; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: color .15s, border-color .15s; }
  .od-tab:hover { color: var(--tp); }
  .od-tab.active { color: var(--ac); border-bottom-color: var(--ac); }

  /* HERO RING SECTION */
  .od-hero { background: linear-gradient(135deg, #ffffff 0%, #f7fafd 100%); border: 1px solid var(--bd); border-radius: 16px; padding: 20px 24px; margin-bottom: 14px; display: grid; grid-template-columns: 320px 1fr; gap: 24px; align-items: center; box-shadow: 0 2px 12px rgba(15,37,68,0.05); }
  .od-hero-ring { position: relative; width: 260px; height: 260px; margin: 0 auto; }
  .od-hero-ring svg { transform: rotate(-90deg); }
  .od-hero-ring .ring-bg { fill: none; stroke-opacity: 0.14; stroke-linecap: round; }
  .od-hero-ring .ring-fg { fill: none; stroke-linecap: round; transition: stroke-dashoffset 1.4s cubic-bezier(0.22, 1, 0.36, 1); }
  .od-hero-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
  .od-hero-center .lbl { font-size: 10px; font-weight: 700; color: var(--tm); text-transform: uppercase; letter-spacing: 0.1em; }
  .od-hero-center .val { font-size: 46px; font-weight: 700; color: var(--tp); line-height: 1; margin: 2px 0 4px; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .od-hero-center .unit { font-size: 20px; color: var(--ts); font-weight: 500; }
  .od-hero-center .delta { margin-top: 8px; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; background: rgba(34,197,94,0.10); color: #16a34a; }
  .od-hero-center .delta.down { background: rgba(239,68,68,0.10); color: #dc2626; }

  .od-hero-side { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
  .od-hero-metric { padding: 14px; border-radius: 12px; background: #ffffff; border: 1px solid var(--bd); position: relative; overflow: hidden; }
  .od-hero-metric::before { content: ""; position: absolute; top: 0; left: 0; height: 3px; width: 100%; }
  .od-hero-metric.a::before { background: linear-gradient(90deg, var(--avl-a), var(--avl-b)); }
  .od-hero-metric.p::before { background: linear-gradient(90deg, var(--prf-a), var(--prf-b)); }
  .od-hero-metric.q::before { background: linear-gradient(90deg, var(--qty-a), var(--qty-b)); }
  .od-hero-metric .name { font-size: 10px; font-weight: 700; color: var(--ts); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
  .od-hero-metric .dot { width: 8px; height: 8px; border-radius: 50%; }
  .od-hero-metric.a .dot { background: var(--avl-b); }
  .od-hero-metric.p .dot { background: var(--prf-b); }
  .od-hero-metric.q .dot { background: var(--qty-a); }
  .od-hero-metric .big { font-size: 26px; font-weight: 700; color: var(--tp); line-height: 1; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }
  .od-hero-metric .big .u { font-size: 13px; color: var(--ts); font-weight: 500; margin-left: 2px; }
  .od-hero-metric .spark { margin-top: 8px; height: 24px; }

  /* KPI ROW - Vercel style */
  .od-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 14px; }
  .od-kpi { background: #fff; border: 1px solid var(--bd); border-radius: 12px; padding: 14px 16px; position: relative; overflow: hidden; transition: transform .18s, box-shadow .18s; cursor: default; }
  .od-kpi:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(15,37,68,0.08); }
  .od-kpi-top { display: flex; justify-content: space-between; align-items: flex-start; }
  .od-kpi-l { font-size: 10.5px; color: var(--ts); text-transform: uppercase; font-weight: 700; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px; }
  .od-kpi-l .fa { color: var(--ac); font-size: 12px; }
  .od-kpi-v { font-size: 28px; font-weight: 700; color: var(--tp); margin-top: 6px; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; line-height: 1.1; }
  .od-kpi-v .u { font-size: 13px; font-weight: 500; color: var(--ts); }
  .od-kpi-spark { position: absolute; right: 12px; bottom: 10px; width: 70px; height: 26px; opacity: 0.85; }

  /* CARDS */
  .od-grid { display: grid; gap: 14px; margin-bottom: 14px; }
  .od-g21 { grid-template-columns: 2fr 1fr; }
  .od-g11 { grid-template-columns: 1fr 1fr; }
  .od-gfull { grid-template-columns: 1fr; }
  .od-card { background: #fff; border: 1px solid var(--bd); border-radius: 12px; padding: 14px 16px; opacity: 0; transform: translateY(8px); transition: opacity .5s cubic-bezier(0.22, 1, 0.36, 1), transform .5s cubic-bezier(0.22, 1, 0.36, 1), box-shadow .18s; box-shadow: 0 1px 3px rgba(15,37,68,0.03); }
  .od-card.in { opacity: 1; transform: translateY(0); }
  .od-card:hover { box-shadow: 0 6px 20px rgba(15,37,68,0.08); }
  .od-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--bd); }
  .od-card-title { font-size: 12px; font-weight: 700; color: var(--tp); text-transform: uppercase; letter-spacing: 0.06em; display: inline-flex; align-items: center; gap: 8px; }
  .od-card-title .fa { color: var(--ac); font-size: 13px; }
  .od-card-sub { font-size: 10.5px; color: var(--ts); }
  .od-canvas-wrap { position: relative; height: 260px; }
  .od-canvas-wrap.tall { height: 320px; }
  .od-canvas-wrap.short { height: 200px; }

  /* Skeleton */
  .skel { background: linear-gradient(90deg, #eef3f9 25%, #f8fbfe 50%, #eef3f9 75%); background-size: 200% 100%; animation: shimmer 1.3s infinite; border-radius: 8px; }
  @keyframes shimmer { 0%{background-position:200% 0;} 100%{background-position:-200% 0;} }
  .skel-num { height: 30px; width: 60%; }
  .skel-bar { height: 240px; width: 100%; }
  .skel-ring { width: 220px; height: 220px; border-radius: 50%; }

  /* PANES */
  .od-pane { display: none; }
  .od-pane.active { display: block; }
  .od-empty { padding: 40px; text-align: center; color: var(--tm); font-size: 13px; }
  .od-empty .fa { font-size: 32px; display: block; margin-bottom: 10px; color: #b3cee4; }

  .od-mini { width: 100%; border-collapse: collapse; font-size: 11.5px; }
  .od-mini th { text-align: left; color: var(--ts); font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; font-size: 10px; padding: 7px 6px; border-bottom: 1px solid var(--bd); }
  .od-mini td { padding: 8px 6px; border-bottom: 1px solid var(--rl); }
  .od-mini td.num { text-align: right; font-family: "IBM Plex Mono", monospace; font-weight: 600; color: var(--tp); font-variant-numeric: tabular-nums; }
  .od-mini tbody tr { transition: background .12s; }
  .od-mini tbody tr:hover { background: #f8fbfe; }

  .od-status { padding: 10px 14px; background: #fff4e6; border: 1px solid #ffd8a8; border-radius: 8px; font-size: 12px; color: #b7791f; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  .od-status.err { background: #fdecec; border-color: #f2c1c1; color: #a12c39; }

  @media (max-width: 1200px) {
    .od-hero { grid-template-columns: 1fr; }
    .od-hero-ring { width: 220px; height: 220px; }
    .od-kpis { grid-template-columns: repeat(2, 1fr); }
    .od-g21, .od-g11 { grid-template-columns: 1fr; }
  }
</style>

<div class="od">
  <div class="od-head">
    <div>
      <h1 class="od-title">OEE Dashboard</h1>
      <div class="od-sub"><span class="live-dot"></span><span id="od-sub-text">Loading...</span></div>
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

  <!-- PRODUCTION -->
  <div class="od-pane active" data-pane="prod">

    <!-- HERO RING -->
    <div class="od-hero">
      <div class="od-hero-ring">
        <svg width="260" height="260" viewBox="0 0 260 260">
          <defs>
            <linearGradient id="gradA" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="var(--avl-a)"/>
              <stop offset="100%" stop-color="var(--avl-b)"/>
            </linearGradient>
            <linearGradient id="gradP" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="var(--prf-a)"/>
              <stop offset="100%" stop-color="var(--prf-b)"/>
            </linearGradient>
            <linearGradient id="gradQ" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="var(--qty-a)"/>
              <stop offset="100%" stop-color="var(--qty-b)"/>
            </linearGradient>
          </defs>
          <!-- backgrounds -->
          <circle cx="130" cy="130" r="112" class="ring-bg" stroke="var(--avl-b)" stroke-width="18"/>
          <circle cx="130" cy="130" r="88"  class="ring-bg" stroke="var(--prf-b)" stroke-width="18"/>
          <circle cx="130" cy="130" r="64"  class="ring-bg" stroke="var(--qty-a)" stroke-width="18"/>
          <!-- foregrounds -->
          <circle id="ring-a" cx="130" cy="130" r="112" class="ring-fg" stroke="url(#gradA)" stroke-width="18" stroke-dasharray="703.7" stroke-dashoffset="703.7"/>
          <circle id="ring-p" cx="130" cy="130" r="88"  class="ring-fg" stroke="url(#gradP)" stroke-width="18" stroke-dasharray="552.9" stroke-dashoffset="552.9"/>
          <circle id="ring-q" cx="130" cy="130" r="64"  class="ring-fg" stroke="url(#gradQ)" stroke-width="18" stroke-dasharray="402.1" stroke-dashoffset="402.1"/>
        </svg>
        <div class="od-hero-center">
          <div class="lbl">Overall OEE</div>
          <div class="val"><span id="hero-oee">0</span><span class="unit">%</span></div>
          <div class="delta" id="hero-delta">Live</div>
        </div>
      </div>
      <div class="od-hero-side">
        <div class="od-hero-metric a">
          <div class="name"><span class="dot"></span>Availability</div>
          <div class="big"><span id="m-a">0</span><span class="u">%</span></div>
          <svg class="spark" id="spark-a" viewBox="0 0 100 24" preserveAspectRatio="none"></svg>
        </div>
        <div class="od-hero-metric p">
          <div class="name"><span class="dot"></span>Performance</div>
          <div class="big"><span id="m-p">0</span><span class="u">%</span></div>
          <svg class="spark" id="spark-p" viewBox="0 0 100 24" preserveAspectRatio="none"></svg>
        </div>
        <div class="od-hero-metric q">
          <div class="name"><span class="dot"></span>Quality</div>
          <div class="big"><span id="m-q">0</span><span class="u">%</span></div>
          <svg class="spark" id="spark-q" viewBox="0 0 100 24" preserveAspectRatio="none"></svg>
        </div>
      </div>
    </div>

    <!-- KPIs -->
    <div class="od-kpis">
      <div class="od-kpi">
        <div class="od-kpi-top"><div class="od-kpi-l"><i class="fa fa-list-alt"></i> Sessions</div></div>
        <div class="od-kpi-v"><span id="k-sessions">0</span></div>
        <svg class="od-kpi-spark" id="spark-sessions" viewBox="0 0 100 26" preserveAspectRatio="none"></svg>
      </div>
      <div class="od-kpi">
        <div class="od-kpi-top"><div class="od-kpi-l"><i class="fa fa-check-circle"></i> OK Produced</div></div>
        <div class="od-kpi-v"><span id="k-ok">0</span></div>
        <svg class="od-kpi-spark" id="spark-ok" viewBox="0 0 100 26" preserveAspectRatio="none"></svg>
      </div>
      <div class="od-kpi">
        <div class="od-kpi-top"><div class="od-kpi-l"><i class="fa fa-times-circle"></i> Rejected</div></div>
        <div class="od-kpi-v"><span id="k-rej">0</span></div>
        <svg class="od-kpi-spark" id="spark-rej" viewBox="0 0 100 26" preserveAspectRatio="none"></svg>
      </div>
    </div>

    <div class="od-grid od-g21">
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-line-chart"></i> OEE Trend</div><div class="od-card-sub">daily average</div></div><div class="od-canvas-wrap"><canvas id="ch-trend"></canvas></div></div>
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-pie-chart"></i> Loss Category</div><div class="od-card-sub">total lost min</div></div><div class="od-canvas-wrap short"><canvas id="ch-loss-cat"></canvas></div></div>
    </div>

    <div class="od-grid od-g11">
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-bar-chart"></i> Machine OEE Ranking</div><div class="od-card-sub">top 10</div></div><div class="od-canvas-wrap tall"><canvas id="ch-machine-rank"></canvas></div></div>
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-columns"></i> Shift Comparison</div><div class="od-card-sub">avg OEE by shift</div></div><div class="od-canvas-wrap tall"><canvas id="ch-shift"></canvas></div></div>
    </div>

    <div class="od-grid od-gfull">
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-signal"></i> Loss Pareto - Top 10 Reasons</div><div class="od-card-sub">bars: minutes - line: cumulative %</div></div><div class="od-canvas-wrap tall"><canvas id="ch-pareto"></canvas></div></div>
    </div>

    <div class="od-grid od-g11">
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-user"></i> Operator Ranking</div><div class="od-card-sub">top by avg OEE</div></div><div id="op-tbl"></div></div>
      <div class="od-card"><div class="od-card-head"><div class="od-card-title"><i class="fa fa-th"></i> Zone Comparison</div><div class="od-card-sub">avg OEE by zone</div></div><div id="zn-tbl"></div></div>
    </div>
  </div>

  <div class="od-pane" data-pane="ml"><div class="od-card in"><div class="od-empty"><i class="fa fa-clock-o"></i>Machine Losses (No JC) charts are coming in the next step.</div></div></div>
  <div class="od-pane" data-pane="tr"><div class="od-card in"><div class="od-empty"><i class="fa fa-clock-o"></i>Tool Room + Development charts are coming in the next step.</div></div></div>
  <div class="od-pane" data-pane="tool"><div class="od-card in"><div class="od-empty"><i class="fa fa-clock-o"></i>Tooling Activity charts are coming in the next step.</div></div></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>
  if (typeof Chart === "undefined") {
    var s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js";
    document.head.appendChild(s);
  }
</script>
<script>
(function () {
  var C = {
    tp: "#0f2544", ts: "#4a5b70", ac: "#0b5fa5",
    aA: "#f7b733", aB: "#fc4a1a",
    pA: "#4facfe", pB: "#00c6ff",
    qA: "#43e97b", qB: "#38b6a0",
    oeeA: "#667eea", oeeB: "#764ba2",
    warn: "#c17817", pr: "#7f5aa8", bad: "#b84a3a"
  };
  var charts = {};
  var lastData = null;
  function $(s){return document.querySelector(s);}
  function fmt(n, d){ if (n===null||n===undefined||isNaN(n)) return "-"; return Number(n).toFixed(d===undefined?1:d); }

  // ---- default dates ----
  function toIso(dt){ return dt.getFullYear()+"-"+String(dt.getMonth()+1).padStart(2,"0")+"-"+String(dt.getDate()).padStart(2,"0"); }
  var today = new Date();
  $("#od-from").value = toIso(new Date(today.getFullYear(), today.getMonth(), 1));
  $("#od-to").value = toIso(today);

  // ---- count-up ----
  function countUp(el, target, dur, decimals) {
    if (!el) return;
    dur = dur || 1100; decimals = decimals === undefined ? 1 : decimals;
    var start = performance.now();
    function step(now) {
      var t = Math.min(1, (now - start) / dur);
      var eased = 1 - Math.pow(1 - t, 3);
      var v = target * eased;
      el.textContent = decimals > 0 ? v.toFixed(decimals) : Math.round(v).toLocaleString();
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // ---- sparkline (SVG polyline area) ----
  function drawSpark(id, data, colorA, colorB) {
    var el = document.getElementById(id);
    if (!el || !data || !data.length) { if (el) el.innerHTML = ""; return; }
    var w = 100, h = 26, n = data.length;
    var min = Math.min.apply(null, data), max = Math.max.apply(null, data);
    var range = max - min || 1;
    var pts = data.map(function(v, i){
      var x = (i/(n-1||1)) * w;
      var y = h - ((v - min)/range) * (h - 4) - 2;
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    var gid = id + "-g";
    var pathD = "M " + pts.join(" L ");
    var areaD = pathD + " L " + w + "," + h + " L 0," + h + " Z";
    el.innerHTML =
      '<defs><linearGradient id="'+gid+'" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="'+colorA+'" stop-opacity="0.45"/>' +
      '<stop offset="100%" stop-color="'+colorA+'" stop-opacity="0"/></linearGradient></defs>' +
      '<path d="'+areaD+'" fill="url(#'+gid+')" stroke="none"/>' +
      '<path d="'+pathD+'" fill="none" stroke="'+colorB+'" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>';
  }

  // ---- ring animation ----
  function setRing(id, pct, circumference) {
    var el = document.getElementById(id);
    if (!el) return;
    var offset = circumference * (1 - Math.max(0, Math.min(100, pct)) / 100);
    // force reflow to trigger transition
    el.style.strokeDashoffset = circumference;
    void el.getBoundingClientRect();
    el.style.strokeDashoffset = offset;
  }

  // ---- gradient helper for chart.js line ----
  function gradientFill(canvasId, colorA, colorB) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return colorA;
    var ctx = canvas.getContext("2d");
    var g = ctx.createLinearGradient(0, 0, 0, canvas.height || 260);
    g.addColorStop(0, colorA);
    g.addColorStop(1, colorB);
    return g;
  }

  // ---- presets ----
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

  // ---- tabs ----
  document.querySelectorAll(".od-tab").forEach(function(t){
    t.addEventListener("click", function(){
      document.querySelectorAll(".od-tab").forEach(function(x){x.classList.remove("active");});
      t.classList.add("active");
      document.querySelectorAll(".od-pane").forEach(function(p){p.classList.remove("active");});
      document.querySelector('.od-pane[data-pane="'+t.dataset.p+'"]').classList.add("active");
    });
  });

  // ---- buttons ----
  $("#od-apply").addEventListener("click", load);
  $("#od-refresh").addEventListener("click", load);
  $("#od-reset").addEventListener("click", function(){
    document.querySelectorAll(".od-preset").forEach(function(x){x.classList.remove("active");});
    document.querySelector('.od-preset[data-preset="this_month"]').classList.add("active");
    applyPreset("this_month");
    $("#od-zone").value=""; $("#od-machine").value=""; $("#od-operator").value="";
    load();
  });

  // ---- filter chips ----
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

  function staggerIn() {
    var cards = document.querySelectorAll('.od-pane[data-pane="prod"] .od-card');
    cards.forEach(function(c){ c.classList.remove("in"); });
    setTimeout(function(){
      cards.forEach(function(c, i){ setTimeout(function(){ c.classList.add("in"); }, i * 90); });
    }, 30);
  }

  function load(){
    if (typeof Chart === "undefined") { setTimeout(load, 200); return; }
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
        lastData = d;
        renderAll(d);
        status("");
      })
      .catch(function(e){ status("Failed to load: "+e.message, true); })
      .finally(function(){ if (btn) btn.classList.remove("spin"); });
  }

  function renderAll(d){
    $("#od-sub-text").textContent = "Showing " + d.period.from_date + " to " + d.period.to_date + " - updated " + new Date().toLocaleTimeString();
    fillDropdown("od-zone", d.filter_options.zones);
    fillDropdown("od-machine", d.filter_options.machines);
    fillDropdown("od-operator", d.filter_options.operators);
    renderChips();

    var k = d.kpis;
    countUp($("#hero-oee"), k.avg_oee, 1300, 1);
    countUp($("#m-a"), k.avg_a, 1300, 1);
    countUp($("#m-p"), k.avg_p, 1300, 1);
    countUp($("#m-q"), k.avg_q, 1300, 1);
    countUp($("#k-sessions"), k.sessions, 1000, 0);
    countUp($("#k-ok"), k.total_ok, 1000, 0);
    countUp($("#k-rej"), k.total_reject, 1000, 0);

    // Rings: circumferences from r values (112, 88, 64) => 2*pi*r
    setTimeout(function(){
      setRing("ring-a", k.avg_a, 2 * Math.PI * 112);
      setRing("ring-p", k.avg_p, 2 * Math.PI * 88);
      setRing("ring-q", k.avg_q, 2 * Math.PI * 64);
    }, 60);

    // Sparklines from trend
    var trend = d.oee_trend || [];
    drawSpark("spark-a", trend.map(function(r){return r.a;}), C.aA, C.aB);
    drawSpark("spark-p", trend.map(function(r){return r.p;}), C.pA, C.pB);
    drawSpark("spark-q", trend.map(function(r){return r.q;}), C.qA, C.qB);
    drawSpark("spark-sessions", trend.map(function(_, i){return i+1;}), C.ac, C.ac);
    drawSpark("spark-ok", trend.map(function(r){return r.q;}), C.qA, C.qB);
    drawSpark("spark-rej", trend.map(function(r){return 100 - r.q;}), C.warn, C.bad);

    renderTrend(trend);
    renderLossCat(d.loss_category);
    renderMachineRank(d.machine_ranking);
    renderShift(d.shift_comparison);
    renderPareto(d.loss_pareto);
    renderOperators(d.operator_ranking);
    renderZones(d.zone_comparison);

    staggerIn();
  }

  function fillDropdown(id, arr) {
    var sel = document.getElementById(id);
    if (!sel || !arr) return;
    var prev = sel.value;
    sel.innerHTML = '<option value="">All</option>';
    arr.forEach(function(v){ var o=document.createElement("option"); o.value=v; o.textContent=v; sel.appendChild(o); });
    sel.value = prev;
  }

  function destroy(name){ if (charts[name]){ charts[name].destroy(); delete charts[name]; } }

  // Chart.js defaults
  Chart.defaults.font.family = "'IBM Plex Sans', system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.color = C.ts;
  Chart.defaults.animation.duration = 900;
  Chart.defaults.animation.easing = "easeOutQuart";
  Chart.defaults.plugins.tooltip.backgroundColor = "rgba(15,37,68,0.95)";
  Chart.defaults.plugins.tooltip.titleColor = "#fff";
  Chart.defaults.plugins.tooltip.bodyColor = "#e3ecf5";
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.boxPadding = 6;
  Chart.defaults.plugins.tooltip.titleFont = { weight: "600", size: 11 };
  Chart.defaults.plugins.tooltip.bodyFont = { size: 11.5 };
  Chart.defaults.plugins.tooltip.displayColors = true;

  function renderTrend(rows){
    destroy("trend");
    var ctx = document.getElementById("ch-trend").getContext("2d");
    var oeeGrad = ctx.createLinearGradient(0, 0, 0, 260);
    oeeGrad.addColorStop(0, "rgba(102,126,234,0.35)");
    oeeGrad.addColorStop(1, "rgba(102,126,234,0)");
    charts.trend = new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map(function(r){ return r.date.slice(5); }),
        datasets: [
          {label:"OEE", data: rows.map(function(r){return r.oee;}), borderColor: C.oeeA, backgroundColor: oeeGrad, borderWidth: 2.6, tension: 0.35, pointRadius: 0, pointHoverRadius: 5, fill: true},
          {label:"Availability", data: rows.map(function(r){return r.a;}), borderColor: C.aB, borderWidth: 1.6, tension: 0.35, pointRadius: 0, pointHoverRadius: 4, fill: false, borderDash: []},
          {label:"Performance", data: rows.map(function(r){return r.p;}), borderColor: C.pB, borderWidth: 1.6, tension: 0.35, pointRadius: 0, pointHoverRadius: 4, fill: false},
          {label:"Quality", data: rows.map(function(r){return r.q;}), borderColor: C.qA, borderWidth: 1.6, tension: 0.35, pointRadius: 0, pointHoverRadius: 4, fill: false}
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: {mode: "index", intersect: false},
        plugins: {
          legend: {position: "bottom", labels: {boxWidth: 8, boxHeight: 8, padding: 12, usePointStyle: true, pointStyle: "circle"}},
          tooltip: { callbacks: { label: function(c){ return c.dataset.label + ": " + fmt(c.parsed.y, 1) + "%"; } } }
        },
        scales: { y: {beginAtZero: true, max: 100, grid: {color: "rgba(15,37,68,0.05)"}, ticks: {callback: function(v){return v+"%";}}}, x: {grid: {display: false}} }
      }
    });
  }

  function renderLossCat(d){
    destroy("cat");
    var ctx = document.getElementById("ch-loss-cat").getContext("2d");
    var arG = ctx.createLinearGradient(0, 0, 0, 200); arG.addColorStop(0, C.aA); arG.addColorStop(1, C.aB);
    var prG = ctx.createLinearGradient(0, 0, 0, 200); prG.addColorStop(0, "#a586c6"); prG.addColorStop(1, C.pr);
    var qrG = ctx.createLinearGradient(0, 0, 0, 200); qrG.addColorStop(0, "#d67e70"); qrG.addColorStop(1, C.bad);
    charts.cat = new Chart(ctx, {
      type: "doughnut",
      data: { labels: ["AR","PR","QR"], datasets: [{ data: [d.AR||0, d.PR||0, d.QR||0], backgroundColor: [arG, prG, qrG], borderWidth: 3, borderColor: "#fff", hoverOffset: 8 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "65%", plugins: { legend: {position: "bottom", labels: {boxWidth: 8, boxHeight: 8, padding: 12, usePointStyle: true, pointStyle: "circle"}}, tooltip: { callbacks: { label: function(c){ return c.label + ": " + fmt(c.parsed, 1) + " min"; } } } } }
    });
  }

  function renderMachineRank(rows){
    destroy("mrank");
    var ctx = document.getElementById("ch-machine-rank").getContext("2d");
    var g = ctx.createLinearGradient(0, 0, 500, 0); g.addColorStop(0, C.pA); g.addColorStop(1, C.oeeA);
    charts.mrank = new Chart(ctx, {
      type: "bar",
      data: { labels: rows.map(function(r){return r.machine;}), datasets: [{ label: "Avg OEE", data: rows.map(function(r){return r.avg_oee;}), backgroundColor: g, borderRadius: 6, barPercentage: 0.7 }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: {legend: {display: false}, tooltip: { callbacks: { label: function(c){ return "OEE: " + fmt(c.parsed.x, 1) + "%"; } } } }, scales: {x: {beginAtZero: true, max: 100, grid: {color: "rgba(15,37,68,0.05)"}, ticks: {callback: function(v){return v+"%";}}}, y: {grid: {display: false}}} }
    });
  }

  function renderShift(rows){
    destroy("shift");
    var ctx = document.getElementById("ch-shift").getContext("2d");
    charts.shift = new Chart(ctx, {
      type: "bar",
      data: {
        labels: rows.map(function(r){return r.shift;}),
        datasets: [
          {label:"Availability", data: rows.map(function(r){return r.a;}), backgroundColor: C.aB, borderRadius: 5},
          {label:"Performance", data: rows.map(function(r){return r.p;}), backgroundColor: C.pB, borderRadius: 5},
          {label:"Quality", data: rows.map(function(r){return r.q;}), backgroundColor: C.qA, borderRadius: 5},
          {label:"OEE", data: rows.map(function(r){return r.oee;}), backgroundColor: C.oeeA, borderRadius: 5}
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: {legend: {position: "bottom", labels: {boxWidth: 8, boxHeight: 8, padding: 12, usePointStyle: true, pointStyle: "circle"}}, tooltip: { callbacks: { label: function(c){ return c.dataset.label + ": " + fmt(c.parsed.y, 1) + "%"; } } } }, scales: {y: {beginAtZero: true, max: 100, grid: {color: "rgba(15,37,68,0.05)"}, ticks: {callback: function(v){return v+"%";}}}, x: {grid: {display: false}}} }
    });
  }

  function renderPareto(rows){
    destroy("pareto");
    var ctx = document.getElementById("ch-pareto").getContext("2d");
    var total = rows.reduce(function(s,r){return s + (r.total_min||0);}, 0);
    var cum = 0;
    var cumPct = rows.map(function(r){ cum += (r.total_min||0); return total ? (cum/total*100) : 0; });
    var barColors = rows.map(function(r){
      var g = ctx.createLinearGradient(0, 0, 0, 320);
      if (r.category==="AR") { g.addColorStop(0, C.aA); g.addColorStop(1, C.aB); }
      else if (r.category==="PR") { g.addColorStop(0, "#a586c6"); g.addColorStop(1, C.pr); }
      else { g.addColorStop(0, "#d67e70"); g.addColorStop(1, C.bad); }
      return g;
    });
    charts.pareto = new Chart(ctx, {
      data: {
        labels: rows.map(function(r){ return (r.code||"") + " " + (r.name||"").slice(0,20); }),
        datasets: [
          { type: "bar", label: "Loss min", data: rows.map(function(r){return r.total_min;}), backgroundColor: barColors, yAxisID: "y", borderRadius: 5, barPercentage: 0.7 },
          { type: "line", label: "Cumulative %", data: cumPct, borderColor: C.tp, backgroundColor: C.tp, borderWidth: 2.4, pointRadius: 4, pointHoverRadius: 6, yAxisID: "y1", tension: 0.2 }
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: {legend: {position: "bottom", labels: {boxWidth: 8, boxHeight: 8, padding: 12, usePointStyle: true, pointStyle: "circle"}}}, scales: { y: {beginAtZero: true, grid: {color: "rgba(15,37,68,0.05)"}, title: {display: true, text: "Minutes"}}, y1: {beginAtZero: true, max: 100, position: "right", grid: {display: false}, ticks: {callback: function(v){return v+"%";}}} } }
    });
  }

  function renderOperators(rows){
    var html = '<table class="od-mini"><thead><tr><th>#</th><th>Operator</th><th class="num">Sessions</th><th class="num">Avg OEE</th></tr></thead><tbody>';
    rows.forEach(function(r, i){ html += "<tr><td>"+(i+1)+"</td><td>"+r.operator+'</td><td class="num">'+r.sessions+'</td><td class="num">'+fmt(r.avg_oee)+"%</td></tr>"; });
    if (!rows.length) html += '<tr><td colspan="4" style="color:#7a8ba1; text-align:center;">No operator data.</td></tr>';
    html += "</tbody></table>";
    $("#op-tbl").innerHTML = html;
  }

  function renderZones(rows){
    var html = '<table class="od-mini"><thead><tr><th>Zone</th><th class="num">Sessions</th><th class="num">Avg OEE</th><th class="num">Losses</th></tr></thead><tbody>';
    rows.forEach(function(r){ html += "<tr><td>"+(r.zone||"-")+'</td><td class="num">'+r.sessions+'</td><td class="num">'+fmt(r.avg_oee)+'%</td><td class="num">'+fmt(r.loss_min,0)+" min</td></tr>"; });
    if (!rows.length) html += '<tr><td colspan="4" style="color:#7a8ba1; text-align:center;">No zone data.</td></tr>';
    html += "</tbody></table>";
    $("#zn-tbl").innerHTML = html;
  }

  // ---- go ----
  load();
})();
</script>
{% endblock %}
"""

tpl_path.write_text(NEW_TPL, encoding="utf-8")
print("[OK] template polished - Apple Fitness ring hero + Vercel KPI cards + gradient charts + animated entrance + count-up + skeletons + filter chips + live pulse")
