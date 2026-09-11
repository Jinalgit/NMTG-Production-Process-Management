<script setup>
import {
    computed,
    onBeforeUnmount,
    onMounted,
    ref,
    watch
} from "vue";

import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Message from "primevue/message";
import ProgressSpinner from "primevue/progressspinner";
import Select from "primevue/select";
import Skeleton from "primevue/skeleton";
import Tag from "primevue/tag";


/* =========================================================
   BOOTSTRAP
========================================================= */

const bootstrap =
    window.NMTG_DATA_VIEW || {};

const previousGlobalLoadData =
    window.loadData;


/* =========================================================
   BASIC STATE
========================================================= */

const activeTab = ref("ppc");

const loading = ref(false);
const errorMessage = ref("");

const rows = ref([]);
const total = ref(0);

const page = ref(1);
const perPage = ref(50);

const search = ref("");
const sortCol = ref("");
const sortOrder = ref("desc");

let searchTimer = null;
let requestSequence = 0;


/* =========================================================
   SERVER OPTIONS
========================================================= */

const wipOptions = ref([]);
const statusOptions = ref([]);
const supervisorOptions = ref([]);
const woOptions = ref([]);

const canSeePriority = ref(false);
const canSeeRmStatus = ref(false);


/* =========================================================
   GLOBAL SIDEBAR DATE
========================================================= */

const sidebarDate = ref(
    localStorage.getItem(
        "jms_filter_date"
    ) || ""
);


/* =========================================================
   NORMAL DATA VIEW COLUMNS
   SAME FAMILIAR ORDER AS EXISTING PAGE
========================================================= */

const NORMAL_COLUMNS = [
    {
        key: "is_priority",
        label: "Urgent",
        width: 74,
        center: true
    },
    {
        key: "job_card_no",
        label: "JC No",
        width: 132
    },
    {
        key: "wip_status",
        label: "WIP Status",
        width: 170
    },
    {
        key: "wip_stage_days",
        label: "Days in Stage",
        width: 112,
        center: true
    },
    {
        key: "remarks",
        label: "Remarks",
        width: 230
    },
    {
        key: "vendor_name",
        label: "Subcontractor",
        width: 175
    },
    {
        key: "so_no",
        label: "SO No",
        width: 125
    },
    {
        key: "customer_name",
        label: "Customer Name",
        width: 215
    },
    {
        key: "parent_code",
        label: "Parent Code",
        width: 145
    },
    {
        key: "child_code",
        label: "Child Code",
        width: 145
    },
    {
        key: "work_order_no",
        label: "WO No",
        width: 130
    },
    {
        key: "item_name",
        label: "Item Name",
        width: 260
    },
    {
        key: "material",
        label: "Material",
        width: 205
    },
    {
        key: "so_qty",
        label: "SO Qty",
        width: 90,
        center: true
    },
    {
        key: "actual_qty",
        label: "Actual Qty",
        width: 94,
        center: true
    },
    {
        key: "total_days",
        label: "Total Days",
        width: 94,
        center: true
    },
    {
        key: "remaining_days",
        label: "Remaining Days",
        width: 118,
        center: true
    },
    {
        key: "days_overdue",
        label: "Days Overdue",
        width: 108,
        center: true
    },
    {
        key: "final_status",
        label: "Status",
        width: 115
    },
    {
        key: "delivery_date",
        label: "Delivery Date",
        width: 128
    },
    {
        key: "so_date",
        label: "SO Date",
        width: 118
    },
    {
        key: "last_audit",
        label: "Last Updated",
        width: 330,
        noSort: true
    }
];


const DISPATCH_COLUMNS = [
    {
        key: "job_card_no",
        label: "JC No",
        width: 135
    },
    {
        key: "wip_status",
        label: "WIP Status",
        width: 175
    },
    {
        key: "so_no",
        label: "SO No",
        width: 130
    },
    {
        key: "customer_name",
        label: "Customer Name",
        width: 230
    },
    {
        key: "delivery_date",
        label: "Delivery Date",
        width: 135
    },
    {
        key: "remaining_days",
        label: "Remaining Days",
        width: 125,
        center: true
    },
    {
        key: "item_name",
        label: "Item Name",
        width: 280
    }
];


const FILTERABLE_COLUMNS =
    new Set([
        "is_priority",
        "job_card_no",
        "so_no",
        "customer_name",
        "parent_code",
        "child_code",
        "work_order_no",
        "item_name",
        "material",
        "so_qty",
        "actual_qty",
        "wip_status",
        "remarks",
        "vendor_name",
        "wip_stage_days",
        "total_days",
        "remaining_days",
        "days_overdue",
        "final_status",
        "delivery_date",
        "so_date",
        "last_audit"
    ]);


/* =========================================================
   DISPATCH MODE
========================================================= */

const dispatchMode =
    computed(() => {

        const role =
            String(
                bootstrap.role || ""
            )
                .trim()
                .toLowerCase();

        return Boolean(
            bootstrap.dispatchAccess ||
            bootstrap.isDispatch ||
            bootstrap.is_dispatch ||
            role === "dispatch"
        );

    });


const baseColumns =
    computed(() => {

        const source =
            dispatchMode.value
                ? DISPATCH_COLUMNS
                : NORMAL_COLUMNS;

        return source.filter(
            column => (
                column.key !== "is_priority" ||
                canSeePriority.value
            )
        );

    });


/* =========================================================
   COLUMN VISIBILITY
========================================================= */

const columnStorageKey =
    `jms_page5_vue_hidden_columns_v2_${
        bootstrap.currentUser ||
        bootstrap.username ||
        bootstrap.role ||
        "default"
    }`;


function readHiddenColumns() {

    try {

        const value =
            JSON.parse(
                localStorage.getItem(
                    columnStorageKey
                ) || "{}"
            );

        if (
            value &&
            typeof value === "object"
        ) {
            return value;
        }

    }
    catch (error) {

        console.warn(
            "Could not read Data View column settings",
            error
        );

    }

    return {};
}


const hiddenColumns =
    ref(
        readHiddenColumns()
    );


const columnDraft =
    ref({});


const visibleColumns =
    computed(() => {

        const visible =
            baseColumns.value.filter(
                column =>
                    !hiddenColumns.value[
                        column.key
                    ]
            );

        return visible.length
            ? visible
            : baseColumns.value;

    });


function saveHiddenColumns() {

    localStorage.setItem(
        columnStorageKey,
        JSON.stringify(
            hiddenColumns.value
        )
    );
}


/* =========================================================
   COLUMN CHOOSER
========================================================= */

const columnsOpen = ref(false);

const columnsPosition =
    ref({
        top: 0,
        left: 0
    });


function openColumns(event) {

    if (columnsOpen.value) {

        columnsOpen.value = false;
        return;

    }

    closeHeaderFilter();

    columnDraft.value = {
        ...hiddenColumns.value
    };

    const rect =
        event.currentTarget
            .getBoundingClientRect();

    const width = 280;

    columnsPosition.value = {
        top:
            Math.min(
                rect.bottom + 6,
                window.innerHeight - 390
            ),

        left:
            Math.max(
                12,
                Math.min(
                    rect.right - width,
                    window.innerWidth -
                        width -
                        12
                )
            )
    };

    columnsOpen.value = true;
}


function draftColumnVisible(key) {

    return !columnDraft.value[key];
}


function toggleDraftColumn(
    key,
    checked
) {

    const next = {
        ...columnDraft.value
    };

    if (checked) {

        delete next[key];

    }
    else {

        next[key] = true;

    }

    columnDraft.value = next;
}


function applyColumns() {

    const visibleCount =
        baseColumns.value.filter(
            column =>
                !columnDraft.value[
                    column.key
                ]
        ).length;

    if (!visibleCount) {
        return;
    }

    hiddenColumns.value = {
        ...columnDraft.value
    };

    saveHiddenColumns();

    columnsOpen.value = false;
}


function showAllColumns() {

    columnDraft.value = {};
}


function closeColumns() {

    columnsOpen.value = false;
}


/* =========================================================
   ADVANCED FILTER PANEL
========================================================= */

const filterOpen = ref(false);


const filters =
    ref({
        wip: "",
        status: "",
        delivery_from: "",
        delivery_to: "",
        overdue: "",
        subcontracting: "",
        supervisor_user_id: "",
        urgent_only: ""
    });


const overdueOptions = [
    {
        label: "All Delivery Status",
        value: ""
    },
    {
        label: "Overdue Only",
        value: "yes"
    },
    {
        label: "Critical (>7 Days)",
        value: "critical"
    }
];


const subcontractOptions = [
    {
        label: "All",
        value: ""
    },
    {
        label: "Subcontract Only",
        value: "yes"
    },
    {
        label: "Non-Subcontract",
        value: "no"
    }
];


const urgentOptions = [
    {
        label: "All Priority",
        value: ""
    },
    {
        label: "Urgent Only",
        value: "yes"
    }
];


const supervisorSelectOptions =
    computed(() => {

        return [
            {
                label: "All Supervisors",
                value: ""
            },

            ...supervisorOptions.value.map(
                row => ({
                    label:
                        row.username ||
                        row.full_name ||
                        `User ${row.id}`,

                    value:
                        String(
                            row.id
                        )
                })
            )
        ];

    });


