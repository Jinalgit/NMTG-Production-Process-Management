<script setup>
import {
    computed,
    onBeforeUnmount,
    onMounted,
    reactive,
    ref,
    watch
} from "vue";

import Button from "primevue/button";
import Drawer from "primevue/drawer";
import InputText from "primevue/inputtext";
import Message from "primevue/message";
import MultiSelect from "primevue/multiselect";
import Select from "primevue/select";
import Tag from "primevue/tag";

import EChart from "./EChart.vue";


const bootstrap = window.NMTG_ANALYTICS || {};

const isAdmin =
    String(bootstrap.role || "")
        .trim()
        .toLowerCase() === "admin";


const previousGlobalLoadData =
    window.loadData;


/* ============================================================
   GENERAL
============================================================ */

const activeTab = ref("dashboard");

const loading = ref(false);

const errorMessage = ref("");

const lastUpdated = ref("");


const darkMode = ref(
    document.documentElement
        .classList
        .contains("jms-dark-theme")
);


let themeObserver = null;


/* ============================================================
   DATE FILTER
============================================================ */

const sidebarDate = ref(
    localStorage.getItem("jms_filter_date") || ""
);


const fromDate = ref("");
const toDate = ref("");


function isoDate(date) {

    const y = date.getFullYear();

    const m = String(
        date.getMonth() + 1
    ).padStart(2, "0");

    const d = String(
        date.getDate()
    ).padStart(2, "0");


    return `${y}-${m}-${d}`;
}


function initialiseDates() {

    const today = new Date();

    const start = new Date();

    start.setDate(
        today.getDate() - 30
    );


    fromDate.value = isoDate(start);

    toDate.value = isoDate(today);
}


function syncSidebarDate() {

    sidebarDate.value =
        localStorage.getItem(
            "jms_filter_date"
        ) || "";
}


const effectiveFrom = computed(
    () =>
        sidebarDate.value ||
        fromDate.value
);


const effectiveTo = computed(
    () =>
        sidebarDate.value ||
        toDate.value
);


function dateQuery() {

    const params =
        new URLSearchParams();


    if (effectiveFrom.value) {

        params.set(
            "from_date",
            effectiveFrom.value
        );
    }


    if (effectiveTo.value) {

        params.set(
            "to_date",
            effectiveTo.value
        );
    }


    const query =
        params.toString();


    return query
        ? `?${query}`
        : "";
}


/* ============================================================
   HTTP
============================================================ */

async function api(
    url,
    options = {}
) {

    const response = await fetch(
        url,
        {
            credentials: "same-origin",
            ...options
        }
    );


    let data;


    try {

        data = await response.json();
    }
    catch {

        throw new Error(
            "Server returned invalid JSON."
        );
    }


    if (
        !response.ok ||
        data.success === false
    ) {

        throw new Error(
            data.error ||
            `Request failed (${response.status}).`
        );
    }


    return data;
}


/* ============================================================
   KPI COUNT-UP
============================================================ */

const summaryTarget = ref({
    total_job_cards: 0,
    active_job_cards: 0,
    completed_this_month: 0,
    overdue_job_cards: 0,
    stages_completed: 0
});


const summaryDisplay = reactive({
    total_job_cards: 0,
    active_job_cards: 0,
    completed_this_month: 0,
    overdue_job_cards: 0,
    stages_completed: 0
});


let kpiFrame = null;


function animateSummary(target) {

    if (kpiFrame) {

        cancelAnimationFrame(
            kpiFrame
        );
    }


    const fields = [
        "total_job_cards",
        "active_job_cards",
        "completed_this_month",
        "overdue_job_cards",
        "stages_completed"
    ];


    const startValues = {};
    const endValues = {};


    for (const field of fields) {

        startValues[field] =
            Number(
                summaryDisplay[field] || 0
            );


        endValues[field] =
            Number(
                target[field] || 0
            );
    }


    const started =
        performance.now();


    const duration = 750;


    function frame(now) {

        const progress =
            Math.min(
                1,
                (now - started) /
                duration
            );


        const eased =
            1 -
            Math.pow(
                1 - progress,
                3
            );


        for (const field of fields) {

            summaryDisplay[field] =
                Math.round(
                    startValues[field] +
                    (
                        endValues[field] -
                        startValues[field]
                    ) *
                    eased
                );
        }


        if (progress < 1) {

            kpiFrame =
                requestAnimationFrame(
                    frame
                );
        }
    }


    kpiFrame =
        requestAnimationFrame(
            frame
        );
}


/* ============================================================
   DASHBOARD DATA
============================================================ */

const wipRows = ref([]);

const dailyRows = ref([]);

const dailySummary = ref({
    total_stages: 0,
    total_job_cards: 0,
    active_supervisors: 0
});

const delayRows = ref([]);

const overdueRows = ref([]);

const supervisorRows = ref([]);


const otd = ref({
    total: 0,
    on_time: 0,
    delayed: 0,
    otd_pct: 0
});


async function loadSummary() {

    const data =
        await api(
            "/api/analytics/summary" +
            dateQuery()
        );


    summaryTarget.value = {
        ...summaryTarget.value,
        ...data
    };


    animateSummary(
        summaryTarget.value
    );
}


async function loadWip() {

    const data =
        await api(
            "/api/analytics/wip_flow" +
            dateQuery()
        );


    wipRows.value =
        Array.isArray(data.data)
            ? data.data
            : [];
}


async function loadDaily() {

    if (sidebarDate.value) {

        const data =
            await api(
                "/api/analytics/daily_breakdown?date=" +
                encodeURIComponent(
                    sidebarDate.value
                )
            );


        dailyRows.value =
            Array.isArray(data.data)
                ? data.data
                : [];


        dailySummary.value = {
            total_stages:
                Number(
                    data.summary?.total_stages ||
                    0
                ),

            total_job_cards:
                Number(
                    data.summary?.total_job_cards ||
                    0
                ),

            active_supervisors:
                Number(
                    data.summary?.active_supervisors ||
                    0
                )
        };


        return;
    }


    const data =
        await api(
            "/api/analytics/daily_activity" +
            dateQuery()
        );


    dailyRows.value =
        Array.isArray(data.data)
            ? data.data
            : [];
}


