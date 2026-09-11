/*
 * ============================================================
 * DATA VIEW VUE - DRAFT 1
 * Clean Excel / Management View
 *
 * Existing Vue table/filter functionality remains authoritative.
 * This module enhances only the rendered presentation.
 * ============================================================
 */

(function () {
    "use strict";

    const ROOT_ID =
        "app";

    let observer =
        null;

    let refreshTimer =
        null;

    let running =
        false;


    function normalize(value) {

        return String(value || "")
            .replace(/\s+/g, " ")
            .trim()
            .toLowerCase();
    }


    function visible(element) {

        if (!element) {
            return false;
        }

        return (
            element.offsetParent !== null
            &&
            getComputedStyle(element).display !== "none"
        );
    }


    function findHeaderRow(table) {

        const rows =
            Array.from(
                table.querySelectorAll("thead tr")
            );


        let best =
            null;

        let bestScore =
            -1;


        rows.forEach(function (row) {

            const headers =
                Array.from(
                    row.querySelectorAll("th")
                );


            if (!headers.length) {
                return;
            }


            const text =
                normalize(
                    headers
                        .map(
                            (header) =>
                                header.textContent
                        )
                        .join(" ")
                );


            let score =
                headers.length;


            if (text.includes("priority")) {
                score += 20;
            }

            if (
                text.includes("delivery")
                ||
                text.includes("due")
            ) {
                score += 10;
            }

            if (text.includes("wip")) {
                score += 10;
            }

            if (
                text.includes("job card")
                ||
                text.includes("jc no")
            ) {
                score += 10;
            }


            if (score > bestScore) {

                bestScore =
                    score;

                best =
                    row;
            }
        });


        return best;
    }


    function columnMap(table) {

        const headerRow =
            findHeaderRow(table);


        if (!headerRow) {
            return null;
        }


        const headers =
            Array.from(
                headerRow.querySelectorAll("th")
            );


        const result = {
            headers,
            priority: -1,
            delivery: -1,
            wip: -1,
            jc: -1
        };


        headers.forEach(
            function (header, index) {

                const text =
                    normalize(
                        header.textContent
                    );


                if (
                    result.priority < 0
                    &&
                    (
                        text.includes("priority")
                        ||
                        text.includes("urgent")
                    )
                ) {
                    result.priority =
                        index;
                }


                if (
                    result.delivery < 0
                    &&
                    (
                        text.includes(
                            "delivery"
                        )
                        ||
                        text === "due"
                    )
                ) {
                    result.delivery =
                        index;
                }


                if (
                    result.wip < 0
                    &&
                    (
                        text.includes(
                            "current wip"
                        )
                        ||
                        text.includes(
                            "wip stage"
                        )
                        ||
                        text.includes(
                            "wip status"
                        )
                        ||
                        text === "wip"
                    )
                ) {
                    result.wip =
                        index;
                }


                if (
                    result.jc < 0
                    &&
                    (
                        text.includes(
                            "job card"
                        )
                        ||
                        text.includes(
                            "jc no"
                        )
                    )
                ) {
                    result.jc =
                        index;
                }
            }
        );


        return result;
    }


    function findPpcTable(root) {

        const tables =
            Array.from(
                root.querySelectorAll("table")
            )
            .filter(visible);


        for (const table of tables) {

            const map =
                columnMap(table);


            if (
                map
                &&
                map.priority >= 0
                &&
                (
                    map.jc >= 0
                    ||
                    map.wip >= 0
                )
            ) {
                return {
                    table,
                    map
                };
            }
        }


        return null;
    }


    function cellSignature(cell) {

        if (!cell) {
            return "";
        }


        const attributes =
            Array.from(
                cell.querySelectorAll("*")
            )
            .map(
                function (element) {

                    return [
                        element.getAttribute(
                            "title"
                        ),
                        element.getAttribute(
                            "aria-label"
                        ),
                        element.getAttribute(
                            "data-priority"
                        ),
                        element.getAttribute(
                            "data-value"
                        )
                    ]
                    .filter(Boolean)
                    .join(" ");
                }
            )
            .join(" ");


        return normalize(
            [
                cell.textContent,
                attributes
            ].join(" ")
        );
    }


    function isUrgentCell(cell) {

        if (!cell) {
            return false;
        }


        if (
            cell.classList.contains(
                "dv-priority-urgent-cell"
            )
        ) {
            return true;
        }


        const raw =
            cellSignature(cell);


        if (
            raw.includes("urgent")
            ||
            raw.includes("★")
            ||
            raw.includes("priority true")
            ||
            raw.includes("is_priority true")
            ||
            raw === "true"
            ||
            raw === "yes"
            ||
            raw === "1"
        ) {
            return true;
        }


        const filledStar =
            Array.from(
                cell.querySelectorAll("*")
            )
            .some(
                function (element) {

                    const text =
                        element.textContent || "";

                    return text.includes("★");
                }
            );


        return filledStar;
    }


    function applyPriority(
        cell,
        row
    ) {

        if (!cell) {
            return false;
        }


        const urgent =
            isUrgentCell(cell);


        cell.classList.toggle(
            "dv-priority-urgent-cell",
            urgent
        );


        row.classList.toggle(
            "dv-row-urgent",
            urgent
        );


        let target =
            cell.querySelector(
                "button, a"
            );


        if (urgent) {

            if (!target) {

                target =
                    cell.querySelector(
                        ".dv-urgent-badge"
                    );
            }


            if (!target) {

                target =
                    document.createElement(
                        "span"
                    );

                cell.textContent = "";

                cell.appendChild(
                    target
                );
            }


            if (
                target.textContent.trim() !==
                "URGENT"
            ) {
                target.textContent =
                    "URGENT";
            }


            target.classList.add(
                "dv-urgent-badge"
            );


            target.setAttribute(
                "title",
                "Urgent job card"
            );

        }
        else {

            /*
             * Normal priority should stay quiet.
             * No NORMAL badge.
             */
            if (
                !cell.querySelector(
                    "input, select"
                )
            ) {

                const current =
                    normalize(
                        cell.textContent
                    );


                if (
                    current.includes("☆")
                    ||
                    current === "false"
                    ||
                    current === "no"
                    ||
                    current === "0"
                    ||
                    current === ""
                ) {
                    cell.textContent =
                        "—";
                }
            }
        }


        return urgent;
    }


    function parseDate(text) {

        const value =
            String(text || "")
                .trim();


        let match =
            value.match(
                /\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b/
            );


        if (match) {

            return {
                year:
                    Number(match[3]),

                month:
                    Number(match[2]),

                day:
                    Number(match[1])
            };
        }


        match =
            value.match(
                /\b(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\b/
            );


        if (match) {

            return {
                year:
                    Number(match[1]),

                month:
                    Number(match[2]),

                day:
                    Number(match[3])
            };
        }


        match =
            value.match(
                /\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b/
            );


        if (match) {

            const months = {
                jan: 1,
                feb: 2,
                mar: 3,
                apr: 4,
                may: 5,
                jun: 6,
                jul: 7,
                aug: 8,
                sep: 9,
                oct: 10,
                nov: 11,
                dec: 12
            };


            const month =
                months[
                    match[2]
                        .slice(0, 3)
                        .toLowerCase()
                ];


            if (month) {

                return {
                    year:
                        Number(match[3]),

                    month,

                    day:
                        Number(match[1])
                };
            }
        }


        return null;
    }


    function calendarDiffDays(
        dateParts
    ) {

        if (!dateParts) {
            return null;
        }


        const now =
            new Date();


        const todayUtc =
            Date.UTC(
                now.getFullYear(),
                now.getMonth(),
                now.getDate()
            );


        const deliveryUtc =
            Date.UTC(
                dateParts.year,
                dateParts.month - 1,
                dateParts.day
            );


        return Math.round(
            (
                deliveryUtc -
                todayUtc
            )
            /
            86400000
        );
    }


    function applyDelivery(cell) {

        if (!cell) {
            return {
                overdue: false
            };
        }


        const oldMeta =
            cell.querySelector(
                ".dv-delivery-meta"
            );


        const rawText =
            Array.from(
                cell.childNodes
            )
            .filter(
                function (node) {

                    return !(
                        node.nodeType ===
                        Node.ELEMENT_NODE
                        &&
                        node.classList
                        &&
                        node.classList.contains(
                            "dv-delivery-meta"
                        )
                    );
                }
            )
            .map(
                (node) =>
                    node.textContent || ""
            )
            .join(" ");


        const date =
            parseDate(rawText);


        if (!date) {

            if (oldMeta) {
                oldMeta.remove();
            }

            return {
                overdue: false
            };
        }


        const days =
            calendarDiffDays(
                date
            );


        if (days === null) {

            return {
                overdue: false
            };
        }


        let text = "";
        let state = "safe";


        if (days < 0) {

            const count =
                Math.abs(days);

            text =
                `${count} day${count === 1 ? "" : "s"} overdue`;

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
                `${days} day${days === 1 ? "" : "s"} left`;

            if (days <= 7) {
                state =
                    "due";
            }
        }


        let meta =
            oldMeta;


        if (!meta) {

            meta =
                document.createElement(
                    "div"
                );

            meta.className =
                "dv-delivery-meta";

            cell.appendChild(
                meta
            );
        }


        const desiredClass =
            `dv-delivery-meta ${state}`;


        if (
            meta.className !==
            desiredClass
        ) {
            meta.className =
                desiredClass;
        }


        if (
            meta.textContent !==
            text
        ) {
            meta.textContent =
                text;
        }


        return {
            overdue:
                state === "overdue"
        };
    }


    function applyWip(cell) {

        if (!cell) {
            return false;
        }


        const text =
            normalize(
                cell.textContent
            );


        const active =
            Boolean(
                text
                &&
                text !== "—"
                &&
                text !== "-"
                &&
                text !== "completed"
            );


        cell.classList.toggle(
            "dv-wip-cell",
            active
        );


        return active;
    }


    function ensureSummary(
        table
    ) {

        let strip =
            document.querySelector(
                ".dv-draft1-summary"
            );


        if (!strip) {

            strip =
                document.createElement(
                    "section"
                );

            strip.className =
                "dv-draft1-summary";

            strip.innerHTML = `
                <div class="dv-draft1-stat">
                    <span>JCs in View</span>
                    <strong data-stat="total">0</strong>
                </div>

                <div class="dv-draft1-stat">
                    <span>In WIP</span>
                    <strong data-stat="wip">0</strong>
                </div>

                <div class="dv-draft1-stat">
                    <span>Urgent</span>
                    <strong data-stat="urgent">0</strong>
                </div>

                <div class="dv-draft1-stat">
                    <span>Overdue</span>
                    <strong data-stat="overdue">0</strong>
                </div>
            `;


            let anchor =
                table;


            for (
                let i = 0;
                i < 3;
                i += 1
            ) {

                const parent =
                    anchor.parentElement;


                if (
                    !parent
                    ||
                    parent.id === ROOT_ID
                ) {
                    break;
                }


                const classes =
                    normalize(
                        parent.className
                    );


                if (
                    classes.includes("table")
                    ||
                    classes.includes("grid")
                    ||
                    classes.includes("wrap")
                    ||
                    classes.includes("panel")
                ) {
                    anchor =
                        parent;
                }
                else {
                    break;
                }
            }


            anchor.parentElement.insertBefore(
                strip,
                anchor
            );
        }


        strip.hidden =
            false;


        return strip;
    }


    function setStat(
        strip,
        name,
        value
    ) {

        const element =
            strip.querySelector(
                `[data-stat="${name}"]`
            );


        if (
            element
            &&
            element.textContent !==
            String(value)
        ) {
            element.textContent =
                String(value);
        }
    }


    function enhance() {

        if (running) {
            return;
        }


        running =
            true;


        try {

            const root =
                document.getElementById(
                    ROOT_ID
                );


            if (!root) {
                return;
            }


            const found =
                findPpcTable(root);


            const existingStrip =
                document.querySelector(
                    ".dv-draft1-summary"
                );


            if (!found) {

                if (existingStrip) {
                    existingStrip.hidden =
                        true;
                }

                return;
            }


            const {
                table,
                map
            } =
                found;


            table.classList.add(
                "dv-draft1-table"
            );


            const rows =
                Array.from(
                    table.querySelectorAll(
                        "tbody tr"
                    )
                )
                .filter(visible);


            let urgentCount = 0;
            let overdueCount = 0;
            let wipCount = 0;


            rows.forEach(
                function (row) {

                    const cells =
                        Array.from(
                            row.children
                        );


                    const priorityCell =
                        cells[
                            map.priority
                        ];


                    if (
                        applyPriority(
                            priorityCell,
                            row
                        )
                    ) {
                        urgentCount +=
                            1;
                    }


                    if (
                        map.delivery >= 0
                        &&
                        applyDelivery(
                            cells[
                                map.delivery
                            ]
                        ).overdue
                    ) {
                        overdueCount +=
                            1;
                    }


                    if (
                        map.wip >= 0
                        &&
                        applyWip(
                            cells[
                                map.wip
                            ]
                        )
                    ) {
                        wipCount +=
                            1;
                    }
                }
            );


            const strip =
                ensureSummary(
                    table
                );


            setStat(
                strip,
                "total",
                rows.length
            );


            setStat(
                strip,
                "wip",
                wipCount
            );


            setStat(
                strip,
                "urgent",
                urgentCount
            );


            setStat(
                strip,
                "overdue",
                overdueCount
            );

        }
        finally {

            running =
                false;
        }
    }


    function scheduleEnhance() {

        if (refreshTimer) {

            clearTimeout(
                refreshTimer
            );
        }


        refreshTimer =
            setTimeout(
                enhance,
                80
            );
    }


    function init() {

        const root =
            document.getElementById(
                ROOT_ID
            );


        if (!root) {
            return;
        }


        enhance();


        observer =
            new MutationObserver(
                scheduleEnhance
            );


        observer.observe(
            root,
            {
                childList: true,
                subtree: true
            }
        );


        window.addEventListener(
            "resize",
            scheduleEnhance,
            {
                passive: true
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
                once: true
            }
        );

    }
    else {

        init();
    }

})();