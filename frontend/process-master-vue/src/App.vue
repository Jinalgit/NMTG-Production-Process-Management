<script setup>
import {
    computed,
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
import Tree from "primevue/tree";


/* =========================================================
   STATE
========================================================= */

const loading = ref(false);
const detailLoading = ref(false);
const flowLoading = ref(false);

const errorMessage = ref("");

const treeNodes = ref([]);
const expandedKeys = ref({});
const selectionKeys = ref({});

const selectedItem = ref(null);

const sideMode = ref("");
const selectedBomNo = ref("");
const processFlow = ref([]);

const page = ref(1);
const perPage = ref(30);
const total = ref(0);

const search = ref("");

const bomLevel = ref("top");
const makeBuy = ref("");
const processStatus = ref("");
const rawMaterial = ref("");

let searchTimer = null;


const stats = ref({
    total_items: 0,
    total_assemblies: 0,
    total_processes: 0
});


/* =========================================================
   FILTER OPTIONS
========================================================= */

const bomLevelOptions = [
    {
        label: "Top Level BOM only",
        value: "top"
    },
    {
        label: "All BOM levels",
        value: "all"
    },
    {
        label: "Child BOM only",
        value: "child"
    },
    {
        label: "Raw Material level only",
        value: "raw"
    }
];


const makeBuyOptions = [
    {
        label: "All Make / Buy",
        value: ""
    },
    {
        label: "A - Make",
        value: "A"
    },
    {
        label: "I - Buy",
        value: "I"
    }
];


const processOptions = [
    {
        label: "All process status",
        value: ""
    },
    {
        label: "Has Process",
        value: "has_process"
    },
    {
        label: "No Process",
        value: "no_process"
    },
    {
        label: "Incomplete Process",
        value: "incomplete_process"
    }
];


const rawOptions = [
    {
        label: "All Raw Material",
        value: ""
    },
    {
        label: "Has Raw Material",
        value: "has_raw_material"
    },
    {
        label: "No Raw Material",
        value: "no_raw_material"
    },
    {
        label: "Multiple Raw Materials",
        value: "multiple_raw_material"
    }
];


/* =========================================================
   COMPUTED
========================================================= */

const loadedCount =
    computed(() => treeNodes.value.length);


const remainingCount =
    computed(() => {

        return Math.max(
            Number(total.value || 0) -
            loadedCount.value,
            0
        );

    });


const hasMore =
    computed(() => {

        return (
            loadedCount.value <
            Number(total.value || 0)
        );

    });


const activeFilterCount =
    computed(() => {

        return [
            makeBuy.value,
            processStatus.value,
            rawMaterial.value,
            (
                bomLevel.value !== "top"
                    ? bomLevel.value
                    : ""
            )
        ].filter(Boolean).length;

    });


const workspaceClass =
    computed(() => ({

        "pmv-workspace-split":
            Boolean(sideMode.value)

    }));


/* =========================================================
   API
========================================================= */

async function api(
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
            "Request failed."
        );

    }


    return data;
}


/* =========================================================
   BASIC HELPERS
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


function makeLabel(value) {

    if (value === "A") {
        return "MAKE";
    }

    if (value === "I") {
        return "BUY";
    }

    return "";
}


function makeSeverity(value) {

    if (value === "A") {
        return "success";
    }

    if (value === "I") {
        return "warn";
    }

    return "secondary";
}


function itemTypeSeverity(value) {

    switch (
        String(value || "")
            .trim()
            .toUpperCase()
    ) {

        case "ASSEMBLY":
            return "info";

        case "RAW_MATERIAL":
            return "warn";

        case "PART":
            return "secondary";

        default:
            return "secondary";
    }
}


/* =========================================================
   TREE BUILDING
========================================================= */

function processNodes(
    item,
    parentKey
) {

    const processes =
        Array.isArray(item.processes)
            ? item.processes
            : [];


    if (!processes.length) {

        return [{
            key:
                `${parentKey}:process:none`,

            label:
                "No Process Routing",

            selectable: false,

            data: {
                kind: "empty-process"
            }
        }];

    }


    return processes.map(
        (process, index) => ({

            key:
                `${parentKey}:process:${index}`,

            label:
                process.process_name ||
                "Process",

            selectable: false,

            data: {
                kind: "process",

                stepNo:
                    process.step_no ||
                    index + 1,

                processName:
                    process.process_name ||
                    ""
            }

        })
    );
}


