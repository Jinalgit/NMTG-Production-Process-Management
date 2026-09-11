/* ?? OEE Dashboard JS ? NMTG JMS ??????????????????????????? */

Chart.defaults.font.family = 'IBM Plex Sans';
Chart.defaults.font.size = 12;


const oeeCharts = {};


const OEE_CHART_ANIM = {
  duration: 900,
  easing: 'easeOutQuart'
};


// ?? Helpers ??????????????????????????????????????????????????????????????????

function oeeDateParams() {

  const sidebarDate =
    localStorage.getItem(
      'jms_filter_date'
    ) || '';


  if (sidebarDate) {

    return (
      `from_date=${encodeURIComponent(sidebarDate)}`
      +
      `&to_date=${encodeURIComponent(sidebarDate)}`
    );

  }


  return '';

}


function oeeFmtDate(str) {

  if (!str) return '?';


  const d =
    new Date(
      str + 'T00:00:00'
    );


  return d.toLocaleDateString(
    'en-IN',
    {
      day: '2-digit',
      month: 'short'
    }
  );

}


function oeeNum(
  value,
  decimals = 0
) {

  const n =
    Number(value || 0);


  return n.toLocaleString(
    'en-IN',
    {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    }
  );

}


function oeePct(value) {

  return (
    Number(value || 0)
    * 100
  ).toFixed(1) + '%';

}


function oeeAnimateCount(
  id,
  final,
  suffix = '',
  decimals = 0
) {

  const el =
    document.getElementById(id);


  if (!el) return;


  const target =
    Number(final || 0);


  const start =
    performance.now();


  const duration =
    850;


  const ease =
    (t) =>
      t * (2 - t);


  function tick(now) {

    const progress =
      Math.min(
        (now - start)
        /
        duration,
        1
      );


    const value =
      target
      *
      ease(progress);


    el.textContent =
      Number(value).toLocaleString(
        'en-IN',
        {
          minimumFractionDigits:
            decimals,

          maximumFractionDigits:
            decimals
        }
      )
      +
      suffix;


    if (progress < 1) {

      requestAnimationFrame(
        tick
      );

    }

  }


  requestAnimationFrame(
    tick
  );

}


function revealOeeCards() {

  document
    .querySelectorAll(
      '.kpi-card, .chart-card'
    )
    .forEach(
      (el, index) => {

        setTimeout(
          () =>
            el.classList.add(
              'visible'
            ),
          index * 55
        );

      }
    );

}


function destroyOeeChart(key) {

  if (
    oeeCharts[key]
  ) {

    oeeCharts[key].destroy();

    delete oeeCharts[key];

  }

}


// ?? KPI Rendering ?????????????????????????????????????????????????????????????

function renderOeeKpis(data) {

  const o =
    data.overview || {};


  oeeAnimateCount(
    'kpi-oee',
    Number(o.oee || 0) * 100,
    '%',
    1
  );


  oeeAnimateCount(
    'kpi-availability',
    Number(o.availability || 0) * 100,
    '%',
    1
  );


  oeeAnimateCount(
    'kpi-plan',
    Number(o.plan_achievement || 0) * 100,
    '%',
    1
  );


  oeeAnimateCount(
    'kpi-quality',
    Number(o.quality || 0) * 100,
    '%',
    1
  );


  oeeAnimateCount(
    'kpi-target',
    o.target_qty,
    '',
    1
  );


  oeeAnimateCount(
    'kpi-actual',
    o.actual_qty,
    '',
    0
  );


  oeeAnimateCount(
    'kpi-gap',
    o.production_gap,
    '',
    1
  );


  oeeAnimateCount(
    'kpi-loss',
    o.total_loss_hours,
    '',
    1
  );


  oeeAnimateCount(
    'kpi-no-operator',
    o.no_operator_hours,
    '',
    1
  );


  oeeAnimateCount(
    'kpi-hiring',
    o.recommended_hiring,
    '',
    0
  );


  oeeAnimateCount(
    'kpi-entry-count',
    o.entry_count,
    '',
    0
  );


  const runningHours =
    Number(
      o.run_minutes || 0
    )
    /
    60;


  oeeAnimateCount(
    'kpi-running-hours',
    runningHours,
    '',
    1
  );


  const gap =
    document.getElementById(
      'kpi-gap'
    );


  if (gap) {

    gap.classList.toggle(
      'oee-negative',
      Number(
        o.production_gap || 0
      ) < 0
    );


    gap.classList.toggle(
      'oee-positive',
      Number(
        o.production_gap || 0
      ) >= 0
    );

  }

}


