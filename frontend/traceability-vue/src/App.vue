<script setup>
import {
    computed,
    nextTick,
    onMounted,
    ref,
    watch
} from "vue";

import Button from "primevue/button";
import Drawer from "primevue/drawer";
import Message from "primevue/message";


/* ============================================================
   STATE
============================================================ */

const searchText = ref("");

const loading = ref(false);

const error = ref("");

const data = ref(null);

const auditRows = ref([]);

const gateInfo = ref(null);

const selectedItemIndex = ref(0);

const stageDrawerOpen = ref(false);

const selectedStage = ref(null);

const ganttScroller = ref(null);


/* ============================================================
   PRIMARY DATA
============================================================ */

const jobCard =
    computed(
        () =>
            data.value?.job_card ||
            {}
    );


const items =
    computed(
        () =>
            Array.isArray(
                data.value?.items
            )
                ? data.value.items
                : []
    );


const currentItem =
    computed(
        () =>
            items.value[
                selectedItemIndex.value
            ] ||
            null
    );


/* ============================================================
   FORMATTERS
============================================================ */

function cleanText(
    value,
    fallback = "—"
) {

    const result =
        String(
            value ?? ""
        ).trim();


    if (
        !result ||
        result === "-"
    ) {
        return fallback;
    }


    return result;
}


function normalize(value) {

    return String(
        value ?? ""
    )
        .trim()
        .toLowerCase();
}


function numberValue(
    value,
    fallback = 0
) {

    const number =
        Number(value);


    return Number.isFinite(number)
        ? number
        : fallback;
}


function formatDate(value) {

    if (!value) {
        return "—";
    }


    const raw =
        String(value);


    const match =
        raw.match(
            /^(\d{4})-(\d{2})-(\d{2})/
        );


    if (!match) {
        return raw;
    }


    const date =
        new Date(
            Number(match[1]),
            Number(match[2]) - 1,
            Number(match[3])
        );


    return date.toLocaleDateString(
        "en-IN",
        {
            day: "2-digit",
            month: "short",
            year: "numeric"
        }
    );
}


function formatDateTime(value) {

    if (!value) {
        return "—";
    }


    const date =
        new Date(value);


    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return cleanText(value);
    }


    return date.toLocaleString(
        "en-IN",
        {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        }
    );
}


function elapsedDays(value) {

    if (!value) {
        return 0;
    }


    const date =
        new Date(value);


    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return 0;
    }


    return Math.max(
        0,
        Math.floor(
            (
                Date.now() -
                date.getTime()
            ) /
            86400000
        )
    );
}


function booleanValue(value) {

    if (
        value === true ||
        value === 1
    ) {
        return true;
    }


    const normalized =
        normalize(value);


    return (
        normalized === "1" ||
        normalized === "true" ||
        normalized === "yes"
    );
}


function hasRealVendor(value) {

    const vendor =
        normalize(value);


    return Boolean(
        vendor &&
        vendor !== "-" &&
        vendor !== "—" &&
        vendor !== "na" &&
        vendor !== "n/a" &&
        vendor !== "none"
    );
}


/* ============================================================
   HTTP
============================================================ */

async function fetchJson(url) {

    const response =
        await fetch(
            url,
            {
                credentials:
                    "same-origin"
            }
        );


    let payload;


    try {

        payload =
            await response.json();
    }
    catch {

        throw new Error(
            "Server returned an invalid response."
        );
    }


    if (
        !response.ok ||
        payload?.success === false
    ) {

        throw new Error(
            payload?.error ||
            `Request failed (${response.status})`
        );
    }


    return payload;
}


/* ============================================================
   LOAD SUPPORTING DATA
============================================================ */

async function loadAuditTrail(jcNo) {

    try {

        const payload =
            await fetchJson(
                "/api/audit_trail/" +
                encodeURIComponent(jcNo)
            );


        const rows =
            payload?.data ??
            payload?.rows ??
            payload?.audit_trail ??
            payload?.audit ??
            [];


        auditRows.value =
            Array.isArray(rows)
                ? rows
                : [];
    }
    catch {

        auditRows.value = [];
    }
}


async function loadGateInfo(jcNo) {

    try {

        gateInfo.value =
            await fetchJson(
                "/api/wip/check-c-child-gate/" +
                encodeURIComponent(jcNo)
            );
    }
    catch {

        gateInfo.value = null;
    }
}


/* ============================================================
   SEARCH
============================================================ */

async function searchJobCard() {

    const jcNo =
        searchText.value.trim();


    if (!jcNo) {

        error.value =
            "Enter a Job Card number.";

        return;
    }


    loading.value = true;

    error.value = "";

    data.value = null;

    auditRows.value = [];

    gateInfo.value = null;

    selectedItemIndex.value = 0;


    try {

        const payload =
            await fetchJson(
                "/api/quality_check/fetch/" +
                encodeURIComponent(jcNo)
            );


        data.value = payload;


        const actualJc =
            String(
                payload?.job_card
                    ?.job_card_no ||
                jcNo
            );


        const url =
            new URL(
                window.location.href
            );


        url.searchParams.set(
            "jc",
            actualJc
        );


        window.history.replaceState(
            {},
            "",
            url
        );


        await Promise.all([
            loadAuditTrail(actualJc),
            loadGateInfo(actualJc)
        ]);

        await scrollGanttToCurrent();
    }
    catch (err) {

        error.value =
            err?.message ||
            "Unable to load Job Card.";
    }
    finally {

        loading.value = false;
    }
}


/* ============================================================
   PROCESS TIMELINE
============================================================ */

function timelineForProcess(
    item,
    processName
) {

    const timeline =
        Array.isArray(
            item?.process_timeline
        )
            ? item.process_timeline
            : [];


    const target =
        normalize(processName);


    return (
        timeline.find(
            row =>
                normalize(
                    row?.process_name
                ) === target
        )
        ||
        null
    );
}


