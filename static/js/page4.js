Chart.defaults.font.family = 'IBM Plex Sans';

// ── 1. Number count-up animation ────────────────────────────────────────────
function animateCountUp(elementId, finalValue, duration = 900, suffix = '') {
  const el = document.getElementById(elementId);
  if (!el) return;
  const isPercent = suffix === '%';
  const target = parseFloat(finalValue) || 0;
  const startTime = performance.now();

  function easeOutQuad(t) { return t * (2 - t); }

  function tick(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = easeOutQuad(progress);
    const current = target * eased;
    el.textContent = isPercent ? current.toFixed(0) + '%' : Math.round(current);
    if (progress < 1) requestAnimationFrame(tick);
    else el.textContent = isPercent ? target.toFixed(0) + '%' : Math.round(target);
  }
  requestAnimationFrame(tick);
}

// ── 5. Animated empty state ─────────────────────────────────────────────────
function showEmpty(wrapId, msg) {
  const el = document.getElementById(wrapId);
  el.innerHTML = `<div class="empty-chart" style="opacity:0;transform:translateY(6px);transition:opacity 0.5s ease, transform 0.5s ease;">${msg}</div>`;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const inner = el.querySelector('.empty-chart');
      if (inner) { inner.style.opacity = '1'; inner.style.transform = 'translateY(0)'; }
    });
  });
}

// ── 3. Card reveal — fades/slides a card in, resolves AFTER the fade
//      finishes, so the chart inside only starts animating once visible ─────
function revealCard(cardEl, delay = 0) {
  return new Promise((resolve) => {
    if (!cardEl) { resolve(); return; }
    cardEl.style.opacity = '0';
    cardEl.style.transform = 'translateY(14px)';
    cardEl.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
    setTimeout(() => {
      cardEl.style.opacity = '1';
      cardEl.style.transform = 'translateY(0)';
    }, delay);
    setTimeout(resolve, delay + 500);
  });
}

function animateChartData(chart, finalDatasets, duration = 900) {
  const steps = 40;
  const stepTime = duration / steps;
  let currentStep = 0;

  const startData = finalDatasets.map(ds => ds.data.map(() => 0));

  const interval = setInterval(() => {
    currentStep++;
    const progress = Math.min(currentStep / steps, 1);
    const eased = progress * (2 - progress);

    chart.data.datasets.forEach((ds, dsIdx) => {
      ds.data = finalDatasets[dsIdx].data.map((finalVal, i) => {
        const start = startData[dsIdx][i];
        return start + (finalVal - start) * eased;
      });
    });
    chart.update('none');

    if (currentStep >= steps) clearInterval(interval);
  }, stepTime);
}
function revealStatCardsImmediately() {
  document.querySelectorAll('.stat-card').forEach((card, idx) => {
    card.style.opacity = '0';
    card.style.transform = 'translateY(14px)';
    card.style.transition = 'opacity 0.45s ease, transform 0.45s ease';
    setTimeout(() => {
      card.style.opacity = '1';
      card.style.transform = 'translateY(0)';
    }, idx * 90);
  });
}

function findCard(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return null;
  return el.closest('.chart-card') || el.closest('.stat-card') || el;
}

// ── 4. Hover micro-interactions (inject once) ───────────────────────────────
function injectHoverStyles() {
  if (document.getElementById('analytics-hover-style')) return;
  const style = document.createElement('style');
  style.id = 'analytics-hover-style';
  style.textContent = `
    .stat-card, .chart-card {
      transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .stat-card:hover, .chart-card:hover {
      transform: translateY(-3px);
      box-shadow: 0 8px 20px rgba(15, 42, 77, 0.10);
    }
  `;
  document.head.appendChild(style);
}

// ── 2. Shared chart animation config ────────────────────────────────────────
const CHART_ANIM = {
  duration: 900,
  easing: 'easeOutQuart',
};