// ?? Shift Table ???????????????????????????????????????????????????????????????

function getOeeShift(
  data,
  shiftName
) {

  return (
    data.shift_summary || []
  ).find(
    row =>
      String(
        row.shift_name
      )
      ===
      String(
        shiftName
      )
  ) || {};

}


function renderOeeShiftSummary(data) {

  const day =
    getOeeShift(
      data,
      '1'
    );


  const night =
    getOeeShift(
      data,
      '2'
    );


  const rows = [

    [
      'Active Days',
      oeeNum(day.active_days),
      oeeNum(night.active_days)
    ],

    [
      'Active Machines',
      oeeNum(day.active_machines),
      oeeNum(night.active_machines)
    ],

    [
      'Planned Hours',
      oeeNum(day.planned_hours, 1),
      oeeNum(night.planned_hours, 1)
    ],

    [
      'Running Hours',
      oeeNum(day.running_hours, 1),
      oeeNum(night.running_hours, 1)
    ],

    [
      'Target Qty',
      oeeNum(day.target_qty, 1),
      oeeNum(night.target_qty, 1)
    ],

    [
      'Actual Qty',
      oeeNum(day.actual_qty),
      oeeNum(night.actual_qty)
    ],

    [
      'Availability',
      oeePct(day.availability),
      oeePct(night.availability)
    ],

    [
      'Plan Achievement',
      oeePct(day.plan_achievement),
      oeePct(night.plan_achievement)
    ],

    [
      'Quality',
      oeePct(day.quality),
      oeePct(night.quality)
    ],

    [
      'OEE',
      oeePct(day.oee),
      oeePct(night.oee)
    ],

    [
      'No-Operator Hours',
      oeeNum(day.no_operator_hours, 1),
      oeeNum(night.no_operator_hours, 1)
    ],

    [
      'Full No-Operator Offs',
      oeeNum(day.full_no_operator_offs),
      oeeNum(night.full_no_operator_offs)
    ],

    [
      'Recommended Hiring',
      oeeNum(
        day.manpower
          ?.recommended_hires
      ),
      oeeNum(
        night.manpower
          ?.recommended_hires
      )
    ]

  ];


  const tbody =
    document.getElementById(
      'oee-shift-summary'
    );


  if (!tbody) return;


  tbody.innerHTML =
    rows.map(
      row => `

        <tr>

          <td>
            ${row[0]}
          </td>

          <td>
            ${row[1]}
          </td>

          <td>
            ${row[2]}
          </td>

        </tr>

      `
    ).join('');

}


// ?? Daily OEE Chart ???????????????????????????????????????????????????????????