const advancedFilterCount =
    computed(() => {

        return Object.values(
            filters.value
        ).filter(Boolean).length;

    });


function toggleFilters() {

    filterOpen.value =
        !filterOpen.value;
}


function applyAdvancedFilters() {

    page.value = 1;

    loadPpcData();
}


function clearAdvancedFilters() {

    filters.value = {
        wip: "",
        status: "",
        delivery_from: "",
        delivery_to: "",
        overdue: "",
        subcontracting: "",
        supervisor_user_id: "",
        urgent_only: ""
    };

    page.value = 1;

    loadPpcData();
}


/* =========================================================
   EXCEL-LIKE HEADER FILTERS
========================================================= */

const excelFilters = ref({});

const filterOptionsCache =
    ref({});


const headerFilter =
    ref({
        open: false,
        key: "",
        label: "",
        top: 0,
        left: 0,
        loading: false,
        search: "",
        options: [],
        draft: [],
        message: ""
    });


const excelFilterCount =
    computed(() => {

        return Object.values(
            excelFilters.value
        ).filter(
            values =>
                Array.isArray(values) &&
                values.length
        ).length;

    });


const totalFilterCount =
    computed(() =>
        advancedFilterCount.value +
        excelFilterCount.value
    );


function isFilterable(key) {

    return FILTERABLE_COLUMNS.has(
        key
    );
}


function isExcelFilterActive(key) {

    return (
        Array.isArray(
            excelFilters.value[key]
        ) &&
        excelFilters.value[key].length > 0
    );
}


async function fetchHeaderFilterOptions(
    key
) {

    if (
        Array.isArray(
            filterOptionsCache.value[key]
        )
    ) {

        return filterOptionsCache
            .value[key];
    }


    const params =
        new URLSearchParams({
            column: key
        });


    if (search.value.trim()) {

        params.set(
            "search",
            search.value.trim()
        );

    }


    const data =
        await apiJson(
            "/api/data/job_cards/filter_options?" +
            params.toString()
        );


    const values =
        Array.isArray(data.values)
            ? data.values.map(
                value =>
                    String(
                        value ?? ""
                    )
            )
            : [];


    filterOptionsCache.value = {
        ...filterOptionsCache.value,

        [key]:
            values
    };


    return values;
}


async function openHeaderFilter(
    event,
    column
) {

    event.preventDefault();
    event.stopPropagation();

    columnsOpen.value = false;


    if (
        headerFilter.value.open &&
        headerFilter.value.key ===
            column.key
    ) {

        closeHeaderFilter();

        return;
    }


    const rect =
        event.currentTarget
            .getBoundingClientRect();


    const width = 300;


    headerFilter.value = {
        open: true,

        key:
            column.key,

        label:
            column.label,

        top:
            Math.min(
                rect.bottom + 6,
                window.innerHeight - 470
            ),

        left:
            Math.max(
                12,
                Math.min(
                    rect.left,
                    window.innerWidth -
                        width -
                        12
                )
            ),

        loading: true,

        search: "",

        options: [],

        draft: [],

        message: ""
    };


    try {

        const options =
            await fetchHeaderFilterOptions(
                column.key
            );


        const active =
            excelFilters.value[
                column.key
            ];


        headerFilter.value.options =
            options;


        headerFilter.value.draft =
            Array.isArray(active) &&
            active.length
                ? [...active]
                : [...options];

    }
    catch (error) {

        headerFilter.value.message =
            error.message ||
            "Unable to load filter values.";

    }
    finally {

        headerFilter.value.loading =
            false;

    }
}


const visibleHeaderFilterOptions =
    computed(() => {

        const query =
            String(
                headerFilter.value.search ||
                ""
            )
                .trim()
                .toLowerCase();


        if (!query) {

            return headerFilter
                .value.options;

        }


        return headerFilter
            .value.options.filter(
                value => {

                    const label =
                        value === ""
                            ? "(Blanks)"
                            : value;

                    return label
                        .toLowerCase()
                        .includes(query);
                }
            );

    });


function toggleHeaderFilterValue(
    value,
    checked
) {

    const stringValue =
        String(
            value ?? ""
        );


    const set =
        new Set(
            headerFilter.value.draft
                .map(String)
        );


    if (checked) {

        set.add(
            stringValue
        );

    }
    else {

        set.delete(
            stringValue
        );

    }


    headerFilter.value.draft =
        [...set];


    headerFilter.value.message = "";
}


function selectAllHeaderValues() {

    headerFilter.value.draft = [
        ...headerFilter.value.options
    ];

    headerFilter.value.message = "";
}


function clearHeaderValuesDraft() {

    headerFilter.value.draft = [];
}


function applyHeaderFilter() {

    const key =
        headerFilter.value.key;


    if (!key) {
        return;
    }


    const draft =
        Array.from(
            new Set(
                headerFilter.value.draft
                    .map(String)
            )
        );


    if (!draft.length) {

        headerFilter.value.message =
            "Select at least one value, or use Clear Filter.";

        return;
    }


    const allOptions =
        headerFilter.value.options
            .map(String);


    const allSelected =
        draft.length ===
            allOptions.length &&
        allOptions.every(
            value =>
                draft.includes(value)
        );


    const next = {
        ...excelFilters.value
    };


    if (allSelected) {

        delete next[key];

    }
    else {

        next[key] =
            draft;

    }


    excelFilters.value = next;

    page.value = 1;

    closeHeaderFilter();

    loadPpcData();
}


function clearCurrentHeaderFilter() {

    const key =
        headerFilter.value.key;


    const next = {
        ...excelFilters.value
    };


    delete next[key];

    excelFilters.value = next;

    page.value = 1;

    closeHeaderFilter();

    loadPpcData();
}


function clearAllHeaderFilters() {

    excelFilters.value = {};

    page.value = 1;

    closeHeaderFilter();

    loadPpcData();
}


function closeHeaderFilter() {

    headerFilter.value.open =
        false;
}


/* =========================================================
   API
========================================================= */

async function apiJson(
    url,
    options = {}
) {

    const response =
        await fetch(
            url,
            {
                credentials:
                    "same-origin",

                ...options
            }
        );


    let data = null;


    try {

        data =
            await response.json();

    }
    catch {

        throw new Error(
            "Invalid server response."
        );

    }


    if (
        !response.ok ||
        data.success === false
    ) {

        throw new Error(
            data.error ||
            `Request failed (${response.status})`
        );

    }


    return data;
}


/* =========================================================
   PPC QUERY
========================================================= */

function buildPpcParams({
    exportAll = false
} = {}) {

    const params =
        new URLSearchParams();


    if (search.value.trim()) {

        params.set(
            "search",
            search.value.trim()
        );

    }


    params.set(
        "page",
        exportAll
            ? "1"
            : String(page.value)
    );


    params.set(
        "per_page",
        exportAll
            ? "99999"
            : String(perPage.value)
    );


    if (sortCol.value) {

        params.set(
            "sort",
            sortCol.value
        );

        params.set(
            "order",
            sortOrder.value
        );

    }


    const filterDate =
        localStorage.getItem(
            "jms_filter_date"
        ) || "";


    sidebarDate.value =
        filterDate;


    if (filterDate) {

        params.set(
            "filter_date",
            filterDate
        );

    }


    const simpleFilters = [
        "wip",
        "status",
        "delivery_from",
        "delivery_to",
        "overdue",
        "subcontracting",
        "supervisor_user_id",
        "urgent_only"
    ];


    simpleFilters.forEach(
        key => {

            const value =
                filters.value[key];

            if (value) {

                params.set(
                    key,
                    value
                );

            }

        }
    );


    /*
     * Preserve the same dependency enrichment
     * requested by the existing Data View.
     */
    params.set(
        "include_dependencies",
        "1"
    );


    Object.entries(
        excelFilters.value
    ).forEach(
        ([
            columnKey,
            selectedValues
        ]) => {

            if (
                !Array.isArray(
                    selectedValues
                ) ||
                !selectedValues.length
            ) {
                return;
            }


            selectedValues.forEach(
                value => {

                    params.append(
                        `xf_${columnKey}`,
                        value === ""
                            ? "__BLANK__"
                            : value
                    );

                }
            );

        }
    );


    return params;
}


/* =========================================================
   LOAD PPC DATA
========================================================= */