async function loadDelays() {

    const data =
        await api(
            "/api/analytics/process_delays" +
            dateQuery()
        );


    delayRows.value =
        Array.isArray(data.data)
            ? data.data
            : [];
}


async function loadOverdue() {

    const data =
        await api(
            "/api/analytics/overdue_jobs" +
            dateQuery()
        );


    overdueRows.value =
        Array.isArray(data.data)
            ? data.data
            : [];
}


async function loadOtd() {

    const data =
        await api(
            "/api/analytics/otd" +
            dateQuery()
        );


    otd.value = {
        total:
            Number(
                data.overall?.total ||
                0
            ),

        on_time:
            Number(
                data.overall?.on_time ||
                0
            ),

        delayed:
            Number(
                data.overall?.delayed ||
                0
            ),

        otd_pct:
            Number(
                data.overall?.otd_pct ||
                0
            )
    };
}


async function loadSupervisors() {

    if (!isAdmin) {
        return;
    }


    const data =
        await api(
            "/api/analytics/supervisor_stages" +
            dateQuery()
        );


    supervisorRows.value =
        Array.isArray(data.data)
            ? data.data
            : [];
}


let refreshId = 0;


async function refreshDashboard(
    {
        silent = false
    } = {}
) {

    const id = ++refreshId;


    if (!silent) {
        loading.value = true;
    }


    errorMessage.value = "";


    const results =
        await Promise.allSettled([
            loadSummary(),
            loadWip(),
            loadDaily(),
            loadDelays(),
            loadOverdue(),
            loadOtd(),
            loadSupervisors()
        ]);


    if (id !== refreshId) {
        return;
    }


    const failed =
        results.find(
            row =>
                row.status === "rejected"
        );


    if (failed) {

        console.error(
            failed.reason
        );


        errorMessage.value =
            failed.reason?.message ||
            "Some Analytics data could not be loaded.";
    }


    lastUpdated.value =
        new Date()
            .toLocaleTimeString(
                "en-IN",
                {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit"
                }
            );


    if (!silent) {
        loading.value = false;
    }
}


/* ============================================================
   FORMAT
============================================================ */

function shortDate(value) {

    if (!value) {
        return "";
    }


    const match =
        String(value).match(
            /^(\d{4})-(\d{2})-(\d{2})/
        );


    if (!match) {
        return String(value);
    }


    return new Date(
        Number(match[1]),
        Number(match[2]) - 1,
        Number(match[3])
    ).toLocaleDateString(
        "en-IN",
        {
            day: "2-digit",
            month: "short"
        }
    );
}


function fullDate(value) {

    if (!value) {
        return "—";
    }


    const match =
        String(value).match(
            /^(\d{4})-(\d{2})-(\d{2})/
        );


    if (!match) {
        return String(value);
    }


    return new Date(
        Number(match[1]),
        Number(match[2]) - 1,
        Number(match[3])
    ).toLocaleDateString(
        "en-IN",
        {
            day: "2-digit",
            month: "short",
            year: "numeric"
        }
    );
}


/* ============================================================
   ECHART THEME
============================================================ */

const chartText = computed(
    () =>
        darkMode.value
            ? "#c8d0d7"
            : "#56616c"
);


const chartGrid = computed(
    () =>
        darkMode.value
            ? "#2d3842"
            : "#edf0f3"
);


const chartMuted = computed(
    () =>
        darkMode.value
            ? "#89949e"
            : "#8f99a2"
);


const chartSurface = computed(
    () =>
        darkMode.value
            ? "#171e25"
            : "#ffffff"
);


/* ============================================================
   MARKET STYLE COMMON OPTIONS
============================================================ */

function toolbox({
    zoom = true,
    magic = true
} = {}) {

    const feature = {};


    if (zoom) {

        feature.dataZoom = {
            yAxisIndex: "none"
        };
    }


    if (magic) {

        feature.magicType = {
            type: [
                "line",
                "bar",
                "stack"
            ]
        };
    }


    feature.dataView = {
        readOnly: true
    };

    feature.restore = {};

    feature.saveAsImage = {
        pixelRatio: 2
    };


    return {
        right: 10,
        top: 5,
        itemSize: 14,

        iconStyle: {
            borderColor:
                chartMuted.value
        },

        emphasis: {
            iconStyle: {
                borderColor:
                    "#0288f7"
            }
        },

        feature
    };
}


function zoomOptions(length) {

    if (length <= 12) {
        return [];
    }


    const start =
        Math.max(
            0,
            100 -
            (
                12 /
                length
            ) *
            100
        );


    return [
        {
            type: "inside",
            start,
            end: 100,
            zoomOnMouseWheel: true,
            moveOnMouseMove: true
        },

        {
            type: "slider",
            start,
            end: 100,
            height: 18,
            bottom: 5,
            borderColor:
                chartGrid.value,

            fillerColor:
                darkMode.value
                    ? "rgba(2,136,247,.24)"
                    : "rgba(2,136,247,.14)",

            textStyle: {
                color:
                    chartMuted.value
            }
        }
    ];
}


function cartesian(
    labels,
    {
        horizontal = false,
        magic = true
    } = {}
) {

    const zoom =
        zoomOptions(
            labels.length
        );


    return {
        animation: true,

        animationDuration:
            900,

        animationEasing:
            "cubicOut",

        animationDurationUpdate:
            700,

        animationEasingUpdate:
            "cubicInOut",

        tooltip: {
            trigger: "axis",
            confine: true,

            axisPointer: {
                type: "cross",

                lineStyle: {
                    color: "#0288f7",
                    type: "dashed"
                },

                crossStyle: {
                    color: "#0288f7"
                },

                label: {
                    backgroundColor:
                        "#344454"
                }
            }
        },

        toolbox:
            toolbox({
                zoom: true,
                magic
            }),

        dataZoom:
            zoom,

        grid: {
            left:
                horizontal
                    ? 145
                    : 50,

            right: 28,
            top: 47,

            bottom:
                zoom.length
                    ? 64
                    : 35
        },

        xAxis:
            horizontal
                ? {
                    type: "value",

                    axisLabel: {
                        color:
                            chartText.value
                    },

                    splitLine: {
                        lineStyle: {
                            color:
                                chartGrid.value
                        }
                    }
                }

                : {
                    type: "category",
                    data: labels,

                    axisLabel: {
                        color:
                            chartText.value,

                        hideOverlap: true
                    },

                    axisLine: {
                        lineStyle: {
                            color:
                                chartGrid.value
                        }
                    }
                },

        yAxis:
            horizontal
                ? {
                    type: "category",
                    data: labels,
                    inverse: true,

                    axisLabel: {
                        color:
                            chartText.value
                    }
                }

                : {
                    type: "value",

                    axisLabel: {
                        color:
                            chartText.value
                    },

                    splitLine: {
                        lineStyle: {
                            color:
                                chartGrid.value
                        }
                    }
                }
    };
}