function renderDailyOeeChart(data) {

  destroyOeeChart(
    'daily'
  );


  const rows =
    data.daily_trend || [];


  const empty =
    document.getElementById(
      'daily-oee-empty'
    );


  const canvas =
    document.getElementById(
      'chart-daily-oee'
    );


  if (
    !canvas
    ||
    !rows.length
  ) {

    if (empty) {
      empty.style.display =
        'flex';
    }

    if (canvas) {
      canvas.style.display =
        'none';
    }

    return;

  }


  if (empty) {
    empty.style.display =
      'none';
  }


  canvas.style.display =
    '';


  const labels =
    rows.map(
      row =>
        oeeFmtDate(
          row.date
        )
    );


  const oee =
    rows.map(
      row =>
        Number(
          row.oee || 0
        )
        *
        100
    );


  const plan =
    rows.map(
      row =>
        Number(
          row.plan_achievement || 0
        )
        *
        100
    );


  oeeCharts.daily =
    new Chart(
      canvas,
      {

        type: 'line',


        data: {

          labels,

          datasets: [

            {

              label: 'OEE',

              data: oee,

              borderColor:
                '#1a56db',

              backgroundColor:
                'rgba(26,86,219,0.08)',

              fill: true,

              tension: 0.4,

              borderWidth: 3,

              pointRadius: 4,

              pointBackgroundColor:
                '#1a56db',

              pointHoverRadius: 7

            },


            {

              label:
                'Plan Achievement',

              data: plan,

              borderColor:
                '#f59e0b',

              backgroundColor:
                'rgba(245,158,11,0.04)',

              fill: false,

              tension: 0.4,

              borderWidth: 3,

              pointRadius: 4,

              pointBackgroundColor:
                '#f59e0b',

              pointHoverRadius: 7

            }

          ]

        },


        options: {

          responsive: true,

          maintainAspectRatio:
            false,


          interaction: {

            intersect: false,

            mode: 'index'

          },


          plugins: {

            legend: {

              position:
                'bottom',

              labels: {

                boxWidth: 12,

                padding: 18,

                usePointStyle:
                  true

              }

            },


            tooltip: {

              callbacks: {

                label: (
                  context
                ) => {

                  return (
                    ` ${context.dataset.label}: `
                    +
                    `${Number(context.raw).toFixed(1)}%`
                  );

                }

              }

            }

          },


          scales: {

            y: {

              beginAtZero: true,

              suggestedMax: 100,

              ticks: {

                callback:
                  value =>
                    value + '%'

              },

              grid: {

                color:
                  '#f3f4f6'

              }

            },


            x: {

              grid: {

                display:
                  false

              },

              ticks: {

                maxTicksLimit:
                  14

              }

            }

          },


          animation: {

            duration: 1100,

            easing:
              'easeOutQuart'

          }

        }

      }
    );

}


// ?? Shift Comparison Chart ????????????????????????????????????????????????????

function renderShiftPerformanceChart(
  data
) {

  destroyOeeChart(
    'shift'
  );


  const day =
    getOeeShift(
      data,
      '1'
    );


  const night =
    getOeeShift(
      data,
      '2'
    );


  const canvas =
    document.getElementById(
      'chart-shift-performance'
    );


  if (!canvas) return;


  oeeCharts.shift =
    new Chart(
      canvas,
      {

        type: 'bar',


        data: {

          labels: [
            'Day Shift',
            'Night Shift'
          ],


          datasets: [

            {

              label:
                'Availability',

              data: [

                Number(
                  day.availability || 0
                ) * 100,

                Number(
                  night.availability || 0
                ) * 100

              ],

              backgroundColor:
                'rgba(22,163,74,0.78)',

              borderRadius: 6,

              borderSkipped:
                false

            },


            {

              label:
                'Plan Achievement',

              data: [

                Number(
                  day.plan_achievement || 0
                ) * 100,

                Number(
                  night.plan_achievement || 0
                ) * 100

              ],

              backgroundColor:
                'rgba(245,158,11,0.80)',

              borderRadius: 6,

              borderSkipped:
                false

            },


            {

              label:
                'Quality',

              data: [

                Number(
                  day.quality || 0
                ) * 100,

                Number(
                  night.quality || 0
                ) * 100

              ],

              backgroundColor:
                'rgba(124,58,237,0.78)',

              borderRadius: 6,

              borderSkipped:
                false

            },


            {

              label: 'OEE',

              data: [

                Number(
                  day.oee || 0
                ) * 100,

                Number(
                  night.oee || 0
                ) * 100

              ],

              backgroundColor:
                'rgba(26,86,219,0.82)',

              borderRadius: 6,

              borderSkipped:
                false

            }

          ]

        },


        options: {

          responsive: true,

          maintainAspectRatio:
            false,


          plugins: {

            legend: {

              position:
                'bottom',

              labels: {

                boxWidth: 12,

                padding: 14

              }

            },


            tooltip: {

              callbacks: {

                label: (
                  context
                ) => {

                  return (
                    ` ${context.dataset.label}: `
                    +
                    `${Number(context.raw).toFixed(1)}%`
                  );

                }

              }

            }

          },


          scales: {

            y: {

              beginAtZero:
                true,

              suggestedMax:
                100,

              ticks: {

                callback:
                  value =>
                    value + '%'

              },

              grid: {

                color:
                  '#f3f4f6'

              }

            },


            x: {

              grid: {

                display:
                  false

              }

            }

          },


          animation: {

            ...OEE_CHART_ANIM,

            delay:
              context =>
                context.dataIndex * 100
                +
                context.datasetIndex * 80

          }

        }

      }
    );

}