function baseStageState(
    item,
    processName,
    index,
    timeline
) {

    const timelineStatus =
        normalize(
            timeline?.status
        );


    if (
        timeline?.out_time ||
        timelineStatus === "completed" ||
        timelineStatus === "on time" ||
        timelineStatus === "delayed"
    ) {
        return "completed";
    }


    const currentWip =
        normalize(
            item?.wip_status
        );


    if (
        currentWip === "store" ||
        currentWip === "completed" ||
        currentWip === "complete"
    ) {
        return "completed";
    }


    const currentIndex =
        Number(
            item?.wip_process_index
        );


    if (
        Number.isInteger(currentIndex) &&
        currentIndex >= 0
    ) {

        if (index < currentIndex) {
            return "completed";
        }


        if (index === currentIndex) {
            return "current";
        }


        return "pending";
    }


    if (
        currentWip &&
        normalize(processName) ===
        currentWip
    ) {
        return "current";
    }


    return "pending";
}


function routeStages(item) {

    const processes =
        Array.isArray(
            item?.processes
        )
            ? item.processes
            : [];


    return processes.map(
        (
            processName,
            index
        ) => {

            const timeline =
                timelineForProcess(
                    item,
                    processName
                );


            const vendorName =
                cleanText(
                    timeline?.vendor_name,
                    ""
                );


            const isSubcontract =
                booleanValue(
                    timeline?.is_subcontract
                )
                ||
                hasRealVendor(
                    vendorName
                );


            const state =
                baseStageState(
                    item,
                    processName,
                    index,
                    timeline
                );


            const plannedDays =
                numberValue(
                    timeline?.lead_days
                );


            let actualDays =
                timeline?.actual_days;


            if (
                actualDays === null ||
                actualDays === undefined ||
                actualDays === ""
            ) {

                if (timeline?.in_time) {

                    actualDays =
                        state === "completed"
                            ? null
                            : elapsedDays(
                                timeline.in_time
                            );
                }
                else {

                    actualDays = null;
                }
            }


            if (
                actualDays !== null
            ) {

                actualDays =
                    numberValue(
                        actualDays
                    );
            }


            const delayed =
                actualDays !== null &&
                plannedDays > 0 &&
                actualDays > plannedDays;


            return {
                index,
                processName,
                timeline,
                state,
                plannedDays,
                actualDays,
                delayed,
                isSubcontract,
                vendorName:
                    vendorName ||
                    "Vendor not recorded",
                expectedDate:
                    timeline
                        ?.subcontract_expected_date ||
                    null
            };
        }
    );
}


const stages =
    computed(
        () =>
            currentItem.value
                ? routeStages(
                    currentItem.value
                )
                : []
    );


const completedCount =
    computed(
        () =>
            stages.value.filter(
                stage =>
                    stage.state ===
                    "completed"
            ).length
    );


const subcontractCount =
    computed(
        () =>
            stages.value.filter(
                stage =>
                    stage.isSubcontract
            ).length
    );


const progressPercent =
    computed(
        () => {

            if (!stages.value.length) {
                return 0;
            }


            return Math.round(
                (
                    completedCount.value /
                    stages.value.length
                ) *
                100
            );
        }
    );


const currentStage =
    computed(
        () =>
            stages.value.find(
                stage =>
                    stage.state ===
                    "current"
            )
            ||
            null
    );


/* ============================================================
   TRACEABILITY_MINI_GANTT_V3

   Status is PRIMARY:
   completed = green
   current   = blue
   pending   = neutral

   Subcontract is SECONDARY metadata only.
============================================================ */

const DAY_MS =
    24 * 60 * 60 * 1000;


function toTime(value) {

    if (!value) {
        return null;
    }


    const date =
        new Date(value);


    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return null;
    }


    return date.getTime();
}


function startOfDay(value) {

    const date =
        new Date(value);


    return new Date(
        date.getFullYear(),
        date.getMonth(),
        date.getDate()
    ).getTime();
}


function ganttTickLabel(ms) {

    return new Date(ms)
        .toLocaleDateString(
            "en-IN",
            {
                day:
                    "2-digit",

                month:
                    "short"
            }
        );
}


const ganttRange =
    computed(
        () => {

            let minimum = null;
            let maximum = null;


            for (
                const stage
                of stages.value
            ) {

                const values = [

                    stage.timeline
                        ?.in_time,

                    stage.timeline
                        ?.out_time,

                    stage.timeline
                        ?.lead_date,

                    stage.expectedDate
                ];


                for (const value of values) {

                    const ms =
                        toTime(value);


                    if (ms === null) {
                        continue;
                    }


                    minimum =
                        minimum === null
                            ? ms
                            : Math.min(
                                minimum,
                                ms
                            );


                    maximum =
                        maximum === null
                            ? ms
                            : Math.max(
                                maximum,
                                ms
                            );
                }
            }


            const now =
                Date.now();


            /*
             * If a process is currently running,
             * make sure today is visible.
             */
            if (currentStage.value) {

                maximum =
                    maximum === null
                        ? now
                        : Math.max(
                            maximum,
                            now
                        );
            }


            if (
                minimum === null ||
                maximum === null
            ) {

                minimum =
                    startOfDay(now);


                maximum =
                    minimum +
                    (
                        7 *
                        DAY_MS
                    );
            }


            minimum =
                startOfDay(
                    minimum
                ) -
                DAY_MS;


            maximum =
                startOfDay(
                    maximum
                ) +
                (
                    2 *
                    DAY_MS
                );


            const totalDays =
                Math.max(
                    1,

                    Math.ceil(
                        (
                            maximum -
                            minimum
                        ) /
                        DAY_MS
                    )
                );


            let tickStep = 1;


            if (totalDays > 20) {
                tickStep = 3;
            }


            if (totalDays > 45) {
                tickStep = 7;
            }


            if (totalDays > 100) {
                tickStep = 14;
            }


            const ticks = [];


            for (
                let day = 0;
                day <= totalDays;
                day += tickStep
            ) {

                const ms =
                    minimum +
                    (
                        day *
                        DAY_MS
                    );


                ticks.push({

                    ms,

                    left:
                        (
                            day /
                            totalDays
                        ) *
                        100,

                    label:
                        ganttTickLabel(
                            ms
                        )
                });
            }


            return {
                startMs:
                    minimum,

                endMs:
                    maximum,

                totalDays,

                ticks
            };
        }
    );