/* ============================================================
   FIXED CHARTS
============================================================ */

const wipOption = computed(
    () => {

        const labels =
            wipRows.value.map(
                row =>
                    row.wip_status ||
                    "Unknown"
            );


        const option =
            cartesian(labels);


        option.series = [
            {
                id: "wip",
                name: "Job Cards",
                type: "bar",
                realtimeSort: true,
                universalTransition: true,
                barMaxWidth: 36,

                itemStyle: {
                    borderRadius:
                        [5, 5, 0, 0]
                },

                data:
                    wipRows.value.map(
                        row =>
                            Number(
                                row.count || 0
                            )
                    )
            }
        ];


        return option;
    }
);


const dailyOption = computed(
    () => {

        const oneDay =
            Boolean(
                sidebarDate.value
            );


        const labels =
            oneDay

                ? dailyRows.value.map(
                    row =>
                        row.process_name ||
                        "Unknown"
                )

                : dailyRows.value.map(
                    row =>
                        shortDate(
                            row.activity_date
                        )
                );


        const values =
            oneDay

                ? dailyRows.value.map(
                    row =>
                        Number(
                            row.completions || 0
                        )
                )

                : dailyRows.value.map(
                    row =>
                        Number(
                            row.stages_completed || 0
                        )
                );


        const option =
            cartesian(
                labels,
                {
                    horizontal:
                        oneDay,

                    magic:
                        !oneDay
                }
            );


        if (oneDay) {

            option.series = [
                {
                    id:
                        "daily-process",

                    name:
                        "Stages Completed",

                    type:
                        "bar",

                    universalTransition:
                        true,

                    barMaxWidth:
                        24,

                    itemStyle: {
                        borderRadius:
                            [0, 5, 5, 0]
                    },

                    data:
                        values
                }
            ];


            return option;
        }


        option.xAxis.boundaryGap =
            false;


        option.series = [
            {
                id:
                    "daily",

                name:
                    "Stages Completed",

                type:
                    "line",

                smooth:
                    0.25,

                universalTransition:
                    true,

                showSymbol:
                    true,

                symbolSize:
                    6,

                lineStyle: {
                    width: 3
                },

                areaStyle: {
                    opacity: 0.10
                },

                data:
                    values
            }
        ];


        if (
            labels.length &&
            values.length
        ) {

            option.series.push(
                {
                    id:
                        "daily-latest",

                    name:
                        "Latest",

                    type:
                        "effectScatter",

                    symbolSize:
                        10,

                    rippleEffect: {
                        scale: 3.5,
                        brushType: "stroke"
                    },

                    tooltip: {
                        show: false
                    },

                    data: [
                        [
                            labels[
                                labels.length - 1
                            ],

                            values[
                                values.length - 1
                            ]
                        ]
                    ],

                    z: 20
                }
            );
        }


        return option;
    }
);


const delayOption = computed(
    () => {

        const labels =
            delayRows.value.map(
                row =>
                    row.process_name ||
                    "Unknown"
            );


        const option =
            cartesian(labels);


        option.legend = {
            type: "scroll",
            top: 8,
            left: 8,
            right: 180,

            textStyle: {
                color:
                    chartText.value
            }
        };


        option.series = [
            {
                id: "planned",
                name: "Planned Avg. Days",
                type: "bar",
                universalTransition: true,
                barMaxWidth: 28,

                data:
                    delayRows.value.map(
                        row =>
                            Number(
                                row.avg_planned ||
                                0
                            )
                    )
            },

            {
                id: "actual",
                name: "Actual Avg. Days",
                type: "bar",
                universalTransition: true,
                barMaxWidth: 28,

                data:
                    delayRows.value.map(
                        row =>
                            Number(
                                row.avg_actual ||
                                0
                            )
                    )
            }
        ];


        return option;
    }
);


const topOverdue = computed(
    () =>
        overdueRows.value.slice(
            0,
            15
        )
);


const overdueOption = computed(
    () => {

        const labels =
            topOverdue.value.map(
                row =>
                    row.job_card_no
            );


        const option =
            cartesian(
                labels,
                {
                    horizontal: true,
                    magic: false
                }
            );


        option.series = [
            {
                id: "overdue",
                name: "Days Overdue",
                type: "bar",
                universalTransition: true,
                barMaxWidth: 23,

                data:
                    topOverdue.value.map(
                        row => ({
                            value:
                                Number(
                                    row.days_overdue ||
                                    0
                                ),

                            itemStyle: {
                                color:
                                    Number(
                                        row.days_overdue ||
                                        0
                                    ) > 7
                                        ? "#d64b4b"
                                        : "#d18724",

                                borderRadius:
                                    [0, 5, 5, 0]
                            }
                        })
                    )
            }
        ];


        return option;
    }
);


const otdOption = computed(
    () => ({
        animation: true,

        animationDuration:
            950,

        animationDurationUpdate:
            700,

        tooltip: {
            trigger: "item",
            formatter:
                "{b}<br/><b>{c}</b> ({d}%)"
        },

        toolbox:
            toolbox({
                zoom: false,
                magic: false
            }),

        legend: {
            bottom: 5,

            textStyle: {
                color:
                    chartText.value
            }
        },

        series: [
            {
                id: "otd",
                name: "OTD",
                type: "pie",

                radius:
                    ["54%", "76%"],

                center:
                    ["50%", "46%"],

                universalTransition:
                    true,

                padAngle: 3,

                itemStyle: {
                    borderRadius: 7,

                    borderColor:
                        chartSurface.value,

                    borderWidth: 2
                },

                data: [
                    {
                        name: "On Time",

                        value:
                            otd.value.on_time,

                        itemStyle: {
                            color: "#229d5b"
                        }
                    },

                    {
                        name: "Delayed",

                        value:
                            otd.value.delayed,

                        itemStyle: {
                            color: "#d64b4b"
                        }
                    }
                ]
            }
        ]
    })
);