// OEE_SHIFT_SUMMARY_CHART_V2
// ?? Shift Capacity & Output ??????????????????????????????????????????????????
//
// LEFT AXIS  = Hours
// RIGHT AXIS = Quantity
//
// This avoids mixing Hours and Qty on one numerical scale.
//

function renderShiftSummaryChart(
  data
) {

  destroyOeeChart(
    'shift-summary'
  );


  const day =
    getOeeShift(
      data,
      '1'
    );


  const night =
    getOeeShift(
      data,
      '2'
    );


  const canvas =
    document.getElementById(
      'chart-shift-summary'
    );


  if (!canvas) return;


  oeeCharts['shift-summary'] =
    new Chart(
      canvas,
      {

        data: {

          labels: [
            'Day Shift',
            'Night Shift'
          ],


          datasets: [

            // =============================================
            // HOURS
            // =============================================

            {

              type: 'bar',

              label:
                'Planned Hours',

              data: [

                Number(
                  day.planned_hours || 0
                ),

                Number(
                  night.planned_hours || 0
                )

              ],

              yAxisID:
                'yHours',

              backgroundColor:
                'rgba(26,86,219,0.72)',

              borderRadius:
                6,

              borderSkipped:
                false

            },


            {

              type: 'bar',

              label:
                'Running Hours',

              data: [

                Number(
                  day.running_hours || 0
                ),

                Number(
                  night.running_hours || 0
                )

              ],

              yAxisID:
                'yHours',

              backgroundColor:
                'rgba(22,163,74,0.78)',

              borderRadius:
                6,

              borderSkipped:
                false

            },


            {

              type: 'bar',

              label:
                'No-Operator Hours',

              data: [

                Number(
                  day.no_operator_hours || 0
                ),

                Number(
                  night.no_operator_hours || 0
                )

              ],

              yAxisID:
                'yHours',

              backgroundColor:
                'rgba(220,38,38,0.72)',

              borderRadius:
                6,

              borderSkipped:
                false

            },


            // =============================================
            // QUANTITY
            // =============================================

            {

              type: 'line',

              label:
                'Target Qty',

              data: [

                Number(
                  day.target_qty || 0
                ),

                Number(
                  night.target_qty || 0
                )

              ],

              yAxisID:
                'yQty',

              borderColor:
                '#7c3aed',

              backgroundColor:
                '#7c3aed',

              borderWidth:
                3,

              tension:
                0.3,

              pointRadius:
                5,

              pointHoverRadius:
                7

            },


            {

              type: 'line',

              label:
                'Actual Qty',

              data: [

                Number(
                  day.actual_qty || 0
                ),

                Number(
                  night.actual_qty || 0
                )

              ],

              yAxisID:
                'yQty',

              borderColor:
                '#f59e0b',

              backgroundColor:
                '#f59e0b',

              borderWidth:
                3,

              tension:
                0.3,

              pointRadius:
                5,

              pointHoverRadius:
                7

            }

          ]

        },


        options: {

          responsive:
            true,

          maintainAspectRatio:
            false,


          interaction: {

            mode:
              'index',

            intersect:
              false

          },


          plugins: {

            legend: {

              position:
                'bottom',

              labels: {

                boxWidth:
                  12,

                padding:
                  12,

                usePointStyle:
                  true

              }

            },


            tooltip: {

              callbacks: {

                label:
                  context => {

                    const value =
                      Number(
                        context.raw || 0
                      );


                    if (
                      context.dataset.yAxisID
                      ===
                      'yHours'
                    ) {

                      return (
                        ` ${context.dataset.label}: `
                        +
                        `${value.toFixed(1)} hrs`
                      );

                    }


                    return (
                      ` ${context.dataset.label}: `
                      +
                      value.toLocaleString(
                        'en-IN',
                        {
                          maximumFractionDigits: 1
                        }
                      )
                    );

                  }

              }

            }

          },


          scales: {

            x: {

              grid: {

                display:
                  false

              }

            },


            yHours: {

              type:
                'linear',

              position:
                'left',

              beginAtZero:
                true,


              title: {

                display:
                  true,

                text:
                  'Hours'

              },


              grid: {

                color:
                  '#f3f4f6'

              },


              ticks: {

                callback:
                  value =>
                    value + ' h'

              }

            },


            yQty: {

              type:
                'linear',

              position:
                'right',

              beginAtZero:
                true,


              title: {

                display:
                  true,

                text:
                  'Quantity'

              },


              grid: {

                drawOnChartArea:
                  false

              }

            }

          },


          animation: {

            ...OEE_CHART_ANIM,

            delay:
              context =>
                context.dataIndex * 100
                +
                context.datasetIndex * 70

          }

        }

      }
    );

}


