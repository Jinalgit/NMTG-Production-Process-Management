(function () {
    "use strict";

    /*
     * =========================================================
     * DATA VIEW PRIORITY FINAL V2
     *
     * FINAL UX:
     *
     * Urgent:
     *     [ URGENT ]
     *
     * Regular:
     *     Mark Urgent
     *
     * Existing endpoint:
     * POST /api/job_card_item/priority
     *
     * No KPI cards.
     * No separate Filters button.
     * Excel column filters remain untouched.
     * =========================================================
     */

    let observer = null;
    let scheduled = false;
    let applying = false;
    let prioritySaving = false;


    function norm(value) {

        return String(value || "")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
    }


    function visible(element) {

        return Boolean(
            element &&
            element.offsetParent !== null
        );
    }


    function showPriorityToast(
        message,
        type
    ) {

        const old =
            document.getElementById(
                "dv-priority-toast"
            );


        if (old) {
            old.remove();
        }


        const toast =
            document.createElement(
                "div"
            );


        toast.id =
            "dv-priority-toast";


        toast.className =
            "dv-priority-toast " +
            (
                type === "error"
                    ? "error"
                    : "success"
            );


        toast.textContent =
            message;


        document.body.appendChild(
            toast
        );


        requestAnimationFrame(
            function () {

                toast.classList.add(
                    "show"
                );
            }
        );


        window.setTimeout(
            function () {

                toast.classList.remove(
                    "show"
                );


                window.setTimeout(
                    function () {

                        toast.remove();
                    },
                    180
                );
            },
            2200
        );
    }


    /* =========================================================
       FIND PPC TABLE
    ========================================================= */

    function getHeaderMap(table) {

        const rows =
            Array.from(
                table.querySelectorAll(
                    "thead tr"
                )
            );


        let best = null;


        for (const row of rows) {

            const headers =
                Array.from(
                    row.querySelectorAll(
                        "th"
                    )
                );


            if (!headers.length) {
                continue;
            }


            const names =
                headers.map(
                    function (header) {

                        return norm(
                            header.textContent
                        );
                    }
                );


            const urgent =
                names.findIndex(
                    function (name) {

                        return (
                            name.includes(
                                "urgent"
                            )
                            ||
                            name.includes(
                                "priority"
                            )
                        );
                    }
                );


            const jc =
                names.findIndex(
                    function (name) {

                        return (
                            name.includes(
                                "jc no"
                            )
                            ||
                            name.includes(
                                "job card"
                            )
                        );
                    }
                );


            const item =
                names.findIndex(
                    function (name) {

                        return (
                            name ===
                            "item name"
                            ||
                            name.includes(
                                "item name"
                            )
                        );
                    }
                );


            const wip =
                names.findIndex(
                    function (name) {

                        return (
                            name.includes(
                                "wip status"
                            )
                            ||
                            name.includes(
                                "current wip"
                            )
                            ||
                            name.includes(
                                "wip stage"
                            )
                        );
                    }
                );


            const delivery =
                names.findIndex(
                    function (name) {

                        return (
                            name.includes(
                                "delivery date"
                            )
                            ||
                            name ===
                            "delivery"
                        );
                    }
                );


            if (
                urgent >= 0
                &&
                jc >= 0
            ) {

                best = {
                    row,
                    headers,
                    names,
                    urgent,
                    jc,
                    item,
                    wip,
                    delivery
                };

                break;
            }
        }


        return best;
    }


    function findPpcTable() {

        const tables =
            Array.from(
                document.querySelectorAll(
                    "table"
                )
            )
            .filter(
                visible
            );


        for (const table of tables) {

            const map =
                getHeaderMap(
                    table
                );


            if (map) {

                return {
                    table,
                    map
                };
            }
        }


        return null;
    }


    /* =========================================================
       REMOVE TOP EXPLICIT FILTER BUTTON

       Excel-style filter buttons inside headers are NOT touched.
    ========================================================= */

    function hideExplicitFilterButton() {

        document
            .querySelectorAll(
                "button"
            )
            .forEach(
                function (button) {

                    const text =
                        norm(
                            button.textContent
                        );


                    const aria =
                        norm(
                            button.getAttribute(
                                "aria-label"
                            )
                        );


                    if (
                        text === "filters"
                        ||
                        aria === "filters"
                    ) {

                        button.classList.add(
                            "dv-hide-explicit-filter"
                        );
                    }
                }
            );
    }


    /* =========================================================
       REMOVE OLD KPI SUMMARY
    ========================================================= */

    function removeDraftKpis() {

        document
            .querySelectorAll(
                ".dv-direct-summary, .dv-draft1-summary"
            )
            .forEach(
                function (element) {

                    element.remove();
                }
            );
    }


    /* =========================================================
       PRIORITY STATE
    ========================================================= */

    function isUrgentCell(cell) {

        if (!cell) {
            return false;
        }


        const savedState =
            cell.dataset
                .priorityState;


        if (savedState === "1") {
            return true;
        }


        if (savedState === "0") {
            return false;
        }


        const text =
            norm(
                cell.textContent
            );


        /*
         * Existing Vue page currently renders urgent
         * rows using a filled star.
         */
        if (
            cell.textContent.includes(
                "★"
            )
            ||
            text === "urgent"
            ||
            text.includes(
                " urgent "
            )
        ) {
            return true;
        }


        return Array
            .from(
                cell.querySelectorAll(
                    "*"
                )
            )
            .some(
                function (element) {

                    const signature =
                        norm(
                            [
                                element.className,
                                element.getAttribute(
                                    "title"
                                ),
                                element.getAttribute(
                                    "aria-label"
                                ),
                                element.getAttribute(
                                    "data-value"
                                ),
                                element.getAttribute(
                                    "data-priority"
                                )
                            ]
                            .filter(Boolean)
                            .join(" ")
                        );


                    return (
                        signature.includes(
                            "star-fill"
                        )
                        ||
                        signature.includes(
                            "filled star"
                        )
                        ||
                        signature.includes(
                            "priority true"
                        )
                        ||
                        signature.includes(
                            "urgent true"
                        )
                    );
                }
            );
    }


    function getCellText(
        row,
        index
    ) {

        if (
            !row
            ||
            index < 0
        ) {
            return "";
        }


        const cell =
            row.children[
                index
            ];


        if (!cell) {
            return "";
        }


        return String(
            cell.textContent || ""
        )
            .replace(/\s+/g, " ")
            .trim();
    }


    /* =========================================================
       PRIORITY API
    ========================================================= */

    async function updatePriority(
        row,
        map,
        nextUrgent,
        button
    ) {

        if (prioritySaving) {
            return;
        }


        const jobCardNo =
            getCellText(
                row,
                map.jc
            );


        const itemName =
            getCellText(
                row,
                map.item
            );


        if (!jobCardNo) {

            showPriorityToast(
                "Could not identify Job Card number.",
                "error"
            );

            return;
        }


        /*
         * The established endpoint identifies the item using
         * Job Card No + Item Name when item_id is not supplied.
         */
        if (!itemName) {

            showPriorityToast(
                "Item Name column must be visible to change priority.",
                "error"
            );

            return;
        }


        prioritySaving =
            true;


        const oldText =
            button.textContent;


        button.disabled =
            true;


        button.textContent =
            "Saving...";


        try {

            const response =
                await fetch(
                    "/api/job_card_item/priority",
                    {
                        method:
                            "POST",

                        headers: {
                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify({
                                item_id:
                                    null,

                                job_card_no:
                                    jobCardNo,

                                item_name:
                                    itemName,

                                is_priority:
                                    nextUrgent
                                        ? 1
                                        : 0
                            })
                    }
                );


            const data =
                await response.json();


            if (
                !response.ok
                ||
                !data.success
            ) {

                throw new Error(
                    data.error
                    ||
                    "Failed to update priority"
                );
            }


            showPriorityToast(
                nextUrgent
                    ? "Marked as Urgent"
                    : "Marked as Regular",
                "success"
            );


            /*
             * Vue Data View exposes its normal reload function.
             * Reuse it so current filters/page remain authoritative.
             */
            if (
                typeof window.loadData ===
                "function"
            ) {

                await window.loadData();
            }
            else {

                /*
                 * Fallback visual update.
                 */
                const cell =
                    row.children[
                        map.urgent
                    ];


                if (cell) {

                    cell.dataset
                        .priorityState =
                        nextUrgent
                            ? "1"
                            : "0";
                }


                schedule();
            }

        }
        catch (error) {

            button.disabled =
                false;


            button.textContent =
                oldText;


            showPriorityToast(
                error.message
                ||
                "Priority update failed.",
                "error"
            );
        }
        finally {

            prioritySaving =
                false;
        }
    }


    /* =========================================================
       RENDER PRIORITY CELL
    ========================================================= */

    function renderPriorityCell(
        row,
        cell,
        map
    ) {

        if (!cell) {
            return;
        }


        const urgent =
            isUrgentCell(
                cell
            );


        cell.dataset
            .priorityState =
            urgent
                ? "1"
                : "0";


        row.classList.toggle(
            "dv-direct-urgent-row",
            urgent
        );


        const existing =
            cell.querySelector(
                ".dv-priority-control"
            );


        if (
            existing
            &&
            existing.dataset
                .urgent ===
                (
                    urgent
                        ? "1"
                        : "0"
                )
        ) {
            return;
        }


        cell.innerHTML =
            "";


        const button =
            document.createElement(
                "button"
            );


        button.type =
            "button";


        button.className =
            urgent
                ? "dv-priority-control dv-priority-urgent"
                : "dv-priority-control dv-priority-regular";


        button.dataset
            .urgent =
            urgent
                ? "1"
                : "0";


        button.textContent =
            urgent
                ? "URGENT"
                : "Mark Urgent";


        button.title =
            urgent
                ? "Click to remove urgent status"
                : "Click to mark this Job Card as urgent";


        button.setAttribute(
            "aria-label",
            button.title
        );


        button.addEventListener(
            "click",
            function () {

                updatePriority(
                    row,
                    map,
                    !urgent,
                    button
                );
            }
        );


        cell.appendChild(
            button
        );
    }


    /* =========================================================
       WIP VISUAL EMPHASIS
    ========================================================= */

    function enhanceWip(
        table,
        map
    ) {

        if (map.wip < 0) {
            return;
        }


        Array
            .from(
                table.querySelectorAll(
                    "tbody tr"
                )
            )
            .forEach(
                function (row) {

                    const cell =
                        row.children[
                            map.wip
                        ];


                    if (!cell) {
                        return;
                    }


                    const text =
                        norm(
                            cell.textContent
                        );


                    const active =
                        Boolean(
                            text
                            &&
                            text !== "-"
                            &&
                            text !== "—"
                            &&
                            text !== "completed"
                        );


                    cell.classList.toggle(
                        "dv-direct-wip",
                        active
                    );
                }
            );
    }


    /* =========================================================
       DELIVERY SECONDARY STATUS
    ========================================================= */

    function parseDate(text) {

        const value =
            String(text || "")
                .trim();


        let match =
            value.match(
                /(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/
            );


        if (match) {

            return new Date(
                Number(match[3]),
                Number(match[2]) - 1,
                Number(match[1])
            );
        }


        match =
            value.match(
                /(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/
            );


        if (match) {

            return new Date(
                Number(match[1]),
                Number(match[2]) - 1,
                Number(match[3])
            );
        }


        return null;
    }


    function enhanceDelivery(
        table,
        map
    ) {

        if (map.delivery < 0) {
            return;
        }


        const today =
            new Date();


        today.setHours(
            0,
            0,
            0,
            0
        );


        Array
            .from(
                table.querySelectorAll(
                    "tbody tr"
                )
            )
            .forEach(
                function (row) {

                    const cell =
                        row.children[
                            map.delivery
                        ];


                    if (!cell) {
                        return;
                    }


                    const oldMeta =
                        cell.querySelector(
                            ".dv-direct-delivery-meta"
                        );


                    const raw =
                        Array
                            .from(
                                cell.childNodes
                            )
                            .filter(
                                function (node) {

                                    return !(
                                        node.nodeType === 1
                                        &&
                                        node.classList
                                        .contains(
                                            "dv-direct-delivery-meta"
                                        )
                                    );
                                }
                            )
                            .map(
                                function (node) {

                                    return (
                                        node.textContent
                                        ||
                                        ""
                                    );
                                }
                            )
                            .join(" ");


                    const date =
                        parseDate(
                            raw
                        );


                    if (!date) {

                        if (oldMeta) {
                            oldMeta.remove();
                        }

                        return;
                    }


                    date.setHours(
                        0,
                        0,
                        0,
                        0
                    );


                    const days =
                        Math.round(
                            (
                                date -
                                today
                            )
                            /
                            86400000
                        );


                    let text;
                    let state;


                    if (days < 0) {

                        const overdue =
                            Math.abs(
                                days
                            );


                        text =
                            `${overdue}d overdue`;


                        state =
                            "overdue";

                    }
                    else if (days === 0) {

                        text =
                            "Due today";


                        state =
                            "due";

                    }
                    else {

                        text =
                            `${days}d left`;


                        state =
                            days <= 7
                                ? "due"
                                : "";
                    }


                    let meta =
                        oldMeta;


                    if (!meta) {

                        meta =
                            document.createElement(
                                "div"
                            );


                        cell.appendChild(
                            meta
                        );
                    }


                    meta.className =
                        "dv-direct-delivery-meta"
                        +
                        (
                            state
                                ? " " + state
                                : ""
                        );


                    meta.textContent =
                        text;
                }
            );
    }


    /* =========================================================
       APPLY
    ========================================================= */

    function apply() {

        if (applying) {
            return;
        }


        applying =
            true;


        try {

            removeDraftKpis();

            hideExplicitFilterButton();


            const found =
                findPpcTable();


            if (!found) {
                return;
            }


            const table =
                found.table;


            const map =
                found.map;


            table.classList.add(
                "dv-direct-table"
            );


            Array
                .from(
                    table.querySelectorAll(
                        "tbody tr"
                    )
                )
                .forEach(
                    function (row) {

                        const cell =
                            row.children[
                                map.urgent
                            ];


                        renderPriorityCell(
                            row,
                            cell,
                            map
                        );
                    }
                );


            enhanceWip(
                table,
                map
            );


            enhanceDelivery(
                table,
                map
            );

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


        requestAnimationFrame(
            function () {

                scheduled =
                    false;


                apply();
            }
        );
    }


    function init() {

        apply();


        observer =
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