const supervisorOption = computed(
    () => {

        const labels =
            supervisorRows.value.map(
                row =>
                    row.supervisor
            );


        const option =
            cartesian(labels);


        option.legend = {
            type: "scroll",
            top: 8,
            left: 8,
            right: 180,

            textStyle: {
                color:
                    chartText.value
            }
        };


        option.series = [
            {
                id:
                    "supervisor-stages",

                name:
                    "Stages Completed",

                type:
                    "bar",

                universalTransition:
                    true,

                data:
                    supervisorRows.value.map(
                        row =>
                            Number(
                                row.stages_completed ||
                                0
                            )
                    )
            },

            {
                id:
                    "supervisor-jc",

                name:
                    "Job Cards",

                type:
                    "bar",

                universalTransition:
                    true,

                data:
                    supervisorRows.value.map(
                        row =>
                            Number(
                                row.job_cards_handled ||
                                0
                            )
                    )
            }
        ];


        return option;
    }
);


/* ============================================================
   CHART CLICK INSIGHT
============================================================ */

const insightOpen = ref(false);


const insight = reactive({
    title: "",
    label: "",
    value: "",
    extra: ""
});


function showInsight(
    title,
    label,
    value,
    extra = ""
) {

    insight.title = title;

    insight.label = label;

    insight.value =
        String(value ?? "—");

    insight.extra = extra;

    insightOpen.value = true;
}


function wipClick(params) {

    showInsight(
        "WIP Flow",
        params.name,
        `${params.value} Job Card(s)`
    );
}


function overdueClick(params) {

    const row =
        topOverdue.value[
            params.dataIndex
        ];


    if (!row) {
        return;
    }


    showInsight(
        row.job_card_no,
        row.current_stage ||
        "Unknown Stage",
        `${row.days_overdue} days overdue`,
        row.customer_name || ""
    );
}


/* ============================================================
   ANALYTICS STUDIO
============================================================ */

const studioMeta = ref({
    datasets: [],
    chart_types: []
});


const builderOpen = ref(false);

const builderLoading = ref(false);


const builder = reactive({
    title: "",
    dataset: "",
    dimension: "",
    measures: [],
    split_by: "",
    chart_type: "bar",
    limit: 40,

    filters: [
        {
            dimension: "",
            value: ""
        },

        {
            dimension: "",
            value: ""
        }
    ]
});


async function loadStudioMeta() {

    const data =
        await api(
            "/api/analytics/studio/meta"
        );


    studioMeta.value = {
        datasets:
            Array.isArray(
                data.datasets
            )
                ? data.datasets
                : [],

        chart_types:
            Array.isArray(
                data.chart_types
            )
                ? data.chart_types
                : []
    };


    if (
        !builder.dataset &&
        studioMeta.value.datasets.length
    ) {

        builder.dataset =
            studioMeta.value
                .datasets[0]
                .key;
    }
}


const selectedDataset = computed(
    () =>
        studioMeta.value
            .datasets
            .find(
                row =>
                    row.key ===
                    builder.dataset
            ) || null
);


const builderDimensions = computed(
    () =>
        selectedDataset.value
            ?.dimensions || []
);


const builderMeasures = computed(
    () =>
        selectedDataset.value
            ?.measures || []
);


const splitOptions = computed(
    () => [
        {
            key: "",
            label: "No Split"
        },

        ...builderDimensions.value.filter(
            row =>
                row.key !==
                builder.dimension
        )
    ]
);


watch(
    () => builder.dataset,
    () => {

        const dataset =
            selectedDataset.value;


        if (!dataset) {
            return;
        }


        builder.dimension =
            dataset.dimensions[0]?.key ||
            "";


        builder.measures =
            dataset.measures[0]
                ? [
                    dataset.measures[0].key
                ]
                : [];


        builder.split_by = "";
    }
);


watch(
    () => builder.dimension,
    () => {

        if (
            builder.split_by ===
            builder.dimension
        ) {

            builder.split_by = "";
        }
    }
);


watch(
    () => builder.chart_type,
    value => {

        if (value === "pie") {
            builder.split_by = "";
        }
    }
);


function openBuilder() {

    errorMessage.value = "";

    builderOpen.value = true;
}


/* ============================================================
   SAVED STUDIO CHARTS
============================================================ */

const STORAGE_KEY =
    "jms_analytics_studio_v4";


function loadStoredCharts() {

    try {

        const rows =
            JSON.parse(
                localStorage.getItem(
                    STORAGE_KEY
                ) || "[]"
            );


        if (!Array.isArray(rows)) {
            return [];
        }


        return rows
            .slice(0, 12)
            .map(
                row => ({
                    id: row.id,

                    title:
                        row.title ||
                        "Custom Analysis",

                    chartType:
                        row.chartType ||
                        "bar",

                    config:
                        row.config || {},

                    result: null,
                    error: "",
                    loading: false
                })
            );
    }
    catch {

        return [];
    }
}


const studioCharts =
    ref(
        loadStoredCharts()
    );


function saveStudioCharts() {

    localStorage.setItem(
        STORAGE_KEY,

        JSON.stringify(
            studioCharts.value.map(
                chart => ({
                    id: chart.id,
                    title: chart.title,
                    chartType:
                        chart.chartType,
                    config:
                        chart.config
                })
            )
        )
    );
}


/* ============================================================
   STUDIO QUERY
============================================================ */

async function runStudioChart(
    chart,
    {
        silent = false
    } = {}
) {

    if (!silent) {
        chart.loading = true;
    }


    chart.error = "";


    try {

        chart.result =
            await api(
                "/api/analytics/studio/query",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            ...chart.config,

                            from_date:
                                effectiveFrom.value,

                            to_date:
                                effectiveTo.value
                        })
                }
            );
    }
    catch (error) {

        chart.error =
            error.message ||
            "Analysis failed.";
    }
    finally {

        chart.loading = false;
    }
}