// ?? Period Label ??????????????????????????????????????????????????????????????

function renderOeePeriod(data) {

  const el =
    document.getElementById(
      'oee-period-label'
    );


  if (!el) return;


  const period =
    data.report_period || {};


  const sidebarDate =
    localStorage.getItem(
      'jms_filter_date'
    ) || '';


  if (sidebarDate) {

    const d =
      new Date(
        sidebarDate
        +
        'T00:00:00'
      );


    el.textContent =
      'Showing OEE for '
      +
      d.toLocaleDateString(
        'en-IN',
        {
          day: '2-digit',
          month: 'short',
          year: 'numeric'
        }
      );


    el.classList.add(
      'oee-period-single-day'
    );

    return;

  }


  el.classList.remove(
    'oee-period-single-day'
  );


  el.textContent =
    period.label
      ? `Reporting Period: ${period.label}`
      : 'No OEE data available';

}



// OEE_REMAINING_CHARTS_V1


// ?? Plan vs Actual ???????????????????????????????????????????????????????????

function renderPlanVsActualChart(
  data
) {

  destroyOeeChart(
    'plan-vs-actual'
  );


  const rows =
    data.daily_trend || [];


  const canvas =
    document.getElementById(
      'chart-plan-vs-actual'
    );


  const empty =
    document.getElementById(
      'plan-vs-actual-empty'
    );


  if (
    !canvas
    ||
    !rows.length
  ) {

    if (canvas) {
      canvas.style.display = 'none';
    }

    if (empty) {
      empty.style.display = 'flex';
    }

    return;

  }


  canvas.style.display = '';

  if (empty) {
    empty.style.display = 'none';
  }


  oeeCharts[
    'plan-vs-actual'
  ] = new Chart(
    canvas,
    {

      type: 'line',


      data: {

        labels:
          rows.map(
            row =>
              oeeFmtDate(
                row.date
              )
          ),


        datasets: [

          {

            label:
              'Target Qty',

            data:
              rows.map(
                row =>
                  Number(
                    row.target_qty || 0
                  )
              ),

            borderColor:
              '#1a56db',

            backgroundColor:
              'rgba(26,86,219,0.08)',

            borderWidth:
              3,

            fill:
              false,

            tension:
              0.35,

            pointRadius:
              4,

            pointHoverRadius:
              7,

          },


          {

            label:
              'Actual Qty',

            data:
              rows.map(
                row =>
                  Number(
                    row.actual_qty || 0
                  )
              ),

            borderColor:
              '#16a34a',

            backgroundColor:
              'rgba(22,163,74,0.08)',

            borderWidth:
              3,

            fill:
              false,

            tension:
              0.35,

            pointRadius:
              4,

            pointHoverRadius:
              7,

          },

        ],

      },


      options: {

        responsive:
          true,

        maintainAspectRatio:
          false,


        interaction: {
          mode: 'index',
          intersect: false,
        },


        plugins: {

          legend: {

            position:
              'bottom',

            labels: {
              boxWidth: 12,
              padding: 18,
              usePointStyle: true,
            },

          },


          tooltip: {

            callbacks: {

              label:
                context =>
                  ` ${context.dataset.label}: `
                  +
                  Number(
                    context.raw || 0
                  ).toLocaleString(
                    'en-IN',
                    {
                      maximumFractionDigits: 1
                    }
                  ),

            },

          },

        },


        scales: {

          y: {

            beginAtZero:
              true,

            grid: {
              color: '#f3f4f6',
            },

            title: {
              display: true,
              text: 'Quantity',
            },

          },


          x: {

            grid: {
              display: false,
            },

            ticks: {
              maxTicksLimit: 14,
            },

          },

        },


        animation: {
          ...OEE_CHART_ANIM,
        },

      },

    }
  );

}