async function loadPpcData() {

    const currentRequest =
        ++requestSequence;


    loading.value = true;

    errorMessage.value = "";


    try {

        const data =
            await apiJson(
                "/api/data/job_cards?" +
                buildPpcParams()
                    .toString()
            );


        if (
            currentRequest !==
            requestSequence
        ) {

            return;
        }


        rows.value =
            Array.isArray(data.data)
                ? data.data
                : [];


        total.value =
            Number(
                data.total || 0
            );


        if (
            Number(data.page)
        ) {

            page.value =
                Number(data.page);

        }


        if (
            Number(data.per_page)
        ) {

            perPage.value =
                Number(
                    data.per_page
                );

        }


        if (
            Array.isArray(
                data.wip_options
            )
        ) {

            wipOptions.value =
                data.wip_options;

        }


        if (
            Array.isArray(
                data.status_options
            )
        ) {

            statusOptions.value =
                data.status_options;

        }


        if (
            Array.isArray(
                data.supervisor_options
            )
        ) {

            supervisorOptions.value =
                data.supervisor_options;

        }


        if (
            Array.isArray(
                data.wo_options
            )
        ) {

            woOptions.value =
                data.wo_options;

        }


        canSeePriority.value =
            Boolean(
                data.can_see_priority_column
            );


        canSeeRmStatus.value =
            Boolean(
                data.can_see_rm_status
            );

    }
    catch (error) {

        console.error(error);

        errorMessage.value =
            error.message ||
            "Unable to load Data View.";

        rows.value = [];

        total.value = 0;

    }
    finally {

        if (
            currentRequest ===
            requestSequence
        ) {

            loading.value =
                false;

        }

    }
}


/* =========================================================
   SEARCH
========================================================= */

watch(
    search,
    () => {

        clearTimeout(
            searchTimer
        );


        searchTimer =
            setTimeout(
                () => {

                    filterOptionsCache.value = {};

                    page.value = 1;

                    loadPpcData();

                },
                350
            );

    }
);


function clearSearch() {

    search.value = "";
}


/* =========================================================
   SORTING
========================================================= */

function sortBy(column) {

    if (column.noSort) {
        return;
    }


    if (
        sortCol.value ===
        column.key
    ) {

        sortOrder.value =
            sortOrder.value === "asc"
                ? "desc"
                : "asc";

    }
    else {

        sortCol.value =
            column.key;

        sortOrder.value =
            "asc";

    }


    page.value = 1;

    loadPpcData();
}


function sortIcon(column) {

    if (
        sortCol.value !==
        column.key
    ) {

        return "pi pi-sort-alt";

    }


    return (
        sortOrder.value === "asc"
            ? "pi pi-sort-amount-up"
            : "pi pi-sort-amount-down"
    );
}


/* =========================================================
   PAGINATION
========================================================= */

const totalPages =
    computed(() => {

        return Math.max(
            1,
            Math.ceil(
                Number(total.value || 0) /
                Number(perPage.value || 50)
            )
        );

    });


const firstRecord =
    computed(() => {

        if (!total.value) {
            return 0;
        }

        return (
            (page.value - 1) *
            perPage.value +
            1
        );

    });


const lastRecord =
    computed(() => {

        return Math.min(
            page.value *
                perPage.value,
            total.value
        );

    });


const perPageOptions = [
    25,
    50,
    100
];


function previousPage() {

    if (page.value <= 1) {
        return;
    }

    page.value -= 1;

    loadPpcData();
}


function nextPage() {

    if (
        page.value >=
        totalPages.value
    ) {
        return;
    }

    page.value += 1;

    loadPpcData();
}


function changePerPage() {

    page.value = 1;

    loadPpcData();
}


/* =========================================================
   FORMATTERS
========================================================= */

function text(value) {

    if (
        value === null ||
        value === undefined ||
        String(value).trim() === ""
    ) {
        return "—";
    }

    return String(value);
}