const ganttPixelsPerDay =
    computed(
        () => {

            const days =
                ganttRange.value
                    .totalDays;


            if (days <= 31) {
                return 34;
            }


            if (days <= 75) {
                return 24;
            }


            if (days <= 150) {
                return 15;
            }


            return 9;
        }
    );


const ganttCanvasWidth =
    computed(
        () =>
            Math.max(
                980,

                ganttRange.value
                    .totalDays
                *
                ganttPixelsPerDay.value
            )
    );


function ganttPercent(ms) {

    if (ms === null) {
        return 0;
    }


    const range =
        ganttRange.value;


    const raw =
        (
            ms -
            range.startMs
        ) /
        (
            range.endMs -
            range.startMs
        );


    return Math.max(
        0,
        Math.min(
            100,
            raw * 100
        )
    );
}


function boundsStyle(
    startMs,
    endMs
) {

    if (
        startMs === null ||
        endMs === null
    ) {
        return null;
    }


    const left =
        ganttPercent(
            startMs
        );


    const right =
        ganttPercent(
            endMs
        );


    const width =
        Math.max(
            0.65,
            right - left
        );


    return {
        left:
            `${left}%`,

        width:
            `${width}%`
    };
}


function ganttActualStyle(stage) {

    const startMs =
        toTime(
            stage.timeline
                ?.in_time
        );


    if (startMs === null) {
        return null;
    }


    let endMs =
        toTime(
            stage.timeline
                ?.out_time
        );


    if (endMs === null) {

        if (
            stage.state ===
            "current"
        ) {

            endMs =
                Date.now();
        }
        else {

            return null;
        }
    }


    if (endMs <= startMs) {

        endMs =
            startMs +
            (
                DAY_MS *
                0.2
            );
    }


    return boundsStyle(
        startMs,
        endMs
    );
}


function ganttPlanStyle(stage) {

    const plannedDays =
        Number(
            stage.plannedDays ||
            0
        );


    if (plannedDays <= 0) {
        return null;
    }


    let startMs =
        toTime(
            stage.timeline
                ?.in_time
        );


    let endMs = null;


    /*
     * For started processes:
     * planned duration begins from actual in-time.
     */
    if (startMs !== null) {

        endMs =
            startMs +
            (
                plannedDays *
                DAY_MS
            );


        return boundsStyle(
            startMs,
            endMs
        );
    }


    /*
     * For pending stages, if JMS returned a lead date,
     * use it as the planned completion point.
     * No fabricated schedule is created.
     */
    endMs =
        toTime(
            stage.timeline
                ?.lead_date
        );


    if (endMs === null) {
        return null;
    }


    startMs =
        endMs -
        (
            plannedDays *
            DAY_MS
        );


    return boundsStyle(
        startMs,
        endMs
    );
}


const todayVisible =
    computed(
        () => {

            const now =
                Date.now();


            return (
                now >=
                ganttRange.value.startMs
                &&
                now <=
                ganttRange.value.endMs
            );
        }
    );


const todayLineStyle =
    computed(
        () => ({

            left:
                `${ganttPercent(
                    Date.now()
                )}%`
        })
    );


function ganttDurationText(stage) {

    if (
        stage.state ===
        "current"
    ) {

        return (
            stage.actualDays ??
            0
        ) + " d so far";
    }


    if (
        stage.actualDays !==
        null
    ) {

        return (
            stage.actualDays +
            " d"
        );
    }


    if (
        stage.plannedDays
    ) {

        return (
            stage.plannedDays +
            " d plan"
        );
    }


    return "";
}


async function scrollGanttToCurrent() {

    await nextTick();


    const stage =
        currentStage.value;


    const scroller =
        ganttScroller.value;


    if (
        !stage ||
        !scroller
    ) {
        return;
    }


    let ms =
        toTime(
            stage.timeline
                ?.in_time
        );


    if (ms === null) {

        ms =
            Date.now();
    }


    const percentage =
        ganttPercent(ms);


    const fullWidth =
        ganttCanvasWidth.value;


    const position =
        (
            percentage /
            100
        ) *
        fullWidth;


    const target =
        Math.max(
            0,

            position -
            (
                scroller.clientWidth *
                0.42
            )
        );


    scroller.scrollTo({
        left:
            target,

        behavior:
            "smooth"
    });
}


watch(
    selectedItemIndex,

    () => {

        scrollGanttToCurrent();
    }
);

/* ============================================================
   BADGES
============================================================ */

function stateLabel(state) {

    if (state === "completed") {
        return "Completed";
    }


    if (state === "current") {
        return "Current Process";
    }


    return "Pending";
}


function stateClass(state) {

    return (
        "tr-status-" +
        state
    );
}


/* ============================================================
   STAGE DRAWER
============================================================ */

function openStage(stage) {

    selectedStage.value =
        stage;

    stageDrawerOpen.value =
        true;
}


/* ============================================================
   INFORMATION BLOCKS
============================================================ */