function rawNodes(
    item,
    parentKey
) {

    const raws =
        Array.isArray(item.raw_materials)
            ? item.raw_materials
            : [];


    if (!raws.length) {

        return [{
            key:
                `${parentKey}:raw:none`,

            label:
                "No Raw Material Found",

            selectable: false,

            data: {
                kind: "empty-raw"
            }
        }];

    }


    return raws.map(
        (raw, index) => {

            const itemCode =
                raw.child_code || "";

            return {

                key:
                    `${parentKey}:raw:${index}:${itemCode}`,

                label:
                    itemCode ||
                    "Raw Material",

                leaf: true,

                data: {
                    kind: "raw-item",

                    itemCode,

                    item: raw
                }

            };

        }
    );
}


function makeItemNode(
    item,
    rootKey,
    index
) {

    const itemCode =
        item.child_code || "";

    const key =
        `${rootKey}:make:${index}:${itemCode}`;


    return {

        key,

        label:
            itemCode,

        data: {
            kind: "make-item",

            itemCode,

            item
        },

        children: [

            {
                key:
                    `${key}:process-group`,

                label:
                    "PROCESS ROUTING",

                selectable: false,

                data: {
                    kind: "process-group",

                    count:
                        Array.isArray(
                            item.processes
                        )
                            ? item.processes.length
                            : 0
                },

                children:
                    processNodes(
                        item,
                        key
                    )
            },

            {
                key:
                    `${key}:raw-group`,

                label:
                    item.raw_material_title ||
                    "RAW MATERIAL",

                selectable: false,

                data: {
                    kind: "raw-group",

                    count:
                        Array.isArray(
                            item.raw_materials
                        )
                            ? item.raw_materials.length
                            : 0
                },

                children:
                    rawNodes(
                        item,
                        key
                    )
            }

        ]

    };
}


function buyItemNode(
    item,
    rootKey,
    index
) {

    const itemCode =
        item.child_code || "";


    return {

        key:
            `${rootKey}:buy:${index}:${itemCode}`,

        label:
            itemCode,

        leaf: true,

        data: {
            kind: "buy-item",

            itemCode,

            item
        }

    };
}


function buildTreeNode(
    bom,
    index
) {

    const bomNo =
        bom.bom_no ||
        "";

    const parentCode =
        bom.parent_code ||
        "";

    const rootKey =
        `bom:${bomNo || parentCode}:${index}`;


    const children = [];


    const buyItems =
        Array.isArray(bom.buy_items)
            ? bom.buy_items
            : [];


    const makeItems =
        Array.isArray(bom.make_items)
            ? bom.make_items
            : [];


    if (buyItems.length) {

        children.push({

            key:
                `${rootKey}:buy-group`,

            label:
                "BUY ITEMS",

            selectable: false,

            data: {
                kind: "buy-group",
                count: buyItems.length
            },

            children:
                buyItems.map(
                    (item, childIndex) =>
                        buyItemNode(
                            item,
                            rootKey,
                            childIndex
                        )
                )

        });

    }


    if (makeItems.length) {

        children.push({

            key:
                `${rootKey}:make-group`,

            label:
                "MAKE ITEMS",

            selectable: false,

            data: {
                kind: "make-group",
                count: makeItems.length
            },

            children:
                makeItems.map(
                    (item, childIndex) =>
                        makeItemNode(
                            item,
                            rootKey,
                            childIndex
                        )
                )

        });

    }


    return {

        key: rootKey,

        label:
            bomNo ||
            parentCode,

        data: {
            kind: "bom",

            bomNo,
            itemCode: parentCode,

            bom,

            buyCount:
                buyItems.length,

            makeCount:
                makeItems.length
        },

        children

    };
}


function buildTree(
    rows,
    offset = 0
) {

    return rows.map(
        (bom, index) =>
            buildTreeNode(
                bom,
                offset + index
            )
    );
}


/* =========================================================
   EXPANSION
========================================================= */

function recursivelyExpand(
    nodes,
    target
) {

    for (const node of nodes) {

        if (
            Array.isArray(node.children) &&
            node.children.length
        ) {

            target[node.key] = true;

            recursivelyExpand(
                node.children,
                target
            );
        }
    }
}


function expandAll() {

    const state = {};

    recursivelyExpand(
        treeNodes.value,
        state
    );

    expandedKeys.value =
        state;
}


function collapseAll() {

    expandedKeys.value = {};
}


function expandFirstBom() {

    const first =
        treeNodes.value[0];

    if (!first) {
        return;
    }


    const state = {};

    state[first.key] = true;


    for (
        const child
        of first.children || []
    ) {

        state[child.key] = true;

    }


    expandedKeys.value =
        state;
}


/* =========================================================
   STATS
========================================================= */