// ?? Complete Loss ? A1 to A27 ???????????????????????????????????????????????

function renderCompleteLossChart(
  data
) {

  destroyOeeChart(
    'complete-loss'
  );


  const rows =
    data.data || [];


  const canvas =
    document.getElementById(
      'chart-complete-loss'
    );


  if (!canvas) return;


  const values =
    rows.map(
      row =>
        Number(
          row.loss_hours || 0
        )
    );


  const maxValue =
    Math.max(
      ...values,
      0
    );


  const colors =
    values.map(
      value => {

        if (!maxValue) {
          return 'rgba(26,86,219,0.72)';
        }


        const ratio =
          value / maxValue;


        if (ratio >= 0.70) {
          return 'rgba(220,38,38,0.82)';
        }


        if (ratio >= 0.40) {
          return 'rgba(245,158,11,0.82)';
        }


        return 'rgba(26,86,219,0.76)';

      }
    );


  oeeCharts[
    'complete-loss'
  ] = new Chart(
    canvas,
    {

      type: 'bar',


      data: {

        labels:
          rows.map(
            row =>
              (
                `${row.loss_code} ? `
                +
                `${row.loss_name || ''}`
              )
          ),


        datasets: [

          {

            label:
              'Loss Hours',

            data:
              values,

            backgroundColor:
              colors,

            borderRadius:
              6,

            borderSkipped:
              false,

          },

        ],

      },


      options: {

        indexAxis:
          'y',

        responsive:
          true,

        maintainAspectRatio:
          false,


        plugins: {

          legend: {
            display: false,
          },


          tooltip: {

            callbacks: {

              title:
                items => {

                  const index =
                    items[0]
                      ?.dataIndex;


                  const row =
                    rows[index];


                  if (!row) {
                    return '';
                  }


                  return (
                    `${row.loss_code} ? `
                    +
                    `${row.loss_name || ''}`
                  );

                },


              label:
                context => {

                  const row =
                    rows[
                      context.dataIndex
                    ];


                  return [

                    ` Loss Hours: ${
                      Number(
                        row.loss_hours || 0
                      ).toFixed(2)
                    }`,

                    ` Events: ${
                      Number(
                        row.events || 0
                      )
                    }`,

                    ` Machines Affected: ${
                      Number(
                        row.machines_affected || 0
                      )
                    }`,

                    ` Top Machine: ${
                      row.top_machine || '?'
                    }`,

                    ` Top Shift: ${
                      row.top_shift || '?'
                    }`,

                  ];

                },

            },

          },

        },


        scales: {

          x: {

            beginAtZero:
              true,

            grid: {
              color: '#f3f4f6',
            },

            title: {
              display: true,
              text: 'Loss Hours',
            },

          },


          y: {

            grid: {
              display: false,
            },


            ticks: {

              autoSkip:
                false,


              callback:
                function(value) {

                  const label =
                    this.getLabelForValue(
                      value
                    );


                  return (
                    label.length > 48
                      ? label.slice(
                          0,
                          48
                        ) + '?'
                      : label
                  );

                },

            },

          },

        },


        animation: {

          ...OEE_CHART_ANIM,

          delay:
            context =>
              context.dataIndex
              * 20,

        },

      },

    }
  );

}



// ?? Machine OEE ? Top 10 ????????????????????????????????????????????????????