async function refreshStudioCharts({
    silent = false
} = {}) {

    await Promise.all(
        studioCharts.value.map(
            chart =>
                runStudioChart(
                    chart,
                    {
                        silent
                    }
                )
        )
    );
}


async function generateAnalysis() {

    errorMessage.value = "";


    if (!builder.dataset) {

        errorMessage.value =
            "Select Data Source.";

        return;
    }


    if (!builder.dimension) {

        errorMessage.value =
            "Select Compare By.";

        return;
    }


    if (!builder.measures.length) {

        errorMessage.value =
            "Select at least one Value.";

        return;
    }


    const measures =
        builder.measures.slice(
            0,
            4
        );


    const dimensionDefinition =
        builderDimensions.value.find(
            row =>
                row.key ===
                builder.dimension
        );


    const measureDefinitions =
        builderMeasures.value.filter(
            row =>
                measures.includes(
                    row.key
                )
        );


    const title =
        builder.title.trim() ||
        (
            measureDefinitions
                .map(
                    row =>
                        row.label
                )
                .join(" + ")
            +
            " by "
            +
            (
                dimensionDefinition?.label ||
                builder.dimension
            )
        );


    const chart = {
        id: Date.now(),

        title,

        chartType:
            builder.chart_type,

        loading: true,

        result: null,

        error: "",

        config: {
            dataset:
                builder.dataset,

            dimension:
                builder.dimension,

            measures,

            split_by:
                builder.chart_type ===
                "pie"
                    ? ""
                    : builder.split_by,

            limit:
                Number(
                    builder.limit || 40
                ),

            filters:
                builder.filters
                    .filter(
                        filter =>
                            filter.dimension &&
                            String(
                                filter.value || ""
                            ).trim()
                    )
                    .map(
                        filter => ({
                            dimension:
                                filter.dimension,

                            value:
                                String(
                                    filter.value
                                ).trim()
                        })
                    )
        }
    };


    builderLoading.value = true;


    studioCharts.value = [
        chart,
        ...studioCharts.value
    ].slice(
        0,
        12
    );


    await runStudioChart(chart);


    saveStudioCharts();


    builderLoading.value = false;

    builderOpen.value = false;

    activeTab.value = "studio";
}


function deleteChart(id) {

    studioCharts.value =
        studioCharts.value.filter(
            chart =>
                chart.id !== id
        );


    saveStudioCharts();
}


function chartTypeChanged(chart) {

    saveStudioCharts();
}


/* ============================================================
   CUSTOM CHART CONVERSION
============================================================ */

function unique(values) {

    return Array.from(
        new Set(values)
    );
}


function makeSeries(
    chart,
    name,
    data,
    index
) {

    if (
        chart.chartType === "line" ||
        chart.chartType === "area"
    ) {

        return {
            id:
                `s-${index}-${name}`,

            name,

            type: "line",

            smooth: 0.25,

            universalTransition: true,

            showSymbol: true,

            symbolSize: 6,

            lineStyle: {
                width: 2.5
            },

            areaStyle:
                chart.chartType === "area"
                    ? {
                        opacity: 0.12
                    }
                    : undefined,

            data
        };
    }


    return {
        id:
            `s-${index}-${name}`,

        name,

        type: "bar",

        stack:
            chart.chartType ===
            "stacked"
                ? "total"
                : undefined,

        universalTransition: true,

        barMaxWidth: 34,

        data
    };
}


function buildStudioOption(chart) {

    const result =
        chart.result;


    if (
        !result ||
        !Array.isArray(result.rows)
    ) {

        return {};
    }


    const rows =
        result.rows;


    const measures =
        Array.isArray(
            result.measures
        )
            ? result.measures
            : [];


    const labels =
        result.measure_labels || {};


    /* PIE */

    if (chart.chartType === "pie") {

        const measure =
            measures[0];


        const totals = {};


        for (const row of rows) {

            const category =
                String(
                    row.dimension ??
                    "Unknown"
                );


            totals[category] =
                Number(
                    totals[category] ||
                    0
                )
                +
                Number(
                    row[measure] ||
                    0
                );
        }


        return {
            animation: true,

            animationDuration:
                900,

            animationDurationUpdate:
                700,

            tooltip: {
                trigger: "item",
                formatter:
                    "{b}<br/><b>{c}</b> ({d}%)"
            },

            toolbox:
                toolbox({
                    zoom: false,
                    magic: false
                }),

            legend: {
                type: "scroll",
                bottom: 5,

                textStyle: {
                    color:
                        chartText.value
                }
            },

            series: [
                {
                    id:
                        `pie-${chart.id}`,

                    name:
                        labels[measure] ||
                        measure,

                    type:
                        "pie",

                    radius:
                        ["48%", "72%"],

                    universalTransition:
                        true,

                    itemStyle: {
                        borderColor:
                            chartSurface.value,

                        borderWidth: 2,

                        borderRadius: 6
                    },

                    data:
                        Object.entries(
                            totals
                        ).map(
                            ([name, value]) => ({
                                name,
                                value
                            })
                        )
                }
            ]
        };
    }


    /* CARTESIAN */

    const categories =
        unique(
            rows.map(
                row =>
                    String(
                        row.dimension ??
                        "Unknown"
                    )
            )
        );


    const option =
        cartesian(categories);


    option.legend = {
        type: "scroll",
        top: 8,
        left: 8,
        right: 180,

        textStyle: {
            color:
                chartText.value
        }
    };


    const series = [];

    let seriesIndex = 0;


    if (result.split_by) {

        const splitValues =
            unique(
                rows.map(
                    row =>
                        String(
                            row.split_value ??
                            "Unknown"
                        )
                )
            );


        for (const measure of measures) {

            for (const splitValue of splitValues) {

                const lookup = {};


                rows
                    .filter(
                        row =>
                            String(
                                row.split_value ??
                                "Unknown"
                            ) === splitValue
                    )
                    .forEach(
                        row => {

                            lookup[
                                String(
                                    row.dimension ??
                                    "Unknown"
                                )
                            ] =
                                Number(
                                    row[measure] ||
                                    0
                                );
                        }
                    );


                series.push(
                    makeSeries(
                        chart,

                        (
                            labels[measure] ||
                            measure
                        )
                        +
                        " · "
                        +
                        splitValue,

                        categories.map(
                            category =>
                                lookup[
                                    category
                                ] || 0
                        ),

                        seriesIndex++
                    )
                );
            }
        }
    }
    else {

        for (const measure of measures) {

            const lookup = {};


            for (const row of rows) {

                lookup[
                    String(
                        row.dimension ??
                        "Unknown"
                    )
                ] =
                    Number(
                        row[measure] ||
                        0
                    );
            }


            series.push(
                makeSeries(
                    chart,

                    labels[measure] ||
                    measure,

                    categories.map(
                        category =>
                            lookup[
                                category
                            ] || 0
                    ),

                    seriesIndex++
                )
            );
        }
    }


    option.series = series;


    return option;
}


