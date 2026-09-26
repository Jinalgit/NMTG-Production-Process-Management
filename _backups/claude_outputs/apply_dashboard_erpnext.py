from pathlib import Path

tpl_path = Path(r"D:\Het\demo2\templates\oee_dashboard.html")

NEW_TPL = r"""{% extends "base.html" %}
{% block title %}OEE Dashboard{% endblock %}
{% block content %}
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
    --good: #29cd42;
    --warn: #ffc107;
    --bad:  #e74c3c;
    --neu:  #6c7680;
    --card: #ffffff;
  }
  .od { padding: 18px 22px; font-family: "IBM Plex Sans", "Inter", system-ui, sans-serif; color: var(--tp); background: #f5f7fa; min-height: 100vh; }

  .od-head { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 12px; }
  .od-title { font-size: 20px; font-weight: 600; margin: 0; letter-spacing: -0.005em; }
  .od-sub { font-size: 12px; color: var(--ts); margin-top: 3px; }

  .od-btn { background: var(--ac); color: #fff; border: none; border-radius: 6px; padding: 8px 13px; font-size: 12px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 7px; transition: background .15s; }
  .od-btn:hover { background: #1a7fd8; }
  .od-btn.ghost { background: #fff; color: var(--tp); border: 1px solid var(--bd); }
  .od-btn.ghost:hover { background: var(--rl); }
  .od-btn .spin { animation: spin .9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .od-presets { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }
  .od-preset { padding: 6px 13px; background: #fff; border: 1px solid var(--bd); border-radius: 4px; font-size: 12px; color: var(--ts); cursor: pointer; transition: all .12s; }
  .od-preset:hover { color: var(--tp); border-color: #c8d0d8; }
  .od-preset.active { background: var(--tp); color: #fff; border-color: var(--tp); }

  .od-filters { background: #fff; border: 1px solid var(--bd); border-radius: 6px; padding: 12px 14px; display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; margin-bottom: 10px; }
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

  /* KPI STRIP */
  .od-kpis { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 12px; }
  .od-kpi { background: var(--card); border: 1px solid var(--bd); border-radius: 6px; padding: 12px 14px; transition: border-color .15s; }
  .od-kpi:hover { border-color: #c8d0d8; }
  .od-kpi-l { font-size: 10px; color: var(--ts); text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
  .od-kpi-l .fa { color: var(--tm); font-size: 11px; }
  .od-kpi-v { font-size: 22px; font-weight: 600; color: var(--tp); letter-spacing: -0.01em; font-variant-numeric: tabular-nums; line-height: 1.1; }
  .od-kpi-v .u { font-size: 12px; font-weight: 500; color: var(--ts); margin-left: 2px; }
  .od-kpi-d { font-size: 10.5px; color: var(--ts); margin-top: 4px; }

  /* CARDS */
  .od-grid { display: grid; gap: 12px; margin-bottom: 12px; }
  .od-g21 { grid-template-columns: 2fr 1fr; }
  .od-g11 { grid-template-columns: 1fr 1fr; }
  .od-gfull { grid-template-columns: 1fr; }
  .od-card { background: var(--card); border: 1px solid var(--bd); border-radius: 6px; padding: 14px 16px; opacity: 0; transform: translateY(4px); transition: opacity .35s ease-out, transform .35s ease-out, border-color .15s; }
  .od-card.in { opacity: 1; transform: translateY(0); }
  .od-card:hover { border-color: #c8d0d8; }
  .od-card-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--bd); }
  .od-card-title { font-size: 12px; font-weight: 600; color: var(--tp); letter-spacing: 0.02em; display: inline-flex; align-items: center; gap: 8px; }
  .od-card-title .fa { color: var(--ac); font-size: 12px; }
  .od-card-sub { font-size: 10.5px; color: var(--ts); }
  .od-canvas-wrap { position: relative; height: 260px; }
  .od-canvas-wrap.tall { height: 300px; }
  .od-canvas-wrap.short { height: 200px; }

  /* PANES */
  .od-pane { display: none; }
  .od-pane.active { display: block; }
  .od-empty { padding: 40px; text-align: center; color: var(--tm); font-size: 13px; }
  .od-empty .fa { font-size: 26px; display: block; margin-bottom: 10px; color: #c8d0d8; }

  .od-mini { width: 100%; border-collapse: collapse; font-size: 12px; }
  .od-mini th { text-align: left; color: var(--ts); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; font-size: 10px; padding: 7px 6px; border-bottom: 1px solid var(--bd); }
  .od-mini td { padding: 8px 6px; border-bottom: 1px solid var(--rl); }
  .od-mini td.num { text-align: right; font-family: "IBM Plex Mono", monospace; font-weight: 500; color: var(--tp); font-variant-numeric: tabular-nums; }
  .od-mini tbody tr:hover { background: var(--rl); }

  .od-status { padding: 10px 12px; background: #fff4e6; border: 1px solid #ffd8a8; border-radius: 4px; font-size: 12px; color: #b7791f; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  .od-status.err { background: #fdecec; border-color: #f2c1c1; color: #a12c39; }

  @media (max-width: 1200px) {
    .od-kpis { grid-template-columns: repeat(3, 1fr); }
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

    <div class="od-kpis">
      <div class="od-kpi"><div class="od-kpi-l"><i class="fa fa-list-alt"></i> Sessions</div><div class="od-kpi-v"><span id="k-sessions">0</span></div></div>
      <div class="od-kpi"><div class="od-kpi-l"><i class="fa fa-tachometer"></i> Avg OEE</div><div class="od-kpi-v"><span id="k-oee">0</span><span class="u">%</span></div></div>
      <div class="od-kpi"><div class="od-kpi-l"><i class="fa fa-play"></i> Availability</div><div class="od-kpi-v"><span id="k-a">0</span><span class="u">%</span></div></div>
      <div class="od-kpi"><div class="od-kpi-l"><i class="fa fa-bolt"></i> Performance</div><div class="od-kpi-v"><span id="k-p">0</span><span class="u">%</span></div></div>
      <div class="od-kpi"><div class="od-kpi-l"><i class="fa fa-check-circle"></i> Quality</div><div class="od-kpi-v"><span id="k-q">0</span><span class="u">%</span></div></div>
      <div class="od-kpi"><div class="od-kpi-l"><i class="fa fa-cube"></i> OK / Reject</div><div class="od-kpi-v"><span id="k-okrej">0 / 0</span></div></div>
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
  // ERPNext-inspired restrained palette
  var C = {
    tp: "#1f272e",
    ts: "#525f6b",
    tm: "#8d97a1",
    bd: "#e2e6ea",
    ac: "#2490ef",
    acSoft: "rgba(36,144,239,0.10)",
    warn: "#ffc107",
    warnSoft: "rgba(255,193,7,0.12)",
    neu: "#6c7680",
    good: "#29cd42",
    bad: "#e74c3c"
  };
  var charts = {};
  function $(s){return document.querySelector(s);}
  function fmt(n, d){ if (n===null||n===undefined||isNaN(n)) return "-"; return Number(n).toFixed(d===undefined?1:d); }

  function toIso(dt){ return dt.getFullYear()+"-"+String(dt.getMonth()+1).padStart(2,"0")+"-"+String(dt.getDate()).padStart(2,"0"); }
  var today = new Date();
  $("#od-from").value = toIso(new Date(today.getFullYear(), today.getMonth(), 1));
  $("#od-to").value = toIso(today);

  function countUp(el, target, dur, decimals) {
    if (!el) return;
    dur = dur || 550; decimals = decimals === undefined ? 1 : decimals;
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

  function staggerIn() {
    var cards = document.querySelectorAll('.od-pane[data-pane="prod"] .od-card');
    cards.forEach(function(c){ c.classList.remove("in"); });
    setTimeout(function(){
      cards.forEach(function(c, i){ setTimeout(function(){ c.classList.add("in"); }, i * 55); });
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
    countUp($("#k-sessions"), k.sessions, 500, 0);
    countUp($("#k-oee"), k.avg_oee, 600, 1);
    countUp($("#k-a"), k.avg_a, 600, 1);
    countUp($("#k-p"), k.avg_p, 600, 1);
    countUp($("#k-q"), k.avg_q, 600, 1);
    $("#k-okrej").textContent = k.total_ok.toLocaleString() + " / " + k.total_reject.toLocaleString();

    renderTrend(d.oee_trend);
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

  // Chart.js global defaults - ERPNext-style
  Chart.defaults.font.family = "'IBM Plex Sans', system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.color = C.ts;
  Chart.defaults.animation.duration = 500;
  Chart.defaults.animation.easing = "easeOutCubic";
  Chart.defaults.plugins.tooltip.backgroundColor = "rgba(31,39,46,0.95)";
  Chart.defaults.plugins.tooltip.titleColor = "#fff";
  Chart.defaults.plugins.tooltip.bodyColor = "#e2e6ea";
  Chart.defaults.plugins.tooltip.padding = 9;
  Chart.defaults.plugins.tooltip.cornerRadius = 4;
  Chart.defaults.plugins.tooltip.titleFont = { weight: "600", size: 11 };
  Chart.defaults.plugins.tooltip.bodyFont = { size: 11.5 };
  Chart.defaults.plugins.tooltip.displayColors = true;
  Chart.defaults.plugins.tooltip.boxWidth = 8;

  function renderTrend(rows){
    destroy("trend");
    var ctx = document.getElementById("ch-trend").getContext("2d");
    // Only OEE line, filled subtly - one dominant color
    charts.trend = new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map(function(r){ return r.date.slice(5); }),
        datasets: [
          {label:"OEE", data: rows.map(function(r){return r.oee;}), borderColor: C.ac, backgroundColor: C.acSoft, borderWidth: 2, tension: 0.3, pointRadius: 0, pointHoverRadius: 4, fill: true},
          {label:"Availability", data: rows.map(function(r){return r.a;}), borderColor: C.neu, borderWidth: 1.2, tension: 0.3, pointRadius: 0, pointHoverRadius: 3, fill: false, borderDash: [4, 3]},
          {label:"Performance", data: rows.map(function(r){return r.p;}), borderColor: C.neu, borderWidth: 1.2, tension: 0.3, pointRadius: 0, pointHoverRadius: 3, fill: false, borderDash: [2, 2]},
          {label:"Quality", data: rows.map(function(r){return r.q;}), borderColor: C.neu, borderWidth: 1.2, tension: 0.3, pointRadius: 0, pointHoverRadius: 3, fill: false, borderDash: [6, 4]}
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: {mode: "index", intersect: false},
        plugins: {
          legend: {position: "bottom", labels: {boxWidth: 10, padding: 12, usePointStyle: true, pointStyle: "line"}},
          tooltip: { callbacks: { label: function(c){ return c.dataset.label + ": " + fmt(c.parsed.y, 1) + "%"; } } }
        },
        scales: { y: {beginAtZero: true, max: 100, grid: {color: "rgba(31,39,46,0.05)"}, ticks: {callback: function(v){return v+"%";}}}, x: {grid: {display: false}} }
      }
    });
  }

  function renderLossCat(d){
    destroy("cat");
    var ctx = document.getElementById("ch-loss-cat").getContext("2d");
    // Three restrained shades - no gradients
    charts.cat = new Chart(ctx, {
      type: "doughnut",
      data: { labels: ["AR","PR","QR"], datasets: [{ data: [d.AR||0, d.PR||0, d.QR||0], backgroundColor: [C.warn, C.neu, C.bad], borderWidth: 2, borderColor: "#fff", hoverOffset: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: {position: "bottom", labels: {boxWidth: 10, padding: 12, usePointStyle: true, pointStyle: "circle"}}, tooltip: { callbacks: { label: function(c){ return c.label + ": " + fmt(c.parsed, 1) + " min"; } } } } }
    });
  }

  function renderMachineRank(rows){
    destroy("mrank");
    var ctx = document.getElementById("ch-machine-rank").getContext("2d");
    // Single color solid bars
    charts.mrank = new Chart(ctx, {
      type: "bar",
      data: { labels: rows.map(function(r){return r.machine;}), datasets: [{ label: "Avg OEE", data: rows.map(function(r){return r.avg_oee;}), backgroundColor: C.ac, borderRadius: 3, barPercentage: 0.75 }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: {legend: {display: false}, tooltip: { callbacks: { label: function(c){ return "OEE: " + fmt(c.parsed.x, 1) + "%"; } } } }, scales: {x: {beginAtZero: true, max: 100, grid: {color: "rgba(31,39,46,0.05)"}, ticks: {callback: function(v){return v+"%";}}}, y: {grid: {display: false}}} }
    });
  }

  function renderShift(rows){
    destroy("shift");
    var ctx = document.getElementById("ch-shift").getContext("2d");
    // Two shades of blue plus dark for OEE - reduced palette
    charts.shift = new Chart(ctx, {
      type: "bar",
      data: {
        labels: rows.map(function(r){return r.shift;}),
        datasets: [
          {label:"Availability", data: rows.map(function(r){return r.a;}), backgroundColor: "#8bc4f2", borderRadius: 3},
          {label:"Performance", data: rows.map(function(r){return r.p;}), backgroundColor: "#5ea9ec", borderRadius: 3},
          {label:"Quality",     data: rows.map(function(r){return r.q;}), backgroundColor: "#2490ef", borderRadius: 3},
          {label:"OEE",         data: rows.map(function(r){return r.oee;}), backgroundColor: C.tp, borderRadius: 3}
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: {legend: {position: "bottom", labels: {boxWidth: 10, padding: 12, usePointStyle: true, pointStyle: "rect"}}, tooltip: { callbacks: { label: function(c){ return c.dataset.label + ": " + fmt(c.parsed.y, 1) + "%"; } } } }, scales: {y: {beginAtZero: true, max: 100, grid: {color: "rgba(31,39,46,0.05)"}, ticks: {callback: function(v){return v+"%";}}}, x: {grid: {display: false}}} }
    });
  }

  function renderPareto(rows){
    destroy("pareto");
    var ctx = document.getElementById("ch-pareto").getContext("2d");
    var total = rows.reduce(function(s,r){return s + (r.total_min||0);}, 0);
    var cum = 0;
    var cumPct = rows.map(function(r){ cum += (r.total_min||0); return total ? (cum/total*100) : 0; });
    // Single amber for AR-loss bars (dominant category), dark line for cumulative
    charts.pareto = new Chart(ctx, {
      data: {
        labels: rows.map(function(r){ return (r.code||"") + " " + (r.name||"").slice(0,20); }),
        datasets: [
          { type: "bar", label: "Loss min", data: rows.map(function(r){return r.total_min;}), backgroundColor: C.warn, yAxisID: "y", borderRadius: 3, barPercentage: 0.75 },
          { type: "line", label: "Cumulative %", data: cumPct, borderColor: C.tp, backgroundColor: C.tp, borderWidth: 1.8, pointRadius: 3, pointHoverRadius: 5, yAxisID: "y1", tension: 0.15 }
        ]
      },
      options: { responsive: true, maintainAspectRatio: false, plugins: {legend: {position: "bottom", labels: {boxWidth: 10, padding: 12, usePointStyle: true, pointStyle: "rect"}}}, scales: { y: {beginAtZero: true, grid: {color: "rgba(31,39,46,0.05)"}, title: {display: true, text: "Minutes"}}, y1: {beginAtZero: true, max: 100, position: "right", grid: {display: false}, ticks: {callback: function(v){return v+"%";}}} } }
    });
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
print("[OK] template rewritten - ERPNext-style restrained palette. No gradients, no hero ring, single dominant color per chart, fast animations (~500ms), muted dashed lines for secondary series in trend.")