const jobInfo =
    computed(
        () => {

            const jc =
                jobCard.value;


            return [
                {
                    label:
                        "SO No.",
                    value:
                        cleanText(
                            jc.so_no
                        )
                },

                {
                    label:
                        "Work Order",
                    value:
                        cleanText(
                            jc.work_order_no
                        )
                },

                {
                    label:
                        "Customer",
                    value:
                        cleanText(
                            jc.customer_name
                        )
                },

                {
                    label:
                        "Job Card Date",
                    value:
                        formatDate(
                            jc.job_card_date
                        )
                },

                {
                    label:
                        "Final Status",
                    value:
                        cleanText(
                            jc.final_status
                        )
                },

                {
                    label:
                        "ERP Status",
                    value:
                        cleanText(
                            jc.erp_status
                        )
                }
            ];
        }
    );


const itemInfo =
    computed(
        () => {

            const item =
                currentItem.value ||
                {};


            return [
                {
                    label:
                        "Item",
                    value:
                        cleanText(
                            item.item_name
                        )
                },

                {
                    label:
                        "Part",
                    value:
                        cleanText(
                            item.part
                        )
                },

                {
                    label:
                        "Size",
                    value:
                        cleanText(
                            item.size
                        )
                },

                {
                    label:
                        "Material",
                    value:
                        cleanText(
                            item.material
                        )
                },

                {
                    label:
                        "Planned Qty",
                    value:
                        cleanText(
                            item.job_card_qty ??
                            item.so_qty
                        )
                },

                {
                    label:
                        "OK Qty",
                    value:
                        cleanText(
                            item.actual_qty
                        )
                },

                {
                    label:
                        "Rejected Qty",
                    value:
                        cleanText(
                            item.rejected_qty
                        )
                },

                {
                    label:
                        "Hold Qty",
                    value:
                        cleanText(
                            item.hold_qty
                        )
                },

                {
                    label:
                        "Delivery",
                    value:
                        formatDate(
                            item.delivery_date
                        )
                },

                {
                    label:
                        "Days in Stage",
                    value:
                        `${numberValue(
                            item.wip_stage_days
                        )} d`
                },

                {
                    label:
                        "Remaining Days",
                    value:
                        `${numberValue(
                            item.remaining_days
                        )} d`
                },

                {
                    label:
                        "Current WIP",
                    value:
                        cleanText(
                            item.wip_status
                        )
                }
            ];
        }
    );


/* ============================================================
   AUDIT
============================================================ */

const normalizedAudit =
    computed(
        () =>
            auditRows.value.map(
                (
                    row,
                    index
                ) => ({

                    id:
                        row.id ??
                        index,

                    oldStage:
                        cleanText(
                            row.old_stage ??
                            row.from_stage
                        ),

                    newStage:
                        cleanText(
                            row.new_stage ??
                            row.to_stage
                        ),

                    changedBy:
                        cleanText(
                            row.changed_by ??
                            row.username ??
                            row.user
                        ),

                    changedAt:
                        formatDateTime(
                            row.changed_at ??
                            row.created_at ??
                            row.timestamp
                        ),

                    item:
                        cleanText(
                            row.item_name
                        )
                })
            )
    );


/* ============================================================
   CHILD GATE
============================================================ */

const blockingRows =
    computed(
        () =>
            Array.isArray(
                gateInfo.value
                    ?.blocking_rows
            )
                ? gateInfo.value.blocking_rows
                : []
    );


/* ============================================================
   INITIAL URL
============================================================ */

onMounted(
    () => {

        const params =
            new URLSearchParams(
                window.location.search
            );


        const jc =
            params.get("jc");


        if (jc) {

            searchText.value =
                jc;

            searchJobCard();
        }
    }
);
</script>