function customClick(
    chart,
    params
) {

    showInsight(
        chart.title,

        params.seriesName ||
        params.name ||
        "Selection",

        Array.isArray(
            params.value
        )
            ? params.value.join(" / ")
            : params.value
    );
}


/* ============================================================
   LIVE REFRESH
============================================================ */

const LIVE_SECONDS = 30;

const liveMode = ref(false);

const liveCountdown =
    ref(LIVE_SECONDS);


let liveTimer = null;
let countdownTimer = null;


async function refreshEverything({
    silent = false
} = {}) {

    syncSidebarDate();


    await Promise.all([
        refreshDashboard({
            silent
        }),

        refreshStudioCharts({
            silent
        })
    ]);


    liveCountdown.value =
        LIVE_SECONDS;
}


async function liveRefresh() {

    if (document.hidden) {
        return;
    }


    await refreshEverything({
        silent: true
    });
}


function stopLive() {

    if (liveTimer) {

        clearInterval(liveTimer);

        liveTimer = null;
    }


    if (countdownTimer) {

        clearInterval(
            countdownTimer
        );

        countdownTimer = null;
    }
}


function startLive() {

    stopLive();


    liveCountdown.value =
        LIVE_SECONDS;


    liveTimer =
        setInterval(
            liveRefresh,
            LIVE_SECONDS * 1000
        );


    countdownTimer =
        setInterval(
            () => {

                liveCountdown.value -= 1;


                if (
                    liveCountdown.value <= 0
                ) {

                    liveCountdown.value =
                        LIVE_SECONDS;
                }
            },
            1000
        );
}


function toggleLive() {

    liveMode.value =
        !liveMode.value;


    if (liveMode.value) {

        startLive();

        liveRefresh();
    }
    else {

        stopLive();
    }
}


/* ============================================================
   GLOBAL DATE CHANGE
============================================================ */

function handleStorage(event) {

    if (
        event.key !==
        "jms_filter_date"
    ) {
        return;
    }


    sidebarDate.value =
        event.newValue || "";


    refreshEverything();
}


/* ============================================================
   MOUNT
============================================================ */

onMounted(
    async () => {

        initialiseDates();


        window.addEventListener(
            "storage",
            handleStorage
        );


        themeObserver =
            new MutationObserver(
                () => {

                    darkMode.value =
                        document.documentElement
                            .classList
                            .contains(
                                "jms-dark-theme"
                            );
                }
            );


        themeObserver.observe(
            document.documentElement,
            {
                attributes: true,
                attributeFilter: ["class"]
            }
        );


        window.loadData =
            refreshEverything;


        loading.value = true;


        try {

            await Promise.all([
                loadStudioMeta(),

                refreshDashboard({
                    silent: true
                })
            ]);


            if (
                studioCharts.value.length
            ) {

                await refreshStudioCharts({
                    silent: true
                });
            }
        }
        catch (error) {

            console.error(error);


            errorMessage.value =
                error.message ||
                "Analytics initialization failed.";
        }
        finally {

            loading.value = false;
        }
    }
);


onBeforeUnmount(
    () => {

        stopLive();


        if (kpiFrame) {
            cancelAnimationFrame(kpiFrame);
        }


        window.removeEventListener(
            "storage",
            handleStorage
        );


        if (themeObserver) {
            themeObserver.disconnect();
        }


        if (previousGlobalLoadData) {

            window.loadData =
                previousGlobalLoadData;
        }
        else {

            delete window.loadData;
        }
    }
);
</script>