function renderMachineOeeChart(
  data
) {

  destroyOeeChart(
    'machine-oee'
  );


  const rows =
    data.top_oee || [];


  const canvas =
    document.getElementById(
      'chart-machine-oee'
    );


  const empty =
    document.getElementById(
      'machine-oee-empty'
    );


  if (
    !canvas
    ||
    !rows.length
  ) {

    if (canvas) {
      canvas.style.display = 'none';
    }

    if (empty) {
      empty.style.display = 'flex';
    }

    return;

  }


  canvas.style.display = '';

  if (empty) {
    empty.style.display = 'none';
  }


  oeeCharts[
    'machine-oee'
  ] = new Chart(
    canvas,
    {

      type:
        'bar',


      data: {

        labels:
          rows.map(
            row =>
              row.machine_no
          ),


        datasets: [

          {

            label:
              'OEE',

            data:
              rows.map(
                row =>
                  Number(
                    row.oee || 0
                  )
                  *
                  100
              ),

            backgroundColor:
              'rgba(26,86,219,0.82)',

            borderRadius:
              7,

            borderSkipped:
              false,

          },

        ],

      },


      options: {

        indexAxis:
          'y',

        responsive:
          true,

        maintainAspectRatio:
          false,


        plugins: {

          legend: {
            display: false,
          },


          tooltip: {

            callbacks: {

              title:
                items => {

                  const row =
                    rows[
                      items[0]
                        .dataIndex
                    ];


                  return (
                    `${row.machine_no}`
                    +
                    (
                      row.machine_name
                        ? ` ? ${row.machine_name}`
                        : ''
                    )
                  );

                },


              label:
                context =>
                  ` OEE: ${
                    Number(
                      context.raw || 0
                    ).toFixed(1)
                  }%`,

              afterLabel:
                context => {

                  const row =
                    rows[
                      context.dataIndex
                    ];


                  return [

                    `Availability: ${
                      (
                        Number(
                          row.availability || 0
                        )
                        *
                        100
                      ).toFixed(1)
                    }%`,

                    `Plan Achievement: ${
                      (
                        Number(
                          row.plan_achievement || 0
                        )
                        *
                        100
                      ).toFixed(1)
                    }%`,

                    `Quality: ${
                      (
                        Number(
                          row.quality || 0
                        )
                        *
                        100
                      ).toFixed(1)
                    }%`,

                  ];

                },

            },

          },

        },


        scales: {

          x: {

            beginAtZero:
              true,

            suggestedMax:
              100,

            ticks: {

              callback:
                value =>
                  value + '%',

            },

            grid: {
              color: '#f3f4f6',
            },

          },


          y: {
            grid: {
              display: false,
            },
          },

        },


        animation: {

          ...OEE_CHART_ANIM,

          delay:
            context =>
              context.dataIndex
              * 60,

        },

      },

    }
  );

}



// ?? Machine Loss ? Top 10 ???????????????????????????????????????????????????

function renderMachineLossChart(
  data
) {

  destroyOeeChart(
    'machine-loss'
  );


  const rows =
    data.top_loss || [];


  const canvas =
    document.getElementById(
      'chart-machine-loss'
    );


  const empty =
    document.getElementById(
      'machine-loss-empty'
    );


  if (
    !canvas
    ||
    !rows.length
  ) {

    if (canvas) {
      canvas.style.display = 'none';
    }

    if (empty) {
      empty.style.display = 'flex';
    }

    return;

  }


  canvas.style.display = '';

  if (empty) {
    empty.style.display = 'none';
  }


  const values =
    rows.map(
      row =>
        Number(
          row.total_loss_hours || 0
        )
    );


  const maxValue =
    Math.max(
      ...values,
      0
    );


  const colors =
    values.map(
      value => {

        if (!maxValue) {
          return 'rgba(220,38,38,0.72)';
        }


        const ratio =
          value / maxValue;


        if (ratio >= 0.70) {
          return 'rgba(220,38,38,0.82)';
        }


        if (ratio >= 0.40) {
          return 'rgba(245,158,11,0.82)';
        }


        return 'rgba(124,58,237,0.74)';

      }
    );


  oeeCharts[
    'machine-loss'
  ] = new Chart(
    canvas,
    {

      type:
        'bar',


      data: {

        labels:
          rows.map(
            row =>
              row.machine_no
          ),


        datasets: [

          {

            label:
              'Loss Hours',

            data:
              values,

            backgroundColor:
              colors,

            borderRadius:
              7,

            borderSkipped:
              false,

          },

        ],

      },


      options: {

        indexAxis:
          'y',

        responsive:
          true,

        maintainAspectRatio:
          false,


        plugins: {

          legend: {
            display: false,
          },


          tooltip: {

            callbacks: {

              title:
                items => {

                  const row =
                    rows[
                      items[0]
                        .dataIndex
                    ];


                  return (
                    `${row.machine_no}`
                    +
                    (
                      row.machine_name
                        ? ` ? ${row.machine_name}`
                        : ''
                    )
                  );

                },


              label:
                context =>
                  ` Loss Hours: ${
                    Number(
                      context.raw || 0
                    ).toFixed(2)
                  }`,

              afterLabel:
                context => {

                  const row =
                    rows[
                      context.dataIndex
                    ];


                  return [

                    `No-Operator Hours: ${
                      Number(
                        row.no_operator_hours || 0
                      ).toFixed(2)
                    }`,

                    `Actual Qty: ${
                      Number(
                        row.actual_qty || 0
                      ).toLocaleString('en-IN')
                    }`,

                    `Production Gap: ${
                      Number(
                        row.production_gap || 0
                      ).toFixed(1)
                    }`,

                  ];

                },

            },

          },

        },


        scales: {

          x: {

            beginAtZero:
              true,

            grid: {
              color: '#f3f4f6',
            },

            title: {
              display: true,
              text: 'Loss Hours',
            },

          },


          y: {
            grid: {
              display: false,
            },
          },

        },


        animation: {

          ...OEE_CHART_ANIM,

          delay:
            context =>
              context.dataIndex
              * 60,

        },

      },

    }
  );

}