async function loadStats() {

    try {

        const data =
            await api(
                "/api/bom/stats"
            );


        stats.value = {
            total_items:
                Number(
                    data.total_items || 0
                ),

            total_assemblies:
                Number(
                    data.total_assemblies || 0
                ),

            total_processes:
                Number(
                    data.total_processes || 0
                )
        };

    }
    catch (error) {

        console.error(
            "Stats:",
            error
        );

    }
}


/* =========================================================
   TREE API
========================================================= */

function buildTreeUrl(
    requestedPage
) {

    const params =
        new URLSearchParams();


    params.set(
        "page",
        String(requestedPage)
    );

    params.set(
        "per_page",
        String(perPage.value)
    );

    params.set(
        "bom_level",
        bomLevel.value
    );


    if (search.value.trim()) {

        params.set(
            "q",
            search.value.trim()
        );

    }


    if (makeBuy.value) {

        params.set(
            "make_buy",
            makeBuy.value
        );

    }


    if (processStatus.value) {

        params.set(
            "process_status",
            processStatus.value
        );

    }


    if (rawMaterial.value) {

        params.set(
            "raw_material",
            rawMaterial.value
        );

    }


    return (
        "/api/bom/bom_tree_nested?" +
        params.toString()
    );
}


async function loadTree({
    append = false
} = {}) {

    loading.value = true;

    errorMessage.value = "";


    try {

        const requestedPage =
            append
                ? page.value + 1
                : 1;


        const data =
            await api(
                buildTreeUrl(
                    requestedPage
                )
            );


        const rows =
            Array.isArray(data.data)
                ? data.data
                : [];


        total.value =
            Number(
                data.total || 0
            );


        const built =
            buildTree(
                rows,
                append
                    ? treeNodes.value.length
                    : 0
            );


        if (append) {

            treeNodes.value = [
                ...treeNodes.value,
                ...built
            ];

            page.value =
                requestedPage;

        }
        else {

            treeNodes.value =
                built;

            page.value = 1;

            selectionKeys.value = {};

            selectedItem.value = null;

            sideMode.value = "";

            processFlow.value = [];

            selectedBomNo.value = "";


            /*
             * Familiar tree behavior:
             * first BOM is open when page loads.
             */
            expandFirstBom();

        }

    }
    catch (error) {

        console.error(error);

        errorMessage.value =
            error.message ||
            "Unable to load Process Master.";

        if (!append) {
            treeNodes.value = [];
            total.value = 0;
        }

    }
    finally {

        loading.value = false;

    }
}


async function loadMore() {

    if (
        loading.value ||
        !hasMore.value
    ) {
        return;
    }

    await loadTree({
        append: true
    });
}


/* =========================================================
   ITEM DETAIL
========================================================= */

async function loadItemDetail(
    itemCode
) {

    if (!itemCode) {
        return;
    }


    detailLoading.value = true;

    errorMessage.value = "";

    sideMode.value = "item";

    processFlow.value = [];

    selectedBomNo.value = "";


    try {

        const data =
            await api(
                "/api/bom/item/" +
                encodeURIComponent(
                    itemCode
                )
            );


        selectedItem.value =
            data.item ||
            null;

    }
    catch (error) {

        errorMessage.value =
            error.message;

        selectedItem.value =
            null;

    }
    finally {

        detailLoading.value =
            false;

    }
}


/* =========================================================
   TREE SELECT
========================================================= */

function onNodeSelect(node) {

    const kind =
        node?.data?.kind || "";


    if (
        kind === "bom" ||
        kind === "make-item" ||
        kind === "buy-item" ||
        kind === "raw-item"
    ) {

        loadItemDetail(
            node.data.itemCode
        );

    }
}


/* =========================================================
   PROCESS FLOW
========================================================= */

async function openProcessFlow(
    bomNo
) {

    if (!bomNo) {
        return;
    }


    flowLoading.value = true;

    sideMode.value = "flow";

    selectedBomNo.value =
        bomNo;

    selectedItem.value = null;

    selectionKeys.value = {};

    errorMessage.value = "";


    try {

        const data =
            await api(
                "/api/bom/process_flow/" +
                encodeURIComponent(
                    bomNo
                )
            );


        processFlow.value =
            Array.isArray(
                data.process_flow
            )
                ? data.process_flow
                : [];

    }
    catch (error) {

        errorMessage.value =
            error.message;

        processFlow.value = [];

    }
    finally {

        flowLoading.value =
            false;

    }
}


/* =========================================================
   PANEL
========================================================= */

function closeSidePanel() {

    sideMode.value = "";

    selectedItem.value = null;

    processFlow.value = [];

    selectedBomNo.value = "";

    selectionKeys.value = {};
}


/* =========================================================
   FILTERS
========================================================= */

function applyFilters() {

    loadTree();
}


