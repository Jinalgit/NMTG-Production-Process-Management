/* ── Analytics Page JS — NMTG JMS ────────────────────────────────────────── */

Chart.defaults.font.family = 'IBM Plex Sans';
Chart.defaults.font.size = 12;

const IS_ADMIN = window.JMS_USER_ROLE === 'admin';

// ── Date range state ──────────────────────────────────────────────────────────
let anaFromDate = '';
let anaToDate = '';

function initDateDefaults() {
  const sidebarDate = localStorage.getItem('jms_filter_date') || '';

  if (sidebarDate) {
    anaFromDate = sidebarDate;
    anaToDate = sidebarDate;
  } else {
    anaFromDate = '';
    anaToDate = '';
  }
}

function dateParams() {
  const sidebarDate = localStorage.getItem('jms_filter_date') || '';

  if (sidebarDate) {
    return `from_date=${sidebarDate}&to_date=${sidebarDate}`;
  }

  const params = new URLSearchParams();

  if (anaFromDate) params.set('from_date', anaFromDate);
  if (anaToDate) params.set('to_date', anaToDate);

  return params.toString();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmtDate(str) {
  if (!str) return '—';
  const d = new Date(str + 'T00:00:00');
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function animateCountUp(id, final, suffix = '', decimals = 0) {
  const el = document.getElementById(id);
  if (!el) return;
  const target = parseFloat(final) || 0;
  const start = performance.now();
  const dur = 900;
  const ease = (t) => t * (2 - t);

  function tick(now) {
    const p = Math.min((now - start) / dur, 1);
    const val = target * ease(p);
    el.textContent = decimals > 0 ? val.toFixed(decimals) + suffix : Math.round(val) + suffix;
    if (p < 1) requestAnimationFrame(tick);
    else el.textContent = decimals > 0 ? target.toFixed(decimals) + suffix : Math.round(target) + suffix;
  }
  requestAnimationFrame(tick);
}

function revealCards(selector, baseDelay = 0) {
  document.querySelectorAll(selector).forEach((el, i) => {
    setTimeout(() => el.classList.add('visible'), baseDelay + i * 80);
  });
}

const CHART_ANIM = { duration: 900, easing: 'easeOutQuart' };

// ── Chart instances (to destroy on re-render) ─────────────────────────────────
const charts = {};

function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); delete charts[key]; }
}

// ── Section 1: KPI Cards ──────────────────────────────────────────────────────
async function loadKPIs() {
  try {
    const res = await fetch(`/api/analytics/summary?${dateParams()}`);
    const d = await res.json();
    if (!d.success) return;

    animateCountUp('kpi-total', d.total_job_cards);
    animateCountUp('kpi-active', d.active_job_cards);
    animateCountUp('kpi-completed', d.completed_this_month);
    animateCountUp('kpi-overdue', d.overdue_job_cards);


    revealCards('.kpi-card');
  } catch (e) { console.error('KPI load error:', e); }
}

