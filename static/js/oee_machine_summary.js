"use strict";


function omsPct(value) {

    const n = Number(value);

    if (!Number.isFinite(n)) {
        return "-";
    }

    return n.toFixed(1) + "%";
}


function omsHours(value) {

    const n = Number(value);

    if (!Number.isFinite(n)) {
        return "-";
    }

    return n.toFixed(1) + "h";
}


function omsNumber(value) {

    const n = Number(value);

    if (!Number.isFinite(n)) {
        return "0";
    }

    return Math.round(n).toLocaleString();
}


function omsEscape(value) {

    return String(
        value === null
        || value === undefined
            ? ""
            : value
    )
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


function omsShiftName(value) {

    const raw = String(
        value || ""
    ).trim();

    if (
        raw === "1"
        || raw.toLowerCase() === "shift 1"
    ) {
        return "Shift 1";
    }

    if (
        raw === "2"
        || raw.toLowerCase() === "shift 2"
    ) {
        return "Shift 2";
    }

    if (!raw) {
        return "-";
    }

    if (
        raw.toLowerCase().startsWith(
            "shift"
        )
    ) {
        return raw;
    }

    return "Shift " + raw;
}


function omsOeeClass(value) {

    const n = Number(value);

    if (!Number.isFinite(n)) {
        return "";
    }

    if (n >= 85) {
        return "oms-oee-good";
    }

    if (n >= 65) {
        return "oms-oee-watch";
    }

    return "oms-oee-low";
}


function omsRenderKpi(kpi) {

    if (!kpi) {
        return;
    }


    const set =
        function(id, value) {

            const el =
                document.getElementById(id);

            if (el) {
                el.textContent = value;
            }
        };


    const active =
        Number(
            kpi.active_machines || 0
        );

    const total =
        Number(
            kpi.total_machines || 0
        );


    set(
        "kpi-machines",
        total > active
            ? active + " / " + total
            : String(active)
    );

    set(
        "kpi-oee",
        omsPct(kpi.oee_pct)
    );

    set(
        "kpi-ar",
        omsPct(kpi.ar_pct)
    );

    set(
        "kpi-pr",
        omsPct(kpi.pr_pct)
    );

    set(
        "kpi-qr",
        omsPct(kpi.qr_pct)
    );

    set(
        "kpi-parts",
        omsNumber(kpi.total_qty)
    );

    set(
        "kpi-planned",
        omsHours(kpi.planned_hours)
    );

    set(
        "kpi-run",
        omsHours(kpi.run_hours)
    );
}


function omsRenderMachines(machines) {

    const host =
        document.getElementById(
            "oms-machine-grid"
        );

    const empty =
        document.getElementById(
            "oms-empty"
        );


    if (!host) {
        return;
    }


    if (
        !Array.isArray(machines)
        || machines.length === 0
    ) {

        host.innerHTML = "";

        if (empty) {
            empty.hidden = false;
        }

        return;
    }


    if (empty) {
        empty.hidden = true;
    }


    const sorted =
        [...machines].sort(
            function(a, b) {

                return (
                    Number(b.oee_pct || 0)
                    -
                    Number(a.oee_pct || 0)
                );
            }
        );


    host.innerHTML =
        sorted.map(
            function(machine, index) {

                const shifts =
                    Array.isArray(
                        machine.shifts
                    )
                        ? machine.shifts
                        : [];


                const rejected =
                    Number(
                        machine.rejected_qty || 0
                    );

                const hold =
                    Number(
                        machine.hold_qty || 0
                    );


                const shiftHtml =
                    shifts.length
                        ? shifts.map(
                            function(shift) {

                                return `
                                    <div
                                        class="
                                            oms-shift-row
                                        "
                                    >
                                        <div
                                            class="
                                                oms-shift-name
                                            "
                                        >
                                            ${omsEscape(
                                                omsShiftName(
                                                    shift.shift_name
                                                )
                                            )}
                                        </div>

                                        <div>
                                            <span>OEE</span>
                                            <strong>
                                                ${omsPct(
                                                    shift.oee_pct
                                                )}
                                            </strong>
                                        </div>

                                        <div>
                                            <span>AR</span>
                                            <strong>
                                                ${omsPct(
                                                    shift.ar_pct
                                                )}
                                            </strong>
                                        </div>

                                        <div>
                                            <span>PR</span>
                                            <strong>
                                                ${omsPct(
                                                    shift.pr_pct
                                                )}
                                            </strong>
                                        </div>

                                        <div>
                                            <span>QR</span>
                                            <strong>
                                                ${omsPct(
                                                    shift.qr_pct
                                                )}
                                            </strong>
                                        </div>

                                        <div>
                                            <span>Runs</span>
                                            <strong>
                                                ${omsNumber(
                                                    shift.session_count
                                                    || 0
                                                )}
                                            </strong>
                                        </div>
                                    </div>
                                `;
                            }
                        ).join("")
                        : `
                            <div
                                class="
                                    oms-no-shift
                                "
                            >
                                No shift details available.
                            </div>
                        `;


                return `
                    <article class="oms-machine">

                        <button
                            type="button"
                            class="oms-machine-main"
                            data-machine-row="${index}"
                            aria-expanded="false"
                        >

                            <div class="oms-machine-identity">

                                <div
                                    class="
                                        oms-machine-rank
                                    "
                                >
                                    ${index + 1}
                                </div>

                                <div>

                                    <strong>
                                        ${omsEscape(
                                            machine.machine_name
                                        )}
                                    </strong>

                                    <span>
                                        ${omsEscape(
                                            machine.machine_no
                                        )}
                                        &nbsp;&middot;&nbsp;
                                        ${omsEscape(
                                            String(
                                                machine.machine_category
                                                || "-"
                                            ).toUpperCase()
                                        )}
                                    </span>

                                </div>

                            </div>


                            <div class="oms-machine-oee">

                                <span>OEE</span>

                                <strong
                                    class="${omsOeeClass(
                                        machine.oee_pct
                                    )}"
                                >
                                    ${omsPct(
                                        machine.oee_pct
                                    )}
                                </strong>

                            </div>


                            <div class="oms-machine-factor">

                                <span>Availability</span>

                                <strong>
                                    ${omsPct(
                                        machine.ar_pct
                                    )}
                                </strong>

                            </div>


                            <div class="oms-machine-factor">

                                <span>Performance</span>

                                <strong>
                                    ${omsPct(
                                        machine.pr_pct
                                    )}
                                </strong>

                            </div>


                            <div class="oms-machine-factor">

                                <span>Quality</span>

                                <strong>
                                    ${omsPct(
                                        machine.qr_pct
                                    )}
                                </strong>

                            </div>


                            <div class="oms-machine-output">

                                <div>
                                    <span>OK</span>
                                    <strong>
                                        ${omsNumber(
                                            machine.ok_qty
                                        )}
                                    </strong>
                                </div>

                                <div>
                                    <span>Reject</span>
                                    <strong
                                        class="${rejected > 0
                                            ? "oms-reject"
                                            : ""}"
                                    >
                                        ${omsNumber(
                                            machine.rejected_qty
                                        )}
                                    </strong>
                                </div>

                                <div>
                                    <span>Hold</span>
                                    <strong
                                        class="${hold > 0
                                            ? "oms-hold"
                                            : ""}"
                                    >
                                        ${omsNumber(
                                            machine.hold_qty
                                        )}
                                    </strong>
                                </div>

                            </div>


                            <div class="oms-machine-time">

                                <div>
                                    <span>Planned</span>
                                    <strong>
                                        ${omsHours(
                                            machine.planned_hours
                                        )}
                                    </strong>
                                </div>

                                <div>
                                    <span>Run</span>
                                    <strong>
                                        ${omsHours(
                                            machine.run_hours
                                        )}
                                    </strong>
                                </div>

                            </div>


                            <div class="oms-machine-expand">

                                <i
                                    class="fa fa-chevron-down"
                                    aria-hidden="true"
                                ></i>

                            </div>

                        </button>


                        <div
                            class="oms-machine-detail"
                            data-machine-detail="${index}"
                            hidden
                        >

                            <div class="oms-detail-title">
                                Shift Performance
                            </div>

                            ${shiftHtml}

                        </div>

                    </article>
                `;
            }
        ).join("");


    host
        .querySelectorAll(
            "[data-machine-row]"
        )
        .forEach(
            function(button) {

                button.addEventListener(
                    "click",
                    function() {

                        const key =
                            button.getAttribute(
                                "data-machine-row"
                            );

                        const detail =
                            host.querySelector(
                                '[data-machine-detail="'
                                + key
                                + '"]'
                            );

                        if (!detail) {
                            return;
                        }


                        const open =
                            button.getAttribute(
                                "aria-expanded"
                            ) === "true";


                        button.setAttribute(
                            "aria-expanded",
                            open
                                ? "false"
                                : "true"
                        );

                        detail.hidden =
                            open;
                    }
                );
            }
        );
}


function omsLoad() {

    const host =
        document.getElementById(
            "oms-machine-grid"
        );

    const error =
        document.getElementById(
            "oms-error"
        );

    const period =
        document.getElementById(
            "oms-period"
        );


    if (error) {
        error.hidden = true;
    }


    if (host) {
        host.innerHTML = `
            <div class="oms-loading">
                <i
                    class="fa fa-spinner fa-spin"
                    aria-hidden="true"
                ></i>
                Loading machine performance...
            </div>
        `;
    }


    const params =
        new URLSearchParams();


    try {

        const date =
            localStorage.getItem(
                "jms_filter_date"
            );

        if (date) {

            params.set(
                "from_date",
                date
            );

            params.set(
                "to_date",
                date
            );
        }

    } catch (_) {
        // Date filter is optional.
    }


    fetch(
        "/api/oee-machine-summary/overview?"
        + params.toString(),
        {
            cache: "no-store"
        }
    )
        .then(
            function(response) {

                if (!response.ok) {
                    throw new Error(
                        "HTTP "
                        + response.status
                    );
                }

                return response.json();
            }
        )
        .then(
            function(data) {

                if (data.error) {
                    throw new Error(
                        data.error
                    );
                }


                if (
                    period
                    && data.period
                    && data.period.from_date
                ) {

                    const from =
                        data.period.from_date;

                    const to =
                        data.period.to_date;


                    period.textContent =
                        from === to
                            ? "Date: " + from
                            : (
                                "Period: "
                                + from
                                + " to "
                                + to
                            );
                }


                omsRenderKpi(
                    data.kpi || {}
                );

                omsRenderMachines(
                    data.machines || []
                );
            }
        )
        .catch(
            function(err) {

                if (host) {
                    host.innerHTML = "";
                }

                if (error) {

                    error.textContent =
                        "Unable to load OEE summary: "
                        + err.message;

                    error.hidden = false;
                }
            }
        );
}


document.addEventListener(
    "DOMContentLoaded",
    function() {

        const refresh =
            document.getElementById(
                "oms-refresh-btn"
            );

        if (refresh) {

            refresh.addEventListener(
                "click",
                omsLoad
            );
        }

        omsLoad();
    }
);