function clearFilters() {

    bomLevel.value = "top";

    makeBuy.value = "";

    processStatus.value = "";

    rawMaterial.value = "";

    loadTree();
}


function clearSearch() {

    search.value = "";
}


/* =========================================================
   SEARCH DEBOUNCE
========================================================= */

watch(
    search,
    () => {

        window.clearTimeout(
            searchTimer
        );


        searchTimer =
            window.setTimeout(
                () => {

                    loadTree();

                },
                350
            );

    }
);


/* =========================================================
   NAVIGATION
========================================================= */

function goOriginal() {

    window.location.href =
        "/page2";
}


/* =========================================================
   REFRESH
========================================================= */

async function refreshPage() {

    await Promise.all([
        loadStats(),
        loadTree()
    ]);
}


/* =========================================================
   MOUNT
========================================================= */

onMounted(
    async () => {

        await Promise.all([
            loadStats(),
            loadTree()
        ]);

    }
);
</script>


<template>

    <main class="pmv-page">


        <!-- =================================================
             HEADER
        ================================================== -->

        <section class="pmv-header">

            <div class="pmv-header-main">

                <div class="pmv-breadcrumb">
                    Masters
                    <i class="pi pi-angle-right"></i>
                    Process Master
                </div>


                <div class="pmv-heading-row">

                    <h1>
                        Process Master
                    </h1>

                    <Tag
                        value="Vue + PrimeVue"
                        severity="info"
                        rounded
                    />

                </div>


                <p>
                    BOM tree, item routing and
                    manufacturing master data.
                </p>

            </div>


            <div class="pmv-header-actions">

                <Button
                    label="Original Page"
                    icon="pi pi-arrow-left"
                    severity="secondary"
                    outlined
                    size="small"
                    @click="goOriginal"
                />

                <Button
                    label="Refresh"
                    icon="pi pi-refresh"
                    severity="secondary"
                    outlined
                    size="small"
                    @click="refreshPage"
                />

            </div>

        </section>


        <!-- =================================================
             COMPACT STATS
        ================================================== -->

        <section class="pmv-stat-strip">

            <div class="pmv-stat">

                <i class="pi pi-box"></i>

                <span>
                    Items
                </span>

                <strong>
                    {{
                        stats.total_items
                            .toLocaleString("en-IN")
                    }}
                </strong>

            </div>


            <div class="pmv-stat">

                <i class="pi pi-sitemap"></i>

                <span>
                    Top Assemblies
                </span>

                <strong>
                    {{
                        stats.total_assemblies
                            .toLocaleString("en-IN")
                    }}
                </strong>

            </div>


            <div class="pmv-stat">

                <i class="pi pi-cog"></i>

                <span>
                    Processes
                </span>

                <strong>
                    {{
                        stats.total_processes
                            .toLocaleString("en-IN")
                    }}
                </strong>

            </div>


            <div class="pmv-stat pmv-stat-bom">

                <i class="pi pi-folder"></i>

                <span>
                    Matching BOMs
                </span>

                <strong>
                    {{
                        Number(total || 0)
                            .toLocaleString("en-IN")
                    }}
                </strong>

            </div>

        </section>


        <!-- =================================================
             SEARCH + FILTERS
        ================================================== -->

        <section class="pmv-toolbar">


            <div class="pmv-search-wrap">

                <i class="pi pi-search"></i>


                <InputText
                    v-model="search"
                    placeholder="Search BOM No, item code, description..."
                    class="pmv-search"
                />


                <button
                    v-if="search"
                    type="button"
                    class="pmv-search-clear"
                    title="Clear search"
                    @click="clearSearch"
                >

                    <i class="pi pi-times"></i>

                </button>

            </div>


            <div class="pmv-tree-actions">

                <Button
                    label="Expand All"
                    icon="pi pi-angle-double-down"
                    severity="secondary"
                    text
                    size="small"
                    @click="expandAll"
                />

                <Button
                    label="Collapse All"
                    icon="pi pi-angle-double-up"
                    severity="secondary"
                    text
                    size="small"
                    @click="collapseAll"
                />

            </div>


            <div class="pmv-filter-grid">

                <Select
                    v-model="bomLevel"
                    :options="bomLevelOptions"
                    optionLabel="label"
                    optionValue="value"
                    class="pmv-filter"
                    @change="applyFilters"
                />


                <Select
                    v-model="makeBuy"
                    :options="makeBuyOptions"
                    optionLabel="label"
                    optionValue="value"
                    class="pmv-filter"
                    @change="applyFilters"
                />


                <Select
                    v-model="processStatus"
                    :options="processOptions"
                    optionLabel="label"
                    optionValue="value"
                    class="pmv-filter"
                    @change="applyFilters"
                />


                <Select
                    v-model="rawMaterial"
                    :options="rawOptions"
                    optionLabel="label"
                    optionValue="value"
                    class="pmv-filter"
                    @change="applyFilters"
                />


                <Button
                    v-if="activeFilterCount"
                    label="Clear Filters"
                    icon="pi pi-filter-slash"
                    severity="secondary"
                    text
                    size="small"
                    @click="clearFilters"
                />

            </div>

        </section>


        <Message
            v-if="errorMessage"
            severity="error"
            :closable="false"
            class="pmv-message"
        >
            {{ errorMessage }}
        </Message>


        <!-- =================================================
             MAIN WORKSPACE
        ================================================== -->

        <section
            class="pmv-workspace"
            :class="workspaceClass"
        >


            <!-- =============================================
                 TREE
            ============================================== -->

            <section class="pmv-tree-card">


                <div class="pmv-card-header">

                    <div>

                        <h2>
                            BOM Tree
                        </h2>

                        <span>
                            Familiar Process Master
                            hierarchy with modern controls
                        </span>

                    </div>


                    <div class="pmv-loaded-count">

                        <strong>
                            {{ loadedCount }}
                        </strong>

                        <span>
                            /
                            {{ total }}
                            loaded
                        </span>

                    </div>

                </div>


                <div
                    v-if="loading && !treeNodes.length"
                    class="pmv-tree-loading"
                >

                    <Skeleton
                        v-for="n in 9"
                        :key="n"
                        height="44px"
                        class="pmv-skeleton"
                    />

                </div>


                <div
                    v-else-if="!treeNodes.length"
                    class="pmv-empty"
                >

                    <i class="pi pi-folder-open"></i>

                    <strong>
                        No BOM records found
                    </strong>

                    <span>
                        Change the search or filters.
                    </span>

                </div>


                <Tree
                    v-else
                    v-model:expandedKeys="expandedKeys"
                    v-model:selectionKeys="selectionKeys"
                    :value="treeNodes"
                    selectionMode="single"
                    class="pmv-tree"
                    @node-select="onNodeSelect"
                >

                    <!-- =====================================
                         CUSTOM TREE NODE
                    ====================================== -->

                    <template #default="{ node }">


                        <!-- BOM ROOT -->

                        <div
                            v-if="node.data?.kind === 'bom'"
                            class="pmv-node pmv-node-bom"
                        >

                            <div class="pmv-node-icon pmv-icon-bom">
                                <i class="pi pi-folder"></i>
                            </div>


                            <div class="pmv-node-copy">

                                <div class="pmv-node-title">

                                    <strong>
                                        {{
                                            node.data.bomNo ||
                                            "BOM"
                                        }}
                                    </strong>

                                    <span class="pmv-parent-code">
                                        {{
                                            node.data.itemCode
                                        }}
                                    </span>

                                </div>


                                <div class="pmv-node-description">

                                    {{
                                        text(
                                            node.data.bom
                                                ?.parent_desc
                                        )
                                    }}

                                </div>

                            </div>


                            <div class="pmv-node-summary">

                                <span class="pmv-count-pill buy">
                                    I
                                    {{ node.data.buyCount }}
                                </span>

                                <span class="pmv-count-pill make">
                                    A
                                    {{ node.data.makeCount }}
                                </span>


                                <Button
                                    v-if="node.data.bomNo"
                                    label="Process Flow"
                                    icon="pi pi-directions"
                                    severity="secondary"
                                    text
                                    size="small"
                                    class="pmv-flow-btn"
                                    @click.stop="
                                        openProcessFlow(
                                            node.data.bomNo
                                        )
                                    "
                                />

                            </div>

                        </div>


                        <!-- GROUP -->

                        <div
                            v-else-if="
                                node.data?.kind === 'buy-group' ||
                                node.data?.kind === 'make-group'
                            "
                            class="pmv-node pmv-node-group"
                            :class="{
                                'pmv-group-buy':
                                    node.data.kind === 'buy-group',

                                'pmv-group-make':
                                    node.data.kind === 'make-group'
                            }"
                        >

                            <div class="pmv-node-icon">
                                <i
                                    :class="
                                        node.data.kind === 'buy-group'
                                            ? 'pi pi-shopping-cart'
                                            : 'pi pi-wrench'
                                    "
                                ></i>
                            </div>


                            <strong>
                                {{ node.label }}
                            </strong>


                            <span class="pmv-group-count">
                                {{ node.data.count }}
                                item<span
                                    v-if="node.data.count !== 1"
                                >s</span>
                            </span>

                        </div>


                        <!-- MAKE / BUY ITEM -->

                        <div
                            v-else-if="
                                node.data?.kind === 'make-item' ||
                                node.data?.kind === 'buy-item'
                            "
                            class="pmv-node pmv-node-item"
                        >

                            <div
                                class="pmv-makebuy-box"
                                :class="
                                    node.data.item?.make_buy === 'A'
                                        ? 'make'
                                        : 'buy'
                                "
                            >
                                {{
                                    node.data.item?.make_buy ||
                                    "?"
                                }}
                            </div>


                            <div class="pmv-node-copy">

                                <div class="pmv-node-title">

                                    <strong class="pmv-item-code">
                                        {{
                                            node.data.itemCode
                                        }}
                                    </strong>


                                    <Tag
                                        v-if="
                                            node.data.item
                                                ?.child_type
                                        "
                                        :value="
                                            node.data.item
                                                .child_type
                                        "
                                        :severity="
                                            itemTypeSeverity(
                                                node.data.item
                                                    .child_type
                                            )
                                        "
                                        rounded
                                        class="pmv-small-tag"
                                    />

                                </div>


                                <div class="pmv-node-description">

                                    {{
                                        text(
                                            node.data.item
                                                ?.child_desc
                                        )
                                    }}

                                </div>


                                <div class="pmv-node-meta">

                                    <span
                                        v-if="
                                            node.data.item
                                                ?.quantity
                                        "
                                    >
                                        Qty:
                                        {{
                                            node.data.item
                                                .quantity
                                        }}
                                        {{
                                            node.data.item
                                                .uom || ""
                                        }}
                                    </span>


                                    <span
                                        v-if="
                                            node.data.item
                                                ?.child_size
                                        "
                                    >
                                        Size:
                                        {{
                                            node.data.item
                                                .child_size
                                        }}
                                    </span>


                                    <span
                                        v-if="
                                            node.data.item
                                                ?.child_material
                                        "
                                    >
                                        {{
                                            node.data.item
                                                .child_material
                                        }}
                                    </span>


                                    <span
                                        v-if="
                                            node.data.item
                                                ?.bom_no
                                        "
                                        class="pmv-child-bom"
                                    >
                                        {{
                                            node.data.item
                                                .bom_no
                                        }}
                                    </span>

                                </div>

                            </div>

                        </div>


                        <!-- PROCESS GROUP -->

                        <div
                            v-else-if="
                                node.data?.kind === 'process-group'
                            "
                            class="pmv-node pmv-node-subgroup"
                        >

                            <div class="pmv-node-icon">
                                <i class="pi pi-cog"></i>
                            </div>

                            <strong>
                                PROCESS ROUTING
                            </strong>

                            <span>
                                {{ node.data.count }}
                                step<span
                                    v-if="node.data.count !== 1"
                                >s</span>
                            </span>

                        </div>


                        <!-- PROCESS STEP -->

                        <div
                            v-else-if="
                                node.data?.kind === 'process'
                            "
                            class="pmv-node pmv-node-process"
                        >

                            <span class="pmv-step">
                                P{{ node.data.stepNo }}
                            </span>

                            <span>
                                {{
                                    node.data.processName
                                }}
                            </span>

                        </div>


                        <!-- RAW GROUP -->

                        <div
                            v-else-if="
                                node.data?.kind === 'raw-group'
                            "
                            class="pmv-node pmv-node-subgroup"
                        >

                            <div class="pmv-node-icon">
                                <i class="pi pi-box"></i>
                            </div>

                            <strong>
                                {{ node.label }}
                            </strong>

                            <span>
                                {{ node.data.count }}
                            </span>

                        </div>


                        <!-- RAW ITEM -->

                        <div
                            v-else-if="
                                node.data?.kind === 'raw-item'
                            "
                            class="pmv-node pmv-node-raw"
                        >

                            <div class="pmv-raw-icon">
                                RM
                            </div>


                            <div class="pmv-node-copy">

                                <div class="pmv-node-title">

                                    <strong class="pmv-item-code">
                                        {{
                                            node.data.itemCode
                                        }}
                                    </strong>


                                    <Tag
                                        v-if="
                                            Number(
                                                node.data.item
                                                    ?.is_alternate || 0
                                            ) === 1
                                        "
                                        value="Alternate"
                                        severity="warn"
                                        rounded
                                        class="pmv-small-tag"
                                    />

                                </div>


                                <div class="pmv-node-description">

                                    {{
                                        text(
                                            node.data.item
                                                ?.child_desc
                                        )
                                    }}

                                </div>


                                <div class="pmv-node-meta">

                                    <span
                                        v-if="
                                            node.data.item
                                                ?.child_material
                                        "
                                    >
                                        {{
                                            node.data.item
                                                .child_material
                                        }}
                                    </span>


                                    <span
                                        v-if="
                                            node.data.item
                                                ?.child_size
                                        "
                                    >
                                        {{
                                            node.data.item
                                                .child_size
                                        }}
                                    </span>


                                    <span
                                        v-if="
                                            node.data.item
                                                ?.cutting_size
                                        "
                                    >
                                        Cut:
                                        {{
                                            node.data.item
                                                .cutting_size
                                        }}
                                    </span>

                                </div>

                            </div>

                        </div>


                        <!-- EMPTY -->

                        <div
                            v-else-if="
                                node.data?.kind === 'empty-process' ||
                                node.data?.kind === 'empty-raw'
                            "
                            class="pmv-node pmv-node-empty"
                        >

                            <i class="pi pi-info-circle"></i>

                            <span>
                                {{ node.label }}
                            </span>

                        </div>


                        <span v-else>
                            {{ node.label }}
                        </span>

                    </template>

                </Tree>


                <!-- LOAD MORE -->

                <div
                    v-if="hasMore"
                    class="pmv-load-more"
                >

                    <Button
                        :label="
                            `Load more (${remainingCount} remaining)`
                        "
                        icon="pi pi-chevron-down"
                        severity="secondary"
                        outlined
                        size="small"
                        :loading="loading"
                        @click="loadMore"
                    />

                </div>

            </section>


            <!-- =============================================
                 RIGHT SIDE PANEL
            ============================================== -->

            <aside
                v-if="sideMode"
                class="pmv-side-panel"
            >


                <!-- =========================================
                     PANEL HEADER
                ========================================== -->

                <div class="pmv-side-head">

                    <div>

                        <span>
                            {{
                                sideMode === "flow"
                                    ? "Manufacturing Sequence"
                                    : "Item Detail"
                            }}
                        </span>

                        <strong>
                            {{
                                sideMode === "flow"
                                    ? selectedBomNo
                                    : selectedItem
                                        ?.item_code || "Loading..."
                            }}
                        </strong>

                    </div>


                    <Button
                        icon="pi pi-times"
                        severity="secondary"
                        text
                        rounded
                        aria-label="Close"
                        @click="closeSidePanel"
                    />

                </div>


                <!-- =========================================
                     ITEM DETAIL
                ========================================== -->

                <div
                    v-if="sideMode === 'item'"
                    class="pmv-side-content"
                >


                    <div
                        v-if="detailLoading"
                        class="pmv-panel-loading"
                    >

                        <ProgressSpinner
                            style="
                                width: 34px;
                                height: 34px
                            "
                        />

                        <span>
                            Loading item...
                        </span>

                    </div>


                    <template
                        v-else-if="selectedItem"
                    >

                        <div class="pmv-detail-top">

                            <div>

                                <h2>
                                    {{
                                        selectedItem
                                            .item_code
                                    }}
                                </h2>

                                <p>
                                    {{
                                        text(
                                            selectedItem
                                                .item_description
                                        )
                                    }}
                                </p>

                            </div>


                            <div class="pmv-detail-tags">

                                <Tag
                                    :value="
                                        text(
                                            selectedItem
                                                .item_type
                                        )
                                    "
                                    :severity="
                                        itemTypeSeverity(
                                            selectedItem
                                                .item_type
                                        )
                                    "
                                    rounded
                                />

                                <Tag
                                    v-if="
                                        selectedItem
                                            .make_default
                                    "
                                    :value="
                                        makeLabel(
                                            selectedItem
                                                .make_default
                                        )
                                    "
                                    :severity="
                                        makeSeverity(
                                            selectedItem
                                                .make_default
                                        )
                                    "
                                    rounded
                                />

                            </div>

                        </div>


                        <div class="pmv-info-grid">

                            <div>
                                <span>Part Name</span>
                                <strong>
                                    {{
                                        text(
                                            selectedItem
                                                .part_name
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Size</span>
                                <strong>
                                    {{
                                        text(
                                            selectedItem
                                                .size
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Material</span>
                                <strong>
                                    {{
                                        text(
                                            selectedItem
                                                .material
                                        )
                                    }}
                                </strong>
                            </div>


                            <div>
                                <span>Children</span>
                                <strong>
                                    {{
                                        selectedItem
                                            .child_count || 0
                                    }}
                                </strong>
                            </div>

                        </div>


                        <!-- ROUTING -->

                        <section class="pmv-detail-section">

                            <div class="pmv-detail-section-head">

                                <strong>
                                    <i class="pi pi-cog"></i>
                                    Process Routing
                                </strong>

                                <span>
                                    {{
                                        selectedItem
                                            .processes?.length || 0
                                    }}
                                    steps
                                </span>

                            </div>


                            <div
                                v-if="
                                    selectedItem
                                        .processes?.length
                                "
                                class="pmv-detail-processes"
                            >

                                <div
                                    v-for="
                                        process in
                                        selectedItem.processes
                                    "
                                    :key="
                                        process.step_no +
                                        ':' +
                                        process.process_name
                                    "
                                    class="pmv-detail-process"
                                >

                                    <span>
                                        {{
                                            process.step_no
                                        }}
                                    </span>

                                    <strong>
                                        {{
                                            process.process_name
                                        }}
                                    </strong>

                                </div>

                            </div>


                            <div
                                v-else
                                class="pmv-detail-empty"
                            >
                                No process routing configured.
                            </div>

                        </section>


                        <!-- USED IN -->

                        <section class="pmv-detail-section">

                            <div class="pmv-detail-section-head">

                                <strong>
                                    <i class="pi pi-sitemap"></i>
                                    Used In
                                </strong>

                                <span>
                                    {{
                                        selectedItem
                                            .parents?.length || 0
                                    }}
                                    parents
                                </span>

                            </div>


                            <div
                                v-if="
                                    selectedItem
                                        .parents?.length
                                "
                                class="pmv-parent-list"
                            >

                                <button
                                    v-for="
                                        parent in
                                        selectedItem.parents
                                    "
                                    :key="
                                        parent.item_code
                                    "
                                    type="button"
                                    class="pmv-parent-row"
                                    @click="
                                        loadItemDetail(
                                            parent.item_code
                                        )
                                    "
                                >

                                    <div>

                                        <strong>
                                            {{
                                                parent
                                                    .item_code
                                            }}
                                        </strong>

                                        <span>
                                            {{
                                                text(
                                                    parent
                                                        .item_description
                                                )
                                            }}
                                        </span>

                                    </div>


                                    <i class="pi pi-angle-right"></i>

                                </button>

                            </div>


                            <div
                                v-else
                                class="pmv-detail-empty"
                            >
                                No parent links found.
                            </div>

                        </section>


                        <div class="pmv-pilot-note">

                            <i class="pi pi-info-circle"></i>

                            <span>
                                Tree browsing is now
                                Vue-native. Editing remains
                                read-only in this pilot until
                                the UX is approved.
                            </span>

                        </div>

                    </template>

                </div>


                <!-- =========================================
                     PROCESS FLOW
                ========================================== -->

                <div
                    v-else-if="sideMode === 'flow'"
                    class="pmv-side-content"
                >


                    <div
                        v-if="flowLoading"
                        class="pmv-panel-loading"
                    >

                        <ProgressSpinner
                            style="
                                width: 34px;
                                height: 34px
                            "
                        />

                        <span>
                            Building process flow...
                        </span>

                    </div>


                    <template v-else>

                        <div class="pmv-flow-intro">

                            <i class="pi pi-directions"></i>

                            <div>

                                <strong>
                                    Bottom-up manufacturing flow
                                </strong>

                                <span>
                                    Deepest Make item processes
                                    appear before upper-level
                                    processes.
                                </span>

                            </div>

                        </div>


                        <div
                            v-if="processFlow.length"
                            class="pmv-flow-list"
                        >

                            <div
                                v-for="
                                    row in processFlow
                                "
                                :key="
                                    row.process_sequence +
                                    ':' +
                                    row.item_code +
                                    ':' +
                                    row.step_no
                                "
                                class="pmv-flow-row"
                            >

                                <div class="pmv-flow-seq">
                                    {{
                                        row.process_sequence
                                    }}
                                </div>


                                <div class="pmv-flow-copy">

                                    <div class="pmv-flow-item">

                                        <strong>
                                            {{
                                                row.item_code
                                            }}
                                        </strong>

                                        <span>
                                            Level
                                            {{
                                                row.level_no
                                            }}
                                        </span>

                                    </div>


                                    <div class="pmv-flow-process">

                                        <span>
                                            P{{ row.step_no }}
                                        </span>

                                        <strong>
                                            {{
                                                row.process_name
                                            }}
                                        </strong>

                                    </div>


                                    <small
                                        v-if="
                                            row.item_description
                                        "
                                    >
                                        {{
                                            row.item_description
                                        }}
                                    </small>

                                </div>

                            </div>

                        </div>


                        <div
                            v-else
                            class="pmv-detail-empty"
                        >
                            No manufacturing process sequence
                            was found for this BOM.
                        </div>

                    </template>

                </div>

            </aside>

        </section>

    </main>

</template>