// ── Section 2: WIP Flow ───────────────────────────────────────────────────────
async function loadWipFlow() {
  destroyChart('wip');
  try {
    const res = await fetch(`/api/analytics/wip_flow?${dateParams()}`);
    const d = await res.json();

    const card = document.getElementById('chart-wip-flow')?.closest('.chart-card');
    if (!d.success || !d.data.length) {
      document.getElementById('wip-flow-empty').style.display = 'flex';
      if (card) setTimeout(() => card.classList.add('visible'), 100);
      return;
    }

    document.getElementById('wip-flow-empty').style.display = 'none';
    if (card) setTimeout(() => card.classList.add('visible'), 100);

    const labels = d.data.map(r => r.wip_status);
    const values = d.data.map(r => r.count);
    const maxVal = Math.max(...values);

    const colors = values.map(v => {
      const ratio = v / maxVal;
      if (ratio > 0.7) return '#dc2626';
      if (ratio > 0.4) return '#f59e0b';
      return '#1a56db';
    });

    charts['wip'] = new Chart(document.getElementById('chart-wip-flow'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Job Cards',
          data: values,
          backgroundColor: colors,
          borderRadius: 6,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.raw} job card${ctx.raw !== 1 ? 's' : ''}`
            }
          }
        },
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: '#f3f4f6' } },
          x: { grid: { display: false } }
        },
        animation: { ...CHART_ANIM, delay: (ctx) => ctx.dataIndex * 40 },
      }
    });
  } catch (e) { console.error('WIP flow error:', e); }
}

// ── Section 3: Daily Activity ─────────────────────────────────────────────────
async function loadDailyActivity() {
  destroyChart('daily');
  try {
    const sidebarDate = localStorage.getItem('jms_filter_date') || '';
    const isSingleDay = sidebarDate !== '';

    const card = document.getElementById('chart-daily-activity')?.closest('.chart-card');
    if (card) setTimeout(() => card.classList.add('visible'), 200);

    if (isSingleDay) {
      // Single day — show process breakdown
      const res = await fetch(`/api/analytics/daily_breakdown?date=${sidebarDate}`);
      const d = await res.json();

      if (!d.success || !d.data.length) {
        document.getElementById('daily-activity-empty').style.display = 'flex';
        document.getElementById('chart-daily-activity').style.display = 'none';
        return;
      }

      document.getElementById('daily-activity-empty').style.display = 'none';
      document.getElementById('chart-daily-activity').style.display = '';

      // Update chart title to show date summary
      const titleEl = card?.querySelector('.chart-title');
      if (titleEl) {
        titleEl.innerHTML = `<i class="fa fa-bar-chart"></i> 
          Production on ${new Date(sidebarDate + 'T00:00:00').toLocaleDateString('en-IN', {day:'2-digit', month:'short', year:'numeric'})}
          &nbsp;<span style="font-size:11px;font-weight:500;color:var(--muted);">
            ${d.summary.total_stages} stages · ${d.summary.total_job_cards} job cards · ${d.summary.active_supervisors} supervisors active
          </span>`;
      }

      const maxVal = Math.max(...d.data.map(r => r.completions));
      charts['daily'] = new Chart(document.getElementById('chart-daily-activity'), {
        type: 'bar',
        data: {
          labels: d.data.map(r => r.process_name),
          datasets: [{
            label: 'Stages Completed',
            data: d.data.map(r => r.completions),
            backgroundColor: d.data.map(r => {
              const ratio = r.completions / maxVal;
              if (ratio > 0.7) return 'rgba(26,86,219,0.85)';
              if (ratio > 0.4) return 'rgba(13,148,136,0.85)';
              return 'rgba(22,163,74,0.85)';
            }),
            borderRadius: 6,
            borderSkipped: false,
          }]
        },
        options: {
          indexAxis: 'y',
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => ` ${ctx.raw} stage${ctx.raw !== 1 ? 's' : ''} completed`
              }
            }
          },
          scales: {
            x: { beginAtZero: true, ticks: { stepSize: 1 }, grid: { color: '#f3f4f6' } },
            y: { grid: { display: false } }
          },
          animation: { ...CHART_ANIM, delay: (ctx) => ctx.dataIndex * 60 },
        }
      });

    } else {
      // Date range — show line chart
      const res = await fetch(`/api/analytics/daily_activity?${dateParams()}`);
      const d = await res.json();

      if (!d.success || !d.data.length) {
        document.getElementById('daily-activity-empty').style.display = 'flex';
        document.getElementById('chart-daily-activity').style.display = 'none';
        return;
      }

      document.getElementById('daily-activity-empty').style.display = 'none';
      document.getElementById('chart-daily-activity').style.display = '';

      const titleEl = card?.querySelector('.chart-title');
      if (titleEl) titleEl.innerHTML = `<i class="fa fa-line-chart"></i> Daily Production Activity`;

      charts['daily'] = new Chart(document.getElementById('chart-daily-activity'), {
        type: 'line',
        data: {
          labels: d.data.map(r => fmtDate(r.activity_date)),
          datasets: [{
            label: 'Stages Completed',
            data: d.data.map(r => r.stages_completed),
            borderColor: '#1a56db',
            backgroundColor: 'rgba(26,86,219,0.08)',
            fill: true,
            tension: 0.4,
            pointRadius: 4,
            pointBackgroundColor: '#1a56db',
            pointHoverRadius: 6,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
            x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } }
          },
          animation: {
            duration: 1100, easing: 'easeOutQuart',
            x: { type: 'number', easing: 'linear', duration: 1100, from: NaN,
              delay(ctx) { if (ctx.type !== 'data' || ctx.xStarted) return 0; ctx.xStarted = true; return ctx.index * 30; }
            },
            y: { type: 'number', easing: 'linear', duration: 1100,
              from: (ctx) => ctx.chart.scales.y.getPixelForValue(0),
              delay(ctx) { if (ctx.type !== 'data' || ctx.yStarted) return 0; ctx.yStarted = true; return ctx.index * 30; }
            },
          }
        }
      });
    }
  } catch (e) { console.error('Daily activity error:', e); }
}

// ── Section 4: Process Delays ─────────────────────────────────────────────────
async function loadProcessDelays() {
  destroyChart('delays');
  try {
    const res = await fetch(`/api/analytics/process_delays?${dateParams()}`);
    const d = await res.json();

    const card = document.getElementById('chart-process-delays')?.closest('.chart-card');
    if (!d.success || !d.data.length) {
      document.getElementById('process-delays-empty').style.display = 'flex';
      document.getElementById('chart-process-delays').style.display = 'none';
      if (card) setTimeout(() => card.classList.add('visible'), 300);
      return;
    }

    document.getElementById('process-delays-empty').style.display = 'none';
    document.getElementById('chart-process-delays').style.display = '';
    if (card) setTimeout(() => card.classList.add('visible'), 300);

    const labels = d.data.map(r => r.process_name);
    const planned = d.data.map(r => parseFloat(r.avg_planned) || 0);
    const actual = d.data.map(r => parseFloat(r.avg_actual) || 0);

    charts['delays'] = new Chart(document.getElementById('chart-process-delays'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Planned (avg days)', data: planned, backgroundColor: 'rgba(26,86,219,0.6)', borderRadius: 4 },
          { label: 'Actual (avg days)', data: actual,
            backgroundColor: actual.map((a, i) => a > planned[i] ? 'rgba(220,38,38,0.75)' : 'rgba(22,163,74,0.75)'),
            borderRadius: 4 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
        scales: {
          y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
          x: { grid: { display: false }, ticks: { maxRotation: 30 } }
        },
        animation: { ...CHART_ANIM, delay: (ctx) => ctx.dataIndex * 50 + ctx.datasetIndex * 100 },
      }
    });
  } catch (e) { console.error('Process delays error:', e); }
}

// ── Section 5: Customer Delivery ──────────────────────────────────────────────
async function loadCustomerDelivery() {
  destroyChart('delivery');
  try {
    const res = { ok: true, json: async () => ({ success: true, data: [], labels: [], values: [] }) };
    const d = await res.json();

    // Donut
    const donutCard = document.getElementById('chart-delivery-donut')?.closest('.chart-card');
    const overall = d.success ? d.overall : { on_time: 0, delayed: 0, critical: 0 };
    const totalDelivered = overall.on_time + overall.delayed + overall.critical;

    if (totalDelivered > 0) {
      document.getElementById('delivery-donut-empty').style.display = 'none';
      if (donutCard) setTimeout(() => donutCard.classList.add('visible'), 100);

      charts['delivery'] = new Chart(document.getElementById('chart-delivery-donut'), {
        type: 'doughnut',
        data: {
          labels: ['On Time', 'Delayed (≤7d)', 'Critical (>7d)'],
          datasets: [{
            data: [overall.on_time, overall.delayed, overall.critical],
            backgroundColor: ['#16a34a', '#f59e0b', '#dc2626'],
            borderWidth: 2,
            borderColor: '#fff',
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '65%',
          plugins: {
            legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const pct = totalDelivered > 0 ? ((ctx.raw / totalDelivered) * 100).toFixed(1) : 0;
                  return ` ${ctx.raw} (${pct}%)`;
                }
              }
            }
          },
          animation: { ...CHART_ANIM, animateRotate: true, animateScale: true },
        }
      });
    } else {
      document.getElementById('delivery-donut-empty').style.display = 'flex';
      if (donutCard) setTimeout(() => donutCard.classList.add('visible'), 100);
    }

    // Per customer table
    const tableWrap = document.getElementById('customer-table-wrap');
    const tableCard = tableWrap?.closest('.chart-card');
    if (tableCard) setTimeout(() => tableCard.classList.add('visible'), 200);

    if (d.success && d.by_customer && d.by_customer.length) {
      document.getElementById('customer-table-empty').style.display = 'none';
      const html = d.by_customer.map(r => {
        const pct = r.total > 0 ? Math.round((r.on_time / r.total) * 100) : 0;
        return `
          <div class="customer-row">
            <div class="customer-name-cell" title="${esc(r.customer_name)}">${esc(r.customer_name)}</div>
            <div class="cust-num on-time">${r.on_time} ✓</div>
            <div class="cust-num delayed-c">${r.delayed_count || 0} ✗</div>
            <div class="cust-num total-c">${r.total}</div>
            <div class="customer-bar-wrap" style="grid-column:1/-1;">
              <div class="customer-bar-fill" style="width:${pct}%;"></div>
            </div>
          </div>`;
      }).join('');
      tableWrap.innerHTML = `
        <div style="display:grid; grid-template-columns:1fr 80px 80px 80px; padding:0 0 6px; gap:8px;">
          <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;">Customer</div>
          <div style="font-size:11px;font-weight:700;color:#16a34a;text-align:center;text-transform:uppercase;">On Time</div>
          <div style="font-size:11px;font-weight:700;color:#dc2626;text-align:center;text-transform:uppercase;">Delayed</div>
          <div style="font-size:11px;font-weight:700;color:var(--muted);text-align:center;text-transform:uppercase;">Total</div>
        </div>
        <div style="border-top:1px solid var(--border);">${html}</div>`;
    } else {
      document.getElementById('customer-table-empty').style.display = 'flex';
    }
  } catch (e) { console.error('Customer delivery error:', e); }
}

// ── Section 6: Overdue Jobs ───────────────────────────────────────────────────
async function loadOverdueJobs() {
  destroyChart('overdue-jobs');
  destroyChart('overdue-stage');

  try {
    const res = await fetch(`/api/analytics/overdue_jobs?${dateParams()}`);
    const d = await res.json();

    const card = document.getElementById('chart-overdue-jobs')?.closest('.chart-card');
    if (card) setTimeout(() => card.classList.add('visible'), 100);

    const empty = document.getElementById('overdue-empty');
    const chartRow = document.getElementById('overdue-chart-row');
    const summaryGrid = document.getElementById('overdue-summary-grid');

    if (!d.success || !d.data || !d.data.length) {
      if (empty) empty.style.display = 'flex';
      if (chartRow) chartRow.style.display = 'none';
      if (summaryGrid) summaryGrid.style.display = 'none';
      return;
    }

    if (empty) empty.style.display = 'none';
    if (chartRow) chartRow.style.display = 'grid';
    if (summaryGrid) summaryGrid.style.display = 'grid';

    const rows = d.data.slice(0, 10);

    const total = d.data.length;
    const critical = d.data.filter(r => Number(r.days_overdue || 0) > 7).length;
    const warning = d.data.filter(r => Number(r.days_overdue || 0) <= 7).length;
    const maxDays = Math.max(...d.data.map(r => Number(r.days_overdue || 0)));

    document.getElementById('overdue-total-count').textContent = total;
    document.getElementById('overdue-critical-count').textContent = critical;
    document.getElementById('overdue-warning-count').textContent = warning;
    document.getElementById('overdue-max-days').textContent = `${maxDays}d`;

    const labels = rows.map(r => `${r.job_card_no} · ${r.current_stage || '—'}`);
    const values = rows.map(r => Number(r.days_overdue || 0));

    const barColors = values.map(v => {
      if (v > 7) return 'rgba(220,38,38,0.82)';
      if (v >= 3) return 'rgba(245,158,11,0.82)';
      return 'rgba(234,179,8,0.82)';
    });

    charts['overdue-jobs'] = new Chart(document.getElementById('chart-overdue-jobs'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Days Overdue',
          data: values,
          backgroundColor: barColors,
          borderRadius: 7,
          borderSkipped: false,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => {
                const idx = items[0].dataIndex;
                const r = rows[idx];
                return `JC ${r.job_card_no}`;
              },
              label: (ctx) => {
                const r = rows[ctx.dataIndex];
                return [
                  ` ${r.days_overdue} day(s) overdue`,
                  ` Stage: ${r.current_stage || '—'}`,
                  ` Customer: ${r.customer_name || '—'}`,
                  ` Delivery: ${fmtDate(r.delivery_date)}`
                ];
              }
            }
          }
        },
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: '#f3f4f6' },
            title: {
              display: true,
              text: 'Days Overdue'
            }
          },
          y: {
            grid: { display: false },
            ticks: {
              autoSkip: false,
              callback: function(value) {
                const label = this.getLabelForValue(value);
                return label.length > 28 ? label.slice(0, 28) + '…' : label;
              }
            }
          }
        },
        animation: {
          ...CHART_ANIM,
          delay: (ctx) => ctx.dataIndex * 60
        },
        onClick: (event, elements) => {
          if (!elements.length) return;
          const r = rows[elements[0].index];
          if (r && r.job_card_no) {
            window.location = `/page3`;
          }
        }
      }
    });

    const stageMap = {};
    d.data.forEach(r => {
      const stage = r.current_stage || 'Unknown';
      stageMap[stage] = (stageMap[stage] || 0) + 1;
    });

    const stageLabels = Object.keys(stageMap);
    const stageValues = Object.values(stageMap);

    charts['overdue-stage'] = new Chart(document.getElementById('chart-overdue-stage'), {
      type: 'doughnut',
      data: {
        labels: stageLabels,
        datasets: [{
          data: stageValues,
          backgroundColor: [
            '#dc2626',
            '#f59e0b',
            '#eab308',
            '#7c3aed',
            '#1a56db',
            '#0d9488',
            '#16a34a',
            '#db2777'
          ],
          borderColor: '#fff',
          borderWidth: 2,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '62%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              boxWidth: 12,
              padding: 12
            }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.raw} job card(s)`
            }
          }
        },
        animation: {
          ...CHART_ANIM,
          animateRotate: true,
          animateScale: true
        }
      }
    });

  } catch (e) {
    console.error('Overdue jobs error:', e);
  }
}
// ── Section 7: Supervisor Performance (Admin only) ────────────────────────────
async function loadSupervisorPerformance() {
  if (!IS_ADMIN) return;
  destroyChart('supervisor');

  try {
    const res = await fetch(`/api/analytics/supervisor_stages?${dateParams()}`);
    const d = await res.json();

    const card = document.getElementById('chart-supervisor')?.closest('.chart-card');
    if (!d.success || !d.data.length) {
      document.getElementById('supervisor-empty').style.display = 'flex';
      document.getElementById('chart-supervisor').style.display = 'none';
      if (card) setTimeout(() => card.classList.add('visible'), 100);
      return;
    }

    document.getElementById('supervisor-empty').style.display = 'none';
    document.getElementById('chart-supervisor').style.display = '';
    if (card) setTimeout(() => card.classList.add('visible'), 100);

    const colors = [
      '#1a56db','#16a34a','#d97706','#7c3aed','#dc2626',
      '#0d9488','#db2777','#ea580c','#4f46e5','#059669',
    ];

    charts['supervisor'] = new Chart(document.getElementById('chart-supervisor'), {
      type: 'bar',
      data: {
        labels: d.data.map(r => r.supervisor),
        datasets: [
          {
            label: 'Stages Completed',
            data: d.data.map(r => r.stages_completed),
            backgroundColor: d.data.map((_, i) => colors[i % colors.length]),
            borderRadius: 6,
            borderSkipped: false,
          },
          {
            label: 'Job Cards Handled',
            data: d.data.map(r => r.job_cards_handled),
            backgroundColor: d.data.map((_, i) => colors[i % colors.length] + '55'),
            borderRadius: 6,
            borderSkipped: false,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
        scales: {
          y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
          x: { grid: { display: false } }
        },
        animation: { ...CHART_ANIM, delay: (ctx) => ctx.dataIndex * 60 + ctx.datasetIndex * 100 },
      }
    });
  } catch (e) { console.error('Supervisor error:', e); }
}

// ── Load All ──────────────────────────────────────────────────────────────────
async function loadAll() {
  // Recalculate date range on every load
  initDateDefaults();

  // Reset all chart cards visibility
  document.querySelectorAll('.chart-card, .kpi-card').forEach(el => {
    el.classList.remove('visible');
  });

  await Promise.all([
    loadKPIs(),
    loadWipFlow(),
    loadDailyActivity(),
    loadProcessDelays(),
    loadOverdueJobs(),
    loadOTD(),
    loadSupervisorPerformance(),
  ]);
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initDateDefaults();
  loadAll();
});

// ── OTD: On Time Delivery ─────────────────────────────────────────────────────
async function loadOTD() {
  destroyChart('otd-donut');
  destroyChart('otd-monthly');
  try {
    const res = await fetch(`/api/analytics/otd?${dateParams()}`);
    const d = await res.json();

    const donutCard = document.getElementById('chart-otd-donut')?.closest('.chart-card');
    const monthlyCard = document.getElementById('chart-otd-monthly')?.closest('.chart-card');

    if (donutCard) setTimeout(() => donutCard.classList.add('visible'), 100);
    if (monthlyCard) setTimeout(() => monthlyCard.classList.add('visible'), 200);

    if (!d.success) return;

    const overall = d.overall;

    if (overall.total === 0) {
      const row = document.querySelector('.chart-row:has(#chart-otd-donut)');
      if (row) row.style.display = 'none';
      const noData = document.getElementById('otd-no-data');
      if (noData) {
        noData.style.display = '';
        setTimeout(() => noData.classList.add('visible'), 100);
      }
      return;
    }

    // Show chart row, hide no-data
    const row = document.querySelector('.chart-row:has(#chart-otd-donut)');
    if (row) row.style.display = '';
    const noData = document.getElementById('otd-no-data');
    if (noData) noData.style.display = 'none';

    document.getElementById('otd-donut-empty').style.display = 'none';
    document.getElementById('otd-pct-display').style.display = 'block';
    document.getElementById('otd-pct-value').textContent = overall.otd_pct + '%';
    document.getElementById('otd-pct-value').style.color =
      overall.otd_pct >= 80 ? '#16a34a' : overall.otd_pct >= 60 ? '#d97706' : '#dc2626';

    charts['otd-donut'] = new Chart(document.getElementById('chart-otd-donut'), {
      type: 'doughnut',
      data: {
        labels: ['On Time', 'Delayed'],
        datasets: [{
          data: [overall.on_time, overall.delayed],
          backgroundColor: ['#16a34a', '#dc2626'],
          borderWidth: 2,
          borderColor: '#fff',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const pct = overall.total > 0 ? ((ctx.raw / overall.total) * 100).toFixed(1) : 0;
                return ` ${ctx.raw} (${pct}%)`;
              }
            }
          }
        },
        animation: { ...CHART_ANIM, animateRotate: true, animateScale: true },
      }
    });

    if (d.monthly && d.monthly.length) {
      document.getElementById('otd-monthly-empty').style.display = 'none';
      const labels = d.monthly.map(r => {
        const [y, m] = r.month.split('-');
        return new Date(y, m - 1).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
      });
      charts['otd-monthly'] = new Chart(document.getElementById('chart-otd-monthly'), {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'On Time', data: d.monthly.map(r => r.on_time),
              backgroundColor: 'rgba(22,163,74,0.8)', borderRadius: 5, borderSkipped: false },
            { label: 'Delayed', data: d.monthly.map(r => r.delayed_count),
              backgroundColor: 'rgba(220,38,38,0.75)', borderRadius: 5, borderSkipped: false }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
          scales: {
            y: { beginAtZero: true, grid: { color: '#f3f4f6' } },
            x: { grid: { display: false } }
          },
          animation: { ...CHART_ANIM, delay: (ctx) => ctx.dataIndex * 50 + ctx.datasetIndex * 80 },
        }
      });
    } else {
      document.getElementById('otd-monthly-empty').style.display = 'flex';
      document.getElementById('chart-otd-monthly').style.display = 'none';
    }
  } catch (e) { console.error('OTD error:', e); }
}