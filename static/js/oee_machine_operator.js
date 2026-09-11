const jcInput =
    document.getElementById(
        "machine-oee-jc-input"
    );


if (jcInput) {

    window.setTimeout(
        function() {
            jcInput.focus();
            jcInput.select();
        },
        100
    );

}



/* MACHINE_OEE_JC_FETCH_V1_START */

let machineOeePendingRunV1 = null;

let machineOeeCurrentFetchedJcV1 = null;

let machineOeeIncomingCardV1 = null;


/* ---------------------------------------------------------
 * HELPERS
 * --------------------------------------------------------- */

function machineOeeEscapeV1(value) {

    return String(
        value === null
        || value === undefined
            ? ""
            : value
    )
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function machineOeeProcessCategoryV1(
    processName
) {

    const name = String(
        processName || ""
    )
        .trim()
        .toLowerCase();


    if (
        name.startsWith(
            "cnc machining"
        )
    ) {
        return "CNC";
    }


    if (
        name.startsWith(
            "vmc machining"
        )
    ) {
        return "VMC";
    }


    return "";
}


function machineOeeRequiredQtyV1(
    card
) {

    const jcQty =
        Number(
            card?.job_card_qty
            || 0
        );


    if (
        Number.isFinite(jcQty)
        &&
        jcQty > 0
    ) {
        return jcQty;
    }


    const soQty =
        Number(
            card?.so_qty
            || 0
        );


    return (
        Number.isFinite(soQty)
        &&
        soQty > 0
    )
        ? soQty
        : 0;
}


function machineOeeSetSearchEnabledV1(
    enabled
) {

    const input =
        document.getElementById(
            "machine-oee-jc-input"
        );


    const button =
        document.getElementById(
            "machine-oee-fetch-btn"
        );


    if (input) {
        input.disabled =
            !enabled;
    }


    if (button) {
        button.disabled =
            !enabled;

        button.style.cursor =
            enabled
                ? "pointer"
                : "not-allowed";

        button.style.opacity =
            enabled
                ? "1"
                : ".55";
    }


    if (
        enabled
        &&
        input
    ) {

        window.setTimeout(
            function() {

                /*
                 * OEE_FOCUS_STEAL_FIX_V107
                 *
                 * Job Card autofocus is useful only when
                 * the operator is actually free to scan/type
                 * a Job Card.
                 *
                 * Never steal focus from Tool UID, Tool
                 * Action, Corner, Reason, Usage, Shift,
                 * losses, production fields, or any other
                 * active editable control.
                 */

                const active =
                    document.activeElement;


                const activeIsEditable =
                    Boolean(
                        active
                        &&
                        active !== document.body
                        &&
                        (
                            active.matches?.(
                                "input, select, textarea, button"
                            )
                            ||
                            active.isContentEditable
                        )
                    );


                if (
                    activeIsEditable
                    &&
                    active !== input
                ) {

                    return;
                }


                /*
                 * Tool Room / Development can leave the
                 * Job Card input present in DOM while its
                 * section is hidden.
                 *
                 * A hidden JC input must never receive
                 * automatic focus.
                 */
                const style =
                    window.getComputedStyle(
                        input
                    );


                const visible =
                    (
                        input.offsetParent !== null
                        &&
                        !input.hidden
                        &&
                        style.display !== "none"
                        &&
                        style.visibility !== "hidden"
                    );


                if (!visible) {

                    return;
                }


                input.focus();
                input.select();
            },
            80
        );
    }
}


/* ---------------------------------------------------------
 * CHECK IF THIS MACHINE ALREADY HAS PENDING WORK
 * --------------------------------------------------------- */

/*
 * MACHINE_OEE_SHARED_PENDING_READ_V1
 *
 * Share repeated pending-run reads during page initialization.
 * Cache lifetime is intentionally short.
 */
const machineOeePendingReadCacheV1 =
    new Map();


async function machineOeeGetPendingSharedV1(
    machineId
) {

    const key =
        String(
            machineId
            || ""
        ).trim();


    if (!key) {

        throw new Error(
            "Machine ID is required."
        );
    }


    const now =
        Date.now();


    const cached =
        machineOeePendingReadCacheV1.get(
            key
        );


    if (
        cached
        &&
        (
            now
            -
            Number(
                cached.createdAt
                || 0
            )
        ) < 1500
    ) {

        return await cached.promise;
    }


    const promise =
        (async function() {

            const response =
                await fetch(
                    "/api/oee-machine/pending/"
                    +
                    encodeURIComponent(
                        key
                    ),
                    {
                        cache:
                            "no-store"
                    }
                );


            const data =
                await response.json();


            return {
                ok:
                    response.ok,

                status:
                    response.status,

                data:
                    data
            };

        })();


    machineOeePendingReadCacheV1.set(
        key,
        {
            createdAt:
                now,

            promise:
                promise
        }
    );


    try {

        return await promise;

    } catch (error) {

        machineOeePendingReadCacheV1.delete(
            key
        );

        throw error;
    }
}


window.machineOeeGetPendingSharedV1 =
    machineOeeGetPendingSharedV1;


async function machineOeeCheckPendingV1() {

    const context =
        window.NMTG_MACHINE_OEE_CONTEXT;


    const resultHost =
        document.getElementById(
            "machine-oee-jc-result-v1"
        );


    if (
        !context
        ||
        !context.machine_id
        ||
        !resultHost
    ) {
        return;
    }


    try {

        const pendingResultV1 =
            await machineOeeGetPendingSharedV1(
                context.machine_id
            );


        const response = {
            ok:
                pendingResultV1.ok,

            status:
                pendingResultV1.status
        };


        const data =
            pendingResultV1.data;


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || "Unable to check machine status."
            );
        }


        machineOeePendingRunV1 =
            data.pending_run
            || null;


        if (
            data.has_pending_run
            &&
            machineOeePendingRunV1
        ) {

            machineOeeSetSearchEnabledV1(
                false
            );


            const run =
                machineOeePendingRunV1;


            resultHost.innerHTML = `

                <div class="pending-machine-v1">

                    <h3>
                        Current / Previous Machine Entry
                    </h3>

                    <p>
                        This machine already has an unfinished
                        Job Card. Continue or complete this work
                        before starting another JC.
                    </p>

                    <div
                        class="jc-state-grid-v1"
                        style="margin-top:11px;"
                    >

                        <div class="jc-info-v1">
                            <span>Job Card</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    run.job_card_no
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Process</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    run.process_name
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Status</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    run.run_status
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Operator</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    run.operator_name
                                    || "-"
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Started</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    run.started_at
                                    || "-"
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Previous Shift</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    run.shift_name
                                    || "-"
                                )}
                            </strong>
                        </div>

                    </div>

                    <div class="oee-void-action-v1">
                        <button
                            type="button"
                            class="oee-void-btn-v1"
                            data-run-id="${machineOeeEscapeV1(String(run.run_id || ""))}"
                        >
                            Wrong JC? Cancel this entry<i fa class="fa fa-times-circle" aria-hidden="true"></i>
                        </button>
                    </div>

                </div>
            `;

            /* MACHINE_OEE_VOID_BUTTON_V1 */
            (function () {
                var _b = resultHost.querySelector(".oee-void-btn-v1");
                if (!_b) { return; }
                _b.addEventListener("click", async function () {
                    var _rid = _b.dataset.runId;
                    if (!_rid) { return; }
                    if (!confirm("Void this run? This cannot be undone.")) { return; }
                    _b.disabled = true;
                    try {
                        var _r = await fetch(
                            "/api/oee-machine/run/" + _rid + "/void",
                            {
                                method: "POST",
                                headers: { "Content-Type": "application/json" }
                            }
                        );
                        if (_r.ok) {
                            resultHost.innerHTML =
                                '<div class="upcoming">' +
                                '<strong>Entry Cancelled</strong>' +
                                '<span>Run voided. You may now start a new JC.</span>' +
                                '</div>';
                            if (typeof machineOeePendingRunV1 !== "undefined") {
                                machineOeePendingRunV1 = null;
                            }
                            if (typeof machineOeeActiveRunV1 !== "undefined") {
                                machineOeeActiveRunV1 = null;
                            }
                            var _pe = document.getElementById(
                                "machine-oee-production-entry-v1"
                            );
                            if (_pe) { _pe.remove(); }
                            if (typeof machineOeeSetSearchEnabledV1 === "function") {
                                machineOeeSetSearchEnabledV1(true);
                            }
                        } else {
                            var _j = await _r.json().catch(function () { return {}; });
                            alert(_j.error || "Could not void. Please try again.");
                            _b.disabled = false;
                        }
                    } catch (_e) {
                        alert("Network error. Please try again.");
                        _b.disabled = false;
                    }
                });
            })();


            return;
        }


        machineOeeSetSearchEnabledV1(
            true
        );


        resultHost.innerHTML = `

            <div class="upcoming">

                <strong>
                    Machine Ready
                </strong>

                <span>
                    Scan / enter Job Card number.
                </span>

            </div>
        `;


    } catch (error) {

        machineOeeSetSearchEnabledV1(
            false
        );


        resultHost.innerHTML = `

            <div class="machine-page-error-v1">
                ${machineOeeEscapeV1(
                    error.message
                    || "Unable to check machine status."
                )}
            </div>
        `;
    }
}


/* ---------------------------------------------------------
 * FETCH JC
 *
 * IMPORTANT:
 * Uses EXISTING proven JMS APIs.
 * --------------------------------------------------------- */

async function machineOeeFetchJcV1() {

    if (machineOeePendingRunV1) {
        return;
    }


    const context =
        window.NMTG_MACHINE_OEE_CONTEXT;


    const input =
        document.getElementById(
            "machine-oee-jc-input"
        );


    const resultHost =
        document.getElementById(
            "machine-oee-jc-result-v1"
        );


    const enteredJc =
        String(
            input?.value
            || ""
        ).trim();


    if (!enteredJc) {

        resultHost.innerHTML = `

            <div class="jc-state-v1 error">

                Please enter Job Card number.

            </div>
        `;

        input?.focus();

        return;
    }


    resultHost.innerHTML = `

        <div class="upcoming">

            <strong>
                Checking Job Card...
            </strong>

            <span>
                Please wait.
            </span>

        </div>
    `;


    try {

        /*
         * Step 1:
         * Existing quality-check fetch resolves
         * shortened JC numbers correctly.
         */
        const fetchResponse =
            await fetch(
                "/api/quality_check/fetch/"
                +
                encodeURIComponent(
                    enteredJc
                ),
                {
                    cache:"no-store"
                }
            );


        const fetchData =
            await fetchResponse.json();


        /*
         * OEE_UI_CLEANUP_V57
         *
         * Keep the already-fetched full JC response for
         * presentation only.
         */
        window.machineOeeUiFetchedDetailsV57 =
            fetchData;



        if (
            !fetchResponse.ok
            ||
            fetchData.success === false
        ) {

            throw new Error(
                fetchData.error
                || fetchData.message
                || "Job Card not found."
            );
        }


        const actualJc =
            String(
                fetchData?.job_card?.job_card_no
                || enteredJc
            ).trim();


        /*
         * Step 2:
         * Reuse existing current/incoming operator
         * queue logic.
         */
        const queueResponse =
            await fetch(
                "/api/operator/job_cards"
                + "?include_incoming=1"
                + "&job_card_no="
                + encodeURIComponent(
                    actualJc
                ),
                {
                    cache:"no-store"
                }
            );


        const queueData =
            await queueResponse.json();


        if (
            !queueResponse.ok
            ||
            queueData.success === false
        ) {

            throw new Error(
                queueData.error
                || "Unable to validate Job Card process."
            );
        }


        const queueCards =
            queueData.job_cards
            || [];


        const currentCard =
            queueCards.find(
                function(card) {

                    return (
                        card?.is_incoming !== true
                        &&
                        String(
                            card?.job_card_no
                            || ""
                        ).trim()
                        === actualJc
                    );
                }
            );


        const incomingCard =
            queueCards.find(
                function(card) {

                    return (
                        card?.is_incoming === true
                        &&
                        String(
                            card?.job_card_no
                            || ""
                        ).trim()
                        === actualJc
                    );
                }
            );


        /*
         * CURRENT CNC/VMC PROCESS
         */
        if (currentCard) {

            const currentProcess =
                String(
                    currentCard.current_process
                    || currentCard.wip_status
                    || ""
                ).trim();


            const requiredCategory =
                machineOeeProcessCategoryV1(
                    currentProcess
                );


            if (
                requiredCategory
                &&
                requiredCategory
                !== String(
                    context.machine_category
                    || ""
                ).trim().toUpperCase()
            ) {

                throw new Error(
                    `${actualJc} is at ${currentProcess}. `
                    +
                    `Please select a ${requiredCategory} machine.`
                );
            }


            machineOeeCurrentFetchedJcV1 =
                currentCard;


            machineOeeIncomingCardV1 =
                null;


            input.value =
                actualJc;


            resultHost.innerHTML = `

                <div class="jc-state-v1 success">

                    <div class="jc-state-head-v1">

                        <strong>
                            Job Card Ready
                        </strong>

                        <span class="jc-status-chip-v1">
                            CURRENT PROCESS
                        </span>

                    </div>


                    <div class="jc-state-grid-v1">

                        <div class="jc-info-v1">
                            <span>Job Card</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    actualJc
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Item</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    currentCard.item_name
                                    || "-"
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Current Process</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    currentProcess
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Next Process</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    currentCard.next_process
                                    || "Store"
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Available Qty</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    currentCard.available_qty
                                    ??
                                    currentCard.job_card_qty
                                    ??
                                    currentCard.so_qty
                                    ??
                                    "-"
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Selected Machine</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    context.machine_no
                                )}
                            </strong>
                        </div>

                    </div>


                    <div class="jc-action-v1">

                        <button
                            type="button"
                            class="jc-ready-btn-v1"
                            disabled
                        >
                            <i
                                class="fa fa-play-circle"
                                aria-hidden="true"
                            ></i>

                            <span>
                                Ready to Start
                            </span>
                        </button>

                    </div>

                </div>
            `;


            return;
        }


        /*
         * IMMEDIATE PREVIOUS PROCESS PENDING
         */
        if (incomingCard) {

            const incomingProcess =
                String(
                    incomingCard.incoming_for_process
                    || incomingCard.next_process
                    || ""
                ).trim();


            const requiredCategory =
                machineOeeProcessCategoryV1(
                    incomingProcess
                );


            if (
                requiredCategory
                &&
                requiredCategory
                !== String(
                    context.machine_category
                    || ""
                ).trim().toUpperCase()
            ) {

                throw new Error(
                    `${actualJc} is incoming for ${incomingProcess}. `
                    +
                    `Please select a ${requiredCategory} machine.`
                );
            }


            machineOeeCurrentFetchedJcV1 =
                null;


            machineOeeIncomingCardV1 =
                incomingCard;


            input.value =
                actualJc;


            const requiredQty =
                machineOeeRequiredQtyV1(
                    incomingCard
                );


            resultHost.innerHTML = `

                <div class="jc-state-v1 warning">

                    <div class="jc-state-head-v1">

                        <strong>
                            Receive Material Required
                        </strong>

                        <span class="jc-status-chip-v1">
                            PREVIOUS PROCESS PENDING
                        </span>

                    </div>


                    <div class="jc-state-grid-v1">

                        <div class="jc-info-v1">
                            <span>Job Card</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    actualJc
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Previous Process</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    incomingCard.previous_process_to_complete
                                    || incomingCard.current_process
                                    || "-"
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Your Process</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    incomingProcess
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">
                            <span>Required Qty</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    requiredQty
                                )}
                            </strong>
                        </div>


                        <div class="jc-info-v1">

                            <span>
                                Received Qty
                            </span>

                            <input
                                id="machine-oee-received-qty-v1"
                                class="receive-qty-v1"
                                type="number"
                                min="0"
                                step="1"
                                value="${machineOeeEscapeV1(
                                    requiredQty
                                )}"
                            >

                        </div>


                        <div class="jc-info-v1">
                            <span>Selected Machine</span>
                            <strong>
                                ${machineOeeEscapeV1(
                                    context.machine_no
                                )}
                            </strong>
                        </div>

                    </div>


                    <div class="jc-action-v1">

                        <button
                            type="button"
                            class="jc-receive-btn-v1"
                            onclick="
                                machineOeeReceiveMaterialV1()
                            "
                        >
                            Receive Material
                        </button>

                    </div>

                </div>
            `;


            return;
        }


        throw new Error(
            `${actualJc} is not currently available `
            +
            `for your CNC/VMC operator process.`
        );

    } catch (error) {

        resultHost.innerHTML = `

            <div class="jc-state-v1 error">
                ${machineOeeEscapeV1(
                    error.message
                    || "Unable to fetch Job Card."
                )}
            </div>
        `;
    }
}


/* MACHINE_OEE_JC_FETCH_V1_END */




/* MACHINE_OEE_RECEIVE_MATERIAL_V1_START */

async function machineOeeReceiveMaterialV1() {

    const card =
        machineOeeIncomingCardV1;


    if (!card) {
        return;
    }


    const qtyInput =
        document.getElementById(
            "machine-oee-received-qty-v1"
        );


    const requiredQty =
        machineOeeRequiredQtyV1(
            card
        );


    const receivedQty =
        Number(
            qtyInput?.value
            || 0
        );


    if (
        !Number.isInteger(
            receivedQty
        )
        ||
        receivedQty <= 0
    ) {

        alert(
            "Enter valid Received Qty."
        );

        qtyInput?.focus();

        return;
    }


    if (
        receivedQty
        !== requiredQty
    ) {

        alert(
            `Full Qty ${requiredQty} must be received.`
        );

        qtyInput?.focus();

        return;
    }


    const incomingProcess =
        String(
            card.incoming_for_process
            || card.next_process
            || ""
        ).trim();


    if (!incomingProcess) {

        alert(
            "Incoming CNC/VMC process was not found."
        );

        return;
    }


    const resultHost =
        document.getElementById(
            "machine-oee-jc-result-v1"
        );


    resultHost.innerHTML = `

        <div class="upcoming">

            <strong>
                Receiving Material...
            </strong>

            <span>
                Please wait.
            </span>

        </div>
    `;


    try {

        const response =
            await fetch(
                "/api/wip/update",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({
                        job_card_no:
                            card.job_card_no,

                        item_name:
                            card.item_name,

                        new_stage:
                            incomingProcess,

                        incoming_receipt:
                            true,

                        received_qty:
                            receivedQty,

                        stage_remark:
                            `Material received by CNC/VMC operator. `
                            +
                            `Received Qty ${receivedQty}/${requiredQty}.`
                    })
                }
            );


        const data =
            await response.json();


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || data.message
                || "Receive Material failed."
            );
        }


        machineOeeIncomingCardV1 =
            null;


        /*
         * Re-fetch same JC.
         * It should now appear as current CNC/VMC.
         */
        await machineOeeFetchJcV1();


    } catch (error) {

        resultHost.innerHTML = `

            <div class="jc-state-v1 error">

                ${machineOeeEscapeV1(
                    error.message
                    || "Receive Material failed."
                )}

            </div>
        `;
    }
}


/* ---------------------------------------------------------
 * EVENTS
 * --------------------------------------------------------- */

const machineOeeFetchButtonV1 =
    document.getElementById(
        "machine-oee-fetch-btn"
    );


const machineOeeJcInputV1 =
    document.getElementById(
        "machine-oee-jc-input"
    );


if (machineOeeFetchButtonV1) {

    machineOeeFetchButtonV1.addEventListener(
        "click",
        machineOeeFetchJcV1
    );
}


if (machineOeeJcInputV1) {

    machineOeeJcInputV1.addEventListener(
        "keydown",
        function(event) {

            if (
                event.key
                === "Enter"
            ) {

                event.preventDefault();

                machineOeeFetchJcV1();
            }
        }
    );


    /* AUTO_FETCH_ON_COMPLETE_JC_V1
     * Fires automatically when operator types
     * a complete 6-digit or 10-digit JC number.
     * 350ms debounce prevents mid-typing triggers.
     */
    let _jcAutoFetchTimerV1 = null;

    machineOeeJcInputV1.addEventListener(
        "input",
        function() {

            clearTimeout(_jcAutoFetchTimerV1);

            if (machineOeePendingRunV1) {
                return;
            }

            const val = String(
                machineOeeJcInputV1.value || ""
            ).trim();

            if (
                !/^\d{6}$/.test(val)
                && !/^\d{10}$/.test(val)
            ) {
                return;
            }

            _jcAutoFetchTimerV1 = window.setTimeout(
                function() {
                    machineOeeFetchJcV1();
                },
                350
            );
        }
    );
}


/*
 * Check machine immediately.
 */
window.setTimeout(
    machineOeeCheckPendingV1,
    100
);


/* MACHINE_OEE_RECEIVE_MATERIAL_V1_END */




/* MACHINE_OEE_START_RUN_V1_START */

const MACHINE_OEE_SHIFT_STORAGE_V1 =
    "jms_machine_oee_shift_v1";


let machineOeeActiveRunV1 =
    null;


/* ---------------------------------------------------------
 * SHIFT - SELECT ONCE
 * --------------------------------------------------------- */

/* MACHINE_OEE_TWO_SHIFT_V21 */

const MACHINE_OEE_SHIFT_TIMES_V11 = {

    "Shift 1": {
        start: "08:00:00",
        end: "19:00:00"
    },

    "Shift 2": {
        start: "19:00:00",
        end: "06:00:00"
    }
};


/* MACHINE_OEE_HMS_INPUT_V18 */

function machineOeeNormalizeHmsV18(
    value
) {

    const raw =
        String(
            value || ""
        ).trim();


    if (!raw) {
        return "";
    }


    const parts =
        raw.split(":");


    if (
        parts.length < 2
        ||
        parts.length > 3
    ) {

        return raw;
    }


    const hours =
        Number(
            parts[0]
        );


    const minutes =
        Number(
            parts[1]
        );


    const seconds =
        parts.length === 3
        ? Number(
            parts[2]
        )
        : 0;


    if (
        !Number.isInteger(hours)
        ||
        !Number.isInteger(minutes)
        ||
        !Number.isInteger(seconds)
        ||
        hours < 0
        ||
        hours > 23
        ||
        minutes < 0
        ||
        minutes > 59
        ||
        seconds < 0
        ||
        seconds > 59
    ) {

        return raw;
    }


    return (
        String(hours).padStart(
            2,
            "0"
        )
        + ":"
        + String(minutes).padStart(
            2,
            "0"
        )
        + ":"
        + String(seconds).padStart(
            2,
            "0"
        )
    );
}


function machineOeeShiftTimeStorageKeyV11(
    shift,
    field
) {

    const safeShift =
        String(
            shift || ""
        )
        .replace(/\s+/g, "_")
        .toLowerCase();


    return (
        "jms_machine_oee_"
        + safeShift
        + "_"
        + field
        + "_v11"
    );
}


function machineOeeShiftDurationMinutesV11(
    startValue,
    endValue
) {

    const parseTime =
        function(value) {

            const parts =
                String(
                    value || ""
                )
                .split(":");


            if (
                parts.length < 2
                ||
                parts.length > 3
            ) {
                return null;
            }


            const hours =
                Number(
                    parts[0]
                );


            const minutes =
                Number(
                    parts[1]
                );


            const seconds =
                parts.length === 3
                ? Number(
                    parts[2]
                )
                : 0;


            if (
                !Number.isInteger(hours)
                ||
                !Number.isInteger(minutes)
                ||
                !Number.isInteger(seconds)
                ||
                hours < 0
                ||
                hours > 23
                ||
                minutes < 0
                ||
                minutes > 59
                ||
                seconds < 0
                ||
                seconds > 59
            ) {
                return null;
            }


            return (
                hours * 60
                +
                minutes
                +
                (
                    seconds
                    / 60
                )
            );
        };


    const start =
        parseTime(
            startValue
        );


    const end =
        parseTime(
            endValue
        );


    if (
        start === null
        ||
        end === null
    ) {
        return null;
    }


    let duration =
        end - start;


    /*
     * Shift 2 crosses midnight:
     * 19:00 -> 06:00 = 660 minutes.
     */
    if (
        duration <= 0
    ) {

        duration +=
            24 * 60;
    }


    return duration;
}


function machineOeeUpdateShiftDurationV11() {

    const startInput =
        document.getElementById(
            "machine-oee-shift-start-v11"
        );


    const endInput =
        document.getElementById(
            "machine-oee-shift-end-v11"
        );


    const view =
        document.getElementById(
            "machine-oee-shift-duration-v11"
        );


    if (
        !startInput
        ||
        !endInput
        ||
        !view
    ) {
        return;
    }


    const duration =
        machineOeeShiftDurationMinutesV11(
            startInput.value,
            endInput.value
        );


    if (duration === null) {

        view.classList.remove(
            "ready"
        );


        view.innerHTML = `

            <i
                class="fa fa-clock-o"
                aria-hidden="true"
            ></i>

            <span>
                Select a shift to load the default time.
            </span>
        `;


        return;
    }


    const hours =
        Math.floor(
            duration / 60
        );


    const minutes =
        duration % 60;


    view.classList.add(
        "ready"
    );


    view.innerHTML = `

        <i
            class="fa fa-clock-o"
            aria-hidden="true"
        ></i>

        <span>
            Planned shift duration:
            ${hours} hr
            ${minutes} min
        </span>
    `;
}


function machineOeeApplyShiftTimesV11(
    shift
) {

    const startInput =
        document.getElementById(
            "machine-oee-shift-start-v11"
        );


    const endInput =
        document.getElementById(
            "machine-oee-shift-end-v11"
        );


    if (
        !startInput
        ||
        !endInput
    ) {
        return;
    }


    const defaults =
        MACHINE_OEE_SHIFT_TIMES_V11[
            shift
        ];


    if (!defaults) {

        startInput.value =
            "";


        endInput.value =
            "";


        startInput.disabled =
            true;


        endInput.disabled =
            true;


        machineOeeUpdateShiftDurationV11();

        return;
    }


    /* MACHINE_OEE_SHIFT_DEFAULT_REFRESH_V22 */

    /*
     * Shift Start/End are editable for the current page only.
     *
     * Never restore an operator-edited value after refresh.
     * Always begin from the official shift defaults.
     */
    startInput.disabled =
        false;


    endInput.disabled =
        false;


    startInput.value =
        machineOeeNormalizeHmsV18(
            defaults.start
        );


    endInput.value =
        machineOeeNormalizeHmsV18(
            defaults.end
        );


    machineOeeUpdateShiftDurationV11();
}


function machineOeeSaveShiftTimeV11(
    field
) {

    const select =
        document.getElementById(
            "machine-oee-shift-v1"
        );


    const input =
        document.getElementById(
            field === "start"
                ? "machine-oee-shift-start-v11"
                : "machine-oee-shift-end-v11"
        );


    if (
        !select
        ||
        !input
    ) {
        return;
    }


    const shift =
        String(
            select.value || ""
        ).trim();


    if (
        !shift
        ||
        !input.value
    ) {
        return;
    }


    const normalizedValue =
        machineOeeNormalizeHmsV18(
            input.value
        );


    if (normalizedValue) {

        input.value =
            normalizedValue;
    }


    /*
     * V22:
     * Use the edited value only while this page is open.
     * Do not persist it for refresh/reopen.
     */
    machineOeeUpdateShiftDurationV11();
}


function machineOeeInitShiftV1() {

    const select =
        document.getElementById(
            "machine-oee-shift-v1"
        );


    const startInput =
        document.getElementById(
            "machine-oee-shift-start-v11"
        );


    const endInput =
        document.getElementById(
            "machine-oee-shift-end-v11"
        );


    if (!select) {
        return;
    }


    /*
     * Remove stale custom shift times saved by older versions.
     * The selected Shift itself may still remain remembered.
     */
    for (
        const shiftName
        of [
            "Shift 1",
            "Shift 2"
        ]
    ) {

        sessionStorage.removeItem(
            machineOeeShiftTimeStorageKeyV11(
                shiftName,
                "start"
            )
        );


        sessionStorage.removeItem(
            machineOeeShiftTimeStorageKeyV11(
                shiftName,
                "end"
            )
        );
    }


    const saved =
        sessionStorage.getItem(
            MACHINE_OEE_SHIFT_STORAGE_V1
        );


    if (
        saved
        &&
        [
            "Shift 1",
            "Shift 2"
        ].includes(
            saved
        )
    ) {

        select.value =
            saved;
    }


    machineOeeApplyShiftTimesV11(
        String(
            select.value || ""
        ).trim()
    );


    select.addEventListener(
        "change",
        function() {

            const value =
                String(
                    select.value || ""
                ).trim();


            if (value) {

                sessionStorage.setItem(
                    MACHINE_OEE_SHIFT_STORAGE_V1,
                    value
                );

            } else {

                sessionStorage.removeItem(
                    MACHINE_OEE_SHIFT_STORAGE_V1
                );
            }


            machineOeeApplyShiftTimesV11(
                value
            );

            if (typeof window.machineOeeEnsureSessionV1 === "function") {
                window.machineOeeEnsureSessionV1();
            }
        }
    );


    if (startInput) {

        startInput.addEventListener(
            "change",
            function() {

                machineOeeSaveShiftTimeV11(
                    "start"
                );
            }
        );
    }


    if (endInput) {

        endInput.addEventListener(
            "change",
            function() {

                machineOeeSaveShiftTimeV11(
                    "end"
                );
            }
        );
    }
}


/*
 * Future-safe helper.
 *
 * This does not change the current backend/session logic.
 * It only exposes the operator-selected timing values.
 */
window.machineOeeGetShiftTimingV11 =
    function() {

        const shift =
            String(
                document.getElementById(
                    "machine-oee-shift-v1"
                )?.value
                || ""
            ).trim();


        const start =
            String(
                document.getElementById(
                    "machine-oee-shift-start-v11"
                )?.value
                || ""
            ).trim();


        const end =
            String(
                document.getElementById(
                    "machine-oee-shift-end-v11"
                )?.value
                || ""
            ).trim();


        return {
            shift_name: shift,
            start_time: start,
            end_time: end,
            planned_minutes:
                machineOeeShiftDurationMinutesV11(
                    start,
                    end
                )
        };
    };


/* ---------------------------------------------------------
 * RENDER CURRENT RUN
 * --------------------------------------------------------- */

function machineOeeRenderRunningRunV1(
    run
) {

    const resultHost =
        document.getElementById(
            "machine-oee-jc-result-v1"
        );


    if (
        !resultHost
        ||
        !run
        ||
        !Number(
            run.run_id
            || 0
        )
    ) {
        return;
    }


    machineOeeActiveRunV1 =
        run;


    machineOeePendingRunV1 =
        run;


    machineOeeSetSearchEnabledV1(
        false
    );


    resultHost.innerHTML = `

        <div class="machine-running-v1">

            <div class="machine-running-head-v1">

                <strong>
                    Current Machine Job
                </strong>
            </div>


            <div class="jc-state-grid-v1">


                <div class="jc-info-v1">

                    <span>
                        Job Card
                    </span>

                    <strong>
                        ${machineOeeEscapeV1(
                            run.job_card_no
                            || "-"
                        )}
                    </strong>

                </div>


                <div class="jc-info-v1">

                    <span>
                        Process
                    </span>

                    <strong>
                        ${machineOeeEscapeV1(
                            run.process_name
                            || "-"
                        )}
                    </strong>

                </div>


                <div class="jc-info-v1">

                    <span>
                        Machine
                    </span>

                    <strong>
                        ${machineOeeEscapeV1(
                            run.machine_no
                            || window
                                .NMTG_MACHINE_OEE_CONTEXT
                                ?.machine_no
                            || "-"
                        )}
                    </strong>

                </div>


                <div class="jc-info-v1">

                    <span>
                        Shift
                    </span>

                    <strong>
                        ${machineOeeEscapeV1(
                            run.shift_name
                            || "-"
                        )}
                    </strong>

                </div>


                <div class="jc-info-v1">

                    <span>
                        Started
                    </span>

                    <strong>
                        ${machineOeeEscapeV1(
                            run.started_at
                            || "-"
                        )}
                    </strong>

                </div>


                <div class="jc-info-v1">

                    <span>
                        Operator
                    </span>

                    <strong>
                        ${machineOeeEscapeV1(
                            run.operator_name
                            || "-"
                        )}
                    </strong>

                </div>


            </div>


            <div
                class="helper"
                style="margin-top:10px;"
            >

                Start time was captured automatically
                by the server.

            </div>


            <div style="margin-top:12px;text-align:right;">

                <button
                    id="oee-void-run-btn-v1"
                    type="button"
                    data-run-id="${
                        machineOeeEscapeV1(
                            String(run.run_id || "")
                        )
                    }"
                    style="
                        background:none;
                        border:none;
                        color:#ef4444;
                        font-size:12px;
                        cursor:pointer;
                        text-decoration:underline;
                        padding:0;
                    "
                >
                    <i
                        class="fa fa-times-circle"
                        aria-hidden="true"
                    ></i>
                    <span>
                        Cancel Wrong JC
                    </span>
                </button>

            </div>

        </div>
    `;


    /* Wire the void button immediately after innerHTML is set */
    const _voidBtn =
        document.getElementById(
            "oee-void-run-btn-v1"
        );


    if (_voidBtn) {

        _voidBtn.addEventListener(
            "click",
            async function() {

                const runId =
                    _voidBtn.dataset.runId;


                if (!runId) {
                    return;
                }


                _voidBtn.disabled = true;

                _voidBtn.textContent =
                    "Cancelling...";


                try {

                    const resp =
                        await fetch(
                            "/api/oee-machine/run/"
                            + encodeURIComponent(runId)
                            + "/void",
                            {
                                method: "POST",
                                headers: {
                                    "Content-Type":
                                        "application/json"
                                }
                            }
                        );


                    const data =
                        await resp.json();


                    if (
                        !resp.ok
                        || data.success === false
                    ) {

                        throw new Error(
                            data.error
                            || "Unable to cancel entry."
                        );
                    }


                    /* Reset all run state */
                    machineOeePendingRunV1  = null;
                    machineOeeActiveRunV1   = null;
                    machineOeeCurrentFetchedJcV1 = null;


                    /* Re-enable JC search */
                    machineOeeSetSearchEnabledV1(
                        true
                    );


                    /* Clear the JC input */
                    const _inp =
                        document.getElementById(
                            "machine-oee-jc-input"
                        );

                    if (_inp) {
                        _inp.value = "";
                        _inp.focus();
                    }


                    /* Clear result area */
                    const _host =
                        document.getElementById(
                            "machine-oee-jc-result-v1"
                        );

                    if (_host) {
                        _host.innerHTML = "";
                    }


                } catch (err) {

                    _voidBtn.disabled = false;

                    _voidBtn.textContent =
                        "Cancel Wrong JC";


                    if (
                        typeof showToast
                        === "function"
                    ) {

                        showToast(
                            err.message
                            || "Cancel failed.",
                            "error"
                        );

                    } else {

                        alert(
                            err.message
                            || "Cancel failed."
                        );
                    }
                }
            }
        );
    }
}


/* ---------------------------------------------------------
 * START JC
 * --------------------------------------------------------- */

async function machineOeeStartRunV1() {

    const card =
        machineOeeCurrentFetchedJcV1;


    const context =
        window.NMTG_MACHINE_OEE_CONTEXT;


    const shiftSelect =
        document.getElementById(
            "machine-oee-shift-v1"
        );


    const resultHost =
        document.getElementById(
            "machine-oee-jc-result-v1"
        );


    if (
        !card
        ||
        !context
    ) {

        return;
    }


    const shiftName =
        String(
            shiftSelect?.value
            || ""
        ).trim();


    if (!shiftName) {

        alert(
            "Please select Shift first."
        );

        shiftSelect?.focus();

        return;
    }


    /*
     * Shared Zone login must identify
     * the actual person before starting.
     */
    if (
        context.is_zone_login
        &&
        !machineOeeActualOperatorIdV1()
    ) {

        alert(
            "Please enter Operator Code or Operator Name."
        );


        document.getElementById(
            "machine-oee-operator-code-v25"
        )?.focus();


        return;
    }


    sessionStorage.setItem(
        MACHINE_OEE_SHIFT_STORAGE_V1,
        shiftName
    );


    resultHost.innerHTML = `

        <div class="upcoming">

            <strong>
                Starting Job Card...
            </strong>

            <span>
                ${machineOeeEscapeV1(
                    card.job_card_no
                    || ""
                )}
                on
                ${machineOeeEscapeV1(
                    context.machine_no
                    || ""
                )}
            </span>

        </div>
    `;


    try {

        const response =
            await fetch(
                "/api/oee-machine/start-run",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        machine_id:
                            context.machine_id,

                        job_card_no:
                            card.job_card_no,

                        item_name:
                            card.item_name
                            || "",

                        shift_name:
                            shiftName,

                        operator_master_id:
                            machineOeeActualOperatorIdV1()
                    })
                }
            );


        const data =
            (
                typeof machineOeeReadApiResponseV2
                === "function"
            )
            ?
            await machineOeeReadApiResponseV2(
                response,
                "Start Job"
            )
            :
            await response.json();


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || "Unable to start Job Card."
            );
        }


        const startedRun =
            data.run
            || null;


        const startedRunId =
            Number(
                startedRun?.run_id
                || 0
            );


        if (startedRunId <= 0) {

            throw new Error(
                "Start Job returned no persisted Machine Run ID."
            );
        }


        /*
         * MACHINE_OEE_START_PERSISTENCE_GUARD_V37
         *
         * Confirm through the normal pending-run API before
         * exposing RUNNING / Production UI. This makes the
         * browser state follow persisted database state.
         */
        const verifyResponse =
            await fetch(
                "/api/oee-machine/pending/"
                +
                encodeURIComponent(
                    context.machine_id
                ),
                {
                    cache: "no-store"
                }
            );


        const verifyData =
            (
                typeof machineOeeReadApiResponseV2
                === "function"
            )
            ?
            await machineOeeReadApiResponseV2(
                verifyResponse,
                "Start Job persistence check"
            )
            :
            await verifyResponse.json();


        const persistedRun =
            verifyData?.pending_run
            || null;


        if (
            !verifyResponse.ok
            ||
            verifyData?.success === false
            ||
            verifyData?.has_pending_run !== true
            ||
            Number(
                persistedRun?.run_id
                || 0
            ) !== startedRunId
            ||
            String(
                persistedRun?.job_card_no
                || ""
            ).trim()
            !==
            String(
                startedRun?.job_card_no
                || card.job_card_no
                || ""
            ).trim()
        ) {

            throw new Error(
                "Start Job was not confirmed in the database. "
                +
                "Refresh the page before retrying."
            );
        }


        machineOeeCurrentFetchedJcV1 =
            null;


        machineOeePendingRunV1 =
            persistedRun;


        machineOeeRenderRunningRunV1(
            persistedRun
        );


        return persistedRun;


    } catch (error) {

        machineOeeActiveRunV1 =
            null;


        machineOeePendingRunV1 =
            null;


        if (
            typeof showToast
            === "function"
        ) {

            showToast(
                error.message
                || "Unable to start Job Card.",
                "error"
            );
        }


        resultHost.innerHTML = `

            <div class="jc-state-v1 error">

                ${machineOeeEscapeV1(
                    error.message
                    || "Unable to start Job Card."
                )}

            </div>
        `;
    }
}


/* ---------------------------------------------------------
 * CHANGE READY BUTTON INTO REAL START BUTTON
 * --------------------------------------------------------- */

const machineOeeFetchJcBaseStartV1 =
    machineOeeFetchJcV1;


machineOeeFetchJcV1 =
    async function machineOeeFetchJcStartEnhancedV1() {

        await machineOeeFetchJcBaseStartV1();


        const card =
            machineOeeCurrentFetchedJcV1;


        if (!card) {
            return;
        }


        const resultHost =
            document.getElementById(
                "machine-oee-jc-result-v1"
            );


        if (!resultHost) {
            return;
        }


        const oldReadyButton =
            resultHost.querySelector(
                ".jc-ready-btn-v1"
            );


        if (!oldReadyButton) {
            return;
        }


        const context =
            window.NMTG_MACHINE_OEE_CONTEXT;


        oldReadyButton.disabled =
            false;


        oldReadyButton.className =
            "machine-start-btn-v1";


        oldReadyButton.textContent =
            `Start on ${
                context?.machine_no
                || "Machine"
            }`;


        oldReadyButton.onclick =
            machineOeeStartRunV1;
    };


/*
 * Initialise shift.
 */
machineOeeInitShiftV1();


/* MACHINE_OEE_ENSURE_SESSION_V1 */
async function machineOeeEnsureSessionV1() {
    try {
        var ctx = window.NMTG_MACHINE_OEE_CONTEXT || {};
        var machineId = Number(ctx.machine_id || 0);
        var shiftEl = document.getElementById("machine-oee-shift-v1");
        var shiftName = String((shiftEl && shiftEl.value) || "").trim();
        if (machineId <= 0 || !shiftName) { return; }
        await fetch("/api/oee-machine/workspace", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ machine_id: machineId, shift_name: shiftName })
        });
    } catch (_) {}
}

window.machineOeeEnsureSessionV1 = machineOeeEnsureSessionV1;

/* create today session before KPI ticker fires */
window.setTimeout(machineOeeEnsureSessionV1, 500);


/* MACHINE_OEE_START_RUN_V1_END */




/* MACHINE_OEE_PRODUCTION_ENTRY_V1_START */


/* ---------------------------------------------------------
 * SHOW PRODUCTION ENTRY FOR ACTIVE MACHINE RUN
 * --------------------------------------------------------- */

function machineOeeRenderProductionEntryV1(
    run
) {

    const host =
        document.getElementById(
            "machine-oee-jc-result-v1"
        );


    if (
        !host
        ||
        !run
    ) {
        return;
    }


    machineOeeActiveRunV1 =
        run;


    /*
     * MACHINE_OEE_JMS_UI_CONSISTENCY_V33
     *
     * The production element is a hidden source only.
     * Direct Entry V3 moves its controls into the visible
     * styled OEE workspace.
     *
     * If that workspace already owns the live controls,
     * keep those controls and do not create duplicate IDs.
     */
    const operatorActionV33 =
        document.getElementById(
            "machine-oee-smart-action-v1"
        );


    if (operatorActionV33) {

        operatorActionV33.style.display =
            "none";
    }


    const directWorkspaceV33 =
        document.getElementById(
            "machine-oee-direct-entry-v3"
        );


    const liveOkInputV33 =
        document.getElementById(
            "machine-oee-ok-qty-v1"
        );


    if (
        directWorkspaceV33
        &&
        liveOkInputV33
        &&
        directWorkspaceV33.contains(
            liveOkInputV33
        )
    ) {

        return;
    }


    const existing =
        document.getElementById(
            "machine-oee-production-entry-v1"
        );


    if (existing) {
        existing.remove();
    }


    /*
     * SOURCE_INPUTS_ONLY_V6
     *
     * These are the real working controls.
     * Direct Entry V3 moves them into the visible OEE panel.
     *
     * No old Production card is rendered.
     */
    const source =
        document.createElement(
            "div"
        );


    source.id =
        "machine-oee-production-entry-v1";


    source.style.display =
        "none";


    source.innerHTML = `

        <input
            id="machine-oee-ok-qty-v1"
            type="number"
            min="0"
            step="1"
            value="${Number(
                run.ok_qty || 0
            )}"
        >


        <input
            id="machine-oee-rejected-qty-v1"
            type="number"
            min="0"
            step="1"
            value="${Number(
                run.rejected_qty || 0
            )}"
        >


        <input
            id="machine-oee-hold-qty-v1"
            type="number"
            min="0"
            step="1"
            value="${Number(
                run.hold_qty || 0
            )}"
        >


        <input
            id="machine-oee-cycle-min-v1"
            type="number"
            min="0"
            step="1"
            value="${Number(
                run.cycle_minutes || 0
            )}"
        >


        <input
            id="machine-oee-cycle-sec-v1"
            type="number"
            min="0"
            max="59"
            step="1"
            value="${Number(
                run.cycle_seconds || 0
            )}"
        >


        <input
            id="machine-oee-load-min-v1"
            type="number"
            min="0"
            step="1"
            value="${Number(
                run.load_unload_minutes || 0
            )}"
        >


        <input
            id="machine-oee-load-sec-v1"
            type="number"
            min="0"
            max="59"
            step="1"
            value="${Number(
                run.load_unload_seconds || 0
            )}"
        >
    `;


    host.appendChild(
        source
    );
}


/* ---------------------------------------------------------
 * SAVE PRODUCTION
 * --------------------------------------------------------- */

async function machineOeeSaveProductionV1() {

    const run =
        machineOeeActiveRunV1;


    if (
        !run
        ||
        !run.run_id
    ) {
        return;
    }


    function value(id) {

        const element =
            document.getElementById(id);


        return Number(
            element?.value || 0
        );
    }


    const payload = {

        ok_qty:
            value(
                "machine-oee-ok-qty-v1"
            ),

        rejected_qty:
            value(
                "machine-oee-rejected-qty-v1"
            ),

        hold_qty:
            value(
                "machine-oee-hold-qty-v1"
            ),

        cycle_minutes:
            value(
                "machine-oee-cycle-min-v1"
            ),

        cycle_seconds:
            value(
                "machine-oee-cycle-sec-v1"
            ),

        load_unload_minutes:
            value(
                "machine-oee-load-min-v1"
            ),

        load_unload_seconds:
            value(
                "machine-oee-load-sec-v1"
            )
    };


    const feedback =
        document.getElementById(
            "machine-oee-production-feedback-v1"
        );


    if (feedback) {

        feedback.textContent =
            "Saving...";
    }


    try {

        const response =
            await fetch(
                `/api/oee-machine/run/${run.run_id}/production`,
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(
                            payload
                        )
                }
            );


        const data =
            await response.json();


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || "Unable to save production."
            );
        }


        Object.assign(
            machineOeeActiveRunV1,
            payload
        );


        if (feedback) {

            feedback.innerHTML = `

                <i
                    class="fa fa-check-circle"
                    aria-hidden="true"
                ></i>

                Progress saved
            `;
        }


        window.setTimeout(
            function() {

                if (feedback) {
                    feedback.textContent = "";
                }

            },
            1800
        );


    } catch (error) {

        if (feedback) {

            feedback.style.color =
                "#b91c1c";

            feedback.textContent =
                error.message
                || "Save failed.";
        }
    }
}


/* ---------------------------------------------------------
 * ENHANCE NEWLY STARTED RUN
 * --------------------------------------------------------- */

const machineOeeRenderRunningRunBaseProdV1 =
    machineOeeRenderRunningRunV1;


machineOeeRenderRunningRunV1 =
    function machineOeeRenderRunningWithProductionV1(
        run
    ) {

        machineOeeRenderRunningRunBaseProdV1(
            run
        );


        machineOeeRenderProductionEntryV1(
            run
        );
    };


/* ---------------------------------------------------------
 * ENHANCE PAGE-LOAD PENDING RUN
 *
 * Existing pending check already gives us the run.
 * After it completes, render the same Production Entry.
 * --------------------------------------------------------- */

const machineOeeCheckPendingBaseProdV1 =
    machineOeeCheckPendingV1;


machineOeeCheckPendingV1 =
    async function machineOeeCheckPendingProductionV1() {

        await machineOeeCheckPendingBaseProdV1();


        if (
            machineOeePendingRunV1
        ) {

            machineOeeActiveRunV1 =
                machineOeePendingRunV1;


            machineOeeRenderProductionEntryV1(
                machineOeePendingRunV1
            );
        }
    };


/* MACHINE_OEE_PRODUCTION_ENTRY_V1_END */




/* MACHINE_OEE_LOSS_ENTRY_V1_START */

/*
 * LEGACY_LOSS_UI_REMOVED_V6
 *
 * Old dropdown-based:
 *   Loss Reason + Minutes + Add Loss
 *
 * has been removed.
 *
 * Direct Entry V3 owns A1-A27 entry.
 */

let machineOeeLossMasterV1 =
    null;


async function machineOeeLoadLossMasterV1() {

    if (
        machineOeeLossMasterV1
    ) {

        return machineOeeLossMasterV1;
    }


    const response =
        await fetch(
            "/api/oee-machine/loss-master",
            {
                cache: "no-store"
            }
        );


    const data =
        await response.json();


    if (
        !response.ok
        ||
        data.success === false
    ) {

        throw new Error(
            data.error
            || "Unable to load OEE losses."
        );
    }


    machineOeeLossMasterV1 =
        data.losses || [];


    return machineOeeLossMasterV1;
}


/*
 * Compatibility only.
 * No old Loss card is rendered.
 */
async function machineOeeRenderLossEntryV1(
    run
) {

    if (
        run
        &&
        run.run_id
    ) {

        machineOeeActiveRunV1 =
            run;
    }


    const old =
        document.getElementById(
            "machine-oee-loss-entry-v1"
        );


    if (old) {
        old.remove();
    }
}


async function machineOeeRefreshLossListV1() {
    return;
}


async function machineOeeAddLossV1() {
    return;
}


async function machineOeeRemoveLossV1(
    eventId
) {

    /*
     * Legacy compatibility only.
     *
     * Direct Entry V3 saves A1-A27 through its own
     * directSaveLossesV3() implementation.
     */
    return;
}


async function machineOeeDeleteLossV1(
    eventId
) {

    return machineOeeRemoveLossV1(
        eventId
    );
}


/* MACHINE_OEE_LOSS_ENTRY_V1_END */




/* MACHINE_OEE_RESUME_RUNNING_UI_V1_START */


/*
 * When page loads with an already RUNNING machine JC,
 * the earlier pending-check timer shows the pending card.
 *
 * This second-stage resume opens the actual Production Entry
 * and Loss Entry for that same run.
 */
async function machineOeeResumeRunningUiV1() {

    let attempts = 0;


    const timer = window.setInterval(
        function() {

            attempts += 1;


            const run =
                machineOeePendingRunV1;


            if (
                run
                &&
                run.run_id
            ) {

                window.clearInterval(
                    timer
                );


                machineOeeActiveRunV1 =
                    run;


                /*
                 * Existing production renderer is already
                 * enhanced by the Loss Entry module,
                 * so this restores BOTH:
                 *
                 *   Production Entry
                 *   Machine Loss Entry
                 */
                if (
                    typeof machineOeeRenderProductionEntryV1
                    === "function"
                ) {

                    machineOeeRenderProductionEntryV1(
                        run
                    );
                }


                /*
                 * Machine is not READY while a JC is running.
                 */
                const statusElements =
                    document.querySelectorAll(
                        ".status-open"
                    );


                statusElements.forEach(
                    function(element) {

                        element.textContent =
                            String(
                                run.run_status
                                || "RUNNING"
                            ).toUpperCase();

                        element.style.color =
                            "#2563eb";
                    }
                );


                return;
            }


            /*
             * Stop trying after ~3 seconds.
             */
            if (attempts >= 30) {

                window.clearInterval(
                    timer
                );
            }

        },
        100
    );
}


/*
 * Run after all existing page scripts have initialized.
 */
window.setTimeout(
    machineOeeResumeRunningUiV1,
    150
);


/* MACHINE_OEE_RESUME_RUNNING_UI_V1_END */




/* MACHINE_OEE_LIVE_PANEL_V1_START */


function machineOeePctV1(
    value
) {

    const number =
        Number(value);


    if (!Number.isFinite(number)) {
        return "-";
    }


    /*
     * Do not cap percentages.
     * Detailed Excel block does not cap AR/PR/OEE.
     */
    return (
        number * 100
    ).toFixed(2) + "%";
}


function machineOeeNumV1(
    value,
    digits = 2
) {

    const number =
        Number(value);


    if (!Number.isFinite(number)) {
        return "-";
    }


    return number.toFixed(
        digits
    );
}


/* ---------------------------------------------------------
 * LOAD MACHINE SESSION CALCULATION
 * --------------------------------------------------------- */

async function machineOeeRefreshLiveCalcV1() {

    const run =
        machineOeeActiveRunV1
        || machineOeePendingRunV1;


    const host =
        document.getElementById(
            "machine-live-oee-host-v1"
        );


    if (!host) {
        return;
    }


    if (
        !run
        ||
        !run.session_id
    ) {

        host.innerHTML = `

            <section
                class="machine-live-oee-v1"
            >

                <div
                    class="machine-live-head-v1"
                >

                    <strong>
                        Live Machine OEE
                    </strong>

                </div>


                <div
                    class="machine-live-three-v25"
                >

                    <div
                        class="machine-live-kpi-v25"
                    >

                        <span>
                            Plan vs Actual
                        </span>

                        <strong>
                            -
                        </strong>

                    </div>


                    <div
                        class="machine-live-kpi-v25"
                    >

                        <span>
                            PR
                        </span>

                        <strong>
                            -
                        </strong>

                    </div>


                    <div
                        class="
                            machine-live-kpi-v25
                            primary
                        "
                    >

                        <span>
                            OEE
                        </span>

                        <strong>
                            -
                        </strong>

                    </div>

                </div>

            </section>
        `;


        return;
    }


    try {

        const response =
            await fetch(
                "/api/oee-machine/session/"
                +
                encodeURIComponent(
                    run.session_id
                )
                +
                "/live-oee",
                {
                    cache:
                        "no-store"
                }
            );


        const data =
            await response.json();


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                ||
                "Unable to calculate Machine OEE."
            );
        }


        if (
            data.calculation_ready
            === false
        ) {

            throw new Error(
                data.message
                ||
                "Formula profile is not confirmed."
            );
        }


        host.innerHTML = `

            <section
                class="machine-live-oee-v1"
            >

                <div
                    class="machine-live-head-v1"
                >

                    <strong>
                        Live Machine OEE
                    </strong>

                </div>


                <div
                    class="machine-live-three-v25"
                >

                    <div
                        class="machine-live-kpi-v25"
                    >

                        <span>
                            Plan vs Actual
                        </span>

                        <strong>
                            ${machineOeePctV1(
                                data.plan_vs_actual
                            )}
                        </strong>

                    </div>


                    <div
                        class="machine-live-kpi-v25"
                    >

                        <span>
                            PR
                        </span>

                        <strong>
                            ${machineOeePctV1(
                                data.pr_ratio
                            )}
                        </strong>

                    </div>


                    <div
                        class="
                            machine-live-kpi-v25
                            primary
                        "
                    >

                        <span>
                            OEE
                        </span>

                        <strong>
                            ${machineOeePctV1(
                                data.oee_ratio
                            )}
                        </strong>

                    </div>

                </div>

            </section>
        `;


    } catch (error) {

        host.innerHTML = `

            <section
                class="machine-live-oee-v1"
            >

                <div
                    class="machine-live-note-v1"
                >

                    ${machineOeeEscapeV1(
                        error.message
                        ||
                        "Unable to calculate Machine OEE."
                    )}

                </div>

            </section>
        `;
    }
}


/* ---------------------------------------------------------
 * REFRESH AFTER PRODUCTION SAVE
 * --------------------------------------------------------- */

const machineOeeSaveProductionBaseCalcV1 =
    machineOeeSaveProductionV1;


machineOeeSaveProductionV1 =
    async function machineOeeSaveProductionCalcV1() {

        await machineOeeSaveProductionBaseCalcV1();

        await machineOeeRefreshLiveCalcV1();
    };


/* ---------------------------------------------------------
 * REFRESH AFTER LOSS ADD
 * --------------------------------------------------------- */

const machineOeeAddLossBaseCalcV1 =
    machineOeeAddLossV1;


machineOeeAddLossV1 =
    async function machineOeeAddLossCalcV1() {

        await machineOeeAddLossBaseCalcV1();

        await machineOeeRefreshLiveCalcV1();
    };


/* ---------------------------------------------------------
 * REFRESH AFTER LOSS REMOVE
 * --------------------------------------------------------- */

const machineOeeRemoveLossBaseCalcV1 =
    machineOeeRemoveLossV1;


machineOeeRemoveLossV1 =
    async function machineOeeRemoveLossCalcV1(
        eventId
    ) {

        await machineOeeRemoveLossBaseCalcV1(
            eventId
        );

        await machineOeeRefreshLiveCalcV1();
    };


/* ---------------------------------------------------------
 * PAGE LOAD / RUN START
 * --------------------------------------------------------- */

window.setTimeout(
    machineOeeRefreshLiveCalcV1,
    500
);


const machineOeeRenderRunningBaseCalcV1 =
    machineOeeRenderRunningRunV1;


machineOeeRenderRunningRunV1 =
    function machineOeeRenderRunningCalcV1(
        run
    ) {

        machineOeeRenderRunningBaseCalcV1(
            run
        );


        window.setTimeout(
            machineOeeRefreshLiveCalcV1,
            50
        );
    };


/* MACHINE_OEE_LIVE_PANEL_V1_END */




/* OEE_OPERATOR_TEXTBOX_AND_LIVE_KPI_V25 */

/* ACTUAL_OPERATOR_SELECTION_V25_START */

const ACTUAL_OPERATOR_STORAGE_V1 = (function () {
    const _ctx = window.NMTG_MACHINE_OEE_CONTEXT || {};
    const _mid = _ctx.machine_id ? String(_ctx.machine_id) : "0";
    return "jms_oee_actual_operator_v1_m" + _mid;
}());


let machineOeeActualOperatorV1 =
    null;


let machineOeeOperatorMasterV25 =
    [];


/* ---------------------------------------------------------
 * ACTUAL OPERATOR MASTER ID
 * --------------------------------------------------------- */

function machineOeeActualOperatorIdV1() {

    const context =
        window.NMTG_MACHINE_OEE_CONTEXT;


    if (
        !context
        ||
        !context.is_zone_login
    ) {

        return null;
    }


    return (
        machineOeeActualOperatorV1?.id
        || null
    );
}


function machineOeeActualOperatorEmployeeNoV25() {

    return String(
        machineOeeActualOperatorV1
            ?.employee_no
        || ""
    ).trim();
}


function machineOeeNormalizeOperatorNameV25(
    value
) {

    return String(
        value
        || ""
    )
    .trim()
    .replace(
        /\s+/g,
        " "
    )
    .toLowerCase();
}


function machineOeeSaveActualOperatorV25(
    operator
) {

    machineOeeActualOperatorV1 =
        operator
        || null;


    if (operator) {

        sessionStorage.setItem(
            ACTUAL_OPERATOR_STORAGE_V1,
            JSON.stringify(
                operator
            )
        );

    } else {

        sessionStorage.removeItem(
            ACTUAL_OPERATOR_STORAGE_V1
        );
    }
}


function machineOeeFillOperatorFieldsV25(
    operator
) {

    const codeInput =
        document.getElementById(
            "machine-oee-operator-code-v25"
        );


    const nameInput =
        document.getElementById(
            "machine-oee-operator-name-v25"
        );


    if (codeInput) {

        codeInput.value =
            operator?.employee_no
            || "";
    }


    if (nameInput) {

        nameInput.value =
            operator?.operator_name
            || "";
    }


    machineOeeSaveActualOperatorV25(
        operator
    );
}


/* ---------------------------------------------------------
 * CODE -> NAME
 * --------------------------------------------------------- */

function machineOeeResolveCodeV25() {

    const codeInput =
        document.getElementById(
            "machine-oee-operator-code-v25"
        );


    const nameInput =
        document.getElementById(
            "machine-oee-operator-name-v25"
        );


    const code =
        String(
            codeInput?.value
            || ""
        ).trim();


    if (!code) {

        if (nameInput) {
            nameInput.value = "";
        }


        machineOeeSaveActualOperatorV25(
            null
        );

        return;
    }


    const operator =
        machineOeeOperatorMasterV25.find(
            function(row) {

                return (
                    String(
                        row.employee_no
                        || ""
                    ).trim()
                    === code
                );
            }
        );


    if (operator) {

        machineOeeFillOperatorFieldsV25(
            operator
        );

        return;
    }


    if (nameInput) {

        nameInput.value =
            "";
    }


    machineOeeSaveActualOperatorV25(
        null
    );
}


/* ---------------------------------------------------------
 * NAME -> CODE
 * --------------------------------------------------------- */

function machineOeeResolveNameV25() {

    const codeInput =
        document.getElementById(
            "machine-oee-operator-code-v25"
        );


    const nameInput =
        document.getElementById(
            "machine-oee-operator-name-v25"
        );


    const name =
        machineOeeNormalizeOperatorNameV25(
            nameInput?.value
        );


    if (!name) {

        if (codeInput) {
            codeInput.value = "";
        }


        machineOeeSaveActualOperatorV25(
            null
        );

        return;
    }


    const operator =
        machineOeeOperatorMasterV25.find(
            function(row) {

                return (
                    machineOeeNormalizeOperatorNameV25(
                        row.operator_name
                    )
                    === name
                );
            }
        );


    if (operator) {

        machineOeeFillOperatorFieldsV25(
            operator
        );

        return;
    }


    if (codeInput) {

        codeInput.value =
            "";
    }


    machineOeeSaveActualOperatorV25(
        null
    );
}


/* ---------------------------------------------------------
 * INITIALIZE OPERATOR INPUTS
 * --------------------------------------------------------- */

async function machineOeeInitActualOperatorV1() {

    const context =
        window.NMTG_MACHINE_OEE_CONTEXT;


    const host =
        document.getElementById(
            "machine-oee-actual-operator-host-v1"
        );


    if (
        !host
        ||
        !context?.is_zone_login
    ) {

        if (host) {

            host.style.display =
                "none";
        }


        return;
    }


    host.innerHTML = `

        <div
            class="actual-operator-box-v1"
        >

            <div
                class="actual-operator-fields-v25"
            >

                <div
                    class="actual-operator-field-v25"
                >

                    <label>
                        Operator Code
                    </label>

                    <input
                        id="machine-oee-operator-code-v25"

                        type="text"

                        inputmode="numeric"

                        autocomplete="off"

                        placeholder="Employee No."
                    >

                </div>


                <div
                    class="actual-operator-field-v25"
                >

                    <label>
                        Operator Name
                    </label>

                    <input
                        id="machine-oee-operator-name-v25"

                        type="text"

                        autocomplete="off"

                        list="machine-oee-operator-name-list-v25"

                        placeholder="Operator Name"
                    >


                    <datalist
                        id="machine-oee-operator-name-list-v25"
                    ></datalist>

                </div>


                <div
                    class="oee-zone-supervisor-line-v100"
                    id="machine-oee-zone-supervisor-v98"
                >

                    <span
                        class="oee-zone-supervisor-label-v100"
                    >
                        Zone Supervisor
                    </span>

                    <span
                        class="oee-zone-supervisor-value-v100"
                    >
                        ${machineOeeEscapeV1(
                            context?.zone_supervisor_name
                            || "-"
                        )}
                    </span>

                </div>

            </div>

        </div>
    `;


    try {

        const response =
            await fetch(
                "/api/oee-machine/operator-master",
                {
                    cache:
                        "no-store"
                }
            );


        const data =
            await response.json();


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                ||
                "Unable to load Operator Master."
            );
        }


        machineOeeOperatorMasterV25 =
            Array.isArray(
                data.operators
            )
            ?
            data.operators
            :
            [];


        const datalist =
            document.getElementById(
                "machine-oee-operator-name-list-v25"
            );


        if (datalist) {

            datalist.innerHTML =
                "";


            for (
                const operator
                of machineOeeOperatorMasterV25
            ) {

                const option =
                    document.createElement(
                        "option"
                    );


                option.value =
                    operator.operator_name
                    || "";


                option.label =
                    String(
                        operator.employee_no
                        || ""
                    );


                datalist.appendChild(
                    option
                );
            }
        }


        const codeInput =
            document.getElementById(
                "machine-oee-operator-code-v25"
            );


        const nameInput =
            document.getElementById(
                "machine-oee-operator-name-v25"
            );


        codeInput?.addEventListener(
            "input",
            machineOeeResolveCodeV25
        );


        codeInput?.addEventListener(
            "change",
            machineOeeResolveCodeV25
        );


        nameInput?.addEventListener(
            "input",
            machineOeeResolveNameV25
        );


        nameInput?.addEventListener(
            "change",
            machineOeeResolveNameV25
        );


        let saved =
            null;


        try {

            saved =
                JSON.parse(
                    sessionStorage.getItem(
                        ACTUAL_OPERATOR_STORAGE_V1
                    )
                    || "null"
                );

        } catch (_) {

            saved =
                null;
        }


        if (saved?.id) {

            const valid =
                machineOeeOperatorMasterV25.find(
                    function(row) {

                        return (
                            Number(row.id)
                            === Number(
                                saved.id
                            )
                        );
                    }
                );


            if (valid) {

                machineOeeFillOperatorFieldsV25(
                    valid
                );
            }
        }


    } catch (error) {

        host.innerHTML = `

            <div
                class="machine-page-error-v1"
            >

                ${machineOeeEscapeV1(
                    error.message
                    ||
                    "Unable to load Operator Master."
                )}

            </div>
        `;
    }
}


window.setTimeout(
    machineOeeInitActualOperatorV1,
    100
);


/* ACTUAL_OPERATOR_SELECTION_V25_END */




/* MACHINE_OEE_OPERATION_COMPLETE_V1_START */


/* ---------------------------------------------------------
 * READ FINAL PRODUCTION VALUES
 * --------------------------------------------------------- */

function machineOeeFinalProductionV1() {

    function read(id) {

        const element =
            document.getElementById(id);


        const value =
            Number(
                element?.value
                || 0
            );


        return Number.isFinite(value)
            ? value
            : 0;
    }


    const currentRun =
        machineOeeActiveRunV1
        || machineOeePendingRunV1
        || {};


    return {

        oee_start_time:
            String(
                document.getElementById(
                    "oee-direct-start-time-v3"
                )?.value
                || currentRun.oee_start_time
                || ""
            ).trim(),

        oee_end_time:
            String(
                document.getElementById(
                    "oee-direct-stop-time-v3"
                )?.value
                || currentRun.oee_end_time
                || ""
            ).trim(),

        ok_qty:
            read(
                "machine-oee-ok-qty-v1"
            ),

        rejected_qty:
            read(
                "machine-oee-rejected-qty-v1"
            ),

        hold_qty:
            read(
                "machine-oee-hold-qty-v1"
            ),

        cycle_minutes:
            read(
                "machine-oee-cycle-min-v1"
            ),

        cycle_seconds:
            read(
                "machine-oee-cycle-sec-v1"
            ),

        load_unload_minutes:
            read(
                "machine-oee-load-min-v1"
            ),

        load_unload_seconds:
            read(
                "machine-oee-load-sec-v1"
            )
    };
}


/* ---------------------------------------------------------
 * RENDER COMPLETE ACTION
 * --------------------------------------------------------- */

function machineOeeRenderCompleteActionV1(
    run
) {

    /*
     * LEGACY_COMPLETE_CARD_REMOVED_V6
     *
     * Direct Entry V3 owns the completion controls.
     * Core machineOeeCompleteOperationV1() remains unchanged.
     */
    return;
}


/* ---------------------------------------------------------
 * FETCH CURRENT JC CONTEXT
 * --------------------------------------------------------- */

async function machineOeeCompletionContextV1(
    run
) {

    const context =
        window.NMTG_MACHINE_OEE_CONTEXT;


    const response =
        await fetch(
            "/api/oee-machine/jc-context/"
            +
            encodeURIComponent(
                context.machine_id
            )
            +
            "/"
            +
            encodeURIComponent(
                run.job_card_no
            ),
            {
                cache:"no-store"
            }
        );


    const data =
        await machineOeeReadApiResponseV2(
            response,
            "Job Card completion validation"
        );


    if (
        !response.ok
        ||
        data.success === false
    ) {

        throw new Error(
            data.error
            || "Unable to validate Job Card."
        );
    }


    if (
        String(
            data.status
            || ""
        ).toUpperCase()
        !== "READY"
        ||
        !data.card
    ) {

        throw new Error(
            data.message
            || "Job Card is no longer ready "
               + "for this machine operation."
        );
    }


    return data.card;
}


/* ---------------------------------------------------------
 * COMPLETE
 * --------------------------------------------------------- */

async function machineOeeCompleteOperationV1() {

    const run =
        machineOeeActiveRunV1
        || machineOeePendingRunV1;


    const context =
        window.NMTG_MACHINE_OEE_CONTEXT;


    const button =
        document.getElementById(
            "machine-oee-complete-btn-v1"
        );


    const feedback =
        document.getElementById(
            "machine-oee-complete-feedback-v1"
        );


    if (
        !run
        ||
        !run.run_id
        ||
        !context
    ) {
        return;
    }


    const production =
        machineOeeFinalProductionV1();


    /*
     * OEE_CORE_REASON_RUN_STORAGE_V50
     *
     * Reason is stored against the current machine run.
     * Dynamic UI rebuilds cannot lose the operator choice.
     */
    const rejectionReason =
        machineOeeCoreReasonValueV50(
            "rejection",
            run
        );


    const holdReason =
        machineOeeCoreReasonValueV50(
            "hold",
            run
        );


    if (
        production.rejected_qty > 0
        &&
        !rejectionReason
    ) {

        feedback.style.color =
            "#b91c1c";


        feedback.textContent =
            "Select Rejection Reason.";


        document.getElementById(
            "machine-oee-rejection-reason-v1"
        )?.focus();


        return;
    }


    if (
        production.hold_qty > 0
        &&
        !holdReason
    ) {

        feedback.style.color =
            "#b91c1c";


        feedback.textContent =
            "Select Hold Reason.";


        document.getElementById(
            "machine-oee-hold-reason-v9"
        )?.focus();


        return;
    }


    /* OEE_CORE_REMOVE_HOLD_ZERO_BLOCK_V51 */

    /*
     * Zone login = authentication.
     * Actual Operator = human traceability name.
     */
    const actualOperator =
        machineOeeActualOperatorV1;


    if (
        context.is_zone_login
        &&
        !actualOperator?.id
    ) {

        feedback.style.color =
            "#b91c1c";


        feedback.textContent =
            "Enter Operator Code or Operator Name.";


        return;
    }


    const changedBy =
        actualOperator?.display_name
        || actualOperator?.full_name
        || actualOperator?.username
        || run.operator_name
        || "Operator";


    const completeRemark =
        String(
            document.getElementById(
                "machine-oee-complete-remark-v1"
            )?.value
            || ""
        ).trim();


    button.disabled = true;


    feedback.style.color =
        "#64748b";


    feedback.textContent =
        "Completing operation...";


    try {

        /*
         * 1. Save latest Production Entry first.
         */
        const productionResponse =
            await fetch(
                `/api/oee-machine/run/${run.run_id}/production`,
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify(
                        production
                    )
                }
            );


        const productionData =
            await machineOeeReadApiResponseV2(
                productionResponse,
                "Final production save"
            );


        if (
            !productionResponse.ok
            ||
            productionData.success === false
        ) {

            throw new Error(
                productionData.error
                || "Unable to save final production."
            );
        }


        /*
         * Save the current run's A1-A27 before WIP movement.
         *
         * If this save fails, completion stops here.
         */
        if (
            typeof window
                .machineOeeSaveCurrentRunLossesCoreV44
            !== "function"
        ) {

            throw new Error(
                "Current run loss save is not available."
            );
        }


        await window
            .machineOeeSaveCurrentRunLossesCoreV44();


        if (
            typeof window.machineOeeSaveToolRowsV5
            === "function"
        ) {

            await window.machineOeeSaveToolRowsV5({
                run_id:
                    Number(
                        run.run_id
                        || 0
                    )
            });
        }


        /*
         * 2. Get Traceability's real next process.
         */
        const card =
            await machineOeeCompletionContextV1(
                run
            );


        const nextProcess =
            String(
                card.next_process
                || "Store"
            ).trim();


        /*
         * 3. Use EXISTING Traceability engine.
         *
         * machine_oee_completion tells backend:
         * - don't create old JC-wise OEE
         * - close the machine run in SAME transaction
         */
        const response =
            await fetch(
                "/api/wip/update",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:JSON.stringify({

                        job_card_no:
                            run.job_card_no,

                        item_name:
                            card.item_name,

                        new_stage:
                            nextProcess,

                        changed_by:
                            changedBy,

                        actual_qty:
                            production.ok_qty,

                        ok_qty:
                            production.ok_qty,

                        rejected_qty:
                            production.rejected_qty,

                        hold_qty:
                            production.hold_qty,

                        rejection_reason:
                            rejectionReason,

                        hold_reason:
                            holdReason,

                        rework_qty:
                            0,

                        rework_remarks:
                            "",

                        stage_remark:
                            completeRemark
                            ||
                            (
                                "Completed from Machine OEE - "
                                +
                                context.machine_no
                            ),

                        machine_oee_completion:
                            true,

                        machine_run_id:
                            run.run_id
                    })
                }
            );


        const data =
            await machineOeeReadApiResponseV2(
                response,
                "Complete Job / Operation"
            );


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || data.message
                || "Operation completion failed."
            );
        }


        machineOeeActiveRunV1 =
            null;


        machineOeePendingRunV1 =
            null;


        feedback.style.color =
            "#15803d";


        feedback.innerHTML = `

            <i
                class="fa fa-check-circle"
                aria-hidden="true"
            ></i>

            Completed. Moved to
            ${machineOeeEscapeV1(
                data.new_stage
                || nextProcess
            )}.
        `;


        /*
         * Refresh Machine OEE once so the
         * COMPLETED run is included.
         */
        try {

            await machineOeeRefreshLiveCalcV1();

        } catch (_) {
            // Non-blocking display refresh only.
        }


        /*
         * MACHINE_OEE_STAY_AFTER_COMPLETE_V12
         *
         * Keep operator on the SAME selected machine
         * after completing the current Job Card.
         *
         * Reloading the current machine page gives us
         * a clean state from the backend:
         *
         * - completed run disappears
         * - Job Card input becomes available again
         * - same machine remains selected
         * - Actual Operator remains remembered
         * - Shift remains remembered
         */
        window.setTimeout(
            function() {

                window.location.reload();

            },
            900
        );


    } catch (error) {

        button.disabled =
            false;


        feedback.style.color =
            "#b91c1c";


        feedback.textContent =
            error.message
            || "Operation completion failed.";
    }
}


/* ---------------------------------------------------------
 * SHOW COMPLETE ACTION AFTER LOSS ENTRY
 * --------------------------------------------------------- */

const machineOeeRenderLossBaseCompleteV1 =
    machineOeeRenderLossEntryV1;


machineOeeRenderLossEntryV1 =
    async function machineOeeRenderLossCompleteV1(
        run
    ) {

        await machineOeeRenderLossBaseCompleteV1(
            run
        );


        machineOeeRenderCompleteActionV1(
            run
        );
    };


/* MACHINE_OEE_OPERATION_COMPLETE_V1_END */




/* MACHINE_OEE_SAFE_JSON_V2_START */


/*
 * Never use response.json() blindly.
 *
 * If Flask/Waitress sends HTML because of a 404/500/redirect,
 * show a useful message instead of:
 *
 * Unexpected token '<'
 */
async function machineOeeReadApiResponseV2(
    response,
    operationName
) {

    const contentType =
        String(
            response.headers.get(
                "content-type"
            )
            || ""
        ).toLowerCase();


    if (
        contentType.includes(
            "application/json"
        )
    ) {

        return await response.json();
    }


    const rawText =
        await response.text();


    const plainText =
        String(
            rawText
            || ""
        )
        .replace(
            /<script[\s\S]*?<\/script>/gi,
            " "
        )
        .replace(
            /<style[\s\S]*?<\/style>/gi,
            " "
        )
        .replace(
            /<[^>]+>/g,
            " "
        )
        .replace(
            /\s+/g,
            " "
        )
        .trim();


    const details =
        plainText
            ? plainText.slice(0, 350)
            : "Server returned a non-JSON response.";


    throw new Error(
        `${operationName} failed `
        +
        `(HTTP ${response.status}). `
        +
        details
    );
}


/* MACHINE_OEE_SAFE_JSON_V2_END */




/* MACHINE_OEE_RUN_COMPLETION_CONTEXT_V2_START */


/*
 * Completion context now comes directly from run_id.
 *
 * We no longer call:
 * /api/oee-machine/jc-context/<machine>/<jc>
 *
 * That lookup is useful while scanning a NEW JC,
 * but unnecessary once a Machine Run already exists.
 */
machineOeeCompletionContextV1 =
    async function machineOeeCompletionContextRunV2(
        run
    ) {

        if (
            !run
            ||
            !run.run_id
        ) {

            throw new Error(
                "Valid Machine Run is required."
            );
        }


        const response =
            await fetch(
                `/api/oee-machine/run/${run.run_id}/completion-context`,
                {
                    cache:"no-store"
                }
            );


        const data =
            await machineOeeReadApiResponseV2(
                response,
                "Job Card completion validation"
            );


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || "Unable to validate Job Card completion."
            );
        }


        if (!data.card) {

            throw new Error(
                "Completion Job Card context was not returned."
            );
        }


        return data.card;
    };


/* MACHINE_OEE_RUN_COMPLETION_CONTEXT_V2_END */




/* MACHINE_OEE_READY_BUTTON_FIX_V3 */

let machineOeeReadyStartLockV3 = false;


/*
 * The FAST JC renderer currently displays
 * "Ready to Start" as a visual status control.
 *
 * Make the rendered control an actual start action.
 */
function machineOeeWireReadyStartV3() {

    const elements =
        Array.from(
            document.querySelectorAll(
                "button, div, span"
            )
        );


    for (const element of elements) {

        /*
         * Use only the smallest element containing
         * the Ready-to-Start text.
         */
        const directText =
            Array.from(
                element.childNodes
            )
            .filter(
                node =>
                    node.nodeType ===
                    Node.TEXT_NODE
            )
            .map(
                node =>
                    String(
                        node.textContent
                        || ""
                    )
            )
            .join(" ")
            .replace(/\s+/g, " ")
            .trim();


        const fullText =
            String(
                element.textContent
                || ""
            )
            .replace(/\s+/g, " ")
            .trim();


        const text =
            directText
            || fullText;


        if (
            !/Ready to Start$/i.test(text)
        ) {
            continue;
        }


        /*
         * Avoid selecting a large parent container.
         */
        const childHasReadyText =
            Array.from(
                element.children
            ).some(
                child =>
                    /Ready to Start$/i.test(
                        String(
                            child.textContent
                            || ""
                        )
                        .replace(/\s+/g, " ")
                        .trim()
                    )
            );


        if (childHasReadyText) {
            continue;
        }


        element.dataset.machineOeeReadyStartV3 =
            "1";


        /*
         * In case it was rendered disabled.
         */
        element.removeAttribute(
            "disabled"
        );


        element.style.pointerEvents =
            "auto";


        element.style.cursor =
            "pointer";


        element.style.userSelect =
            "none";


        element.setAttribute(
            "role",
            "button"
        );


        if (
            !element.hasAttribute(
                "tabindex"
            )
        ) {

            element.tabIndex = 0;
        }
    }
}


/*
 * Use capture mode so only ONE Start request is made,
 * even if an old handler exists on the status element.
 */
document.addEventListener(
    "click",

    async function(event) {

        const target =
            event.target.closest(
                '[data-machine-oee-ready-start-v3="1"]'
            );


        if (!target) {
            return;
        }


        event.preventDefault();
        event.stopImmediatePropagation();


        if (
            machineOeeReadyStartLockV3
        ) {
            return;
        }


        if (
            typeof machineOeeStartRunV1
            !== "function"
        ) {

            alert(
                "Start Run function is not available."
            );

            return;
        }


        machineOeeReadyStartLockV3 =
            true;


        try {

            await machineOeeStartRunV1();

        } finally {

            window.setTimeout(
                function() {

                    machineOeeReadyStartLockV3 =
                        false;

                },
                1000
            );
        }
    },

    true
);


/*
 * Keyboard support.
 */
document.addEventListener(
    "keydown",

    function(event) {

        const target =
            event.target.closest(
                '[data-machine-oee-ready-start-v3="1"]'
            );


        if (!target) {
            return;
        }


        if (
            event.key !== "Enter"
            &&
            event.key !== " "
        ) {
            return;
        }


        event.preventDefault();

        target.click();
    }
);


/*
 * JC result is rendered dynamically after Fetch,
 * therefore watch for newly-rendered Ready controls.
 */
const machineOeeReadyObserverV3 =
    new MutationObserver(
        function() {

            machineOeeWireReadyStartV3();

        }
    );


machineOeeReadyObserverV3.observe(
    document.body,
    {
        childList: true,
        subtree: true
    }
);


window.setTimeout(
    machineOeeWireReadyStartV3,
    100
);




/* OEE_CORE_FLOW_CLEANUP_V1 - DUPLICATE_SMART_ACTION_REMOVED */

/* ==========================================================
   MACHINE_OEE_JOBCARD_NATIVE_V1
   ========================================================== */

(function () {

    let jobCardUiTimerV1 =
        null;


    /* ------------------------------------------------------
       NORMALIZE TEXT
       ------------------------------------------------------ */

    function jcNativeTextV1(
        value
    ) {

        return String(
            value || ""
        )
        .replace(/\s+/g, " ")
        .trim();
    }


    /* ------------------------------------------------------
       FIND JOB CARD INPUT
       ------------------------------------------------------ */

    function jcNativeInputV1() {

        const inputs =
            Array.from(
                document.querySelectorAll(
                    'input[type="text"], input:not([type])'
                )
            );


        return (
            inputs.find(
                function (input) {

                    const id =
                        jcNativeTextV1(
                            input.id
                        ).toLowerCase();


                    const placeholder =
                        jcNativeTextV1(
                            input.placeholder
                        ).toLowerCase();


                    return (
                        (
                            id.includes("job")
                            &&
                            id.includes("card")
                        )
                        ||
                        (
                            id.includes("jc")
                            &&
                            !id.includes("actual")
                        )
                        ||
                        placeholder.includes(
                            "job card"
                        )
                    );
                }
            )
            || null
        );
    }


    /* ------------------------------------------------------
       FIND JOB CARD CARD
       ------------------------------------------------------ */

    function jcNativeCardV1() {

        const input =
            jcNativeInputV1();


        if (!input) {
            return null;
        }


        let node =
            input;


        while (
            node
            &&
            node !== document.body
        ) {

            const value =
                jcNativeTextV1(
                    node.textContent
                ).toLowerCase();


            if (
                value.includes(
                    "job card"
                )
                &&
                (
                    node.tagName === "SECTION"
                    ||
                    node.classList.contains(
                        "card"
                    )
                    ||
                    node.classList.contains(
                        "machine-card-v1"
                    )
                    ||
                    node.classList.contains(
                        "machine-page-card-v1"
                    )
                )
            ) {

                return node;
            }


            node =
                node.parentElement;
        }


        return (
            input.closest(
                "section"
            )
            ||
            input.parentElement
        );
    }


    /* ------------------------------------------------------
       FIND FETCH BUTTON
       ------------------------------------------------------ */

    function jcNativeFetchButtonV1() {

        const card =
            jcNativeCardV1();


        if (!card) {
            return null;
        }


        return (
            Array.from(
                card.querySelectorAll(
                    "button"
                )
            )
            .find(
                function (button) {

                    const value =
                        jcNativeTextV1(
                            button.textContent
                        ).toLowerCase();


                    return (
                        value === "fetch"
                        ||
                        value.includes(
                            "fetch job"
                        )
                        ||
                        value.includes(
                            "check job"
                        )
                    );
                }
            )
            || null
        );
    }


    /* ------------------------------------------------------
       SECTION HEADER
       ------------------------------------------------------ */

    function jcNativeSectionHeaderV1(
        card
    ) {

        if (
            !card
            ||
            card.querySelector(
                ".machine-oee-jc-section-head-v1"
            )
        ) {

            return;
        }


        const header =
            document.createElement(
                "div"
            );


        header.className =
            "machine-oee-jc-section-head-v1";


        header.innerHTML = `

            <span
                class="machine-oee-jc-section-icon-v1"
                aria-hidden="true"
            >
                <i class="fa fa-barcode"></i>
            </span>


            <span
                class="machine-oee-jc-section-title-v1"
            >

                <strong>
                    Job Card
                </strong>
            </span>
        `;


        card.insertBefore(
            header,
            card.firstChild
        );
    }


    /* ------------------------------------------------------
       FETCH BUTTON ICON
       ------------------------------------------------------ */

    function jcNativeDecorateFetchV1() {

        const button =
            jcNativeFetchButtonV1();


        if (
            !button
            ||
            button.dataset
                .machineOeeFetchFaV1
            === "1"
        ) {

            return;
        }


        button.dataset
            .machineOeeFetchFaV1 =
            "1";


        button.classList.add(
            "machine-oee-jc-fetch-v1"
        );


        button.innerHTML = `

            <i
                class="fa fa-search"
                aria-hidden="true"
            ></i>

            <span>
                Fetch
            </span>
        `;
    }


    /* ------------------------------------------------------
       FIELD ICON MAP
       ------------------------------------------------------ */

    function jcNativeIconClassV1(
        label
    ) {

        const value =
            jcNativeTextV1(
                label
            ).toLowerCase();


        if (
            value === "job card"
            ||
            value.includes(
                "job card"
            )
        ) {

            return "fa-id-card";
        }


        if (
            value === "item"
            ||
            value.includes(
                "part"
            )
        ) {

            return "fa-cube";
        }


        if (
            value.includes(
                "current process"
            )
        ) {

            return "fa-cogs";
        }


        if (
            value.includes(
                "next process"
            )
        ) {

            return "fa-level-up";
        }


        if (
            value.includes(
                "available qty"
            )
            ||
            value.includes(
                "quantity"
            )
        ) {

            return "fa-cubes";
        }


        if (
            value.includes(
                "selected machine"
            )
            ||
            value === "machine"
        ) {

            return "fa-microchip";
        }


        return "fa-info-circle";
    }


    /* ------------------------------------------------------
       FIND FETCHED RESULT
       ------------------------------------------------------ */

    function jcNativeResultPanelV1(
        card
    ) {

        if (!card) {
            return null;
        }


        const candidates =
            Array.from(
                card.querySelectorAll(
                    "div, section"
                )
            )
            .filter(
                function (node) {

                    const value =
                        jcNativeTextV1(
                            node.textContent
                        ).toLowerCase();


                    return (
                        value.includes(
                            "current process"
                        )
                        &&
                        (
                            value.includes(
                                "available qty"
                            )
                            ||
                            value.includes(
                                "selected machine"
                            )
                        )
                    );
                }
            );


        if (!candidates.length) {
            return null;
        }


        /*
         * Use the smallest matching container.
         */
        candidates.sort(
            function (a, b) {

                return (
                    jcNativeTextV1(
                        a.textContent
                    ).length
                    -
                    jcNativeTextV1(
                        b.textContent
                    ).length
                );
            }
        );


        return candidates[0];
    }


    /* ------------------------------------------------------
       DECORATE FETCHED INFO
       ------------------------------------------------------ */

    function jcNativeDecorateResultV1() {

        const card =
            jcNativeCardV1();


        if (!card) {
            return;
        }


        const result =
            jcNativeResultPanelV1(
                card
            );


        if (!result) {
            return;
        }


        result.classList.add(
            "machine-oee-jc-result-v1"
        );


        const labels =
            Array.from(
                result.querySelectorAll(
                    "label, small, span, div"
                )
            )
            .filter(
                function (node) {

                    const value =
                        jcNativeTextV1(
                            node.textContent
                        ).toLowerCase();


                    return [
                        "job card",
                        "item",
                        "current process",
                        "next process",
                        "available qty",
                        "selected machine"
                    ].includes(
                        value
                    );
                }
            );


        for (const label of labels) {

            const labelText =
                jcNativeTextV1(
                    label.textContent
                );


            let box =
                label.parentElement;


            if (
                !box
                ||
                box === result
            ) {

                continue;
            }


            box.dataset
                .machineOeeJcInfoV1 =
                "1";


            if (
                labelText.toLowerCase()
                    === "job card"
                ||
                labelText.toLowerCase()
                    === "current process"
            ) {

                box.classList.add(
                    "machine-oee-jc-info-primary-v1"
                );
            }


            if (
                label.dataset
                    .machineOeeLabelFaV1
                === "1"
            ) {

                continue;
            }


            label.dataset
                .machineOeeLabelFaV1 =
                "1";


            label.classList.add(
                "machine-oee-jc-info-label-v1"
            );


            const icon =
                jcNativeIconClassV1(
                    labelText
                );


            label.insertAdjacentHTML(
                "afterbegin",
                `

                <i
                    class="fa ${icon}"
                    aria-hidden="true"
                ></i>

                `
            );
        }
    }


    /* ------------------------------------------------------
       READY BUTTON
       REMOVE DAMAGED SYMBOLS
       USE FONT AWESOME PLAY ICON
       ------------------------------------------------------ */

    function jcNativeReadyButtonV1() {

        const candidates =
            Array.from(
                document.querySelectorAll(
                    "button, [role='button'], div, span"
                )
            );


        for (const element of candidates) {

            const value =
                jcNativeTextV1(
                    element.textContent
                );


            if (
                !/ready to start$/i.test(
                    value
                )
            ) {

                continue;
            }


            const childHasSame =
                Array.from(
                    element.children
                )
                .some(
                    function (child) {

                        return /ready to start$/i.test(
                            jcNativeTextV1(
                                child.textContent
                            )
                        );
                    }
                );


            if (childHasSame) {
                continue;
            }


            if (
                element.dataset
                    .machineOeeReadyFaV1
                === "1"
            ) {

                continue;
            }


            element.dataset
                .machineOeeReadyFaV1 =
                "1";


            element.classList.add(
                "machine-oee-ready-fa-v1"
            );


            element.innerHTML = `

                <i
                    class="fa fa-play-circle"
                    aria-hidden="true"
                ></i>

                <span>
                    Ready to Start
                </span>
            `;
        }
    }


    /* ------------------------------------------------------
       SMART ACTION BUTTON ICON
       ------------------------------------------------------ */

    function jcNativeSmartActionV1() {

        const button =
            document.getElementById(
                "machine-oee-smart-action-btn-v1"
            );


        if (!button) {
            return;
        }


        const value =
            jcNativeTextV1(
                button.textContent
            ).toLowerCase();


        let icon =
            "fa-search";


        if (
            value.includes(
                "receive"
            )
        ) {

            icon =
                "fa-download";
        }


        else if (
            value.includes(
                "start"
            )
        ) {

            icon =
                "fa-play";
        }


        else if (
            value.includes(
                "not ready"
            )
            ||
            value.includes(
                "blocked"
            )
        ) {

            icon =
                "fa-lock";
        }


        const currentIcon =
            button.querySelector(
                "i"
            );


        if (
            currentIcon
            &&
            currentIcon.classList.contains(
                icon
            )
        ) {

            return;
        }


        const label =
            jcNativeTextV1(
                button.textContent
            );


        button.innerHTML = `

            <i
                class="fa ${icon}"
                aria-hidden="true"
            ></i>

            <span>
                ${label}
            </span>
        `;
    }


    /* ------------------------------------------------------
       INIT
       ------------------------------------------------------ */

    function jcNativeInitV1() {

        const card =
            jcNativeCardV1();


        const input =
            jcNativeInputV1();


        if (
            !card
            ||
            !input
        ) {

            return;
        }


        card.classList.add(
            "machine-oee-jc-native-v1"
        );


        input.dataset
            .machineOeeJcInputV1 =
            "1";


        jcNativeSectionHeaderV1(
            card
        );


        jcNativeDecorateFetchV1();

        jcNativeDecorateResultV1();

        jcNativeReadyButtonV1();

        jcNativeSmartActionV1();
    }


    /* ------------------------------------------------------
       DYNAMIC OBSERVER
       ------------------------------------------------------ */

    const observer =
        new MutationObserver(
            function () {

                window.clearTimeout(
                    jobCardUiTimerV1
                );


                jobCardUiTimerV1 =
                    window.setTimeout(
                        jcNativeInitV1,
                        80
                    );
            }
        );


    observer.observe(
        document.body,
        {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: [
                "class",
                "disabled"
            ]
        }
    );


    window.setTimeout(
        jcNativeInitV1,
        100
    );


    window.setTimeout(
        jcNativeInitV1,
        500
    );

})();


/* ==========================================================
   MACHINE_OEE_JOBCARD_NATIVE_V1_END
   ========================================================== */














/* ==========================================================
   MACHINE_OEE_DIRECT_ENTRY_V3
   ========================================================== */

(function () {

    let directTimerV3 =
        null;


    let directLossMasterV3 =
        [];


    let directLossRowsV3 =
        [];


    let directLossLoadedRunV3 =
        0;


    let directBusyV3 =
        false;


    /* ------------------------------------------------------
       HELPERS
       ------------------------------------------------------ */

    function directNumberV3(value) {

        const number =
            Number(
                value || 0
            );


        return Number.isFinite(number)
            ? number
            : 0;
    }


    function directEscapeV3(value) {

        return String(
            value ?? ""
        )
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }


    function directRunV3() {

        try {

            return (
                machineOeeActiveRunV1
                ||
                machineOeePendingRunV1
                ||
                null
            );

        } catch (_) {

            return null;
        }
    }


    function directRunIdV3() {

        const run =
            directRunV3();


        return Number(
            run?.run_id
            || run?.id
            || 0
        );
    }


    function directTimeV3(value) {

        if (!value) {
            return "";
        }


        const raw =
            String(value);


        const match =
            raw.match(
                /(\d{2}):(\d{2})(?::\d{2})?/
            );


        if (match) {

            return (
                match[1]
                + ":"
                + match[2]
            );
        }


        try {

            const date =
                new Date(value);


            if (
                !Number.isNaN(
                    date.getTime()
                )
            ) {

                return (
                    String(
                        date.getHours()
                    ).padStart(2, "0")
                    +
                    ":"
                    +
                    String(
                        date.getMinutes()
                    ).padStart(2, "0")
                );
            }

        } catch (_) {
        }


        return "";
    }


    /* ------------------------------------------------------
       EXISTING REAL INPUTS
       ------------------------------------------------------ */

    function directInputsV3() {

        return {

            ok:
                document.getElementById(
                    "machine-oee-ok-qty-v1"
                ),

            reject:
                document.getElementById(
                    "machine-oee-rejected-qty-v1"
                ),

            hold:
                document.getElementById(
                    "machine-oee-hold-qty-v1"
                ),

            cycleMin:
                document.getElementById(
                    "machine-oee-cycle-min-v1"
                ),

            cycleSec:
                document.getElementById(
                    "machine-oee-cycle-sec-v1"
                ),

            loadMin:
                document.getElementById(
                    "machine-oee-load-min-v1"
                ),

            loadSec:
                document.getElementById(
                    "machine-oee-load-sec-v1"
                ),

            rejectionReason:
                document.getElementById(
                    "machine-oee-rejection-reason-v1"
                ),

            completionRemark:
                document.getElementById(
                    "machine-oee-complete-remark-v1"
                ),

            completeButton:
                document.getElementById(
                    "machine-oee-complete-btn-v1"
                )
        };
    }


    /* ------------------------------------------------------
       SOURCE SHELL FINDER
       ------------------------------------------------------ */

    function directCommonParentV3(
        first,
        requiredIds
    ) {

        if (!first) {
            return null;
        }


        let node =
            first.parentElement;


        while (
            node
            &&
            node !== document.body
        ) {

            const hasAll =
                requiredIds.every(
                    function(id) {

                        return Boolean(
                            node.querySelector(
                                "#" + id
                            )
                        );
                    }
                );


            if (hasAll) {
                return node;
            }


            node =
                node.parentElement;
        }


        return null;
    }


    /* ------------------------------------------------------
       BUILD WORKSPACE
       ------------------------------------------------------ */

    function directBuildV3() {

        const inputs =
            directInputsV3();


        if (
            !inputs.ok
            ||
            !inputs.reject
            ||
            !inputs.hold
        ) {

            return null;
        }


        let workspace =
            document.getElementById(
                "machine-oee-direct-entry-v3"
            );


        if (workspace) {
            return workspace;
        }


        const productionShell =
            directCommonParentV3(
                inputs.ok,
                [
                    "machine-oee-rejected-qty-v1",
                    "machine-oee-hold-qty-v1",
                    "machine-oee-cycle-min-v1",
                    "machine-oee-load-min-v1"
                ]
            );


        if (!productionShell) {
            return null;
        }


        workspace =
            document.createElement(
                "section"
            );


        workspace.id =
            "machine-oee-direct-entry-v3";


        workspace.innerHTML = `

            <div class="oee-direct-head-v3">

                <div class="oee-direct-title-v3">

                    <span
                        class="oee-direct-title-icon-v3"
                    >
                        <i
                            class="fa fa-tachometer"
                            aria-hidden="true"
                        ></i>
                    </span>


                    <span>

                        <strong>
                            OEE Entry
                        </strong>
                    </span>

                </div>


                <span
                    class="oee-direct-run-status-v3"
                >

                    <i
                        class="fa fa-cog"
                        aria-hidden="true"
                    ></i>

                    Machine Running

                </span>

            </div>


            <div class="oee-direct-body-v3">


                <div class="oee-direct-section-v3">

                    <div
                        class="oee-direct-section-head-v3"
                    >

                        <div
                            class="oee-direct-section-title-v3"
                        >

                            <i
                                class="fa fa-cubes"
                                aria-hidden="true"
                            ></i>

                            Production &amp; Time

                        </div>
                    </div>


                    <div
                        class="oee-direct-production-grid-v3"
                    >

                        <!-- MACHINE_OEE_QTY_COUNTERS_V8 -->

                        <div
                            class="
                                oee-direct-field-v3
                                oee-qty-field-v8
                                ok
                            "
                        >

                            <label>

                                <i
                                    class="fa fa-check-circle"
                                    aria-hidden="true"
                                ></i>

                                OK Qty

                            </label>


                            <div
                                class="
                                    oee-qty-counter-v8
                                    ok
                                "
                            >

                                <button
                                    type="button"
                                    class="oee-qty-btn-v8"
                                    data-qty-target-v8="machine-oee-ok-qty-v1"
                                    data-qty-delta-v8="-1"
                                    aria-label="Decrease OK Qty"
                                >

                                    <i
                                        class="fa fa-minus"
                                        aria-hidden="true"
                                    ></i>

                                </button>


                                <div
                                    id="oee-direct-ok-slot-v3"
                                    class="oee-qty-input-slot-v8"
                                ></div>


                                <button
                                    type="button"
                                    class="oee-qty-btn-v8"
                                    data-qty-target-v8="machine-oee-ok-qty-v1"
                                    data-qty-delta-v8="1"
                                    aria-label="Increase OK Qty"
                                >

                                    <i
                                        class="fa fa-plus"
                                        aria-hidden="true"
                                    ></i>

                                </button>

                            </div>

                        </div>


                        <div
                            class="
                                oee-direct-field-v3
                                oee-qty-field-v8
                                reject
                            "
                        >

                            <label>

                                <i
                                    class="fa fa-times-circle"
                                    aria-hidden="true"
                                ></i>

                                Rejected Qty

                            </label>


                            <div
                                class="
                                    oee-qty-counter-v8
                                    reject
                                "
                            >

                                <button
                                    type="button"
                                    class="oee-qty-btn-v8"
                                    data-qty-target-v8="machine-oee-rejected-qty-v1"
                                    data-qty-delta-v8="-1"
                                    aria-label="Decrease Rejected Qty"
                                >

                                    <i
                                        class="fa fa-minus"
                                        aria-hidden="true"
                                    ></i>

                                </button>


                                <div
                                    id="oee-direct-reject-slot-v3"
                                    class="oee-qty-input-slot-v8"
                                ></div>


                                <button
                                    type="button"
                                    class="oee-qty-btn-v8"
                                    data-qty-target-v8="machine-oee-rejected-qty-v1"
                                    data-qty-delta-v8="1"
                                    aria-label="Increase Rejected Qty"
                                >

                                    <i
                                        class="fa fa-plus"
                                        aria-hidden="true"
                                    ></i>

                                </button>

                            </div>

                        </div>


                        <div
                            class="
                                oee-direct-field-v3
                                oee-qty-field-v8
                                hold
                            "
                        >

                            <label>

                                <i
                                    class="fa fa-pause-circle"
                                    aria-hidden="true"
                                ></i>

                                Rework Qty

                            </label>


                            <div
                                class="
                                    oee-qty-counter-v8
                                    hold
                                "
                            >

                                <button
                                    type="button"
                                    class="oee-qty-btn-v8"
                                    data-qty-target-v8="machine-oee-hold-qty-v1"
                                    data-qty-delta-v8="-1"
                                    aria-label="Decrease Hold Qty"
                                >

                                    <i
                                        class="fa fa-minus"
                                        aria-hidden="true"
                                    ></i>

                                </button>


                                <div
                                    id="oee-direct-hold-slot-v3"
                                    class="oee-qty-input-slot-v8"
                                ></div>


                                <button
                                    type="button"
                                    class="oee-qty-btn-v8"
                                    data-qty-target-v8="machine-oee-hold-qty-v1"
                                    data-qty-delta-v8="1"
                                    aria-label="Increase Hold Qty"
                                >

                                    <i
                                        class="fa fa-plus"
                                        aria-hidden="true"
                                    ></i>

                                </button>

                            </div>

                        </div>


                        <input
                            id="oee-direct-available-qty-v3"
                            type="hidden"
                            value=""
                        >


                        <div
                            id="oee-direct-qty-reasons-v9"
                            class="oee-direct-qty-reasons-v9"
                        ></div>


                        <div
                            class="oee-direct-field-v3"
                        >

                            <label>

                                <i
                                    class="fa fa-play-circle"
                                    aria-hidden="true"
                                ></i>

                                Start Time

                            </label>


                            <input
                                id="oee-direct-start-time-v3"
                                type="text"
                                inputmode="numeric"
                                autocomplete="off"
                                placeholder="HH:MM:SS"
                            >

                        </div>


                        <div
                            class="oee-direct-field-v3"
                        >

                            <label>

                                <i
                                    class="fa fa-stop-circle"
                                    aria-hidden="true"
                                ></i>

                                Stop Time

                            </label>


                            <input
                                id="oee-direct-stop-time-v3"
                                type="text"
                                inputmode="numeric"
                                autocomplete="off"
                                placeholder="HH:MM:SS"
                            >

                        </div>


                        <div
                            class="
                                oee-direct-field-v3
                                wide
                            "
                        >

                            <label>

                                <i
                                    class="fa fa-clock-o"
                                    aria-hidden="true"
                                ></i>

                                Cycle Time

                            </label>


                            <div
                                class="oee-direct-time-pair-v3"
                            >

                                <div
                                    id="oee-direct-cycle-min-slot-v3"
                                    class="oee-direct-time-input-v3"
                                >
                                    <span>min</span>
                                </div>


                                <div
                                    id="oee-direct-cycle-sec-slot-v3"
                                    class="oee-direct-time-input-v3"
                                >
                                    <span>sec</span>
                                </div>

                            </div>

                        </div>


                        <div
                            class="oee-direct-field-v3"
                        >

                            <label>

                                <i
                                    class="fa fa-exchange"
                                    aria-hidden="true"
                                ></i>

                                Load / Unload

                            </label>


                            <div
                                class="oee-direct-time-pair-v3"
                            >

                                <div
                                    id="oee-direct-load-min-slot-v3"
                                    class="oee-direct-time-input-v3"
                                >
                                    <span>min</span>
                                </div>


                                <div
                                    id="oee-direct-load-sec-slot-v3"
                                    class="oee-direct-time-input-v3"
                                >
                                    <span>sec</span>
                                </div>

                            </div>

                        </div>

                    </div>

                </div>


                <div class="oee-direct-section-v3">

                    <div
                        class="oee-direct-section-head-v3"
                    >

                        <button
                            id="oee-direct-loss-toggle-v3"
                            class="
                                oee-direct-section-title-v3
                                oee-loss-title-toggle-v62
                            "
                            type="button"
                            aria-expanded="true"
                        >

                            <i
                                class="fa fa-clock-o"
                                aria-hidden="true"
                            ></i>

                            <span>
                                Losses
                            </span>

                            <i
                                class="
                                    fa
                                    fa-chevron-up
                                    oee-loss-title-chevron-v62
                                "
                                aria-hidden="true"
                            ></i>

                        </button>
                    </div>


                    <div
                        id="oee-direct-loss-grid-v3"
                    >

                        <div
                            style="
                                grid-column:1 / -1;
                                color:#6b7280;
                                font-size:10px;
                            "
                        >

                            Loading loss master...

                        </div>

                    </div>

                </div>


                <div class="oee-direct-section-v3">

                    <div
                        class="oee-direct-section-head-v3"
                    >

                        <div
                            class="oee-direct-section-title-v3"
                        >

                            <i
                                class="fa fa-check-square-o"
                                aria-hidden="true"
                            ></i>

                            Operation Completion

                        </div>

                    </div>


                    <div
                        class="oee-direct-completion-grid-v3"
                    >

                        <div
                            class="oee-direct-field-v3"
                        >

                            <label>

                                <i
                                    class="fa fa-exclamation-circle"
                                    aria-hidden="true"
                                ></i>

                                Rejection Reason

                            </label>


                            <div
                                id="oee-direct-rejection-slot-v3"
                            >

                                <input
                                    id="machine-oee-rejection-reason-v1"
                                    type="text"
                                    placeholder="Enter only if required"
                                >

                            </div>

                        </div>


                        <div
                            class="oee-direct-field-v3"
                        >

                            <label>

                                <i
                                    class="fa fa-comment-o"
                                    aria-hidden="true"
                                ></i>

                                Completion Remark

                            </label>


                            <div
                                id="oee-direct-remark-slot-v3"
                            >

                                <input
                                    id="machine-oee-complete-remark-v1"
                                    type="text"
                                    placeholder="Optional"
                                >

                            </div>

                        </div>

                    </div>

                </div>


                <div
                    class="oee-direct-actions-v3"
                >

                    <div
                        id="oee-direct-feedback-v3"
                        class="oee-direct-feedback-v3"
                    ></div>


                    <div
                        id="machine-oee-complete-feedback-v1"
                        class="oee-direct-feedback-v3"
                    ></div>


                    <button
                        id="oee-direct-save-v3"
                        class="
                            oee-direct-button-v3
                            oee-direct-save-v3
                        "
                        type="button"
                    >

                        <i
                            class="fa fa-floppy-o"
                            aria-hidden="true"
                        ></i>

                        <span>
                            Save Progress
                        </span>

                    </button>


                    <div
                        id="oee-direct-complete-slot-v3"
                    >

                        <button
                            id="machine-oee-complete-btn-v1"
                            type="button"
                            class="
                                oee-direct-button-v3
                                oee-direct-complete-v3
                            "
                            onclick="
                                machineOeeCompleteOperationV1()
                            "
                        >

                            <i
                                class="fa fa-check"
                                aria-hidden="true"
                            ></i>

                            <span>
                                Complete Operation
                            </span>

                        </button>

                    </div>

                </div>


            </div>
        `;


        productionShell.parentNode.insertBefore(
            workspace,
            productionShell
        );


        return workspace;
    }


    /* ------------------------------------------------------
       MOVE EXISTING REAL INPUTS
       ------------------------------------------------------ */

    function directMoveInputV3(
        input,
        slotId
    ) {

        const slot =
            document.getElementById(
                slotId
            );


        if (
            !input
            ||
            !slot
            ||
            slot.contains(input)
        ) {

            return;
        }


        slot.insertBefore(
            input,
            slot.firstChild
        );
    }


    function directMoveInputsV3() {

        const inputs =
            directInputsV3();


        directMoveInputV3(
            inputs.ok,
            "oee-direct-ok-slot-v3"
        );


        directMoveInputV3(
            inputs.reject,
            "oee-direct-reject-slot-v3"
        );


        directMoveInputV3(
            inputs.hold,
            "oee-direct-hold-slot-v3"
        );


        directMoveInputV3(
            inputs.cycleMin,
            "oee-direct-cycle-min-slot-v3"
        );


        directMoveInputV3(
            inputs.cycleSec,
            "oee-direct-cycle-sec-slot-v3"
        );


        directMoveInputV3(
            inputs.loadMin,
            "oee-direct-load-min-slot-v3"
        );


        directMoveInputV3(
            inputs.loadSec,
            "oee-direct-load-sec-slot-v3"
        );


        directMoveInputV3(
            inputs.rejectionReason,
            "oee-direct-rejection-slot-v3"
        );


        directMoveInputV3(
            inputs.completionRemark,
            "oee-direct-remark-slot-v3"
        );


        if (
            inputs.completeButton
        ) {

            const slot =
                document.getElementById(
                    "oee-direct-complete-slot-v3"
                );


            if (
                slot
                &&
                !slot.contains(
                    inputs.completeButton
                )
            ) {

                inputs.completeButton
                    .classList.add(
                        "oee-direct-button-v3",
                        "oee-direct-complete-v3"
                    );


                inputs.completeButton.innerHTML = `

                    <i
                        class="fa fa-check"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Complete Operation
                    </span>
                `;


                slot.appendChild(
                    inputs.completeButton
                );
            }
        }
    }


    /* ------------------------------------------------------
       HIDE OLD PRODUCTION / LOSS / COMPLETE UI
       after real inputs are moved.
       ------------------------------------------------------ */

    function directHideOldUiV3() {

        const inputs =
            directInputsV3();


        const workspace =
            document.getElementById(
                "machine-oee-direct-entry-v3"
            );


        if (!workspace) {
            return;
        }


        /*
         * Old production shell.
         */
        const productionShell =
            directCommonParentV3(
                inputs.ok,
                []
            );


        /*
         * Find containers by their old titles instead.
         */
        const all =
            Array.from(
                document.querySelectorAll(
                    "div, section"
                )
            );


        for (const node of all) {

            if (
                node === workspace
                ||
                workspace.contains(node)
            ) {

                continue;
            }


            const text =
                String(
                    node.textContent
                    || ""
                )
                .replace(/\s+/g, " ")
                .trim()
                .toLowerCase();


            if (
                text.startsWith(
                    "production entry"
                )
                ||
                text.startsWith(
                    "machine loss entry"
                )
                ||
                text.startsWith(
                    "finish current operation"
                )
            ) {

                /*
                 * Only hide a container if it no longer
                 * contains one of the moved live inputs.
                 */
                const containsLive =
                    [
                        inputs.ok,
                        inputs.reject,
                        inputs.hold,
                        inputs.cycleMin,
                        inputs.loadMin,
                        inputs.rejectionReason,
                        inputs.completionRemark,
                        inputs.completeButton
                    ]
                    .some(
                        function(input) {

                            return (
                                input
                                &&
                                node.contains(input)
                            );
                        }
                    );


                if (!containsLive) {

                    node.classList.add(
                        "oee-direct-hidden-old-v3"
                    );
                }
            }
        }


        /*
         * Old loss dropdown UI is no longer relevant.
         */
        const oldLoss =
            document.getElementById(
                "machine-oee-loss-entry-v1"
            );


        if (
            oldLoss
            &&
            !workspace.contains(
                oldLoss
            )
        ) {

            oldLoss.classList.add(
                "oee-direct-hidden-old-v3"
            );
        }


        /*
         * Old completion shell is no longer relevant.
         */
        const oldComplete =
            document.getElementById(
                "machine-oee-complete-v1"
            );


        if (
            oldComplete
            &&
            !workspace.contains(
                oldComplete
            )
        ) {

            oldComplete.classList.add(
                "oee-direct-hidden-old-v3"
            );
        }
    }


    /* ------------------------------------------------------
       COMPLETION CONTEXT
       Available Qty + start time.
       ------------------------------------------------------ */

    /*
     * MACHINE_OEE_COMPLETION_CONTEXT_SHARED_V1
     *
     * A single run completion-context request is shared by
     * all UI consumers.
     *
     * This prevents Direct Entry and the JC detail renderer
     * from requesting the same endpoint independently.
     */
    const machineOeeCompletionContextCacheSharedV1 =
        new Map();


    async function machineOeeGetCompletionContextSharedV1(
        runId
    ) {

        const key =
            String(
                runId
                || ""
            ).trim();


        if (!key) {
            return null;
        }


        if (
            machineOeeCompletionContextCacheSharedV1.has(
                key
            )
        ) {

            return await (
                machineOeeCompletionContextCacheSharedV1.get(
                    key
                )
            );
        }


        const requestPromise =
            (async function() {

                const response =
                    await fetch(
                        "/api/oee-machine/run/"
                        + encodeURIComponent(key)
                        + "/completion-context",
                        {
                            cache:
                                "no-store"
                        }
                    );


                const data =
                    await response.json();


                if (
                    !response.ok
                    ||
                    data.success === false
                ) {

                    throw new Error(
                        data.error
                        ||
                        "Unable to load completion context."
                    );
                }


                return data;

            })();


        machineOeeCompletionContextCacheSharedV1.set(
            key,
            requestPromise
        );


        try {

            return await requestPromise;

        } catch (error) {

            /*
             * Failed requests are not permanently cached.
             * A later genuine retry is therefore allowed.
             */
            machineOeeCompletionContextCacheSharedV1.delete(
                key
            );

            throw error;
        }
    }


    window.machineOeeGetCompletionContextSharedV1 =
        machineOeeGetCompletionContextSharedV1;


    async function directLoadContextV3() {

        const runId =
            directRunIdV3();


        if (!runId) {
            return;
        }


        /*
         * MACHINE_OEE_CONTEXT_CACHE_V35
         *
         * Completion context is stable while the same
         * machine run is active.
         *
         * The Direct Entry MutationObserver may re-run
         * initialization when other UI sections change.
         * That must NOT create another DB/API request.
         */
        const contextStateV35 =
            directLoadContextV3._stateV35
            || {};


        if (
            Number(
                contextStateV35.runId
            ) === Number(runId)
            &&
            (
                contextStateV35.status
                === "loaded"
                ||
                contextStateV35.status
                === "loading"
            )
        ) {

            return;
        }


        if (
            Number(
                contextStateV35.runId
            ) === Number(runId)
            &&
            contextStateV35.status
            === "failed"
            &&
            (
                Date.now()
                -
                Number(
                    contextStateV35.failedAt
                    || 0
                )
            ) < 5000
        ) {

            return;
        }


        directLoadContextV3._stateV35 = {
            runId:
                runId,

            status:
                "loading"
        };


        try {

            const data =
                await machineOeeGetCompletionContextSharedV1(
                    runId
                );


            if (!data) {

                directLoadContextV3._stateV35 = {
                    runId:
                        runId,

                    status:
                        "failed",

                    failedAt:
                        Date.now()
                };


                return;
            }


            directLoadContextV3._stateV35 = {
                runId:
                    runId,

                status:
                    "loaded",

                card:
                    data.card
                    || null
            };


            const qty =
                data.card?.available_qty
                ?? data.card?.job_card_qty
                ?? data.card?.so_qty
                ?? "";


            const qtyInput =
                document.getElementById(
                    "oee-direct-available-qty-v3"
                );


            if (qtyInput) {

                qtyInput.value =
                    qty;
            }


            directUpdateQtyUiV8();


        } catch (_) {

            directLoadContextV3._stateV35 = {
                runId:
                    runId,

                status:
                    "failed",

                failedAt:
                    Date.now()
            };
        }


        const run =
            directRunV3();


        const start =
            document.getElementById(
                "oee-direct-start-time-v3"
            );


        const stop =
            document.getElementById(
                "oee-direct-stop-time-v3"
            );


        if (start) {

            start.value =
                directTimeV3(
                    run?.oee_start_time
                );
        }


        if (stop) {

            stop.value =
                directTimeV3(
                    run?.oee_end_time
                );
        }
    }


    /* ------------------------------------------------------
       LOSS MASTER + CURRENT VALUES
       ------------------------------------------------------ */

    function directLossListFromResponseV3(
        data
    ) {

        if (
            Array.isArray(
                data?.losses
            )
        ) {

            return data.losses;
        }


        if (
            Array.isArray(
                data?.loss_types
            )
        ) {

            return data.loss_types;
        }


        if (
            Array.isArray(
                data?.loss_master
            )
        ) {

            return data.loss_master;
        }


        if (
            Array.isArray(data)
        ) {

            return data;
        }


        return [];
    }


    async function directLoadLossesV3() {

        const context =
            window.NMTG_MACHINE_OEE_CONTEXT
            || {};


        const machineId =
            Number(
                context.machine_id
                || 0
            );


        if (!machineId) {

            throw new Error(
                "Selected machine is not available."
            );
        }


        directEnsureLossPeriodV16();


        const run =
            directRunV3();


        const runId =
            directRunIdV3();


        const shiftSelect =
            document.getElementById(
                "machine-oee-shift-v1"
            );


        const shiftName =
            String(
                run?.shift_name
                || shiftSelect?.value
                || ""
            ).trim();


        const entryDate =
            String(
                document.getElementById(
                    "oee-loss-entry-date-v16"
                )?.value
                || directTodayV16()
            ).trim();


        const loadKey =
            runId
            ?
            (
                "RUN|"
                + String(runId)
            )
            :
            (
                "MACHINE|"
                + String(machineId)
                + "|"
                + (
                    shiftName
                    || "NO_SHIFT"
                )
                + "|"
                + entryDate
            );


        if (
            directLossLoadedRunV3
            === loadKey
            &&
            directLossMasterV3.length
        ) {

            const existingInputs =
                document.querySelectorAll(
                    "#oee-direct-loss-grid-v3 "
                    + ".oee-direct-loss-input-v3"
                );


            if (
                existingInputs.length
                !== 27
            ) {

                directRenderLossGridV3();
            }


            return;
        }


        /*
         * PERFORMANCE_FIX_LOSS_MASTER_V2
         *
         * A1-A27 loss master is static for this page session.
         * directLoadLossesV3 may run again when startup moves
         * from machine/shift context to the restored RUN context.
         *
         * Reuse the already-loaded master instead of requesting
         * /loss-master again. Current run losses are still loaded
         * separately below.
         */
        if (!directLossMasterV3.length) {

            const masterResponse =
                await fetch(
                    "/api/oee-machine/loss-master",
                    {
                        cache:"no-store"
                    }
                );


            const masterData =
                (
                    typeof machineOeeReadApiResponseV2
                    === "function"
                )
                ?
                await machineOeeReadApiResponseV2(
                    masterResponse,
                    "OEE loss master"
                )
                :
                await masterResponse.json();


            if (
                !masterResponse.ok
                ||
                masterData.success
                === false
            ) {

                throw new Error(
                    masterData.error
                    ||
                    "Unable to load loss master."
                );
            }


            directLossMasterV3 =
                directLossListFromResponseV3(
                    masterData
                );
        }


        directLossRowsV3 =
            [];


        if (runId) {

            const currentResponse =
                await fetch(
                    "/api/oee-machine/run/"
                    + encodeURIComponent(
                        runId
                    )
                    + "/losses",
                    {
                        cache:"no-store"
                    }
                );


            const currentData =
                (
                    typeof machineOeeReadApiResponseV2
                    === "function"
                )
                ?
                await machineOeeReadApiResponseV2(
                    currentResponse,
                    "Run OEE losses"
                )
                :
                await currentResponse.json();


            if (
                !currentResponse.ok
                ||
                currentData.success
                === false
            ) {

                throw new Error(
                    currentData.error
                    ||
                    "Unable to load run losses."
                );
            }


            directLossRowsV3 =
                directLossListFromResponseV3(
                    currentData
                );

        } else if (shiftName) {

            const currentResponse =
                await fetch(
                    "/api/oee-machine/"
                    + "machine-losses/"
                    + encodeURIComponent(
                        machineId
                    )
                    + "?shift_name="
                    + encodeURIComponent(
                        shiftName
                    )
                    + "&entry_date="
                    + encodeURIComponent(
                        entryDate
                    ),
                    {
                        cache:"no-store"
                    }
                );


            const currentData =
                (
                    typeof machineOeeReadApiResponseV2
                    === "function"
                )
                ?
                await machineOeeReadApiResponseV2(
                    currentResponse,
                    "Machine OEE losses"
                )
                :
                await currentResponse.json();


            if (
                !currentResponse.ok
                ||
                currentData.success
                === false
            ) {

                throw new Error(
                    currentData.error
                    ||
                    "Unable to load machine losses."
                );
            }


            directLossRowsV3 =
                directLossListFromResponseV3(
                    currentData
                );
        }


        directLossLoadedRunV3 =
            loadKey;


        directRenderLossGridV3();
    }


        function directLossCodeV3(row) {

        return String(
            row?.loss_code
            || row?.code
            || ""
        ).trim();
    }


    function directLossNameV3(row) {

        return String(
            row?.loss_name
            || row?.name
            || row?.description
            || directLossCodeV3(row)
        ).trim();
    }


    function directLossMinutesV3(code) {

        return directLossRowsV3
            .filter(
                function(row) {

                    return (
                        directLossCodeV3(row)
                        === code
                    );
                }
            )
            .reduce(
                function(total, row) {

                    return (
                        total
                        +
                        directNumberV3(
                            row.loss_minutes
                            ?? row.minutes
                            ?? 0
                        )
                    );
                },
                0
            );
    }


    /* MACHINE_OEE_COMMON_LOSS_UI_V16 */

    function directTodayV16() {

        const now =
            new Date();


        const year =
            String(
                now.getFullYear()
            );


        const month =
            String(
                now.getMonth()
                + 1
            ).padStart(
                2,
                "0"
            );


        const day =
            String(
                now.getDate()
            ).padStart(
                2,
                "0"
            );


        return (
            year
            + "-"
            + month
            + "-"
            + day
        );
    }


    function directLossClockMinutesV16(
        value
    ) {

        const match =
            String(
                value
                || ""
            )
            .trim()
            .match(
                /^(\d{2}):(\d{2})$/
            );


        if (!match) {
            return null;
        }


        const hours =
            Number(
                match[1]
            );


        const minutes =
            Number(
                match[2]
            );


        if (
            !Number.isInteger(
                hours
            )
            ||
            !Number.isInteger(
                minutes
            )
            ||
            hours < 0
            ||
            hours > 23
            ||
            minutes < 0
            ||
            minutes > 59
        ) {

            return null;
        }


        return (
            hours * 60
            + minutes
        );
    }


    function directLossDurationV16(
        startValue,
        stopValue
    ) {

        const start =
            directLossClockMinutesV16(
                startValue
            );


        const stop =
            directLossClockMinutesV16(
                stopValue
            );


        if (
            start === null
            ||
            stop === null
        ) {

            return null;
        }


        let duration =
            stop
            - start;


        if (duration < 0) {

            duration +=
                24 * 60;
        }


        return duration;
    }


    function directLossCurrentTotalV16() {

        return Array.from(
            document.querySelectorAll(
                ".oee-direct-loss-input-v3"
            )
        )
        .reduce(
            function(
                total,
                input
            ) {

                const value =
                    Number(
                        input.value
                        || 0
                    );


                return (
                    total
                    +
                    (
                        Number.isFinite(
                            value
                        )
                        &&
                        value > 0

                        ? value
                        : 0
                    )
                );
            },
            0
        );
    }


    function directEnsureLossPeriodV16() {

        /*
         * Running JC already uses Production Start/Stop.
         * Do not render the separate loss-period block.
         *
         * Keep this block only for no-JC machine-level
         * loss entry, where its Start/End fields are still
         * required by the existing save workflow.
         */
        if (
            directRunIdV3()
        ) {

            const oldBlock =
                document.getElementById(
                    "oee-loss-period-v16"
                );


            if (oldBlock) {
                oldBlock.remove();
            }


            return null;
        }


        const grid =
            document.getElementById(
                "oee-direct-loss-grid-v3"
            );


        if (
            !grid
            ||
            !grid.parentNode
        ) {

            return null;
        }


        let block =
            document.getElementById(
                "oee-loss-period-v16"
            );


        if (block) {

            return block;
        }


        block =
            document.createElement(
                "div"
            );


        block.id =
            "oee-loss-period-v16";


        block.className =
            "oee-loss-period-v16";


        block.innerHTML = `

            <div
                class="oee-loss-period-grid-v16"
            >
                <div
                    class="oee-loss-period-field-v16"
                >

                    <label>
                        Start Time
                    </label>

                    <input
                        id="oee-loss-start-v16"
                        type="time"
                    >

                </div>


                <div
                    class="oee-loss-period-field-v16"
                >

                    <label>
                        End Time
                    </label>

                    <input
                        id="oee-loss-stop-v16"
                        type="time"
                    >

                </div>


            </div>
        `;


        grid.parentNode.insertBefore(
            block,
            grid
        );


        directWireLossPeriodV16();

        directUpdateLossPeriodV16();


        return block;
    }


    function directUpdateLossPeriodV16() {

        /*
         * V17:
         * Duration, Loss Total, Difference and live
         * match text are intentionally not displayed.
         *
         * Backend still performs the time comparison
         * and returns a warning after Save when needed.
         */
        return;
    }


    function directWireLossPeriodV16() {

        const ids = [
            "oee-loss-start-v16",
            "oee-loss-stop-v16"
        ];


        for (const id of ids) {

            const input =
                document.getElementById(
                    id
                );


            if (
                !input
                ||
                input.dataset.wiredV16
                === "1"
            ) {

                continue;
            }


            input.dataset.wiredV16 =
                "1";


            input.addEventListener(
                "input",
                directUpdateLossPeriodV16
            );


            input.addEventListener(
                "change",
                directUpdateLossPeriodV16
            );
        }


        const dateInput =
            document.getElementById(
                "oee-loss-entry-date-v16"
            );


        if (
            dateInput
            &&
            dateInput.dataset.wiredV16
            !== "1"
        ) {

            dateInput.dataset.wiredV16 =
                "1";


            dateInput.addEventListener(
                "change",
                function() {

                    directLossLoadedRunV3 =
                        "";


                    directLoadLossesV3();
                }
            );
        }


        const lossInputs =
            Array.from(
                document.querySelectorAll(
                    ".oee-direct-loss-input-v3"
                )
            );


        for (
            const input
            of lossInputs
        ) {

            if (
                input.dataset.wiredV16
                === "1"
            ) {

                continue;
            }


            input.dataset.wiredV16 =
                "1";


            input.addEventListener(
                "input",
                directUpdateLossPeriodV16
            );


            input.addEventListener(
                "change",
                directUpdateLossPeriodV16
            );
        }
    }


    function directShowLossSaveResultV16(
        data
    ) {

        const feedback =
            document.getElementById(
                "machine-oee-machine-loss-feedback-v13"
            );


        if (!feedback) {
            return;
        }


        if (data?.warning) {

            feedback.style.color =
                "#b45309";


            feedback.textContent =
                "Saved with warning: "
                + String(
                    data.warning
                );


            return;
        }


        feedback.style.color =
            "#15803d";


        feedback.textContent =
            "Machine losses saved successfully.";
    }


    function directResetLossBlockV16() {

        const start =
            document.getElementById(
                "oee-loss-start-v16"
            );


        const stop =
            document.getElementById(
                "oee-loss-stop-v16"
            );


        if (start) {

            start.value =
                "";
        }


        if (stop) {

            stop.value =
                "";
        }


        for (
            const input
            of document.querySelectorAll(
                ".oee-direct-loss-input-v3"
            )
        ) {

            input.value =
                "0";
        }


        directUpdateLossPeriodV16();
    }


    function directRenderLossGridV3() {

        const grid =
            document.getElementById(
                "oee-direct-loss-grid-v3"
            );


        if (!grid) {
            return;
        }


        directEnsureLossPeriodV16();


        const sorted =
            directLossMasterV3
            .slice()
            .sort(
                function(
                    a,
                    b
                ) {

                    const aCode =
                        directLossCodeV3(
                            a
                        );


                    const bCode =
                        directLossCodeV3(
                            b
                        );


                    const aNum =
                        Number(
                            aCode.replace(
                                /\D/g,
                                ""
                            )
                            || 0
                        );


                    const bNum =
                        Number(
                            bCode.replace(
                                /\D/g,
                                ""
                            )
                            || 0
                        );


                    return (
                        aNum
                        - bNum
                    );
                }
            );


        grid.innerHTML =
            sorted
            .map(
                function(row) {

                    const code =
                        directLossCodeV3(
                            row
                        );


                    const name =
                        directLossNameV3(
                            row
                        );


                    /* MACHINE_OEE_LOSS_RENDER_MINUTES_V41 */

                    const minutes =
                        directLossMinutesV3(
                            code
                        );


                    const typeId =
                        Number(
                            row.id
                            ||
                            row.loss_type_id
                            ||
                            0
                        );


                    return `

                        <div
                            class="oee-direct-loss-row-v3"
                        >

                            <div
                                class="oee-direct-loss-info-v3"
                            >

                                <span
                                    class="oee-direct-loss-code-v3"
                                >
                                    ${directEscapeV3(
                                        code
                                    )}
                                </span>


                                <span
                                    class="oee-direct-loss-name-v3"
                                >
                                    ${directEscapeV3(
                                        name
                                    )}
                                </span>

                            </div>


                            <div
                                class="oee-direct-loss-input-wrap-v3"
                            >

                                <input
                                    class="oee-direct-loss-input-v3"

                                    type="number"

                                    min="0"
                                    step="0.01"

                                    data-loss-code-v3="${directEscapeV3(
                                        code
                                    )}"

                                    data-loss-type-id-v3="${typeId}"

                                    value="${directRunIdV3() ? minutes : 0}"
                                >


                                <span
                                    class="oee-direct-loss-unit-v3"
                                >
                                    min
                                </span>

                            </div>

                        </div>
                    `;
                }
            )
            .join("");


        directWireLossPeriodV16();

        directUpdateLossPeriodV16();
    }


    /* ------------------------------------------------------
       SAVE PRODUCTION
       ------------------------------------------------------ */

    async function directSaveProductionV3() {

        const runId =
            directRunIdV3();


        if (!runId) {

            throw new Error(
                "No active machine run."
            );
        }


        const inputs =
            directInputsV3();


        const payload = {

            oee_start_time:
                String(
                    document.getElementById(
                        "oee-direct-start-time-v3"
                    )?.value
                    || ""
                ).trim(),

            oee_end_time:
                String(
                    document.getElementById(
                        "oee-direct-stop-time-v3"
                    )?.value
                    || ""
                ).trim(),

            ok_qty:
                directNumberV3(
                    inputs.ok?.value
                ),

            rejected_qty:
                directNumberV3(
                    inputs.reject?.value
                ),

            hold_qty:
                directNumberV3(
                    inputs.hold?.value
                ),

            cycle_minutes:
                directNumberV3(
                    inputs.cycleMin?.value
                ),

            cycle_seconds:
                directNumberV3(
                    inputs.cycleSec?.value
                ),

            load_unload_minutes:
                directNumberV3(
                    inputs.loadMin?.value
                ),

            load_unload_seconds:
                directNumberV3(
                    inputs.loadSec?.value
                )
        };


        const response =
            await fetch(
                `/api/oee-machine/run/${runId}/production`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(
                            payload
                        )
                }
            );


        const data =
            await response.json();


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || "Production save failed."
            );
        }
    }


    /* ------------------------------------------------------
       SAVE DIRECT LOSS GRID
       ------------------------------------------------------ */

    async function directSaveLossesV3() {

        const context =
            window.NMTG_MACHINE_OEE_CONTEXT
            || {};


        const machineId =
            Number(
                context.machine_id
                || 0
            );


        if (!machineId) {

            throw new Error(
                "Selected machine is not available."
            );
        }


        directEnsureLossPeriodV16();


        const run =
            directRunV3();


        const runId =
            directRunIdV3();


        const shiftSelect =
            document.getElementById(
                "machine-oee-shift-v1"
            );


        const shiftName =
            String(
                run?.shift_name
                || shiftSelect?.value
                || ""
            ).trim();


        if (!shiftName) {

            throw new Error(
                "Please select Shift before saving losses."
            );
        }


        const entryDate =
            String(
                document.getElementById(
                    "oee-loss-entry-date-v16"
                )?.value
                ||
                run?.session_date
                ||
                directTodayV16()
            ).trim();


        const lossStartTime =
            String(
                (
                    runId
                    ?
                    document.getElementById(
                        "oee-direct-start-time-v3"
                    )?.value
                    :
                    document.getElementById(
                        "oee-loss-start-v16"
                    )?.value
                )
                || ""
            ).trim();


        const lossStopTime =
            String(
                (
                    runId
                    ?
                    document.getElementById(
                        "oee-direct-stop-time-v3"
                    )?.value
                    :
                    document.getElementById(
                        "oee-loss-stop-v16"
                    )?.value
                )
                || ""
            ).trim();


        if (
            !lossStartTime
            ||
            !lossStopTime
        ) {

            throw new Error(
                runId
                ?
                "Please enter Production Start Time and Stop Time."
                :
                "Please enter Loss Start Time and Loss End Time."
            );
        }


        const inputs =
            Array.from(
                document.querySelectorAll(
                    ".oee-direct-loss-input-v3"
                )
            );


        if (
            inputs.length !== 27
        ) {

            throw new Error(
                "A1 to A27 Loss Entry is not fully loaded."
            );
        }


        const losses =
            [];


        for (const input of inputs) {

            const code =
                String(
                    input.dataset
                        .lossCodeV3
                    || ""
                ).trim().toUpperCase();


            const raw =
                String(
                    input.value
                    ?? ""
                ).trim();


            const minutes =
                raw === ""
                ? 0
                : Number(
                    raw
                );


            if (
                !/^A([1-9]|1[0-9]|2[0-7])$/
                    .test(
                        code
                    )
            ) {

                throw new Error(
                    "Invalid OEE Loss Code."
                );
            }


            if (
                !Number.isFinite(
                    minutes
                )
                ||
                minutes < 0
            ) {

                throw new Error(
                    code
                    + " loss minutes must be 0 or more."
                );
            }


            losses.push({
                loss_code:
                    code,

                loss_minutes:
                    minutes
            });
        }


        if (
            directLossCurrentTotalV16()
            <= 0
        ) {

            throw new Error(
                "Enter at least one A1-A27 loss before saving."
            );
        }


        let actualOperatorMasterId =
            null;


        try {

            if (
                typeof machineOeeActualOperatorIdV1
                === "function"
            ) {

                actualOperatorMasterId =
                    machineOeeActualOperatorIdV1();
            }

        } catch (_) {

            actualOperatorMasterId =
                null;
        }


        const url =
            runId
            ?
            (
                "/api/oee-machine/run/"
                + encodeURIComponent(
                    runId
                )
                + "/losses"
            )
            :
            (
                "/api/oee-machine/"
                + "machine-losses/"
                + encodeURIComponent(
                    machineId
                )
            );


        const response =
            await fetch(
                url,
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            entry_date:
                                entryDate,

                            shift_name:
                                shiftName,

                            loss_start_time:
                                lossStartTime,

                            loss_stop_time:
                                lossStopTime,

                            operator_master_id:
                                actualOperatorMasterId,

                            losses:
                                losses
                        })
                }
            );


        const data =
            (
                typeof machineOeeReadApiResponseV2
                === "function"
            )
            ?
            await machineOeeReadApiResponseV2(
                response,
                runId
                ?
                "Save Run OEE losses"
                :
                "Save Machine OEE losses"
            )
            :
            await response.json();


        if (
            !response.ok
            ||
            data.success
            === false
        ) {

            throw new Error(
                data.error
                ||
                "OEE loss save failed."
            );
        }


        directLossRowsV3 =
            directLossListFromResponseV3(
                data
            );


        directLossLoadedRunV3 =
            runId
            ?
            (
                "RUN|"
                + String(runId)
            )
            :
            (
                "MACHINE|"
                + String(machineId)
                + "|"
                + shiftName
                + "|"
                + entryDate
            );


        directRenderLossGridV3();


        /*
         * Running JC keeps its saved loss values visible.
         * No-JC mode starts a fresh machine-loss block.
         */
        if (!runId) {

            directResetLossBlockV16();
        }


        directShowLossSaveResultV16(
            data
        );


        return data;
    }


    /*
     * Existing public hooks used by the
     * no-JC Machine Loss card.
     */
    window.machineOeeDirectLoadMachineLossesV13 =
        directLoadLossesV3;


    /* OEE_ACTIVITY_SHARED_NO_JC_SAVE_V91 */

    function activityTimePartsV91(
        value
    ) {

        const text =
            String(
                value
                || ""
            ).trim();


        const match =
            text.match(
                /^(\d{2}):(\d{2}):(\d{2})$/
            );


        if (!match) {

            throw new Error(
                "Time must be in HH:MM:SS format."
            );
        }


        const hour =
            Number(match[1]);

        const minute =
            Number(match[2]);

        const second =
            Number(match[3]);


        if (
            hour > 23
            ||
            minute > 59
            ||
            second > 59
        ) {

            throw new Error(
                "Enter a valid Start Time and Stop Time."
            );
        }


        return {
            hour:
                hour,

            minute:
                minute,

            second:
                second,

            total:
                (
                    hour * 3600
                    +
                    minute * 60
                    +
                    second
                )
        };
    }


    function activityDateTimeV91(
        dateValue,
        timeValue,
        addDay
    ) {

        const dateText =
            String(
                dateValue
                || ""
            ).trim();


        if (
            !/^\d{4}-\d{2}-\d{2}$/
                .test(
                    dateText
                )
        ) {

            throw new Error(
                "Valid activity date is required."
            );
        }


        const parts =
            dateText.split("-")
                .map(Number);


        const time =
            activityTimePartsV91(
                timeValue
            );


        const dt =
            new Date(
                parts[0],
                parts[1] - 1,
                parts[2],
                time.hour,
                time.minute,
                time.second,
                0
            );


        if (addDay) {

            dt.setDate(
                dt.getDate() + 1
            );
        }


        const pad =
            function(value) {

                return String(value)
                    .padStart(
                        2,
                        "0"
                    );
            };


        return (
            dt.getFullYear()
            + "-"
            + pad(
                dt.getMonth() + 1
            )
            + "-"
            + pad(
                dt.getDate()
            )
            + " "
            + pad(
                dt.getHours()
            )
            + ":"
            + pad(
                dt.getMinutes()
            )
            + ":"
            + pad(
                dt.getSeconds()
            )
        );
    }


    async function readActivityApiV91(
        response,
        label
    ) {

        let data = null;


        try {

            data =
                await response.json();

        } catch (_) {

            throw new Error(
                label
                + " returned an invalid response."
            );
        }


        return data;
    }


    async function saveSelectedActivityV91(
        selection
    ) {

        const context =
            window.NMTG_MACHINE_OEE_CONTEXT
            || {};


        const machineId =
            Number(
                context.machine_id
                || 0
            );


        if (!machineId) {

            throw new Error(
                "Selected machine is not available."
            );
        }


        const shiftSelect =
            document.getElementById(
                "machine-oee-shift-v1"
            );


        const shiftName =
            String(
                shiftSelect?.value
                || ""
            ).trim();


        if (!shiftName) {

            throw new Error(
                "Please select Shift first."
            );
        }


        if (
            !Number(
                selection.activity_master_id
                || 0
            )
        ) {

            throw new Error(
                "Please select an activity first."
            );
        }


        if (
            selection.remarks_required
            &&
            !String(
                selection.remarks
                || ""
            ).trim()
        ) {

            throw new Error(
                "Reason is required for Other."
            );
        }


        directEnsureLossPeriodV16();


        const entryDate =
            String(
                document.getElementById(
                    "oee-loss-entry-date-v16"
                )?.value
                ||
                directTodayV16()
            ).trim();


        const startTime =
            String(
                document.getElementById(
                    "oee-loss-start-v16"
                )?.value
                || ""
            ).trim();


        const stopTime =
            String(
                document.getElementById(
                    "oee-loss-stop-v16"
                )?.value
                || ""
            ).trim();


        if (
            !startTime
            ||
            !stopTime
        ) {

            throw new Error(
                "Please enter Loss Start Time and Loss End Time."
            );
        }


        const startParts =
            activityTimePartsV91(
                startTime
            );


        const stopParts =
            activityTimePartsV91(
                stopTime
            );


        const crossesMidnight =
            stopParts.total
            <
            startParts.total;


        const startedAt =
            activityDateTimeV91(
                entryDate,
                startTime,
                false
            );


        const endedAt =
            activityDateTimeV91(
                entryDate,
                stopTime,
                crossesMidnight
            );


        const inputs =
            Array.from(
                document.querySelectorAll(
                    ".oee-direct-loss-input-v3"
                )
            );


        if (
            inputs.length !== 27
        ) {

            throw new Error(
                "A1 to A27 Loss Entry is not fully loaded."
            );
        }


        const losses = [];


        for (const input of inputs) {

            const code =
                String(
                    input.dataset
                        .lossCodeV3
                    || ""
                ).trim().toUpperCase();


            const raw =
                String(
                    input.value
                    ?? ""
                ).trim();


            const minutes =
                raw === ""
                ? 0
                : Number(raw);


            if (
                !/^A([1-9]|1[0-9]|2[0-7])$/
                    .test(
                        code
                    )
            ) {

                throw new Error(
                    "Invalid OEE Loss Code."
                );
            }


            if (
                !Number.isFinite(
                    minutes
                )
                ||
                minutes < 0
            ) {

                throw new Error(
                    code
                    + " loss minutes must be 0 or more."
                );
            }


            losses.push({
                loss_code:
                    code,

                loss_minutes:
                    minutes
            });
        }


        if (
            losses.reduce(
                function(total, item) {

                    return (
                        total
                        +
                        Number(
                            item.loss_minutes
                            || 0
                        )
                    );
                },
                0
            ) <= 0
        ) {

            throw new Error(
                "Enter at least one A1-A27 loss before saving."
            );
        }


        /* OEE_ACTIVITY_OPERATOR_PAYLOAD_V92 */

        let activityOperatorMasterId =
            null;


        try {

            if (
                typeof machineOeeActualOperatorIdV1
                === "function"
            ) {

                activityOperatorMasterId =
                    Number(
                        machineOeeActualOperatorIdV1()
                        || 0
                    );
            }

        } catch (_) {

            activityOperatorMasterId =
                null;
        }


        if (
            !activityOperatorMasterId
        ) {

            throw new Error(
                "Please enter the actual machine operator."
            );
        }


        /*
         * Resolve the same current machine/date/shift
         * session already used by the OEE workspace.
         */
        const workspaceResponse =
            await fetch(
                "/api/oee-machine/workspace",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            machine_id:
                                machineId,

                            shift_name:
                                shiftName
                        })
                }
            );


        const workspaceData =
            await readActivityApiV91(
                workspaceResponse,
                "Resolve OEE session"
            );


        if (
            !workspaceResponse.ok
            ||
            workspaceData.success
                === false
        ) {

            throw new Error(
                workspaceData.error
                ||
                "Unable to resolve OEE session."
            );
        }


        // 2-table model: no persistent machine_session row.
        // Keep sessionId as 0 — the backend no longer requires it.
        const sessionId = 0;


        /*
         * Start the Tool Room / Development activity.
         */
        const startResponse =
            await fetch(
                "/api/oee-machine/activity-runs/start",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            session_id:
                                sessionId,

                            machine_id:
                                machineId,

                            activity_master_id:
                                Number(
                                    selection
                                        .activity_master_id
                                ),

                            operator_master_id:
                                activityOperatorMasterId,

                            started_at:
                                startedAt,

                            remarks:
                                String(
                                    selection.remarks
                                    || ""
                                ).trim()
                        })
                }
            );


        const startData =
            await readActivityApiV91(
                startResponse,
                "Start activity"
            );


        let activityRunId = 0;


        if (
            startResponse.ok
            &&
            startData.success
                !== false
        ) {

            activityRunId =
                Number(
                    startData
                        .activity_run
                        ?.id
                    || 0
                );

        } else if (
            startResponse.status
                === 409
            &&
            startData.running_activity
            &&
            Number(
                startData
                    .running_activity
                    .id
                || 0
            )
            &&
            String(
                startData
                    .running_activity
                    .activity_name
                || ""
            ).trim()
            ===
            String(
                selection.activity_name
                || ""
            ).trim()
        ) {

            /*
             * Safe retry path:
             * reuse the already-running same activity.
             */
            activityRunId =
                Number(
                    startData
                        .running_activity
                        .id
                );

        } else {

            throw new Error(
                startData.error
                ||
                "Unable to start activity."
            );
        }


        if (!activityRunId) {

            throw new Error(
                "Activity run ID was not returned."
            );
        }


        if (
            typeof window.machineOeeSaveToolRowsV5
            === "function"
        ) {

            await window.machineOeeSaveToolRowsV5({
                activity_run_id:
                    activityRunId
            });
        }


        /*
         * Save A1-A27 using the same visible loss grid,
         * but link it to activity_run_id.
         */
        const lossResponse =
            await fetch(
                "/api/oee-machine/activity-run/"
                + encodeURIComponent(
                    activityRunId
                )
                + "/losses",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            entry_date:
                                entryDate,

                            shift_name:
                                shiftName,

                            loss_start_time:
                                startTime,

                            loss_stop_time:
                                stopTime,

                            losses:
                                losses
                        })
                }
            );


        const lossData =
            await readActivityApiV91(
                lossResponse,
                "Save activity losses"
            );


        if (
            !lossResponse.ok
            ||
            lossData.success
                === false
        ) {

            throw new Error(
                lossData.error
                ||
                "Unable to save activity losses."
            );
        }


        /*
         * Stop/complete the activity after its losses
         * have saved successfully.
         */
        const completeResponse =
            await fetch(
                "/api/oee-machine/activity-runs/complete",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            activity_run_id:
                                activityRunId,

                            ended_at:
                                endedAt
                        })
                }
            );


        const completeData =
            await readActivityApiV91(
                completeResponse,
                "Complete activity"
            );


        if (
            !completeResponse.ok
            ||
            completeData.success
                === false
        ) {

            throw new Error(
                completeData.error
                ||
                "Unable to complete activity."
            );
        }


        return {
            success:
                true,

            activity_run_id:
                activityRunId,

            activity:
                completeData
                    .activity_run,

            losses:
                lossData
        };
    }


    async function directSaveMachineLossesByModeV91() {

        const selection =
            (
                typeof window
                    .machineOeeGetActivitySelectionV89
                === "function"
            )
            ?
            window
                .machineOeeGetActivitySelectionV89()
            :
            {
                mode:
                    "PRODUCTION"
            };


        const mode =
            String(
                selection.mode
                || "PRODUCTION"
            ).trim().toUpperCase();


        /*
         * Existing Production + no-JC behavior
         * remains completely unchanged.
         */
        if (
            mode === "PRODUCTION"
        ) {

            /* OEE_PRODUCTION_SAVE_LOSSES_TOOLING_V119 */
            /* OEE_MACHINE_LOSS_TOOLING_V121 */

            const lossResult =
                await directSaveLossesV3();


            const runId =
                Number(
                    directRunIdV3()
                    || 0
                );


            const machineLossEntryId =
                Number(
                    (
                        lossResult
                        &&
                        lossResult.session_id
                    )
                    || 0
                );


            if (
                runId > 0
                &&
                typeof window.machineOeeSaveToolRowsV5
                === "function"
            ) {

                await window.machineOeeSaveToolRowsV5({
                    run_id:
                        runId
                });

            } else if (
                runId <= 0
                &&
                machineLossEntryId > 0
                &&
                typeof window.machineOeeSaveToolRowsV5
                === "function"
            ) {

                await window.machineOeeSaveToolRowsV5({
                    machine_loss_entry_id:
                        machineLossEntryId
                });
            }


            return lossResult;
        }


        if (
            mode !== "TOOL_ROOM"
            &&
            mode !== "DEVELOPMENT"
        ) {

            throw new Error(
                "Invalid OEE activity mode."
            );
        }


        return await saveSelectedActivityV91(
            selection
        );
    }


    window.machineOeeDirectSaveMachineLossesV13 =
        directSaveMachineLossesByModeV91;


    window.machineOeeDirectResetMachineLossesV13 =
        function() {

            directLossLoadedRunV3 =
                "";
        };


        /*
     * OEE_CORE_COMPLETE_SAVE_V44
     *
     * Complete Job reuses the existing Direct Entry
     * run-linked A1-A27 saver.
     *
     * No second loss-save implementation is created here.
     */
    window.machineOeeSaveCurrentRunLossesCoreV44 =
        async function() {

            const run =
                directRunV3();


            if (
                !run
                ||
                !Number(
                    run.run_id
                    || 0
                )
            ) {

                throw new Error(
                    "No active machine run."
                );
            }


            /*
             * OEE_COMPLETE_LOSSES_GUARD_V44
             *
             * If the operator has entered no loss minutes at all
             * (every A1-A27 field is 0), saving an all-zero loss
             * record is meaningless and the backend rejects it.
             *
             * Skip the save exactly as directSaveAllV3 does.
             * The session OEE recalc still runs via the production
             * save route and will use whatever losses are already
             * stored in oee_machine_loss_events for this session.
             */
            if (
                typeof directLossCurrentTotalV16
                === "function"
                &&
                directLossCurrentTotalV16() <= 0
            ) {
                return;
            }


            return await directSaveLossesV3();
        };


/* ------------------------------------------------------
       SAVE ALL
       ------------------------------------------------------ */

    async function directSaveAllV3() {

        if (directBusyV3) {
            return;
        }


        const button =
            document.getElementById(
                "oee-direct-save-v3"
            );


        const feedback =
            document.getElementById(
                "oee-direct-feedback-v3"
            );


        directBusyV3 =
            true;


        if (button) {

            button.disabled =
                true;
        }


        if (feedback) {

            feedback.style.color =
                "#6b7280";


            feedback.textContent =
                "Saving...";
        }


        try {

            await directSaveProductionV3();

            if (
                typeof window.machineOeeSaveToolRowsV5
                === "function"
            ) {

                await window.machineOeeSaveToolRowsV5({
                    run_id:
                        directRunIdV3()
                });
            }

            if (
                directLossCurrentTotalV16()
                > 0
            ) {

                await directSaveLossesV3();
            }


            try {

                if (
                    typeof machineOeeRefreshLiveCalcV1
                    === "function"
                ) {

                    await machineOeeRefreshLiveCalcV1();
                }

            } catch (_) {
            }


            if (feedback) {

                feedback.style.color =
                    "#16833a";


                feedback.innerHTML = `

                    <i
                        class="fa fa-check-circle"
                        aria-hidden="true"
                    ></i>

                    Saved
                `;
            }


            if (
                typeof showToast
                === "function"
            ) {

                showToast(
                    "OEE progress saved successfully.",
                    "success"
                );
            }


        } catch (error) {

            const saveErrorV39 =
                error.message
                || "Save failed.";


            if (feedback) {

                feedback.style.color =
                    "#b42318";


                feedback.textContent =
                    saveErrorV39;
            }


            if (
                typeof showToast
                === "function"
            ) {

                showToast(
                    saveErrorV39,
                    "error"
                );
            }


        } finally {

            directBusyV3 =
                false;


            if (button) {

                button.disabled =
                    false;
            }
        }
    }


    /* ------------------------------------------------------
       QTY COUNTERS V8
       ------------------------------------------------------ */

    function directQtyInputsV8() {

        return [
            document.getElementById(
                "machine-oee-ok-qty-v1"
            ),

            document.getElementById(
                "machine-oee-rejected-qty-v1"
            ),

            document.getElementById(
                "machine-oee-hold-qty-v1"
            )
        ]
        .filter(Boolean);
    }


    function directAvailableQtyV8() {

        return Math.max(
            0,
            Math.floor(
                directNumberV3(
                    document.getElementById(
                        "oee-direct-available-qty-v3"
                    )?.value
                )
            )
        );
    }


    function directQtyTotalV8() {

        return directQtyInputsV8()
            .reduce(
                function(total, input) {

                    return (
                        total
                        +
                        Math.max(
                            0,
                            Math.floor(
                                directNumberV3(
                                    input.value
                                )
                            )
                        )
                    );
                },
                0
            );
    }


    function directUpdateQtyUiV8() {

        const availableInput =
            document.getElementById(
                "oee-direct-available-qty-v3"
            );


        const okInput =
            document.getElementById(
                "machine-oee-ok-qty-v1"
            );


        const rejectedInput =
            document.getElementById(
                "machine-oee-rejected-qty-v1"
            );


        const holdInput =
            document.getElementById(
                "machine-oee-hold-qty-v1"
            );


        if (
            !okInput
            ||
            !rejectedInput
            ||
            !holdInput
        ) {
            return;
        }


        const available =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        availableInput?.value
                    )
                )
            );


        /*
         * Fresh run only:
         * OK Qty defaults to full Available Qty.
         *
         * Existing saved Qty is never overwritten.
         */
        if (
            available > 0
            &&
            availableInput
            &&
            availableInput.dataset
                .autoOkAppliedV10
            !== "1"
        ) {

            const currentOk =
                Math.max(
                    0,
                    Math.floor(
                        directNumberV3(
                            okInput.value
                        )
                    )
                );


            const currentRejected =
                Math.max(
                    0,
                    Math.floor(
                        directNumberV3(
                            rejectedInput.value
                        )
                    )
                );


            const currentHold =
                Math.max(
                    0,
                    Math.floor(
                        directNumberV3(
                            holdInput.value
                        )
                    )
                );


            if (
                currentOk === 0
                &&
                currentRejected === 0
                &&
                currentHold === 0
            ) {

                okInput.value =
                    String(
                        available
                    );
            }


            availableInput.dataset
                .autoOkAppliedV10 =
                "1";
        }


        for (
            const input
            of [
                okInput,
                rejectedInput,
                holdInput
            ]
        ) {

            if (
                input.dataset.lastQtyV10
                === undefined
            ) {

                input.dataset.lastQtyV10 =
                    String(
                        Math.max(
                            0,
                            Math.floor(
                                directNumberV3(
                                    input.value
                                )
                            )
                        )
                    );
            }
        }


        const ok =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        okInput.value
                    )
                )
            );


        const rejected =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        rejectedInput.value
                    )
                )
            );


        const hold =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        holdInput.value
                    )
                )
            );


        const buttons =
            Array.from(
                document.querySelectorAll(
                    ".oee-qty-btn-v8"
                )
            );


        for (const button of buttons) {

            const targetId =
                String(
                    button.dataset.qtyTargetV8
                    || ""
                );


            const delta =
                Number(
                    button.dataset.qtyDeltaV8
                    || 0
                );


            const target =
                document.getElementById(
                    targetId
                );


            if (!target) {
                continue;
            }


            const current =
                Math.max(
                    0,
                    Math.floor(
                        directNumberV3(
                            target.value
                        )
                    )
                );


            if (delta < 0) {

                button.disabled =
                    current <= 0;

                continue;
            }


            if (
                targetId
                === "machine-oee-ok-qty-v1"
            ) {

                const maximumOk =
                    Math.max(
                        available
                        -
                        rejected
                        -
                        hold,
                        0
                    );


                button.disabled =
                    available > 0
                    &&
                    ok >= maximumOk;


                continue;
            }


            if (
                targetId
                === "machine-oee-rejected-qty-v1"
                ||
                targetId
                === "machine-oee-hold-qty-v1"
            ) {

                /*
                 * Reject/Hold is transferred from OK.
                 */
                button.disabled =
                    available > 0
                    &&
                    ok <= 0;
            }
        }


        if (
            typeof machineOeeUpdateReasonRowsV9
            === "function"
        ) {

            machineOeeUpdateReasonRowsV9();
        }
    }


    function directNormalizeQtyInputV8(
        input
    ) {

        if (!input) {
            return;
        }


        const available =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        document.getElementById(
                            "oee-direct-available-qty-v3"
                        )?.value
                    )
                )
            );


        const okInput =
            document.getElementById(
                "machine-oee-ok-qty-v1"
            );


        const rejectedInput =
            document.getElementById(
                "machine-oee-rejected-qty-v1"
            );


        const holdInput =
            document.getElementById(
                "machine-oee-hold-qty-v1"
            );


        if (
            !okInput
            ||
            !rejectedInput
            ||
            !holdInput
        ) {
            return;
        }


        const id =
            String(
                input.id
                || ""
            );


        const previous =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        input.dataset.lastQtyV10
                        ?? input.value
                    )
                )
            );


        let wanted =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        input.value
                    )
                )
            );


        const currentOk =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        okInput.value
                    )
                )
            );


        const currentRejected =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        rejectedInput.value
                    )
                )
            );


        const currentHold =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        holdInput.value
                    )
                )
            );


        /*
         * OK cannot overlap with Reject/Hold.
         */
        if (
            id
            === "machine-oee-ok-qty-v1"
        ) {

            if (available > 0) {

                const maxOk =
                    Math.max(
                        available
                        -
                        currentRejected
                        -
                        currentHold,
                        0
                    );


                wanted =
                    Math.min(
                        wanted,
                        maxOk
                    );
            }


            input.value =
                String(
                    wanted
                );
        }


        /*
         * Rejected/Hold Qty directly transfers
         * quantity from/to OK.
         */
        else if (
            id
            === "machine-oee-rejected-qty-v1"
            ||
            id
            === "machine-oee-hold-qty-v1"
        ) {

            const isRejected =
                id
                === "machine-oee-rejected-qty-v1";


            const otherOutcome =
                isRejected
                    ? currentHold
                    : currentRejected;


            if (available > 0) {

                wanted =
                    Math.min(
                        wanted,
                        Math.max(
                            available
                            -
                            otherOutcome,
                            0
                        )
                    );
            }


            let delta =
                wanted
                -
                previous;


            /*
             * Reject/Hold increase must come
             * from currently available OK Qty.
             */
            if (
                delta > 0
                &&
                delta > currentOk
            ) {

                delta =
                    currentOk;


                wanted =
                    previous
                    +
                    delta;
            }


            const newOk =
                Math.max(
                    currentOk
                    -
                    delta,
                    0
                );


            input.value =
                String(
                    wanted
                );


            okInput.value =
                String(
                    newOk
                );
        }


        /*
         * Save current balanced values as next baseline.
         */
        for (
            const field
            of [
                okInput,
                rejectedInput,
                holdInput
            ]
        ) {

            field.dataset.lastQtyV10 =
                String(
                    Math.max(
                        0,
                        Math.floor(
                            directNumberV3(
                                field.value
                            )
                        )
                    )
                );
        }


        directUpdateQtyUiV8();
    }


    function directAdjustQtyV8(
        targetId,
        delta
    ) {

        const input =
            document.getElementById(
                targetId
            );


        if (!input) {
            return;
        }


        const current =
            Math.max(
                0,
                Math.floor(
                    directNumberV3(
                        input.value
                    )
                )
            );


        input.dataset.lastQtyV10 =
            String(
                current
            );


        input.value =
            String(
                Math.max(
                    0,
                    current
                    +
                    Number(
                        delta
                        || 0
                    )
                )
            );


        directNormalizeQtyInputV8(
            input
        );


        input.dispatchEvent(
            new Event(
                "change",
                {
                    bubbles:true
                }
            )
        );
    }


    function directWireQtyCountersV8() {

        const buttons =
            Array.from(
                document.querySelectorAll(
                    ".oee-qty-btn-v8"
                )
            );


        for (const button of buttons) {

            if (
                button.dataset
                    .qtyWiredV8
                === "1"
            ) {

                continue;
            }


            button.dataset
                .qtyWiredV8 =
                "1";


            button.addEventListener(
                "click",
                function() {

                    directAdjustQtyV8(
                        button.dataset
                            .qtyTargetV8,

                        Number(
                            button.dataset
                                .qtyDeltaV8
                            || 0
                        )
                    );
                }
            );
        }


        for (
            const input
            of directQtyInputsV8()
        ) {

            if (
                input.dataset
                    .qtyWiredV8
                === "1"
            ) {

                continue;
            }


            input.dataset
                .qtyWiredV8 =
                "1";


            input.addEventListener(
                "input",
                function() {

                    directNormalizeQtyInputV8(
                        input
                    );
                }
            );


            input.addEventListener(
                "change",
                function() {

                    directNormalizeQtyInputV8(
                        input
                    );
                }
            );
        }


        directUpdateQtyUiV8();
    }



    /* ======================================================
       MACHINE_OEE_REASON_AND_ACTIVE_LOCK_V9
       ====================================================== */


    function machineOeeReasonOptionsV9(
        type
    ) {

        if (
            type
            === "hold"
        ) {

            return [
                "Awaiting QC decision",
                "Dimension borderline",
                "Fixture issue",
                "Program correction needed",
                "Customer clarification",
                "Rework decision pending",
                "Other"
            ];
        }


        return [
            "Dimensional oversize",
            "Dimensional undersize",
            "Surface finish NG",
            "Thread damage",
            "Concentricity NG",
            "Tool mark",
            "Material defect",
            "Setup error",
            "Other"
        ];
    }


    function machineOeeBuildReasonControlV9(
        type,
        slot,
        oldValue
    ) {

        if (!slot) {
            return;
        }


        const isHold =
            type
            === "hold";


        const selectId =
            isHold
                ? "machine-oee-hold-reason-v9"
                : "machine-oee-rejection-reason-v1";


        const otherId =
            isHold
                ? "machine-oee-hold-other-v9"
                : "machine-oee-rejection-other-v9";


        const placeholder =
            isHold
                ? "Select hold reason"
                : "Select rejection reason";


        const options =
            machineOeeReasonOptionsV9(
                type
            );


        slot.innerHTML =
            "";


        const select =
            document.createElement(
                "select"
            );


        select.id =
            selectId;


        select.className =
            "oee-reason-select-v9";


        const blank =
            document.createElement(
                "option"
            );


        blank.value =
            "";


        blank.textContent =
            placeholder;


        select.appendChild(
            blank
        );


        for (
            const value
            of options
        ) {

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                value;


            option.textContent =
                value;


            select.appendChild(
                option
            );
        }


        const other =
            document.createElement(
                "input"
            );


        other.id =
            otherId;


        other.type =
            "text";


        other.className =
            "oee-reason-other-v9";


        other.placeholder =
            isHold
                ? "Enter other hold reason"
                : "Enter other rejection reason";


        const previous =
            String(
                oldValue
                || ""
            ).trim();


        if (previous) {

            if (
                options.includes(
                    previous
                )
            ) {

                select.value =
                    previous;

            } else {

                select.value =
                    "Other";


                other.value =
                    previous;


                other.style.display =
                    "block";
            }
        }


        select.addEventListener(
            "change",
            function() {

                machineOeeToggleReasonOtherV9(
                    type
                );
            }
        );


        slot.appendChild(
            select
        );


        slot.appendChild(
            other
        );
    }


    function machineOeeEnsureReasonFieldsV9() {

        const host =
            document.getElementById(
                "oee-direct-qty-reasons-v9"
            );


        if (!host) {
            return false;
        }


        /*
         * Existing Rejection Reason field.
         * Move it below the Qty counters and
         * convert the old text input to dropdown.
         */
        const rejectionSlot =
            document.getElementById(
                "oee-direct-rejection-slot-v3"
            );


        if (rejectionSlot) {

            const rejectionField =
                rejectionSlot.closest(
                    ".oee-direct-field-v3"
                );


            if (rejectionField) {

                rejectionField.id =
                    "oee-direct-rejection-field-v9";


                rejectionField.classList.add(
                    "oee-direct-reason-field-v9"
                );


                const label =
                    rejectionField.querySelector(
                        "label"
                    );


                if (label) {

                    label.innerHTML =
                        '<i class="fa fa-times-circle" '
                        +
                        'aria-hidden="true"></i>'
                        +
                        ' Not OK Reason';
                }


                if (
                    rejectionField.parentElement
                    !== host
                ) {

                    host.appendChild(
                        rejectionField
                    );
                }
            }


            const existing =
                document.getElementById(
                    "machine-oee-rejection-reason-v1"
                );


            if (
                !existing
                ||
                existing.tagName
                    .toLowerCase()
                    !== "select"
            ) {

                const oldValue =
                    String(
                        existing?.value
                        || ""
                    ).trim();


                machineOeeBuildReasonControlV9(
                    "rejection",
                    rejectionSlot,
                    oldValue
                );
            }
        }


        /*
         * Hold Reason field.
         */
        let holdField =
            document.getElementById(
                "oee-direct-hold-field-v9"
            );


        if (!holdField) {

            holdField =
                document.createElement(
                    "div"
                );


            holdField.id =
                "oee-direct-hold-field-v9";


            holdField.className =
                "oee-direct-field-v3 "
                +
                "oee-direct-reason-field-v9";


            holdField.innerHTML = `

                <label>

                    <i
                        class="fa fa-pause-circle"
                        aria-hidden="true"
                    ></i>

                    Hold Reason

                </label>


                <div
                    id="oee-direct-hold-slot-v9"
                ></div>
            `;


            host.appendChild(
                holdField
            );


            machineOeeBuildReasonControlV9(
                "hold",
                document.getElementById(
                    "oee-direct-hold-slot-v9"
                ),
                ""
            );
        }


        /*
         * Completion Remark remains full width
         * in the completion section.
         */
        const remarkSlot =
            document.getElementById(
                "oee-direct-remark-slot-v3"
            );


        const remarkField =
            remarkSlot?.closest(
                ".oee-direct-field-v3"
            );


        if (remarkField) {

            remarkField.style.gridColumn =
                "1 / -1";
        }


        return true;
    }


    function machineOeeToggleReasonOtherV9(
        type
    ) {

        const isHold =
            type
            === "hold";


        const select =
            document.getElementById(
                isHold
                    ? "machine-oee-hold-reason-v9"
                    : "machine-oee-rejection-reason-v1"
            );


        const other =
            document.getElementById(
                isHold
                    ? "machine-oee-hold-other-v9"
                    : "machine-oee-rejection-other-v9"
            );


        if (
            !select
            ||
            !other
        ) {
            return;
        }


        const show =
            select.value
            === "Other";


        other.style.display =
            show
                ? "block"
                : "none";


        if (!show) {

            other.value =
                "";
        }
    }


    function machineOeeReasonValueV9(
        type
    ) {

        const isHold =
            type
            === "hold";


        const select =
            document.getElementById(
                isHold
                    ? "machine-oee-hold-reason-v9"
                    : "machine-oee-rejection-reason-v1"
            );


        if (!select) {
            return "";
        }


        const selected =
            String(
                select.value
                || ""
            ).trim();


        if (
            selected
            !== "Other"
        ) {

            return selected;
        }


        const other =
            document.getElementById(
                isHold
                    ? "machine-oee-hold-other-v9"
                    : "machine-oee-rejection-other-v9"
            );


        return String(
            other?.value
            || ""
        ).trim();
    }


    function machineOeeResetReasonV9(
        type
    ) {

        const isHold =
            type
            === "hold";


        const select =
            document.getElementById(
                isHold
                    ? "machine-oee-hold-reason-v9"
                    : "machine-oee-rejection-reason-v1"
            );


        const other =
            document.getElementById(
                isHold
                    ? "machine-oee-hold-other-v9"
                    : "machine-oee-rejection-other-v9"
            );


        if (select) {

            select.value =
                "";
        }


        if (other) {

            other.value =
                "";


            other.style.display =
                "none";
        }
    }


    function machineOeeUpdateReasonRowsV9() {

        if (
            !machineOeeEnsureReasonFieldsV9()
        ) {
            return;
        }


        const rejected =
            Math.max(
                0,
                Number(
                    document.getElementById(
                        "machine-oee-rejected-qty-v1"
                    )?.value
                    || 0
                )
            );


        const hold =
            Math.max(
                0,
                Number(
                    document.getElementById(
                        "machine-oee-hold-qty-v1"
                    )?.value
                    || 0
                )
            );


        const rejectionField =
            document.getElementById(
                "oee-direct-rejection-field-v9"
            );


        const holdField =
            document.getElementById(
                "oee-direct-hold-field-v9"
            );


        const host =
            document.getElementById(
                "oee-direct-qty-reasons-v9"
            );


        if (rejectionField) {

            rejectionField.style.display =
                rejected > 0
                    ? ""
                    : "none";
        }


        if (holdField) {

            holdField.style.display =
                hold > 0
                    ? ""
                    : "none";
        }


        if (
            rejected <= 0
        ) {

            machineOeeResetReasonV9(
                "rejection"
            );
        }


        if (
            hold <= 0
        ) {

            machineOeeResetReasonV9(
                "hold"
            );
        }


        if (host) {

            const visibleCount =
                (
                    rejected > 0
                        ? 1
                        : 0
                )
                +
                (
                    hold > 0
                        ? 1
                        : 0
                );


            host.style.display =
                visibleCount > 0
                    ? "grid"
                    : "none";


            host.classList.toggle(
                "one",
                visibleCount
                === 1
            );
        }
    }


    /*
     * V8 already owns Qty synchronization.
     * Extend it without changing V8 quantity logic.
     */
    const machineOeeQtyUpdateBaseV9 =
        directUpdateQtyUiV8;


    directUpdateQtyUiV8 =
        function directUpdateQtyUiReasonV9() {

            machineOeeQtyUpdateBaseV9();


            machineOeeUpdateReasonRowsV9();
        };


    /*
     * Make sure reason controls are also created
     * when an existing RUNNING JC is resumed.
     */
    window.setTimeout(
        machineOeeUpdateReasonRowsV9,
        350
    );


    window.setTimeout(
        machineOeeUpdateReasonRowsV9,
        800
    );


    /* ------------------------------------------------------
       CLEAR CURRENT MACHINE LOCK MESSAGE
       ------------------------------------------------------ */

    function machineOeeApplyActiveMachineLockV9() {

        const run =
            machineOeePendingRunV1
            ||
            machineOeeActiveRunV1;


        const input =
            document.getElementById(
                "machine-oee-jc-input"
            );


        const button =
            document.getElementById(
                "machine-oee-fetch-btn"
            );


        const resultHost =
            document.getElementById(
                "machine-oee-jc-result-v1"
            );


        if (!run) {

            if (
                input
                &&
                input.dataset
                    .machineLockedV9
            ) {

                if (
                    String(
                        input.value
                        || ""
                    )
                    ===
                    String(
                        input.dataset
                            .machineLockedV9
                        || ""
                    )
                ) {

                    input.value =
                        "";
                }


                delete input.dataset
                    .machineLockedV9;
            }


            if (
                button
                &&
                button.dataset
                    .machineLockedV9
                === "1"
            ) {

                button.innerHTML =
                    '<i class="fa fa-search" '
                    +
                    'aria-hidden="true"></i>'
                    +
                    ' Fetch';


                delete button.dataset
                    .machineLockedV9;
            }


            return;
        }


        const jcNo =
            String(
                run.job_card_no
                || ""
            ).trim();


        if (input) {

            input.value =
                jcNo;


            input.disabled =
                true;


            input.dataset
                .machineLockedV9 =
                jcNo;


            input.title =
                "Complete the current machine job "
                +
                "before entering another Job Card.";
        }


        if (button) {

            button.disabled =
                true;


            button.style.cursor =
                "not-allowed";


            button.style.opacity =
                ".7";


            button.dataset
                .machineLockedV9 =
                "1";


            button.innerHTML =
                '<i class="fa fa-lock" '
                +
                'aria-hidden="true"></i>'
                +
                ' Current Job Running';
        }


        if (!resultHost) {
            return;
        }


        const box =
            resultHost.querySelector(
                ".pending-machine-v1"
            );


        if (!box) {
            return;
        }


        box.classList.add(
            "machine-active-lock-v9"
        );


        const heading =
            box.querySelector(
                "h3"
            );


        if (
            heading
            &&
            heading.textContent.trim()
            !== "Current Machine Job"
        ) {

            heading.innerHTML =
                '<i class="fa fa-lock" '
                +
                'aria-hidden="true"></i>'
                +
                ' Current Machine Job';
        }


        const paragraph =
            box.querySelector(
                "p"
            );


        const context =
            window.NMTG_MACHINE_OEE_CONTEXT
            || {};


        const machineNo =
            String(
                context.machine_no
                || "This machine"
            );


        const message =
            machineNo
            +
            " already has a RUNNING Job Card. "
            +
            "Complete the current operation before "
            +
            "entering the next Job Card.";


        if (
            paragraph
            &&
            paragraph.textContent
                .replace(/\s+/g, " ")
                .trim()
            !== message
        ) {

            paragraph.textContent =
                message;
        }


        const labels =
            Array.from(
                box.querySelectorAll(
                    ".jc-info-v1 span"
                )
            );


        for (
            const label
            of labels
        ) {

            if (
                label.textContent
                    .replace(/\s+/g, " ")
                    .trim()
                === "Previous Shift"
            ) {

                label.textContent =
                    "Shift";
            }
        }
    }


    const machineOeeLockHostV9 =
        document.getElementById(
            "machine-oee-jc-result-v1"
        );


    if (machineOeeLockHostV9) {

        const machineOeeLockObserverV9 =
            new MutationObserver(
                function() {

                    window.setTimeout(
                        machineOeeApplyActiveMachineLockV9,
                        0
                    );
                }
            );


        machineOeeLockObserverV9.observe(
            machineOeeLockHostV9,
            {
                childList:true,
                subtree:true
            }
        );
    }


    window.setTimeout(
        machineOeeApplyActiveMachineLockV9,
        250
    );


    window.setTimeout(
        machineOeeApplyActiveMachineLockV9,
        700
    );


    /* ------------------------------------------------------
       LOSS COLLAPSE
       ------------------------------------------------------ */

    function directToggleLossV3() {

        const grid =
            document.getElementById(
                "oee-direct-loss-grid-v3"
            );


        const button =
            document.getElementById(
                "oee-direct-loss-toggle-v3"
            );


        if (
            !grid
            ||
            !button
        ) {

            return;
        }


        const collapsed =
            grid.classList.toggle(
                "collapsed"
            );


        button.setAttribute(
            "aria-expanded",
            collapsed
                ? "false"
                : "true"
        );


        const chevron =
            button.querySelector(
                ".oee-loss-title-chevron-v62"
            );


        if (chevron) {

            chevron.classList.toggle(
                "fa-chevron-down",
                collapsed
            );


            chevron.classList.toggle(
                "fa-chevron-up",
                !collapsed
            );
        }
    }


    /* ------------------------------------------------------
       FA ICON CLEANUP FOR EXISTING PAGE
       ------------------------------------------------------ */

    function directIconCleanupV3() {

        const elements =
            Array.from(
                document.querySelectorAll(
                    "a, button"
                )
            );


        for (const element of elements) {

            const text =
                String(
                    element.textContent
                    || ""
                )
                .replace(/\s+/g, " ")
                .trim();


            if (
                text.toLowerCase()
                .includes(
                    "back to machine selection"
                )
            ) {

                element.innerHTML = `

                    <i
                        class="fa fa-arrow-left"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Back to Machine Selection
                    </span>
                `;
            }
        }
    }


    /* ------------------------------------------------------
       INIT
       ------------------------------------------------------ */

    let directInitApiBusyV3 =
        false;


    async function directInitV3() {

        const workspace =
            directBuildV3();


        if (!workspace) {
            return;
        }


        /*
         * Current JC is already running.
         * Pre-start Operator Action is no longer relevant.
         */
        const oldOperatorAction =
            document.getElementById(
                "machine-oee-smart-action-v1"
            );


        if (oldOperatorAction) {

            oldOperatorAction.style.display =
                "none";
        }


        directMoveInputsV3();

        directWireQtyCountersV8();

        directUpdateQtyUiV8();

        directHideOldUiV3();

        directIconCleanupV3();


        const save =
            document.getElementById(
                "oee-direct-save-v3"
            );


        if (
            save
            &&
            save.dataset.wiredV3
            !== "1"
        ) {

            save.dataset.wiredV3 =
                "1";


            save.addEventListener(
                "click",
                directSaveAllV3
            );
        }


        const toggle =
            document.getElementById(
                "oee-direct-loss-toggle-v3"
            );


        if (
            toggle
            &&
            toggle.dataset.wiredV3
            !== "1"
        ) {

            toggle.dataset.wiredV3 =
                "1";


            toggle.addEventListener(
                "click",
                directToggleLossV3
            );
        }


        /*
         * PERFORMANCE_FIX_V1
         *
         * directInitV3 is intentionally allowed to run
         * repeatedly for DOM/UI synchronization.
         *
         * However, API initialization must never run
         * concurrently. Multiple MutationObserver/timer
         * triggers previously caused duplicate
         * loss-master, losses and context requests.
         */
        if (directInitApiBusyV3) {
            return;
        }


        directInitApiBusyV3 =
            true;


        try {

            await directLoadContextV3();

            await directLoadLossesV3();

        } finally {

            directInitApiBusyV3 =
                false;
        }
    }


    /* MACHINE_OEE_DIRECT_RUN_BRIDGE_V38 */

    /*
     * Do not rely only on MutationObserver timing.
     *
     * A newly persisted RUNNING JC creates the hidden
     * production source inputs first. Direct Entry must
     * then open immediately and move those controls into
     * the visible Qty / Time / Loss workspace.
     */
    if (
        typeof machineOeeRenderRunningRunV1
        === "function"
    ) {

        const directRunningBaseV38 =
            machineOeeRenderRunningRunV1;


        machineOeeRenderRunningRunV1 =
            function(run) {

                const result =
                    directRunningBaseV38(
                        run
                    );


                window.setTimeout(
                    directInitV3,
                    0
                );


                window.setTimeout(
                    directInitV3,
                    100
                );


                return result;
            };
    }


    /*
     * Same protection for a persisted RUNNING JC
     * restored after browser refresh.
     */
    if (
        typeof machineOeeCheckPendingV1
        === "function"
    ) {

        const directPendingBaseV38 =
            machineOeeCheckPendingV1;


        machineOeeCheckPendingV1 =
            async function() {

                const result =
                    await directPendingBaseV38();


                if (
                    machineOeePendingRunV1
                    &&
                    machineOeePendingRunV1.run_id
                ) {

                    window.setTimeout(
                        directInitV3,
                        0
                    );


                    window.setTimeout(
                        directInitV3,
                        100
                    );
                }


                return result;
            };
    }


    /* ------------------------------------------------------
       DYNAMIC RUN RENDER SUPPORT
       ------------------------------------------------------ */

    const observer =
        new MutationObserver(
            function() {

                window.clearTimeout(
                    directTimerV3
                );


                directTimerV3 =
                    window.setTimeout(
                        directInitV3,
                        100
                    );
            }
        );


    observer.observe(
        document.body,
        {
            childList: true,
            subtree: true
        }
    );


    window.setTimeout(
        directInitV3,
        120
    );


    window.setTimeout(
        directInitV3,
        600
    );


     window.setTimeout(
        directInitV3,
        1400
    );


    window.machineOeeBuildReasonControlV9 =
        machineOeeBuildReasonControlV9;

    window.machineOeeReasonValueV9 =
        machineOeeReasonValueV9;

    window.machineOeeResetReasonV9 =
        machineOeeResetReasonV9;


})();


/* ==========================================================
   MACHINE_OEE_DIRECT_ENTRY_V3_END
   ========================================================== */















/* MACHINE_OEE_MACHINE_LEVEL_LOSSES_V13 */

(function () {

    let machineLossTimerV13 =
        null;


    let machineLossStateV13 =
        "";


    function machineLossHasRunV13() {

        try {

            return Boolean(
                machineOeeActiveRunV1
                ||
                machineOeePendingRunV1
            );

        } catch (_) {

            return false;
        }
    }


    function machineLossShiftV13() {

        return String(
            document.getElementById(
                "machine-oee-shift-v1"
            )?.value
            || ""
        ).trim();
    }


    function machineLossHostV13() {

        return document.getElementById(
            "machine-oee-machine-loss-only-v13"
        );
    }


    function machineLossRemoveHostV13() {

        const host =
            machineLossHostV13();


        if (host) {

            host.remove();
        }
    }


    function machineLossBuildHostV13() {

        if (
            machineLossHasRunV13()
        ) {

            machineLossRemoveHostV13();

            return null;
        }


        let host =
            machineLossHostV13();


        if (host) {

            return host;
        }


        const jcInput =
            document.getElementById(
                "machine-oee-jc-input"
            );


        if (!jcInput) {

            return null;
        }


        const jcCard =
            jcInput.closest(
                ".card"
            );


        if (!jcCard) {

            return null;
        }


        host =
            document.createElement(
                "section"
            );


        host.id =
            "machine-oee-machine-loss-only-v13";


        host.className =
            "oee-machine-loss-only-v13";


        host.innerHTML = `

            <div
                class="oee-direct-section-head-v3"
            >

                <button
                    type="button"
                    id="machine-oee-loss-toggle-v13"
                    class="
                        oee-direct-section-title-v3
                        oee-loss-title-toggle-v62
                    "
                    aria-expanded="true"
                >

                    <i
                        class="fa fa-clock-o"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Losses
                    </span>

                    <i
                        class="
                            fa
                            fa-chevron-up
                            oee-loss-title-chevron-v62
                        "
                        aria-hidden="true"
                    ></i>

                </button>

            </div>


            <div
                id="oee-direct-loss-grid-v3"
            ></div>


            <div
                class="oee-direct-actions-v3"
            >

                <div
                    id="machine-oee-machine-loss-feedback-v13"
                    class="oee-direct-feedback-v3"
                ></div>


                <button
                    type="button"
                    id="machine-oee-machine-loss-save-v13"
                    class="
                        oee-direct-button-v3
                        oee-direct-save-v3
                    "
                >

                    <i
                        class="fa fa-floppy-o"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Save Losses
                    </span>

                </button>

            </div>
        `;


        jcCard.insertAdjacentElement(
            "afterend",
            host
        );


        const toggle =
            document.getElementById(
                "machine-oee-loss-toggle-v13"
            );


        if (toggle) {

            toggle.addEventListener(
                "click",
                function() {

                    const grid =
                        document.getElementById(
                            "oee-direct-loss-grid-v3"
                        );


                    if (!grid) {
                        return;
                    }


                    const collapsed =
                        grid.classList.toggle(
                            "collapsed"
                        );


                    toggle.setAttribute(
                        "aria-expanded",
                        collapsed
                            ? "false"
                            : "true"
                    );


                    const chevron =
                        toggle.querySelector(
                            ".oee-loss-title-chevron-v62"
                        );


                    if (chevron) {

                        chevron.classList.toggle(
                            "fa-chevron-down",
                            collapsed
                        );

                        chevron.classList.toggle(
                            "fa-chevron-up",
                            !collapsed
                        );
                    }
                }
            );
        }


        const saveButton =
            document.getElementById(
                "machine-oee-machine-loss-save-v13"
            );


        if (saveButton) {

            saveButton.addEventListener(
                "click",
                machineLossSaveV13
            );
        }


        return host;
    }


    async function machineLossLoadV13() {

        const host =
            machineLossBuildHostV13();


        if (!host) {
            return;
        }


        const feedback =
            document.getElementById(
                "machine-oee-machine-loss-feedback-v13"
            );


        if (
            typeof window
                .machineOeeDirectLoadMachineLossesV13
            !== "function"
        ) {

            if (feedback) {

                feedback.style.color =
                    "#b42318";


                feedback.textContent =
                    "Loss module is not ready.";
            }

            return;
        }


        if (feedback) {

            feedback.style.color =
                "#6b7280";


            feedback.textContent =
                machineLossShiftV13()
                ? "Loading..."
                : "Select Shift to save losses.";
        }


        try {

            await window
                .machineOeeDirectLoadMachineLossesV13();


            if (feedback) {

                feedback.style.color =
                    "#6b7280";


                feedback.textContent =
                    machineLossShiftV13()
                    ?
                    "Machine-level loss entry ready."
                    :
                    "Select Shift to save losses.";
            }

        } catch (error) {

            if (feedback) {

                feedback.style.color =
                    "#b42318";


                feedback.textContent =
                    error.message
                    || "Unable to load machine losses.";
            }
        }
    }


    async function machineLossSaveV13() {

        const button =
            document.getElementById(
                "machine-oee-machine-loss-save-v13"
            );


        const feedback =
            document.getElementById(
                "machine-oee-machine-loss-feedback-v13"
            );


        if (!machineLossShiftV13()) {

            if (feedback) {

                feedback.style.color =
                    "#b42318";


                feedback.textContent =
                    "Please select Shift first.";
            }

            return;
        }


        if (
            typeof window
                .machineOeeDirectSaveMachineLossesV13
            !== "function"
        ) {

            return;
        }


        if (button) {

            button.disabled =
                true;
        }


        if (feedback) {

            feedback.style.color =
                "#6b7280";


            feedback.textContent =
                "Saving...";
        }


        try {

            /*
             * Reset before each no-JC / Activity save so an old
             * Tool Room count cannot leak into a later save message.
             */
            window.machineOeeLastToolSaveCountV6 =
                0;


            await window
                .machineOeeDirectSaveMachineLossesV13();


            const toolCountV6 =
                Number(
                    window.machineOeeLastToolSaveCountV6
                    || 0
                );


            const saveMessageV6 =
                toolCountV6 > 0
                ?
                (
                    "Machine losses and "
                    + toolCountV6
                    + " Tool Position "
                    + (
                        toolCountV6 === 1
                        ? "record"
                        : "records"
                    )
                    + " saved successfully."
                )
                :
                "Machine losses saved successfully.";


            /* OEE_NO_JC_LOSS_TOAST_V52 */

            if (
                typeof showToast
                === "function"
            ) {

                showToast(
                    saveMessageV6,
                    "success"
                );
            }


            if (feedback) {

                feedback.style.color =
                    "#16833a";

                feedback.textContent =
                    saveMessageV6;
            }


            /*
             * MACHINE_SHIFT_CAPACITY_ACTIVITY_UI_V94
             *
             * Tool Room / Development has now been
             * completed in the database.
             *
             * Refresh the same Shift Used / Remaining
             * header used by Production.
             */
            if (
                typeof window
                    .machineOeeRefreshShiftCapacityV71
                === "function"
            ) {

                try {

                    await window
                        .machineOeeRefreshShiftCapacityV71();

                } catch (_) {

                    /*
                     * Display refresh must never make
                     * a successfully saved activity fail.
                     */
                }
            }


        } catch (error) {

            if (feedback) {

                feedback.style.color =
                    "#b42318";


                feedback.textContent =
                    error.message
                    || "Unable to save machine losses.";
            }


        } finally {

            if (button) {

                button.disabled =
                    false;
            }
        }
    }


    function machineLossSyncV13() {

        const hasRun =
            machineLossHasRunV13();


        const state =
            hasRun
            ? "RUN"
            : "IDLE";


        if (hasRun) {

            machineLossRemoveHostV13();


            machineLossStateV13 =
                state;


            return;
        }


        const hadHost =
            Boolean(
                machineLossHostV13()
            );


        const host =
            machineLossBuildHostV13();


        if (
            host
            &&
            (
                !hadHost
                ||
                machineLossStateV13
                    !== state
            )
        ) {

            window.setTimeout(
                machineLossLoadV13,
                30
            );
        }


        machineLossStateV13 =
            state;
    }


    const shiftSelect =
        document.getElementById(
            "machine-oee-shift-v1"
        );


    if (shiftSelect) {

        shiftSelect.addEventListener(
            "change",
            function() {

                if (
                    typeof window
                        .machineOeeDirectResetMachineLossesV13
                    === "function"
                ) {

                    window
                        .machineOeeDirectResetMachineLossesV13();
                }


                if (
                    machineLossHasRunV13()
                ) {

                    /*
                     * During a RUN, the existing Direct V3
                     * workspace owns the visible Loss section.
                     *
                     * Its patched loader uses run.shift_name,
                     * so the active JC stays tied to its
                     * original Shift.
                     */
                    return;
                }


                window.setTimeout(
                    machineLossLoadV13,
                    30
                );
            }
        );
    }


    const observer =
        new MutationObserver(
            function() {

                window.clearTimeout(
                    machineLossTimerV13
                );


                machineLossTimerV13 =
                    window.setTimeout(
                        machineLossSyncV13,
                        80
                    );
            }
        );


    observer.observe(
        document.body,
        {
            childList: true,
            subtree: true
        }
    );


    window.setTimeout(
        machineLossSyncV13,
        160
    );


    window.setTimeout(
        machineLossSyncV13,
        700
    );

})();

/* MACHINE_OEE_MACHINE_LEVEL_LOSSES_V13_END */



/* MACHINE_OEE_HMS_CUSTOM_V20 */

(function () {

    function machineOeeHmsPrefixValidV20(
        digits
    ) {

        const value =
            String(
                digits || ""
            );


        if (!value) {
            return true;
        }


        if (
            value.length >= 1
            && Number(value[0]) > 2
        ) {
            return false;
        }


        if (
            value.length >= 2
            && Number(
                value.slice(0, 2)
            ) > 23
        ) {
            return false;
        }


        if (
            value.length >= 3
            && Number(value[2]) > 5
        ) {
            return false;
        }


        if (
            value.length >= 5
            && Number(value[4]) > 5
        ) {
            return false;
        }


        return true;
    }


    function machineOeeHmsFormatDigitsV20(
        digits
    ) {

        const value =
            String(
                digits || ""
            )
            .replace(/\D/g, "")
            .slice(0, 6);


        if (value.length === 0) {
            return "";
        }


        if (value.length < 2) {
            return value;
        }


        if (value.length === 2) {

            return (
                value
                + ":"
            );
        }


        if (value.length < 4) {

            return (
                value.slice(0, 2)
                + ":"
                + value.slice(2)
            );
        }


        if (value.length === 4) {

            return (
                value.slice(0, 2)
                + ":"
                + value.slice(2, 4)
                + ":"
            );
        }


        return (
            value.slice(0, 2)
            + ":"
            + value.slice(2, 4)
            + ":"
            + value.slice(4, 6)
        );
    }


    function machineOeeHmsDigitsV20(
        value
    ) {

        return String(
            value || ""
        )
        .replace(/\D/g, "")
        .slice(0, 6);
    }


    function machineOeeMoveCaretEndV20(
        input
    ) {

        window.requestAnimationFrame(
            function () {

                try {

                    const end =
                        input.value.length;


                    input.setSelectionRange(
                        end,
                        end
                    );

                } catch (_) {

                    return;
                }
            }
        );
    }


    function machineOeeWireHmsV20(
        input
    ) {

        if (!input) {
            return;
        }


        if (
            input.dataset.hmsV20Wired
            === "1"
        ) {
            return;
        }


        input.dataset.hmsV20Wired =
            "1";


        const existingValue =
            String(
                input.value || ""
            ).trim();


        /*
         * Change native time control into normal text
         * so browser --:--:-- is removed.
         */
        input.type =
            "text";


        input.placeholder =
            "HH:MM:SS";


        input.maxLength =
            8;


        input.setAttribute(
            "inputmode",
            "numeric"
        );


        input.setAttribute(
            "autocomplete",
            "off"
        );


        input.setAttribute(
            "spellcheck",
            "false"
        );


        if (existingValue) {

            const normalized =
                machineOeeNormalizeHmsV18(
                    existingValue
                );


            input.value =
                normalized;
        }


        input.dataset.hmsV20Digits =
            machineOeeHmsDigitsV20(
                input.value
            );


        /*
         * Main typing behavior:
         *
         * 08 -> 08:
         * 0830 -> 08:30:
         * 083015 -> 08:30:15
         */
        input.addEventListener(
            "input",
            function () {

                const digits =
                    machineOeeHmsDigitsV20(
                        input.value
                    );


                if (
                    !machineOeeHmsPrefixValidV20(
                        digits
                    )
                ) {

                    input.value =
                        machineOeeHmsFormatDigitsV20(
                            input.dataset.hmsV20Digits
                            || ""
                        );


                    machineOeeMoveCaretEndV20(
                        input
                    );


                    return;
                }


                input.dataset.hmsV20Digits =
                    digits;


                input.value =
                    machineOeeHmsFormatDigitsV20(
                        digits
                    );


                machineOeeMoveCaretEndV20(
                    input
                );
            }
        );


        /*
         * Backspace from an empty MM or SS section
         * moves naturally into the previous section.
         */
        input.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key !== "Backspace"
                    ||
                    input.selectionStart
                        !== input.selectionEnd
                ) {
                    return;
                }


                const caret =
                    Number(
                        input.selectionStart
                        || 0
                    );


                if (
                    caret !== 3
                    &&
                    caret !== 6
                ) {
                    return;
                }


                if (
                    input.value[
                        caret - 1
                    ] !== ":"
                ) {
                    return;
                }


                event.preventDefault();


                let digits =
                    machineOeeHmsDigitsV20(
                        input.value
                    );


                const digitIndex =
                    caret === 3
                    ? 1
                    : 3;


                digits =
                    digits.slice(
                        0,
                        digitIndex
                    )
                    +
                    digits.slice(
                        digitIndex + 1
                    );


                input.dataset.hmsV20Digits =
                    digits;


                input.value =
                    machineOeeHmsFormatDigitsV20(
                        digits
                    );


                machineOeeMoveCaretEndV20(
                    input
                );
            }
        );


        const normalizeComplete =
            function () {

                const digits =
                    machineOeeHmsDigitsV20(
                        input.value
                    );


                if (!digits) {
                    return;
                }


                if (
                    digits.length !== 6
                    ||
                    !machineOeeHmsPrefixValidV20(
                        digits
                    )
                ) {
                    return;
                }


                input.value =
                    machineOeeNormalizeHmsV18(
                        machineOeeHmsFormatDigitsV20(
                            digits
                        )
                    );


                input.dataset.hmsV20Digits =
                    digits;
            };


        input.addEventListener(
            "change",
            normalizeComplete
        );


        input.addEventListener(
            "blur",
            normalizeComplete
        );
    }


    function machineOeeApplyHmsV20(
        root
    ) {

        const inputs =
            [];


        if (
            root
            &&
            root.matches
            &&
            root.matches(
                'input[type="time"]'
            )
        ) {

            inputs.push(
                root
            );
        }


        if (
            root
            &&
            root.querySelectorAll
        ) {

            inputs.push(
                ...root.querySelectorAll(
                    'input[type="time"]'
                )
            );
        }


        for (
            const input
            of inputs
        ) {

            machineOeeWireHmsV20(
                input
            );
        }
    }


    /*
     * Existing time fields.
     */
    machineOeeApplyHmsV20(
        document
    );


    document.addEventListener(
        "DOMContentLoaded",
        function () {

            machineOeeApplyHmsV20(
                document
            );
        }
    );


    /*
     * Time fields created later by the OEE UI,
     * including the machine loss Start/End fields.
     */
    const observer =
        new MutationObserver(
            function (
                mutations
            ) {

                for (
                    const mutation
                    of mutations
                ) {

                    for (
                        const node
                        of mutation.addedNodes
                    ) {

                        if (
                            node
                            &&
                            node.nodeType === 1
                        ) {

                            machineOeeApplyHmsV20(
                                node
                            );
                        }
                    }
                }
            }
        );


    observer.observe(
        document.documentElement,
        {
            childList: true,
            subtree: true
        }
    );

})();



/* MACHINE_OEE_JC_FETCH_MODE_LOCK_V26 */

(function () {

    let machineOeeModeMessageShownV26 =
        false;


    function machineOeeNoJcStartV26() {

        return document.getElementById(
            "oee-loss-start-v16"
        );
    }


    function machineOeeNoJcEndV26() {

        return document.getElementById(
            "oee-loss-stop-v16"
        );
    }


    function machineOeeJcInputV26() {

        return document.getElementById(
            "machine-oee-jc-input"
        );
    }


    function machineOeeFetchButtonV26() {

        return document.getElementById(
            "machine-oee-fetch-btn"
        );
    }


    function machineOeeHasNoJcTimeV26() {

        const start =
            String(
                machineOeeNoJcStartV26()
                    ?.value
                || ""
            ).trim();


        const end =
            String(
                machineOeeNoJcEndV26()
                    ?.value
                || ""
            ).trim();


        return Boolean(
            start
            ||
            end
        );
    }


    function machineOeeHasJcModeV26() {

        const jcInput =
            machineOeeJcInputV26();


        const entered =
            String(
                jcInput?.value
                || ""
            ).trim();


        const active =
            Boolean(
                machineOeeActiveRunV1
                ?.run_id
            );


        const pending =
            Boolean(
                machineOeePendingRunV1
                ?.run_id
            );


        const fetched =
            Boolean(
                machineOeeCurrentFetchedJcV1
            );


        return Boolean(
            entered
            ||
            fetched
            ||
            active
            ||
            pending
        );
    }


    function machineOeeSetLossTimeDisabledV26(
        disabled
    ) {

        const inputs = [
            machineOeeNoJcStartV26(),
            machineOeeNoJcEndV26()
        ];


        for (const input of inputs) {

            if (!input) {
                continue;
            }


            input.disabled =
                Boolean(
                    disabled
                );


            input.style.opacity =
                disabled
                ? ".55"
                : "1";


            input.style.cursor =
                disabled
                ? "not-allowed"
                : "";
        }
    }


    function machineOeeSetJcDisabledV26(
        disabled
    ) {

        const input =
            machineOeeJcInputV26();


        const button =
            machineOeeFetchButtonV26();


        /*
         * A RUNNING/PENDING JC already has its own
         * existing machine lock. Do not override it.
         */
        const machineLocked =
            Boolean(
                machineOeeActiveRunV1
                    ?.run_id
                ||
                machineOeePendingRunV1
                    ?.run_id
            );


        const finalDisabled =
            Boolean(
                disabled
                ||
                machineLocked
            );


        if (input) {

            input.disabled =
                finalDisabled;


            input.style.opacity =
                finalDisabled
                ? ".65"
                : "1";
        }


        if (button) {

            button.disabled =
                finalDisabled;


            button.style.opacity =
                finalDisabled
                ? ".55"
                : "1";


            button.style.cursor =
                finalDisabled
                ? "not-allowed"
                : "pointer";
        }
    }


    function machineOeeApplyEntryModeV26() {

        const hasNoJcTime =
            machineOeeHasNoJcTimeV26();


        const hasJcMode =
            machineOeeHasJcModeV26();


        /*
         * RULE 1:
         * JC selected / typed / running
         * -> no-JC Start/End unavailable.
         */
        if (hasJcMode) {

            machineOeeSetLossTimeDisabledV26(
                true
            );


            machineOeeSetJcDisabledV26(
                false
            );


            return;
        }


        /*
         * RULE 2:
         * No-JC Start/End entered
         * -> JC entry unavailable.
         */
        if (hasNoJcTime) {

            machineOeeSetLossTimeDisabledV26(
                false
            );


            machineOeeSetJcDisabledV26(
                true
            );


            return;
        }


        /*
         * Neither mode started.
         * Operator may choose either path.
         */
        machineOeeSetLossTimeDisabledV26(
            false
        );


        machineOeeSetJcDisabledV26(
            false
        );
    }


    /* -----------------------------------------------------
     * FEATURE 1:
     * FIX FETCH BUTTON USING OLD FUNCTION REFERENCE
     * ----------------------------------------------------- */

    const fetchButton =
        machineOeeFetchButtonV26();


    if (fetchButton) {

        /*
         * Original listener was registered before
         * machineOeeFetchJcV1 was enhanced.
         *
         * Remove that captured old function.
         */
        if (
            typeof machineOeeFetchJcBaseStartV1
            === "function"
        ) {

            fetchButton.removeEventListener(
                "click",
                machineOeeFetchJcBaseStartV1
            );
        }


        const latestFetchHandlerV26 =
            async function(event) {

                event?.preventDefault();


                if (
                    machineOeeHasNoJcTimeV26()
                ) {

                    return;
                }


                await machineOeeFetchJcV1();


                /*
                 * Apply immediately after fetch so JC
                 * details/start controls appear without
                 * requiring a page refresh.
                 */
                machineOeeApplyEntryModeV26();
            };


        fetchButton.addEventListener(
            "click",
            latestFetchHandlerV26
        );
    }


    /* -----------------------------------------------------
     * FEATURE 2:
     * JC vs NO-JC TIME EXCLUSIVE ENTRY
     * ----------------------------------------------------- */

    const jcInput =
        machineOeeJcInputV26();


    if (jcInput) {

        jcInput.addEventListener(
            "input",
            function() {

                /*
                 * If operator clears a JC before starting it,
                 * release fetched-JC mode as well.
                 */
                if (
                    !String(
                        jcInput.value
                        || ""
                    ).trim()
                    &&
                    !machineOeeActiveRunV1
                        ?.run_id
                    &&
                    !machineOeePendingRunV1
                        ?.run_id
                ) {

                    machineOeeCurrentFetchedJcV1 =
                        null;
                }


                machineOeeApplyEntryModeV26();
            }
        );
    }


    for (
        const input
        of [
            machineOeeNoJcStartV26(),
            machineOeeNoJcEndV26()
        ]
    ) {

        if (!input) {
            continue;
        }


        const updateMode =
            function() {

                machineOeeApplyEntryModeV26();
            };


        input.addEventListener(
            "input",
            updateMode
        );


        input.addEventListener(
            "change",
            updateMode
        );


        input.addEventListener(
            "blur",
            updateMode
        );
    }


    /* -----------------------------------------------------
     * KEEP LOCK CORRECT AFTER JC FETCH / START / RESUME
     * ----------------------------------------------------- */

    if (
        typeof machineOeeRenderRunningRunV1
        === "function"
    ) {

        const renderRunningBaseV26 =
            machineOeeRenderRunningRunV1;


        machineOeeRenderRunningRunV1 =
            function(run) {

                const result =
                    renderRunningBaseV26(
                        run
                    );


                machineOeeApplyEntryModeV26();


                return result;
            };
    }


    if (
        typeof machineOeeCheckPendingV1
        === "function"
    ) {

        const pendingBaseV26 =
            machineOeeCheckPendingV1;


        machineOeeCheckPendingV1 =
            async function() {

                const result =
                    await pendingBaseV26();


                machineOeeApplyEntryModeV26();


                return result;
            };
    }


    /*
     * Initial page state.
     */
    window.setTimeout(
        machineOeeApplyEntryModeV26,
        300
    );


    window.machineOeeApplyEntryModeV26 =
        machineOeeApplyEntryModeV26;

})();



/* MACHINE_OEE_INLINE_MACHINE_SWITCH_V27 */

(function () {

    function machineOeeEscapeMachineV27(
        value
    ) {

        return String(
            value === null
            ||
            value === undefined
                ? ""
                : value
        )
        .replaceAll(
            "&",
            "&amp;"
        )
        .replaceAll(
            "<",
            "&lt;"
        )
        .replaceAll(
            ">",
            "&gt;"
        )
        .replaceAll(
            '"',
            "&quot;"
        )
        .replaceAll(
            "'",
            "&#039;"
        );
    }


    function machineOeeMachineHostV27() {

        let host =
            document.getElementById(
                "oee-machine-switcher-v27"
            );


        if (host) {

            return host;
        }


        const topbar =
            document.querySelector(
                ".oee-topbar"
            );


        if (!topbar) {

            return null;
        }


        host =
            document.createElement(
                "section"
            );


        host.id =
            "oee-machine-switcher-v27";


        host.className =
            "oee-machine-switcher-v27";


        topbar.insertAdjacentElement(
            "afterend",
            host
        );


        return host;
    }


    function machineOeeSwitchV27(
        machineId
    ) {

        const context =
            window.NMTG_MACHINE_OEE_CONTEXT
            || {};


        const targetId =
            Number(
                machineId
                || 0
            );


        const currentId =
            Number(
                context.machine_id
                || 0
            );


        if (
            !targetId
            ||
            targetId === currentId
        ) {

            return;
        }


        const buttons =
            document.querySelectorAll(
                ".oee-machine-btn-v27"
            );


        for (
            const button
            of buttons
        ) {

            button.disabled =
                true;


            button.classList.add(
                "loading"
            );
        }


        /*
         * Same Machine OEE workspace route.
         *
         * We are NOT returning to Page 3 /
         * Machine Selection first.
         *
         * Backend still validates that this
         * machine belongs to the Zone login.
         */
        window.location.assign(
            "/oee-machine/operator?machine_id="
            + encodeURIComponent(
                targetId
            )
        );
    }


    async function machineOeeLoadMachinesV27() {

        const context =
            window.NMTG_MACHINE_OEE_CONTEXT
            || {};


        /*
         * This inline selector is intended for
         * the shared Zone OEE workstation.
         */
        if (
            !context.is_zone_login
        ) {

            return;
        }


        const host =
            machineOeeMachineHostV27();


        if (!host) {

            return;
        }


        host.innerHTML = `

            <div
                class="oee-machine-switcher-head-v27"
            >

                <div
                    class="oee-machine-switcher-title-v27"
                >

                    <i
                        class="fa fa-cogs"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Zone Machines
                    </span>

                </div>

            </div>


            <div
                style="
                    color:#64748b;
                    font-size:10px;
                "
            >

                Loading machines...

            </div>
        `;


        try {

            const response =
                await fetch(
                    "/api/oee-machine/zone-workspace",
                    {
                        cache:
                            "no-store"
                    }
                );


            const data =
                (
                    typeof machineOeeReadApiResponseV2
                    === "function"
                )
                ?
                await machineOeeReadApiResponseV2(
                    response,
                    "Zone machine list"
                )
                :
                await response.json();


            if (
                !response.ok
                ||
                data.success === false
            ) {

                throw new Error(
                    data.error
                    ||
                    "Unable to load Zone machines."
                );
            }


            const machines =
                Array.isArray(
                    data.machines
                )
                ?
                data.machines
                :
                [];


            const currentId =
                Number(
                    context.machine_id
                    || 0
                );


            host.innerHTML = `

                <div
                    class="oee-machine-switcher-head-v27"
                >

                    <div
                        class="oee-machine-switcher-title-v27"
                    >

                        <i
                            class="fa fa-cogs"
                            aria-hidden="true"
                        ></i>

                        <span>
                            Machines
                        </span>

                    </div>


                    <div
                        class="oee-machine-switcher-zone-v27"
                    >

                        Zone
                        ${machineOeeEscapeMachineV27(
                            data.zone
                            || context.zone
                            || "-"
                        )}

                        &nbsp;|&nbsp;

                        ${machines.length}
                        Machine(s)

                    </div>

                </div>


                <div
                    id="oee-machine-switcher-list-v27"

                    class="oee-machine-switcher-list-v27"
                ></div>
            `;


            const list =
                document.getElementById(
                    "oee-machine-switcher-list-v27"
                );


            if (!list) {

                return;
            }


            for (
                const machine
                of machines
            ) {

                const id =
                    Number(
                        machine.id
                        || 0
                    );


                if (!id) {

                    continue;
                }


                const button =
                    document.createElement(
                        "button"
                    );


                button.type =
                    "button";


                button.className =
                    "oee-machine-btn-v27";


                if (
                    id === currentId
                ) {

                    button.classList.add(
                        "active"
                    );
                }


                button.title =
                    String(
                        machine.machine_no
                        || ""
                    )
                    + " - "
                    + String(
                        machine.machine_name
                        || ""
                    );


                button.innerHTML = `

                    <span
                        class="oee-machine-btn-no-v27"
                    >
                        ${machineOeeEscapeMachineV27(
                            machine.machine_no
                            || ""
                        )}
                    </span>


                    <span
                        class="oee-machine-btn-name-v27"
                    >
                        ${machineOeeEscapeMachineV27(
                            machine.machine_name
                            || ""
                        )}
                    </span>
                `;


                if (
                    id !== currentId
                ) {

                    button.addEventListener(
                        "click",
                        function() {

                            machineOeeSwitchV27(
                                id
                            );
                        }
                    );
                }


                list.appendChild(
                    button
                );
            }


        } catch (error) {

            host.innerHTML = `

                <div
                    class="machine-page-error-v1"
                >

                    ${machineOeeEscapeMachineV27(
                        error.message
                        ||
                        "Unable to load Zone machines."
                    )}

                </div>
            `;
        }
    }


    window.machineOeeSwitchV27 =
        machineOeeSwitchV27;


    window.setTimeout(
        machineOeeLoadMachinesV27,
        250
    );

})();



/* MACHINE_OEE_RUNNING_UI_REPAIR_V29 */

(function () {

    function machineOeeRunningRunV29() {

        try {

            return (
                machineOeeActiveRunV1
                ||
                machineOeePendingRunV1
                ||
                null
            );

        } catch (_) {

            return null;
        }
    }


    function machineOeeRepairRunningUiV29() {

        const run =
            machineOeeRunningRunV29();


        if (
            !run
            ||
            !run.run_id
        ) {

            return;
        }


        /*
         * A RUNNING JC must always have its
         * Production Entry available.
         */
        let production =
            document.getElementById(
                "machine-oee-production-entry-v1"
            );


        if (
            !production
            &&
            typeof machineOeeRenderProductionEntryV1
                === "function"
        ) {

            machineOeeRenderProductionEntryV1(
                run
            );


            production =
                document.getElementById(
                    "machine-oee-production-entry-v1"
                );
        }


        if (production) {

            production.hidden = true;


            production.style.display = "none";
        }


        /*
         * The smart-action layer must not show
         * Start Job once the machine run exists.
         */
        const actionButton =
            document.getElementById(
                "machine-oee-smart-action-btn-v1"
            );


        if (actionButton) {

            actionButton.disabled =
                true;


            actionButton.textContent =
                "Current Job Running";


            actionButton.style.cursor =
                "default";


            actionButton.style.opacity =
                ".75";
        }


        /*
         * Re-apply JC/no-JC entry locking.
         *
         * In JC mode the separate machine-loss
         * Start/End period stays disabled.
         */
        if (
            typeof machineOeeApplyEntryModeV26
            === "function"
        ) {

            machineOeeApplyEntryModeV26();
        }
    }


    /*
     * Repair immediately whenever a new run
     * is rendered.
     */
    if (
        typeof machineOeeRenderRunningRunV1
        === "function"
    ) {

        const baseRenderV29 =
            machineOeeRenderRunningRunV1;


        machineOeeRenderRunningRunV1 =
            function(run) {

                const result =
                    baseRenderV29(
                        run
                    );


                window.setTimeout(
                    machineOeeRepairRunningUiV29,
                    20
                );


                window.setTimeout(
                    machineOeeRepairRunningUiV29,
                    150
                );


                return result;
            };
    }


    /*
     * Also repair an already-running JC when
     * the page is refreshed/reopened.
     */
    if (
        typeof machineOeeCheckPendingV1
        === "function"
    ) {

        const basePendingV29 =
            machineOeeCheckPendingV1;


        machineOeeCheckPendingV1 =
            async function() {

                const result =
                    await basePendingV29();


                window.setTimeout(
                    machineOeeRepairRunningUiV29,
                    20
                );


                return result;
            };
    }


    window.machineOeeRepairRunningUiV29 =
        machineOeeRepairRunningUiV29;


    window.setTimeout(
        machineOeeRepairRunningUiV29,
        300
    );


    window.setTimeout(
        machineOeeRepairRunningUiV29,
        1000
    );

})();

/* MACHINE_OEE_MODE_VISIBILITY_AND_LIVE_RIGHT_V31 */

(function () {

    let syncTimerV31 =
        null;


    function currentJcModeV31() {

        let hasRun =
            false;


        try {

            hasRun =
                Boolean(
                    machineOeeActiveRunV1
                    ?.run_id
                    ||
                    machineOeePendingRunV1
                    ?.run_id
                );

        } catch (_) {

            hasRun =
                false;
        }


        let fetched =
            false;


        try {

            fetched =
                Boolean(
                    machineOeeCurrentFetchedJcV1
                );

        } catch (_) {

            fetched =
                false;
        }


        const jcValue =
            String(
                document.getElementById(
                    "machine-oee-jc-input"
                )?.value
                || ""
            ).trim();


        /*
         * MACHINE_OEE_START_PERSISTENCE_GUARD_V37
         *
         * Production Start/Stop belongs to a persisted JC run.
         * Merely typing/fetching a JC must not make the page look
         * as if production has already started.
         */
        return hasRun;
    }


    function toggleFieldV31(
        input,
        show
    ) {

        if (!input) {
            return;
        }


        const field =
            input.closest(
                ".oee-direct-field-v3"
            )
            ||
            input.closest(
                ".oee-loss-period-field-v16"
            );


        if (field) {

            field.classList.toggle(
                "oee-time-hidden-v31",
                !show
            );
        }


        input.disabled =
            !show;
    }


    function syncTimeModeV31() {

        const jcMode =
            currentJcModeV31();


        const jcStart =
            document.getElementById(
                "oee-direct-start-time-v3"
            );


        const jcEnd =
            document.getElementById(
                "oee-direct-stop-time-v3"
            );


        const lossStart =
            document.getElementById(
                "oee-loss-start-v16"
            );


        const lossEnd =
            document.getElementById(
                "oee-loss-stop-v16"
            );


        /*
         * JC MODE
         *
         * Show:
         *   Qty
         *   JC Start/End
         *   Cycle
         *   Load/Unload
         *
         * Hide:
         *   No-JC loss Start/End
         */
        toggleFieldV31(
            jcStart,
            jcMode
        );


        toggleFieldV31(
            jcEnd,
            jcMode
        );


        /*
         * NO-JC MODE
         *
         * Show:
         *   Loss Start/End
         *
         * Hide:
         *   JC Production Start/End
         */
        toggleFieldV31(
            lossStart,
            !jcMode
        );


        toggleFieldV31(
            lossEnd,
            !jcMode
        );
    }


    function placeLiveOeeRightV31() {

        const host =
            document.getElementById(
                "machine-live-oee-host-v1"
            );


        if (!host) {
            return;
        }


        const aside =
            host.closest(
                "aside"
            )
            ||
            document.querySelector(
                ".workspace-grid > aside"
            );


        if (!aside) {
            return;
        }


        /*
         * Keep Live OEE directly below
         * Machine Context and above later
         * dynamically-created side cards.
         */
        const firstCard =
            Array.from(
                aside.children
            ).find(
                function(node) {

                    return (
                        node !== host
                        &&
                        node.classList
                        ?.contains(
                            "card"
                        )
                    );
                }
            );


        if (
            firstCard
            &&
            firstCard.nextElementSibling
                !== host
        ) {

            firstCard.insertAdjacentElement(
                "afterend",
                host
            );
        }
    }


    function syncAllV31() {

        window.clearTimeout(
            syncTimerV31
        );


        syncTimerV31 =
            window.setTimeout(
                function() {

                    syncTimeModeV31();

                    placeLiveOeeRightV31();

                },
                20
            );
    }


    /*
     * JC typing must immediately switch mode.
     */
    const jcInput =
        document.getElementById(
            "machine-oee-jc-input"
        );


    if (jcInput) {

        jcInput.addEventListener(
            "input",
            syncAllV31
        );


        jcInput.addEventListener(
            "change",
            syncAllV31
        );
    }


    /*
     * Existing JC mode function remains authority
     * for enable/disable behavior.
     *
     * V31 only adds correct VISIBILITY.
     */
    if (
        typeof window.machineOeeApplyEntryModeV26
        === "function"
    ) {

        const baseModeV31 =
            window.machineOeeApplyEntryModeV26;


        window.machineOeeApplyEntryModeV26 =
            function() {

                const result =
                    baseModeV31();


                syncAllV31();


                return result;
            };
    }


    /*
     * Dynamic OEE/JC elements are created after
     * fetch/start/resume, so keep UI synchronized.
     */
    const observer =
        new MutationObserver(
            syncAllV31
        );


    observer.observe(
        document.body,
        {
            childList:true,
            subtree:true
        }
    );


    window.machineOeeSyncModeVisibilityV31 =
        syncAllV31;


    window.setTimeout(
        syncAllV31,
        100
    );


    window.setTimeout(
        syncAllV31,
        500
    );


    window.setTimeout(
        syncAllV31,
        1200
    );

})();



/* MACHINE_OEE_SAVE_CONFIRM_AND_KPI_V32 */

(function () {

    let toastTimerV32 =
        null;


    function machineOeePctV32(
        value
    ) {

        if (
            value === null
            ||
            value === undefined
            ||
            value === ""
        ) {

            return "-";
        }


        const number =
            Number(
                value
            );


        if (
            !Number.isFinite(
                number
            )
        ) {

            return "-";
        }


        return (
            number * 100
        ).toFixed(
            2
        ) + "%";
    }


    function machineOeeShowDbToastV32(
        title,
        message
    ) {

        let toast =
            document.getElementById(
                "machine-oee-db-toast-v32"
            );


        if (!toast) {

            toast =
                document.createElement(
                    "div"
                );


            toast.id =
                "machine-oee-db-toast-v32";


            document.body.appendChild(
                toast
            );
        }


        toast.innerHTML = `

            <i
                class="fa fa-check-circle"
                aria-hidden="true"
            ></i>

            <div>

                <strong>
                    ${machineOeeEscapeV1(
                        title
                    )}
                </strong>

                <span>
                    ${machineOeeEscapeV1(
                        message
                    )}
                </span>

            </div>
        `;


        toast.classList.add(
            "show"
        );


        window.clearTimeout(
            toastTimerV32
        );


        toastTimerV32 =
            window.setTimeout(
                function() {

                    toast.classList.remove(
                        "show"
                    );

                },
                4000
            );
    }


    /*
     * PERFORMANCE_FIX_LIVE_OEE_SHARED_V1
     *
     * Startup intentionally calls the Live OEE refresh more
     * than once. If an identical session request is already
     * in flight, share that Promise instead of opening a
     * second HTTP request.
     */
    const machineOeeLiveOeePendingV1 =
        new Map();


    async function machineOeeGetLiveOeeSharedV1(
        sessionId
    ) {

        const key =
            String(
                sessionId
                || ""
            ).trim();


        if (!key) {
            throw new Error(
                "OEE session is not available."
            );
        }


        if (
            machineOeeLiveOeePendingV1.has(
                key
            )
        ) {
            return machineOeeLiveOeePendingV1.get(
                key
            );
        }


        const promise =
            (async function() {

                const response =
                    await fetch(
                        "/api/oee-machine/session/"
                        +
                        encodeURIComponent(
                            key
                        )
                        +
                        "/live-oee",
                        {
                            cache:
                                "no-store"
                        }
                    );


                const data =
                    await response.json();


                return {
                    response:
                        response,

                    data:
                        data
                };
            })();


        machineOeeLiveOeePendingV1.set(
            key,
            promise
        );


        try {

            return await promise;

        } finally {

            machineOeeLiveOeePendingV1.delete(
                key
            );
        }
    }


    async function machineOeeRefreshLiveV32() {

        /* MACHINE_OEE_LIVE_RUN_REHYDRATE_V42 */

        let run =
            machineOeeActiveRunV1
            ||
            machineOeePendingRunV1;


        /*
         * The database is the authority.
         *
         * If layered frontend code temporarily loses the
         * active/pending run object, restore it once from
         * the normal persisted pending-run API.
         *
         * This is NOT polling.
         */
        if (
            !run
            ||
            !run.session_id
        ) {

            try {

                const context =
                    window.NMTG_MACHINE_OEE_CONTEXT
                    || {};


                const machineId =
                    Number(
                        context.machine_id
                        || 0
                    );


                if (machineId > 0) {

                    const pendingResultV32 =
                        await machineOeeGetPendingSharedV1(
                            machineId
                        );


                    const response = {
                        ok:
                            pendingResultV32.ok,

                        status:
                            pendingResultV32.status
                    };


                    const data =
                        pendingResultV32.data;


                    const persistedRun =
                        data?.pending_run
                        || null;


                    if (
                        response.ok
                        &&
                        data?.success !== false
                        &&
                        data?.has_pending_run === true
                        &&
                        persistedRun
                        &&
                        persistedRun.run_id
                        &&
                        persistedRun.session_id
                    ) {

                        machineOeePendingRunV1 =
                            persistedRun;


                        machineOeeActiveRunV1 =
                            persistedRun;


                        run =
                            persistedRun;
                    }
                }

            } catch (_) {

                /*
                 * Existing Live OEE fallback below will
                 * display "-" if restore genuinely fails.
                 */
            }
        }


        const host =
            document.getElementById(
                "machine-live-oee-host-v1"
            );


        if (!host) {
            return;
        }


        if (
            !run
            ||
            !run.session_id
        ) {

            host.innerHTML = `

                
            `;


            return;
        }


        try {

            const liveResult =
                await machineOeeGetLiveOeeSharedV1(
                    run.session_id
                );


            const response =
                liveResult.response;


            const data =
                liveResult.data;


            if (
                !response.ok
                ||
                data.success === false
            ) {

                throw new Error(
                    data.error
                    ||
                    "Unable to calculate Live OEE."
                );
            }


            if (
                data.calculation_ready
                === false
            ) {

                host.innerHTML = `

                    <section
                        class="machine-live-v32"
                    >

                        <div
                            class="machine-live-head-v32"
                        >

                            <strong>
                                Live Machine OEE
                            </strong>

                        </div>


                        <div
                            class="machine-live-note-v32"
                        >

                            ${machineOeeEscapeV1(
                                data.message
                                ||
                                "OEE formula is not ready."
                            )}

                        </div>

                    </section>
                `;


                return;
            }


            const pvaNote =
                String(
                    data.plan_vs_actual_note
                    || ""
                ).trim();


            host.innerHTML = `

                <section
                    class="machine-live-v32"
                >

                    <div
                        class="machine-live-head-v32"
                    >

                        <strong>
                            Live Machine OEE
                        </strong>


                        <span>

                            ${machineOeeEscapeV1(
                                data.machine
                                ?.machine_no
                                || ""
                            )}

                        </span>

                    </div>


                    <div
                        class="machine-live-kpis-v32"
                    >

                        <div
                            class="machine-live-kpi-v32"
                        >

                            <span>
                                Plan vs Actual
                            </span>

                            <strong>

                                ${machineOeePctV32(
                                    data.plan_vs_actual
                                )}

                            </strong>

                        </div>


                        <div
                            class="machine-live-kpi-v32"
                        >

                            <span>
                                PR
                            </span>

                            <strong>

                                ${machineOeePctV32(
                                    data.pr_ratio
                                )}

                            </strong>

                        </div>


                        <div
                            class="
                                machine-live-kpi-v32
                                oee
                            "
                        >

                            <span>
                                OEE
                            </span>

                            <strong>

                                ${machineOeePctV32(
                                    data.oee_ratio
                                )}

                            </strong>

                        </div>

                    </div>


                    ${
                        pvaNote
                        ?
                        `

                            <div
                                class="machine-live-note-v32"
                            >

                                ${machineOeeEscapeV1(
                                    pvaNote
                                )}

                            </div>
                        `
                        :
                        ""
                    }

                </section>
            `;


        } catch (error) {

            host.innerHTML = `

                <section
                    class="machine-live-v32"
                >

                    <div
                        class="machine-live-head-v32"
                    >

                        <strong>
                            Live Machine OEE
                        </strong>

                    </div>


                    <div
                        class="machine-live-note-v32"
                    >

                        ${machineOeeEscapeV1(
                            error.message
                            ||
                            "Unable to calculate Live OEE."
                        )}

                    </div>

                </section>
            `;
        }
    }


    /*
     * V32 becomes the current Live OEE renderer.
     */
    try {

        machineOeeRefreshLiveCalcV1 =
            machineOeeRefreshLiveV32;

    } catch (_) {
    }


    window.machineOeeRefreshLiveCalcV1 =
        machineOeeRefreshLiveV32;


    /*
     * Watch existing feedback.
     *
     * We do NOT change the save transaction itself.
     * Existing API success remains the authority.
     */
    function machineOeeSyncSaveFeedbackV32() {

        const progress =
            document.getElementById(
                "oee-direct-feedback-v3"
            );


        if (progress) {

            const text =
                String(
                    progress.textContent
                    || ""
                ).trim()
                .toLowerCase();


            if (
                text === "saving..."
            ) {

                progress.dataset
                    .dbConfirmedV32 =
                    "0";


                progress.classList.remove(
                    "oee-db-confirm-v32"
                );
            }


            if (
                (
                    text === "saved"
                    ||
                    text === "progress saved"
                )
                &&
                progress.dataset
                    .dbConfirmedV32
                    !== "1"
            ) {

                progress.dataset
                    .dbConfirmedV32 =
                    "1";


                progress.classList.add(
                    "oee-db-confirm-v32"
                );


                progress.innerHTML = `

                    <i
                        class="fa fa-check-circle"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Progress saved to database
                    </span>
                `;


                machineOeeShowDbToastV32(
                    "Saved to Database",
                    "Production and OEE losses were saved successfully."
                );


                window.setTimeout(
                    machineOeeRefreshLiveV32,
                    80
                );
            }
        }


        const machineLoss =
            document.getElementById(
                "machine-oee-machine-loss-feedback-v13"
            );


        if (machineLoss) {

            const text =
                String(
                    machineLoss.textContent
                    || ""
                ).trim()
                .toLowerCase();


            if (
                text === "saving..."
            ) {

                machineLoss.dataset
                    .dbConfirmedV32 =
                    "0";


                machineLoss.classList.remove(
                    "oee-db-confirm-v32"
                );
            }


            if (
                text.includes(
                    "machine losses saved"
                )
                &&
                machineLoss.dataset
                    .dbConfirmedV32
                    !== "1"
            ) {

                machineLoss.dataset
                    .dbConfirmedV32 =
                    "1";


                machineLoss.classList.add(
                    "oee-db-confirm-v32"
                );


                const toolCountV6 =
                    Number(
                        window.machineOeeLastToolSaveCountV6
                        || 0
                    );


                const confirmedMessageV6 =
                    toolCountV6 > 0
                    ?
                    (
                        "Machine losses and "
                        + toolCountV6
                        + " Tool Position "
                        + (
                            toolCountV6 === 1
                            ? "record"
                            : "records"
                        )
                        + " saved to database."
                    )
                    :
                    "Machine losses saved to database";


                machineLoss.innerHTML = `

                    <i
                        class="fa fa-check-circle"
                        aria-hidden="true"
                    ></i>

                    <span>
                        ${confirmedMessageV6}
                    </span>
                `;


                machineOeeShowDbToastV32(
                    "Saved to Database",
                    confirmedMessageV6
                );
            }
        }
    }


    const observerV32 =
        new MutationObserver(
            machineOeeSyncSaveFeedbackV32
        );


    observerV32.observe(
        document.body,
        {
            childList:true,
            subtree:true,
            characterData:true
        }
    );


    window.setTimeout(
        machineOeeSyncSaveFeedbackV32,
        200
    );


    window.setTimeout(
        machineOeeRefreshLiveV32,
        350
    );

    window.setTimeout(
        machineOeeRefreshLiveV32,
        1000
    );



})();


/* MACHINE_OEE_JMS_TOAST_BRIDGE_V33 */

(function () {

    window.machineOeeShowDbToastV32 =
        function(
            title,
            message,
            type
        ) {

            const toastMessage =
                String(
                    message
                    || title
                    || "Saved successfully."
                );


            if (
                typeof showToast
                === "function"
            ) {

                showToast(
                    toastMessage,
                    type || "success"
                );
            }
        };


    /*
     * Remove any V32 toast element if an older runtime
     * layer created one before this bridge loaded.
     */
    const oldToast =
        document.getElementById(
            "machine-oee-db-toast-v32"
        );


    if (oldToast) {
        oldToast.remove();
    }

})();

/* V33 TOAST BRIDGE END */



/* MACHINE_OEE_DURATION_HMS_V34 */

(function () {

    let wireTimerV34 =
        null;


    const durationConfigV34 = [

        {
            displayId:
                "oee-direct-cycle-hms-v34",

            minId:
                "machine-oee-cycle-min-v1",

            secId:
                "machine-oee-cycle-sec-v1"
        },

        {
            displayId:
                "oee-direct-load-hms-v34",

            minId:
                "machine-oee-load-min-v1",

            secId:
                "machine-oee-load-sec-v1"
        }
    ];


    function numberV34(
        value
    ) {

        const number =
            Number(
                value
                || 0
            );


        if (
            !Number.isFinite(
                number
            )
            ||
            number < 0
        ) {

            return 0;
        }


        return Math.floor(
            number
        );
    }


    /*
     * Existing DB structure:
     *
     * minutes + seconds
     *
     * Visible structure:
     *
     * HH:MM:SS
     *
     * Example:
     * 01:05:30
     * becomes
     * 65 minutes + 30 seconds.
     */
    function sourceToHmsV34(
        minuteInput,
        secondInput
    ) {

        const totalMinutes =
            numberV34(
                minuteInput?.value
            );


        const seconds =
            Math.min(
                numberV34(
                    secondInput?.value
                ),
                59
            );


        const hours =
            Math.floor(
                totalMinutes / 60
            );


        const minutes =
            totalMinutes % 60;


        return (
            String(hours)
                .padStart(
                    2,
                    "0"
                )
            +
            ":"
            +
            String(minutes)
                .padStart(
                    2,
                    "0"
                )
            +
            ":"
            +
            String(seconds)
                .padStart(
                    2,
                    "0"
                )
        );
    }


    function formatTypingV34(
        input
    ) {

        const digits =
            String(
                input.value
                || ""
            )
            .replace(
                /\D/g,
                ""
            )
            .slice(
                0,
                6
            );


        let value =
            digits.slice(
                0,
                2
            );


        if (
            digits.length >= 2
        ) {

            value += ":";
        }


        if (
            digits.length > 2
        ) {

            value +=
                digits.slice(
                    2,
                    4
                );
        }


        if (
            digits.length >= 4
        ) {

            value += ":";
        }


        if (
            digits.length > 4
        ) {

            value +=
                digits.slice(
                    4,
                    6
                );
        }


        input.value =
            value;
    }


    function parseHmsV34(
        value
    ) {

        const match =
            /^(\d{2}):(\d{2}):(\d{2})$/
            .exec(
                String(
                    value
                    || ""
                ).trim()
            );


        if (!match) {

            return null;
        }


        const hours =
            Number(
                match[1]
            );


        const minutes =
            Number(
                match[2]
            );


        const seconds =
            Number(
                match[3]
            );


        /*
         * Cycle/Load are DURATIONS.
         *
         * Hours may be 00-99.
         * Minutes and seconds must be 00-59.
         */
        if (
            minutes > 59
            ||
            seconds > 59
        ) {

            return null;
        }


        return {
            hours:
                hours,

            minutes:
                minutes,

            seconds:
                seconds
        };
    }


    function syncDisplayToSourceV34(
        config,
        showError
    ) {

        const display =
            document.getElementById(
                config.displayId
            );


        const minuteInput =
            document.getElementById(
                config.minId
            );


        const secondInput =
            document.getElementById(
                config.secId
            );


        if (
            !display
            ||
            !minuteInput
            ||
            !secondInput
        ) {

            return false;
        }


        const parsed =
            parseHmsV34(
                display.value
            );


        if (!parsed) {

            if (
                showError
                &&
                display.value
            ) {

                if (
                    typeof showToast
                    === "function"
                ) {

                    showToast(
                        "Enter duration in HH:MM:SS format.",
                        "error"
                    );
                }
            }


            return false;
        }


        minuteInput.value =
            String(
                (
                    parsed.hours
                    * 60
                )
                +
                parsed.minutes
            );


        secondInput.value =
            String(
                parsed.seconds
            );


        return true;
    }


    function buildDurationInputV34(
        config
    ) {

        const minuteInput =
            document.getElementById(
                config.minId
            );


        const secondInput =
            document.getElementById(
                config.secId
            );


        if (
            !minuteInput
            ||
            !secondInput
        ) {

            return;
        }


        const pair =
            minuteInput.closest(
                ".oee-direct-time-pair-v3"
            );


        if (!pair) {

            return;
        }


        const field =
            pair.closest(
                ".oee-direct-field-v3"
            );


        if (!field) {

            return;
        }


        pair.classList.add(
            "oee-duration-source-hidden-v34"
        );


        let display =
            document.getElementById(
                config.displayId
            );


        if (!display) {

            display =
                document.createElement(
                    "input"
                );


            display.id =
                config.displayId;


            display.type =
                "text";


            display.inputMode =
                "numeric";


            display.autocomplete =
                "off";


            display.placeholder =
                "HH:MM:SS";


            display.className =
                "oee-duration-hms-v34";


            field.insertBefore(
                display,
                pair
            );


            /*
             * OEE_CYCLE_LOAD_TIME_ENTRY_V111
             *
             * Cycle Time and Load / Unload Time now use
             * the same operator-entry behaviour as the
             * existing Start / End time fields.
             *
             * Important:
             * - never insert ":" while typing
             * - allow normal cursor editing
             * - normalize only when entry is committed
             * - keep V34 hidden minute/second source fields
             */

            display.addEventListener(
                "focus",
                function () {

                    display.setAttribute(
                        "maxlength",
                        "8"
                    );


                    display.setAttribute(
                        "inputmode",
                        "numeric"
                    );


                    display.setAttribute(
                        "autocomplete",
                        "off"
                    );


                    display.setAttribute(
                        "placeholder",
                        "HH:MM:SS"
                    );


                    display.setCustomValidity(
                        ""
                    );
                }
            );


            display.addEventListener(
                "input",
                function () {

                    display.dataset
                        .userEditedV34 =
                        "1";


                    /*
                     * Same as Start / End:
                     *
                     * Do NOT auto-format while typing.
                     *
                     * Examples while operator types:
                     *
                     * 2
                     * 23
                     * 230
                     * 1230
                     *
                     * Formatting happens only when the
                     * operator leaves/commits the field.
                     */
                    display.setCustomValidity(
                        ""
                    );
                }
            );


            display.addEventListener(
                "change",
                function () {

                    const raw =
                        String(
                            display.value
                            || ""
                        ).trim();


                    if (!raw) {
                        return;
                    }


                    if (
                        typeof window.normalizeOeeTimeV79
                        !== "function"
                    ) {

                        return;
                    }


                    const normalized =
                        window.normalizeOeeTimeV79(
                            raw
                        );


                    /*
                     * Blur owns visible validation.
                     * Do not interrupt the operator here.
                     */
                    if (
                        normalized === null
                    ) {

                        return;
                    }


                    display.value =
                        normalized;


                    display.setCustomValidity(
                        ""
                    );


                    syncDisplayToSourceV34(
                        config,
                        false
                    );
                }
            );


            display.addEventListener(
                "blur",
                function () {

                    const raw =
                        String(
                            display.value
                            || ""
                        ).trim();


                    /*
                     * Preserve existing Cycle / Load empty
                     * value behaviour.
                     */
                    if (!raw) {

                        display.value =
                            "00:00:00";


                        display.setCustomValidity(
                            ""
                        );


                        syncDisplayToSourceV34(
                            config,
                            false
                        );


                        return;
                    }


                    if (
                        typeof window.normalizeOeeTimeV79
                        !== "function"
                    ) {

                        return;
                    }


                    const normalized =
                        window.normalizeOeeTimeV79(
                            raw
                        );


                    if (
                        normalized === null
                    ) {

                        display.setCustomValidity(
                            "Enter valid time in HH:MM:SS format."
                        );


                        display.reportValidity();


                        return;
                    }


                    display.setCustomValidity(
                        ""
                    );


                    display.value =
                        normalized;


                    /*
                     * Keep the existing V34 architecture:
                     *
                     * visible HH:MM:SS
                     *        |
                     *        v
                     * hidden minute + second fields
                     *
                     * Existing save and OEE calculation
                     * logic therefore remains unchanged.
                     */
                    syncDisplayToSourceV34(
                        config,
                        false
                    );


                    display.dispatchEvent(
                        new Event(
                            "change",
                            {
                                bubbles:
                                    true
                            }
                        )
                    );
                }
            );
        }


        /*
         * Initial value / refreshed running JC.
         *
         * Do not overwrite something the operator
         * is currently typing.
         */
        if (
            display.dataset
                .userEditedV34
                !== "1"
        ) {

            display.value =
                sourceToHmsV34(
                    minuteInput,
                    secondInput
                );
        }
    }


    function wireDurationsV34() {

        for (
            const config
            of durationConfigV34
        ) {

            buildDurationInputV34(
                config
            );
        }
    }


    function syncAllBeforeSaveV34() {

        for (
            const config
            of durationConfigV34
        ) {

            syncDisplayToSourceV34(
                config,
                false
            );
        }
    }


    /*
     * Capture phase:
     * ensure hidden minute/second fields are updated
     * BEFORE existing Save Progress / Complete handlers
     * read them.
     */
    document.addEventListener(
        "click",
        function (event) {

            const button =
                event.target
                ?.closest(
                    "button"
                );


            if (!button) {

                return;
            }


            const id =
                String(
                    button.id
                    || ""
                );


            const text =
                String(
                    button.textContent
                    || ""
                )
                .replace(
                    /\s+/g,
                    " "
                )
                .trim()
                .toLowerCase();


            if (
                id.includes(
                    "save"
                )
                ||
                id.includes(
                    "complete"
                )
                ||
                text.includes(
                    "save progress"
                )
                ||
                text.includes(
                    "complete operation"
                )
            ) {

                syncAllBeforeSaveV34();
            }

        },
        true
    );


    /*
     * Production controls are dynamically moved/rendered.
     * Re-wire only when DOM changes.
     */
    const observerV34 =
        new MutationObserver(
            function () {

                window.clearTimeout(
                    wireTimerV34
                );


                wireTimerV34 =
                    window.setTimeout(
                        wireDurationsV34,
                        30
                    );
            }
        );


    observerV34.observe(
        document.body,
        {
            childList:
                true,

            subtree:
                true
        }
    );


    window.machineOeeWireDurationsV34 =
        wireDurationsV34;


    window.setTimeout(
        wireDurationsV34,
        100
    );


    window.setTimeout(
        wireDurationsV34,
        500
    );

})();

/* V34 END */


/* OEE_CORE_CURRENT_SESSION_KPI_FRONTEND_V47 */

(function () {

    function pctV47(
        value
    ) {

        if (
            value === null
            ||
            value === undefined
            ||
            value === ""
        ) {

            return "-";
        }


        const number =
            Number(
                value
            );


        if (
            !Number.isFinite(
                number
            )
        ) {

            return "-";
        }


        return (
            number * 100
        ).toFixed(2)
        + "%";
    }


    function escapeV47(
        value
    ) {

        return String(
            value ?? ""
        )
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );
    }


    function hostV47() {

        return document.getElementById(
            "machine-live-oee-host-v1"
        );
    }


    function shiftV47() {

        return String(
            document.getElementById(
                "machine-oee-shift-v1"
            )?.value
            || ""
        ).trim();
    }


    function machineIdV47() {

        try {

            const context =
                window
                    .NMTG_MACHINE_OEE_CONTEXT
                || {};


            const machineId =
                Number(
                    context.machine_id
                    || 0
                );


            if (machineId > 0) {
                return machineId;
            }

        } catch (_) {
        }


        return Number(
            window.NMTG_MACHINE_OEE_CONTEXT.machine_id
        ) || 0;
    }


    function emptyV47(
        message
    ) {

        const host =
            hostV47();


        if (!host) {
            return;
        }


        host.innerHTML = `

            <section
                class="machine-live-v32"
            >

                <div
                    class="machine-live-head-v32"
                >

                    <strong>
                        Machine OEE
                    </strong>

                </div>


                <div
                    class="machine-live-kpis-v32"
                >

                    <div
                        class="machine-live-kpi-v32"
                    >

                        <span>
                            Plan vs Actual
                        </span>

                        <strong>
                            -
                        </strong>

                    </div>


                    <div
                        class="machine-live-kpi-v32"
                    >

                        <span>
                            PR
                        </span>

                        <strong>
                            -
                        </strong>

                    </div>


                    <div
                        class="
                            machine-live-kpi-v32
                            oee
                        "
                    >

                        <span>
                            OEE
                        </span>

                        <strong>
                            -
                        </strong>

                    </div>

                </div>


                ${
                    message
                    ?
                    `

                        <div
                            class="machine-live-note-v32"
                        >
                            ${escapeV47(
                                message
                            )}
                        </div>
                    `
                    :
                    ""
                }

            </section>
        `;
    }


    /*
     * PERFORMANCE_FIX_CURRENT_SESSION_KPI_SHARED_V2
     *
     * Startup can request the same Machine + Shift KPI more
     * than once a few hundred milliseconds apart.
     *
     * Share in-flight work and retain the parsed result for
     * 1500 ms. Genuine later refreshes are therefore still
     * fetched normally.
     */
    const currentSessionKpiCacheV47 =
        new Map();


    async function getCurrentSessionKpiSharedV47(
        machineId,
        shiftName
    ) {

        const key =
            String(machineId)
            + "|"
            + String(
                shiftName
                || ""
            ).trim();


        const now =
            Date.now();


        const cached =
            currentSessionKpiCacheV47.get(
                key
            );


        if (
            cached
            &&
            cached.expiresAt > now
        ) {

            return cached.promise;
        }


        const promise =
            (async function() {

                const response =
                    await fetch(
                        "/api/oee-machine/"
                        +
                        "current-session-kpi/"
                        +
                        encodeURIComponent(
                            machineId
                        )
                        +
                        "?shift_name="
                        +
                        encodeURIComponent(
                            shiftName
                        ),
                        {
                            cache:
                                "no-store"
                        }
                    );


                const data =
                    (
                        typeof
                            machineOeeReadApiResponseV2
                        === "function"
                    )
                    ?
                    await machineOeeReadApiResponseV2(
                        response,
                        "Load Machine OEE KPI"
                    )
                    :
                    await response.json();


                return {
                    ok:
                        response.ok,

                    status:
                        response.status,

                    data:
                        data
                };
            })();


        currentSessionKpiCacheV47.set(
            key,
            {
                promise:
                    promise,

                expiresAt:
                    now + 1500
            }
        );


        try {

            return await promise;

        } catch (error) {

            currentSessionKpiCacheV47.delete(
                key
            );

            throw error;
        }
    }



    async function refreshV47() {

        const host =
            hostV47();


        if (!host) {
            return;
        }


        const machineId =
            machineIdV47();


        const shiftName =
            shiftV47();


        if (machineId <= 0) {

            emptyV47(
                "Selected machine is not available."
            );

            return;
        }


        if (!shiftName) {

            emptyV47(
                "Select Shift to view Machine OEE."
            );

            return;
        }


        try {

            const kpiResult =
                await getCurrentSessionKpiSharedV47(
                    machineId,
                    shiftName
                );


            const response = {
                ok:
                    kpiResult.ok,

                status:
                    kpiResult.status
            };


            const data =
                kpiResult.data;


            if (
                !response.ok
                ||
                data.success === false
            ) {

                throw new Error(
                    data.error
                    ||
                    "Unable to load Machine OEE."
                );
            }


            if (
                data.has_session
                !== true
                ||
                !data.session
            ) {

                emptyV47(
                    data.message
                    ||
                    "No OEE entry exists for this shift today."
                );

                return;
            }


            const row =
                data.session;


            host.innerHTML = `

                <section
                    class="machine-live-v32"
                >

                    <div
                        class="machine-live-head-v32"
                    >

                        <strong>
                            Machine OEE
                        </strong>


                        <span>

                            ${escapeV47(
                                row.machine_no
                                || ""
                            )}

                            |

                            ${escapeV47(
                                row.shift_name
                                || ""
                            )}

                        </span>

                    </div>


                    <div
                        class="machine-live-kpis-v32"
                    >

                        <div
                            class="machine-live-kpi-v32"
                        >

                            <span>
                                Plan vs Actual
                            </span>

                            <strong>

                                ${pctV47(
                                    row.plan_vs_actual
                                )}

                            </strong>

                        </div>


                        <div
                            class="machine-live-kpi-v32"
                        >

                            <span>
                                PR
                            </span>

                            <strong>

                                ${pctV47(
                                    row.pr_ratio
                                )}

                            </strong>

                        </div>


                        <div
                            class="
                                machine-live-kpi-v32
                                oee
                            "
                        >

                            <span>
                                OEE
                            </span>

                            <strong>

                                ${pctV47(
                                    row.oee_ratio
                                )}

                            </strong>

                        </div>

                    </div>


                    <div
                        class="machine-live-note-v32"
                    >

                        Session
                        ${escapeV47(
                            row.session_id
                        )}

                        |

                        ${escapeV47(
                            row.session_date
                            || ""
                        )}

                    </div>

                </section>
            `;


        } catch (error) {

            emptyV47(
                error.message
                ||
                "Unable to load Machine OEE."
            );
        }
    }


    /*
     * Make THIS the current KPI refresh function.
     *
     * It does not use activeRun/pendingRun.
     */
    try {

        machineOeeRefreshLiveCalcV1 =
            refreshV47;

    } catch (_) {
    }


    window.machineOeeRefreshLiveCalcV1 =
        refreshV47;


    window.machineOeeRefreshStoredSessionV47 =
        refreshV47;


    /*
     * Refresh whenever Shift changes.
     */
    const shiftSelect =
        document.getElementById(
            "machine-oee-shift-v1"
        );


    if (shiftSelect) {

        shiftSelect.addEventListener(
            "change",
            function() {

                window.setTimeout(
                    refreshV47,
                    80
                );
            }
        );
    }


    /*
     * Existing V32 has old delayed render calls.
     * Run after them once so persisted session KPI
     * becomes final owner of the right-side panel.
     *
     * This is not polling.
     */
    window.setTimeout(
        refreshV47,
        1200
    );


    window.setTimeout(
        refreshV47,
        1800
    );


    /*
     * Complete Job already reloads this page.
     * This early refresh is useful before that reload.
     */
    document.addEventListener(
        "click",
        function(event) {

            const button =
                event.target?.closest?.(
                    "#machine-oee-complete-btn-v1"
                );


            if (!button) {
                return;
            }


            window.setTimeout(
                refreshV47,
                500
            );

        },
        true
    );

})();

/* OEE_CORE_CURRENT_SESSION_KPI_FRONTEND_V47_END */


/* OEE_CORE_TYPED_KPI_PREVIEW_FRONTEND_V48 */

(function () {

    let timerV48 = null;


    function numberV48(
        id
    ) {

        const value =
            Number(
                document.getElementById(
                    id
                )?.value
                || 0
            );


        return Number.isFinite(value)
            ? value
            : 0;
    }


    function pctV48(
        value
    ) {

        if (
            value === null
            ||
            value === undefined
            ||
            value === ""
        ) {
            return "-";
        }


        const n = Number(value);


        if (!Number.isFinite(n)) {
            return "-";
        }


        return (
            n * 100
        ).toFixed(2) + "%";
    }


    function machineIdV48() {

        return Number(
            window
                .NMTG_MACHINE_OEE_CONTEXT
                ?.machine_id
            || 0
        );
    }


    function runExistsV48() {

        try {

            return Boolean(
                machineOeeActiveRunV1
                ||
                machineOeePendingRunV1
            );

        } catch (_) {

            return false;
        }
    }


    function lossRowsV48() {

        return Array.from(
            document.querySelectorAll(
                ".oee-direct-loss-input-v3"
            )
        )
        .map(
            function(input) {

                return {
                    loss_code:
                        String(
                            input.dataset
                                .lossCodeV3
                            || ""
                        ).trim(),

                    loss_minutes:
                        Number(
                            input.value
                            || 0
                        ) || 0
                };
            }
        );
    }


    function renderV48(
        data
    ) {

        const host =
            document.getElementById(
                "machine-live-oee-host-v1"
            );


        if (!host) {
            return;
        }


        host.innerHTML = `

            <section
                class="machine-live-v32"
            >

                <div
                    class="machine-live-head-v32"
                >

                    <strong>
                        Live Machine OEE
                    </strong>

                    <span>
                        Preview
                    </span>

                </div>


                <div
                    class="machine-live-kpis-v32"
                >

                    <div
                        class="machine-live-kpi-v32"
                    >

                        <span>
                            Plan vs Actual
                        </span>

                        <strong>
                            ${pctV48(
                                data.plan_vs_actual
                            )}
                        </strong>

                    </div>


                    <div
                        class="machine-live-kpi-v32"
                    >

                        <span>
                            PR
                        </span>

                        <strong>
                            ${pctV48(
                                data.pr_ratio
                            )}
                        </strong>

                    </div>


                    <div
                        class="
                            machine-live-kpi-v32
                            oee
                        "
                    >

                        <span>
                            OEE
                        </span>

                        <strong>
                            ${pctV48(
                                data.oee_ratio
                            )}
                        </strong>

                    </div>

                </div>

            </section>
        `;
    }


    async function refreshV48() {

        if (!runExistsV48()) {
            return;
        }


        const machineId =
            machineIdV48();


        if (!machineId) {
            return;
        }


        const losses =
            lossRowsV48();


        if (losses.length !== 27) {
            return;
        }


        const payload = {

            machine_id:
                machineId,

            oee_start_time:
                String(
                    document.getElementById(
                        "oee-direct-start-time-v3"
                    )?.value
                    || ""
                ).trim(),

            oee_end_time:
                String(
                    document.getElementById(
                        "oee-direct-stop-time-v3"
                    )?.value
                    || ""
                ).trim(),

            ok_qty:
                numberV48(
                    "machine-oee-ok-qty-v1"
                ),

            rejected_qty:
                numberV48(
                    "machine-oee-rejected-qty-v1"
                ),

            hold_qty:
                numberV48(
                    "machine-oee-hold-qty-v1"
                ),

            cycle_minutes:
                numberV48(
                    "machine-oee-cycle-min-v1"
                ),

            cycle_seconds:
                numberV48(
                    "machine-oee-cycle-sec-v1"
                ),

            load_unload_minutes:
                numberV48(
                    "machine-oee-load-min-v1"
                ),

            load_unload_seconds:
                numberV48(
                    "machine-oee-load-sec-v1"
                ),

            losses:
                losses
        };


        /*
         * Do not show misleading KPI until the
         * essential production values exist.
         */
        if (
            !payload.oee_start_time
            ||
            !payload.oee_end_time
            ||
            (
                payload.cycle_minutes === 0
                &&
                payload.cycle_seconds === 0
                &&
                payload.load_unload_minutes === 0
                &&
                payload.load_unload_seconds === 0
            )
        ) {
            return;
        }


        /*
         * MACHINE_OEE_LOCAL_KPI_PREVIEW_V1
         *
         * Live preview is calculated locally.
         *
         * IMPORTANT:
         * Final OEE calculation and validation on Complete
         * Process remain authoritative on the backend.
         */

        const machineNoV48 =
            String(
                window
                    .NMTG_MACHINE_OEE_CONTEXT
                    ?.machine_no
                || ""
            )
            .trim()
            .toUpperCase()
            .replace(
                /\\s+/g,
                " "
            );


        const allLossCodesV48 =
            Array.from(
                {
                    length:
                        27
                },
                function(_, index) {

                    return (
                        "A"
                        +
                        String(
                            index + 1
                        )
                    );
                }
            );


        const p01MachinesV48 =
            new Set([
                "CNC 01",
                "CNC 02"
            ]);


        const p02MachinesV48 =
            new Set([
                "CNC 03",
                "CNC 05",
                "CNC 06",
                "CNC 31"
            ]);


        const p06MachinesV48 =
            new Set([
                "CNC 15",
                "CNC 17",
                "VMC 01",
                "VMC 02",
                "VMC 03",

                "CNC 11",
                "CNC 19",
                "CNC 20",
                "CNC 27",

                "CNC 16",
                "CNC 24",
                "CNC 34",
                "VMC 04",
                "VMC 6",

                "CNC 10",
                "CNC 13",
                "CNC 22",
                "CNC 23",
                "CNC 25",
                "CNC 26",
                "CNC 28",
                "CNC 29",
                "CNC 33"
            ]);


        let arCodesV48 =
            null;

        let prCodesV48 =
            null;

        let targetDeductCodeV48 =
            "";


        if (
            p01MachinesV48.has(
                machineNoV48
            )
        ) {

            arCodesV48 =
                allLossCodesV48;

            prCodesV48 = [
                "A17",
                "A21",
                "A22"
            ];

            targetDeductCodeV48 =
                "A7";

        } else if (
            p02MachinesV48.has(
                machineNoV48
            )
        ) {

            arCodesV48 =
                allLossCodesV48;

            prCodesV48 = [
                "A17",
                "A21",
                "A22"
            ];

            targetDeductCodeV48 =
                "A8";

        } else if (
            p06MachinesV48.has(
                machineNoV48
            )
        ) {

            prCodesV48 = [
                "A4",
                "A6",
                "A9",
                "A16"
            ];


            const prSetV48 =
                new Set(
                    prCodesV48
                );


            arCodesV48 =
                allLossCodesV48.filter(
                    function(code) {

                        return !prSetV48.has(
                            code
                        );
                    }
                );


            targetDeductCodeV48 =
                "A7";

        } else {

            /*
             * CNC 32 and any machine without a confirmed
             * Excel formula profile remain intentionally
             * unsupported.
             */
            return;
        }


        const lossMapV48 =
            Object.create(
                null
            );


        for (
            const item
            of losses
        ) {

            const code =
                String(
                    item.loss_code
                    || ""
                )
                .trim()
                .toUpperCase();


            const minutes =
                Math.max(
                    Number(
                        item.loss_minutes
                        || 0
                    )
                    || 0,
                    0
                );


            if (code) {

                lossMapV48[
                    code
                ] = minutes;
            }
        }


        const sumCodesV48 =
            function(codes) {

                return codes.reduce(
                    function(total, code) {

                        return (
                            total
                            +
                            Number(
                                lossMapV48[
                                    code
                                ]
                                || 0
                            )
                        );
                    },
                    0
                );
            };


        /*
         * Match backend time calculation:
         *
         * default = 660 minutes
         * valid Start + Stop = actual duration
         * cross-midnight is supported.
         */
        const timeToSecondsV48 =
            function(value) {

                const match =
                    String(
                        value
                        || ""
                    )
                    .trim()
                    .match(
                        /^(\d{2}):(\d{2})(?::(\d{2}))?$/
                    );


                if (!match) {
                    return null;
                }


                const hour =
                    Number(
                        match[1]
                    );

                const minute =
                    Number(
                        match[2]
                    );

                const second =
                    Number(
                        match[3]
                        || 0
                    );


                if (
                    hour > 23
                    ||
                    minute > 59
                    ||
                    second > 59
                ) {
                    return null;
                }


                return (
                    hour * 3600
                    +
                    minute * 60
                    +
                    second
                );
            };


        let plannedMinutesV48 =
            660;


        const startSecondsV48 =
            timeToSecondsV48(
                payload.oee_start_time
            );

        const endSecondsV48 =
            timeToSecondsV48(
                payload.oee_end_time
            );


        if (
            startSecondsV48
            !== null
            &&
            endSecondsV48
            !== null
        ) {

            let diffSecondsV48 =
                endSecondsV48
                -
                startSecondsV48;


            if (
                diffSecondsV48 < 0
            ) {

                diffSecondsV48 +=
                    24 * 60 * 60;
            }


            plannedMinutesV48 =
                Math.max(
                    diffSecondsV48
                    / 60,
                    0
                );
        }


        const okQtyV48 =
            Math.max(
                Number(
                    payload.ok_qty
                    || 0
                )
                || 0,
                0
            );


        const rejectedQtyV48 =
            Math.max(
                Number(
                    payload.rejected_qty
                    || 0
                )
                || 0,
                0
            );


        const holdQtyV48 =
            Math.max(
                Number(
                    payload.hold_qty
                    || 0
                )
                || 0,
                0
            );


        const totalQtyV48 =
            okQtyV48
            +
            rejectedQtyV48
            +
            holdQtyV48;


        const idealCycleMinutesV48 =
            Math.max(
                Number(
                    payload.cycle_minutes
                    || 0
                )
                || 0,
                0
            )
            +
            (
                Math.max(
                    Number(
                        payload.cycle_seconds
                        || 0
                    )
                    || 0,
                    0
                )
                / 60
            )
            +
            Math.max(
                Number(
                    payload.load_unload_minutes
                    || 0
                )
                || 0,
                0
            )
            +
            (
                Math.max(
                    Number(
                        payload.load_unload_seconds
                        || 0
                    )
                    || 0,
                    0
                )
                / 60
            );


        const runMinutesV48 =
            okQtyV48
            *
            idealCycleMinutesV48;


        const arLossV48 =
            sumCodesV48(
                arCodesV48
            );


        const prLossV48 =
            sumCodesV48(
                prCodesV48
            );


        const targetDeductMinutesV48 =
            Number(
                lossMapV48[
                    targetDeductCodeV48
                ]
                || 0
            );


        const availableTimeV48 =
            plannedMinutesV48;


        const utilizationV48 =
            Math.max(
                availableTimeV48
                -
                arLossV48,
                0
            );


        const afterPrV48 =
            Math.max(
                utilizationV48
                -
                prLossV48,
                0
            );


        const arRatioV48 =
            availableTimeV48
            ?
                utilizationV48
                /
                availableTimeV48
            :
                0;


        const prRatioV48 =
            afterPrV48
            ?
                runMinutesV48
                /
                afterPrV48
            :
                0;


        const qrRatioV48 =
            totalQtyV48
            ?
                okQtyV48
                /
                totalQtyV48
            :
                0;


        const oeeRatioV48 =
            arRatioV48
            *
            prRatioV48
            *
            qrRatioV48;


        let targetQtyV48 =
            null;

        let planVsActualV48 =
            null;


        if (
            idealCycleMinutesV48 > 0
        ) {

            const targetMinutesV48 =
                Math.max(
                    plannedMinutesV48
                    -
                    targetDeductMinutesV48,
                    0
                );


            targetQtyV48 =
                targetMinutesV48
                /
                idealCycleMinutesV48;


            if (
                targetQtyV48 > 0
            ) {

                planVsActualV48 =
                    totalQtyV48
                    /
                    targetQtyV48;
            }
        }


        renderV48({
            success:
                true,

            calculation_ready:
                true,

            planned_minutes:
                plannedMinutesV48,

            run_minutes:
                runMinutesV48,

            ideal_cycle_minutes:
                idealCycleMinutesV48,

            ar_loss:
                arLossV48,

            pr_loss:
                prLossV48,

            target_deduct_minutes:
                targetDeductMinutesV48,

            target_qty:
                targetQtyV48,

            plan_vs_actual:
                planVsActualV48,

            ar_ratio:
                arRatioV48,

            pr_ratio:
                prRatioV48,

            qr_ratio:
                qrRatioV48,

            oee_ratio:
                oeeRatioV48
        });
    }


    function scheduleV48() {

        window.clearTimeout(
            timerV48
        );


        timerV48 =
            window.setTimeout(
                refreshV48,
                1200
            );
    }


    /*
     * Event delegation is required because the
     * Direct Entry controls are rendered dynamically.
     */
    document.addEventListener(
        "input",
        function(event) {

            const target =
                event.target;


            if (!target) {
                return;
            }


            if (
                target.matches(
                    "#oee-direct-start-time-v3,"
                    + "#oee-direct-stop-time-v3,"
                    + "#oee-direct-cycle-hms-v34,"
                    + "#oee-direct-load-hms-v34,"
                    + "#machine-oee-ok-qty-v1,"
                    + "#machine-oee-rejected-qty-v1,"
                    + "#machine-oee-hold-qty-v1,"
                    + ".oee-direct-loss-input-v3"
                )
            ) {

                /*
                 * V34 synchronizes visible HH:MM:SS
                 * back to hidden minute/second fields.
                 */
                window.setTimeout(
                    scheduleV48,
                    30
                );
            }
        },
        true
    );


    document.addEventListener(
        "change",
        function(event) {

            const target =
                event.target;


            if (
                target
                &&
                target.matches(
                    "#oee-direct-start-time-v3,"
                    + "#oee-direct-stop-time-v3,"
                    + "#oee-direct-cycle-hms-v34,"
                    + "#oee-direct-load-hms-v34,"
                    + "#machine-oee-ok-qty-v1,"
                    + "#machine-oee-rejected-qty-v1,"
                    + "#machine-oee-hold-qty-v1,"
                    + ".oee-direct-loss-input-v3"
                )
            ) {

                window.setTimeout(
                    scheduleV48,
                    30
                );
            }
        },
        true
    );


    window.machineOeeRefreshTypedKpiV48 =
        refreshV48;


    window.setTimeout(
        scheduleV48,
        1000
    );

})();

/* OEE_CORE_TYPED_KPI_PREVIEW_FRONTEND_V48_END */


/* OEE_CORE_REASON_STATE_V49 */

(function () {

    /*
     * Reason controls are dynamic.
     *
     * Preserve the operator's selected reason even if
     * another OEE renderer rebuilds the reason fields.
     */
    const state =
        window.machineOeeReasonStateV49
        || {
            rejection: {
                touched:false,
                value:""
            },

            hold: {
                touched:false,
                value:""
            }
        };


    window.machineOeeReasonStateV49 =
        state;


    function stateForV49(
        type
    ) {

        return (
            type === "hold"
            ? state.hold
            : state.rejection
        );
    }


    function idsV49(
        type
    ) {

        const isHold =
            type === "hold";


        return {
            select:
                isHold
                ? "machine-oee-hold-reason-v9"
                : "machine-oee-rejection-reason-v1",

            other:
                isHold
                ? "machine-oee-hold-other-v9"
                : "machine-oee-rejection-other-v9"
        };
    }


    function readDomV49(
        type
    ) {

        const ids =
            idsV49(
                type
            );


        const select =
            document.getElementById(
                ids.select
            );


        if (!select) {
            return "";
        }


        const selected =
            String(
                select.value
                || ""
            ).trim();


        if (
            selected !== "Other"
        ) {

            return selected;
        }


        return String(
            document.getElementById(
                ids.other
            )?.value
            || ""
        ).trim();
    }


    function rememberV49(
        type
    ) {

        const target =
            stateForV49(
                type
            );


        target.touched =
            true;


        target.value =
            readDomV49(
                type
            );
    }


    /*
     * Cache operator selection immediately.
     */
    document.addEventListener(
        "change",
        function (event) {

            const id =
                String(
                    event.target?.id
                    || ""
                );


            if (
                id ===
                "machine-oee-hold-reason-v9"
            ) {

                rememberV49(
                    "hold"
                );

                return;
            }


            if (
                id ===
                "machine-oee-rejection-reason-v1"
            ) {

                rememberV49(
                    "rejection"
                );
            }

        },
        true
    );


    /*
     * Cache custom "Other" text too.
     */
    document.addEventListener(
        "input",
        function (event) {

            const id =
                String(
                    event.target?.id
                    || ""
                );


            if (
                id ===
                "machine-oee-hold-other-v9"
            ) {

                rememberV49(
                    "hold"
                );

                return;
            }


            if (
                id ===
                "machine-oee-rejection-other-v9"
            ) {

                rememberV49(
                    "rejection"
                );
            }

        },
        true
    );


    /*
     * If a dynamic renderer rebuilds a reason control,
     * restore the selected value into the new control.
     */
    const buildBaseV49 =
        window.machineOeeBuildReasonControlV9;


    window.machineOeeBuildReasonControlV9 =
        function (
            type,
            slot,
            oldValue
        ) {

            const saved =
                stateForV49(
                    type
                );


            const restoreValue =
                saved.touched
                ? saved.value
                : oldValue;


            return buildBaseV49(
                type,
                slot,
                restoreValue
            );
        };


    /*
     * Completion validation uses this function.
     *
     * Prefer current DOM value.
     * If the field was just rebuilt and is temporarily
     * blank, use the operator's cached selection.
     */
    const valueBaseV49 =
        window.machineOeeReasonValueV9;


    window.machineOeeReasonValueV9 =
        function (
            type
        ) {

            const current =
                String(
                    valueBaseV49(
                        type
                    )
                    || ""
                ).trim();


            const saved =
                stateForV49(
                    type
                );


            if (current) {

                saved.touched =
                    true;

                saved.value =
                    current;

                return current;
            }


            if (
                saved.touched
            ) {

                return String(
                    saved.value
                    || ""
                ).trim();
            }


            return "";
        };


    /*
     * When Qty returns to zero, the existing reset must
     * also clear our cached reason.
     */
    const resetBaseV49 =
        window.machineOeeResetReasonV9;


    window.machineOeeResetReasonV9 =
        function (
            type
        ) {

            const result =
                resetBaseV49(
                    type
                );


            const saved =
                stateForV49(
                    type
                );


            saved.touched =
                false;

            saved.value =
                "";


            return result;
        };


})();

/* OEE_CORE_REASON_STATE_V49_END */


/* OEE_CORE_REASON_RUN_STORAGE_V50 */

(function () {

    function currentRunV50() {

        try {

            return (
                machineOeeActiveRunV1
                ||
                machineOeePendingRunV1
                ||
                null
            );

        } catch (_) {

            return null;
        }
    }


    function idsV50(
        type
    ) {

        if (
            type === "hold"
        ) {

            return {
                select:
                    "machine-oee-hold-reason-v9",

                other:
                    "machine-oee-hold-other-v9"
            };
        }


        return {
            select:
                "machine-oee-rejection-reason-v1",

            other:
                "machine-oee-rejection-other-v9"
        };
    }


    function keyV50(
        type,
        run
    ) {

        const runId =
            Number(
                run?.run_id
                || 0
            );


        if (runId <= 0) {
            return "";
        }


        return (
            "nmtg_oee_reason_v50_"
            + runId
            + "_"
            + type
        );
    }


    function readDomV50(
        type
    ) {

        const ids =
            idsV50(
                type
            );


        const select =
            document.getElementById(
                ids.select
            );


        if (!select) {

            return {
                selected:"",
                value:""
            };
        }


        const selected =
            String(
                select.value
                || ""
            ).trim();


        if (!selected) {

            return {
                selected:"",
                value:""
            };
        }


        if (
            selected !== "Other"
        ) {

            return {
                selected:
                    selected,

                value:
                    selected
            };
        }


        const other =
            String(
                document.getElementById(
                    ids.other
                )?.value
                || ""
            ).trim();


        return {
            selected:
                "Other",

            value:
                other
        };
    }


    function saveV50(
        type
    ) {

        const run =
            currentRunV50();


        const key =
            keyV50(
                type,
                run
            );


        if (!key) {
            return;
        }


        const data =
            readDomV50(
                type
            );


        if (!data.selected) {
            return;
        }


        try {

            sessionStorage.setItem(
                key,
                JSON.stringify(
                    data
                )
            );

        } catch (_) {
        }
    }


    function loadV50(
        type,
        run
    ) {

        const key =
            keyV50(
                type,
                run
            );


        if (!key) {
            return null;
        }


        try {

            const raw =
                sessionStorage.getItem(
                    key
                );


            if (!raw) {
                return null;
            }


            const data =
                JSON.parse(
                    raw
                );


            if (
                !data
                ||
                !data.selected
            ) {
                return null;
            }


            return {
                selected:
                    String(
                        data.selected
                        || ""
                    ).trim(),

                value:
                    String(
                        data.value
                        || ""
                    ).trim()
            };

        } catch (_) {

            return null;
        }
    }


    /*
     * This is now the authoritative getter used by
     * Complete Job.
     */
    window.machineOeeCoreReasonValueV50 =
        function (
            type,
            run
        ) {

            const current =
                readDomV50(
                    type
                );


            if (
                current.selected
                &&
                current.value
            ) {

                const key =
                    keyV50(
                        type,
                        run
                    );


                if (key) {

                    try {

                        sessionStorage.setItem(
                            key,
                            JSON.stringify(
                                current
                            )
                        );

                    } catch (_) {
                    }
                }


                return current.value;
            }


            const saved =
                loadV50(
                    type,
                    run
                );


            return String(
                saved?.value
                || ""
            ).trim();
        };


    /*
     * Save immediately when operator chooses a reason.
     */
    document.addEventListener(
        "change",
        function (
            event
        ) {

            const id =
                String(
                    event.target?.id
                    || ""
                );


            if (
                id ===
                "machine-oee-hold-reason-v9"
            ) {

                saveV50(
                    "hold"
                );

                return;
            }


            if (
                id ===
                "machine-oee-rejection-reason-v1"
            ) {

                saveV50(
                    "rejection"
                );
            }

        },
        true
    );


    /*
     * Save custom Other text while typing.
     */
    document.addEventListener(
        "input",
        function (
            event
        ) {

            const id =
                String(
                    event.target?.id
                    || ""
                );


            if (
                id ===
                "machine-oee-hold-other-v9"
            ) {

                saveV50(
                    "hold"
                );

                return;
            }


            if (
                id ===
                "machine-oee-rejection-other-v9"
            ) {

                saveV50(
                    "rejection"
                );
            }

        },
        true
    );


})();

/* OEE_CORE_REASON_RUN_STORAGE_V50_END */


/* OEE_UI_CLEANUP_V58 */

(function () {

    let detailRequestV58 = null;


    function cleanV58(
        value
    ) {

        return String(
            value ?? ""
        ).trim();
    }


    function escV58(
        value
    ) {

        return cleanV58(
            value
        )
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );
    }


    function todayV58() {

        const d =
            new Date();


        return (
            d.getFullYear()
            + "-"
            + String(
                d.getMonth() + 1
            ).padStart(
                2,
                "0"
            )
            + "-"
            + String(
                d.getDate()
            ).padStart(
                2,
                "0"
            )
        );
    }


    function currentRunV58() {

        try {

            return (
                machineOeeActiveRunV1
                ||
                machineOeePendingRunV1
                ||
                null
            );

        } catch (_) {

            return null;
        }
    }


    /* -----------------------------------------------------
       DATE
       ----------------------------------------------------- */

    function ensureDateV58() {

        const controls =
            document.querySelector(
                ".machine-shift-controls-v11"
            );


        if (!controls) {
            return;
        }


        let field =
            document.getElementById(
                "oee-ui-date-field-v58"
            );


        if (!field) {

            field =
                document.createElement(
                    "div"
                );


            field.id =
                "oee-ui-date-field-v58";


            field.className =
                "machine-shift-control-v11 "
                + "oee-ui-date-control-v58";


            field.innerHTML = `

                <label
                    for="oee-ui-date-v58"
                >

                    <i
                        class="fa fa-calendar"
                        aria-hidden="true"
                    ></i>

                    Date

                </label>


                <input
                    id="oee-ui-date-v58"
                    type="date"
                    value="${todayV58()}"
                >
            `;


            controls.insertBefore(
                field,
                controls.firstChild
            );


            document.getElementById(
                "oee-ui-date-v58"
            )?.addEventListener(
                "change",
                syncDateV58
            );
        }


        syncDateV58();
    }


    function syncDateV58() {

        const top =
            document.getElementById(
                "oee-ui-date-v58"
            );


        const real =
            document.getElementById(
                "oee-loss-entry-date-v16"
            );


        if (
            !top
            ||
            !real
        ) {
            return;
        }


        if (
            !top.dataset.initializedV58
        ) {

            if (
                cleanV58(
                    real.value
                )
            ) {

                top.value =
                    real.value;
            }


            top.dataset.initializedV58 =
                "1";
        }


        if (
            cleanV58(
                top.value
            )
        ) {

            real.value =
                top.value;
        }


        const dateField =
            real.closest(
                ".oee-loss-period-field-v16"
            );


        if (dateField) {

            dateField.classList.add(
                "oee-ui-hide-loss-date-v58"
            );
        }


        const period =
            document.getElementById(
                "oee-loss-period-v16"
            );


        const grid =
            period?.querySelector(
                ".oee-loss-period-grid-v16"
            );


        if (grid) {

            grid.style.gridTemplateColumns =
                "repeat(2,minmax(150px,1fr))";
        }


        /*
         * When a JC is running, loss Start/End use
         * Production Start/Stop, therefore the old
         * loss-period box has no visible purpose.
         */
        if (period) {

            period.style.display =
                currentRunV58()
                ? "none"
                : "";
        }
    }


    /* -----------------------------------------------------
       JC DATA
       ----------------------------------------------------- */

    async function fetchDetailsV58(
        jc
    ) {

        const jobCard =
            cleanV58(
                jc
            );


        if (!jobCard) {
            return null;
        }


        const cache =
            window.machineOeeUiDataV58
            || {};


        if (
            cache.jobCard
            === jobCard
            &&
            cache.data
        ) {

            return cache.data;
        }


        if (
            detailRequestV58
            &&
            detailRequestV58.jobCard
            === jobCard
        ) {

            return await
                detailRequestV58.promise;
        }


        const promise =
            (async function () {

                try {

                    const response =
                        await fetch(
                            "/api/quality_check/fetch/"
                            +
                            encodeURIComponent(
                                jobCard
                            ),
                            {
                                cache:
                                    "no-store"
                            }
                        );


                    const data =
                        await response.json();


                    if (
                        !response.ok
                        ||
                        data.success === false
                    ) {

                        return null;
                    }


                    window.machineOeeUiDataV58 = {
                        jobCard:
                            jobCard,

                        data:
                            data
                    };


                    return data;


                } catch (_) {

                    return null;
                }

            })();


        detailRequestV58 = {
            jobCard:
                jobCard,

            promise:
                promise
        };


        const result =
            await promise;


        detailRequestV58 =
            null;


        return result;
    }


    function matchingItemV58(
        data,
        run
    ) {

        const items =
            Array.isArray(
                data?.items
            )
                ? data.items
                : [];


        const wanted =
            cleanV58(
                run?.item_name
            ).toLowerCase();


        if (wanted) {

            const found =
                items.find(
                    function (
                        item
                    ) {

                        return (
                            cleanV58(
                                item?.item_name
                            ).toLowerCase()
                            === wanted
                        );
                    }
                );


            if (found) {
                return found;
            }
        }


        return (
            items[0]
            || {}
        );
    }


    function sizeV58(
        item
    ) {

        const name =
            cleanV58(
                item?.item_name
            );


        const marker =
            " - ";


        const pos =
            name.lastIndexOf(
                marker
            );


        if (
            pos >= 0
            &&
            pos + marker.length
                < name.length
        ) {

            return name.slice(
                pos + marker.length
            ).trim();
        }


        const dia =
            cleanV58(
                item?.dia
            );


        const length =
            cleanV58(
                item?.length
            );


        if (
            dia
            &&
            length
        ) {

            return (
                dia
                + " x "
                + length
            );
        }


        return "";
    }


    function nextProcessV58(
        item,
        current
    ) {

        const list =
            Array.isArray(
                item?.processes
            )
                ? item.processes
                : [];


        const wanted =
            cleanV58(
                current
            ).toLowerCase();


        const index =
            list.findIndex(
                function (
                    process
                ) {

                    return (
                        cleanV58(
                            process
                        ).toLowerCase()
                        === wanted
                    );
                }
            );


        if (
            index >= 0
            &&
            index + 1 < list.length
        ) {

            return cleanV58(
                list[
                    index + 1
                ]
            );
        }


        return "";
    }


    function cellV58(
        label,
        value,
        wide=false
    ) {

        const text =
            cleanV58(
                value
            );


        if (!text) {
            return "";
        }


        return `

            <div
                class="
                    oee-ui-jc-info-v58
                    ${wide ? "wide" : ""}
                "
            >

                <span>
                    ${escV58(label)}
                </span>

                <strong>
                    ${escV58(text)}
                </strong>

            </div>
        `;
    }


    function processCellV58(currentProcess, runId) {

        const text = cleanV58(currentProcess) || "";

        const _opts = [
            "CNC Machining",
            "CNC Machining 1st Side",
            "CNC Machining 2nd Side",
            "CNC Machining 3rd Side",
            "CNC Machining 4th Side",
            "CNC Machining 5th Side"
        ];

        const _listId = "oee-process-list-v58";

        const _optHtml = _opts.map(function(o) {
            return '<option value="' + escV58(o) + '"></option>';
        }).join("");

        return `
            <div class="oee-ui-jc-info-v58 oee-process-cell-v58">
                <span>Current Process</span>
                <datalist id="${_listId}">${_optHtml}</datalist>
                <input
                    type="text"
                    class="oee-process-input-v58"
                    list="${_listId}"
                    value="${escV58(text)}"
                    placeholder="Select or type process..."
                    autocomplete="off"
                    data-run-id="${escV58(String(runId || ""))}"
                >
            </div>
        `;
    }


    async function completionCardV58(
        run
    ) {

        if (
            !run
            ||
            !run.run_id
        ) {

            return null;
        }


        try {

            const data =
                await window
                    .machineOeeGetCompletionContextSharedV1(
                        run.run_id
                    );


            return (
                data?.card
                || null
            );


        } catch (_) {

            return null;
        }
    }


    function buildDetailsV58(
        data,
        run,
        completion
    ) {

        const item =
            matchingItemV58(
                data,
                run
            );


        const currentProcess =
            cleanV58(
                run?.process_name
                ||
                completion?.current_process
                ||
                item?.wip_status
            );


        const nextProcess =
            cleanV58(
                completion?.next_process
            )
            ||
            nextProcessV58(
                item,
                currentProcess
            );


        return `

            <div
                class="
                    oee-ui-jc-grid-v58
                    oee-ui-jc-grid-compact-v70
                "
            >

                ${cellV58(
                    "Item / Model",
                    item?.item_name
                    || run?.item_name
                )}


                ${processCellV58(
                    currentProcess,
                    run?.run_id
                )}


                ${cellV58(
                    "Next Process",
                    nextProcess
                )}

            </div>
        `;
    }


    /* -----------------------------------------------------
       RUNNING CARD
       ----------------------------------------------------- */

    async function decorateRunningV58() {

        const run =
            currentRunV58();


        if (
            !run
            ||
            !run.job_card_no
        ) {

            return;
        }


        const card =
            document.querySelector(
                "#machine-oee-jc-result-v1 "
                + ".pending-machine-v1"
            )
            ||
            document.querySelector(
                "#machine-oee-jc-result-v1 "
                + ".machine-running-v1"
            );


        if (!card) {
            return;
        }


        const key =
            String(
                run.run_id
                || run.job_card_no
            );


        if (
            card.dataset.uiV58
            === key
        ) {

            syncDateV58();

            return;
        }


        const data =
            await fetchDetailsV58(
                run.job_card_no
            );


        if (!data) {
            return;
        }


        /* render immediately with null; completion fills in async below */
        const completion = null;


        const oldGrid =
            card.querySelector(
                ".jc-state-grid-v1"
            );


        if (oldGrid) {

            oldGrid.classList.add(
                "oee-ui-old-current-grid-v58"
            );
        }


        const helper =
            card.querySelector(
                ".helper"
            );


        if (helper) {

            helper.style.display =
                "none";
        }


        const paragraph =
            card.querySelector(
                "p"
            );


        if (paragraph) {

            paragraph.style.display =
                "none";
        }


        const heading =
            card.querySelector(
                "h3"
            )
            ||
            card.querySelector(
                ".machine-running-head-v1 strong"
            );


        if (heading) {

            heading.innerHTML =
                '<i class="fa fa-file-text-o" '
                +
                'aria-hidden="true"></i> '
                +
                'Job Card Details';
        }


        let details =
            card.querySelector(
                ".oee-ui-jc-details-v58"
            );


        if (!details) {

            details =
                document.createElement(
                    "div"
                );


            details.className =
                "oee-ui-jc-details-v58";


            card.appendChild(
                details
            );
        }


        function _wireProcV58(det) {
            var _pi = det.querySelector(".oee-process-input-v58");
            if (!_pi || !run || !run.run_id) { return; }
            _pi.addEventListener("change", async function () {
                var _np = (_pi.value || "").trim();
                if (!_np) { return; }
                _pi.disabled = true;
                try {
                    var _r = await fetch(
                        "/api/oee-machine/run/" + run.run_id + "/process",
                        {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ process_name: _np })
                        }
                    );
                    if (!_r.ok) {
                        alert("Could not update process. Please try again.");
                    }
                } catch (_e) {
                    alert("Network error updating process.");
                } finally {
                    _pi.disabled = false;
                }
            });
        }

        details.innerHTML = buildDetailsV58(data, run, completion);
        _wireProcV58(details);

        card.dataset.uiV58 = key;

        /* async: re-render with real completion data (available qty etc.) */
        completionCardV58(run).then(function (_comp) {
            if (!_comp || !details.isConnected) { return; }
            details.innerHTML = buildDetailsV58(data, run, _comp);
            _wireProcV58(details);
        });


        syncDateV58();
    }


    /* -----------------------------------------------------
       READY CARD AFTER FETCH

       Receive Material warning is deliberately untouched
       because its Received Qty field is functional.
       ----------------------------------------------------- */

    async function decorateReadyV58() {

        const fetched =
            window
                .machineOeeCurrentFetchedJcV1
            || null;


        if (
            !fetched
            ||
            !fetched.job_card_no
        ) {

            return;
        }


        const card =
            document.querySelector(
                "#machine-oee-jc-result-v1 "
                + ".jc-state-v1.success"
            );


        if (!card) {
            return;
        }


        const data =
            await fetchDetailsV58(
                fetched.job_card_no
            );


        if (!data) {
            return;
        }


        const oldGrid =
            card.querySelector(
                ".jc-state-grid-v1"
            );


        if (oldGrid) {

            oldGrid.classList.add(
                "oee-ui-old-current-grid-v58"
            );
        }


        let details =
            card.querySelector(
                ".oee-ui-jc-details-v58"
            );


        if (!details) {

            details =
                document.createElement(
                    "div"
                );


            details.className =
                "oee-ui-jc-details-v58";


            const action =
                card.querySelector(
                    ".jc-action-v1"
                );


            if (action) {

                card.insertBefore(
                    details,
                    action
                );

            } else {

                card.appendChild(
                    details
                );
            }
        }


        details.innerHTML =
            buildDetailsV58(
                data,
                {
                    job_card_no:
                        fetched.job_card_no,

                    item_name:
                        fetched.item_name,

                    process_name:
                        fetched.current_process
                        ||
                        fetched.wip_status
                },
                {
                    current_process:
                        fetched.current_process
                        ||
                        fetched.wip_status,

                    next_process:
                        fetched.next_process,

                    available_qty:
                        fetched.available_qty
                        ??
                        fetched.job_card_qty
                        ??
                        ""
                }
            );
    }


    /* -----------------------------------------------------
       APPLY
       ----------------------------------------------------- */

    async function applyV58() {

        ensureDateV58();

        syncDateV58();

        await decorateReadyV58();

        await decorateRunningV58();
    }


    /*
     * Wrap only existing render entry points.
     *
     * No MutationObserver.
     * No polling.
     */


    if (
        typeof machineOeeCheckPendingV1
        === "function"
    ) {

        const basePendingV58 =
            machineOeeCheckPendingV1;


        machineOeeCheckPendingV1 =
            async function () {

                const result =
                    await basePendingV58();


                window.setTimeout(
                    applyV58,
                    80
                );


                window.setTimeout(
                    applyV58,
                    350
                );


                return result;
            };
    }


    if (
        typeof machineOeeRenderRunningRunV1
        === "function"
    ) {

        const baseRunningV58 =
            machineOeeRenderRunningRunV1;


        machineOeeRenderRunningRunV1 =
            function (
                run
            ) {

                const result =
                    baseRunningV58(
                        run
                    );


                window.setTimeout(
                    applyV58,
                    80
                );


                window.setTimeout(
                    applyV58,
                    350
                );


                return result;
            };
    }


    if (
        typeof machineOeeFetchJcV1
        === "function"
    ) {

        const baseFetchV58 =
            machineOeeFetchJcV1;


        machineOeeFetchJcV1 =
            async function () {

                const result =
                    await baseFetchV58();


                window.setTimeout(
                    applyV58,
                    80
                );


                return result;
            };
    }


    window.machineOeeUiApplyV58 =
        applyV58;


    window.setTimeout(
        applyV58,
        150
    );


    window.setTimeout(
        applyV58,
        700
    );


    window.setTimeout(
        applyV58,
        1500
    );

})();

/* OEE_UI_CLEANUP_V58_END */


/* =========================================================
   OEE_COMPACT_MACHINE_KPI_BAR_V59
   UI ONLY
   ========================================================= */

(function () {

    let attemptsV59 = 0;
    let observerV59 = null;


    function shortLabelsV59() {

        const host =
            document.getElementById(
                "machine-live-oee-host-v1"
            );


        if (!host) {
            return;
        }


        const labels =
            host.querySelectorAll(
                ".machine-live-kpi-v32 span,"
                +
                ".machine-live-kpi-v25 span"
            );


        labels.forEach(
            function (label) {

                const text =
                    String(
                        label.textContent
                        || ""
                    )
                    .replace(
                        /\s+/g,
                        " "
                    )
                    .trim()
                    .toLowerCase();


                if (
                    text ===
                    "plan vs actual"
                ) {

                    label.textContent =
                        "PVA";
                }
            }
        );
    }


    function applyV59() {

        const switcher =
            document.getElementById(
                "oee-machine-switcher-v27"
            )
            ||
            document.querySelector(
                ".oee-machine-switcher-v27"
            );


        const kpiHost =
            document.getElementById(
                "machine-live-oee-host-v1"
            );


        if (
            !switcher
            ||
            !kpiHost
        ) {

            return false;
        }


        switcher.classList.add(
            "oee-machine-kpi-bar-v59"
        );


        let slot =
            document.getElementById(
                "oee-machine-kpi-slot-v59"
            );


        if (!slot) {

            slot =
                document.createElement(
                    "div"
                );


            slot.id =
                "oee-machine-kpi-slot-v59";


            slot.className =
                "oee-machine-kpi-slot-v59";


            switcher.appendChild(
                slot
            );
        }


        /*
         * Move the existing KPI host.
         *
         * getElementById() still finds the same node,
         * so existing V47/V48 KPI rendering continues.
         */
        if (
            kpiHost.parentElement
            !== slot
        ) {

            slot.appendChild(
                kpiHost
            );
        }


        /*
         * Old right-side Machine Context becomes redundant.
         */
        const aside =
            document.querySelector(
                ".workspace-grid > aside"
            );


        if (aside) {

            aside.classList.add(
                "oee-aside-compact-hidden-v59"
            );
        }


        shortLabelsV59();


        /*
         * KPI innerHTML changes whenever live/stored OEE
         * refreshes. Observe ONLY this KPI node.
         *
         * No OEE initialization or API call is triggered.
         */
        if (!observerV59) {

            observerV59 =
                new MutationObserver(
                    function () {

                        shortLabelsV59();
                    }
                );


            observerV59.observe(
                kpiHost,
                {
                    childList:
                        true,

                    subtree:
                        true
                }
            );
        }


        return true;
    }


    function startV59() {

        if (
            applyV59()
        ) {

            return;
        }


        attemptsV59 += 1;


        if (
            attemptsV59 < 30
        ) {

            window.setTimeout(
                startV59,
                100
            );
        }
    }


    window.setTimeout(
        startV59,
        50
    );


    window.addEventListener(
        "load",
        startV59
    );


    window.oeeCompactMachineKpiV59 =
        applyV59;

})();

/* OEE_COMPACT_MACHINE_KPI_BAR_V59_END */


/* OEE_FIRST_TWO_SECTIONS_V61 */

(function () {

    const contextV61 =
        window.NMTG_MACHINE_OEE_CONTEXT
        || {};


    /* -----------------------------------------------------
       SECTION 1 - LOAD ZONE MACHINES INTO NEW TOP STRIP

       Uses the EXISTING read-only Zone Workspace API.
       No WIP / OEE / DB logic is changed.
       ----------------------------------------------------- */

    function escapeV61(value) {

        return String(
            value === null
            || value === undefined
                ? ""
                : value
        )
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }


    function machinesFromResponseV61(data) {

        if (
            Array.isArray(
                data?.machines
            )
        ) {

            return data.machines;
        }


        if (
            Array.isArray(
                data?.zones
            )
        ) {

            const currentZone =
                String(
                    contextV61.zone
                    || ""
                )
                .trim()
                .toUpperCase();


            const zoneRow =
                data.zones.find(
                    function(row) {

                        return (
                            String(
                                row?.zone
                                || ""
                            )
                            .trim()
                            .toUpperCase()
                            === currentZone
                        );
                    }
                );


            if (
                Array.isArray(
                    zoneRow?.machines
                )
            ) {

                return zoneRow.machines;
            }
        }


        return [];
    }


    function renderMachineTabsV61(
        machines
    ) {

        const host =
            document.getElementById(
                "oee-sph-tabs-v60"
            );


        if (!host) {
            return;
        }


        const currentId =
            Number(
                contextV61.machine_id
                || 0
            );


        host.innerHTML =
            "";


        const rows =
            Array.isArray(machines)
                ? machines
                : [];


        for (
            const machine
            of rows
        ) {

            const id =
                Number(
                    machine?.id
                    || 0
                );


            if (!id) {
                continue;
            }


            const link =
                document.createElement(
                    "a"
                );


            link.className =
                "oee-sph-tab-v60";


            if (
                id === currentId
            ) {

                link.classList.add(
                    "active"
                );
            }


            link.href =
                "/oee-machine/operator?machine_id="
                +
                encodeURIComponent(id);


            link.dataset.machineId =
                String(id);


            link.title =
                String(
                    machine?.machine_name
                    || machine?.machine_no
                    || ""
                );


            const dot =
                document.createElement(
                    "span"
                );


            dot.className =
                "oee-sph-tab-dot-v60";


            const label =
                document.createElement(
                    "span"
                );


            label.textContent =
                String(
                    machine?.machine_no
                    || ""
                );


            link.appendChild(dot);

            link.appendChild(label);

            host.appendChild(link);
        }


        /*
         * Safety fallback:
         * never leave the top machine strip blank.
         */
        if (
            !host.children.length
            &&
            currentId
        ) {

            host.innerHTML = `

                <a
                    class="oee-sph-tab-v60 active"
                    href="#"
                >

                    <span
                        class="oee-sph-tab-dot-v60"
                    ></span>

                    <span>
                        ${escapeV61(
                            contextV61.machine_no
                            || "Machine"
                        )}
                    </span>

                </a>
            `;
        }
    }


    async function loadMachinesV61() {

        const host =
            document.getElementById(
                "oee-sph-tabs-v60"
            );


        if (!host) {
            return;
        }


        try {

            const response =
                await fetch(
                    "/api/oee-machine/zone-workspace",
                    {
                        cache:
                            "no-store"
                    }
                );


            const data =
                (
                    typeof
                        window.machineOeeReadApiResponseV2
                    === "function"
                )
                    ?
                    await window
                        .machineOeeReadApiResponseV2(
                            response,
                            "Zone machines"
                        )
                    :
                    await response.json();


            if (
                !response.ok
                ||
                data?.success === false
            ) {

                throw new Error(
                    data?.error
                    || "Unable to load Zone machines."
                );
            }


            renderMachineTabsV61(
                machinesFromResponseV61(
                    data
                )
            );


        } catch (_) {

            /*
             * If API loading ever fails, preserve any
             * server-rendered tabs already present.
             */
            if (
                !host.children.length
            ) {

                renderMachineTabsV61(
                    []
                );
            }
        }
    }


    /* -----------------------------------------------------
       SECTION 1 - MIRROR EXISTING OEE DISPLAY INTO TOP KPI

       Existing OEE calculation remains the owner.
       V61 only reads already-rendered text and mirrors it.
       ----------------------------------------------------- */

    function readKpiV61(
        wantedLabels
    ) {

        const host =
            document.getElementById(
                "machine-live-oee-host-v1"
            );


        if (!host) {
            return "-";
        }


        const wanted =
            wantedLabels.map(
                function(label) {

                    return String(label)
                        .trim()
                        .toLowerCase();
                }
            );


        const candidates =
            host.querySelectorAll(
                [
                    ".machine-live-kpi-v32",
                    ".machine-live-kpi-v25",
                    ".machine-oee-kpi-v1",
                    ".machine-oee-metric-v1"
                ].join(",")
            );


        for (
            const row
            of candidates
        ) {

            const labelElement =
                row.querySelector(
                    "span"
                );


            const valueElement =
                row.querySelector(
                    "strong"
                );


            if (
                !labelElement
                ||
                !valueElement
            ) {

                continue;
            }


            const label =
                String(
                    labelElement.textContent
                    || ""
                )
                .replace(/\s+/g, " ")
                .trim()
                .toLowerCase();


            if (
                wanted.includes(
                    label
                )
            ) {

                return (
                    String(
                        valueElement.textContent
                        || "-"
                    ).trim()
                    || "-"
                );
            }
        }


        return "-";
    }


    function setKpiV61(
        id,
        value
    ) {

        const target =
            document.getElementById(
                id
            );


        if (!target) {
            return;
        }


        target.textContent =
            value
            || "-";
    }


    function syncKpisV61() {

        setKpiV61(
            "oee-kpi-plva-val-v60",
            readKpiV61([
                "Plan vs Actual",
                "PlvA",
                "PVA"
            ])
        );


        setKpiV61(
            "oee-kpi-pr-val-v60",
            readKpiV61([
                "PR"
            ])
        );


        let oee =
            readKpiV61([
                "OEE"
            ]);


        /*
         * Older live panel may show OEE in its hero
         * instead of a KPI tile.
         */
        if (
            !oee
            ||
            oee === "-"
        ) {

            const hero =
                document.querySelector(
                    "#machine-live-oee-host-v1 "
                    +
                    ".machine-oee-hero-v1 strong"
                );


            if (hero) {

                oee =
                    String(
                        hero.textContent
                        || "-"
                    ).trim();
            }
        }


        setKpiV61(
            "oee-kpi-oee-val-v60",
            oee
        );
    }


    function watchKpisV61() {

        const host =
            document.getElementById(
                "machine-live-oee-host-v1"
            );


        if (!host) {
            return;
        }


        if (
            host.dataset
                .topKpiWatchV61
            === "1"
        ) {

            syncKpisV61();

            return;
        }


        host.dataset
            .topKpiWatchV61 =
            "1";


        const observer =
            new MutationObserver(
                function() {

                    syncKpisV61();
                }
            );


        observer.observe(
            host,
            {
                childList:true,
                subtree:true,
                characterData:true
            }
        );


        syncKpisV61();
    }


    /* -----------------------------------------------------
       INIT
       ----------------------------------------------------- */

    window.setTimeout(
        loadMachinesV61,
        120
    );


    window.setTimeout(
        watchKpisV61,
        180
    );


    window.setTimeout(
        syncKpisV61,
        500
    );


    window.setTimeout(
        syncKpisV61,
        1200
    );

})();

/* V61 END */


/* MACHINE_OEE_TOOL_ENTRY_V1_START */

(function () {

    const TOOL_HOST_ID_V1 =
        "machine-oee-tool-entry-v1";


    function machineOeeToolEscapeV1(
        value
    ) {

        return String(
            value === null
            || value === undefined
                ? ""
                : value
        )
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }


    function machineOeeToolRowHtmlV1(
        position
    ) {

        const number =
            Number(position || 1);


        const canRemove =
            number > 1;


        return `

            <div
                class="machine-oee-tool-row-v1"
                data-tool-position-v1="${number}"
            >

                <div
                    class="machine-oee-tool-row-head-v1"
                >

                    <div
                        class="machine-oee-tool-position-v1"
                    >

                        <span
                            class="machine-oee-tool-position-number-v1"
                        >
                            ${number}
                        </span>

                        <strong>
                            Tool Position ${number}
                        </strong>

                    </div>


                    <button
                        type="button"
                        class="
                            machine-oee-tool-remove-v1
                            ${canRemove
                                ? ""
                                : "is-hidden"}
                        "
                        title="Remove Tool Position"
                        aria-label="Remove Tool Position"
                    >

                        <i
                            class="fa fa-trash-o"
                            aria-hidden="true"
                        ></i>

                        <span>
                            Remove
                        </span>

                    </button>

                </div>


                <div
                    class="machine-oee-tool-fields-v1"
                >

                    <div
                        class="machine-oee-tool-field-v1"
                    >

                        <label>
                            Tool UID
                        </label>

                        <input
                            type="text"
                            class="machine-oee-tool-uid-v1"
                            autocomplete="off"
                            placeholder="Enter / Scan Tool UID"
                        >

                        <div
                            class="machine-oee-tool-uid-info-v117"
                            hidden
                        >

                            <div
                                class="machine-oee-tool-uid-code-v117"
                            ></div>

                            <div
                                class="machine-oee-tool-uid-name-v117"
                            ></div>

                            <div
                                class="machine-oee-tool-uid-status-v117"
                            ></div>

                        </div>

                        <div
                            class="machine-oee-tool-uid-error-v117"
                            hidden
                        ></div>

                    </div>

                    <div
                        class="machine-oee-tool-field-v1"
                    >

                        <label>
                            Tool Action
                        </label>

                        <select
                            class="
                                machine-oee-tool-action-v1
                                machine-oee-tool-select-v3
                            "
                            disabled
                        >
                            <option value="">
                                Loading...
                            </option>
                        </select>

                    </div>


                    <div
                        class="machine-oee-tool-field-v1"
                    >

                        <label>
                            Corner
                        </label>

                        <select
                            class="
                                machine-oee-tool-corner-v1
                                machine-oee-tool-select-v3
                            "
                            disabled
                        >
                            <option value="">
                                -- Select Corner --
                            </option>
                        </select>

                    </div>


                    <div
                        class="machine-oee-tool-field-v1"
                    >

                        <label>
                            Usage / Part (Manual)
                        </label>

                        <input
                            type="text"
                            class="machine-oee-tool-usage-v1"
                            autocomplete="off"
                            placeholder="Enter Usage / Part"
                        >

                    </div>


                    <div
                        class="
                            machine-oee-tool-field-v1
                            machine-oee-tool-reason-wrap-v3
                        "
                        hidden
                    >

                        <label
                            class="machine-oee-tool-reason-label-v3"
                        >
                            Change Reason
                        </label>

                        <select
                            class="
                                machine-oee-tool-reason-v3
                                machine-oee-tool-select-v3
                            "
                        >
                            <option value="">
                                -- Select Reason --
                            </option>
                        </select>

                    </div>


                </div>

            </div>
        `;
    }


    function machineOeeToolRenumberV1(
        host
    ) {

        if (!host) {
            return;
        }


        const rows =
            host.querySelectorAll(
                ".machine-oee-tool-row-v1"
            );


        rows.forEach(
            function(row, index) {

                const position =
                    index + 1;


                row.setAttribute(
                    "data-tool-position-v1",
                    String(position)
                );


                const number =
                    row.querySelector(
                        ".machine-oee-tool-position-number-v1"
                    );


                if (number) {

                    number.textContent =
                        String(position);
                }


                const title =
                    row.querySelector(
                        ".machine-oee-tool-position-v1 strong"
                    );


                if (title) {

                    title.textContent =
                        "Tool Position "
                        + position;
                }


                const remove =
                    row.querySelector(
                        ".machine-oee-tool-remove-v1"
                    );


                if (remove) {

                    remove.classList.toggle(
                        "is-hidden",
                        position === 1
                    );
                }
            }
        );
    }


    function machineOeeToolBindRowV1(
        row,
        host
    ) {

        if (
            !row
            || !host
        ) {
            return;
        }


        const remove =
            row.querySelector(
                ".machine-oee-tool-remove-v1"
            );


        if (!remove) {
            return;
        }


        remove.addEventListener(
            "click",
            function() {

                const rows =
                    host.querySelectorAll(
                        ".machine-oee-tool-row-v1"
                    );


                if (rows.length <= 1) {
                    return;
                }


                row.remove();


                machineOeeToolRenumberV1(
                    host
                );
            }
        );
    }


    function machineOeeToolAddRowV1(
        host
    ) {

        if (!host) {
            return;
        }


        const rowsHost =
            host.querySelector(
                "#machine-oee-tool-rows-v1"
            );


        if (!rowsHost) {
            return;
        }


        const nextPosition =
            rowsHost.querySelectorAll(
                ".machine-oee-tool-row-v1"
            ).length + 1;


        const wrapper =
            document.createElement(
                "div"
            );


        wrapper.innerHTML =
            machineOeeToolRowHtmlV1(
                nextPosition
            );


        const row =
            wrapper.firstElementChild;


        if (!row) {
            return;
        }


        rowsHost.appendChild(
            row
        );


        machineOeeToolBindRowV1(
            row,
            host
        );


        const firstInput =
            row.querySelector(
                "input"
            );


        if (firstInput) {

            firstInput.focus();
        }
    }


    function machineOeeToolBuildV1() {

        const section =
            document.createElement(
                "section"
            );


        section.id =
            TOOL_HOST_ID_V1;


        section.className =
            "machine-oee-tool-section-v1";


        section.innerHTML = `

            <div
                class="machine-oee-tool-section-head-v1"
            >

                <div
                    class="machine-oee-tool-title-v1"
                >

                    <div
                        class="machine-oee-tool-icon-v1"
                    >

                        <i
                            class="fa fa-wrench"
                            aria-hidden="true"
                        ></i>

                    </div>


                    <div>

                        <strong>
                            Tool
                        </strong>

                        <span>
                            Record tools used for this operation
                        </span>

                    </div>

                </div>


            </div>


            <div
                id="machine-oee-tool-rows-v1"
                class="machine-oee-tool-rows-v1"
            >

                ${machineOeeToolRowHtmlV1(
                    1
                )}

            </div>


            <div
                class="machine-oee-tool-add-wrap-v1"
            >

                <button
                    type="button"
                    id="machine-oee-tool-add-v1"
                    class="machine-oee-tool-add-v1"
                >

                    <i
                        class="fa fa-plus"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Add Tool Position
                    </span>

                </button>

            </div>

        `;


        const firstRow =
            section.querySelector(
                ".machine-oee-tool-row-v1"
            );


        machineOeeToolBindRowV1(
            firstRow,
            section
        );


        const addButton =
            section.querySelector(
                "#machine-oee-tool-add-v1"
            );


        if (addButton) {

            addButton.addEventListener(
                "click",
                function() {

                    machineOeeToolAddRowV1(
                        section
                    );
                }
            );
        }


        return section;
    }


    function machineOeeToolFindAnchorV1() {

        /*
         * ACTIVE JC / RUN:
         *
         * Insert immediately after the OEE Losses
         * section and before Operation Completion.
         */

        const activeLossGrid =
            document.getElementById(
                "oee-direct-loss-grid-v3"
            );


        if (activeLossGrid) {

            const activeLossSection =
                activeLossGrid.closest(
                    ".oee-direct-section-v3"
                );


            if (activeLossSection) {

                return {
                    mode:
                        "after-section",

                    anchor:
                        activeLossSection
                };
            }
        }


        /*
         * MACHINE_OEE_TOOL_SAVE_BUTTON_BOTTOM_V7
         *
         * NO-JC / TOOL ROOM / DEVELOPMENT:
         *
         * Required order:
         *
         * Losses
         * Tool Position
         * Save Losses
         *
         * The existing Save Losses action remains unchanged.
         * Only Tool Position placement is changed so the
         * save action stays at the bottom of the full form.
         */

        const machineLossSave =
            document.getElementById(
                "machine-oee-machine-loss-save-v13"
            );


        if (machineLossSave) {

            const actions =
                machineLossSave.closest(
                    ".oee-direct-actions-v3"
                );


            if (actions) {

                return {
                    mode:
                        "before-actions",

                    anchor:
                        actions
                };
            }
        }


        return null;
    }


    function machineOeeToolSyncV1() {

        const target =
            machineOeeToolFindAnchorV1();


        const existing =
            document.getElementById(
                TOOL_HOST_ID_V1
            );


        if (!target) {

            if (existing) {
                existing.remove();
            }

            return;
        }


        let section =
            existing;


        if (!section) {

            section =
                machineOeeToolBuildV1();
        }


        /*
         * NO-JC / Tool Room / Development:
         *
         * Tool Position must sit immediately before
         * the Save Losses action container.
         *
         * target.anchor is now the stable actions node,
         * never actions.previousElementSibling.
         */
        if (
            target.mode
            === "before-actions"
        ) {

            if (
                section.nextElementSibling
                !== target.anchor
            ) {

                target.anchor.insertAdjacentElement(
                    "beforebegin",
                    section
                );
            }


            return;
        }


        /*
         * ACTIVE JC:
         *
         * Keep Tool Position immediately after the
         * existing OEE Losses section.
         */
        if (
            section.previousElementSibling
            !== target.anchor
        ) {

            target.anchor.insertAdjacentElement(
                "afterend",
                section
            );
        }
    }


    let machineOeeToolTimerV1 =
        null;


    const observer =
        new MutationObserver(
            function() {

                window.clearTimeout(
                    machineOeeToolTimerV1
                );


                machineOeeToolTimerV1 =
                    window.setTimeout(
                        machineOeeToolSyncV1,
                        80
                    );
            }
        );


    observer.observe(
        document.body,
        {
            childList: true,
            subtree: true
        }
    );


    window.setTimeout(
        machineOeeToolSyncV1,
        150
    );


    window.setTimeout(
        machineOeeToolSyncV1,
        700
    );



    
    /* MACHINE_OEE_TOOL_DB_MASTER_V3 */

    let machineOeeToolMasterV3 =
        null;

    let machineOeeToolMasterPromiseV3 =
        null;


    async function machineOeeToolLoadMasterV3() {

        if (machineOeeToolMasterV3) {

            return machineOeeToolMasterV3;
        }


        if (machineOeeToolMasterPromiseV3) {

            return machineOeeToolMasterPromiseV3;
        }


        machineOeeToolMasterPromiseV3 =
            fetch(
                "/api/oee-machine/tooling-master",
                {
                    cache:
                        "no-store"
                }
            )
            .then(
                async function(response) {

                    const data =
                        await response.json();


                    if (
                        !response.ok
                        ||
                        data.success === false
                    ) {

                        throw new Error(
                            data.error
                            ||
                            "Unable to load Tooling Master."
                        );
                    }


                    machineOeeToolMasterV3 = {
                        actions:
                            Array.isArray(
                                data.actions
                            )
                                ? data.actions
                                : [],

                        corners:
                            Array.isArray(
                                data.corners
                            )
                                ? data.corners
                                : [],

                        reasons:
                            (
                                data.reasons
                                &&
                                typeof data.reasons
                                    === "object"
                            )
                                ? data.reasons
                                : {}
                    };


                    return machineOeeToolMasterV3;
                }
            )
            .finally(
                function() {

                    machineOeeToolMasterPromiseV3 =
                        null;
                }
            );


        return machineOeeToolMasterPromiseV3;
    }


    function machineOeeToolResetSelectV3(
        select,
        placeholder
    ) {

        if (!select) {
            return;
        }


        select.innerHTML =
            "";


        const option =
            document.createElement(
                "option"
            );


        option.value =
            "";

        option.textContent =
            placeholder;


        select.appendChild(
            option
        );
    }


    function machineOeeToolPopulateActionsV3(
        select,
        actions
    ) {

        machineOeeToolResetSelectV3(
            select,
            "-- Select Action --"
        );


        for (const item of actions) {

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                String(
                    item.action_code
                    || ""
                );


            option.textContent =
                String(
                    item.action_name
                    || ""
                );


            option.dataset.masterIdV3 =
                String(
                    item.id
                    || ""
                );


            option.dataset.enablesCornerV3 =
                item.enables_corner
                    ? "1"
                    : "0";


            option.dataset.reasonGroupV3 =
                String(
                    item.reason_group
                    || ""
                );


            select.appendChild(
                option
            );
        }


        select.disabled =
            false;
    }


    function machineOeeToolPopulateCornersV3(
        select,
        corners
    ) {

        machineOeeToolResetSelectV3(
            select,
            "-- Select Corner --"
        );


        for (const item of corners) {

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                String(
                    item.corner_code
                    || ""
                );


            option.textContent =
                String(
                    item.corner_name
                    || ""
                );


            option.dataset.masterIdV3 =
                String(
                    item.id
                    || ""
                );


            select.appendChild(
                option
            );
        }


        select.disabled =
            true;
    }


    function machineOeeToolHideReasonV3(
        row
    ) {

        const wrap =
            row.querySelector(
                ".machine-oee-tool-reason-wrap-v3"
            );


        const reason =
            row.querySelector(
                ".machine-oee-tool-reason-v3"
            );


        if (wrap) {

            wrap.hidden =
                true;
        }


        if (reason) {

            machineOeeToolResetSelectV3(
                reason,
                "-- Select Reason --"
            );
        }


        row.dataset.toolReasonGroupV3 =
            "";
    }


    async function machineOeeToolShowReasonV3(
        row,
        reasonGroup,
        labelText
    ) {

        const master =
            await machineOeeToolLoadMasterV3();


        const wrap =
            row.querySelector(
                ".machine-oee-tool-reason-wrap-v3"
            );


        const label =
            row.querySelector(
                ".machine-oee-tool-reason-label-v3"
            );


        const select =
            row.querySelector(
                ".machine-oee-tool-reason-v3"
            );


        if (
            !wrap
            ||
            !select
        ) {
            return;
        }


        const rows =
            Array.isArray(
                master.reasons[
                    reasonGroup
                ]
            )
                ? master.reasons[
                    reasonGroup
                ]
                : [];


        machineOeeToolResetSelectV3(
            select,
            "-- Select Reason --"
        );


        for (const item of rows) {

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                String(
                    item.reason_code
                    || ""
                );


            option.textContent =
                String(
                    item.reason_name
                    || ""
                );


            option.dataset.masterIdV3 =
                String(
                    item.id
                    || ""
                );


            select.appendChild(
                option
            );
        }


        if (label) {

            label.textContent =
                labelText;
        }


        row.dataset.toolReasonGroupV3 =
            reasonGroup;


        wrap.hidden =
            false;
    }


    async function machineOeeToolHydrateRowV3(
        row
    ) {

        if (
            !row
            ||
            row.dataset
                .toolMasterHydratedV3
                === "1"
        ) {
            return;
        }


        const action =
            row.querySelector(
                ".machine-oee-tool-action-v1"
            );


        const corner =
            row.querySelector(
                ".machine-oee-tool-corner-v1"
            );


        if (
            !action
            ||
            !corner
        ) {
            return;
        }


        const master =
            await machineOeeToolLoadMasterV3();


        machineOeeToolPopulateActionsV3(
            action,
            master.actions
        );


        machineOeeToolPopulateCornersV3(
            corner,
            master.corners
        );


        machineOeeToolHideReasonV3(
            row
        );


        row.dataset.toolMasterHydratedV3 =
            "1";
    }


    function machineOeeToolHydrateAllV3() {

        document
            .querySelectorAll(
                ".machine-oee-tool-row-v1"
            )
            .forEach(
                function(row) {

                    machineOeeToolHydrateRowV3(
                        row
                    )
                    .catch(
                        function(error) {

                            console.error(
                                "Tooling Master load failed:",
                                error
                            );
                        }
                    );
                }
            );
    }


    document.addEventListener(
        "change",
        function(event) {

            const target =
                event.target;


            if (
                !(target instanceof HTMLElement)
            ) {
                return;
            }


            const row =
                target.closest(
                    ".machine-oee-tool-row-v1"
                );


            if (!row) {
                return;
            }


            if (
                target.classList.contains(
                    "machine-oee-tool-action-v1"
                )
            ) {

                const action =
                    target;


                const corner =
                    row.querySelector(
                        ".machine-oee-tool-corner-v1"
                    );


                const selected =
                    action.selectedOptions[
                        0
                    ]
                    || null;


                const actionCode =
                    String(
                        action.value
                        || ""
                    ).trim().toUpperCase();


                const enablesCorner =
                    Boolean(
                        selected
                        &&
                        selected.dataset
                            .enablesCornerV3
                            === "1"
                    );


                const reasonGroup =
                    String(
                        selected?.dataset
                            .reasonGroupV3
                        || ""
                    ).trim().toUpperCase();


                machineOeeToolHideReasonV3(
                    row
                );


                if (corner) {

                    corner.disabled =
                        !enablesCorner;


                    corner.value =
                        "";
                }


                if (
                    actionCode
                    === "TOOL_CHANGE"
                    &&
                    reasonGroup
                ) {

                    machineOeeToolShowReasonV3(
                        row,
                        reasonGroup,
                        "Tool Change Reason"
                    );
                }


                return;
            }


            if (
                target.classList.contains(
                    "machine-oee-tool-corner-v1"
                )
            ) {

                const action =
                    row.querySelector(
                        ".machine-oee-tool-action-v1"
                    );


                const selectedAction =
                    action?.selectedOptions[
                        0
                    ]
                    || null;


                const actionCode =
                    String(
                        action?.value
                        || ""
                    ).trim().toUpperCase();


                const reasonGroup =
                    String(
                        selectedAction?.dataset
                            .reasonGroupV3
                        || ""
                    ).trim().toUpperCase();


                if (
                    actionCode
                    === "CORNER_CHANGE"
                    &&
                    String(
                        target.value
                        || ""
                    ).trim()
                    &&
                    reasonGroup
                ) {

                    machineOeeToolShowReasonV3(
                        row,
                        reasonGroup,
                        "Corner Change Reason"
                    );

                } else {

                    machineOeeToolHideReasonV3(
                        row
                    );
                }
            }
        },
        true
    );


    const machineOeeToolMasterObserverV3 =
        new MutationObserver(
            function() {

                window.clearTimeout(
                    machineOeeToolMasterObserverV3
                        .timerV3
                );


                machineOeeToolMasterObserverV3
                    .timerV3 =
                    window.setTimeout(
                        machineOeeToolHydrateAllV3,
                        50
                    );
            }
        );


    machineOeeToolMasterObserverV3.observe(
        document.body,
        {
            childList:
                true,

            subtree:
                true
        }
    );


    window.setTimeout(
        machineOeeToolHydrateAllV3,
        150
    );


    window.setTimeout(
        machineOeeToolHydrateAllV3,
        700
    );


    /*
     * Frontend-only helper for future backend work.
     *
     * Nothing is currently saved.
     */
    window.machineOeeGetToolRowsV1 =
        function() {

            const host =
                document.getElementById(
                    TOOL_HOST_ID_V1
                );


            if (!host) {
                return [];
            }


            return Array.from(
                host.querySelectorAll(
                    ".machine-oee-tool-row-v1"
                )
            ).map(
                function(row, index) {

                    return {

                        tool_position:
                            index + 1,

                        tool_uid:
                            String(
                                row.querySelector(
                                    ".machine-oee-tool-uid-v1"
                                )?.value
                                || ""
                            ).trim(),

                        corner:
                            String(
                                row.querySelector(
                                    ".machine-oee-tool-corner-v1"
                                )?.value
                                || ""
                            ).trim(),

                        tool_action:
                            String(
                                row.querySelector(
                                    ".machine-oee-tool-action-v1"
                                )?.value
                                || ""
                            ).trim(),

                        tool_action_master_id:
                            Number(
                                row.querySelector(
                                    ".machine-oee-tool-action-v1"
                                )?.selectedOptions?.[0]
                                    ?.dataset
                                    ?.masterIdV3
                                || 0
                            )
                            || null,

                        corner_master_id:
                            Number(
                                row.querySelector(
                                    ".machine-oee-tool-corner-v1"
                                )?.selectedOptions?.[0]
                                    ?.dataset
                                    ?.masterIdV3
                                || 0
                            )
                            || null,

                        change_reason_master_id:
                            Number(
                                row.querySelector(
                                    ".machine-oee-tool-reason-v3"
                                )?.selectedOptions?.[0]
                                    ?.dataset
                                    ?.masterIdV3
                                || 0
                            )
                            || null,

                        change_reason:
                            String(
                                row.querySelector(
                                    ".machine-oee-tool-reason-v3"
                                )?.selectedOptions?.[0]
                                    ?.textContent
                                || ""
                            ).trim(),

                        reason_group:
                            String(
                                row.dataset
                                    .toolReasonGroupV3
                                || ""
                            ).trim(),

                        usage_per_part:
                            String(
                                row.querySelector(
                                    ".machine-oee-tool-usage-v1"
                                )?.value
                                || ""
                            ).trim()
                    };
                }
            );
        };


    /* MACHINE_OEE_TOOL_PERSISTENCE_UI_V5 */

    let machineOeeToolLoadRunBusyV5 =
        false;


    async function machineOeeToolReadApiV5(
        response,
        label
    ) {

        let data = null;


        try {

            data =
                await response.json();

        } catch (_) {

            throw new Error(
                label
                + " returned an invalid response."
            );
        }


        if (
            !response.ok
            ||
            data.success === false
        ) {

            throw new Error(
                data.error
                || label + " failed."
            );
        }


        return data;
    }


    function machineOeeToolCurrentRunIdV5() {

        let run = null;


        try {

            run =
                machineOeeActiveRunV1
                || machineOeePendingRunV1
                || null;

        } catch (_) {

            run = null;
        }


        return Number(
            run?.run_id
            || run?.id
            || 0
        );
    }


    async function machineOeeToolSaveRowsV5(
        context
    ) {

        const runId =
            Number(
                context?.run_id
                || 0
            );


        const activityRunId =
            Number(
                context?.activity_run_id
                || 0
            );


        /* OEE_MACHINE_LOSS_TOOLING_V122 */
        const machineLossEntryId =
            Number(
                context?.machine_loss_entry_id
                || 0
            );


        const providedContexts =
            (runId > 0 ? 1 : 0)
            + (activityRunId > 0 ? 1 : 0)
            + (machineLossEntryId > 0 ? 1 : 0);


        if (providedContexts !== 1) {

            throw new Error(
                "Valid Tooling transaction context is required."
            );
        }


        if (
            typeof window.machineOeeGetToolRowsV1
            !== "function"
        ) {

            throw new Error(
                "Tool Position collector is not available."
            );
        }


        /* OEE_TOOL_UID_SAVE_GUARD_V118 */

        let collectedRows =
            window.machineOeeGetToolRowsV1();


        const toolHost =
            document.getElementById(
                TOOL_HOST_ID_V1
            );


        const domRows =
            toolHost
                ? Array.from(
                    toolHost.querySelectorAll(
                        ".machine-oee-tool-row-v1"
                    )
                )
                : [];


        for (
            let index = 0;
            index < collectedRows.length;
            index += 1
        ) {

            const toolRow =
                collectedRows[index]
                || {};


            const hasToolData =
                Boolean(
                    String(
                        toolRow.tool_uid
                        || ""
                    ).trim()
                    ||
                    String(
                        toolRow.tool_action
                        || ""
                    ).trim()
                    ||
                    String(
                        toolRow.corner
                        || ""
                    ).trim()
                    ||
                    String(
                        toolRow.change_reason
                        || ""
                    ).trim()
                    ||
                    String(
                        toolRow.usage_per_part
                        || ""
                    ).trim()
                );


            if (!hasToolData) {
                continue;
            }


            const uid =
                String(
                    toolRow.tool_uid
                    || ""
                ).trim();


            const domRow =
                domRows[index]
                || null;


            const uidInput =
                domRow?.querySelector(
                    ".machine-oee-tool-uid-v1"
                )
                || null;


            if (!uid) {

                uidInput?.focus();

                throw new Error(
                    "Tool UID is required for Tool Position "
                    + String(index + 1)
                    + "."
                );
            }


            if (
                domRow?.dataset?.toolUidValidV117
                !== "1"
            ) {

                if (
                    typeof window.machineOeeLookupToolUidV117
                    !== "function"
                ) {

                    throw new Error(
                        "Tool UID validation is not available."
                    );
                }


                const valid =
                    await window.machineOeeLookupToolUidV117(
                        uidInput
                    );


                if (!valid) {

                    uidInput?.focus();

                    throw new Error(
                        "Tool UID "
                        + uid
                        + " is not registered."
                    );
                }
            }
        }


        collectedRows =
            window.machineOeeGetToolRowsV1();


        const payload = {
            tool_rows:
                collectedRows
        };


        if (runId > 0) {

            payload.run_id =
                runId;

        } else if (activityRunId > 0) {

            payload.activity_run_id =
                activityRunId;

        } else {

            payload.machine_loss_entry_id =
                machineLossEntryId;
        }


        const response =
            await fetch(
                "/api/oee-machine/tooling-entries",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(
                            payload
                        )
                }
            );


        const result =
            await machineOeeToolReadApiV5(
                response,
                "Save Tool Position entries"
            );


        window.machineOeeLastToolSaveCountV6 =
            Number(
                result?.saved_count
                || 0
            );


        return result;
    }


    async function machineOeeToolRenderSavedRowsV5(
        entries,
        runId
    ) {

        machineOeeToolSyncV1();


        const host =
            document.getElementById(
                TOOL_HOST_ID_V1
            );


        const rowsHost =
            host?.querySelector(
                "#machine-oee-tool-rows-v1"
            );


        if (
            !host
            || !rowsHost
        ) {
            return;
        }


        await machineOeeToolLoadMasterV3();


        const savedRows =
            Array.isArray(entries)
            ? entries
            : [];


        const renderRows =
            savedRows.length
            ? savedRows
            : [null];


        rowsHost.innerHTML =
            "";


        for (
            let index = 0;
            index < renderRows.length;
            index += 1
        ) {

            const saved =
                renderRows[index];


            const wrapper =
                document.createElement(
                    "div"
                );


            wrapper.innerHTML =
                machineOeeToolRowHtmlV1(
                    index + 1
                );


            const row =
                wrapper.firstElementChild;


            if (!row) {
                continue;
            }


            rowsHost.appendChild(
                row
            );


            machineOeeToolBindRowV1(
                row,
                host
            );


            await machineOeeToolHydrateRowV3(
                row
            );


            if (!saved) {
                continue;
            }


            const uid =
                row.querySelector(
                    ".machine-oee-tool-uid-v1"
                );


            const action =
                row.querySelector(
                    ".machine-oee-tool-action-v1"
                );


            const corner =
                row.querySelector(
                    ".machine-oee-tool-corner-v1"
                );


            const usage =
                row.querySelector(
                    ".machine-oee-tool-usage-v1"
                );


            if (uid) {

                uid.value =
                    String(
                        saved.tool_uid
                        || ""
                    );
            }


            if (usage) {

                usage.value =
                    String(
                        saved.usage_per_part
                        || ""
                    );
            }


            if (!action) {
                continue;
            }


            action.value =
                String(
                    saved.tool_action_code
                    || ""
                );


            const selected =
                action.selectedOptions?.[0]
                || null;


            const actionCode =
                String(
                    action.value
                    || ""
                ).trim().toUpperCase();


            const enablesCorner =
                Boolean(
                    selected
                    &&
                    selected.dataset
                        .enablesCornerV3
                        === "1"
                );


            const reasonGroup =
                String(
                    selected?.dataset
                        .reasonGroupV3
                    || saved.reason_group
                    || ""
                ).trim().toUpperCase();


            machineOeeToolHideReasonV3(
                row
            );


            if (corner) {

                corner.disabled =
                    !enablesCorner;


                corner.value =
                    enablesCorner
                    ? String(
                        saved.corner_code
                        || ""
                      )
                    : "";
            }


            if (reasonGroup) {

                await machineOeeToolShowReasonV3(
                    row,
                    reasonGroup,
                    actionCode === "TOOL_CHANGE"
                        ? "Tool Change Reason"
                        : "Corner Change Reason"
                );


                const reason =
                    row.querySelector(
                        ".machine-oee-tool-reason-v3"
                    );


                if (reason) {

                    reason.value =
                        String(
                            saved.change_reason_code
                            || ""
                        );
                }
            }
        }


        machineOeeToolRenumberV1(
            host
        );


        host.dataset.toolLoadedRunV5 =
            String(runId);
    }


    async function machineOeeToolMaybeLoadRunV5() {

        const runId =
            machineOeeToolCurrentRunIdV5();


        if (runId <= 0) {
            return;
        }


        machineOeeToolSyncV1();


        const host =
            document.getElementById(
                TOOL_HOST_ID_V1
            );


        if (
            host?.dataset
                .toolLoadedRunV5
            === String(runId)
        ) {
            return;
        }


        if (machineOeeToolLoadRunBusyV5) {
            return;
        }


        machineOeeToolLoadRunBusyV5 =
            true;


        try {

            const response =
                await fetch(
                    "/api/oee-machine/tooling-entries"
                    + "?run_id="
                    + encodeURIComponent(
                        runId
                    ),
                    {
                        cache:
                            "no-store"
                    }
                );


            const data =
                await machineOeeToolReadApiV5(
                    response,
                    "Load Tool Position entries"
                );


            await machineOeeToolRenderSavedRowsV5(
                data.entries,
                runId
            );

        } catch (error) {

            console.error(
                "Tool Position restore failed:",
                error
            );

        } finally {

            machineOeeToolLoadRunBusyV5 =
                false;
        }
    }


    window.machineOeeSaveToolRowsV5 =
        machineOeeToolSaveRowsV5;


    window.machineOeeLoadToolRowsV5 =
        machineOeeToolMaybeLoadRunV5;


    window.setTimeout(
        machineOeeToolMaybeLoadRunV5,
        250
    );


    window.setTimeout(
        machineOeeToolMaybeLoadRunV5,
        850
    );


    const machineOeeToolRestoreObserverV5 =
        new MutationObserver(
            function() {

                window.clearTimeout(
                    machineOeeToolRestoreObserverV5
                        .timerV5
                );


                machineOeeToolRestoreObserverV5
                    .timerV5 =
                    window.setTimeout(
                        machineOeeToolMaybeLoadRunV5,
                        100
                    );
            }
        );


    machineOeeToolRestoreObserverV5.observe(
        document.body,
        {
            childList:
                true,

            subtree:
                true
        }
    );


})();

/* MACHINE_OEE_TOOL_ENTRY_V1_END */



/* MACHINE_OEE_FIXED_TOP_BAR_V1 */
(function () {

    let placeholderV1 =
        null;

    let originalTopV1 =
        null;


    function cardV1() {

        return document.querySelector(
            ".oee-machtabs-card-v60"
        );
    }


    function resetV1(card) {

        if (!card) {
            return;
        }


        card.style.position =
            "";

        card.style.top =
            "";

        card.style.left =
            "";

        card.style.width =
            "";

        card.style.zIndex =
            "";

        card.style.marginBottom =
            "";

        card.classList.remove(
            "oee-machine-fixed-top-v1"
        );


        if (
            placeholderV1
            &&
            placeholderV1.parentNode
        ) {

            placeholderV1.remove();
        }


        placeholderV1 =
            null;
    }


    function syncV1() {

        const card =
            cardV1();


        if (!card) {
            return;
        }


        /*
         * Record the card's normal document position once.
         */
        if (
            originalTopV1
            === null
        ) {

            const rect =
                card.getBoundingClientRect();


            originalTopV1 =
                rect.top
                +
                window.scrollY;
        }


        const shouldFix =
            window.scrollY
            >= originalTopV1;


        if (!shouldFix) {

            resetV1(
                card
            );

            return;
        }


        /*
         * Insert a placeholder so the page does not jump
         * when the real card becomes position:fixed.
         */
        if (!placeholderV1) {

            const rect =
                card.getBoundingClientRect();


            placeholderV1 =
                document.createElement(
                    "div"
                );


            placeholderV1.style.height =
                rect.height
                + "px";


            placeholderV1.style.marginBottom =
                getComputedStyle(
                    card
                ).marginBottom;


            card.parentNode.insertBefore(
                placeholderV1,
                card
            );
        }


        /*
         * Keep the fixed bar aligned exactly with its
         * normal content column.
         */
        const reference =
            placeholderV1
            .getBoundingClientRect();


        card.style.position =
            "fixed";

        card.style.top =
            "0";

        card.style.left =
            reference.left
            + "px";

        const availableWidth =
            Math.max(
                320,
                window.innerWidth
                - reference.left
            );


        card.style.setProperty(
            "width",
            Math.min(
                reference.width,
                availableWidth
            )
            + "px",
            "important"
        );

        card.style.zIndex =
            "2000";

        card.style.marginBottom =
            "0";

        card.classList.add(
            "oee-machine-fixed-top-v1"
        );
    }


    window.addEventListener(
        "scroll",
        syncV1,
        {
            passive:
                true
        }
    );


    window.addEventListener(
        "resize",
        function() {

            const card =
                cardV1();


            if (
                card
                &&
                placeholderV1
            ) {

                const reference =
                    placeholderV1
                    .getBoundingClientRect();


                card.style.left =
                    reference.left
                    + "px";

                card.style.width =
                    reference.width
                    + "px";
            }
        }
    );


    window.setTimeout(
        syncV1,
        300
    );

})();


/* OEE_TIME_ARROW_NAV_V68 */

(function () {

    const TIME_FIELD_IDS_V68 = [
        "oee-direct-start-time-v3",
        "oee-direct-stop-time-v3",
        "oee-direct-cycle-hms-v34",
        "oee-direct-load-hms-v34"
    ];


    function getFieldV68(index) {

        if (
            index < 0
            ||
            index >= TIME_FIELD_IDS_V68.length
        ) {
            return null;
        }

        return document.getElementById(
            TIME_FIELD_IDS_V68[index]
        );
    }


    document.addEventListener(
        "keydown",
        function(event) {

            const target =
                event.target;


            if (
                !(target instanceof HTMLInputElement)
            ) {
                return;
            }


            const index =
                TIME_FIELD_IDS_V68.indexOf(
                    target.id
                );


            if (index === -1) {
                return;
            }


            const start =
                target.selectionStart ?? 0;

            const end =
                target.selectionEnd ?? 0;

            const length =
                target.value.length;


            let nextIndex =
                null;


            /*
             * Left Arrow:
             * normal cursor movement inside field.
             * Move to previous field only at beginning.
             */
            if (
                event.key === "ArrowLeft"
            ) {

                if (
                    start !== 0
                    ||
                    end !== 0
                ) {
                    return;
                }

                nextIndex =
                    index - 1;
            }


            /*
             * Right Arrow:
             * normal cursor movement inside field.
             * Move to next field only at end.
             */
            else if (
                event.key === "ArrowRight"
            ) {

                if (
                    start !== length
                    ||
                    end !== length
                ) {
                    return;
                }

                nextIndex =
                    index + 1;
            }


            /*
             * Up / Down always navigate between fields.
             */
            else if (
                event.key === "ArrowUp"
            ) {

                nextIndex =
                    index - 1;
            }


            else if (
                event.key === "ArrowDown"
            ) {

                nextIndex =
                    index + 1;
            }


            else {

                return;
            }


            const nextField =
                getFieldV68(
                    nextIndex
                );


            if (
                !nextField
                ||
                nextField.disabled
                ||
                nextField.readOnly
            ) {
                return;
            }


            event.preventDefault();

            nextField.focus();


            /*
             * Keep cursor position intuitive:
             *
             * moving left/up -> cursor at end
             * moving right/down -> cursor at start
             */
            window.setTimeout(
                function() {

                    const pos =
                        (
                            event.key === "ArrowLeft"
                            ||
                            event.key === "ArrowUp"
                        )
                        ?
                        nextField.value.length
                        :
                        0;


                    try {

                        nextField.setSelectionRange(
                            pos,
                            pos
                        );

                    } catch (_) {
                    }

                },
                0
            );
        }
    );

})();

/* OEE_TIME_ARROW_NAV_V68_END */

/* OEE_TIME_SMART_ENTRY_V69_END */



/* MACHINE_SHIFT_CAPACITY_UI_V71 */

(function () {

    let requestTokenV71 = 0;


    function valueV71(id) {

        return String(
            document.getElementById(
                id
            )?.value
            || ""
        ).trim();
    }


    function numberV71(value) {

        const n =
            Number(value);

        return Number.isFinite(n)
            ? n
            : 0;
    }


    function displayMinutesV71(
        value
    ) {

        const n =
            numberV71(value);

        if (
            Math.abs(
                n - Math.round(n)
            ) < 0.005
        ) {

            return String(
                Math.round(n)
            );
        }

        return n.toFixed(2);
    }


    function ensureHostV71() {

        let host =
            document.getElementById(
                "oee-shift-capacity-v71"
            );


        if (host) {
            return host;
        }


        const duration =
            document.getElementById(
                "machine-oee-shift-duration-v11"
            );


        const box =
            document.querySelector(
                ".machine-shift-timing-v11"
            );


        if (!box) {
            return null;
        }


        host =
            document.createElement(
                "div"
            );


        host.id =
            "oee-shift-capacity-v71";


        host.className =
            "oee-shift-capacity-v71";


        host.innerHTML = `

            <div class="oee-shift-capacity-item-v71">

                <span>
                    Shift
                </span>

                <strong
                    id="oee-shift-capacity-total-v71"
                >
                    -
                </strong>

            </div>


            <div class="oee-shift-capacity-divider-v71">
            </div>


            <div class="oee-shift-capacity-item-v71">

                <span>
                    Used
                </span>

                <strong
                    id="oee-shift-capacity-used-v71"
                >
                    -
                </strong>

            </div>


            <div class="oee-shift-capacity-divider-v71">
            </div>


            <div
                class="
                    oee-shift-capacity-item-v71
                    remaining
                "
            >

                <span>
                    Remaining
                </span>

                <strong
                    id="oee-shift-capacity-remaining-v71"
                >
                    -
                </strong>

            </div>
        `;


        if (
            duration
            &&
            duration.parentNode
        ) {

            duration.parentNode.insertBefore(
                host,
                duration.nextSibling
            );

        } else {

            box.appendChild(
                host
            );
        }


        return host;
    }


    function setEmptyV71() {

        ensureHostV71();


        const total =
            document.getElementById(
                "oee-shift-capacity-total-v71"
            );

        const used =
            document.getElementById(
                "oee-shift-capacity-used-v71"
            );

        const remaining =
            document.getElementById(
                "oee-shift-capacity-remaining-v71"
            );


        if (total) {
            total.textContent = "-";
        }

        if (used) {
            used.textContent = "-";
        }

        if (remaining) {
            remaining.textContent = "-";
        }
    }


    async function refreshV71() {

        const context =
            window.NMTG_MACHINE_OEE_CONTEXT
            || {};


        const machineId =
            Number(
                context.machine_id
                || 0
            );


        const shiftName =
            valueV71(
                "machine-oee-shift-v1"
            );


        const shiftStart =
            valueV71(
                "machine-oee-shift-start-v11"
            );


        const shiftEnd =
            valueV71(
                "machine-oee-shift-end-v11"
            );


        const entryDate =
            valueV71(
                "oee-ui-date-v58"
            );


        ensureHostV71();


        if (
            !machineId
            ||
            !shiftName
            ||
            !shiftStart
            ||
            !shiftEnd
            ||
            !entryDate
        ) {

            setEmptyV71();
            return;
        }


        const token =
            ++requestTokenV71;


        try {

            const params =
                new URLSearchParams({
                    date:
                        entryDate,

                    shift_name:
                        shiftName,

                    shift_start:
                        shiftStart,

                    shift_end:
                        shiftEnd
                });


            const response =
                await fetch(
                    "/api/oee-machine/"
                    +
                    "shift-capacity/"
                    +
                    encodeURIComponent(
                        machineId
                    )
                    +
                    "?"
                    +
                    params.toString(),
                    {
                        cache:
                            "no-store"
                    }
                );


            const data =
                await response.json();


            if (
                token
                !== requestTokenV71
            ) {
                return;
            }


            if (
                !response.ok
                ||
                data.success === false
            ) {

                throw new Error(
                    data.error
                    ||
                    "Unable to load shift capacity."
                );
            }


            const total =
                document.getElementById(
                    "oee-shift-capacity-total-v71"
                );

            const used =
                document.getElementById(
                    "oee-shift-capacity-used-v71"
                );

            const remaining =
                document.getElementById(
                    "oee-shift-capacity-remaining-v71"
                );


            if (total) {

                total.textContent =
                    displayMinutesV71(
                        data.shift_minutes
                    )
                    +
                    " min";
            }


            if (used) {

                used.textContent =
                    displayMinutesV71(
                        data.used_minutes
                    )
                    +
                    " min";
            }


            if (remaining) {

                remaining.textContent =
                    displayMinutesV71(
                        data.remaining_minutes
                    )
                    +
                    " min";
            }


        } catch (_) {

            if (
                token
                === requestTokenV71
            ) {

                setEmptyV71();
            }
        }
    }


    window.machineOeeRefreshShiftCapacityV71 =
        refreshV71;


    document.addEventListener(
        "change",
        function (event) {

            const id =
                String(
                    event.target?.id
                    || ""
                );


            if (
                id ===
                    "machine-oee-shift-v1"
                ||
                id ===
                    "oee-ui-date-v58"
            ) {

                window.setTimeout(
                    refreshV71,
                    80
                );
            }
        },
        true
    );


    /*
     * Shift start/end are populated by existing JS after
     * Shift selection, so refresh again after that update.
     */
    document.addEventListener(
        "change",
        function (event) {

            const id =
                String(
                    event.target?.id
                    || ""
                );


            if (
                id ===
                    "machine-oee-shift-v1"
            ) {

                window.setTimeout(
                    refreshV71,
                    250
                );
            }
        },
        true
    );


    /*
     * After Complete Operation, give the backend time to
     * finish the existing completion flow, then reload the
     * machine shift capacity.
     */
    document.addEventListener(
        "click",
        function (event) {

            const button =
                event.target?.closest?.(
                    "#machine-oee-complete-btn-v1"
                );


            if (!button) {
                return;
            }


            window.setTimeout(
                refreshV71,
                1200
            );
        },
        true
    );


    /*
     * Date V58 is created dynamically.
     */
    window.setTimeout(
        refreshV71,
        400
    );

    window.setTimeout(
        refreshV71,
        1000
    );


})();

/* MACHINE_SHIFT_CAPACITY_UI_V71_END */



/* OEE_ALL_TIME_TEXT_ENTRY_V79 */

(function () {

    const TIME_IDS_V79 = new Set([
        "oee-direct-start-time-v3",
        "oee-direct-stop-time-v3",
        "oee-loss-start-v16",
        "oee-loss-stop-v16"
    ]);


    function pad2V79(value) {

        return String(value)
            .padStart(2, "0");
    }


    function normalizeV79(value) {

        const raw =
            String(
                value || ""
            ).trim();


        if (!raw) {
            return "";
        }


        /*
         * Normal HH:MM or HH:MM:SS entry.
         */
        if (raw.includes(":")) {

            const parts =
                raw.split(":");


            if (
                parts.length !== 2
                &&
                parts.length !== 3
            ) {
                return null;
            }


            const hh =
                Number(parts[0]);

            const mm =
                Number(parts[1]);

            const ss =
                parts.length === 3
                    ? Number(parts[2])
                    : 0;


            if (
                !Number.isInteger(hh)
                ||
                !Number.isInteger(mm)
                ||
                !Number.isInteger(ss)
                ||
                hh < 0
                ||
                hh > 23
                ||
                mm < 0
                ||
                mm > 59
                ||
                ss < 0
                ||
                ss > 59
            ) {
                return null;
            }


            return (
                pad2V79(hh)
                + ":"
                + pad2V79(mm)
                + ":"
                + pad2V79(ss)
            );
        }


        /*
         * Digits-only operator entry.
         *
         * 8       -> 08:00:00
         * 08      -> 08:00:00
         * 930     -> 09:30:00
         * 0930    -> 09:30:00
         * 08000   -> 08:00:00
         * 93000   -> 09:30:00
         * 190000  -> 19:00:00
         */
        const digits =
            raw.replace(
                /\D/g,
                ""
            );


        if (
            !digits
            ||
            digits.length > 6
        ) {
            return null;
        }


        let hh = 0;
        let mm = 0;
        let ss = 0;


        if (digits.length <= 2) {

            hh =
                Number(digits);
        }


        else if (digits.length <= 4) {

            const value4 =
                digits.padStart(
                    4,
                    "0"
                );

            hh =
                Number(
                    value4.slice(0, 2)
                );

            mm =
                Number(
                    value4.slice(2, 4)
                );
        }


        else if (digits.length === 5) {

            /*
             * First try:
             * 08000 -> 08:00:00
             */

            const directH =
                Number(
                    digits.slice(0, 2)
                );

            const directM =
                Number(
                    digits.slice(2, 4)
                );

            const directS =
                Number(
                    digits.slice(4, 5)
                );


            if (
                directH <= 23
                &&
                directM <= 59
                &&
                directS <= 59
            ) {

                hh = directH;
                mm = directM;
                ss = directS;

            } else {

                /*
                 * Fallback:
                 * 93000 -> 09:30:00
                 */

                const value6 =
                    digits.padStart(
                        6,
                        "0"
                    );

                hh =
                    Number(
                        value6.slice(0, 2)
                    );

                mm =
                    Number(
                        value6.slice(2, 4)
                    );

                ss =
                    Number(
                        value6.slice(4, 6)
                    );
            }
        }


        else {

            hh =
                Number(
                    digits.slice(0, 2)
                );

            mm =
                Number(
                    digits.slice(2, 4)
                );

            ss =
                Number(
                    digits.slice(4, 6)
                );
        }


        if (
            !Number.isInteger(hh)
            ||
            !Number.isInteger(mm)
            ||
            !Number.isInteger(ss)
            ||
            hh < 0
            ||
            hh > 23
            ||
            mm < 0
            ||
            mm > 59
            ||
            ss < 0
            ||
            ss > 59
        ) {
            return null;
        }


        return (
            pad2V79(hh)
            + ":"
            + pad2V79(mm)
            + ":"
            + pad2V79(ss)
        );
    }


    /*
     * Capture the input before the older V20/V34 handlers.
     *
     * Do not format while operator is typing.
     */
    document.addEventListener(
        "input",
        function (event) {

            const input =
                event.target;


            if (
                !(input instanceof HTMLInputElement)
                ||
                !TIME_IDS_V79.has(
                    input.id
                )
            ) {
                return;
            }


            input.setCustomValidity(
                ""
            );


            /*
             * Prevent old smart-format handlers
             * from rewriting the typed value.
             */
            event.stopImmediatePropagation();

        },
        true
    );


    document.addEventListener(
        "focusin",
        function (event) {

            const input =
                event.target;


            if (
                !(input instanceof HTMLInputElement)
                ||
                !TIME_IDS_V79.has(
                    input.id
                )
            ) {
                return;
            }


            input.setAttribute(
                "maxlength",
                "8"
            );

            input.setAttribute(
                "inputmode",
                "numeric"
            );

            input.setAttribute(
                "autocomplete",
                "off"
            );

            input.setAttribute(
                "placeholder",
                "HH:MM:SS"
            );

        },
        true
    );


    document.addEventListener(
        "focusout",
        function (event) {

            const input =
                event.target;


            if (
                !(input instanceof HTMLInputElement)
                ||
                !TIME_IDS_V79.has(
                    input.id
                )
            ) {
                return;
            }


            const raw =
                String(
                    input.value || ""
                ).trim();


            if (!raw) {
                return;
            }


            const normalized =
                normalizeV79(
                    raw
                );


            if (normalized === null) {

                input.setCustomValidity(
                    "Enter valid time in HH:MM:SS format."
                );

                input.reportValidity();

                return;
            }


            input.setCustomValidity(
                ""
            );

            input.value =
                normalized;


            /*
             * Allow existing Cycle/Load sync,
             * KPI preview and save logic to update
             * after normalization.
             */
            input.dispatchEvent(
                new Event(
                    "change",
                    {
                        bubbles: true
                    }
                )
            );

        },
        true
    );


    window.normalizeOeeTimeV79 =
        normalizeV79;

})();

/* OEE_ALL_TIME_TEXT_ENTRY_V79_END */


/* OEE_ACTIVITY_SINGLE_CARD_V81 */

(function () {

    const STORAGE_KEY_V81 =
        "jms_oee_activity_type_v81";


    function currentRunV81() {

        try {

            return (
                machineOeeActiveRunV1
                ||
                machineOeePendingRunV1
                ||
                null
            );

        } catch (_) {

            return null;
        }
    }


    function hasRunV81() {

        const run =
            currentRunV81();

        return Boolean(
            Number(
                run?.run_id
                || run?.id
                || 0
            )
        );
    }


    function jcCardV81() {

        const input =
            document.getElementById(
                "machine-oee-jc-input"
            );

        return input
            ? input.closest(".card")
            : null;
    }


    function headerV81(card) {

        return card?.querySelector(
            ".machine-oee-jc-section-head-v1"
        ) || null;
    }


    function modeLabelV81(mode) {

        if (mode === "TOOL_ROOM") {
            return "Tool Room";
        }

        if (mode === "DEVELOPMENT") {
            return "Development";
        }

        return "Production";
    }


    function createSelectorV81(card) {

        const header =
            headerV81(card);


        if (!header) {
            return null;
        }


        let selector =
            document.getElementById(
                "oee-activity-selector-v81"
            );


        if (selector) {
            return selector;
        }


        /*
         * Remove old Job Card title content.
         */
        header.innerHTML = "";


        selector =
            document.createElement(
                "div"
            );

        selector.id =
            "oee-activity-selector-v81";

        selector.className =
            "oee-activity-selector-v81";


        selector.innerHTML = `
            <button
                type="button"
                id="oee-activity-toggle-v81"
                class="
                    oee-direct-section-title-v3
                    oee-loss-title-toggle-v62
                    oee-activity-toggle-v81
                "
                aria-expanded="false"
            >
                <i
                    id="oee-activity-icon-v81"
                    class="fa fa-industry"
                    aria-hidden="true"
                ></i>

                <span
                    id="oee-activity-label-v81"
                >
                    Production
                </span>

                <i
                    class="
                        fa
                        fa-chevron-down
                        oee-activity-chevron-v81
                    "
                    aria-hidden="true"
                ></i>
            </button>

            <div
                id="oee-activity-menu-v81"
                class="oee-activity-menu-v81"
                hidden
            >
                <button
                    type="button"
                    data-oee-mode-v81="PRODUCTION"
                >
                    <i
                        class="fa fa-cogs"
                        aria-hidden="true"
                        style="color:var(--accent, #2f6397);"
                    ></i>&nbsp;
                    <span>Production</span>
                </button>

                <button
                    type="button"
                    data-oee-mode-v81="TOOL_ROOM"
                >
                    <i
                        class="fa fa-wrench"
                        aria-hidden="true"
                        style="color:var(--accent, #2f6397);"
                    ></i>&nbsp;
                    <span>Tool Room</span>
                </button>

                <button
                    type="button"
                    data-oee-mode-v81="DEVELOPMENT"
                >
                    <i
                        class="fa fa-flask"
                        aria-hidden="true"
                        style="color:var(--accent, #2f6397);"
                    ></i>&nbsp;
                    <span>Development</span>
                </button>
            </div>
        `;


        header.appendChild(
            selector
        );


        return selector;
    }


    function createActivityBodyV81(card) {

        let body =
            document.getElementById(
                "oee-activity-body-v81"
            );


        if (body) {
            return body;
        }


        body =
            document.createElement(
                "div"
            );

        body.id =
            "oee-activity-body-v81";

        body.className =
            "oee-activity-body-v81";

        body.hidden =
            true;


        body.innerHTML = `
            <div
                id="oee-tool-room-options-v81"
                class="oee-activity-options-v81"
                hidden
            >
                <div class="oee-activity-pills-v81">

                    <button
                        type="button"
                        data-activity-v81="Fixture"
                    >
                        Fixture
                    </button>

                    <button
                        type="button"
                        data-activity-v81="Jaw"
                    >
                        Jaw
                    </button>

                    <button
                        type="button"
                        data-activity-v81="Pata"
                    >
                        Pata
                    </button>

                    <button
                        type="button"
                        data-activity-v81="Rollerpin"
                    >
                        Rollerpin
                    </button>

                    <button
                        type="button"
                        data-activity-v81="Tool Modification"
                    >
                        Tool Modification
                    </button>

                    <button
                        type="button"
                        data-activity-v81="Other"
                    >
                        Other
                    </button>

                </div>
            </div>


            <div
                id="oee-development-options-v81"
                class="oee-activity-options-v81"
                hidden
            >
                <div class="oee-activity-pills-v81">

                    <button
                        type="button"
                        data-activity-v81="NPD"
                    >
                        NPD
                    </button>

                    <button
                        type="button"
                        data-activity-v81="Job Trial"
                    >
                        Job Trial
                    </button>

                    <button
                        type="button"
                        data-activity-v81="Other"
                    >
                        Other
                    </button>

                </div>
            </div>


            <div
                id="oee-activity-reason-wrap-v81"
                class="oee-activity-reason-v81"
                hidden
            >
                <label
                    for="oee-activity-reason-v81"
                >
                    Reason
                </label>

                <input
                    id="oee-activity-reason-v81"
                    type="text"
                    autocomplete="off"
                    placeholder="Enter reason"
                >
            </div>


            
        `;


        const header =
            headerV81(card);


        if (
            header
            &&
            header.nextSibling
        ) {

            card.insertBefore(
                body,
                header.nextSibling
            );

        } else {

            card.appendChild(
                body
            );
        }


        return body;
    }


    function productionElementsV81(
        card
    ) {

        const body =
            document.getElementById(
                "oee-activity-body-v81"
            );

        const header =
            headerV81(card);


        return Array.from(
            card.children
        ).filter(
            function (element) {

                return (
                    element !== header
                    &&
                    element !== body
                );
            }
        );
    }


    function setProductionVisibleV81(
        card,
        visible
    ) {

        const elements =
            productionElementsV81(
                card
            );


        for (const element of elements) {

            if (visible) {

                if (
                    element.dataset
                        .oeeOldDisplayV81
                    !== undefined
                ) {

                    element.style.display =
                        element.dataset
                            .oeeOldDisplayV81;

                    delete element.dataset
                        .oeeOldDisplayV81;

                } else {

                    element.style.display =
                        "";
                }

            } else {

                if (
                    element.dataset
                        .oeeOldDisplayV81
                    === undefined
                ) {

                    element.dataset
                        .oeeOldDisplayV81 =
                        element.style.display
                        || "";
                }

                element.style.display =
                    "none";
            }
        }
    }


    function selectedModeV81() {

        return (
            window
                .machineOeeActivityModeV81
            ||
            "PRODUCTION"
        );
    }


    function closeMenuV81() {

        const menu =
            document.getElementById(
                "oee-activity-menu-v81"
            );

        const toggle =
            document.getElementById(
                "oee-activity-toggle-v81"
            );

        const chevron =
            document.querySelector(
                ".oee-activity-chevron-v81"
            );


        if (menu) {
            menu.hidden = true;
        }


        if (toggle) {

            toggle.setAttribute(
                "aria-expanded",
                "false"
            );
        }


        if (chevron) {

            chevron.classList.remove(
                "fa-chevron-up"
            );

            chevron.classList.add(
                "fa-chevron-down"
            );
        }
    }


    function clearActivitySelectionV81() {

        document.querySelectorAll(
            "[data-activity-v81]"
        ).forEach(
            function (button) {

                button.classList.remove(
                    "selected"
                );
            }
        );


        const reasonWrap =
            document.getElementById(
                "oee-activity-reason-wrap-v81"
            );

        const reason =
            document.getElementById(
                "oee-activity-reason-v81"
            );


        if (reasonWrap) {
            reasonWrap.hidden = true;
        }


        if (reason) {

            reason.value = "";
            reason.required = false;
        }


        window.machineOeeSelectedActivityV81 =
            "";
    }


    function applyModeV81(
        requestedMode
    ) {

        const card =
            jcCardV81();


        if (!card) {
            return;
        }


        let mode =
            requestedMode
            || "PRODUCTION";


        /*
         * Existing running JC remains Production.
         */
        if (hasRunV81()) {
            mode = "PRODUCTION";
        }


        window.machineOeeActivityModeV81 =
            mode;


        const label =
            document.getElementById(
                "oee-activity-label-v81"
            );

        const activityBody =
            document.getElementById(
                "oee-activity-body-v81"
            );

        const toolRoom =
            document.getElementById(
                "oee-tool-room-options-v81"
            );

        const development =
            document.getElementById(
                "oee-development-options-v81"
            );


        if (label) {

            label.textContent =
                modeLabelV81(
                    mode
                );
        }


        const icon =
            document.getElementById(
                "oee-activity-icon-v81"
            );


        if (icon) {

            icon.className =
                "fa "
                +
                (
                    mode === "TOOL_ROOM"
                        ? "fa-wrench"
                        :
                    mode === "DEVELOPMENT"
                        ? "fa-flask"
                        :
                        "fa-cogs"
                );
        }


        const production =
            mode === "PRODUCTION";


        setProductionVisibleV81(
            card,
            production
        );


        if (activityBody) {

            activityBody.hidden =
                production;
        }


        if (toolRoom) {

            toolRoom.hidden =
                mode !== "TOOL_ROOM";
        }


        if (development) {

            development.hidden =
                mode !== "DEVELOPMENT";
        }


        clearActivitySelectionV81();


        if (!hasRunV81()) {

            sessionStorage.setItem(
                STORAGE_KEY_V81,
                mode
            );
        }


        closeMenuV81();
    }


    function wireV81() {

        const toggle =
            document.getElementById(
                "oee-activity-toggle-v81"
            );

        const menu =
            document.getElementById(
                "oee-activity-menu-v81"
            );


        if (
            toggle
            &&
            toggle.dataset.wiredV81
            !== "1"
        ) {

            toggle.dataset.wiredV81 =
                "1";


            toggle.addEventListener(
                "click",
                function () {

                    if (hasRunV81()) {
                        return;
                    }


                    const opening =
                        Boolean(
                            menu?.hidden
                        );


                    if (menu) {

                        menu.hidden =
                            !opening;
                    }


                    toggle.setAttribute(
                        "aria-expanded",
                        opening
                            ? "true"
                            : "false"
                    );


                    const chevron =
                        toggle.querySelector(
                            ".oee-activity-chevron-v81"
                        );


                    if (chevron) {

                        chevron.classList.toggle(
                            "fa-chevron-down",
                            !opening
                        );

                        chevron.classList.toggle(
                            "fa-chevron-up",
                            opening
                        );
                    }
                }
            );
        }


        document.querySelectorAll(
            "[data-oee-mode-v81]"
        ).forEach(
            function (button) {

                if (
                    button.dataset.wiredV81
                    === "1"
                ) {
                    return;
                }


                button.dataset.wiredV81 =
                    "1";


                button.addEventListener(
                    "click",
                    function () {

                        applyModeV81(
                            button.dataset
                                .oeeModeV81
                        );
                    }
                );
            }
        );


        document.querySelectorAll(
            "[data-activity-v81]"
        ).forEach(
            function (button) {

                if (
                    button.dataset
                        .activityWiredV81
                    === "1"
                ) {
                    return;
                }


                button.dataset
                    .activityWiredV81 =
                    "1";


                button.addEventListener(
                    "click",
                    function () {

                        document.querySelectorAll(
                            "[data-activity-v81]"
                        ).forEach(
                            function (other) {

                                other.classList.remove(
                                    "selected"
                                );
                            }
                        );


                        button.classList.add(
                            "selected"
                        );


                        const value =
                            String(
                                button.dataset
                                    .activityV81
                                || ""
                            );


                        window
                            .machineOeeSelectedActivityV81 =
                            value;


                        const reasonWrap =
                            document.getElementById(
                                "oee-activity-reason-wrap-v81"
                            );

                        const reason =
                            document.getElementById(
                                "oee-activity-reason-v81"
                            );


                        const isOther =
                            value === "Other";


                        if (reasonWrap) {

                            reasonWrap.hidden =
                                !isOther;
                        }


                        if (reason) {

                            reason.required =
                                isOther;

                            if (!isOther) {
                                reason.value = "";
                            }

                            if (isOther) {
                                reason.focus();
                            }
                        }
                    }
                );
            }
        );
    }


    function initV81() {

        const card =
            jcCardV81();


        if (!card) {
            return;
        }


        const alreadyBuilt =
            Boolean(
                document.getElementById(
                    "oee-activity-selector-v81"
                )
                &&
                document.getElementById(
                    "oee-activity-body-v81"
                )
            );


        createSelectorV81(
            card
        );

        createActivityBodyV81(
            card
        );

        wireV81();


        /*
         * Important:
         * MutationObserver may call init repeatedly.
         * Do not re-apply mode every time because
         * applyModeV81 closes the open dropdown.
         */
        if (alreadyBuilt) {

            if (hasRunV81()) {

                const currentMode =
                    selectedModeV81();

                if (
                    currentMode !== "PRODUCTION"
                ) {

                    applyModeV81(
                        "PRODUCTION"
                    );
                }
            }

            return;
        }


        if (
            hasRunV81()
        ) {

            applyModeV81(
                "PRODUCTION"
            );

            return;
        }


        if (
            !window
                .machineOeeActivityModeV81
        ) {

            const saved =
                sessionStorage.getItem(
                    STORAGE_KEY_V81
                );


            if (
                saved === "PRODUCTION"
                ||
                saved === "TOOL_ROOM"
                ||
                saved === "DEVELOPMENT"
            ) {

                window
                    .machineOeeActivityModeV81 =
                    saved;

            } else {

                window
                    .machineOeeActivityModeV81 =
                    "PRODUCTION";
            }
        }


        applyModeV81(
            selectedModeV81()
        );
    }


    const observerV81 =
        new MutationObserver(
            function () {

                window.clearTimeout(
                    initV81._timer
                );


                initV81._timer =
                    window.setTimeout(
                        initV81,
                        80
                    );
            }
        );


    observerV81.observe(
        document.body,
        {
            childList: true,
            subtree: true
        }
    );


    window.machineOeeApplyActivityModeV81 =
        applyModeV81;


    window.setTimeout(
        initV81,
        120
    );

    window.setTimeout(
        initV81,
        700
    );



/* OEE_ACTIVITY_DB_MASTER_V84 */

let oeeActivityMasterV84 = null;
let oeeActivityMasterPromiseV84 = null;


/*
 * Read Tool Room + Development master
 * from DB through the new read-only API.
 */
async function loadActivityMasterV84() {

    if (oeeActivityMasterV84) {
        return oeeActivityMasterV84;
    }


    if (oeeActivityMasterPromiseV84) {
        return oeeActivityMasterPromiseV84;
    }


    oeeActivityMasterPromiseV84 =
        fetch(
            "/api/oee-machine/activity-master",
            {
                cache: "no-store"
            }
        )
        .then(
            async function(response) {

                const data =
                    await response.json();


                if (
                    !response.ok
                    ||
                    data.success === false
                ) {

                    throw new Error(
                        data.error
                        || "Unable to load activity master."
                    );
                }


                oeeActivityMasterV84 = {
                    TOOL_ROOM:
                        Array.isArray(
                            data.tool_room
                        )
                            ? data.tool_room
                            : [],

                    DEVELOPMENT:
                        Array.isArray(
                            data.development
                        )
                            ? data.development
                            : []
                };


                return oeeActivityMasterV84;
            }
        )
        .finally(
            function() {

                oeeActivityMasterPromiseV84 =
                    null;
            }
        );


    return oeeActivityMasterPromiseV84;
}


/*
 * Escape DB text before adding it to HTML.
 */
function activityEscapeV84(value) {

    return String(
        value
        ?? ""
    )
    .replaceAll(
        "&",
        "&amp;"
    )
    .replaceAll(
        "<",
        "&lt;"
    )
    .replaceAll(
        ">",
        "&gt;"
    )
    .replaceAll(
        '"',
        "&quot;"
    )
    .replaceAll(
        "'",
        "&#039;"
    );
}


/*
 * Find the currently-visible V81 activity pill
 * container without depending on hard-coded names.
 */
function activityVisiblePillGridV84() {

    const body =
        document.getElementById(
            "oee-activity-body-v81"
        );


    if (!body) {
        return null;
    }


    const grids =
        Array.from(
            body.querySelectorAll(
                ".oee-activity-pills-v81"
            )
        );


    return (
        grids.find(
            function(grid) {

                const parent =
                    grid.parentElement;


                return (
                    parent
                    &&
                    window.getComputedStyle(
                        parent
                    ).display !== "none"
                );
            }
        )
        ||
        grids[0]
        ||
        null
    );
}


/*
 * Render DB activities as the existing V81 pills.
 */
async function renderActivityMasterV84(
    mode
) {

    if (
        mode !== "TOOL_ROOM"
        &&
        mode !== "DEVELOPMENT"
    ) {
        return;
    }


    const master =
        await loadActivityMasterV84();


    const rows =
        master[mode]
        || [];


    const grid =
        activityVisiblePillGridV84();


    if (!grid) {
        return;
    }


    grid.innerHTML =
        rows
        .map(
            function(row) {

                const id =
                    Number(
                        row.id
                        || 0
                    );


                const code =
                    activityEscapeV84(
                        row.activity_code
                    );


                const name =
                    activityEscapeV84(
                        row.activity_name
                    );


                const remarksRequired =
                    row.remarks_required
                        ? "1"
                        : "0";


                /* OEE_ACTIVITY_SELECTION_PERSIST_V90 */

                const savedSelection =
                    window
                        .machineOeeActivitySelectionStateV90
                    || {};


                const selectedClass =
                    (
                        String(
                            savedSelection.mode
                            || ""
                        ) === String(mode)
                        &&
                        Number(
                            savedSelection.activity_master_id
                            || 0
                        ) === id
                    )
                    ? " selected"
                    : "";


                return `

                    <button
                        type="button"

                        class="oee-activity-pill-v81${selectedClass}"

                        data-activity-master-id-v84="${id}"

                        data-activity-code-v81="${code}"

                        data-remarks-required-v84="${remarksRequired}"
                    >
                        ${name}
                    </button>
                `;
            }
        )
        .join("");
}


/*
 * Whenever V81 mode changes,
 * replace static pills with DB master pills.
 */
const applyModeV81BaseV84 =
    applyModeV81;


applyModeV81 =
    function applyModeWithDbMasterV84(
        mode
    ) {

        applyModeV81BaseV84(
            mode
        );


        if (
            mode === "TOOL_ROOM"
            ||
            mode === "DEVELOPMENT"
        ) {

            renderActivityMasterV84(
                mode
            )
            .catch(
                function(error) {

                    console.error(
                        "Activity master load failed:",
                        error
                    );
                }
            );
        }
    };


/*
 * Preserve the current V81 pill-selection UX,
 * including the Other -> Reason field rule,
 * but now use remarks_required from DB.
 */
document.addEventListener(
    "click",
    function(event) {

        const pill =
            event.target.closest(
                ".oee-activity-pill-v81"
            );


        if (!pill) {
            return;
        }


        const body =
            document.getElementById(
                "oee-activity-body-v81"
            );


        if (!body) {
            return;
        }


        window.machineOeeActivitySelectionStateV90 = {
            mode:
                (
                    typeof selectedModeV81
                    === "function"
                )
                ? selectedModeV81()
                : "",

            activity_master_id:
                Number(
                    pill.dataset
                        .activityMasterIdV84
                    || 0
                ),

            activity_code:
                String(
                    pill.dataset
                        .activityCodeV81
                    || ""
                ).trim(),

            activity_name:
                String(
                    pill.textContent
                    || ""
                ).trim(),

            remarks_required:
                pill.dataset
                    .remarksRequiredV84
                    === "1"
        };


        body
        .querySelectorAll(
            ".oee-activity-pill-v81"
        )
        .forEach(
            function(button) {

                button.classList.remove(
                    "selected"
                );
            }
        );


        pill.classList.add(
            "selected"
        );


        const reasonWrap =
            document.getElementById(
                "oee-activity-reason-wrap-v81"
            );


        const reasonInput =
            document.getElementById(
                "oee-activity-reason-v81"
            );


        if (
            !reasonWrap
            ||
            !reasonInput
        ) {
            return;
        }


        const required =
            pill.dataset
                .remarksRequiredV84
            === "1";


        reasonWrap.hidden =
            !required;


        reasonInput.required =
            required;


        if (!required) {

            reasonInput.value =
                "";
        }
    },
    true
);




/* OEE_ACTIVITY_SELECTION_BRIDGE_V89 */

/*
 * Expose the current Tool Room / Development selection
 * to the existing no-JC Start/Stop/Loss save flow.
 *
 * Production remains the default when no non-production
 * activity is selected.
 */
window.machineOeeGetActivitySelectionV89 =
    function() {

        const mode =
            (
                typeof selectedModeV81
                === "function"
            )
            ?
            selectedModeV81()
            :
            "PRODUCTION";


        const pill =
            document.querySelector(
                "#oee-activity-body-v81 "
                + ".oee-activity-pill-v81.selected"
            );


        const reasonInput =
            document.getElementById(
                "oee-activity-reason-v81"
            );


        const activityMasterId =
            pill
            ?
            Number(
                pill.dataset
                    .activityMasterIdV84
                || 0
            )
            :
            0;


        const remarksRequired =
            Boolean(
                pill
                &&
                pill.dataset
                    .remarksRequiredV84
                    === "1"
            );


        return {
            mode:
                mode,

            activity_master_id:
                activityMasterId,

            activity_code:
                pill
                ?
                String(
                    pill.dataset
                        .activityCodeV81
                    || ""
                ).trim()
                :
                "",

            activity_name:
                pill
                ?
                String(
                    pill.textContent
                    || ""
                ).trim()
                :
                "",

            remarks_required:
                remarksRequired,

            remarks:
                reasonInput
                ?
                String(
                    reasonInput.value
                    || ""
                ).trim()
                :
                ""
        };
    };


/* OEE_ACTIVITY_DB_MASTER_V84_END */

})();





/* OEE_ACTIVITY_SINGLE_CARD_V81_END */



/* OEE_TOOL_SAVE_MESSAGE_V6
 *
 * Activity/no-JC save feedback now reports the actual number
 * of Tool Position records persisted by Tooling V5.
 *
 * No database logic is changed here.
 */
/* OEE_TOOL_SAVE_MESSAGE_V6_END */



/* MACHINE_OEE_TOOL_SAVE_BUTTON_BOTTOM_V7_END
 *
 * Tool Room / Development layout:
 *
 * Losses
 * Tool Position
 * Save Losses
 *
 * Save logic and database behavior are unchanged.
 */



/* MACHINE_SHIFT_CAPACITY_ACTIVITY_UI_V94_END
 *
 * After Tool Room / Development Save Losses:
 * refresh Shift Used / Remaining immediately.
 *
 * No save or database logic changed.
 */



/* OEE_SELECTED_MACHINE_SUPERVISOR_UI_V98
 *
 * Selected machine Zone Supervisor is displayed
 * as a read-only field below Operator Code.
 *
 * Source:
 * oee_machines.zone_supervisor_name
 */
/* OEE_SELECTED_MACHINE_SUPERVISOR_UI_V98_END */



/* OEE_ZONE_SUPERVISOR_COMPACT_UI_V100
 *
 * Selected machine supervisor is displayed as
 * compact information below the Operator row.
 *
 * It is not an editable input field.
 */
/* OEE_ZONE_SUPERVISOR_COMPACT_UI_V100_END */



/* OEE_FOCUS_STEAL_FIX_V107
 *
 * Prevent hidden / irrelevant Job Card autofocus from
 * stealing focus from Tooling and other operator controls.
 *
 * Production JC autofocus remains available when no other
 * editable control is active.
 */
/* OEE_FOCUS_STEAL_FIX_V107_END */



/* OEE_TOOL_DOM_ANCHOR_FIX_V108
 *
 * Fixed unstable NO-JC Tool Position anchor.
 *
 * Previous:
 * actions.previousElementSibling
 *
 * Problem:
 * after Tool insertion, that element became Tool itself.
 *
 * Final:
 * Save Losses actions container is the stable anchor.
 *
 * Order:
 * Losses -> Tool Position -> Save Losses
 */
/* OEE_TOOL_DOM_ANCHOR_FIX_V108_END */



/* OEE_CYCLE_LOAD_TIME_ENTRY_V111
 *
 * Cycle Time and Load / Unload Time now follow
 * the same operator text-entry behaviour as
 * Start / End Time.
 *
 * No formatting occurs while typing.
 * Normalization occurs on commit/blur.
 *
 * Existing V34 minute/second synchronization,
 * persistence and OEE calculations are retained.
 */
/* OEE_CYCLE_LOAD_TIME_ENTRY_V111_END */







/* =========================================================
   OEE_OPERATOR_TOOL_UID_LOOKUP_V117

   Operator enters/scans a registered physical Tool UID.

   UID
     -> oee_tool_uid
     -> oee_tool_master
     -> Tool Item Code + Tool Name

   Dynamic Tool Position rows are supported through
   event delegation.
   ========================================================= */

(function () {

    function machineOeeClearToolUidV117(
        row
    ) {

        if (!row) {
            return;
        }


        row.dataset.toolUidValidV117 =
            "0";

        row.dataset.toolUidSerialV117 =
            "";

        row.dataset.toolMasterIdV117 =
            "";

        row.dataset.toolItemCodeV117 =
            "";

        row.dataset.toolItemNameV117 =
            "";


        const info =
            row.querySelector(
                ".machine-oee-tool-uid-info-v117"
            );

        const error =
            row.querySelector(
                ".machine-oee-tool-uid-error-v117"
            );


        if (info) {
            info.hidden = true;
        }


        if (error) {

            error.hidden = true;
            error.textContent = "";
        }


        const code =
            row.querySelector(
                ".machine-oee-tool-uid-code-v117"
            );

        const name =
            row.querySelector(
                ".machine-oee-tool-uid-name-v117"
            );

        const status =
            row.querySelector(
                ".machine-oee-tool-uid-status-v117"
            );


        if (code) {
            code.textContent = "";
        }


        if (name) {
            name.textContent = "";
        }


        if (status) {
            status.textContent = "";
        }
    }


    function machineOeeShowToolUidErrorV117(
        row,
        message
    ) {

        machineOeeClearToolUidV117(
            row
        );


        const error =
            row?.querySelector(
                ".machine-oee-tool-uid-error-v117"
            );


        if (error) {

            error.textContent =
                message
                || "Tool UID not registered.";

            error.hidden = false;
        }
    }


    async function machineOeeLookupToolUidV117(
        input
    ) {

        if (!input) {
            return false;
        }


        const row =
            input.closest(
                ".machine-oee-tool-row-v1"
            );


        if (!row) {
            return false;
        }


        const uid =
            String(
                input.value
                || ""
            ).trim();


        machineOeeClearToolUidV117(
            row
        );


        if (!uid) {
            return false;
        }


        input.classList.add(
            "is-checking-v117"
        );


        try {

            const response =
                await fetch(
                    "/api/oee-machine/"
                    + "tool-uid/lookup"
                    + "?uid="
                    + encodeURIComponent(
                        uid
                    )
                );


            const data =
                await response.json();


            if (
                !response.ok
                ||
                !data.success
                ||
                !data.tool
            ) {

                throw new Error(
                    data.error
                    ||
                    "Tool UID not registered."
                );
            }


            const tool =
                data.tool;


            input.value =
                String(
                    tool.tool_uid
                    || uid
                ).trim();


            row.dataset.toolUidValidV117 =
                "1";

            row.dataset.toolUidSerialV117 =
                String(
                    tool.uid_serial
                    || ""
                );

            row.dataset.toolMasterIdV117 =
                String(
                    tool.tool_master_id
                    || ""
                );

            row.dataset.toolItemCodeV117 =
                String(
                    tool.tool_item_code
                    || ""
                );

            row.dataset.toolItemNameV117 =
                String(
                    tool.tool_item_name
                    || ""
                );


            const info =
                row.querySelector(
                    ".machine-oee-tool-uid-info-v117"
                );

            const code =
                row.querySelector(
                    ".machine-oee-tool-uid-code-v117"
                );

            const name =
                row.querySelector(
                    ".machine-oee-tool-uid-name-v117"
                );

            const status =
                row.querySelector(
                    ".machine-oee-tool-uid-status-v117"
                );


            if (code) {

                code.textContent =
                    (
                        "Item: "
                        + (
                            tool.tool_item_code
                            || "-"
                        )
                    );
            }


            if (name) {

                name.textContent =
                    tool.tool_item_name
                    || "-";
            }


            if (status) {

                status.textContent =
                    (
                        "Status: "
                        + (
                            tool.status
                            || "-"
                        )
                    );
            }


            if (info) {
                info.hidden = false;
            }


            return true;


        } catch (error) {

            machineOeeShowToolUidErrorV117(
                row,
                error.message
                ||
                "Tool UID not registered."
            );


            return false;


        } finally {

            input.classList.remove(
                "is-checking-v117"
            );
        }
    }


    /*
     * If operator edits an already validated UID,
     * immediately clear the old Tool Item relation.
     */
    document.addEventListener(
        "input",
        function (event) {

            const input =
                event.target?.closest?.(
                    ".machine-oee-tool-uid-v1"
                );


            if (!input) {
                return;
            }


            const row =
                input.closest(
                    ".machine-oee-tool-row-v1"
                );


            if (!row) {
                return;
            }


            machineOeeClearToolUidV117(
                row
            );
        },
        true
    );


    /*
     * Lookup when operator leaves UID field.
     */
    document.addEventListener(
        "blur",
        function (event) {

            const input =
                event.target?.closest?.(
                    ".machine-oee-tool-uid-v1"
                );


            if (!input) {
                return;
            }


            machineOeeLookupToolUidV117(
                input
            );
        },
        true
    );


    /*
     * Scanner / keyboard:
     * pressing Enter validates immediately.
     */
    document.addEventListener(
        "keydown",
        function (event) {

            const input =
                event.target?.closest?.(
                    ".machine-oee-tool-uid-v1"
                );


            if (!input) {
                return;
            }


            if (
                event.key
                !== "Enter"
            ) {
                return;
            }


            event.preventDefault();


            machineOeeLookupToolUidV117(
                input
            );
        },
        true
    );


    /*
     * Expose lookup for future save validation.
     */
    window.machineOeeLookupToolUidV117 =
        machineOeeLookupToolUidV117;

})();


/* OEE_OPERATOR_TOOL_UID_LOOKUP_V117_END */


/* OEE_TOOL_UID_SAVE_GUARD_V118_END */


/* OEE_PRODUCTION_SAVE_LOSSES_TOOLING_V119_END */