<template>

    <main class="anx-page">


        <header class="anx-header">

            <div>

                <div class="anx-breadcrumb">

                    Reports

                    <i class="pi pi-angle-right"></i>

                    Analytics

                </div>


                <div class="anx-title-row">

                    <h1>Analytics</h1>


                    <Tag
                        value="Interactive Studio"
                        severity="info"
                        rounded
                    />


                    <span
                        v-if="liveMode"
                        class="anx-live"
                    >

                        <i></i>

                        LIVE

                    </span>

                </div>


                <p>
                    Production intelligence,
                    interactive comparisons and
                    live operational trends.
                </p>

            </div>


            <div class="anx-actions">

                <div
                    v-if="lastUpdated"
                    class="anx-updated"
                >
                    Updated
                    <strong>
                        {{ lastUpdated }}
                    </strong>
                </div>


                <Button
                    label="Create Analysis"
                    icon="pi pi-plus"
                    size="small"
                    @click="openBuilder"
                />


                <Button
                    :label="
                        liveMode
                            ? `Live · ${liveCountdown}s`
                            : 'Live'
                    "
                    :icon="
                        liveMode
                            ? 'pi pi-circle-fill'
                            : 'pi pi-play'
                    "
                    :severity="
                        liveMode
                            ? 'success'
                            : 'secondary'
                    "
                    :outlined="!liveMode"
                    size="small"
                    @click="toggleLive"
                />


                <Button
                    icon="pi pi-refresh"
                    severity="secondary"
                    outlined
                    size="small"
                    :loading="loading"
                    @click="refreshEverything()"
                />

            </div>

        </header>


        <nav class="anx-tabs">

            <button
                type="button"
                :class="{
                    active:
                        activeTab === 'dashboard'
                }"
                @click="
                    activeTab = 'dashboard'
                "
            >
                <i class="pi pi-chart-bar"></i>
                Dashboard
            </button>


            <button
                type="button"
                :class="{
                    active:
                        activeTab === 'studio'
                }"
                @click="
                    activeTab = 'studio'
                "
            >
                <i class="pi pi-sliders-h"></i>

                Analysis Studio

                <span
                    v-if="studioCharts.length"
                >
                    {{ studioCharts.length }}
                </span>

            </button>

        </nav>


        <section class="anx-datebar">

            <div
                v-if="sidebarDate"
                class="anx-sidebar-date"
            >
                <i class="pi pi-calendar"></i>

                Sidebar Date

                <strong>
                    {{ fullDate(sidebarDate) }}
                </strong>
            </div>


            <template v-else>

                <label>
                    <span>From</span>

                    <input
                        v-model="fromDate"
                        type="date"
                    />
                </label>


                <span>→</span>


                <label>
                    <span>To</span>

                    <input
                        v-model="toDate"
                        type="date"
                    />
                </label>


                <Button
                    label="Apply"
                    icon="pi pi-filter"
                    size="small"
                    @click="refreshEverything()"
                />

            </template>


            <small class="anx-live-help">

                <i class="pi pi-bolt"></i>

                Live mode updates charts without
                reloading the page.

            </small>

        </section>


        <Message
            v-if="errorMessage"
            severity="warn"
            :closable="false"
            class="anx-message"
        >
            {{ errorMessage }}
        </Message>


        <!-- ==================================================
             DASHBOARD
        =================================================== -->

        <template
            v-if="
                activeTab === 'dashboard'
            "
        >

            <section class="anx-kpis">

                <article>
                    <span>Total Job Cards</span>

                    <strong>
                        {{
                            summaryDisplay
                                .total_job_cards
                                .toLocaleString('en-IN')
                        }}
                    </strong>

                    <small>Selected period</small>
                </article>


                <article>
                    <span>Active Job Cards</span>

                    <strong>
                        {{
                            summaryDisplay
                                .active_job_cards
                                .toLocaleString('en-IN')
                        }}
                    </strong>

                    <small>Current WIP</small>
                </article>


                <article class="good">
                    <span>Completed</span>

                    <strong>
                        {{
                            summaryDisplay
                                .completed_this_month
                                .toLocaleString('en-IN')
                        }}
                    </strong>

                    <small>Production completed</small>
                </article>


                <article class="bad">
                    <span>Overdue</span>

                    <strong>
                        {{
                            summaryDisplay
                                .overdue_job_cards
                                .toLocaleString('en-IN')
                        }}
                    </strong>

                    <small>Delivery risk</small>
                </article>


                <article>
                    <span>Stage Completions</span>

                    <strong>
                        {{
                            summaryDisplay
                                .stages_completed
                                .toLocaleString('en-IN')
                        }}
                    </strong>

                    <small>Process movements</small>
                </article>

            </section>


            <section class="anx-grid-two">

                <article class="anx-card">

                    <div class="anx-card-head">

                        <div>
                            <h2>WIP Flow</h2>

                            <p>
                                Current production
                                distribution.
                            </p>
                        </div>

                    </div>


                    <EChart
                        :option="wipOption"
                        height="340px"
                        @chart-click="wipClick"
                    />

                </article>


                <article class="anx-card">

                    <div class="anx-card-head">

                        <div>
                            <h2>On Time Delivery</h2>

                            <p>
                                Store completion against
                                committed delivery.
                            </p>
                        </div>


                        <strong class="anx-score">
                            {{ otd.otd_pct }}%
                        </strong>

                    </div>


                    <EChart
                        :option="otdOption"
                        height="340px"
                    />

                </article>

            </section>


            <article class="anx-card anx-full">

                <div class="anx-card-head">

                    <div>
                        <h2>
                            {{
                                sidebarDate
                                    ? `Production on ${fullDate(sidebarDate)}`
                                    : 'Daily Production Activity'
                            }}
                        </h2>

                        <p>
                            Hover crosshair · mouse-wheel zoom ·
                            drag timeline · live animated updates.
                        </p>
                    </div>


                    <Tag
                        value="Interactive Timeline"
                        severity="info"
                        rounded
                    />

                </div>


                <EChart
                    :option="dailyOption"
                    height="400px"
                />

            </article>


            <article class="anx-card anx-full">

                <div class="anx-card-head">

                    <div>
                        <h2>
                            Process Delay Analysis
                        </h2>

                        <p>
                            Planned vs actual average days.
                        </p>
                    </div>

                </div>


                <EChart
                    :option="delayOption"
                    height="380px"
                />

            </article>


            <article class="anx-card anx-full">

                <div class="anx-card-head">

                    <div>
                        <h2>
                            Top Overdue Job Cards
                        </h2>

                        <p>
                            Click any bar to inspect it.
                        </p>
                    </div>


                    <Tag
                        :value="
                            `${overdueRows.length} overdue`
                        "
                        severity="danger"
                        rounded
                    />

                </div>


                <EChart
                    :option="overdueOption"
                    height="410px"
                    @chart-click="overdueClick"
                />

            </article>


            <article
                v-if="isAdmin"
                class="anx-card anx-full"
            >

                <div class="anx-card-head">

                    <div>
                        <h2>
                            Supervisor Performance
                        </h2>

                        <p>
                            Stage completions vs
                            Job Cards handled.
                        </p>
                    </div>

                </div>


                <EChart
                    :option="supervisorOption"
                    height="380px"
                />

            </article>

        </template>


        <!-- ==================================================
             ANALYSIS STUDIO
        =================================================== -->

        <template v-else>

            <section class="anx-studio-head">

                <div>
                    <h2>Analysis Studio</h2>

                    <p>
                        Build your own comparisons
                        without SQL.
                    </p>
                </div>


                <Button
                    label="Create Analysis"
                    icon="pi pi-plus"
                    @click="openBuilder"
                />

            </section>


            <section
                v-if="!studioCharts.length"
                class="anx-empty"
            >

                <i class="pi pi-chart-line"></i>

                <h2>
                    Build your first analysis
                </h2>

                <p>
                    Compare processes, customers,
                    WIP, material, supervisors,
                    quantities and timing metrics.
                </p>


                <Button
                    label="Create Analysis"
                    icon="pi pi-plus"
                    @click="openBuilder"
                />

            </section>


            <section
                v-else
                class="anx-custom-grid"
            >

                <article
                    v-for="chart in studioCharts"
                    :key="chart.id"
                    class="anx-card"
                >

                    <div class="anx-card-head">

                        <div>
                            <h2>{{ chart.title }}</h2>

                            <p v-if="chart.result">
                                {{
                                    chart.result
                                        .dataset_label
                                }}
                                ·
                                {{
                                    chart.result
                                        .dimension_label
                                }}

                                <template
                                    v-if="
                                        chart.result
                                            .split_label
                                    "
                                >
                                    · Split by
                                    {{
                                        chart.result
                                            .split_label
                                    }}
                                </template>
                            </p>
                        </div>


                        <div class="anx-chart-actions">

                            <Select
                                v-model="
                                    chart.chartType
                                "
                                :options="
                                    studioMeta
                                        .chart_types
                                "
                                optionLabel="label"
                                optionValue="key"
                                class="anx-type"
                                @change="
                                    chartTypeChanged(
                                        chart
                                    )
                                "
                            />


                            <Button
                                icon="pi pi-refresh"
                                severity="secondary"
                                text
                                rounded
                                :loading="
                                    chart.loading
                                "
                                @click="
                                    runStudioChart(
                                        chart
                                    )
                                "
                            />


                            <Button
                                icon="pi pi-trash"
                                severity="danger"
                                text
                                rounded
                                @click="
                                    deleteChart(
                                        chart.id
                                    )
                                "
                            />

                        </div>

                    </div>


                    <Message
                        v-if="chart.error"
                        severity="error"
                        :closable="false"
                    >
                        {{ chart.error }}
                    </Message>


                    <div
                        v-if="
                            chart.loading &&
                            !chart.result
                        "
                        class="anx-loading"
                    >
                        <i class="pi pi-spin pi-spinner"></i>
                        Generating...
                    </div>


                    <EChart
                        v-else-if="chart.result"
                        :option="
                            buildStudioOption(
                                chart
                            )
                        "
                        height="390px"
                        @chart-click="
                            customClick(
                                chart,
                                $event
                            )
                        "
                    />

                </article>

            </section>

        </template>


        <!-- ==================================================
             CREATE ANALYSIS
        =================================================== -->

        <Drawer
            v-model:visible="builderOpen"
            position="right"
            class="anx-builder"
        >

            <template #header>
                <div class="anx-drawer-title">
                    <span>Analytics Studio</span>
                    <strong>Create Analysis</strong>
                </div>
            </template>


            <div class="anx-builder-body">

                <label class="anx-field">
                    <span>Analysis Name</span>

                    <InputText
                        v-model="builder.title"
                        placeholder="Example: Planned vs Actual by Process"
                    />
                </label>


                <label class="anx-field">
                    <span>Data Source</span>

                    <Select
                        v-model="builder.dataset"
                        :options="
                            studioMeta.datasets
                        "
                        optionLabel="label"
                        optionValue="key"
                    />

                    <small
                        v-if="selectedDataset"
                    >
                        {{
                            selectedDataset.description
                        }}
                    </small>
                </label>


                <label class="anx-field">
                    <span>Compare By</span>

                    <Select
                        v-model="
                            builder.dimension
                        "
                        :options="
                            builderDimensions
                        "
                        optionLabel="label"
                        optionValue="key"
                    />
                </label>


                <label class="anx-field">
                    <span>Values</span>

                    <MultiSelect
                        v-model="
                            builder.measures
                        "
                        :options="
                            builderMeasures
                        "
                        optionLabel="label"
                        optionValue="key"
                        display="chip"
                        :maxSelectedLabels="4"
                        placeholder="Select up to 4 values"
                    />

                    <small>
                        Select multiple metrics for
                        direct comparison.
                    </small>
                </label>


                <label
                    v-if="
                        builder.chart_type !==
                        'pie'
                    "
                    class="anx-field"
                >
                    <span>Split By</span>

                    <Select
                        v-model="
                            builder.split_by
                        "
                        :options="
                            splitOptions
                        "
                        optionLabel="label"
                        optionValue="key"
                    />
                </label>


                <label class="anx-field">
                    <span>Chart Type</span>

                    <Select
                        v-model="
                            builder.chart_type
                        "
                        :options="
                            studioMeta.chart_types
                        "
                        optionLabel="label"
                        optionValue="key"
                    />
                </label>


                <section class="anx-filter-box">

                    <strong>
                        Optional Filters
                    </strong>


                    <div
                        v-for="
                            (filter, index)
                            in builder.filters
                        "
                        :key="index"
                        class="anx-filter-row"
                    >

                        <Select
                            v-model="
                                filter.dimension
                            "
                            :options="
                                builderDimensions
                            "
                            optionLabel="label"
                            optionValue="key"
                            placeholder="Field"
                        />


                        <InputText
                            v-model="
                                filter.value
                            "
                            placeholder="Contains..."
                        />

                    </div>

                </section>


                <label class="anx-field">
                    <span>Maximum Categories</span>

                    <Select
                        v-model="builder.limit"
                        :options="[
                            10,
                            20,
                            40,
                            75,
                            120
                        ]"
                    />
                </label>


                <div class="anx-range">

                    <span>Analysis Range</span>

                    <strong>
                        {{
                            fullDate(
                                effectiveFrom
                            )
                        }}
                        →
                        {{
                            fullDate(
                                effectiveTo
                            )
                        }}
                    </strong>

                </div>


                <Button
                    label="Generate Analysis"
                    icon="pi pi-chart-line"
                    size="large"
                    class="anx-generate"
                    :loading="builderLoading"
                    @click="generateAnalysis"
                />

            </div>

        </Drawer>


        <!-- ==================================================
             INSIGHT
        =================================================== -->

        <Drawer
            v-model:visible="insightOpen"
            position="right"
            class="anx-insight"
        >

            <template #header>
                <div class="anx-drawer-title">
                    <span>Chart Selection</span>
                    <strong>{{ insight.title }}</strong>
                </div>
            </template>


            <div class="anx-insight-content">

                <span>Selected</span>

                <h2>{{ insight.label }}</h2>

                <strong>{{ insight.value }}</strong>

                <p v-if="insight.extra">
                    {{ insight.extra }}
                </p>

            </div>

        </Drawer>

    </main>

</template>