<template>

    <main class="tr-page">


        <!-- =================================================
             HEADER
        ================================================== -->

        <header class="tr-header">

            <div>

                <div class="tr-breadcrumb">
                    Production
                    <span>›</span>
                    Traceability
                </div>


                <div class="tr-title-row">

                    <h1>
                        Traceability
                    </h1>


                    <span class="tr-header-badge">
                        Production Journey
                    </span>

                </div>


                <p>
                    Track the complete manufacturing
                    history of a Job Card.
                </p>

            </div>


            <Button
                label="Original Operational Page"
                severity="secondary"
                outlined
                size="small"
                @click="
                    window.location.href =
                        '/page3'
                "
            />

        </header>


        <!-- =================================================
             SEARCH
        ================================================== -->

        <section class="tr-search-card">

            <label>
                Job Card Number
            </label>


            <div class="tr-search-row">

                <input
                    v-model="searchText"
                    type="text"
                    autocomplete="off"
                    placeholder="Enter Job Card No."
                    @keyup.enter="
                        searchJobCard
                    "
                />


                <Button
                    label="Search"
                    :loading="loading"
                    @click="
                        searchJobCard
                    "
                />

            </div>


            <small>
                Press Enter or Search to load
                complete Job Card traceability.
            </small>

        </section>


        <Message
            v-if="error"
            severity="error"
            :closable="false"
            class="tr-message"
        >
            {{ error }}
        </Message>


        <!-- =================================================
             EMPTY
        ================================================== -->

        <section
            v-if="
                !data &&
                !loading
            "
            class="tr-empty"
        >

            <div class="tr-empty-symbol">
                JC
            </div>


            <h2>
                Search a Job Card to begin
            </h2>


            <p>
                Item information, current WIP,
                complete process route, subcontract
                history and movement audit will appear here.
            </p>

        </section>


        <!-- =================================================
             LOADING
        ================================================== -->

        <section
            v-if="loading"
            class="tr-loading"
        >

            <div class="tr-loading-line"></div>

            <div class="tr-loading-grid">

                <div
                    v-for="i in 6"
                    :key="i"
                ></div>

            </div>


            <div class="tr-loading-route"></div>

        </section>


        <!-- =================================================
             RESULT
        ================================================== -->

        <template
            v-if="
                data &&
                !loading
            "
        >

            <!-- JC SUMMARY -->

            <section class="tr-jc-card">

                <div class="tr-jc-main">

                    <div>

                        <span class="tr-label">
                            Job Card
                        </span>


                        <h2>
                            {{
                                cleanText(
                                    jobCard.job_card_no
                                )
                            }}
                        </h2>

                    </div>


                    <span
                        class="tr-status-badge"
                        :class="
                            normalize(
                                jobCard.final_status
                            ) === 'completed'
                                ? 'tr-status-completed'
                                : 'tr-status-current'
                        "
                    >
                        {{
                            cleanText(
                                jobCard.final_status
                            )
                        }}
                    </span>

                </div>


                <div class="tr-info-grid tr-job-info-grid">

                    <div
                        v-for="
                            field
                            in jobInfo
                        "
                        :key="
                            field.label
                        "
                        class="tr-info-field"
                    >

                        <span>
                            {{ field.label }}
                        </span>

                        <strong>
                            {{ field.value }}
                        </strong>

                    </div>

                </div>

            </section>


            <!-- MULTIPLE ITEMS -->

            <section
                v-if="
                    items.length > 1
                "
                class="tr-item-selector"
            >

                <span class="tr-label">
                    Job Card Items
                </span>


                <div>

                    <button
                        v-for="
                            (
                                item,
                                index
                            )
                            in items
                        "
                        :key="index"
                        type="button"
                        :class="{
                            active:
                                selectedItemIndex ===
                                index
                        }"
                        @click="
                            selectedItemIndex =
                                index
                        "
                    >

                        <span>
                            Item {{ index + 1 }}
                        </span>

                        <strong>
                            {{
                                cleanText(
                                    item.item_name
                                )
                            }}
                        </strong>

                    </button>

                </div>

            </section>


            <!-- ITEM -->

            <section class="tr-section-card">

                <div class="tr-section-header">

                    <div>

                        <span class="tr-eyebrow">
                            Selected Item
                        </span>


                        <h2 class="tr-item-title">
                            {{
                                cleanText(
                                    currentItem
                                        ?.item_name
                                )
                            }}
                        </h2>

                    </div>


                    <div class="tr-wip-box">

                        <span>
                            Current WIP
                        </span>

                        <strong>
                            {{
                                cleanText(
                                    currentItem
                                        ?.wip_status
                                )
                            }}
                        </strong>

                    </div>

                </div>


                <div class="tr-info-grid tr-item-info-grid">

                    <div
                        v-for="
                            field
                            in itemInfo
                        "
                        :key="
                            field.label
                        "
                        class="tr-info-field"
                    >

                        <span>
                            {{ field.label }}
                        </span>

                        <strong>
                            {{ field.value }}
                        </strong>

                    </div>

                </div>


                <div
                    v-if="
                        currentItem?.remarks
                    "
                    class="tr-note"
                >

                    <span>
                        NOTE
                    </span>


                    <p>
                        {{
                            currentItem
                                .remarks
                        }}
                    </p>

                </div>

            </section>

            <!-- =================================================
                 MINI GANTT PRODUCTION TIMELINE
            ================================================== -->

            <section class="tr-section-card tr-mini-gantt-card">

                <div class="tr-section-header">

                    <div>

                        <span class="tr-eyebrow">
                            Manufacturing Route
                        </span>


                        <h2>
                            Production Timeline
                        </h2>


                        <p>
                            Actual process duration against
                            planned duration across the Job Card journey.
                        </p>

                    </div>


                    <div class="tr-journey-summary">

                        <div>

                            <strong>
                                {{ progressPercent }}%
                            </strong>

                            <span>
                                {{
                                    completedCount
                                }}
                                /
                                {{
                                    stages.length
                                }}
                                completed
                            </span>

                        </div>


                        <div
                            v-if="
                                subcontractCount
                            "
                            class="tr-subcontract-summary"
                        >

                            <strong>
                                {{ subcontractCount }}
                            </strong>

                            <span>
                                subcontract
                            </span>

                        </div>

                    </div>

                </div>


                <div class="tr-progress">

                    <span
                        :style="{
                            width:
                                progressPercent +
                                '%'
                        }"
                    ></span>

                </div>


                <!-- LEGEND / TOOLBAR -->

                <div class="tr-gantt-toolbar">

                    <div class="tr-gantt-legend">

                        <span>
                            <i class="completed"></i>
                            Completed
                        </span>


                        <span>
                            <i class="current"></i>
                            Current WIP
                        </span>


                        <span>
                            <i class="planned"></i>
                            Planned Duration
                        </span>


                        <span>
                            <i class="subcontract"></i>
                            Amber underline = Subcontract
                        </span>

                    </div>


                    <button
                        type="button"
                        class="tr-center-current"
                        :disabled="
                            !currentStage
                        "
                        @click="
                            scrollGanttToCurrent
                        "
                    >
                        Center Current WIP
                    </button>

                </div>


                <!-- MINI GANTT -->

                <div
                    v-if="
                        stages.length
                    "
                    class="tr-mini-gantt"
                >


                    <!-- FIXED PROCESS COLUMN -->

                    <div class="tr-gantt-label-column">

                        <div class="tr-gantt-label-axis">
                            Process
                        </div>


                        <button
                            v-for="
                                stage
                                in stages
                            "
                            :key="
                                'label-' +
                                stage.index
                            "
                            type="button"
                            class="tr-gantt-label-row"
                            :class="[
                                'state-' +
                                stage.state,

                                {
                                    subcontract:
                                        stage.isSubcontract
                                }
                            ]"
                            @click="
                                openStage(stage)
                            "
                        >

                            <span
                                class="tr-gantt-status-dot"
                                :class="
                                    stage.state
                                "
                            ></span>


                            <div>

                                <strong>

                                    P{{
                                        stage.index +
                                        1
                                    }}

                                    ·

                                    {{
                                        stage.processName
                                    }}

                                </strong>


                                <small
                                    v-if="
                                        stage.isSubcontract
                                    "
                                    class="tr-gantt-vendor"
                                >
                                    SC ·
                                    {{
                                        stage.vendorName
                                    }}
                                </small>


                                <small v-else>
                                    {{
                                        stateLabel(
                                            stage.state
                                        )
                                    }}
                                </small>

                            </div>

                        </button>

                    </div>


                    <!-- SCROLLABLE CALENDAR -->

                    <div
                        ref="ganttScroller"
                        class="tr-gantt-scroll"
                    >

                        <div
                            class="tr-gantt-canvas"
                            :style="{
                                width:
                                    ganttCanvasWidth +
                                    'px'
                            }"
                        >


                            <!-- DATE AXIS -->

                            <div class="tr-gantt-axis">

                                <span
                                    v-for="
                                        tick
                                        in ganttRange.ticks
                                    "
                                    :key="
                                        tick.ms
                                    "
                                    :style="{
                                        left:
                                            tick.left +
                                            '%'
                                    }"
                                >
                                    {{ tick.label }}
                                </span>

                            </div>


                            <!-- TODAY -->

                            <div
                                v-if="
                                    todayVisible
                                "
                                class="tr-gantt-today"
                                :style="
                                    todayLineStyle
                                "
                            >

                                <span>
                                    Today
                                </span>

                            </div>


                            <!-- PROCESS ROWS -->

                            <div
                                v-for="
                                    stage
                                    in stages
                                "
                                :key="
                                    'track-' +
                                    stage.index
                                "
                                class="tr-gantt-track-row"
                                :class="{
                                    current:
                                        stage.state ===
                                        'current'
                                }"
                            >


                                <!-- GRID -->

                                <span
                                    v-for="
                                        tick
                                        in ganttRange.ticks
                                    "
                                    :key="
                                        'grid-' +
                                        stage.index +
                                        '-' +
                                        tick.ms
                                    "
                                    class="tr-gantt-grid-line"
                                    :style="{
                                        left:
                                            tick.left +
                                            '%'
                                    }"
                                ></span>


                                <!-- PLANNED BAR -->

                                <button
                                    v-if="
                                        ganttPlanStyle(
                                            stage
                                        )
                                    "
                                    type="button"
                                    class="tr-gantt-plan-bar"
                                    :style="
                                        ganttPlanStyle(
                                            stage
                                        )
                                    "
                                    :title="
                                        'Planned: ' +
                                        (
                                            stage.plannedDays ||
                                            0
                                        ) +
                                        ' days'
                                    "
                                    @click="
                                        openStage(stage)
                                    "
                                ></button>


                                <!-- ACTUAL BAR -->

                                <button
                                    v-if="
                                        ganttActualStyle(
                                            stage
                                        )
                                    "
                                    type="button"
                                    class="tr-gantt-actual-bar"
                                    :class="[
                                        stage.state,

                                        {
                                            subcontract:
                                                stage.isSubcontract,

                                            delayed:
                                                stage.delayed
                                        }
                                    ]"
                                    :style="
                                        ganttActualStyle(
                                            stage
                                        )
                                    "
                                    @click="
                                        openStage(stage)
                                    "
                                >

                                    <span>
                                        {{
                                            stage.state ===
                                            'current'
                                                ? 'CURRENT'
                                                : ganttDurationText(
                                                    stage
                                                )
                                        }}
                                    </span>


                                    <i
                                        v-if="
                                            stage.state ===
                                            'current'
                                        "
                                        class="tr-gantt-current-end"
                                    ></i>

                                </button>


                                <!-- NO ACTUAL DATA -->

                                <span
                                    v-if="
                                        !ganttActualStyle(
                                            stage
                                        )
                                        &&
                                        !ganttPlanStyle(
                                            stage
                                        )
                                    "
                                    class="tr-gantt-empty-status"
                                >
                                    {{
                                        stage.state ===
                                        'pending'
                                            ? 'Pending'
                                            : 'No timing data'
                                    }}
                                </span>

                            </div>

                        </div>

                    </div>

                </div>


                <div
                    v-else
                    class="tr-gantt-no-route"
                >
                    No process route was returned for this item.
                </div>


                <div class="tr-gantt-help">

                    <strong>
                        How to read:
                    </strong>

                    Solid bar = actual time.

                    Dashed outline = planned time.

                    Blue = current WIP.

                    Amber underline means the process was subcontracted.

                </div>

            </section>




            <!-- =================================================
                 TIMELINE + CURRENT POSITION
            ================================================== -->

            <section class="tr-lower-layout">

                <!-- TIMELINE -->

                <article class="tr-section-card">

                    <div class="tr-card-header">

                        <div>

                            <span class="tr-eyebrow">
                                Timing
                            </span>

                            <h2>
                                Process Timeline
                            </h2>

                        </div>


                        <span class="tr-count-badge">
                            {{ stages.length }} stages
                        </span>

                    </div>


                    <div class="tr-table-wrap">

                        <table>

                            <thead>

                                <tr>
                                    <th>Stage</th>
                                    <th>Process</th>
                                    <th>Type</th>
                                    <th>In</th>
                                    <th>Out</th>
                                    <th>Actual</th>
                                    <th>Plan</th>
                                    <th>Status</th>
                                    <th>Vendor</th>
                                </tr>

                            </thead>


                            <tbody>

                                <tr
                                    v-for="
                                        stage
                                        in stages
                                    "
                                    :key="
                                        stage.index
                                    "
                                    :class="{
                                        subcontract:
                                            stage.isSubcontract
                                    }"
                                    @click="
                                        openStage(stage)
                                    "
                                >

                                    <td>
                                        P{{
                                            stage.index +
                                            1
                                        }}
                                    </td>


                                    <td class="tr-table-process">
                                        {{
                                            stage.processName
                                        }}
                                    </td>


                                    <td>

                                        <span
                                            v-if="
                                                stage.isSubcontract
                                            "
                                            class="tr-type-badge subcontract"
                                        >
                                            SUBCONTRACT
                                        </span>


                                        <span
                                            v-else
                                            class="tr-type-badge"
                                        >
                                            IN-HOUSE
                                        </span>

                                    </td>


                                    <td>
                                        {{
                                            formatDateTime(
                                                stage.timeline
                                                    ?.in_time
                                            )
                                        }}
                                    </td>


                                    <td>
                                        {{
                                            formatDateTime(
                                                stage.timeline
                                                    ?.out_time
                                            )
                                        }}
                                    </td>


                                    <td>
                                        {{
                                            stage.actualDays ===
                                            null
                                                ? '—'
                                                : stage.actualDays +
                                                  ' d'
                                        }}
                                    </td>


                                    <td>
                                        {{
                                            stage.plannedDays
                                                ? stage.plannedDays +
                                                  ' d'
                                                : '—'
                                        }}
                                    </td>


                                    <td>

                                        <span
                                            class="tr-status-badge"
                                            :class="
                                                stateClass(
                                                    stage.state
                                                )
                                            "
                                        >
                                            {{
                                                stateLabel(
                                                    stage.state
                                                )
                                            }}
                                        </span>

                                    </td>


                                    <td>

                                        <strong
                                            v-if="
                                                stage.isSubcontract
                                            "
                                            class="tr-table-vendor"
                                        >
                                            {{
                                                stage.vendorName
                                            }}
                                        </strong>


                                        <span v-else>
                                            —
                                        </span>

                                    </td>

                                </tr>

                            </tbody>

                        </table>

                    </div>

                </article>


                <!-- RIGHT SIDE -->

                <div class="tr-side-column">


                    <!-- CURRENT -->

                    <article class="tr-section-card tr-current-card">

                        <div class="tr-card-header">

                            <div>

                                <span class="tr-eyebrow">
                                    Live Position
                                </span>

                                <h2>
                                    Current Status
                                </h2>

                            </div>

                        </div>


                        <template v-if="currentStage">

                            <div
                                class="tr-current-process"
                                :class="{
                                    subcontract:
                                        currentStage
                                            .isSubcontract
                                }"
                            >

                                <span class="tr-current-dot-large"></span>


                                <div>

                                    <span>
                                        Current Process
                                    </span>


                                    <strong>
                                        {{
                                            currentStage
                                                .processName
                                        }}
                                    </strong>


                                    <small
                                        v-if="
                                            currentStage
                                                .isSubcontract
                                        "
                                    >
                                        SUBCONTRACT ·
                                        {{
                                            currentStage
                                                .vendorName
                                        }}
                                    </small>

                                </div>

                            </div>


                            <div class="tr-current-grid">

                                <div>
                                    <span>Entered</span>

                                    <strong>
                                        {{
                                            formatDateTime(
                                                currentStage
                                                    .timeline
                                                    ?.in_time
                                            )
                                        }}
                                    </strong>
                                </div>


                                <div>
                                    <span>Days in Stage</span>

                                    <strong>
                                        {{
                                            currentStage
                                                .actualDays ??
                                            0
                                        }}
                                        d
                                    </strong>
                                </div>


                                <div>
                                    <span>Planned</span>

                                    <strong>
                                        {{
                                            currentStage
                                                .plannedDays ||
                                            0
                                        }}
                                        d
                                    </strong>
                                </div>


                                <div>
                                    <span>Remaining</span>

                                    <strong>
                                        {{
                                            numberValue(
                                                currentItem
                                                    ?.remaining_days
                                            )
                                        }}
                                        d
                                    </strong>
                                </div>

                            </div>

                        </template>


                        <div
                            v-else
                            class="tr-route-complete"
                        >

                            <strong>
                                ✓ Route Completed
                            </strong>

                            <span>
                                No active production
                                stage is currently shown.
                            </span>

                        </div>

                    </article>


                    <!-- CHILD C -->

                    <article
                        v-if="gateInfo"
                        class="tr-section-card"
                    >

                        <div class="tr-card-header">

                            <div>

                                <span class="tr-eyebrow">
                                    Dependency
                                </span>

                                <h2>
                                    Child-C Gate
                                </h2>

                            </div>


                            <span
                                class="tr-status-badge"
                                :class="
                                    gateInfo.can_start_upper
                                        ? 'tr-status-completed'
                                        : 'tr-status-waiting'
                                "
                            >
                                {{
                                    gateInfo.can_start_upper
                                        ? 'Ready'
                                        : 'Waiting'
                                }}
                            </span>

                        </div>


                        <div class="tr-gate-grid">

                            <div>
                                <span>
                                    Child-C Items
                                </span>

                                <strong>
                                    {{
                                        gateInfo
                                            .total_child_c_items ??
                                        '—'
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>
                                    Blocking
                                </span>

                                <strong>
                                    {{
                                        gateInfo
                                            .blocking_count ??
                                        blockingRows.length
                                    }}
                                </strong>
                            </div>

                        </div>


                        <div
                            v-if="
                                blockingRows.length
                            "
                            class="tr-block-list"
                        >

                            <div
                                v-for="
                                    (
                                        row,
                                        index
                                    )
                                    in blockingRows
                                "
                                :key="index"
                            >

                                <span class="tr-block-dot"></span>


                                <div>

                                    <strong>
                                        {{
                                            cleanText(
                                                row.child_job_card_no ??
                                                row.job_card_no
                                            )
                                        }}
                                    </strong>


                                    <span>
                                        {{
                                            cleanText(
                                                row.child_item_name ??
                                                row.item_name
                                            )
                                        }}
                                    </span>

                                </div>

                            </div>

                        </div>


                        <p
                            v-else
                            class="tr-ready-text"
                        >
                            No blocking Child-C record
                            was returned.
                        </p>

                    </article>

                </div>

            </section>


            <!-- =================================================
                 AUDIT
            ================================================== -->

            <section class="tr-section-card tr-audit-card">

                <div class="tr-card-header">

                    <div>

                        <span class="tr-eyebrow">
                            History
                        </span>


                        <h2>
                            Movement Audit
                        </h2>


                        <p>
                            Chronological process movement
                            recorded in JMS.
                        </p>

                    </div>


                    <span class="tr-count-badge">
                        {{
                            normalizedAudit.length
                        }}
                        events
                    </span>

                </div>


                <div
                    v-if="
                        normalizedAudit.length
                    "
                    class="tr-audit-list"
                >

                    <div
                        v-for="
                            (
                                row,
                                index
                            )
                            in normalizedAudit
                        "
                        :key="
                            row.id
                        "
                        class="tr-audit-row"
                    >

                        <div class="tr-audit-line">

                            <span></span>

                            <i
                                v-if="
                                    index <
                                    normalizedAudit.length - 1
                                "
                            ></i>

                        </div>


                        <div class="tr-audit-content">

                            <strong>
                                {{ row.oldStage }}

                                <b>→</b>

                                {{ row.newStage }}
                            </strong>


                            <span>
                                {{ row.item }}
                            </span>

                        </div>


                        <div class="tr-audit-user">

                            <strong>
                                {{ row.changedBy }}
                            </strong>

                            <span>
                                {{ row.changedAt }}
                            </span>

                        </div>

                    </div>

                </div>


                <div
                    v-else
                    class="tr-no-audit"
                >
                    No movement audit rows were returned.
                </div>

            </section>

        </template>


        <!-- =================================================
             PROCESS DRAWER
        ================================================== -->

        <Drawer
            v-model:visible="
                stageDrawerOpen
            "
            position="right"
            class="tr-stage-drawer"
        >

            <template #header>

                <div class="tr-drawer-title">

                    <span>
                        Process Detail
                    </span>

                    <strong>
                        {{
                            selectedStage
                                ?.processName ||
                            'Process'
                        }}
                    </strong>

                </div>

            </template>


            <div
                v-if="
                    selectedStage
                "
                class="tr-drawer-body"
            >

                <div class="tr-drawer-badges">

                    <span
                        class="tr-status-badge"
                        :class="
                            stateClass(
                                selectedStage
                                    .state
                            )
                        "
                    >
                        {{
                            stateLabel(
                                selectedStage
                                    .state
                            )
                        }}
                    </span>


                    <span
                        v-if="
                            selectedStage
                                .isSubcontract
                        "
                        class="tr-sc-badge tr-sc-large"
                    >
                        SUBCONTRACT
                    </span>


                    <span
                        v-if="
                            selectedStage
                                .delayed
                        "
                        class="tr-delay-badge"
                    >
                        DELAYED
                    </span>

                </div>


                <!-- SUBCONTRACT HERO -->

                <section
                    v-if="
                        selectedStage
                            .isSubcontract
                    "
                    class="tr-drawer-subcontract"
                >

                    <span>
                        External / Subcontract Process
                    </span>


                    <strong>
                        {{
                            selectedStage
                                .vendorName
                        }}
                    </strong>


                    <div>

                        <span>
                            Expected Return
                        </span>

                        <b>
                            {{
                                formatDate(
                                    selectedStage
                                        .expectedDate
                                )
                            }}
                        </b>

                    </div>

                </section>


                <div class="tr-drawer-metrics">

                    <div>
                        <span>Stage</span>

                        <strong>
                            P{{
                                selectedStage.index +
                                1
                            }}
                        </strong>
                    </div>


                    <div>
                        <span>Planned</span>

                        <strong>
                            {{
                                selectedStage
                                    .plannedDays ||
                                0
                            }}
                            d
                        </strong>
                    </div>


                    <div>
                        <span>Actual / So Far</span>

                        <strong>
                            {{
                                selectedStage
                                    .actualDays ??
                                0
                            }}
                            d
                        </strong>
                    </div>


                    <div>
                        <span>Timeline Status</span>

                        <strong>
                            {{
                                cleanText(
                                    selectedStage
                                        .timeline
                                        ?.status
                                )
                            }}
                        </strong>
                    </div>

                </div>


                <section class="tr-drawer-section">

                    <h3>
                        Process Timing
                    </h3>


                    <div>
                        <span>In Time</span>

                        <strong>
                            {{
                                formatDateTime(
                                    selectedStage
                                        .timeline
                                        ?.in_time
                                )
                            }}
                        </strong>
                    </div>


                    <div>
                        <span>Out Time</span>

                        <strong>
                            {{
                                formatDateTime(
                                    selectedStage
                                        .timeline
                                        ?.out_time
                                )
                            }}
                        </strong>
                    </div>


                    <div>
                        <span>Lead Date</span>

                        <strong>
                            {{
                                formatDate(
                                    selectedStage
                                        .timeline
                                        ?.lead_date
                                )
                            }}
                        </strong>
                    </div>

                </section>


                <Message
                    severity="info"
                    :closable="false"
                >
                    This Vue Traceability pilot is
                    read-only. Production actions remain
                    on the existing operational Page 3.
                </Message>

            </div>

        </Drawer>

    </main>

</template>