function formatDate(value) {

    if (!value) {
        return "—";
    }


    const raw =
        String(value).trim();


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


function displayValue(
    row,
    column
) {

    const value =
        row?.[column.key];


    if (
        column.key ===
            "delivery_date" ||
        column.key ===
            "so_date"
    ) {

        return formatDate(
            value
        );

    }


    return text(
        value
    );
}


function statusSeverity(value) {

    const normalized =
        String(
            value || ""
        )
            .trim()
            .toLowerCase();


    if (
        normalized === "completed" ||
        normalized === "store"
    ) {
        return "success";
    }


    if (
        normalized === "partial"
    ) {
        return "warn";
    }


    return "secondary";
}


function wipClass(value) {

    const normalized =
        String(
            value || ""
        )
            .trim()
            .toLowerCase();


    if (
        normalized === "store"
    ) {
        return "complete";
    }


    if (
        normalized.includes(
            "quality"
        ) ||
        normalized.includes(
            "inspection"
        )
    ) {
        return "quality";
    }


    if (
        normalized.includes(
            "raw material"
        )
    ) {
        return "raw";
    }


    if (
        normalized.includes(
            "subcontract"
        )
    ) {
        return "subcontract";
    }


    return "active";
}


function rowClass(row) {

    return {
        "dvv-row-urgent":
            Boolean(
                Number(
                    row?.is_priority || 0
                )
            ),

        "dvv-row-overdue":
            !Number(
                row?.is_priority || 0
            ) &&
            Number(
                row?.days_overdue || 0
            ) > 0
    };
}


function cellClass(
    row,
    column
) {

    return {
        "dvv-cell-center":
            Boolean(
                column.center
            ),

        "dvv-cell-overdue":
            column.key ===
                "days_overdue" &&
            Number(
                row?.days_overdue || 0
            ) > 0,

        "dvv-cell-warning":
            column.key ===
                "remaining_days" &&
            Number(
                row?.remaining_days
            ) >= 0 &&
            Number(
                row?.remaining_days
            ) <= 7,

        "dvv-cell-negative":
            column.key ===
                "remaining_days" &&
            Number(
                row?.remaining_days
            ) < 0
    };
}


/* =========================================================
   RIGHT DRAWER
========================================================= */

const sideOpen = ref(false);
const sideMode = ref("");
const sideRow = ref(null);

const stageLoading = ref(false);
const stagePayload = ref(null);
const stageItem = ref(null);


function openDetail(row) {

    sideMode.value = "detail";

    sideRow.value = row;

    stagePayload.value = null;

    stageItem.value = null;

    sideOpen.value = true;
}


function openEditPreview(row) {

    sideMode.value = "edit";

    sideRow.value = row;

    stagePayload.value = null;

    stageItem.value = null;

    sideOpen.value = true;
}


function openPriorityPreview(row) {

    sideMode.value = "priority";

    sideRow.value = row;

    stagePayload.value = null;

    stageItem.value = null;

    sideOpen.value = true;
}


async function openStagePreview(row) {

    sideMode.value = "stage";

    sideRow.value = row;

    sideOpen.value = true;

    stageLoading.value = true;

    stagePayload.value = null;

    stageItem.value = null;


    try {

        const data =
            await apiJson(
                "/api/quality_check/fetch/" +
                encodeURIComponent(
                    row.job_card_no
                )
            );


        stagePayload.value =
            data;


        const items =
            Array.isArray(
                data.items
            )
                ? data.items
                : (
                    Array.isArray(
                        data.data?.items
                    )
                        ? data.data.items
                        : []
                );


        const selected =
            items.find(
                item =>
                    String(
                        item.item_name || ""
                    )
                        .trim()
                        .toLowerCase() ===
                    String(
                        row.item_name || ""
                    )
                        .trim()
                        .toLowerCase()
            ) ||
            items[0] ||
            null;


        stageItem.value =
            selected;

    }
    catch (error) {

        stagePayload.value = {
            error:
                error.message ||
                "Unable to load stage preview."
        };

    }
    finally {

        stageLoading.value =
            false;

    }
}


function closeSidePanel() {

    sideOpen.value = false;

    sideMode.value = "";

    sideRow.value = null;

    stagePayload.value = null;

    stageItem.value = null;
}


const sideTitle =
    computed(() => {

        if (!sideRow.value) {
            return "Job Card";
        }


        switch (
            sideMode.value
        ) {

            case "stage":
                return "Stage Change Preview";

            case "edit":
                return "Edit Job Card Preview";

            case "priority":
                return "Priority Preview";

            default:
                return "Job Card Detail";
        }

    });


const previewNextProcess =
    computed(() => {

        return (
            stageItem.value?.next_process ||
            stagePayload.value?.next_process ||
            stagePayload.value
                ?.data?.next_process ||
            ""
        );

    });


function fieldEditable(key) {

    const fields =
        sideRow.value
            ?.page5_editable_fields;


    return (
        Array.isArray(fields) &&
        fields.includes(key)
    );
}


function openOriginalPage() {

    window.location.href =
        "/page5";
}


/* =========================================================
   WIP SUMMARY
========================================================= */

const wipSummaryLoading =
    ref(false);

const wipSummaryLoaded =
    ref(false);

const wipFrom = ref("");
const wipTo = ref("");

const wipProcesses = ref([]);
const wipRows = ref([]);


async function loadWipSummary() {

    wipSummaryLoading.value = true;

    errorMessage.value = "";


    try {

        const params =
            new URLSearchParams();


        if (wipFrom.value) {

            params.set(
                "from_date",
                wipFrom.value
            );

        }


        if (wipTo.value) {

            params.set(
                "to_date",
                wipTo.value
            );

        }


        const data =
            await apiJson(
                "/api/wip_summary?" +
                params.toString()
            );


        wipProcesses.value =
            Array.isArray(
                data.processes
            )
                ? data.processes
                : [];


        wipRows.value =
            Array.isArray(
                data.rows
            )
                ? data.rows
                : [];


        if (data.from_date) {
            wipFrom.value =
                data.from_date;
        }


        if (data.to_date) {
            wipTo.value =
                data.to_date;
        }


        wipSummaryLoaded.value =
            true;

    }
    catch (error) {

        errorMessage.value =
            error.message ||
            "Unable to load WIP Summary.";

        wipProcesses.value = [];

        wipRows.value = [];

    }
    finally {

        wipSummaryLoading.value =
            false;

    }
}


/* =========================================================
   WIP SUMMARY DETAIL
========================================================= */

const wipDetailOpen = ref(false);
const wipDetailLoading = ref(false);

const wipDetailDate = ref("");
const wipDetailProcess = ref("");
const wipDetailRows = ref([]);


async function openWipDetail(
    date,
    process,
    count
) {

    if (
        !Number(count)
    ) {
        return;
    }


    wipDetailOpen.value =
        true;

    wipDetailLoading.value =
        true;

    wipDetailDate.value =
        date;

    wipDetailProcess.value =
        process;

    wipDetailRows.value = [];


    try {

        const params =
            new URLSearchParams({
                date,
                process
            });


        const data =
            await apiJson(
                "/api/wip_summary/detail?" +
                params.toString()
            );


        wipDetailRows.value =
            Array.isArray(
                data.rows
            )
                ? data.rows
                : [];

    }
    catch (error) {

        errorMessage.value =
            error.message ||
            "Unable to load WIP detail.";

    }
    finally {

        wipDetailLoading.value =
            false;

    }
}


function closeWipDetail() {

    wipDetailOpen.value =
        false;
}


/* =========================================================
   TAB SWITCH
========================================================= */

async function switchTab(tab) {

    activeTab.value =
        tab;

    closeSidePanel();

    closeHeaderFilter();

    closeColumns();


    if (
        tab === "wip" &&
        !wipSummaryLoaded.value
    ) {

        await loadWipSummary();

    }
}


/* =========================================================
   REFRESH
========================================================= */

function refreshCurrent() {

    if (
        activeTab.value === "wip"
    ) {

        loadWipSummary();

    }
    else {

        loadPpcData();

    }
}


/* =========================================================
   EXPORT CURRENT DATA AS EXCEL-FRIENDLY CSV
========================================================= */

const exportLoading =
    ref(false);


function csvEscape(value) {

    const text =
        String(
            value ?? ""
        );

    return (
        '"' +
        text.replace(
            /"/g,
            '""'
        ) +
        '"'
    );
}


async function exportCsv() {

    exportLoading.value = true;

    errorMessage.value = "";


    try {

        const data =
            await apiJson(
                "/api/data/job_cards?" +
                buildPpcParams({
                    exportAll: true
                }).toString()
            );


        const exportRows =
            Array.isArray(data.data)
                ? data.data
                : [];


        const columns =
            visibleColumns.value;


        const matrix = [
            columns.map(
                column =>
                    csvEscape(
                        column.label
                    )
            ).join(","),

            ...exportRows.map(
                row =>
                    columns.map(
                        column =>
                            csvEscape(
                                displayValue(
                                    row,
                                    column
                                ) === "—"
                                    ? ""
                                    : displayValue(
                                        row,
                                        column
                                    )
                            )
                    ).join(",")
            )
        ];


        const blob =
            new Blob(
                [
                    "\uFEFF" +
                    matrix.join(
                        "\r\n"
                    )
                ],
                {
                    type:
                        "text/csv;charset=utf-8"
                }
            );


        const url =
            URL.createObjectURL(
                blob
            );


        const anchor =
            document.createElement(
                "a"
            );


        const stamp =
            new Date()
                .toISOString()
                .slice(0, 10);


        anchor.href = url;

        anchor.download =
            `NMTG_Data_View_${stamp}.csv`;


        document.body
            .appendChild(
                anchor
            );


        anchor.click();

        anchor.remove();

        URL.revokeObjectURL(
            url
        );

    }
    catch (error) {

        errorMessage.value =
            error.message ||
            "Unable to export Data View.";

    }
    finally {

        exportLoading.value =
            false;

    }
}


/* =========================================================
   DOCUMENT / KEYBOARD EVENTS
========================================================= */

function handleDocumentClick(event) {

    const target =
        event.target;


    if (
        !(target instanceof Element)
    ) {
        return;
    }


    if (
        headerFilter.value.open &&
        !target.closest(
            ".dvv-header-filter-popover"
        ) &&
        !target.closest(
            ".dvv-th-filter"
        )
    ) {

        closeHeaderFilter();

    }


    if (
        columnsOpen.value &&
        !target.closest(
            ".dvv-column-popover"
        ) &&
        !target.closest(
            ".dvv-columns-button"
        )
    ) {

        closeColumns();

    }
}


function handleKeydown(event) {

    if (
        event.key !== "Escape"
    ) {
        return;
    }

    closeHeaderFilter();

    closeColumns();

    if (wipDetailOpen.value) {

        closeWipDetail();

        return;
    }

    if (sideOpen.value) {

        closeSidePanel();

    }
}


function handleStorage(event) {

    if (
        event.key ===
        "jms_filter_date"
    ) {

        sidebarDate.value =
            event.newValue || "";

        page.value = 1;

        loadPpcData();

    }
}


/* =========================================================
   MOUNT
========================================================= */

onMounted(
    async () => {

        document.addEventListener(
            "click",
            handleDocumentClick
        );

        document.addEventListener(
            "keydown",
            handleKeydown
        );

        window.addEventListener(
            "storage",
            handleStorage
        );


        /*
         * Existing shared sidebar date filter calls
         * loadData(). Give it a safe Vue equivalent.
         */
        window.loadData =
            loadPpcData;


        await loadPpcData();

    }
);


onBeforeUnmount(
    () => {

        clearTimeout(
            searchTimer
        );


        document.removeEventListener(
            "click",
            handleDocumentClick
        );


        document.removeEventListener(
            "keydown",
            handleKeydown
        );


        window.removeEventListener(
            "storage",
            handleStorage
        );


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

    <main class="dvv-page">


        <!-- =================================================
             HEADER
        ================================================== -->

        <header class="dvv-header">

            <div>

                <div class="dvv-breadcrumb">

                    Data

                    <i class="pi pi-angle-right"></i>

                    Data View

                </div>


                <div class="dvv-title-row">

                    <h1>
                        Data View
                    </h1>

                    <Tag
                        value="Vue Pilot"
                        severity="info"
                        rounded
                    />

                </div>


                <p>
                    Production records, WIP status and
                    delivery tracking.
                </p>

            </div>


            <div class="dvv-header-actions">

                <Button
                    label="Original Page"
                    icon="pi pi-arrow-left"
                    severity="secondary"
                    outlined
                    size="small"
                    @click="openOriginalPage"
                />

                <Button
                    label="Refresh"
                    icon="pi pi-refresh"
                    severity="secondary"
                    outlined
                    size="small"
                    :loading="
                        loading ||
                        wipSummaryLoading
                    "
                    @click="refreshCurrent"
                />

            </div>

        </header>


        <!-- =================================================
             TAB BAR
        ================================================== -->

        <nav class="dvv-tabs">

            <button
                type="button"
                :class="{
                    active:
                        activeTab === 'ppc'
                }"
                @click="
                    switchTab('ppc')
                "
            >

                <i class="pi pi-table"></i>

                PPC

            </button>


            <button
                type="button"
                :class="{
                    active:
                        activeTab === 'wip'
                }"
                @click="
                    switchTab('wip')
                "
            >

                <i class="pi pi-chart-bar"></i>

                WIP Summary

            </button>

        </nav>


        <Message
            v-if="errorMessage"
            severity="error"
            :closable="false"
            class="dvv-message"
        >
            {{ errorMessage }}
        </Message>


        <!-- =================================================
             PPC TAB
        ================================================== -->

        <template
            v-if="activeTab === 'ppc'"
        >


            <!-- =============================================
                 TOOLBAR
            ============================================== -->

            <section class="dvv-toolbar">

                <div class="dvv-search-wrap">

                    <i class="pi pi-search"></i>


                    <InputText
                        v-model="search"
                        class="dvv-search"
                        placeholder="Search JC No, SO, customer, item, material, WIP..."
                    />


                    <button
                        v-if="search"
                        type="button"
                        class="dvv-clear-search"
                        title="Clear Search"
                        @click="clearSearch"
                    >
                        <i class="pi pi-times"></i>
                    </button>

                </div>


                <div class="dvv-toolbar-actions">

                    <Button
                        :label="
                            totalFilterCount
                                ? `Filters (${totalFilterCount})`
                                : 'Filters'
                        "
                        icon="pi pi-filter"
                        severity="secondary"
                        outlined
                        size="small"
                        :class="{
                            'dvv-active-button':
                                filterOpen ||
                                totalFilterCount
                        }"
                        @click="toggleFilters"
                    />


                    <Button
                        label="Columns"
                        icon="pi pi-table"
                        severity="secondary"
                        outlined
                        size="small"
                        class="dvv-columns-button"
                        @click="openColumns"
                    />


                    <Button
                        label="Export CSV"
                        icon="pi pi-download"
                        severity="secondary"
                        outlined
                        size="small"
                        :loading="exportLoading"
                        @click="exportCsv"
                    />

                </div>

            </section>


            <!-- =============================================
                 ACTIVE GLOBAL DATE
            ============================================== -->

            <div
                v-if="sidebarDate"
                class="dvv-global-date"
            >

                <i class="pi pi-calendar"></i>

                <span>
                    Sidebar date filter:
                </span>

                <strong>
                    {{ formatDate(sidebarDate) }}
                </strong>

            </div>


            <!-- =============================================
                 ADVANCED FILTER PANEL
            ============================================== -->

            <section
                v-if="filterOpen"
                class="dvv-filter-panel"
            >

                <div class="dvv-filter-panel-head">

                    <div>

                        <strong>
                            Filters
                        </strong>

                        <span>
                            Same production filters,
                            compact layout
                        </span>

                    </div>


                    <Button
                        v-if="advancedFilterCount"
                        label="Clear"
                        icon="pi pi-filter-slash"
                        severity="secondary"
                        text
                        size="small"
                        @click="clearAdvancedFilters"
                    />

                </div>


                <div class="dvv-filter-grid">

                    <label>

                        <span>
                            WIP Status
                        </span>

                        <Select
                            v-model="filters.wip"
                            :options="wipOptions"
                            placeholder="All"
                            showClear
                            @change="applyAdvancedFilters"
                        />

                    </label>


                    <label>

                        <span>
                            Final Status
                        </span>

                        <Select
                            v-model="filters.status"
                            :options="
                                statusOptions.length
                                    ? statusOptions
                                    : [
                                        'Pending',
                                        'Completed'
                                    ]
                            "
                            placeholder="All"
                            showClear
                            @change="applyAdvancedFilters"
                        />

                    </label>


                    <label>

                        <span>
                            Delivery From
                        </span>

                        <input
                            v-model="filters.delivery_from"
                            type="date"
                            @change="applyAdvancedFilters"
                        />

                    </label>


                    <label>

                        <span>
                            Delivery To
                        </span>

                        <input
                            v-model="filters.delivery_to"
                            type="date"
                            @change="applyAdvancedFilters"
                        />

                    </label>


                    <label>

                        <span>
                            Overdue
                        </span>

                        <Select
                            v-model="filters.overdue"
                            :options="overdueOptions"
                            optionLabel="label"
                            optionValue="value"
                            @change="applyAdvancedFilters"
                        />

                    </label>


                    <label>

                        <span>
                            Subcontracting
                        </span>

                        <Select
                            v-model="filters.subcontracting"
                            :options="subcontractOptions"
                            optionLabel="label"
                            optionValue="value"
                            @change="applyAdvancedFilters"
                        />

                    </label>


                    <label
                        v-if="
                            supervisorOptions.length
                        "
                    >

                        <span>
                            Supervisor
                        </span>

                        <Select
                            v-model="
                                filters.supervisor_user_id
                            "
                            :options="
                                supervisorSelectOptions
                            "
                            optionLabel="label"
                            optionValue="value"
                            @change="applyAdvancedFilters"
                        />

                    </label>


                    <label
                        v-if="canSeePriority"
                    >

                        <span>
                            Priority
                        </span>

                        <Select
                            v-model="
                                filters.urgent_only
                            "
                            :options="
                                urgentOptions
                            "
                            optionLabel="label"
                            optionValue="value"
                            @change="applyAdvancedFilters"
                        />

                    </label>

                </div>


                <div
                    v-if="excelFilterCount"
                    class="dvv-active-excel-filters"
                >

                    <span>
                        Column Filters:
                    </span>


                    <button
                        v-for="
                            (values, key)
                            in excelFilters
                        "
                        :key="key"
                        type="button"
                        class="dvv-filter-chip"
                    >

                        {{ key }}

                        <strong>
                            {{ values.length }}
                        </strong>

                    </button>


                    <Button
                        label="Clear Column Filters"
                        severity="secondary"
                        text
                        size="small"
                        @click="
                            clearAllHeaderFilters
                        "
                    />

                </div>

            </section>


            <!-- =============================================
                 TABLE CARD
            ============================================== -->

            <section class="dvv-table-card">


                <div class="dvv-table-info">

                    <div>

                        <strong>
                            PPC Records
                        </strong>

                        <span>
                            {{
                                Number(total || 0)
                                    .toLocaleString(
                                        'en-IN'
                                    )
                            }}
                            records
                        </span>

                    </div>


                    <div class="dvv-table-info-right">

                        <span>
                            {{
                                visibleColumns.length
                            }}
                            columns visible
                        </span>

                        <span>
                            Click WIP status for
                            stage preview
                        </span>

                    </div>

                </div>


                <div
                    v-if="
                        loading &&
                        !rows.length
                    "
                    class="dvv-table-loading"
                >

                    <Skeleton
                        v-for="n in 10"
                        :key="n"
                        height="39px"
                        class="dvv-skeleton"
                    />

                </div>


                <div
                    v-else
                    class="dvv-table-scroll"
                >

                    <table class="dvv-table">

                        <thead>

                            <tr>

                                <th
                                    v-for="
                                        column
                                        in visibleColumns
                                    "
                                    :key="column.key"
                                    :style="{
                                        minWidth:
                                            column.width +
                                            'px',
                                        width:
                                            column.width +
                                            'px'
                                    }"
                                    :data-key="
                                        column.key
                                    "
                                >

                                    <div class="dvv-th-inner">

                                        <button
                                            type="button"
                                            class="dvv-th-sort"
                                            :class="{
                                                disabled:
                                                    column.noSort
                                            }"
                                            @click="
                                                sortBy(
                                                    column
                                                )
                                            "
                                        >

                                            <span>
                                                {{
                                                    column.label
                                                }}
                                            </span>


                                            <i
                                                v-if="
                                                    !column.noSort
                                                "
                                                :class="
                                                    sortIcon(
                                                        column
                                                    )
                                                "
                                            ></i>

                                        </button>


                                        <button
                                            v-if="
                                                isFilterable(
                                                    column.key
                                                )
                                            "
                                            type="button"
                                            class="dvv-th-filter"
                                            :class="{
                                                active:
                                                    isExcelFilterActive(
                                                        column.key
                                                    )
                                            }"
                                            title="Filter column"
                                            @click="
                                                openHeaderFilter(
                                                    $event,
                                                    column
                                                )
                                            "
                                        >

                                            <i
                                                class="pi pi-filter"
                                            ></i>

                                        </button>

                                    </div>

                                </th>


                                <th
                                    class="dvv-action-head"
                                >
                                    Actions
                                </th>

                            </tr>

                        </thead>


                        <tbody>

                            <tr
                                v-if="
                                    !loading &&
                                    !rows.length
                                "
                            >

                                <td
                                    :colspan="
                                        visibleColumns.length +
                                        1
                                    "
                                    class="dvv-empty"
                                >

                                    <i
                                        class="pi pi-search"
                                    ></i>

                                    <strong>
                                        No records found
                                    </strong>

                                    <span>
                                        Change search or
                                        filters and try
                                        again.
                                    </span>

                                </td>

                            </tr>


                            <tr
                                v-for="
                                    row
                                    in rows
                                "
                                v-else
                                :key="
                                    String(
                                        row.item_id ||
                                        ''
                                    ) +
                                    ':' +
                                    String(
                                        row.job_card_no ||
                                        ''
                                    ) +
                                    ':' +
                                    String(
                                        row.item_name ||
                                        ''
                                    )
                                "
                                :class="
                                    rowClass(row)
                                "
                                @click="
                                    openDetail(row)
                                "
                            >

                                <td
                                    v-for="
                                        column
                                        in visibleColumns
                                    "
                                    :key="
                                        column.key
                                    "
                                    :class="
                                        cellClass(
                                            row,
                                            column
                                        )
                                    "
                                    :data-key="
                                        column.key
                                    "
                                >


                                    <!-- URGENT -->

                                    <template
                                        v-if="
                                            column.key ===
                                            'is_priority'
                                        "
                                    >

                                        <button
                                            type="button"
                                            class="dvv-priority"
                                            :class="{
                                                active:
                                                    Number(
                                                        row.is_priority ||
                                                        0
                                                    )
                                            }"
                                            :title="
                                                Number(
                                                    row.is_priority ||
                                                    0
                                                )
                                                    ? 'Urgent'
                                                    : 'Normal Priority'
                                            "
                                            @click.stop="
                                                openPriorityPreview(
                                                    row
                                                )
                                            "
                                        >

                                            <i
                                                :class="
                                                    Number(
                                                        row.is_priority ||
                                                        0
                                                    )
                                                        ? 'pi pi-star-fill'
                                                        : 'pi pi-star'
                                                "
                                            ></i>

                                        </button>

                                    </template>


                                    <!-- JC NUMBER -->

                                    <template
                                        v-else-if="
                                            column.key ===
                                            'job_card_no'
                                        "
                                    >

                                        <button
                                            type="button"
                                            class="dvv-jc-link"
                                            @click.stop="
                                                openDetail(
                                                    row
                                                )
                                            "
                                        >
                                            {{
                                                text(
                                                    row.job_card_no
                                                )
                                            }}
                                        </button>

                                    </template>


                                    <!-- WIP STATUS -->

                                    <template
                                        v-else-if="
                                            column.key ===
                                            'wip_status'
                                        "
                                    >

                                        <button
                                            type="button"
                                            class="dvv-wip-pill"
                                            :class="
                                                wipClass(
                                                    row.wip_status
                                                )
                                            "
                                            @click.stop="
                                                openStagePreview(
                                                    row
                                                )
                                            "
                                        >

                                            <span>
                                                {{
                                                    text(
                                                        row.wip_status
                                                    )
                                                }}
                                            </span>


                                            <i
                                                class="pi pi-angle-right"
                                            ></i>

                                        </button>


                                        <span
                                            v-if="
                                                canSeeRmStatus &&
                                                row.rm_hold_reason
                                            "
                                            class="dvv-rm-status"
                                            :class="
                                                String(
                                                    row.rm_hold_reason
                                                ).toLowerCase()
                                            "
                                        >
                                            {{
                                                row.rm_hold_reason
                                            }}
                                        </span>

                                    </template>


                                    <!-- STATUS -->

                                    <template
                                        v-else-if="
                                            column.key ===
                                            'final_status'
                                        "
                                    >

                                        <Tag
                                            :value="
                                                text(
                                                    row.final_status
                                                )
                                            "
                                            :severity="
                                                statusSeverity(
                                                    row.final_status
                                                )
                                            "
                                            rounded
                                            class="dvv-table-tag"
                                        />

                                    </template>


                                    <!-- REMARKS / LONG TEXT -->

                                    <template
                                        v-else-if="
                                            column.key ===
                                                'remarks' ||
                                            column.key ===
                                                'item_name' ||
                                            column.key ===
                                                'customer_name' ||
                                            column.key ===
                                                'material' ||
                                            column.key ===
                                                'last_audit'
                                        "
                                    >

                                        <span
                                            class="dvv-cell-ellipsis"
                                            :title="
                                                text(
                                                    row[
                                                        column.key
                                                    ]
                                                )
                                            "
                                        >
                                            {{
                                                displayValue(
                                                    row,
                                                    column
                                                )
                                            }}
                                        </span>

                                    </template>


                                    <!-- NORMAL -->

                                    <template
                                        v-else
                                    >

                                        {{
                                            displayValue(
                                                row,
                                                column
                                            )
                                        }}

                                    </template>

                                </td>


                                <!-- ACTIONS -->

                                <td
                                    class="dvv-row-actions"
                                    @click.stop
                                >

                                    <button
                                        type="button"
                                        title="View"
                                        @click="
                                            openDetail(
                                                row
                                            )
                                        "
                                    >
                                        <i
                                            class="pi pi-eye"
                                        ></i>
                                    </button>


                                    <button
                                        type="button"
                                        title="Edit Preview"
                                        @click="
                                            openEditPreview(
                                                row
                                            )
                                        "
                                    >
                                        <i
                                            class="pi pi-pencil"
                                        ></i>
                                    </button>

                                </td>

                            </tr>

                        </tbody>

                    </table>

                </div>


                <!-- =========================================
                     PAGINATION
                ========================================== -->

                <footer class="dvv-pagination">

                    <div class="dvv-page-count">

                        Showing

                        <strong>
                            {{ firstRecord }}
                        </strong>

                        –

                        <strong>
                            {{ lastRecord }}
                        </strong>

                        of

                        <strong>
                            {{
                                Number(total || 0)
                                    .toLocaleString(
                                        'en-IN'
                                    )
                            }}
                        </strong>

                    </div>


                    <div class="dvv-pagination-actions">

                        <span>
                            Rows
                        </span>


                        <Select
                            v-model="perPage"
                            :options="
                                perPageOptions
                            "
                            class="dvv-per-page"
                            @change="
                                changePerPage
                            "
                        />


                        <Button
                            icon="pi pi-angle-left"
                            severity="secondary"
                            outlined
                            size="small"
                            :disabled="
                                page <= 1 ||
                                loading
                            "
                            aria-label="Previous Page"
                            @click="
                                previousPage
                            "
                        />


                        <span class="dvv-page-label">
                            Page
                            <strong>
                                {{ page }}
                            </strong>
                            of
                            <strong>
                                {{ totalPages }}
                            </strong>
                        </span>


                        <Button
                            icon="pi pi-angle-right"
                            severity="secondary"
                            outlined
                            size="small"
                            :disabled="
                                page >=
                                    totalPages ||
                                loading
                            "
                            aria-label="Next Page"
                            @click="
                                nextPage
                            "
                        />

                    </div>

                </footer>

            </section>

        </template>


        <!-- =================================================
             WIP SUMMARY
        ================================================== -->

        <template v-else>

            <section class="dvv-wip-toolbar">

                <div>

                    <h2>
                        WIP Summary
                    </h2>

                    <span>
                        Process completions by date.
                        Click any count to see job cards.
                    </span>

                </div>


                <div class="dvv-wip-date-controls">

                    <label>

                        <span>
                            From
                        </span>

                        <input
                            v-model="wipFrom"
                            type="date"
                        />

                    </label>


                    <label>

                        <span>
                            To
                        </span>

                        <input
                            v-model="wipTo"
                            type="date"
                        />

                    </label>


                    <Button
                        label="Apply"
                        icon="pi pi-refresh"
                        size="small"
                        :loading="
                            wipSummaryLoading
                        "
                        @click="
                            loadWipSummary
                        "
                    />

                </div>

            </section>


            <section class="dvv-wip-card">

                <div
                    v-if="
                        wipSummaryLoading &&
                        !wipRows.length
                    "
                    class="dvv-wip-loading"
                >

                    <ProgressSpinner
                        style="
                            width: 36px;
                            height: 36px
                        "
                    />

                    <span>
                        Loading WIP Summary...
                    </span>

                </div>


                <div
                    v-else-if="
                        !wipRows.length
                    "
                    class="dvv-empty dvv-wip-empty"
                >

                    <i class="pi pi-chart-bar"></i>

                    <strong>
                        No WIP summary data
                    </strong>

                    <span>
                        No process completions were
                        found for this date range.
                    </span>

                </div>


                <div
                    v-else
                    class="dvv-wip-scroll"
                >

                    <table class="dvv-wip-table">

                        <thead>

                            <tr>

                                <th class="dvv-wip-date-col">
                                    Date
                                </th>


                                <th
                                    v-for="
                                        process
                                        in wipProcesses
                                    "
                                    :key="process"
                                >
                                    {{ process }}
                                </th>

                            </tr>

                        </thead>


                        <tbody>

                            <tr
                                v-for="
                                    row
                                    in wipRows
                                "
                                :key="row.date"
                            >

                                <td class="dvv-wip-date-cell">

                                    {{
                                        formatDate(
                                            row.date
                                        )
                                    }}

                                </td>


                                <td
                                    v-for="
                                        process
                                        in wipProcesses
                                    "
                                    :key="process"
                                    class="dvv-wip-number"
                                >

                                    <button
                                        v-if="
                                            Number(
                                                row[
                                                    process
                                                ] || 0
                                            ) > 0
                                        "
                                        type="button"
                                        @click="
                                            openWipDetail(
                                                row.date,
                                                process,
                                                row[
                                                    process
                                                ]
                                            )
                                        "
                                    >

                                        {{
                                            row[
                                                process
                                            ]
                                        }}

                                    </button>


                                    <span v-else>
                                        —
                                    </span>

                                </td>

                            </tr>

                        </tbody>

                    </table>

                </div>

            </section>

        </template>


        <!-- =================================================
             COLUMN CHOOSER
        ================================================== -->

        <div
            v-if="columnsOpen"
            class="dvv-column-popover"
            :style="{
                top:
                    columnsPosition.top +
                    'px',
                left:
                    columnsPosition.left +
                    'px'
            }"
            @click.stop
        >

            <div class="dvv-popover-head">

                <strong>
                    Columns
                </strong>

                <button
                    type="button"
                    @click="
                        closeColumns
                    "
                >
                    <i class="pi pi-times"></i>
                </button>

            </div>


            <div class="dvv-column-list">

                <label
                    v-for="
                        column
                        in baseColumns
                    "
                    :key="column.key"
                >

                    <input
                        type="checkbox"
                        :checked="
                            draftColumnVisible(
                                column.key
                            )
                        "
                        @change="
                            toggleDraftColumn(
                                column.key,
                                $event.target
                                    .checked
                            )
                        "
                    />

                    <span>
                        {{ column.label }}
                    </span>

                </label>

            </div>


            <div class="dvv-popover-actions">

                <button
                    type="button"
                    class="dvv-link-button"
                    @click="
                        showAllColumns
                    "
                >
                    Show All
                </button>


                <div>

                    <Button
                        label="Cancel"
                        severity="secondary"
                        text
                        size="small"
                        @click="
                            closeColumns
                        "
                    />


                    <Button
                        label="Apply"
                        size="small"
                        @click="
                            applyColumns
                        "
                    />

                </div>

            </div>

        </div>


        <!-- =================================================
             EXCEL HEADER FILTER POPOVER
        ================================================== -->

        <div
            v-if="headerFilter.open"
            class="dvv-header-filter-popover"
            :style="{
                top:
                    headerFilter.top +
                    'px',
                left:
                    headerFilter.left +
                    'px'
            }"
            @click.stop
        >

            <div class="dvv-popover-head">

                <div>

                    <strong>
                        {{ headerFilter.label }}
                    </strong>

                    <span>
                        Filter values
                    </span>

                </div>


                <button
                    type="button"
                    @click="
                        closeHeaderFilter
                    "
                >

                    <i class="pi pi-times"></i>

                </button>

            </div>


            <div class="dvv-filter-sort-actions">

                <button
                    type="button"
                    @click="
                        sortCol =
                            headerFilter.key;
                        sortOrder = 'asc';
                        page = 1;
                        closeHeaderFilter();
                        loadPpcData();
                    "
                >

                    <i class="pi pi-sort-amount-up"></i>

                    Sort A → Z

                </button>


                <button
                    type="button"
                    @click="
                        sortCol =
                            headerFilter.key;
                        sortOrder = 'desc';
                        page = 1;
                        closeHeaderFilter();
                        loadPpcData();
                    "
                >

                    <i class="pi pi-sort-amount-down"></i>

                    Sort Z → A

                </button>

            </div>


            <div class="dvv-filter-search">

                <i class="pi pi-search"></i>

                <input
                    v-model="
                        headerFilter.search
                    "
                    type="text"
                    placeholder="Search values..."
                />

            </div>


            <div
                v-if="
                    headerFilter.loading
                "
                class="dvv-filter-loading"
            >

                <ProgressSpinner
                    style="
                        width: 28px;
                        height: 28px
                    "
                />

            </div>


            <template v-else>

                <div class="dvv-filter-select-actions">

                    <button
                        type="button"
                        @click="
                            selectAllHeaderValues
                        "
                    >
                        Select All
                    </button>

                    <button
                        type="button"
                        @click="
                            clearHeaderValuesDraft
                        "
                    >
                        Deselect All
                    </button>

                </div>


                <div class="dvv-filter-values">

                    <label
                        v-for="
                            option
                            in visibleHeaderFilterOptions
                        "
                        :key="
                            String(option)
                        "
                    >

                        <input
                            type="checkbox"
                            :checked="
                                headerFilter.draft
                                    .includes(
                                        String(option)
                                    )
                            "
                            @change="
                                toggleHeaderFilterValue(
                                    option,
                                    $event.target
                                        .checked
                                )
                            "
                        />

                        <span>

                            {{
                                option === ''
                                    ? '(Blanks)'
                                    : option
                            }}

                        </span>

                    </label>


                    <div
                        v-if="
                            !visibleHeaderFilterOptions
                                .length
                        "
                        class="dvv-filter-no-values"
                    >
                        No matching values.
                    </div>

                </div>


                <div
                    v-if="
                        headerFilter.message
                    "
                    class="dvv-filter-message"
                >
                    {{
                        headerFilter.message
                    }}
                </div>


                <div class="dvv-popover-actions">

                    <button
                        type="button"
                        class="dvv-link-button danger"
                        @click="
                            clearCurrentHeaderFilter
                        "
                    >
                        Clear Filter
                    </button>


                    <div>

                        <Button
                            label="Cancel"
                            severity="secondary"
                            text
                            size="small"
                            @click="
                                closeHeaderFilter
                            "
                        />


                        <Button
                            label="Apply"
                            size="small"
                            @click="
                                applyHeaderFilter
                            "
                        />

                    </div>

                </div>

            </template>

        </div>


        <!-- =================================================
             RIGHT DETAIL DRAWER
        ================================================== -->

        <div
            v-if="sideOpen"
            class="dvv-drawer-backdrop"
            @click.self="
                closeSidePanel
            "
        >

            <aside class="dvv-drawer">

                <header class="dvv-drawer-head">

                    <div>

                        <span>
                            {{ sideTitle }}
                        </span>

                        <strong>
                            {{
                                text(
                                    sideRow
                                        ?.job_card_no
                                )
                            }}
                        </strong>

                    </div>


                    <Button
                        icon="pi pi-times"
                        severity="secondary"
                        text
                        rounded
                        aria-label="Close"
                        @click="
                            closeSidePanel
                        "
                    />

                </header>


                <div class="dvv-drawer-body">


                    <!-- =====================================
                         BASIC DETAIL
                    ====================================== -->

                    <template
                        v-if="
                            sideMode ===
                            'detail'
                        "
                    >

                        <div class="dvv-detail-title">

                            <div>

                                <h2>
                                    {{
                                        text(
                                            sideRow
                                                ?.item_name
                                        )
                                    }}
                                </h2>

                                <span>
                                    {{
                                        text(
                                            sideRow
                                                ?.customer_name
                                        )
                                    }}
                                </span>

                            </div>


                            <Tag
                                :value="
                                    text(
                                        sideRow
                                            ?.final_status
                                    )
                                "
                                :severity="
                                    statusSeverity(
                                        sideRow
                                            ?.final_status
                                    )
                                "
                                rounded
                            />

                        </div>


                        <div class="dvv-detail-grid">

                            <div>
                                <span>SO No</span>
                                <strong>
                                    {{
                                        text(
                                            sideRow
                                                ?.so_no
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>WO No</span>
                                <strong>
                                    {{
                                        text(
                                            sideRow
                                                ?.work_order_no
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Parent Code</span>
                                <strong>
                                    {{
                                        text(
                                            sideRow
                                                ?.parent_code
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Child Code</span>
                                <strong>
                                    {{
                                        text(
                                            sideRow
                                                ?.child_code
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>SO Qty</span>
                                <strong>
                                    {{
                                        text(
                                            sideRow
                                                ?.so_qty
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Actual Qty</span>
                                <strong>
                                    {{
                                        text(
                                            sideRow
                                                ?.actual_qty
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Delivery</span>
                                <strong>
                                    {{
                                        formatDate(
                                            sideRow
                                                ?.delivery_date
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Remaining Days</span>
                                <strong>
                                    {{
                                        text(
                                            sideRow
                                                ?.remaining_days
                                        )
                                    }}
                                </strong>
                            </div>

                        </div>


                        <section class="dvv-detail-section">

                            <div class="dvv-section-label">
                                Current WIP
                            </div>


                            <button
                                type="button"
                                class="dvv-detail-wip"
                                @click="
                                    openStagePreview(
                                        sideRow
                                    )
                                "
                            >

                                <span
                                    class="dvv-wip-pill"
                                    :class="
                                        wipClass(
                                            sideRow
                                                ?.wip_status
                                        )
                                    "
                                >
                                    {{
                                        text(
                                            sideRow
                                                ?.wip_status
                                        )
                                    }}
                                </span>


                                <i
                                    class="pi pi-angle-right"
                                ></i>

                            </button>

                        </section>


                        <section class="dvv-detail-section">

                            <div class="dvv-section-label">
                                Material
                            </div>

                            <p>
                                {{
                                    text(
                                        sideRow
                                            ?.material
                                    )
                                }}
                            </p>

                        </section>


                        <section class="dvv-detail-section">

                            <div class="dvv-section-label">
                                Remarks
                            </div>

                            <p>
                                {{
                                    text(
                                        sideRow
                                            ?.remarks
                                    )
                                }}
                            </p>

                        </section>


                        <section
                            v-if="
                                sideRow
                                    ?.last_audit
                            "
                            class="dvv-detail-section"
                        >

                            <div class="dvv-section-label">
                                Last Updated
                            </div>

                            <p>
                                {{
                                    sideRow
                                        .last_audit
                                }}
                            </p>

                        </section>

                    </template>


                    <!-- =====================================
                         EDIT PREVIEW
                    ====================================== -->

                    <template
                        v-else-if="
                            sideMode ===
                            'edit'
                        "
                    >

                        <div class="dvv-pilot-banner">

                            <i class="pi pi-lock"></i>

                            <div>

                                <strong>
                                    Safe Vue Pilot
                                </strong>

                                <span>
                                    Editing is intentionally
                                    read-only here until this
                                    Data View UX is approved.
                                </span>

                            </div>

                        </div>


                        <div class="dvv-preview-form">

                            <label>

                                <span>
                                    JC No
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.job_card_no ||
                                        ''
                                    "
                                    readonly
                                />

                                <small
                                    v-if="
                                        fieldEditable(
                                            'job_card_no'
                                        )
                                    "
                                >
                                    Editable on original page
                                </small>

                            </label>


                            <label>

                                <span>
                                    SO No
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.so_no ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label>

                                <span>
                                    Customer
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.customer_name ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label>

                                <span>
                                    WO No
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.work_order_no ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label>

                                <span>
                                    Parent Code
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.parent_code ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label>

                                <span>
                                    Child Code
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.child_code ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label class="wide">

                                <span>
                                    Item Name
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.item_name ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label class="wide">

                                <span>
                                    Material
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.material ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label>

                                <span>
                                    SO Qty
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.so_qty ??
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label>

                                <span>
                                    Actual Qty
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.actual_qty ??
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label class="wide">

                                <span>
                                    Delivery Date
                                </span>

                                <input
                                    :value="
                                        sideRow
                                            ?.delivery_date ||
                                        ''
                                    "
                                    readonly
                                />

                            </label>


                            <label class="wide">

                                <span>
                                    Remarks
                                </span>

                                <textarea
                                    :value="
                                        sideRow
                                            ?.remarks ||
                                        ''
                                    "
                                    rows="4"
                                    readonly
                                ></textarea>

                            </label>

                        </div>


                        <Button
                            label="Open Original Data View to Edit"
                            icon="pi pi-external-link"
                            class="dvv-full-button"
                            @click="
                                openOriginalPage
                            "
                        />

                    </template>


                    <!-- =====================================
                         STAGE PREVIEW
                    ====================================== -->

                    <template
                        v-else-if="
                            sideMode ===
                            'stage'
                        "
                    >

                        <div
                            v-if="
                                stageLoading
                            "
                            class="dvv-drawer-loading"
                        >

                            <ProgressSpinner
                                style="
                                    width: 34px;
                                    height: 34px
                                "
                            />

                            <span>
                                Loading current stage...
                            </span>

                        </div>


                        <template v-else>

                            <div class="dvv-pilot-banner">

                                <i class="pi pi-lock"></i>

                                <div>

                                    <strong>
                                        Stage Preview
                                    </strong>

                                    <span>
                                        The familiar WIP click
                                        is preserved. Actual stage
                                        movement remains on the
                                        original page during this
                                        UX pilot.
                                    </span>

                                </div>

                            </div>


                            <Message
                                v-if="
                                    stagePayload
                                        ?.error
                                "
                                severity="error"
                                :closable="false"
                            >
                                {{
                                    stagePayload.error
                                }}
                            </Message>


                            <template v-else>

                                <div class="dvv-stage-current">

                                    <span>
                                        Current Process
                                    </span>

                                    <strong>
                                        {{
                                            text(
                                                stageItem
                                                    ?.wip_status ||
                                                sideRow
                                                    ?.wip_status
                                            )
                                        }}
                                    </strong>

                                </div>


                                <div class="dvv-stage-arrow">

                                    <i
                                        class="pi pi-arrow-down"
                                    ></i>

                                </div>


                                <div class="dvv-stage-next">

                                    <span>
                                        Move To / Next Process
                                    </span>

                                    <strong>
                                        {{
                                            previewNextProcess ||
                                            'Use existing stage workflow'
                                        }}
                                    </strong>

                                </div>


                                <div class="dvv-detail-grid dvv-stage-qty">

                                    <div>
                                        <span>Planned Qty</span>
                                        <strong>
                                            {{
                                                text(
                                                    stageItem
                                                        ?.job_card_qty ||
                                                    stageItem
                                                        ?.so_qty ||
                                                    sideRow
                                                        ?.so_qty
                                                )
                                            }}
                                        </strong>
                                    </div>


                                    <div>
                                        <span>Actual Qty</span>
                                        <strong>
                                            {{
                                                text(
                                                    stageItem
                                                        ?.actual_qty ??
                                                    sideRow
                                                        ?.actual_qty
                                                )
                                            }}
                                        </strong>
                                    </div>


                                    <div>
                                        <span>Days in Stage</span>
                                        <strong>
                                            {{
                                                text(
                                                    sideRow
                                                        ?.wip_stage_days
                                                )
                                            }}
                                        </strong>
                                    </div>


                                    <div>
                                        <span>Subcontractor</span>
                                        <strong>
                                            {{
                                                text(
                                                    sideRow
                                                        ?.vendor_name
                                                )
                                            }}
                                        </strong>
                                    </div>

                                </div>


                                <div
                                    v-if="
                                        sideRow
                                            ?.rm_hold_reason
                                    "
                                    class="dvv-rm-preview"
                                >

                                    <span>
                                        Raw Material Status
                                    </span>

                                    <strong>
                                        {{
                                            sideRow
                                                .rm_hold_reason
                                        }}
                                    </strong>

                                </div>


                                <Button
                                    label="Open Original Stage Change"
                                    icon="pi pi-external-link"
                                    class="dvv-full-button"
                                    @click="
                                        openOriginalPage
                                    "
                                />

                            </template>

                        </template>

                    </template>


                    <!-- =====================================
                         PRIORITY PREVIEW
                    ====================================== -->

                    <template
                        v-else-if="
                            sideMode ===
                            'priority'
                        "
                    >

                        <div class="dvv-priority-preview">

                            <div
                                class="dvv-priority-large"
                                :class="{
                                    active:
                                        Number(
                                            sideRow
                                                ?.is_priority ||
                                            0
                                        )
                                }"
                            >

                                <i
                                    :class="
                                        Number(
                                            sideRow
                                                ?.is_priority ||
                                            0
                                        )
                                            ? 'pi pi-star-fill'
                                            : 'pi pi-star'
                                    "
                                ></i>

                            </div>


                            <h2>
                                {{
                                    Number(
                                        sideRow
                                            ?.is_priority ||
                                        0
                                    )
                                        ? 'Urgent Job Card'
                                        : 'Normal Priority'
                                }}
                            </h2>


                            <p>
                                Priority changing remains
                                on the original Data View
                                until this Vue screen is
                                approved.
                            </p>


                            <Button
                                label="Open Original Data View"
                                icon="pi pi-external-link"
                                @click="
                                    openOriginalPage
                                "
                            />

                        </div>

                    </template>

                </div>

            </aside>

        </div>


        <!-- =================================================
             WIP DETAIL MODAL
        ================================================== -->

        <div
            v-if="wipDetailOpen"
            class="dvv-modal-backdrop"
            @click.self="
                closeWipDetail
            "
        >

            <section class="dvv-wip-modal">

                <header>

                    <div>

                        <span>
                            Completed Process
                        </span>

                        <h2>
                            {{
                                wipDetailProcess
                            }}
                        </h2>

                        <p>
                            {{
                                formatDate(
                                    wipDetailDate
                                )
                            }}
                        </p>

                    </div>


                    <Button
                        icon="pi pi-times"
                        severity="secondary"
                        text
                        rounded
                        @click="
                            closeWipDetail
                        "
                    />

                </header>


                <div
                    v-if="
                        wipDetailLoading
                    "
                    class="dvv-modal-loading"
                >

                    <ProgressSpinner
                        style="
                            width: 34px;
                            height: 34px
                        "
                    />

                    Loading completed job cards...

                </div>


                <div
                    v-else
                    class="dvv-wip-detail-body"
                >

                    <div class="dvv-wip-detail-count">

                        <strong>
                            {{
                                wipDetailRows.length
                            }}
                        </strong>

                        record<span
                            v-if="
                                wipDetailRows.length !==
                                1
                            "
                        >s</span>

                    </div>


                    <div class="dvv-wip-detail-table-wrap">

                        <table class="dvv-wip-detail-table">

                            <thead>

                                <tr>
                                    <th>JC No</th>
                                    <th>Item</th>
                                    <th>Completed By</th>
                                    <th>Completed At</th>
                                    <th>Advanced To</th>
                                </tr>

                            </thead>


                            <tbody>

                                <tr
                                    v-for="
                                        (
                                            row,
                                            index
                                        )
                                        in wipDetailRows
                                    "
                                    :key="
                                        index +
                                        ':' +
                                        row.job_card_no
                                    "
                                >

                                    <td>
                                        <button
                                            type="button"
                                            class="dvv-jc-link"
                                            @click="
                                                search =
                                                    row.job_card_no;
                                                closeWipDetail();
                                                switchTab(
                                                    'ppc'
                                                );
                                            "
                                        >
                                            {{
                                                text(
                                                    row.job_card_no
                                                )
                                            }}
                                        </button>
                                    </td>

                                    <td>
                                        {{
                                            text(
                                                row.item_name
                                            )
                                        }}
                                    </td>

                                    <td>
                                        {{
                                            text(
                                                row.changed_by
                                            )
                                        }}
                                    </td>

                                    <td>
                                        {{
                                            text(
                                                row.changed_at_ist
                                            )
                                        }}
                                    </td>

                                    <td>
                                        {{
                                            text(
                                                row.advanced_to
                                            )
                                        }}
                                    </td>

                                </tr>


                                <tr
                                    v-if="
                                        !wipDetailRows.length
                                    "
                                >
                                    <td
                                        colspan="5"
                                        class="dvv-empty-small"
                                    >
                                        No records found.
                                    </td>
                                </tr>

                            </tbody>

                        </table>

                    </div>

                </div>

            </section>

        </div>


        <!-- =================================================
             PILOT FOOTNOTE
        ================================================== -->

        <div class="dvv-pilot-footnote">

            <i class="pi pi-shield"></i>

            <span>
                Vue pilot is using the existing Flask/MySQL
                read APIs. Production-changing actions remain
                on the original Data View until UX approval.
            </span>

        </div>

    </main>

</template>