async function loadAll() {
  injectHoverStyles();
  revealStatCardsImmediately();

  try {
    const [sum, byItem, bySup, daily, wip] = await Promise.all([
      fetch('/api/analytics/summary').then(r => r.json()),
      fetch('/api/analytics/quality_by_item').then(r => r.json()),
      fetch('/api/analytics/supervisor_performance').then(r => r.json()),
      fetch('/api/analytics/daily_checks').then(r => r.json()),
      fetch('/api/analytics/wip_distribution').then(r => r.json()),
    ]);

    if (sum.success) {
      animateCountUp('s-jc', sum.total_job_cards);
      animateCountUp('s-items', sum.total_items);
      animateCountUp('s-qc', sum.total_quality_checks);
      animateCountUp('s-ok', sum.ok_pct, 900, '%');
      document.getElementById('s-ok-sub').textContent = `${sum.ok} OK / ${sum.not_ok} Not OK`;
    }

    await revealCard(findCard('chart-donut'));
    console.log('About to create donut chart at', performance.now());
    if (sum.success && (sum.ok + sum.not_ok > 0)) {
      new Chart(document.getElementById('chart-donut'), {
        type: 'doughnut',
        data: {
          labels: ['OK', 'Not OK'],
          datasets: [{ data: [sum.ok, sum.not_ok], backgroundColor: ['#16a34a', '#dc2626'], borderWidth: 0 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom' } },
          animation: { ...CHART_ANIM, animateRotate: true, animateScale: true },
        }
      });
    } else showEmpty('donut-wrap', 'No quality check data yet');

    await revealCard(findCard('chart-wip'), 80);
    if (wip.success && wip.data.length) {
      new Chart(document.getElementById('chart-wip'), {
        type: 'bar',
        data: {
          labels: wip.data.map(d => d.wip_status),
          datasets: [{ label: 'Items', data: wip.data.map(d => d.count), backgroundColor: '#1a56db', borderRadius: 4 }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
          plugins: { legend: { display: false } },
          animation: { ...CHART_ANIM, delay: (ctx) => ctx.dataIndex * 60 },
        }
      });
    } else showEmpty('wip-wrap', 'No WIP data yet');

    await revealCard(findCard('chart-supervisor'), 80);
    if (bySup.success && bySup.data.length) {
      new Chart(document.getElementById('chart-supervisor'), {
        type: 'bar',
        data: {
          labels: bySup.data.map(d => d.supervisor),
          datasets: [
            { label: 'OK', data: bySup.data.map(d => d.ok_count), backgroundColor: '#1a56db', borderRadius: 4 },
            { label: 'Not OK', data: bySup.data.map(d => d.not_ok_count), backgroundColor: '#fca5a5', borderRadius: 4 }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: { y: { beginAtZero: true } },
          plugins: { legend: { position: 'bottom' } },
          animation: { ...CHART_ANIM, delay: (ctx) => ctx.dataIndex * 60 + ctx.datasetIndex * 120 },
        }
      });
    } else showEmpty('sup-wrap', 'No supervisor data yet');

    await revealCard(findCard('chart-daily'), 80);
    if (daily.success && daily.data.length) {
      new Chart(document.getElementById('chart-daily'), {
        type: 'line',
        data: {
          labels: daily.data.map(d => formatDateForDisplay(d.date)),
          datasets: [{
            label: 'Quality Checks', data: daily.data.map(d => d.count),
            borderColor: '#1a56db', backgroundColor: 'rgba(26,86,219,0.08)',
            fill: true, tension: 0.3, pointRadius: 3
          }]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          scales: { y: { beginAtZero: true } },
          plugins: { legend: { display: false } },
          animation: {
            duration: 1100,
            easing: 'easeOutQuart',
            x: {
              type: 'number', easing: 'linear', duration: 1100, from: NaN,
              delay(ctx) {
                if (ctx.type !== 'data' || ctx.xStarted) return 0;
                ctx.xStarted = true;
                return ctx.index * 35;
              }
            },
            y: {
              type: 'number', easing: 'linear', duration: 1100,
              from: (ctx) => ctx.chart.scales.y.getPixelForValue(0),
              delay(ctx) {
                if (ctx.type !== 'data' || ctx.yStarted) return 0;
                ctx.yStarted = true;
                return ctx.index * 35;
              }
            },
          },
        }
      });
    } else showEmpty('daily-wrap', 'No data in last 30 days');

  } catch (e) { console.error('Analytics error:', e); }
}

loadAll();