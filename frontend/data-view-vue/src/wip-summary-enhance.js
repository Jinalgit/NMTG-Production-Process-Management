/*
 * ============================================================
 * DATA VIEW - WIP SUMMARY MATRIX V2
 *
 * Actual structure:
 *
 * Row    = Date
 * Column = Process
 * Cell   = Completion count
 *
 * Existing Vue data/date filtering/cell drill-down remains
 * authoritative.
 * ============================================================
 */

(function () {
    "use strict";

    const HIDE_EMPTY_KEY =
        "jms_wip_matrix_hide_empty";

    let table =
        null;

    let toolbar =
        null;

    let matrix =
        null;

    let searchText =
        "";

    let hideEmpty =
        localStorage.getItem(
            HIDE_EMPTY_KEY
        ) === "1";

    let topProcessIndex =
        -1;

    let scheduled =
        false;

    let applying =
        false;


    function norm(value) {

        return String(value || "")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
    }


    function clean(value) {

        return String(value || "")
            .replace(/\s+/g, " ")
            .trim();
    }


    function isVisible(element) {

        if (!element) {
            return false;
        }

        const style =
            window.getComputedStyle(
                element
            );

        return (
            style.display !== "none"
            &&
            style.visibility !== "hidden"
            &&
            element.getClientRects().length > 0
        );
    }


    function numberValue(value) {

        const text =
            String(value || "")
                .replace(/,/g, "")
                .trim();


        if (
            !text
            ||
            text === "-"
            ||
            text === "—"
        ) {
            return 0;
        }


        const match =
            text.match(
                /-?\d+(?:\.\d+)?/
            );


        if (!match) {
            return 0;
        }


        const number =
            Number(match[0]);


        return Number.isFinite(number)
            ? number
            : 0;
    }


    function getHeaderRow(candidate) {

        const rows =
            Array.from(
                candidate.querySelectorAll(
                    "thead tr"
                )
            );


        let best =
            null;

        let bestCount =
            0;


        rows.forEach(
            function (row) {

                const count =
                    row.querySelectorAll(
                        "th"
                    ).length;


                if (count > bestCount) {

                    best =
                        row;

                    bestCount =
                        count;
                }
            }
        );


        return best;
    }


    function detectMatrix() {

        const candidates =
            Array.from(
                document.querySelectorAll(
                    "table"
                )
            )
            .filter(
                isVisible
            );


        let best =
            null;

        let bestScore =
            -1;


        candidates.forEach(
            function (candidate) {

                const headerRow =
                    getHeaderRow(
                        candidate
                    );


                if (!headerRow) {
                    return;
                }


                const headers =
                    Array.from(
                        headerRow.querySelectorAll(
                            "th"
                        )
                    );


                if (headers.length < 4) {
                    return;
                }


                const names =
                    headers.map(
                        function (header) {

                            return norm(
                                header.textContent
                            );
                        }
                    );


                const dateIndex =
                    names.findIndex(
                        function (name) {

                            return (
                                name === "date"
                                ||
                                name === "process date"
                            );
                        }
                    );


                if (dateIndex < 0) {
                    return;
                }


                const rows =
                    Array.from(
                        candidate.querySelectorAll(
                            "tbody tr"
                        )
                    );


                if (!rows.length) {
                    return;
                }


                let numericCells =
                    0;


                rows
                    .slice(
                        0,
                        8
                    )
                    .forEach(
                        function (row) {

                            Array
                                .from(
                                    row.children
                                )
                                .forEach(
                                    function (
                                        cell,
                                        index
                                    ) {

                                        if (
                                            index ===
                                            dateIndex
                                        ) {
                                            return;
                                        }


                                        const text =
                                            clean(
                                                cell.textContent
                                            );


                                        if (
                                            /^\d+(?:\.\d+)?$/
                                                .test(text)
                                            ||
                                            text === "-"
                                            ||
                                            text === "—"
                                        ) {
                                            numericCells +=
                                                1;
                                        }
                                    }
                                );
                        }
                    );


                const score =
                    headers.length * 2
                    +
                    numericCells;


                if (score > bestScore) {

                    bestScore =
                        score;


                    best = {
                        table:
                            candidate,

                        headerRow,

                        headers,

                        names,

                        rows,

                        dateIndex
                    };
                }
            }
        );


        return best;
    }


    function resetOldEnhancement() {

        document
            .querySelectorAll(
                ".wse-toolbar"
            )
            .forEach(
                function (element) {

                    element.remove();
                }
            );


        document
            .querySelectorAll(
                ".wse-hidden-row"
            )
            .forEach(
                function (element) {

                    element.classList.remove(
                        "wse-hidden-row"
                    );
                }
            );


        document
            .querySelectorAll(
                ".wse-bottleneck"
            )
            .forEach(
                function (element) {

                    element.classList.remove(
                        "wse-bottleneck"
                    );
                }
            );
    }


    function removeGeneratedLabels() {

        if (!table) {
            return;
        }


        table
            .querySelectorAll(
                ".wse2-process-total, .wse2-day-total"
            )
            .forEach(
                function (element) {

                    element.remove();
                }
            );
    }


    function clearMatrixStyles() {

        if (!table) {
            return;
        }


        table
            .querySelectorAll(
                "th, td"
            )
            .forEach(
                function (cell) {

                    cell.classList.remove(
                        "wse2-hidden-column",
                        "wse2-load-cell",
                        "wse2-top-process",
                        "wse2-peak-cell"
                    );


                    cell.style.removeProperty(
                        "--wse2-load"
                    );
                }
            );
    }


    function buildProcessStats() {

        if (!matrix) {
            return [];
        }


        const stats =
            [];


        matrix.headers.forEach(
            function (
                header,
                index
            ) {

                if (
                    index ===
                    matrix.dateIndex
                ) {
                    return;
                }


                let total =
                    0;

                let max =
                    0;

                let nonZero =
                    0;


                matrix.rows.forEach(
                    function (row) {

                        const cell =
                            row.children[
                                index
                            ];


                        if (!cell) {
                            return;
                        }


                        const value =
                            numberValue(
                                cell.textContent
                            );


                        total +=
                            value;


                        if (value > max) {
                            max =
                                value;
                        }


                        if (value > 0) {
                            nonZero +=
                                1;
                        }
                    }
                );


                stats.push({
                    index,

                    name:
                        clean(
                            header.textContent
                        ),

                    total,

                    max,

                    nonZero
                });
            }
        );


        return stats;
    }


    function visibleProcessStats(
        allStats
    ) {

        const query =
            norm(
                searchText
            );


        return allStats.filter(
            function (stat) {

                const matchesSearch =
                    !query
                    ||
                    norm(
                        stat.name
                    ).includes(
                        query
                    );


                const matchesEmpty =
                    !hideEmpty
                    ||
                    stat.total > 0;


                return (
                    matchesSearch
                    &&
                    matchesEmpty
                );
            }
        );
    }


    function hideColumn(
        index,
        hidden
    ) {

        if (!matrix) {
            return;
        }


        const header =
            matrix.headers[
                index
            ];


        if (header) {

            header.classList.toggle(
                "wse2-hidden-column",
                hidden
            );
        }


        matrix.rows.forEach(
            function (row) {

                const cell =
                    row.children[
                        index
                    ];


                if (cell) {

                    cell.classList.toggle(
                        "wse2-hidden-column",
                        hidden
                    );
                }
            }
        );
    }


    function appendProcessTotals(
        allStats
    ) {

        allStats.forEach(
            function (stat) {

                const header =
                    matrix.headers[
                        stat.index
                    ];


                if (!header) {
                    return;
                }


                const label =
                    document.createElement(
                        "div"
                    );


                label.className =
                    "wse2-process-total";


                label.textContent =
                    `${stat.total} total`;


                header.appendChild(
                    label
                );
            }
        );
    }


    function appendDailyTotals(
        visibleStats
    ) {

        matrix.rows.forEach(
            function (row) {

                const dateCell =
                    row.children[
                        matrix.dateIndex
                    ];


                if (!dateCell) {
                    return;
                }


                let total =
                    0;


                visibleStats.forEach(
                    function (stat) {

                        const cell =
                            row.children[
                                stat.index
                            ];


                        if (!cell) {
                            return;
                        }


                        total +=
                            numberValue(
                                cell.textContent
                            );
                    }
                );


                const label =
                    document.createElement(
                        "div"
                    );


                label.className =
                    "wse2-day-total";


                label.textContent =
                    `${total} total`;


                dateCell.appendChild(
                    label
                );
            }
        );
    }


    function applyHeatmap(
        visibleStats
    ) {

        let maxCellValue =
            0;

        let peakCell =
            null;


        visibleStats.forEach(
            function (stat) {

                matrix.rows.forEach(
                    function (row) {

                        const cell =
                            row.children[
                                stat.index
                            ];


                        if (!cell) {
                            return;
                        }


                        const value =
                            numberValue(
                                cell.textContent
                            );


                        if (
                            value >
                            maxCellValue
                        ) {

                            maxCellValue =
                                value;

                            peakCell =
                                cell;
                        }
                    }
                );
            }
        );


        if (
            maxCellValue <= 0
        ) {
            return;
        }


        visibleStats.forEach(
            function (stat) {

                matrix.rows.forEach(
                    function (row) {

                        const cell =
                            row.children[
                                stat.index
                            ];


                        if (!cell) {
                            return;
                        }


                        const value =
                            numberValue(
                                cell.textContent
                            );


                        if (value <= 0) {
                            return;
                        }


                        const percentage =
                            Math.max(
                                8,
                                Math.min(
                                    100,
                                    (
                                        value /
                                        maxCellValue
                                    ) *
                                    100
                                )
                            );


                        cell.classList.add(
                            "wse2-load-cell"
                        );


                        cell.style.setProperty(
                            "--wse2-load",
                            `${percentage}%`
                        );


                        const clickable =
                            cell.querySelector(
                                "button, a"
                            );


                        if (clickable) {

                            const process =
                                clean(
                                    matrix.headers[
                                        stat.index
                                    ].childNodes[0]
                                        ?.textContent
                                    ||
                                    stat.name
                                );


                            const date =
                                clean(
                                    row.children[
                                        matrix.dateIndex
                                    ]?.childNodes[0]
                                        ?.textContent
                                    ||
                                    ""
                                );


                            clickable.title =
                                `${process} - ${date}: ${value} completions`;
                        }
                    }
                );
            }
        );


        if (peakCell) {

            peakCell.classList.add(
                "wse2-peak-cell"
            );
        }
    }


    function highlightTopProcess(
        visibleStats
    ) {

        topProcessIndex =
            -1;


        if (!visibleStats.length) {
            return null;
        }


        let top =
            visibleStats[0];


        visibleStats.forEach(
            function (stat) {

                if (
                    stat.total >
                    top.total
                ) {
                    top =
                        stat;
                }
            }
        );


        if (
            !top
            ||
            top.total <= 0
        ) {
            return null;
        }


        topProcessIndex =
            top.index;


        const header =
            matrix.headers[
                top.index
            ];


        if (header) {

            header.classList.add(
                "wse2-top-process"
            );
        }


        matrix.rows.forEach(
            function (row) {

                const cell =
                    row.children[
                        top.index
                    ];


                if (cell) {

                    cell.classList.add(
                        "wse2-top-process"
                    );
                }
            }
        );


        return top;
    }


    function updateToolbar(
        allStats,
        visibleStats,
        top
    ) {

        if (!toolbar) {
            return;
        }


        const processElement =
            toolbar.querySelector(
                '[data-wse2-stat="processes"]'
            );


        const totalElement =
            toolbar.querySelector(
                '[data-wse2-stat="total"]'
            );


        const topElement =
            toolbar.querySelector(
                '[data-wse2-stat="top"]'
            );


        const hideButton =
            toolbar.querySelector(
                '[data-wse2-action="hide-empty"]'
            );


        if (processElement) {

            processElement.textContent =
                `${visibleStats.length}/${allStats.length}`;
        }


        const total =
            visibleStats.reduce(
                function (
                    sum,
                    stat
                ) {

                    return (
                        sum +
                        stat.total
                    );
                },
                0
            );


        if (totalElement) {

            totalElement.textContent =
                String(total);
        }


        if (topElement) {

            topElement.textContent =
                top
                    ? `${top.name} (${top.total})`
                    : "-";
        }


        if (hideButton) {

            hideButton.classList.toggle(
                "active",
                hideEmpty
            );


            hideButton.setAttribute(
                "aria-pressed",
                hideEmpty
                    ? "true"
                    : "false"
            );
        }
    }


    function applyMatrixEnhancement() {

        if (
            !table
            ||
            !matrix
        ) {
            return;
        }


        removeGeneratedLabels();

        clearMatrixStyles();


        const allStats =
            buildProcessStats();


        const visibleStats =
            visibleProcessStats(
                allStats
            );


        const visibleIndexes =
            new Set(
                visibleStats.map(
                    function (stat) {

                        return stat.index;
                    }
                )
            );


        allStats.forEach(
            function (stat) {

                hideColumn(
                    stat.index,
                    !visibleIndexes.has(
                        stat.index
                    )
                );
            }
        );


        appendProcessTotals(
            allStats
        );


        appendDailyTotals(
            visibleStats
        );


        applyHeatmap(
            visibleStats
        );


        const top =
            highlightTopProcess(
                visibleStats
            );


        updateToolbar(
            allStats,
            visibleStats,
            top
        );
    }


    function focusTopProcess() {

        if (
            !matrix
            ||
            topProcessIndex < 0
        ) {

            showToast(
                "No active process found."
            );

            return;
        }


        const header =
            matrix.headers[
                topProcessIndex
            ];


        if (!header) {
            return;
        }


        header.scrollIntoView({
            behavior:
                "smooth",

            inline:
                "center",

            block:
                "nearest"
        });


        header.classList.add(
            "wse2-focus-pulse"
        );


        window.setTimeout(
            function () {

                header.classList.remove(
                    "wse2-focus-pulse"
                );
            },
            1600
        );
    }


    function csvEscape(value) {

        const text =
            String(value ?? "");


        if (
            text.includes(",")
            ||
            text.includes('"')
            ||
            text.includes("\n")
        ) {

            return (
                '"' +
                text.replace(
                    /"/g,
                    '""'
                ) +
                '"'
            );
        }


        return text;
    }


    function exportVisibleMatrix() {

        if (
            !matrix
            ||
            !table
        ) {
            return;
        }


        const visibleIndexes =
            [];


        matrix.headers.forEach(
            function (
                header,
                index
            ) {

                if (
                    !header.classList.contains(
                        "wse2-hidden-column"
                    )
                ) {
                    visibleIndexes.push(
                        index
                    );
                }
            }
        );


        const headerData =
            visibleIndexes.map(
                function (index) {

                    const header =
                        matrix.headers[
                            index
                        ];


                    const clone =
                        header.cloneNode(
                            true
                        );


                    clone
                        .querySelectorAll(
                            ".wse2-process-total"
                        )
                        .forEach(
                            function (element) {

                                element.remove();
                            }
                        );


                    return clean(
                        clone.textContent
                    );
                }
            );


        const rows =
            matrix.rows.map(
                function (row) {

                    return visibleIndexes.map(
                        function (index) {

                            const cell =
                                row.children[
                                    index
                                ];


                            if (!cell) {
                                return "";
                            }


                            const clone =
                                cell.cloneNode(
                                    true
                                );


                            clone
                                .querySelectorAll(
                                    ".wse2-day-total"
                                )
                                .forEach(
                                    function (element) {

                                        element.remove();
                                    }
                                );


                            return clean(
                                clone.textContent
                            );
                        }
                    );
                }
            );


        const csv =
            [
                headerData,
                ...rows
            ]
            .map(
                function (row) {

                    return row
                        .map(
                            csvEscape
                        )
                        .join(",");
                }
            )
            .join("\r\n");


        const blob =
            new Blob(
                [csv],
                {
                    type:
                        "text/csv;charset=utf-8"
                }
            );


        const url =
            URL.createObjectURL(
                blob
            );


        const link =
            document.createElement(
                "a"
            );


        const now =
            new Date();


        const stamp =
            [
                now.getFullYear(),
                String(
                    now.getMonth() + 1
                ).padStart(
                    2,
                    "0"
                ),
                String(
                    now.getDate()
                ).padStart(
                    2,
                    "0"
                )
            ].join("");


        link.href =
            url;


        link.download =
            `wip-summary-${stamp}.csv`;


        document.body.appendChild(
            link
        );


        link.click();

        link.remove();


        URL.revokeObjectURL(
            url
        );


        showToast(
            "Visible WIP Summary exported."
        );
    }


    function showToast(message) {

        let toast =
            document.getElementById(
                "wse2-toast"
            );


        if (!toast) {

            toast =
                document.createElement(
                    "div"
                );


            toast.id =
                "wse2-toast";


            toast.className =
                "wse2-toast";


            document.body.appendChild(
                toast
            );
        }


        toast.textContent =
            message;


        toast.classList.add(
            "show"
        );


        window.clearTimeout(
            toast._timer
        );


        toast._timer =
            window.setTimeout(
                function () {

                    toast.classList.remove(
                        "show"
                    );
                },
                2100
            );
    }


    function findToolbarAnchor() {

        let anchor =
            table;


        for (
            let i = 0;
            i < 4;
            i += 1
        ) {

            const parent =
                anchor.parentElement;


            if (!parent) {
                break;
            }


            const classes =
                norm(
                    parent.className
                );


            const style =
                window.getComputedStyle(
                    parent
                );


            const scrollContainer =
                style.overflowX === "auto"
                ||
                style.overflowX === "scroll";


            if (
                classes.includes("table")
                ||
                classes.includes("scroll")
                ||
                classes.includes("wrap")
                ||
                classes.includes("grid")
                ||
                scrollContainer
            ) {

                anchor =
                    parent;

                continue;
            }


            break;
        }


        return anchor;
    }


    function createToolbar() {

        if (toolbar) {

            toolbar.remove();
        }


        toolbar =
            document.createElement(
                "section"
            );


        toolbar.className =
            "wse2-toolbar";


        toolbar.innerHTML = `
            <div class="wse2-search">

                <i
                    class="fa fa-search"
                    aria-hidden="true"
                ></i>

                <input
                    type="search"
                    placeholder="Find process..."
                    aria-label="Search WIP process"
                >

                <button
                    type="button"
                    class="wse2-search-clear"
                    title="Clear"
                >
                    <i
                        class="fa fa-times"
                        aria-hidden="true"
                    ></i>
                </button>

            </div>


            <button
                type="button"
                class="wse2-action"
                data-wse2-action="hide-empty"
                aria-pressed="false"
            >
                <i
                    class="fa fa-eye-slash"
                    aria-hidden="true"
                ></i>

                Hide Empty
            </button>


            <button
                type="button"
                class="wse2-action"
                data-wse2-action="focus-top"
            >
                <i
                    class="fa fa-crosshairs"
                    aria-hidden="true"
                ></i>

                Focus Top Process
            </button>


            <button
                type="button"
                class="wse2-action"
                data-wse2-action="export"
            >
                <i
                    class="fa fa-download"
                    aria-hidden="true"
                ></i>

                Export
            </button>


            <div class="wse2-spacer"></div>


            <div class="wse2-stats">

                <div>
                    <span>
                        Processes
                    </span>

                    <strong
                        data-wse2-stat="processes"
                    >
                        -
                    </strong>
                </div>


                <div>
                    <span>
                        Total Completions
                    </span>

                    <strong
                        data-wse2-stat="total"
                    >
                        -
                    </strong>
                </div>


                <div class="wse2-top-stat">
                    <span>
                        Top Process
                    </span>

                    <strong
                        data-wse2-stat="top"
                    >
                        -
                    </strong>
                </div>

            </div>
        `;


        const anchor =
            findToolbarAnchor();


        if (
            !anchor
            ||
            !anchor.parentElement
        ) {
            return;
        }


        anchor.parentElement.insertBefore(
            toolbar,
            anchor
        );


        const search =
            toolbar.querySelector(
                ".wse2-search input"
            );


        const clear =
            toolbar.querySelector(
                ".wse2-search-clear"
            );


        const hideButton =
            toolbar.querySelector(
                '[data-wse2-action="hide-empty"]'
            );


        const focusButton =
            toolbar.querySelector(
                '[data-wse2-action="focus-top"]'
            );


        const exportButton =
            toolbar.querySelector(
                '[data-wse2-action="export"]'
            );


        search.value =
            searchText;


        search.addEventListener(
            "input",
            function () {

                searchText =
                    search.value;


                clear.classList.toggle(
                    "visible",
                    Boolean(
                        searchText
                    )
                );


                applyMatrixEnhancement();
            }
        );


        clear.addEventListener(
            "click",
            function () {

                searchText =
                    "";

                search.value =
                    "";

                clear.classList.remove(
                    "visible"
                );


                search.focus();


                applyMatrixEnhancement();
            }
        );


        hideButton.addEventListener(
            "click",
            function () {

                hideEmpty =
                    !hideEmpty;


                localStorage.setItem(
                    HIDE_EMPTY_KEY,
                    hideEmpty
                        ? "1"
                        : "0"
                );


                applyMatrixEnhancement();
            }
        );


        focusButton.addEventListener(
            "click",
            focusTopProcess
        );


        exportButton.addEventListener(
            "click",
            exportVisibleMatrix
        );


        clear.classList.toggle(
            "visible",
            Boolean(
                searchText
            )
        );
    }


    function enhance() {

        if (applying) {
            return;
        }


        applying =
            true;


        try {

            const found =
                detectMatrix();


            if (!found) {

                if (toolbar) {

                    toolbar.remove();

                    toolbar =
                        null;
                }


                table =
                    null;

                matrix =
                    null;

                return;
            }


            const changed =
                table !==
                found.table;


            table =
                found.table;


            matrix =
                found;


            table.classList.add(
                "wse2-matrix"
            );


            if (
                changed
                ||
                !toolbar
                ||
                !document.body.contains(
                    toolbar
                )
            ) {

                createToolbar();
            }


            applyMatrixEnhancement();

        }
        finally {

            applying =
                false;
        }
    }


    function schedule() {

        if (scheduled) {
            return;
        }


        scheduled =
            true;


        window.setTimeout(
            function () {

                scheduled =
                    false;


                enhance();
            },
            80
        );
    }


    function init() {

        resetOldEnhancement();

        enhance();


        const observer =
            new MutationObserver(
                schedule
            );


        observer.observe(
            document.body,
            {
                childList:
                    true,

                subtree:
                    true
            }
        );


        /*
         * Date Apply and tab switching may rebuild the matrix.
         */
        document.addEventListener(
            "click",
            function () {

                window.setTimeout(
                    schedule,
                    60
                );
            },
            true
        );


        window.addEventListener(
            "resize",
            schedule,
            {
                passive:
                    true
            }
        );
    }


    if (
        document.readyState ===
        "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            init,
            {
                once:
                    true
            }
        );

    }
    else {

        init();
    }

})();