// ?? Main Load ????????????????????????????????????????????????????????????????

async function loadAll() {

  Object.keys(
    oeeCharts
  ).forEach(
    destroyOeeChart
  );


  document
    .querySelectorAll(
      '.kpi-card, .chart-card'
    )
    .forEach(
      el =>
        el.classList.remove(
          'visible'
        )
    );


  try {

    const params =
      oeeDateParams();


    const suffix =
      params
        ? `?${params}`
        : '';


    const [
      overviewResponse,
      lossResponse,
      machineResponse
    ] = await Promise.all([

      fetch(
        `/api/oee-dashboard/overview${suffix}`
      ),

      fetch(
        `/api/oee-dashboard/losses${suffix}`
      ),

      fetch(
        `/api/oee-dashboard/machines${suffix}`
      ),

    ]);


    const [
      overviewData,
      lossData,
      machineData
    ] = await Promise.all([

      overviewResponse.json(),

      lossResponse.json(),

      machineResponse.json(),

    ]);


    if (
      !overviewResponse.ok
      ||
      !overviewData.success
    ) {

      throw new Error(
        overviewData.error
        ||
        'Unable to load OEE Overview.'
      );

    }


    if (
      !lossResponse.ok
      ||
      !lossData.success
    ) {

      throw new Error(
        lossData.error
        ||
        'Unable to load Complete Loss Analysis.'
      );

    }


    if (
      !machineResponse.ok
      ||
      !machineData.success
    ) {

      throw new Error(
        machineData.error
        ||
        'Unable to load Machine OEE Scorecard.'
      );

    }


    renderOeePeriod(
      overviewData
    );


    renderOeeKpis(
      overviewData
    );


    renderDailyOeeChart(
      overviewData
    );


    renderShiftPerformanceChart(
      overviewData
    );


    renderShiftSummaryChart(
      overviewData
    );


    renderPlanVsActualChart(
      overviewData
    );


    renderCompleteLossChart(
      lossData
    );


    renderMachineOeeChart(
      machineData
    );


    renderMachineLossChart(
      machineData
    );


    revealOeeCards();

  }

  catch (error) {

    console.error(
      'OEE Dashboard error:',
      error
    );


    const period =
      document.getElementById(
        'oee-period-label'
      );


    if (period) {

      period.textContent =
        error.message;

      period.style.color =
        '#dc2626';

    }

  }

}


// Explicitly expose this because base.html calls loadAll()
// when the global sidebar date filter changes.
window.loadAll =
  loadAll;


document.addEventListener(
  'DOMContentLoaded',
  loadAll
);
