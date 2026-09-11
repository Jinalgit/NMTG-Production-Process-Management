function renderPendingAutoRequirements(){

    const tbody =
        document.getElementById(
            "cp-auto-body"
        );

    if(!tbody){
        return;
    }


    cpEnsurePendingAutoCutSizeColumn();


    const rows =
        window.cpPendingAutoRows || [];


    const counter =
        document.getElementById(
            "cp-auto-count"
        );

    if(counter){
        counter.textContent =
            rows.length;
    }


    if(!rows.length){

        tbody.innerHTML = `
            <tr>
                <td
                    colspan="9"
                    class="cp-auto-empty"
                >
                    <div class="cp-auto-empty-title">
                        No pending AUTO requirements
                    </div>

                    <div>
                        New Job Cards will appear here after
                        Raw Material advances to Cutting.
                    </div>
                </td>
            </tr>
        `;


        window.cpPendingAutoSelected.clear();

        updatePendingAutoSelectionUI();

        return;

    }


    tbody.innerHTML =
        rows.map(plan => {


        const checked =
            window.cpPendingAutoSelected.has(
                Number(plan.id)
            );


        const hasMaterial =
            String(
                plan.material_spec || ""
            ).trim() !== "";


        const hasCutSize =
            String(
                plan.cut_size || ""
            ).trim() !== "";


        const qty =
            Number(
                plan.planned_qty || 0
            );


        const hasQty =
            Number.isInteger(qty)
            &&
            qty > 0;


        return `
            <tr
                class="${checked ? "selected" : ""}"
                data-plan-id="${plan.id}"
            >


                <!-- SELECT -->
                <td class="cp-check-col">

                    <input
                        type="checkbox"
                        class="cp-auto-row-check"
                        ${checked ? "checked" : ""}
                        onchange="togglePendingAutoRow(
                            ${plan.id},
                            this.checked
                        )"
                    >

                </td>


                <!-- JOB CARD -->
                <td>

                    <div class="cp-auto-jc">

                        ${cpEscapeHtml(
                            plan.job_card_no || "-"
                        )}

                    </div>

                    <div class="cp-auto-source-id">

                        AUTO #${plan.id}

                    </div>

                </td>


                <!-- DATE -->
                <td>

                    ${cpEscapeHtml(
                        cpFormatPlannedDate(
                            plan.planned_date,
                            "-"
                        )
                    )}

                </td>


                <!-- MATERIAL -->
                <td>

                    <input
                        type="text"

                        value="${cpEscapeHtml(
                            plan.material_spec || ""
                        )}"

                        placeholder="Enter Material"

                        onchange="
                            savePendingAutoEditableField(
                                ${plan.id},
                                'material_spec',
                                this
                            )
                        "

                        style="
                            width:100%;
                            min-width:190px;
                            padding:7px 8px;

                            border:${
                                hasMaterial
                                    ? "1px solid #cfd6df"
                                    : "1px solid #c62828"
                            };

                            border-radius:6px;
                            box-sizing:border-box;
                        "
                    >


                    ${
                        !hasMaterial
                        ? `
                            <div
                                style="
                                    margin-top:4px;
                                    color:#c62828;
                                    font-size:11px;
                                    font-weight:700;
                                    white-space:nowrap;
                                "
                            >
                                MATERIAL REQUIRED
                            </div>
                        `
                        : ""
                    }

                </td>


                <!-- CUT SIZE -->
                <td>

                    <input
                        type="text"

                        value="${cpEscapeHtml(
                            plan.cut_size || ""
                        )}"

                        placeholder="Enter Cut Size"

                        onchange="
                            savePendingAutoEditableField(
                                ${plan.id},
                                'cut_size',
                                this
                            )
                        "

                        style="
                            width:100%;
                            min-width:115px;
                            padding:7px 8px;

                            border:${
                                hasCutSize
                                    ? "1px solid #cfd6df"
                                    : "1px solid #c62828"
                            };

                            border-radius:6px;
                            box-sizing:border-box;
                        "
                    >


                    ${
                        !hasCutSize
                        ? `
                            <div
                                style="
                                    margin-top:4px;
                                    color:#c62828;
                                    font-size:11px;
                                    font-weight:700;
                                    white-space:nowrap;
                                "
                            >
                                CUT SIZE REQUIRED
                            </div>
                        `
                        : ""
                    }

                </td>


                <!-- QTY -->
                <td>

                    <input
                        type="number"

                        min="1"
                        step="1"

                        value="${
                            hasQty
                                ? qty
                                : ""
                        }"

                        placeholder="Qty"

                        onchange="
                            savePendingAutoEditableField(
                                ${plan.id},
                                'planned_qty',
                                this
                            )
                        "

                        style="
                            width:85px;
                            padding:7px 8px;

                            border:${
                                hasQty
                                    ? "1px solid #cfd6df"
                                    : "1px solid #c62828"
                            };

                            border-radius:6px;
                            box-sizing:border-box;
                            text-align:center;
                            font-weight:600;
                        "
                    >


                    ${
                        !hasQty
                        ? `
                            <div
                                style="
                                    margin-top:4px;
                                    color:#c62828;
                                    font-size:11px;
                                    font-weight:700;
                                    white-space:nowrap;
                                "
                            >
                                QTY REQUIRED
                            </div>
                        `
                        : ""
                    }

                </td>


                <!-- PART -->
                <td>

                    ${cpEscapeHtml(
                        plan.part || "-"
                    )}

                </td>


                <!-- MODEL -->
                <td class="cp-model-cell">

                    ${cpEscapeHtml(
                        plan.model_size ||
                        plan.item_name ||
                        "-"
                    )}

                </td>


                <!-- MOVE TO -->
                <td>

                    ${cpPendingMovePills(plan)}

                </td>


            </tr>
        `;

    }).join("");


    updatePendingAutoSelectionUI();

}


/* ==========================================================
   CUTTING_PLAN_DD_MM_YYYY_V1

   Display only:
       YYYY-MM-DD -> DD-MM-YYYY

   Database/API value remains unchanged.
   ========================================================== */

function cpFormatPlannedDate(
    value,
    fallback = "-"
){

    const raw = String(
        value || ""
    ).trim();


    if(!raw){

        return fallback;

    }


    const match = raw.match(
        /^(\d{4})-(\d{2})-(\d{2})/
    );


    if(!match){

        return raw;

    }


    return (
        `${match[3]}-${match[2]}-${match[1]}`
    );

}




async function loadCuttingPlans(){

    try{

        const res =
            await fetch(
                "/api/cutting-plan/plans"
            );


        const data =
            await res.json();


        const plans =
            data.plans || [];


        /*
         * Keep original DB rows available
         * for detail-level functions later.
         */
        window.cuttingPlans = plans;


        /*
         * BATCHWISE_PLANNING_LIST_V3
         *
         * Same plan_batch_no
         * = ONE Cutting Plan on planning screen.
         *
         * Legacy record without plan_batch_no
         * = its own single-row Cutting Plan.
         */

        const batchMap = new Map();


        plans.forEach(function(plan){

            const hasBatch =
                plan.plan_batch_no !== null
                &&
                plan.plan_batch_no !== undefined
                &&
                String(
                    plan.plan_batch_no
                ).trim() !== "";


            const key =
                hasBatch
                    ? "batch-" + String(plan.plan_batch_no)
                    : "single-" + String(plan.id);


            if(!batchMap.has(key)){

                batchMap.set(
                    key,
                    {
                        key: key,
                        plan_batch_no:
                            hasBatch
                                ? plan.plan_batch_no
                                : null,
                        rows: []
                    }
                );

            }


            batchMap
                .get(key)
                .rows
                .push(plan);

        });


        const batches =
            Array.from(
                batchMap.values()
            );


        window.cuttingPlanBatches =
            batches;


        function uniqueValues(rows, field){

            return Array.from(
                new Set(
                    rows
                        .map(function(row){

                            return String(
                                row[field] || ""
                            ).trim();

                        })
                        .filter(Boolean)
                )
            );

        }


        function sourceDisplay(rows){

            const values =
                uniqueValues(
                    rows,
                    "source_type"
                );

            if(!values.length){
                return "-";
            }

            if(values.length === 1){
                return values[0];
            }

            return "MIXED";
        }


        function jobCardDisplay(rows){

            const values =
                uniqueValues(
                    rows,
                    "job_card_no"
                );

            if(!values.length){
                return "-";
            }

            if(values.length === 1){
                return values[0];
            }

            return values.length + " JCs";
        }


        function materialDisplay(rows){

            const values =
                uniqueValues(
                    rows,
                    "material_spec"
                );


            if(!values.length){
                return "-";
            }


            if(values.length <= 3){

                return values.join(", ");

            }


            return (
                values
                    .slice(0, 3)
                    .join(", ")
                + " +"
                + (values.length - 3)
            );
        }


        function dateDisplay(rows){

            const values =
                uniqueValues(
                    rows,
                    "planned_date"
                );


            if(!values.length){
                return "-";
            }


            if(values.length === 1){
                return values[0];
            }


            return "Multiple";
        }


        /*
         * Total = number of Cutting Plan batches,
         * not number of underlying records.
         */

        const totalEl =
            document.getElementById(
                "cp-total"
            );


        if(totalEl){

            totalEl.innerText =
                batches.length;

        }


        const tbody =
            document.getElementById(
                "cutting-plan-body"
            );


        if(!tbody){
            return;
        }


        tbody.innerHTML = "";


        if(!batches.length){

            tbody.innerHTML = `
                <tr>
                    <td
                        colspan="7"
                        style="text-align:center">
                        No Cutting Plans found
                    </td>
                </tr>
            `;

            return;
        }


        batches.forEach(function(batch){

            const rows =
                batch.rows
                    .slice()
                    .sort(function(a, b){

                        return (
                            Number(a.id)
                            -
                            Number(b.id)
                        );

                    });


            if(!rows.length){
                return;
            }


            /*
             * Any record ID in a batch can be used.
             * Backend Print loads all records with
             * the same plan_batch_no.
             */
            const firstPlan =
                rows[0];


            const totalQty =
                rows.reduce(
                    function(total, row){

                        return (
                            total
                            +
                            Number(
                                row.planned_qty || 0
                            )
                        );

                    },
                    0
                );


            tbody.innerHTML += `

                <tr>

                    <td>
                        ${sourceDisplay(rows)}
                    </td>

                    <td>
                        ${jobCardDisplay(rows)}
                    </td>

                    <td>
                        <strong>
                            ${rows.length}
                        </strong>
                    </td>

                    <td>
                        ${materialDisplay(rows)}
                    </td>

                    <td>
                        <strong>
                            ${totalQty}
                        </strong>
                    </td>

                    <td>
                        ${dateDisplay(rows)}
                    </td>

                    <td>

                        <button
                            class="cp-btn cp-primary"
                            onclick="
                                window.location.href=
                                '/cutting-plan/${firstPlan.id}/print'
                            ">
                            Print
                        </button>

                    </td>

                </tr>

            `;

        });

        




    }
    catch(e){

        console.error(
            "Cutting Plan Error",
            e
        );

    }

}


document.addEventListener(
"DOMContentLoaded",
loadCuttingPlans
);






















let manualCuttingPlanRowCounter = 0;


function openManualPlanModal(){

    const modal =
        document.getElementById("manual-plan-modal");

    const tbody =
        document.getElementById("manual-batch-rows");


    if(!modal || !tbody){
        return;
    }


    if(!tbody.children.length){

        addManualCuttingPlanRow();

    }


    modal.style.display = "flex";

}


function closeManualPlanModal(){

    const modal =
        document.getElementById("manual-plan-modal");


    if(modal){

        modal.style.display = "none";

    }

}


function addManualCuttingPlanRow(){

    const tbody =
        document.getElementById("manual-batch-rows");


    if(!tbody){
        return;
    }


    manualCuttingPlanRowCounter += 1;

    const rowKey =
        manualCuttingPlanRowCounter;


    const card =
        document.createElement("div");

    card.className =
        "cp-batch-entry-row cp-cutting-sheet-row";

    card.dataset.rowKey =
        String(rowKey);


    card.innerHTML = `

        <div class="cp-sheet-cell cp-sheet-sr">
            <span class="cp-batch-row-number"></span>
        </div>


        <div class="cp-sheet-cell">
            <input
                type="date"
                class="cp-batch-input cp-row-planned-date">
        </div>


        <div class="cp-sheet-cell">
            <input
                type="text"
                class="cp-batch-input cp-row-material"
                placeholder="EN9">
        </div>


        <div class="cp-sheet-cell">

            <div class="cp-sheet-cut-size">

                <span>D</span>

                <input
                    type="number"
                    min="0"
                    step="any"
                    class="cp-batch-small-input cp-row-cut-dia"
                    placeholder="90">

                <span>mm</span>

                <span>x</span>

                <span>TL</span>

                <input
                    type="number"
                    min="0"
                    step="any"
                    class="cp-batch-small-input cp-row-cut-tl"
                    placeholder="35">

                <span>mm</span>

            </div>

        </div>


        <div class="cp-sheet-cell">
            <input
                type="number"
                min="1"
                step="1"
                class="cp-batch-input cp-row-qty"
                placeholder="10">
        </div>


        <div class="cp-sheet-cell">
            <input
                type="text"
                class="cp-batch-input cp-row-part"
                placeholder="Inner">
        </div>


        <div class="cp-sheet-cell">
            <input
                type="text"
                class="cp-batch-input cp-row-model"
                placeholder="N7012 - 85 x 125 x 28">
        </div>


        <div class="cp-sheet-cell">
            <input
                type="text"
                class="cp-batch-input cp-row-so"
                placeholder="Advance Plan">
        </div>


        <div class="cp-sheet-cell">

            <div class="cp-sheet-move-pills">

                <button
                    type="button"
                    class="cp-batch-move-pill"
                    data-value="F"
                    onclick="selectManualBatchMoveTo(this)">
                    F
                </button>

                <button
                    type="button"
                    class="cp-batch-move-pill"
                    data-value="SC"
                    onclick="selectManualBatchMoveTo(this)">
                    SC
                </button>

                <button
                    type="button"
                    class="cp-batch-move-pill"
                    data-value="U1"
                    onclick="selectManualBatchMoveTo(this)">
                    U1
                </button>

                <button
                    type="button"
                    class="cp-batch-move-pill"
                    data-value="U2"
                    onclick="selectManualBatchMoveTo(this)">
                    U2
                </button>

                <input
                    type="hidden"
                    class="cp-row-move-to"
                    value="">

            </div>

        </div>


        <div class="cp-sheet-cell cp-sheet-remove-cell">

            <button
                type="button"
                class="cp-batch-remove-btn"
                title="Remove row"
                onclick="removeManualCuttingPlanRow(this)">
                &times;
            </button>

        </div>

    `;


    tbody.appendChild(card);

    renumberManualCuttingPlanRows();

}


function removeManualCuttingPlanRow(button){

    const tbody =
        document.getElementById("manual-batch-rows");


    if(!tbody){
        return;
    }


    if(tbody.children.length <= 1){

        showToast(
            "At least one Cutting Plan row is required.",
            "warning"
        );

        return;

    }


    const row =
        button.closest(".cp-batch-entry-row");


    if(row){
        row.remove();
    }


    renumberManualCuttingPlanRows();

}


function renumberManualCuttingPlanRows(){

    document.querySelectorAll(
        "#manual-batch-rows .cp-batch-entry-row"
    ).forEach(function(row, index){

        const number =
            row.querySelector(".cp-batch-row-number");

        if(number){

            number.textContent =
                String(index + 1);

        }

    });

}


function selectManualBatchMoveTo(button){

    const holder =
        button.closest(".cp-sheet-move-pills");


    if(!holder){
        return;
    }


    const value =
        String(button.dataset.value || "")
            .trim()
            .toUpperCase();


    holder.querySelectorAll(
        ".cp-batch-move-pill"
    ).forEach(function(item){

        item.classList.toggle(
            "selected",
            item === button
        );

    });


    const hidden =
        holder.querySelector(".cp-row-move-to");


    if(hidden){

        hidden.value = value;

    }

}


function buildManualCutSize(row){

    const dia =
        normalizeCuttingNumber(
            row.querySelector(
                ".cp-row-cut-dia"
            )?.value
        );

    const tl =
        normalizeCuttingNumber(
            row.querySelector(
                ".cp-row-cut-tl"
            )?.value
        );


    if(!dia || !tl){
        return "";
    }


    return (
        "D"
        + dia
        + " mm x TL"
        + tl
        + " mm"
    );

}


async function createManualCuttingPlan(){

    const rowElements = Array.from(
        document.querySelectorAll(
            "#manual-batch-rows .cp-batch-entry-row"
        )
    );


    if(!rowElements.length){

        showToast(
            "Add at least one Cutting Plan row.",
            "error"
        );

        return;

    }


    const rows = [];


    for(
        let index = 0;
        index < rowElements.length;
        index += 1
    ){

        const row =
            rowElements[index];

        const rowNumber =
            index + 1;


        const plannedDate =
            row.querySelector(
                ".cp-row-planned-date"
            )?.value || "";


        const material =
            row.querySelector(
                ".cp-row-material"
            )?.value.trim() || "";


        const cutSize =
            buildManualCutSize(row);


        const qty =
            Number(
                row.querySelector(
                    ".cp-row-qty"
                )?.value || 0
            );


        const part =
            row.querySelector(
                ".cp-row-part"
            )?.value.trim() || "";


        const modelSize =
            normalizeCuttingModelSize(
                row.querySelector(
                    ".cp-row-model"
                )?.value || ""
            );


        const soNo =
            row.querySelector(
                ".cp-row-so"
            )?.value.trim() || "";


        const moveTo =
            row.querySelector(
                ".cp-row-move-to"
            )?.value.trim() || "";


        if(qty <= 0){

            showToast(
                "Row "
                + rowNumber
                + ": Quantity must be greater than zero.",
                "error"
            );

            return;

        }


        // Move To retired from manual Cutting Plan.

        rows.push({

            planned_date:
                plannedDate,

            material_spec:
                material,

            cut_size:
                cutSize,

            planned_qty:
                qty,

            part:
                part,

            model_size:
                modelSize,

            so_no:
                soNo

        });

    }


    const remarks =
        document.getElementById(
            "manual-remarks"
        )?.value.trim() || "";


    const payload = {

        rows:
            rows,

        remarks:
            remarks

    };


    try{

        const response =
            await fetch(
                "/api/cutting-plan/manual",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(payload)
                }
            );


        const data =
            await response.json();


        if(!response.ok || !data.success){

            showToast(
                data.error
                || "Unable to create Cutting Plan.",
                "error"
            );

            return;

        }


        showToast(
            data.message
            || "Cutting Plan created.",
            "success"
        );


        closeManualPlanModal();

        clearManualPlanForm();

        loadCuttingPlans();


    }
    catch(error){

        console.error(error);

        showToast(
            "Unable to create Cutting Plan.",
            "error"
        );

    }

}


function clearManualPlanForm(){

    const tbody =
        document.getElementById(
            "manual-batch-rows"
        );


    if(tbody){

        tbody.innerHTML = "";

    }


    const remarks =
        document.getElementById(
            "manual-remarks"
        );


    if(remarks){

        remarks.value = "";

    }


    manualCuttingPlanRowCounter = 0;

    addManualCuttingPlanRow();

}


function setCuttingPlanViewValue(id, value){

    const el = document.getElementById(id);

    if(!el){
        return;
    }

    el.value = (
        value === null ||
        value === undefined ||
        value === ""
    ) ? "-" : value;

}


function openCuttingPlanView(planId){

    const plans = window.cuttingPlans || [];

    const plan = plans.find(function(item){
        return String(item.id) === String(planId);
    });


    if(!plan){

        showToast(
            "Cutting Plan details not found",
            "error"
        );

        return;

    }


    setCuttingPlanViewValue(
        "view-source",
        plan.source_type
    );

    setCuttingPlanViewValue(
        "view-job-card",
        plan.job_card_no
    );

    setCuttingPlanViewValue(
        "view-part",
        plan.part || plan.item_name
    );

    setCuttingPlanViewValue(
        "view-material",
        plan.material_spec
    );

    setCuttingPlanViewValue(
        "view-cut-size",
        plan.cut_size
    );

    setCuttingPlanViewValue(
        "view-qty",
        plan.planned_qty
    );

    setCuttingPlanViewValue(
        "view-model-size",
        normalizeCuttingModelSize(
            plan.model_size
        )
    );

    setCuttingPlanViewValue(
        "view-so",
        plan.so_display ||
        plan.so_no ||
        "Advance Plan"
    );

    setCuttingPlanViewValue(
        "view-move-to",
        plan.move_to
    );

    setCuttingPlanViewValue(
        "view-status",
        plan.status
    );

    setCuttingPlanViewValue(
        "view-created-date",
        plan.created_at
    );

    setCuttingPlanViewValue(
        "view-remarks",
        plan.remarks
    );


    const modal = document.getElementById(
        "cutting-plan-view-modal"
    );

    if(modal){
        modal.style.display = "flex";
    }

}


function closeCuttingPlanView(){

    const modal = document.getElementById(
        "cutting-plan-view-modal"
    );

    if(modal){
        modal.style.display = "none";
    }

}

async function releaseCuttingPlan(planId, button){

    if(button){
        button.disabled = true;
        button.textContent = "Releasing...";
    }

    try{

        const response = await fetch(
            `/api/cutting-plan/${planId}/release`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                }
            }
        );


        const data = await response.json();


        if(data.success){

            showToast(
                "Cutting Plan released successfully",
                "success"
            );

            await loadCuttingPlans();

            return;
        }


        showToast(
            data.error || "Unable to release Cutting Plan",
            "error"
        );

    }
    catch(error){

        console.error(
            "Cutting Plan Release Error",
            error
        );

        showToast(
            "Server error while releasing Cutting Plan",
            "error"
        );

    }
    finally{

        if(button && document.body.contains(button)){
            button.disabled = false;
            button.textContent = "Release";
        }

    }

}

function setEditValue(id, value){

    const el = document.getElementById(id);

    if(!el){
        return;
    }

    el.value = (
        value === null ||
        value === undefined
    ) ? "" : value;

}


function openEditCuttingPlan(planId){

    const plans = window.cuttingPlans || [];

    const plan = plans.find(function(item){
        return String(item.id) === String(planId);
    });


    if(!plan){

        showToast(
            "Cutting Plan details not found",
            "error"
        );

        return;

    }


    if(plan.status !== "Draft"){

        showToast(
            "Only Draft Cutting Plans can be edited here",
            "error"
        );

        return;

    }


    setEditValue("edit-plan-id", plan.id);
    setEditValue("edit-planned-date", plan.planned_date);

    setEditValue("edit-material", plan.material_spec);
    setEditValue("edit-cut-size", plan.cut_size);

    loadCuttingCutSize(
        "edit",
        plan.cut_size
    );
    setEditValue("edit-qty", plan.planned_qty);
    setEditValue("edit-part", plan.part);
    setEditValue(
        "edit-model-size",
        normalizeCuttingModelSize(
            plan.model_size
        )
    );
    setEditValue("edit-so", plan.so_no);
    setEditValue("edit-move", plan.move_to);

    syncCuttingMoveToPills(
        "edit",
        plan.move_to
    );
    setEditValue("edit-remarks", plan.remarks);


    const modal = document.getElementById(
        "edit-cutting-plan-modal"
    );

    if(modal){
        modal.style.display = "flex";
    }

}


function closeEditCuttingPlan(){

    const modal = document.getElementById(
        "edit-cutting-plan-modal"
    );

    if(modal){
        modal.style.display = "none";
    }

}


async function saveEditCuttingPlan(){

    const planId =
        document.getElementById("edit-plan-id").value;


    const payload = {

        planned_date:
        document.getElementById("edit-planned-date").value,

        material_spec:
        document.getElementById("edit-material").value.trim(),

        cut_size:
        document.getElementById("edit-cut-size").value.trim(),

        planned_qty:
        Number(
            document.getElementById("edit-qty").value || 0
        ),

        part:
        document.getElementById("edit-part").value.trim(),

        model_size:
        normalizeCuttingModelSize(
            document.getElementById("edit-model-size").value
        ),

        so_no:
        document.getElementById("edit-so").value.trim(),

        move_to:
        document.getElementById("edit-move").value.trim(),

        remarks:
        document.getElementById("edit-remarks").value.trim()

    };


    if(!payload.planned_qty){

        showToast(
            "Quantity must be greater than zero",
            "error"
        );

        return;

    }


    const button =
        document.getElementById("edit-save-btn");

    if(button){
        button.disabled = true;
        button.textContent = "Saving...";
    }


    try{

        const response = await fetch(
            `/api/cutting-plan/${planId}`,
            {
                method: "PATCH",

                headers:{
                    "Content-Type":"application/json"
                },

                body: JSON.stringify(payload)
            }
        );


        const data = await response.json();


        if(data.success){

            closeEditCuttingPlan();

            showToast(
                "Cutting Plan updated successfully",
                "success"
            );

            await loadCuttingPlans();

        }
        else{

            showToast(
                data.error || "Unable to update Cutting Plan",
                "error"
            );

        }

    }
    catch(error){

        console.error(
            "Cutting Plan Edit Error",
            error
        );

        showToast(
            "Server error while updating Cutting Plan",
            "error"
        );

    }
    finally{

        if(button){
            button.disabled = false;
            button.textContent = "Save Changes";
        }

    }

}

function syncCuttingMoveToPills(scope, value){

    const selectedValue = String(value || "")
        .trim()
        .toUpperCase();

    document.querySelectorAll(
        `.cp-move-pills[data-scope="${scope}"] .cp-move-pill`
    ).forEach(function(button){

        const buttonValue = String(
            button.dataset.value || ""
        ).trim().toUpperCase();

        button.classList.toggle(
            "selected",
            buttonValue === selectedValue
        );

    });

}


function selectCuttingMoveTo(scope, value){

    const inputId =
        scope === "edit"
            ? "edit-move"
            : "manual-move";

    const input =
        document.getElementById(inputId);

    if(!input){
        return;
    }

    input.value = String(value || "")
        .trim()
        .toUpperCase();

    syncCuttingMoveToPills(
        scope,
        input.value
    );

}

function normalizeCuttingNumber(value){

    const raw = String(value ?? "").trim();

    if(!raw){
        return "";
    }

    const num = Number(raw);

    if(!Number.isFinite(num)){
        return "";
    }

    return String(num);
}


function syncCuttingCutSize(scope){

    const prefix =
        scope === "edit"
            ? "edit"
            : "manual";

    const diaInput =
        document.getElementById(prefix + "-cut-dia");

    const tlInput =
        document.getElementById(prefix + "-cut-tl");

    const hiddenInput =
        document.getElementById(prefix + "-cut-size");


    if(!diaInput || !tlInput || !hiddenInput){
        return;
    }


    const dia =
        normalizeCuttingNumber(diaInput.value);

    const tl =
        normalizeCuttingNumber(tlInput.value);


    if(!dia || !tl){

        hiddenInput.value = "";
        return;

    }


    hiddenInput.value =
        "D" + dia + " mm x TL" + tl + " mm";
}


function parseCuttingCutSize(value){

    const text =
        String(value || "").trim();

    if(!text){

        return {
            dia: "",
            tl: ""
        };

    }


    const numbers =
        text.match(/\d+(?:\.\d+)?/g) || [];


    return {
        dia: numbers[0] || "",
        tl: numbers[1] || ""
    };
}


function loadCuttingCutSize(scope, value){

    const prefix =
        scope === "edit"
            ? "edit"
            : "manual";

    const parsed =
        parseCuttingCutSize(value);

    const diaInput =
        document.getElementById(prefix + "-cut-dia");

    const tlInput =
        document.getElementById(prefix + "-cut-tl");


    if(diaInput){
        diaInput.value = parsed.dia;
    }

    if(tlInput){
        tlInput.value = parsed.tl;
    }


    syncCuttingCutSize(scope);
}

function normalizeCuttingModelSize(value){

    const text =
        String(value || "").trim();

    if(!text){
        return "";
    }


    /*
      Examples:

      Inner Ring of N7012 - 85 x 125 x 28
          ->
      N7012 - 85 x 125 x 28

      Outer Race of NRHD 1400 - 750 x 330
          ->
      NRHD 1400 - 750 x 330

      N7012 - 85 x 125 x 28
          ->
      N7012 - 85 x 125 x 28
    */

    const match =
        text.match(/^.+?\s+of\s+(.+)$/i);


    if(match && match[1]){

        return match[1].trim();

    }


    return text;
}




/* ==========================================================
   AUTO_PENDING_REQUIREMENTS_UI_V1
   ========================================================== */

window.cpPendingAutoRows = [];
window.cpPendingAutoSelected = new Set();


function cpEscapeHtml(value){

    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

}


function cpPendingMovePills(plan){

    const selected = String(
        plan.move_to || ""
    ).toUpperCase();


    return `
        <div
            class="cp-auto-move-pills"
            data-plan-id="${plan.id}"
        >
            ${["F","SC","U1","U2"].map(value => `
                <button
                    type="button"
                    class="cp-auto-move-pill
                    ${selected === value ? "active" : ""}"
                    onclick="setPendingAutoMove(
                        ${plan.id},
                        '${value}'
                    )"
                >
                    ${value}
                </button>
            `).join("")}
        </div>
    `;

}


function updatePendingAutoSelectionUI(){

    const selectedCount =
        window.cpPendingAutoSelected.size;


    const label = document.getElementById(
        "cp-auto-selection-label"
    );

    if(label){

        label.textContent =
            `${selectedCount} selected`;

    }


    const button = document.getElementById(
        "cp-auto-create-batch-btn"
    );

    if(button){

        button.disabled =
            selectedCount === 0;

    }


    const selectAll = document.getElementById(
        "cp-auto-select-all"
    );

    if(selectAll){

        const selectable =
            window.cpPendingAutoRows.length;

        selectAll.checked =
            selectable > 0 &&
            selectedCount === selectable;

        selectAll.indeterminate =
            selectedCount > 0 &&
            selectedCount < selectable;

    }

}


function renderPendingAutoRequirements(){

    const tbody = document.getElementById(
        "cp-auto-body"
    );

    if(!tbody){
        return;
    }


    const rows =
        window.cpPendingAutoRows || [];


    const counter = document.getElementById(
        "cp-auto-count"
    );

    if(counter){
        counter.textContent = rows.length;
    }


    if(!rows.length){

        tbody.innerHTML = `
            <tr>
                <td
                    colspan="8"
                    class="cp-auto-empty"
                >
                    <div class="cp-auto-empty-title">
                        No pending AUTO requirements
                    </div>

                    <div>
                        New Job Cards will appear here after
                        Raw Material advances to Cutting.
                    </div>
                </td>
            </tr>
        `;

        window.cpPendingAutoSelected.clear();

        updatePendingAutoSelectionUI();

        return;
    }


    tbody.innerHTML = rows.map(plan => {

        const checked =
            window.cpPendingAutoSelected.has(
                Number(plan.id)
            );


        const material =
            plan.material_spec ||
            "Not available";


        return `
            <tr
                class="${checked ? "selected" : ""}"
                data-plan-id="${plan.id}"
            >

                <td class="cp-check-col">

                    <input
                        type="checkbox"
                        class="cp-auto-row-check"
                        ${checked ? "checked" : ""}
                        onchange="togglePendingAutoRow(
                            ${plan.id},
                            this.checked
                        )"
                    >

                </td>


                <td>

                    <div class="cp-auto-jc">
                        ${cpEscapeHtml(
                            plan.job_card_no || "-"
                        )}
                    </div>

                    <div class="cp-auto-source-id">
                        AUTO #${plan.id}
                    </div>

                </td>


                <td>
                    ${cpEscapeHtml(
                        cpFormatPlannedDate(plan.planned_date, "-")
                    )}
                </td>


                <td>

                    <span class="${
                        plan.material_spec
                        ? ""
                        : "cp-value-missing"
                    }">

                        ${cpEscapeHtml(material)}

                    </span>

                </td>


                <td>

                    <span class="cp-qty-badge">
                        ${Number(
                            plan.planned_qty || 0
                        )}
                    </span>

                </td>


                <td>
                    ${cpEscapeHtml(
                        plan.part || "-"
                    )}
                </td>


                <td class="cp-model-cell">
                    ${cpEscapeHtml(
                        plan.model_size ||
                        plan.item_name ||
                        "-"
                    )}
                </td>


                <td>
                    ${cpPendingMovePills(plan)}
                </td>

            </tr>
        `;

    }).join("");


    updatePendingAutoSelectionUI();

}


async function loadPendingAutoRequirements(){

    const tbody = document.getElementById(
        "cp-auto-body"
    );


    if(tbody){

        tbody.innerHTML = `
            <tr>
                <td
                    colspan="8"
                    class="cp-auto-empty"
                >
                    Loading pending requirements...
                </td>
            </tr>
        `;

    }


    try{

        const response = await fetch(
            "/api/cutting-plan/plans" +
            "?source_type=AUTO" +
            "&status=Draft" +
            "&include_pending_auto=1" +
            "&limit=500"
        );


        const data = await response.json();


        if(!response.ok || !data.success){

            throw new Error(
                data.error ||
                "Unable to load pending AUTO requirements."
            );

        }


        window.cpPendingAutoRows = (
            data.plans || []
        ).filter(plan => {

            return (
                String(
                    plan.source_type || ""
                ).toUpperCase() === "AUTO"
                &&
                String(
                    plan.status || ""
                ) === "Draft"
                &&
                (
                    plan.plan_batch_no === null
                    ||
                    plan.plan_batch_no === ""
                    ||
                    typeof plan.plan_batch_no ===
                        "undefined"
                )
            );

        });


        const validIds = new Set(
            window.cpPendingAutoRows.map(
                row => Number(row.id)
            )
        );


        window.cpPendingAutoSelected =
            new Set(
                Array.from(
                    window.cpPendingAutoSelected
                ).filter(
                    id => validIds.has(id)
                )
            );


        renderPendingAutoRequirements();


    }
    catch(error){

        console.error(
            "Pending AUTO Cutting Plan Error",
            error
        );


        if(tbody){

            tbody.innerHTML = `
                <tr>
                    <td
                        colspan="8"
                        class="cp-auto-empty cp-auto-error"
                    >
                        ${cpEscapeHtml(
                            error.message ||
                            "Unable to load pending requirements."
                        )}
                    </td>
                </tr>
            `;

        }


        showToast(
            error.message ||
            "Unable to load pending AUTO requirements.",
            "error"
        );

    }

}


function togglePendingAutoRow(
    planId,
    checked
){

    planId = Number(planId);


    if(checked){

        window.cpPendingAutoSelected.add(
            planId
        );

    }
    else{

        window.cpPendingAutoSelected.delete(
            planId
        );

    }


    renderPendingAutoRequirements();

}


function togglePendingAutoSelectAll(
    checked
){

    window.cpPendingAutoSelected.clear();


    if(checked){

        window.cpPendingAutoRows.forEach(
            row => {

                window.cpPendingAutoSelected.add(
                    Number(row.id)
                );

            }
        );

    }


    renderPendingAutoRequirements();

}


async function setPendingAutoMove(
    planId,
    moveTo
){

    moveTo = String(
        moveTo || ""
    ).toUpperCase();


    if(
        !["F","SC","U1","U2"].includes(
            moveTo
        )
    ){

        showToast(
            "Invalid Move To selection.",
            "error"
        );

        return;

    }


    try{

        const response = await fetch(
            `/api/cutting-plan/${planId}`,
            {
                method:"PATCH",

                headers:{
                    "Content-Type":
                    "application/json"
                },

                body:JSON.stringify({
                    move_to:moveTo
                })
            }
        );


        const data =
            await response.json();


        if(!response.ok || !data.success){

            throw new Error(
                data.error ||
                "Unable to update Move To."
            );

        }


        const row =
            window.cpPendingAutoRows.find(
                item =>
                    Number(item.id) ===
                    Number(planId)
            );


        if(row){
            row.move_to = moveTo;
        }


        renderPendingAutoRequirements();


        showToast(
            `Move To set to ${moveTo}`,
            "success"
        );


    }
    catch(error){

        console.error(error);

        showToast(
            error.message ||
            "Unable to update Move To.",
            "error"
        );

    }

}


async function createSelectedAutoBatch(){

    const planIds =
        Array.from(
            window.cpPendingAutoSelected
        );


    if(!planIds.length){

        showToast(
            "Select at least one AUTO requirement.",
            "error"
        );

        return;

    }


    const selectedRows =
        window.cpPendingAutoRows.filter(
            row =>
                planIds.includes(
                    Number(row.id)
                )
        );


    // AUTO_BATCH_CUT_SIZE_REQUIRED_V1
    const missingCutSize =
        selectedRows.filter(
            row =>
                !String(
                    row.cut_size || ""
                ).trim()
        );


    if(missingCutSize.length){

        showToast(
            "Cut Size is required for every selected row before Create Batch.",
            "error"
        );

        return;

    }


    // CUTTING_PLAN_LOCAL_MOVE_TO_FINAL_REMOVE_V2
    // Move To validation retired for Create Batch.


    const button = document.getElementById(
        "cp-auto-create-batch-btn"
    );


    if(button){

        button.disabled = true;
        button.textContent =
            "Creating Batch...";

    }


    try{

        const response = await fetch(
            "/api/cutting-plan/auto-batch",
            {
                method:"POST",

                headers:{
                    "Content-Type":
                    "application/json"
                },

                body:JSON.stringify({
                    plan_ids:planIds
                })
            }
        );


        const data =
            await response.json();


        if(!response.ok || !data.success){

            let message =
                data.error ||
                "Unable to create AUTO batch.";


            if(
                Array.isArray(
                    data.validation_errors
                )
                &&
                data.validation_errors.length
            ){

                message =
                    data.validation_errors.join(
                        " | "
                    );

            }


            throw new Error(message);

        }


        window.cpPendingAutoSelected.clear();


        showToast(
            `Batch ${data.plan_batch_no} created with ` +
            `${data.line_count} row(s).`,
            "success"
        );


        await loadPendingAutoRequirements();


        if(
            typeof loadCuttingPlans ===
            "function"
        ){

            await loadCuttingPlans();

        }


    }
    catch(error){

        console.error(error);


        showToast(
            error.message ||
            "Unable to create AUTO batch.",
            "error"
        );

    }
    finally{

        if(button){

            button.textContent =
                "Create Batch";

            updatePendingAutoSelectionUI();

        }

    }

}


document.addEventListener(
    "DOMContentLoaded",
    function(){

        loadPendingAutoRequirements();

    }
);

/* AUTO_PENDING_REQUIREMENTS_UI_V1_END */




/* ==========================================================
   CUTTING_PLAN_BATCH_VISIBLE_DATE_V1

   Formats only the visible Planned Date column in the
   Cutting Plan Batches table:

       YYYY-MM-DD -> DD-MM-YYYY

   No database/API value is changed.
   ========================================================== */

function cpFormatBatchVisibleDate(value){

    const raw = String(
        value || ""
    ).trim();

    const match = raw.match(
        /^(\d{4})-(\d{2})-(\d{2})$/
    );

    if(!match){
        return raw;
    }

    return (
        `${match[3]}-${match[2]}-${match[1]}`
    );

}


function cpRefreshBatchVisibleDates(){

    const tbody = document.getElementById(
        "cutting-plan-body"
    );

    if(!tbody){
        return;
    }


    const rows = tbody.querySelectorAll(
        "tr"
    );


    rows.forEach(row => {

        const cells = row.querySelectorAll(
            "td"
        );


        /*
          Batch table column order:

          1 Source
          2 Job Card
          3 Records
          4 Materials
          5 Total Qty
          6 Planned Date
          7 Action
        */

        if(cells.length < 6){
            return;
        }


        const dateCell = cells[5];

        const current = String(
            dateCell.textContent || ""
        ).trim();


        const formatted =
            cpFormatBatchVisibleDate(
                current
            );


        if(
            formatted &&
            formatted !== current
        ){

            dateCell.textContent =
                formatted;

        }

    });

}


document.addEventListener(
    "DOMContentLoaded",
    function(){

        const tbody = document.getElementById(
            "cutting-plan-body"
        );


        if(!tbody){
            return;
        }


        /*
          loadCuttingPlans() rebuilds tbody dynamically.
          Observe that tbody and format the date immediately
          whenever its rows are refreshed.
        */

        const observer =
            new MutationObserver(
                function(){

                    cpRefreshBatchVisibleDates();

                }
            );


        observer.observe(
            tbody,
            {
                childList:true,
                subtree:true
            }
        );


        cpRefreshBatchVisibleDates();

    }
);


/* CUTTING_PLAN_BATCH_VISIBLE_DATE_V1_END */



/* ==========================================================
   AUTO_PENDING_EDITABLE_OVERRIDE_V3
   Material + Cut Size + Qty editable
   ========================================================== */

function cpEnsurePendingAutoCutSizeColumn(){

    const tbody = document.getElementById("cp-auto-body");

    if(!tbody){
        return;
    }

    const table = tbody.closest("table");

    if(!table){
        return;
    }

    const headerRow = table.querySelector("thead tr");

    if(!headerRow){
        return;
    }

    const alreadyExists = Array.from(
        headerRow.querySelectorAll("th")
    ).some(function(th){
        return String(
            th.textContent || ""
        ).trim().toUpperCase() === "CUT SIZE";
    });

    if(alreadyExists){
        return;
    }

    const th = document.createElement("th");

    th.id = "cp-auto-cut-size-header";
    th.textContent = "Cut Size";

    const headers = headerRow.querySelectorAll("th");

    if(headers.length >= 5){
        headerRow.insertBefore(
            th,
            headers[4]
        );
    }
    else{
        headerRow.appendChild(th);
    }
}


async function savePendingAutoEditableField(
    planId,
    field,
    input
){

    planId = Number(planId);

    field = String(
        field || ""
    ).trim();


    if(
        ![
            "material_spec",
            "cut_size",
            "planned_qty"
        ].includes(field)
    ){
        showToast(
            "Invalid Cutting Plan field.",
            "error"
        );
        return;
    }


    const row = window.cpPendingAutoRows.find(
        item => Number(item.id) === planId
    );

    if(!row){
        return;
    }


    let value;


    if(field === "planned_qty"){

        value = Number(
            String(
                input?.value || ""
            ).trim()
        );

        if(
            !Number.isInteger(value)
            ||
            value <= 0
        ){
            showToast(
                "Quantity must be a whole number greater than zero.",
                "error"
            );

            input.value = Number(
                row.planned_qty || 0
            );

            return;
        }
    }
    else{

        value = String(
            input?.value || ""
        ).trim();

    }


    input.disabled = true;


    try{

        const response = await fetch(
            `/api/cutting-plan/${planId}`,
            {
                method: "PATCH",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    [field]: value
                })
            }
        );


        const data = await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){
            throw new Error(
                data.error ||
                "Unable to update Cutting Plan."
            );
        }


        if(data.plan){

            row.material_spec =
                data.plan.material_spec;

            row.cut_size =
                data.plan.cut_size;

            row.planned_qty =
                data.plan.planned_qty;

        }
        else{

            row[field] = value;

        }


        renderPendingAutoRequirements();


        if(field === "material_spec"){

            showToast(
                "Material updated.",
                "success"
            );

        }
        else if(field === "cut_size"){

            showToast(
                "Cut Size updated.",
                "success"
            );

        }
        else{

            showToast(
                "Quantity updated.",
                "success"
            );

        }

    }
    catch(error){

        console.error(
            "Pending AUTO edit error",
            error
        );

        showToast(
            error.message ||
            "Unable to update Cutting Plan.",
            "error"
        );

        await loadPendingAutoRequirements();

    }

}


function renderPendingAutoRequirements(){

    const tbody =
        document.getElementById(
            "cp-auto-body"
        );

    if(!tbody){
        return;
    }


    cpEnsurePendingAutoCutSizeColumn();


    const rows =
        window.cpPendingAutoRows || [];


    const counter =
        document.getElementById(
            "cp-auto-count"
        );

    if(counter){
        counter.textContent = rows.length;
    }


    if(!rows.length){

        tbody.innerHTML = `
            <tr>
                <td
                    colspan="9"
                    class="cp-auto-empty"
                >
                    <div class="cp-auto-empty-title">
                        No pending AUTO requirements
                    </div>

                    <div>
                        New Job Cards will appear here after
                        Raw Material advances to Cutting.
                    </div>
                </td>
            </tr>
        `;

        window.cpPendingAutoSelected.clear();

        updatePendingAutoSelectionUI();

        return;
    }


    tbody.innerHTML = rows.map(function(plan){

        const checked =
            window.cpPendingAutoSelected.has(
                Number(plan.id)
            );


        const material =
            String(
                plan.material_spec || ""
            ).trim();


        const cutSize =
            String(
                plan.cut_size || ""
            ).trim();


        const qty =
            Number(
                plan.planned_qty || 0
            );


        const qtyValid =
            Number.isInteger(qty)
            &&
            qty > 0;


        return `

            <tr
                class="${checked ? "selected" : ""}"
                data-plan-id="${plan.id}"
            >


                <td class="cp-check-col">

                    <input
                        type="checkbox"
                        class="cp-auto-row-check"

                        ${checked ? "checked" : ""}

                        onchange="
                            togglePendingAutoRow(
                                ${plan.id},
                                this.checked
                            )
                        "
                    >

                </td>


                <td>

                    <div class="cp-auto-jc">

                        ${cpEscapeHtml(
                            plan.job_card_no || "-"
                        )}

                    </div>

                    <div class="cp-auto-source-id">

                        AUTO #${plan.id}

                    </div>

                </td>


                <td>

                    ${cpEscapeHtml(
                        cpFormatPlannedDate(
                            plan.planned_date,
                            "-"
                        )
                    )}

                </td>


                <!-- MATERIAL -->

                <td>

                    <input
                        type="text"

                        value="${cpEscapeHtml(material)}"

                        placeholder="Enter Material"

                        onchange="
                            savePendingAutoEditableField(
                                ${plan.id},
                                'material_spec',
                                this
                            )
                        "

                        style="
                            width:100%;
                            min-width:190px;
                            padding:7px 8px;
                            border:${
                                material
                                ? "1px solid #cfd6df"
                                : "1px solid #c62828"
                            };
                            border-radius:6px;
                            box-sizing:border-box;
                        "
                    >


                    ${!material ? `

                        <div
                            style="
                                margin-top:4px;
                                color:#c62828;
                                font-size:11px;
                                font-weight:700;
                                white-space:nowrap;
                            "
                        >
                            MATERIAL REQUIRED
                        </div>

                    ` : ""}

                </td>


                <!-- CUT SIZE -->

                <td>

                    <input
                        type="text"

                        value="${cpEscapeHtml(cutSize)}"

                        placeholder="Enter Cut Size"

                        onchange="
                            savePendingAutoEditableField(
                                ${plan.id},
                                'cut_size',
                                this
                            )
                        "

                        style="
                            width:100%;
                            min-width:110px;
                            padding:7px 8px;
                            border:${
                                cutSize
                                ? "1px solid #cfd6df"
                                : "1px solid #c62828"
                            };
                            border-radius:6px;
                            box-sizing:border-box;
                        "
                    >


                    ${!cutSize ? `

                        <div
                            style="
                                margin-top:4px;
                                color:#c62828;
                                font-size:11px;
                                font-weight:700;
                                white-space:nowrap;
                            "
                        >
                            CUT SIZE REQUIRED
                        </div>

                    ` : ""}

                </td>


                <!-- QTY -->

                <td>

                    <input
                        type="number"

                        min="1"
                        step="1"

                        value="${
                            qtyValid
                            ? qty
                            : ""
                        }"

                        placeholder="Qty"

                        onchange="
                            savePendingAutoEditableField(
                                ${plan.id},
                                'planned_qty',
                                this
                            )
                        "

                        style="
                            width:80px;
                            padding:7px 8px;
                            text-align:center;
                            font-weight:600;
                            border:${
                                qtyValid
                                ? "1px solid #cfd6df"
                                : "1px solid #c62828"
                            };
                            border-radius:6px;
                            box-sizing:border-box;
                        "
                    >


                    ${!qtyValid ? `

                        <div
                            style="
                                margin-top:4px;
                                color:#c62828;
                                font-size:11px;
                                font-weight:700;
                            "
                        >
                            QTY REQUIRED
                        </div>

                    ` : ""}

                </td>


                <td>

                    ${cpEscapeHtml(
                        plan.part || "-"
                    )}

                </td>


                <td class="cp-model-cell">

                    ${cpEscapeHtml(
                        plan.model_size ||
                        plan.item_name ||
                        "-"
                    )}

                </td>


                <td>

                    ${cpPendingMovePills(plan)}

                </td>


            </tr>

        `;

    }).join("");


    updatePendingAutoSelectionUI();

}


/* AUTO_PENDING_EDITABLE_OVERRIDE_V3_END */



/* ==========================================================
   AUTO_ADD_EXISTING_BATCH_UI_V1
   ========================================================== */


function cpInjectExistingBatchControls(){

    if(
        document.getElementById(
            "cp-auto-add-existing-btn"
        )
    ){
        return;
    }


    const createButton =
        document.getElementById(
            "cp-auto-create-batch-btn"
        );


    if(!createButton){
        return;
    }


    const holder =
        document.createElement("div");


    holder.id =
        "cp-auto-existing-batch-controls";


    holder.style.display = "inline-flex";
    holder.style.alignItems = "center";
    holder.style.gap = "8px";
    holder.style.marginLeft = "8px";


    holder.innerHTML = `

        <select
            id="cp-auto-existing-batch-select"
            class="cp-form-input"
            style="
                width:auto;
                min-width:170px;
                padding:8px 10px;
            "
            onchange="cpSyncExistingBatchButton()"
        >
            <option value="">
                Select Existing Batch
            </option>
        </select>


        <button
            type="button"
            id="cp-auto-add-existing-btn"
            class="cp-btn cp-secondary"
            onclick="addSelectedAutoToExistingBatch()"
            disabled
        >
            Add to Existing Batch
        </button>

    `;


    createButton.insertAdjacentElement(
        "afterend",
        holder
    );

}



function cpSyncExistingBatchButton(){

    const button =
        document.getElementById(
            "cp-auto-add-existing-btn"
        );


    const select =
        document.getElementById(
            "cp-auto-existing-batch-select"
        );


    if(!button){
        return;
    }


    const hasRows =
        window.cpPendingAutoSelected
        &&
        window.cpPendingAutoSelected.size > 0;


    const hasBatch =
        select
        &&
        Number(select.value) > 0;


    button.disabled =
        !hasRows || !hasBatch;

}



async function cpLoadExistingBatchChoices(){

    cpInjectExistingBatchControls();


    const select =
        document.getElementById(
            "cp-auto-existing-batch-select"
        );


    if(!select){
        return;
    }


    const oldValue =
        String(select.value || "");


    try{

        const response =
            await fetch(
                "/api/cutting-plan/plans?limit=500"
            );


        const data =
            await response.json();


        if(!response.ok || !data.success){

            throw new Error(
                data.error ||
                "Unable to load existing batches."
            );

        }


        const batchMap =
            new Map();


        (data.plans || []).forEach(function(plan){

            const rawBatch =
                plan.plan_batch_no;


            if(
                rawBatch === null
                ||
                rawBatch === undefined
                ||
                String(rawBatch).trim() === ""
            ){
                return;
            }


            const batchNo =
                Number(rawBatch);


            if(!Number.isInteger(batchNo)){
                return;
            }


            if(!batchMap.has(batchNo)){

                batchMap.set(
                    batchNo,
                    []
                );

            }


            batchMap
                .get(batchNo)
                .push(plan);

        });


        const eligible = [];


        batchMap.forEach(
            function(rows, batchNo){

                const blocked =
                    rows.some(function(row){

                        return [
                            "Completed",
                            "Cancelled"
                        ].includes(
                            String(
                                row.status || ""
                            ).trim()
                        );

                    });


                if(!blocked){

                    eligible.push({
                        batch_no: batchNo,
                        rows: rows
                    });

                }

            }
        );


        eligible.sort(
            function(a, b){

                return (
                    Number(a.batch_no)
                    -
                    Number(b.batch_no)
                );

            }
        );


        select.innerHTML = `
            <option value="">
                Select Existing Batch
            </option>
        `;


        eligible.forEach(function(batch){

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                String(batch.batch_no);


            option.textContent =
                `Batch ${batch.batch_no} (${batch.rows.length} row${batch.rows.length === 1 ? "" : "s"})`;


            select.appendChild(
                option
            );

        });


        if(
            oldValue
            &&
            Array.from(
                select.options
            ).some(
                option =>
                    option.value ===
                    oldValue
            )
        ){

            select.value =
                oldValue;

        }


        cpSyncExistingBatchButton();

    }
    catch(error){

        console.error(
            "Existing batch list error",
            error
        );


        showToast(
            error.message ||
            "Unable to load existing batches.",
            "error"
        );

    }

}



async function addSelectedAutoToExistingBatch(){

    const planIds =
        Array.from(
            window.cpPendingAutoSelected || []
        );


    if(!planIds.length){

        showToast(
            "Select at least one AUTO requirement.",
            "error"
        );

        return;

    }


    const select =
        document.getElementById(
            "cp-auto-existing-batch-select"
        );


    const batchNo =
        Number(
            select?.value || 0
        );


    if(
        !Number.isInteger(batchNo)
        ||
        batchNo <= 0
    ){

        showToast(
            "Please select an existing batch.",
            "error"
        );

        return;

    }


    const selectedRows =
        (window.cpPendingAutoRows || [])
        .filter(function(row){

            return planIds.includes(
                Number(row.id)
            );

        });


    const missingCutSize =
        selectedRows.filter(function(row){

            return !String(
                row.cut_size || ""
            ).trim();

        });


    if(missingCutSize.length){

        showToast(
            "Cut Size is required for every selected row.",
            "error"
        );

        return;

    }


    const invalidQty =
        selectedRows.filter(function(row){

            return (
                !Number.isInteger(
                    Number(row.planned_qty)
                )
                ||
                Number(row.planned_qty) <= 0
            );

        });


    if(invalidQty.length){

        showToast(
            "Quantity must be greater than zero for every selected row.",
            "error"
        );

        return;

    }


    // CUTTING_PLAN_LOCAL_MOVE_TO_FINAL_REMOVE_V2
    // Move To validation retired for Add Existing Batch.


    const button =
        document.getElementById(
            "cp-auto-add-existing-btn"
        );


    if(button){

        button.disabled = true;

        button.textContent =
            "Adding...";

    }


    try{

        const response =
            await fetch(
                "/api/cutting-plan/auto-batch/add-existing",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            plan_ids:
                                planIds,

                            plan_batch_no:
                                batchNo
                        })
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            let message =
                data.error ||
                "Unable to add to existing batch.";


            if(
                Array.isArray(
                    data.validation_errors
                )
                &&
                data.validation_errors.length
            ){

                message =
                    data.validation_errors.join(
                        " | "
                    );

            }


            throw new Error(message);

        }


        window.cpPendingAutoSelected.clear();


        showToast(
            data.message ||
            `Added to Batch ${batchNo}.`,
            "success"
        );


        await loadPendingAutoRequirements();


        if(
            typeof loadCuttingPlans ===
            "function"
        ){

            await loadCuttingPlans();

        }


        await cpLoadExistingBatchChoices();

    }
    catch(error){

        console.error(
            "Add existing batch error",
            error
        );


        showToast(
            error.message ||
            "Unable to add to existing batch.",
            "error"
        );

    }
    finally{

        if(button){

            button.textContent =
                "Add to Existing Batch";

        }


        cpSyncExistingBatchButton();

    }

}



/*
 * Extend existing selection UI without replacing
 * the current Create Batch behaviour.
 */

if(
    typeof updatePendingAutoSelectionUI ===
    "function"
){

    const cpExistingBatchOriginalSelectionUpdate =
        updatePendingAutoSelectionUI;


    updatePendingAutoSelectionUI =
        function(){

            cpExistingBatchOriginalSelectionUpdate();

            cpSyncExistingBatchButton();

        };

}



document.addEventListener(
    "DOMContentLoaded",
    function(){

        cpInjectExistingBatchControls();

        cpLoadExistingBatchChoices();

    }
);


/* AUTO_ADD_EXISTING_BATCH_UI_V1_END */



/* ==========================================================
   CUTTING_PLAN_PARENT_SEARCH_UI_V1
   Parent Code -> Child Codes -> Job Cards
   ========================================================== */

window.cpParentSearchRows = [];
window.cpParentSearchSelected = new Set();


function cpInjectParentSearchUI(){

    if(
        document.getElementById(
            "cp-parent-search-panel"
        )
    ){
        return;
    }


    const pendingBody =
        document.getElementById(
            "cp-auto-body"
        );

    if(!pendingBody){
        return;
    }


    const pendingTable =
        pendingBody.closest("table");

    if(!pendingTable){
        return;
    }


    let anchor = pendingTable;

    /*
     * Prefer inserting before the whole Pending section/card
     * when possible.
     */
    const possibleCard =
        pendingTable.closest(
            ".cp-card, .card, .table-card, .cp-section"
        );

    if(possibleCard){
        anchor = possibleCard;
    }


    const panel =
        document.createElement("div");


    panel.id =
        "cp-parent-search-panel";


    panel.style.cssText = `
        margin-bottom:20px;
        background:#fff;
        border:1px solid #dfe5ec;
        border-radius:10px;
        padding:16px;
        box-sizing:border-box;
    `;


    panel.innerHTML = `

        <div
            style="
                display:flex;
                justify-content:space-between;
                align-items:center;
                gap:12px;
                flex-wrap:wrap;
                margin-bottom:12px;
            "
        >

            <div>

                <div
                    style="
                        font-size:16px;
                        font-weight:700;
                    "
                >
                    Search Job Cards by Parent Code
                </div>

                <div
                    style="
                        margin-top:3px;
                        font-size:12px;
                        color:#667085;
                    "
                >
                    Enter Parent Code to find associated Child Codes and Job Cards.
                </div>

            </div>


            <div
                style="
                    display:flex;
                    gap:8px;
                    align-items:center;
                    flex-wrap:wrap;
                "
            >

                <input
                    id="cp-parent-code-search"
                    type="text"
                    placeholder="Enter Parent Code"
                    autocomplete="off"
                    style="
                        width:230px;
                        padding:9px 11px;
                        border:1px solid #cfd6df;
                        border-radius:7px;
                        box-sizing:border-box;
                    "
                    onkeydown="
                        if(event.key === 'Enter'){
                            searchCuttingPlanByParentCode();
                        }
                    "
                >


                <button
                    type="button"
                    class="cp-btn cp-primary"
                    onclick="searchCuttingPlanByParentCode()"
                >
                    Search
                </button>


                <button
                    type="button"
                    class="cp-btn cp-secondary"
                    onclick="clearCuttingPlanParentSearch()"
                >
                    Clear
                </button>

            </div>

        </div>


        <div
            id="cp-parent-search-summary"
            style="
                display:none;
                margin-bottom:10px;
                padding:8px 10px;
                background:#f5f7fa;
                border-radius:6px;
                font-size:13px;
            "
        ></div>


        <div
            id="cp-parent-search-results"
            style="display:none;"
        >

            <div
                style="
                    overflow-x:auto;
                    border:1px solid #e4e7ec;
                    border-radius:8px;
                "
            >

                <table
                    style="
                        width:100%;
                        border-collapse:collapse;
                        min-width:950px;
                    "
                >

                    <thead>

                        <tr>

                            <th style="padding:9px;">
                                <input
                                    id="cp-parent-select-all"
                                    type="checkbox"
                                    onchange="
                                        toggleAllParentSearchRows(
                                            this.checked
                                        )
                                    "
                                >
                            </th>

                            <th style="padding:9px;">
                                Level
                            </th>

                            <th style="padding:9px;">
                                Child Code
                            </th>

                            <th style="padding:9px;">
                                Job Card No.
                            </th>

                            <th style="padding:9px;">
                                Material
                            </th>

                            <th style="padding:9px;">
                                Qty
                            </th>

                            <th style="padding:9px;">
                                Cut Size
                            </th>

                            <th style="padding:9px;">
                                Cutting Plan
                            </th>

                        </tr>

                    </thead>


                    <tbody id="cp-parent-search-body">

                        <tr>
                            <td
                                colspan="8"
                                style="
                                    text-align:center;
                                    padding:18px;
                                "
                            >
                                Search a Parent Code.
                            </td>
                        </tr>

                    </tbody>

                </table>

            </div>


            <div
                style="
                    margin-top:10px;
                    display:flex;
                    align-items:center;
                    gap:10px;
                "
            >

                <strong id="cp-parent-selected-count">
                    0 selected
                </strong>

            </div>

        </div>

    `;


    anchor.parentNode.insertBefore(
        panel,
        anchor
    );

}



function cpParentRowCanSelect(row){

    /*
     * Selectable:
     * 1. JC has no Cutting Plan yet.
     * 2. JC already has a Draft, unbatched Cutting Plan.
     *
     * Already batched/released/completed rows stay visible
     * but cannot be selected again.
     */

    if(!row.already_in_cutting_plan){
        return true;
    }


    return (
        String(
            row.cutting_plan_status || ""
        ).trim() === "Draft"
        &&
        (
            row.plan_batch_no === null
            ||
            row.plan_batch_no === undefined
            ||
            String(
                row.plan_batch_no
            ).trim() === ""
        )
    );

}



function cpParentPlanStatus(row){

    if(!row.already_in_cutting_plan){

        return `
            <span
                style="
                    color:#475467;
                    font-weight:600;
                "
            >
                Not Created
            </span>
        `;

    }


    if(
        row.plan_batch_no !== null
        &&
        row.plan_batch_no !== undefined
        &&
        String(
            row.plan_batch_no
        ).trim() !== ""
    ){

        return `
            <span
                style="
                    color:#067647;
                    font-weight:700;
                "
            >
                Batch ${cpEscapeHtml(
                    row.plan_batch_no
                )}
            </span>
        `;

    }


    return `
        <span
            style="
                color:#175cd3;
                font-weight:700;
            "
        >
            ${cpEscapeHtml(
                row.cutting_plan_status || "Draft"
            )}
        </span>
    `;

}



function renderCuttingPlanParentSearch(){

    const tbody =
        document.getElementById(
            "cp-parent-search-body"
        );


    if(!tbody){
        return;
    }


    const rows =
        window.cpParentSearchRows || [];


    if(!rows.length){

        tbody.innerHTML = `

            <tr>

                <td
                    colspan="8"
                    style="
                        text-align:center;
                        padding:20px;
                        color:#667085;
                    "
                >
                    No related Job Cards found.
                </td>

            </tr>

        `;


        updateParentSearchSelectionUI();

        return;

    }


    tbody.innerHTML =
        rows.map(function(row, index){

            const selectable =
                cpParentRowCanSelect(row);


            const checked =
                window.cpParentSearchSelected.has(
                    index
                );


            const qty =
                row.so_qty ??
                row.actual_qty ??
                "";


            return `

                <tr
                    style="
                        ${selectable
                            ? ""
                            : "opacity:0.65;background:#f8f9fb;"
                        }
                    "
                >

                    <td
                        style="
                            text-align:center;
                            padding:9px;
                        "
                    >

                        <input
                            type="checkbox"

                            ${checked ? "checked" : ""}

                            ${selectable ? "" : "disabled"}

                            onchange="
                                toggleParentSearchRow(
                                    ${index},
                                    this.checked
                                )
                            "
                        >

                    </td>


                    <td style="padding:9px;">
                        L${cpEscapeHtml(
                            row.level || ""
                        )}
                    </td>


                    <td style="padding:9px;">

                        <strong>
                            ${cpEscapeHtml(
                                row.child_code || "-"
                            )}
                        </strong>

                    </td>


                    <td style="padding:9px;">

                        <strong>
                            ${cpEscapeHtml(
                                row.job_card_no || "-"
                            )}
                        </strong>

                    </td>


                    <td style="padding:9px;">

                        ${cpEscapeHtml(
                            row.material || "-"
                        )}

                    </td>


                    <td style="padding:9px;">

                        ${cpEscapeHtml(
                            qty
                        )}

                    </td>


                    <td style="padding:9px;">

                        ${
                            row.cut_size
                                ? cpEscapeHtml(
                                    row.cut_size
                                )
                                : `
                                    <span
                                        style="
                                            color:#b42318;
                                            font-weight:700;
                                        "
                                    >
                                        ${
                                            row.already_in_cutting_plan
                                                ? "CUT SIZE REQUIRED"
                                                : "-"
                                        }
                                    </span>
                                `
                        }

                    </td>


                    <td style="padding:9px;">

                        ${cpParentPlanStatus(row)}

                    </td>

                </tr>

            `;

        }).join("");


    updateParentSearchSelectionUI();

}



function toggleParentSearchRow(
    index,
    checked
){

    index = Number(index);


    const row =
        window.cpParentSearchRows[
            index
        ];


    if(!row){
        return;
    }


    if(!cpParentRowCanSelect(row)){
        return;
    }


    if(checked){

        window.cpParentSearchSelected.add(
            index
        );

    }
    else{

        window.cpParentSearchSelected.delete(
            index
        );

    }


    updateParentSearchSelectionUI();

}



function toggleAllParentSearchRows(
    checked
){

    window.cpParentSearchSelected.clear();


    if(checked){

        window.cpParentSearchRows
            .forEach(function(row, index){

                if(
                    cpParentRowCanSelect(row)
                ){

                    window.cpParentSearchSelected.add(
                        index
                    );

                }

            });

    }


    renderCuttingPlanParentSearch();

}



function updateParentSearchSelectionUI(){

    const count =
        document.getElementById(
            "cp-parent-selected-count"
        );


    if(count){

        count.textContent =
            `${window.cpParentSearchSelected.size} selected`;

    }


    const selectAll =
        document.getElementById(
            "cp-parent-select-all"
        );


    if(selectAll){

        const selectableIndexes =
            [];


        window.cpParentSearchRows
            .forEach(function(row, index){

                if(cpParentRowCanSelect(row)){
                    selectableIndexes.push(index);
                }

            });


        selectAll.checked =
            selectableIndexes.length > 0
            &&
            selectableIndexes.every(
                index =>
                    window.cpParentSearchSelected.has(
                        index
                    )
            );

    }

}



async function searchCuttingPlanByParentCode(){

    const input =
        document.getElementById(
            "cp-parent-code-search"
        );


    const parentCode =
        String(
            input?.value || ""
        )
        .trim()
        .toUpperCase();


    if(!parentCode){

        showToast(
            "Enter Parent Code.",
            "error"
        );

        return;

    }


    const summary =
        document.getElementById(
            "cp-parent-search-summary"
        );


    const results =
        document.getElementById(
            "cp-parent-search-results"
        );


    if(summary){

        summary.style.display =
            "block";

        summary.textContent =
            "Searching...";

    }


    if(results){

        results.style.display =
            "none";

    }


    window.cpParentSearchSelected.clear();


    try{

        const response =
            await fetch(
                "/api/cutting-plan/parent-search?parent_code="
                +
                encodeURIComponent(
                    parentCode
                )
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Parent Code search failed."
            );

        }


        window.cpParentSearchRows =
            data.records || [];


        if(summary){

            summary.innerHTML = `

                <strong>
                    ${cpEscapeHtml(
                        data.parent_code || parentCode
                    )}
                </strong>

                &nbsp; | &nbsp;

                Child Codes:
                <strong>
                    ${Number(
                        data.child_code_count || 0
                    )}
                </strong>

                &nbsp; | &nbsp;

                Job Cards:
                <strong>
                    ${Number(
                        data.job_card_count || 0
                    )}
                </strong>

            `;

        }


        if(results){

            results.style.display =
                "block";

        }


        renderCuttingPlanParentSearch();

    }
    catch(error){

        console.error(
            "Parent Code search error",
            error
        );


        window.cpParentSearchRows = [];


        if(summary){

            summary.textContent =
                error.message ||
                "Unable to search Parent Code.";

        }


        showToast(
            error.message ||
            "Unable to search Parent Code.",
            "error"
        );

    }

}



function clearCuttingPlanParentSearch(){

    const input =
        document.getElementById(
            "cp-parent-code-search"
        );


    if(input){
        input.value = "";
    }


    window.cpParentSearchRows = [];
    window.cpParentSearchSelected.clear();


    const summary =
        document.getElementById(
            "cp-parent-search-summary"
        );


    const results =
        document.getElementById(
            "cp-parent-search-results"
        );


    if(summary){

        summary.style.display =
            "none";

        summary.innerHTML = "";

    }


    if(results){

        results.style.display =
            "none";

    }

}



document.addEventListener(
    "DOMContentLoaded",
    function(){

        cpInjectParentSearchUI();

    }
);


/* CUTTING_PLAN_PARENT_SEARCH_UI_V1_END */



/* ==========================================================
   CUTTING_PLAN_UNIFIED_SEARCH_UI_V2

   PAGE WORKFLOW:

   1. Search Parent Code
   2. Child Codes + Job Cards
   3. Edit Material / Cut Size / Qty / Move To
   4. Select JCs
   5. Create New Batch OR Add to Existing Batch
   6. Ready to Print list

   Legacy Pending list is no longer displayed.
   ========================================================== */

window.cpSearchRows = [];
window.cpSearchSelected = new Set();


/*
 * Disable old Pending loaders/controls.
 * Existing backend logic remains untouched.
 */

loadPendingAutoRequirements =
    async function(){
        return;
    };


cpInjectExistingBatchControls =
    function(){
        return;
    };


cpLoadExistingBatchChoices =
    async function(){
        return;
    };



function cpUnifiedCommonAncestor(a, b){

    if(!a || !b){
        return null;
    }

    let node = a;

    while(node){

        if(node.contains(b)){
            return node;
        }

        node = node.parentElement;

    }

    return null;

}



function cpUnifiedHideOldPendingUI(){

    /*
     * Rename old Pending heading.
     */

    document.querySelectorAll(
        "h1,h2,h3,h4,h5"
    ).forEach(function(el){

        if(
            String(
                el.textContent || ""
            ).trim()
            ===
            "Pending Cutting Requirements"
        ){

            el.textContent =
                "Search & Prepare Cutting Plan";

        }


        if(
            String(
                el.textContent || ""
            ).trim()
            ===
            "Cutting Plan Batches"
        ){

            el.textContent =
                "Ready to Print Cutting Plans";

        }

    });


    document.querySelectorAll(
        "p,div,span"
    ).forEach(function(el){

        const text =
            String(
                el.textContent || ""
            ).trim();


        if(
            text ===
            "Job Cards received automatically when Raw Material advances to Cutting."
        ){

            el.textContent =
                "Search by Parent Code, select required Job Cards and prepare the Cutting Plan.";

        }

    });


    /*
     * Hide old Pending table.
     */

    const pendingBody =
        document.getElementById(
            "cp-auto-body"
        );


    const pendingTable =
        pendingBody
        ? pendingBody.closest("table")
        : null;


    if(pendingTable){

        pendingTable.style.display =
            "none";

    }


    /*
     * Hide old Select All / Create Batch toolbar.
     */

    const oldSelect =
        document.getElementById(
            "cp-auto-select-all"
        );


    const oldCreate =
        document.getElementById(
            "cp-auto-create-batch-btn"
        );


    const toolbar =
        cpUnifiedCommonAncestor(
            oldSelect,
            oldCreate
        );


    if(
        toolbar
        &&
        toolbar !== document.body
    ){

        toolbar.style.display =
            "none";

    }
    else{

        if(oldSelect){
            oldSelect.style.display =
                "none";
        }

        if(oldCreate){
            oldCreate.style.display =
                "none";
        }

    }


    const oldExisting =
        document.getElementById(
            "cp-auto-existing-batch-controls"
        );

    if(oldExisting){

        oldExisting.style.display =
            "none";

    }


    /*
     * Hide Pending badge.
     */

    const pendingCount =
        document.getElementById(
            "cp-auto-count"
        );

    if(pendingCount){

        const holder =
            pendingCount.parentElement;

        if(holder){

            holder.style.display =
                "none";

        }

    }


    /*
     * Hide summary statistics cards.
     * Page now focuses on:
     * Search + Ready to Print.
     */

    const statFirst =
        document.getElementById(
            "cp-total"
        );

    const statLast =
        document.getElementById(
            "cp-completed"
        );


    const statsHolder =
        cpUnifiedCommonAncestor(
            statFirst,
            statLast
        );


    if(
        statsHolder
        &&
        statsHolder !== document.body
        &&
        !statsHolder.contains(
            document.getElementById(
                "cutting-plan-body"
            )
        )
    ){

        statsHolder.style.display =
            "none";

    }

}



function cpInjectParentSearchUI(){

    if(
        document.getElementById(
            "cp-parent-search-panel"
        )
    ){

        return;

    }


    const pendingBody =
        document.getElementById(
            "cp-auto-body"
        );


    if(!pendingBody){
        return;
    }


    const pendingTable =
        pendingBody.closest(
            "table"
        );


    if(!pendingTable){
        return;
    }


    const panel =
        document.createElement(
            "div"
        );


    panel.id =
        "cp-parent-search-panel";


    panel.style.cssText = `
        background:#ffffff;
        border:1px solid #dfe5ec;
        border-radius:10px;
        padding:16px;
        margin:0 0 12px 0;
        box-sizing:border-box;
    `;


    panel.innerHTML = `

        <div
            style="
                display:flex;
                justify-content:space-between;
                gap:14px;
                align-items:center;
                flex-wrap:wrap;
                margin-bottom:14px;
            "
        >

            <div>

                <div
                    style="
                        font-size:17px;
                        font-weight:700;
                        color:#102a43;
                    "
                >
                    Search by Parent Code
                </div>

                <div
                    style="
                        font-size:12px;
                        color:#667085;
                        margin-top:3px;
                    "
                >
                    Find all associated Child Codes and Job Cards.
                </div>

            </div>


            <div
                style="
                    display:flex;
                    gap:8px;
                    flex-wrap:wrap;
                "
            >

                <input
                    id="cp-parent-code-search"
                    type="text"
                    placeholder="Enter Parent Code"
                    autocomplete="off"

                    style="
                        width:240px;
                        padding:9px 11px;
                        border:1px solid #cfd6df;
                        border-radius:7px;
                    "

                    onkeydown="
                        if(event.key === 'Enter'){
                            searchCuttingPlanByParentCode();
                        }
                    "
                >


                <button
                    type="button"
                    class="cp-btn cp-primary"
                    onclick="searchCuttingPlanByParentCode()"
                >
                    Search
                </button>


                <button
                    type="button"
                    class="cp-btn cp-secondary"
                    onclick="clearCuttingPlanParentSearch()"
                >
                    Clear
                </button>

            </div>

        </div>


        <div
            id="cp-parent-search-summary"
            style="
                display:none;
                background:#f5f7fa;
                padding:9px 11px;
                border-radius:7px;
                margin-bottom:10px;
                font-size:13px;
            "
        ></div>


        <div
            id="cp-parent-search-results"
            style="display:none;"
        >

            <div
                style="
                    overflow-x:auto;
                    border:1px solid #e4e7ec;
                    border-radius:8px;
                "
            >

                <table
                    style="
                        width:100%;
                        min-width:1250px;
                        border-collapse:collapse;
                    "
                >

                    <thead>

                        <tr>

                            <th style="padding:9px;">
                                <input
                                    id="cp-parent-select-all"
                                    type="checkbox"
                                    onchange="
                                        cpSearchToggleAll(
                                            this.checked
                                        )
                                    "
                                >
                            </th>

                            <th style="padding:9px;">
                                Child Code
                            </th>

                            <th style="padding:9px;">
                                Job Card
                            </th>

                            <th style="padding:9px;">
                                Material
                            </th>

                            <th style="padding:9px;">
                                Cut Size
                            </th>

                            <th style="padding:9px;">
                                Qty
                            </th>

                            <th style="padding:9px;">
                                Part
                            </th>

                            <th style="padding:9px;">
                                Model & Size
                            </th>

                            <th style="padding:9px;">
                                Move To
                            </th>

                            <th style="padding:9px;">
                                Status
                            </th>

                        </tr>

                    </thead>


                    <tbody
                        id="cp-parent-search-body"
                    ></tbody>

                </table>

            </div>


            <div
                style="
                    display:flex;
                    justify-content:space-between;
                    align-items:center;
                    gap:12px;
                    flex-wrap:wrap;
                    margin-top:12px;
                "
            >

                <strong
                    id="cp-parent-selected-count"
                >
                    0 selected
                </strong>


                <div
                    style="
                        display:flex;
                        gap:8px;
                        align-items:center;
                        flex-wrap:wrap;
                    "
                >

                    <button
                        id="cp-search-create-batch"
                        type="button"
                        class="cp-btn cp-primary"
                        onclick="cpCreateSearchBatch()"
                        disabled
                    >
                        Create New Batch
                    </button>


                    <select
                        id="cp-search-existing-batch"
                        style="
                            min-width:180px;
                            padding:8px 10px;
                            border:1px solid #cfd6df;
                            border-radius:7px;
                        "
                        onchange="
                            cpSearchUpdateActions()
                        "
                    >
                        <option value="">
                            Select Existing Batch
                        </option>
                    </select>


                    <button
                        id="cp-search-add-existing"
                        type="button"
                        class="cp-btn cp-secondary"
                        onclick="
                            cpAddSearchToExistingBatch()
                        "
                        disabled
                    >
                        Add to Existing Batch
                    </button>

                </div>

            </div>

        </div>

    `;


    pendingTable.parentNode.insertBefore(
        panel,
        pendingTable
    );


    cpUnifiedHideOldPendingUI();

}



function cpSearchRowSelectable(row){

    return Boolean(
        row
        &&
        row.selectable
    );

}



function cpSearchStatus(row){

    if(
        row.plan_batch_no !== null
        &&
        row.plan_batch_no !== undefined
        &&
        String(
            row.plan_batch_no
        ).trim() !== ""
    ){

        return `
            <span
                style="
                    color:#067647;
                    font-weight:700;
                "
            >
                Batch ${cpEscapeHtml(
                    row.plan_batch_no
                )}
            </span>
        `;

    }


    if(!row.has_cutting_process){

        return `
            <span
                style="
                    color:#b42318;
                    font-weight:700;
                "
                title="${cpEscapeHtml(
                    row.cutting_process_error || ""
                )}"
            >
                No Cutting Process
            </span>
        `;

    }


    if(row.cutting_plan_id){

        return `
            <span
                style="
                    color:#175cd3;
                    font-weight:700;
                "
            >
                Draft
            </span>
        `;

    }


    return `
        <span
            style="
                color:#475467;
                font-weight:600;
            "
        >
            Ready
        </span>
    `;

}



function cpSearchMovePills(
    row,
    index
){

    const selected =
        String(
            row.move_to || ""
        ).toUpperCase();


    const disabled =
        !cpSearchRowSelectable(row);


    return `

        <div
            style="
                display:flex;
                gap:5px;
                white-space:nowrap;
            "
        >

            ${["F","SC","U1","U2"]
                .map(function(value){

                    const active =
                        selected === value;

                    return `

                        <button
                            type="button"

                            ${disabled
                                ? "disabled"
                                : ""
                            }

                            onclick="
                                cpSearchSetMove(
                                    ${index},
                                    '${value}'
                                )
                            "

                            style="
                                padding:6px 9px;
                                border-radius:7px;
                                border:1px solid ${
                                    active
                                    ? "#0b67a3"
                                    : "#ccd5df"
                                };
                                background:${
                                    active
                                    ? "#0b67a3"
                                    : "#ffffff"
                                };
                                color:${
                                    active
                                    ? "#ffffff"
                                    : "#344054"
                                };
                                font-weight:700;
                                cursor:${
                                    disabled
                                    ? "not-allowed"
                                    : "pointer"
                                };
                            "
                        >
                            ${value}
                        </button>

                    `;

                })
                .join("")
            }

        </div>

    `;

}



function renderCuttingPlanParentSearch(){

    const tbody =
        document.getElementById(
            "cp-parent-search-body"
        );


    if(!tbody){
        return;
    }


    const rows =
        window.cpSearchRows || [];


    if(!rows.length){

        tbody.innerHTML = `

            <tr>

                <td
                    colspan="10"
                    style="
                        text-align:center;
                        padding:22px;
                        color:#667085;
                    "
                >
                    No related Cutting Job Cards found.
                </td>

            </tr>

        `;


        cpSearchUpdateActions();

        return;

    }


    tbody.innerHTML =
        rows.map(
            function(row, index){

                const selectable =
                    cpSearchRowSelectable(
                        row
                    );


                const checked =
                    window.cpSearchSelected
                    .has(index);


                const material =
                    String(
                        row.material || ""
                    ).trim();


                const cutSize =
                    String(
                        row.cut_size || ""
                    ).trim();


                const qty =
                    Number(
                        row.planned_qty || 0
                    );


                const qtyValid =
                    Number.isInteger(qty)
                    &&
                    qty > 0;


                const disabled =
                    selectable
                    ? ""
                    : "disabled";


                return `

                    <tr
                        style="${
                            selectable
                            ? ""
                            : "opacity:0.62;background:#f8f9fb;"
                        }"
                    >


                        <td
                            style="
                                padding:9px;
                                text-align:center;
                            "
                        >

                            <input
                                type="checkbox"

                                ${checked
                                    ? "checked"
                                    : ""
                                }

                                ${disabled}

                                onchange="
                                    cpSearchToggleRow(
                                        ${index},
                                        this.checked
                                    )
                                "
                            >

                        </td>


                        <td style="padding:9px;">

                            <strong>
                                ${cpEscapeHtml(
                                    row.child_code || "-"
                                )}
                            </strong>

                        </td>


                        <td style="padding:9px;">

                            <strong>
                                ${cpEscapeHtml(
                                    row.job_card_no || "-"
                                )}
                            </strong>

                        </td>


                        <td style="padding:7px;">

                            <input
                                type="text"

                                value="${cpEscapeHtml(
                                    material
                                )}"

                                ${disabled}

                                placeholder="Enter Material"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'material_spec',
                                        this
                                    )
                                "

                                style="
                                    width:100%;
                                    min-width:185px;
                                    padding:7px 8px;
                                    border:${
                                        material
                                        ? "1px solid #cfd6df"
                                        : "1px solid #e53935"
                                    };
                                    border-radius:6px;
                                    box-sizing:border-box;
                                "
                            >

                            ${!material && selectable
                                ? `
                                    <div
                                        style="
                                            color:#c62828;
                                            font-size:10px;
                                            font-weight:700;
                                            margin-top:3px;
                                        "
                                    >
                                        MATERIAL REQUIRED
                                    </div>
                                `
                                : ""
                            }

                        </td>


                        <td style="padding:7px;">

                            <input
                                type="text"

                                value="${cpEscapeHtml(
                                    cutSize
                                )}"

                                ${disabled}

                                placeholder="Enter Cut Size"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'cut_size',
                                        this
                                    )
                                "

                                style="
                                    width:125px;
                                    padding:7px 8px;
                                    border:${
                                        cutSize
                                        ? "1px solid #cfd6df"
                                        : "1px solid #e53935"
                                    };
                                    border-radius:6px;
                                "
                            >

                            ${!cutSize && selectable
                                ? `
                                    <div
                                        style="
                                            color:#c62828;
                                            font-size:10px;
                                            font-weight:700;
                                            margin-top:3px;
                                            white-space:nowrap;
                                        "
                                    >
                                        CUT SIZE REQUIRED
                                    </div>
                                `
                                : ""
                            }

                        </td>


                        <td style="padding:7px;">

                            <input
                                type="number"

                                min="1"
                                step="1"

                                value="${
                                    qtyValid
                                    ? qty
                                    : ""
                                }"

                                ${disabled}

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'planned_qty',
                                        this
                                    )
                                "

                                style="
                                    width:75px;
                                    padding:7px 8px;
                                    text-align:center;
                                    border:${
                                        qtyValid
                                        ? "1px solid #cfd6df"
                                        : "1px solid #e53935"
                                    };
                                    border-radius:6px;
                                "
                            >

                        </td>


                        <td style="padding:9px;">

                            ${cpEscapeHtml(
                                row.part || "-"
                            )}

                        </td>


                        <td
                            style="
                                padding:9px;
                                min-width:180px;
                            "
                        >

                            ${cpEscapeHtml(
                                row.model_size ||
                                row.item_name ||
                                "-"
                            )}

                        </td>


                        <td style="padding:7px;">

                            ${cpSearchMovePills(
                                row,
                                index
                            )}

                        </td>


                        <td style="padding:9px;">

                            ${cpSearchStatus(row)}

                        </td>


                    </tr>

                `;

            }
        )
        .join("");


    cpSearchUpdateActions();

}



async function searchCuttingPlanByParentCode(){

    const input =
        document.getElementById(
            "cp-parent-code-search"
        );


    const parentCode =
        String(
            input?.value || ""
        )
        .trim()
        .toUpperCase();


    if(!parentCode){

        showToast(
            "Enter Parent Code.",
            "error"
        );

        return;

    }


    const summary =
        document.getElementById(
            "cp-parent-search-summary"
        );


    const results =
        document.getElementById(
            "cp-parent-search-results"
        );


    summary.style.display =
        "block";

    summary.textContent =
        "Searching...";


    results.style.display =
        "none";


    window.cpSearchSelected.clear();


    try{

        const response =
            await fetch(
                "/api/cutting-plan/parent-search?parent_code="
                +
                encodeURIComponent(
                    parentCode
                )
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Parent Code search failed."
            );

        }


        window.cpSearchRows =
            data.records || [];


        summary.innerHTML = `

            <strong>
                ${cpEscapeHtml(
                    data.parent_code ||
                    parentCode
                )}
            </strong>

            &nbsp; | &nbsp;

            Child Codes:
            <strong>
                ${Number(
                    data.child_code_count || 0
                )}
            </strong>

            &nbsp; | &nbsp;

            Job Cards:
            <strong>
                ${Number(
                    data.job_card_count || 0
                )}
            </strong>

        `;


        results.style.display =
            "block";


        renderCuttingPlanParentSearch();

        await cpSearchLoadBatchChoices();

    }
    catch(error){

        console.error(
            error
        );


        window.cpSearchRows = [];


        summary.textContent =
            error.message ||
            "Unable to search Parent Code.";


        showToast(
            error.message ||
            "Unable to search Parent Code.",
            "error"
        );

    }

}



function clearCuttingPlanParentSearch(){

    const input =
        document.getElementById(
            "cp-parent-code-search"
        );


    if(input){
        input.value = "";
    }


    window.cpSearchRows = [];
    window.cpSearchSelected.clear();


    const summary =
        document.getElementById(
            "cp-parent-search-summary"
        );


    const results =
        document.getElementById(
            "cp-parent-search-results"
        );


    if(summary){

        summary.style.display =
            "none";

        summary.innerHTML = "";

    }


    if(results){

        results.style.display =
            "none";

    }


    cpSearchUpdateActions();

}



async function cpSearchEnsurePlan(index){

    const row =
        window.cpSearchRows[
            index
        ];


    if(!row){

        throw new Error(
            "Search row not found."
        );

    }


    if(row.cutting_plan_id){

        return Number(
            row.cutting_plan_id
        );

    }


    const response =
        await fetch(
            "/api/cutting-plan/search-prepare",
            {
                method:"POST",

                headers:{
                    "Content-Type":
                        "application/json"
                },

                body:
                    JSON.stringify({

                        job_card_no:
                            row.job_card_no,

                        item_id:
                            row.source_item_id

                    })
            }
        );


    const data =
        await response.json();


    if(
        !response.ok
        ||
        !data.success
        ||
        !data.plan
    ){

        throw new Error(
            data.error ||
            "Unable to prepare Cutting Plan."
        );

    }


    row.cutting_plan_id =
        Number(
            data.plan.id
        );


    row.cutting_plan_status =
        data.plan.status;


    row.material =
        data.plan.material_spec
        ||
        row.material
        ||
        "";


    row.cut_size =
        data.plan.cut_size
        ||
        row.cut_size
        ||
        "";


    if(
        Number(
            data.plan.planned_qty
        ) > 0
    ){

        row.planned_qty =
            Number(
                data.plan.planned_qty
            );

    }


    row.move_to =
        data.plan.move_to
        ||
        row.move_to
        ||
        "";


    return row.cutting_plan_id;

}



async function cpSearchPatchRow(
    index,
    payload
){

    const row =
        window.cpSearchRows[
            index
        ];


    const planId =
        await cpSearchEnsurePlan(
            index
        );


    const response =
        await fetch(
            `/api/cutting-plan/${planId}`,
            {
                method:"PATCH",

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


    if(
        !response.ok
        ||
        !data.success
    ){

        throw new Error(
            data.error ||
            "Unable to update Cutting Plan."
        );

    }


    if(data.plan){

        row.material =
            data.plan.material_spec
            ??
            row.material;


        row.cut_size =
            data.plan.cut_size
            ??
            row.cut_size;


        if(
            Number(
                data.plan.planned_qty
            ) > 0
        ){

            row.planned_qty =
                Number(
                    data.plan.planned_qty
                );

        }


        row.move_to =
            data.plan.move_to
            ??
            row.move_to;

    }


    return row;

}



async function cpSearchSaveField(
    index,
    field,
    input
){

    const row =
        window.cpSearchRows[
            index
        ];


    if(!row){
        return;
    }


    let value;


    if(field === "planned_qty"){

        value =
            Number(
                input.value
            );


        if(
            !Number.isInteger(value)
            ||
            value <= 0
        ){

            showToast(
                "Quantity must be a whole number greater than zero.",
                "error"
            );

            renderCuttingPlanParentSearch();

            return;

        }

    }
    else{

        value =
            String(
                input.value || ""
            ).trim();

    }


    input.disabled = true;


    try{

        await cpSearchPatchRow(
            index,
            {
                [field]:
                    value
            }
        );


        if(field === "material_spec"){

            row.material =
                value;

        }
        else{

            row[field] =
                value;

        }


        showToast(
            "Cutting Plan updated.",
            "success"
        );

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }
    finally{

        renderCuttingPlanParentSearch();

    }

}



async function cpSearchSetMove(
    index,
    moveTo
){

    const row =
        window.cpSearchRows[
            index
        ];


    if(!row){
        return;
    }


    moveTo =
        String(
            moveTo || ""
        ).toUpperCase();


    try{

        await cpSearchPatchRow(
            index,
            {
                move_to:
                    moveTo
            }
        );


        row.move_to =
            moveTo;


        renderCuttingPlanParentSearch();

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }

}



async function cpSearchSyncRow(index){

    const row =
        window.cpSearchRows[
            index
        ];


    if(!row){
        return;
    }


    await cpSearchPatchRow(
        index,
        {
            material_spec:
                String(
                    row.material || ""
                ).trim(),

            cut_size:
                String(
                    row.cut_size || ""
                ).trim(),

            planned_qty:
                Number(
                    row.planned_qty || 0
                ),

            move_to:
                String(
                    row.move_to || ""
                ).trim()
        }
    );

}



async function cpSearchToggleRow(
    index,
    checked
){

    index =
        Number(index);


    const row =
        window.cpSearchRows[
            index
        ];


    if(
        !row
        ||
        !cpSearchRowSelectable(row)
    ){

        return;

    }


    if(!checked){

        window.cpSearchSelected.delete(
            index
        );

        cpSearchUpdateActions();

        return;

    }


    try{

        await cpSearchSyncRow(
            index
        );


        window.cpSearchSelected.add(
            index
        );

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }


    renderCuttingPlanParentSearch();

}



async function cpSearchToggleAll(
    checked
){

    window.cpSearchSelected.clear();


    if(!checked){

        renderCuttingPlanParentSearch();

        return;

    }


    for(
        let index = 0;
        index < window.cpSearchRows.length;
        index += 1
    ){

        const row =
            window.cpSearchRows[index];


        if(!cpSearchRowSelectable(row)){
            continue;
        }


        try{

            await cpSearchSyncRow(
                index
            );


            window.cpSearchSelected.add(
                index
            );

        }
        catch(error){

            showToast(
                `${row.job_card_no}: ${error.message}`,
                "error"
            );

        }

    }


    renderCuttingPlanParentSearch();

}



function cpSearchSelectedRows(){

    return Array.from(
        window.cpSearchSelected
    )
    .map(
        index =>
            window.cpSearchRows[
                index
            ]
    )
    .filter(Boolean);

}



function cpSearchUpdateActions(){

    const selectedCount =
        window.cpSearchSelected.size;


    const count =
        document.getElementById(
            "cp-parent-selected-count"
        );


    if(count){

        count.textContent =
            `${selectedCount} selected`;

    }


    const createButton =
        document.getElementById(
            "cp-search-create-batch"
        );


    if(createButton){

        createButton.disabled =
            selectedCount === 0;

    }


    const batchSelect =
        document.getElementById(
            "cp-search-existing-batch"
        );


    const addButton =
        document.getElementById(
            "cp-search-add-existing"
        );


    if(addButton){

        addButton.disabled =
            selectedCount === 0
            ||
            !Number(
                batchSelect?.value || 0
            );

    }


    const selectAll =
        document.getElementById(
            "cp-parent-select-all"
        );


    if(selectAll){

        const selectable =
            window.cpSearchRows
            .map(
                function(row,index){

                    return (
                        cpSearchRowSelectable(row)
                        ? index
                        : null
                    );

                }
            )
            .filter(
                index =>
                    index !== null
            );


        selectAll.checked =
            selectable.length > 0
            &&
            selectable.every(
                index =>
                    window.cpSearchSelected
                    .has(index)
            );


        selectAll.indeterminate =
            selectedCount > 0
            &&
            !selectAll.checked;

    }

}



function cpSearchValidate(){

    const rows =
        cpSearchSelectedRows();


    if(!rows.length){

        return (
            "Select at least one Job Card."
        );

    }


    for(const row of rows){

        const jc =
            row.job_card_no || "Job Card";


        if(
            !String(
                row.material || ""
            ).trim()
        ){

            return (
                `${jc}: Material is required.`
            );

        }


        if(
            !String(
                row.cut_size || ""
            ).trim()
        ){

            return (
                `${jc}: Cut Size is required.`
            );

        }


        const qty =
            Number(
                row.planned_qty || 0
            );


        if(
            !Number.isInteger(qty)
            ||
            qty <= 0
        ){

            return (
                `${jc}: Quantity must be greater than zero.`
            );

        }


        // CUTTING_PLAN_MOVE_TO_LOCAL_FRONTEND_REMOVED_V1
        // Move To is retired.

    }


    return "";

}



async function cpSearchPrepareSelected(){

    const indexes =
        Array.from(
            window.cpSearchSelected
        );


    const planIds = [];


    for(const index of indexes){

        await cpSearchSyncRow(
            index
        );


        const row =
            window.cpSearchRows[
                index
            ];


        planIds.push(
            Number(
                row.cutting_plan_id
            )
        );

    }


    return planIds;

}



async function cpCreateSearchBatch(){

    const error =
        cpSearchValidate();


    if(error){

        showToast(
            error,
            "error"
        );

        return;

    }


    const button =
        document.getElementById(
            "cp-search-create-batch"
        );


    button.disabled = true;
    button.textContent =
        "Creating...";


    try{

        const planIds =
            await cpSearchPrepareSelected();


        const response =
            await fetch(
                "/api/cutting-plan/auto-batch",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            plan_ids:
                                planIds
                        })
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                (
                    Array.isArray(
                        data.validation_errors
                    )
                    &&
                    data.validation_errors.length
                )
                ?
                data.validation_errors.join(
                    " | "
                )
                :
                (
                    data.error ||
                    "Unable to create batch."
                )
            );

        }


        showToast(
            `Batch ${data.plan_batch_no} created successfully.`,
            "success"
        );


        window.cpSearchSelected.clear();


        await searchCuttingPlanByParentCode();

        await loadCuttingPlans();

        await cpSearchLoadBatchChoices();

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }
    finally{

        button.textContent =
            "Create New Batch";

        cpSearchUpdateActions();

    }

}



async function cpSearchLoadBatchChoices(){

    const select =
        document.getElementById(
            "cp-search-existing-batch"
        );


    if(!select){
        return;
    }


    const oldValue =
        String(
            select.value || ""
        );


    try{

        const response =
            await fetch(
                "/api/cutting-plan/plans?limit=500"
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){
            return;
        }


        const map =
            new Map();


        (data.plans || [])
        .forEach(function(plan){

            const batch =
                plan.plan_batch_no;


            if(
                batch === null
                ||
                batch === undefined
                ||
                String(batch).trim() === ""
            ){
                return;
            }


            const number =
                Number(batch);


            if(!map.has(number)){

                map.set(
                    number,
                    []
                );

            }


            map.get(number)
                .push(plan);

        });


        select.innerHTML = `
            <option value="">
                Select Existing Batch
            </option>
        `;


        Array.from(
            map.entries()
        )
        .sort(
            (a,b) =>
                a[0] - b[0]
        )
        .forEach(
            function(entry){

                const batchNo =
                    entry[0];

                const rows =
                    entry[1];


                const blocked =
                    rows.some(
                        row =>
                            [
                                "Completed",
                                "Cancelled"
                            ]
                            .includes(
                                String(
                                    row.status || ""
                                ).trim()
                            )
                    );


                if(blocked){
                    return;
                }


                const option =
                    document.createElement(
                        "option"
                    );


                option.value =
                    batchNo;


                option.textContent =
                    `Batch ${batchNo} (${rows.length} JC${rows.length === 1 ? "" : "s"})`;


                select.appendChild(
                    option
                );

            }
        );


        if(
            oldValue
            &&
            Array.from(
                select.options
            )
            .some(
                option =>
                    option.value
                    === oldValue
            )
        ){

            select.value =
                oldValue;

        }


        cpSearchUpdateActions();

    }
    catch(error){

        console.error(
            error
        );

    }

}



async function cpAddSearchToExistingBatch(){

    const error =
        cpSearchValidate();


    if(error){

        showToast(
            error,
            "error"
        );

        return;

    }


    const select =
        document.getElementById(
            "cp-search-existing-batch"
        );


    const batchNo =
        Number(
            select?.value || 0
        );


    if(batchNo <= 0){

        showToast(
            "Select an existing batch.",
            "error"
        );

        return;

    }


    const button =
        document.getElementById(
            "cp-search-add-existing"
        );


    button.disabled = true;
    button.textContent =
        "Adding...";


    try{

        const planIds =
            await cpSearchPrepareSelected();


        const response =
            await fetch(
                "/api/cutting-plan/auto-batch/add-existing",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            plan_ids:
                                planIds,

                            plan_batch_no:
                                batchNo

                        })
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Unable to add to existing batch."
            );

        }


        showToast(
            data.message ||
            `Added to Batch ${batchNo}.`,
            "success"
        );


        window.cpSearchSelected.clear();


        await searchCuttingPlanByParentCode();

        await loadCuttingPlans();

        await cpSearchLoadBatchChoices();

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }
    finally{

        button.textContent =
            "Add to Existing Batch";

        cpSearchUpdateActions();

    }

}



/*
 * READY TO PRINT ONLY
 * Draft/unbatched requirements are no longer shown here.
 */

loadCuttingPlans =
    async function(){

        try{

            const response =
                await fetch(
                    "/api/cutting-plan/plans?limit=500"
                );


            const data =
                await response.json();


            const allPlans =
                data.plans || [];


            window.cuttingPlans =
                allPlans;


            const readyPlans =
                allPlans.filter(
                    function(plan){

                        return (
                            plan.plan_batch_no
                                !== null
                            &&
                            plan.plan_batch_no
                                !== undefined
                            &&
                            String(
                                plan.plan_batch_no
                            ).trim() !== ""
                            &&
                            String(
                                plan.status || ""
                            ).trim() !==
                                "Cancelled"
                        );

                    }
                );


            const batchMap =
                new Map();


            readyPlans.forEach(
                function(plan){

                    const batchNo =
                        Number(
                            plan.plan_batch_no
                        );


                    if(
                        !batchMap.has(
                            batchNo
                        )
                    ){

                        batchMap.set(
                            batchNo,
                            []
                        );

                    }


                    batchMap
                        .get(batchNo)
                        .push(plan);

                }
            );


            const tbody =
                document.getElementById(
                    "cutting-plan-body"
                );


            if(!tbody){
                return;
            }


            tbody.innerHTML = "";


            if(!batchMap.size){

                tbody.innerHTML = `

                    <tr>

                        <td
                            colspan="7"
                            style="
                                text-align:center;
                                padding:20px;
                            "
                        >
                            No Cutting Plans ready to print.
                        </td>

                    </tr>

                `;

                return;

            }


            Array.from(
                batchMap.entries()
            )
            .sort(
                (a,b) =>
                    a[0] - b[0]
            )
            .forEach(
                function(entry){

                    const batchNo =
                        entry[0];

                    const rows =
                        entry[1];


                    const first =
                        rows[0];


                    const jobCards =
                        Array.from(
                            new Set(
                                rows
                                .map(
                                    row =>
                                        String(
                                            row.job_card_no ||
                                            ""
                                        ).trim()
                                )
                                .filter(Boolean)
                            )
                        );


                    const materials =
                        Array.from(
                            new Set(
                                rows
                                .map(
                                    row =>
                                        String(
                                            row.material_spec ||
                                            ""
                                        ).trim()
                                )
                                .filter(Boolean)
                            )
                        );


                    const materialDisplay =
                        materials.length <= 3
                        ?
                        materials.join(", ")
                        :
                        (
                            materials
                            .slice(0,3)
                            .join(", ")
                            +
                            ` +${materials.length - 3}`
                        );


                    const totalQty =
                        rows.reduce(
                            (
                                total,
                                row
                            ) =>
                                total
                                +
                                Number(
                                    row.planned_qty ||
                                    0
                                ),
                            0
                        );


                    const dates =
                        Array.from(
                            new Set(
                                rows
                                .map(
                                    row =>
                                        String(
                                            row.planned_date ||
                                            ""
                                        ).trim()
                                )
                                .filter(Boolean)
                            )
                        );


                    const dateDisplay =
                        dates.length === 1
                        ?
                        cpFormatPlannedDate(
                            dates[0],
                            "-"
                        )
                        :
                        "Multiple";


                    tbody.innerHTML += `

                        <tr>

                            <td>
                                ${cpEscapeHtml(
                                    first.source_type ||
                                    "AUTO"
                                )}
                            </td>


                            <td>
                                ${
                                    jobCards.length === 1
                                    ?
                                    cpEscapeHtml(
                                        jobCards[0]
                                    )
                                    :
                                    `${jobCards.length} JCs`
                                }
                            </td>


                            <td>
                                <strong>
                                    ${rows.length}
                                </strong>
                            </td>


                            <td>
                                ${cpEscapeHtml(
                                    materialDisplay ||
                                    "-"
                                )}
                            </td>


                            <td>
                                <strong>
                                    ${totalQty}
                                </strong>
                            </td>


                            <td>
                                ${cpEscapeHtml(
                                    dateDisplay
                                )}
                            </td>


                            <td>

                                <button
                                    class="cp-btn cp-primary"
                                    onclick="
                                        window.location.href=
                                        '/cutting-plan/${first.id}/print'
                                    "
                                >
                                    Print
                                </button>

                            </td>

                        </tr>

                    `;

                }
            );

        }
        catch(error){

            console.error(
                "Ready to Print error",
                error
            );

        }

    };



function cpUnifiedInit(){

    cpUnifiedHideOldPendingUI();

    cpInjectParentSearchUI();

    cpUnifiedHideOldPendingUI();

    cpSearchLoadBatchChoices();

    loadCuttingPlans();

}



if(
    document.readyState ===
    "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        cpUnifiedInit
    );

}
else{

    setTimeout(
        cpUnifiedInit,
        0
    );

}


/* CUTTING_PLAN_UNIFIED_SEARCH_UI_V2_END */



/* ==========================================================
   CUTTING_PLAN_UI_POLISH_V3
   Earlier Pending UI style + Parent Code workflow
   ========================================================== */


function cpInjectUnifiedSearchStyle(){

    if(
        document.getElementById(
            "cp-unified-search-style-v3"
        )
    ){
        return;
    }

    const style =
        document.createElement("style");

    style.id =
        "cp-unified-search-style-v3";

    style.textContent = `

        #cp-parent-search-panel{
            margin:0 !important;
            padding:0 !important;
            border:0 !important;
            border-radius:0 !important;
            background:transparent !important;
        }

        .cp-search-v3-searchbar{
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:14px;
            flex-wrap:wrap;
            padding:16px 20px;
            border-top:1px solid #dce5ee;
            border-bottom:1px solid #dce5ee;
            background:#ffffff;
        }

        .cp-search-v3-search-controls{
            display:flex;
            align-items:center;
            gap:8px;
            flex-wrap:wrap;
        }

        #cp-parent-code-search{
            width:250px;
            height:40px;
            padding:8px 12px;
            border:1px solid #ccd6e0;
            border-radius:8px;
            outline:none;
            background:#ffffff;
            box-sizing:border-box;
        }

        #cp-parent-code-search:focus{
            border-color:#0b67a3;
            box-shadow:0 0 0 2px rgba(11,103,163,.10);
        }

        .cp-search-v3-summary{
            margin:12px 20px 0 20px;
            padding:9px 12px;
            background:#f4f7fa;
            border-radius:7px;
            font-size:13px;
            color:#344054;
        }

        .cp-search-v3-toolbar{
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
            flex-wrap:wrap;
            padding:14px 20px;
            border-bottom:1px solid #dce5ee;
            background:#ffffff;
        }

        .cp-search-v3-select{
            display:flex;
            align-items:center;
            gap:10px;
            font-size:14px;
            color:#344054;
        }

        .cp-search-v3-actions{
            display:flex;
            align-items:center;
            gap:10px;
            flex-wrap:wrap;
        }

        .cp-search-v3-table-wrap{
            overflow-x:auto;
            background:#ffffff;
        }

        .cp-search-v3-table{
            width:100%;
            min-width:1420px;
            border-collapse:collapse;
        }

        .cp-search-v3-table thead th{
            padding:12px 14px;
            background:#f0f5f9;
            border-bottom:1px solid #d7e0e8;
            text-align:left;
            font-size:12px;
            font-weight:700;
            color:#344054;
            text-transform:uppercase;
            letter-spacing:.02em;
            white-space:nowrap;
        }

        .cp-search-v3-table tbody td{
            padding:12px 14px;
            border-bottom:1px solid #e8edf2;
            vertical-align:middle;
            font-size:13px;
            color:#17324d;
        }

        .cp-search-v3-table tbody tr:last-child td{
            border-bottom:0;
        }

        .cp-search-v3-table tbody tr:hover{
            background:#fbfdff;
        }

        .cp-search-v3-jc{
            font-weight:700;
            color:#003b70;
            white-space:nowrap;
        }

        .cp-search-v3-child{
            font-weight:600;
            white-space:nowrap;
        }

        .cp-search-v3-input{
            width:100%;
            padding:7px 9px;
            border:1px solid #cfd8e2;
            border-radius:7px;
            background:#ffffff;
            box-sizing:border-box;
            font:inherit;
        }

        .cp-search-v3-input.required{
            border-color:#ef5350;
        }

        .cp-search-v3-warning{
            margin-top:3px;
            color:#c62828;
            font-size:10px;
            line-height:1.1;
            font-weight:700;
            white-space:nowrap;
        }

        #cp-search-existing-batch{
            height:40px;
            min-width:190px;
        }

    `;

    document.head.appendChild(style);

}



function cpPolishSearchSectionHeader(){

    document.querySelectorAll(
        "p,div,span"
    ).forEach(function(el){

        if(
            String(
                el.textContent || ""
            ).trim()
            ===
            "Job Cards received automatically when Raw Material advances to Cutting."
        ){
            el.textContent =
                "Search by Parent Code and prepare the required Job Cards for cutting.";
        }

    });

}



function cpInjectParentSearchUI(){

    cpInjectUnifiedSearchStyle();
    cpPolishSearchSectionHeader();


    if(
        document.getElementById(
            "cp-parent-search-panel"
        )
    ){
        return;
    }


    const pendingBody =
        document.getElementById(
            "cp-auto-body"
        );

    if(!pendingBody){
        return;
    }


    const pendingTable =
        pendingBody.closest("table");

    if(!pendingTable){
        return;
    }


    const panel =
        document.createElement("div");

    panel.id =
        "cp-parent-search-panel";


    panel.innerHTML = `

        <div class="cp-search-v3-searchbar">

            <div>
                <div
                    style="
                        font-size:13px;
                        font-weight:700;
                        color:#0b5f96;
                        text-transform:uppercase;
                        letter-spacing:.04em;
                    "
                >
                    Search by Parent Code
                </div>

                <div
                    style="
                        margin-top:3px;
                        font-size:12px;
                        color:#667085;
                    "
                >
                    Find all associated Child Codes and Job Cards.
                </div>
            </div>


            <div class="cp-search-v3-search-controls">

                <input
                    id="cp-parent-code-search"
                    type="text"
                    placeholder="Enter Parent Code"
                    autocomplete="off"

                    onkeydown="
                        if(event.key === 'Enter'){
                            searchCuttingPlanByParentCode();
                        }
                    "
                >

                <button
                    type="button"
                    class="cp-btn cp-primary"
                    onclick="searchCuttingPlanByParentCode()"
                >
                    Search
                </button>

                <button
                    type="button"
                    class="cp-btn cp-secondary"
                    onclick="clearCuttingPlanParentSearch()"
                >
                    Clear
                </button>

            </div>

        </div>


        <div
            id="cp-parent-search-summary"
            class="cp-search-v3-summary"
            style="display:none;"
        ></div>


        <div
            id="cp-parent-search-results"
            style="display:none;"
        >

            <div class="cp-search-v3-toolbar">

                <div class="cp-search-v3-select">

                    <input
                        id="cp-parent-select-all"
                        type="checkbox"
                        onchange="
                            cpSearchToggleAll(
                                this.checked
                            )
                        "
                    >

                    <strong>
                        Select All
                    </strong>

                    <span
                        id="cp-parent-selected-count"
                        style="
                            color:#667085;
                            font-weight:400;
                        "
                    >
                        0 selected
                    </span>

                </div>


                <div class="cp-search-v3-actions">

                    <button
                        id="cp-search-create-batch"
                        type="button"
                        class="cp-btn cp-primary"
                        onclick="cpCreateSearchBatch()"
                        disabled
                    >
                        Create New Batch
                    </button>


                    <select
                        id="cp-search-existing-batch"
                        onchange="
                            cpSearchUpdateActions()
                        "
                    >
                        <option value="">
                            Select Existing Batch
                        </option>
                    </select>


                    <button
                        id="cp-search-add-existing"
                        type="button"
                        class="cp-btn cp-secondary"
                        onclick="
                            cpAddSearchToExistingBatch()
                        "
                        disabled
                    >
                        Add to Existing Batch
                    </button>

                </div>

            </div>


            <div class="cp-search-v3-table-wrap">

                <table class="cp-search-v3-table">

                    <thead>

                        <tr>
                            <th style="width:42px;"></th>
                            <th>Job Card</th>
                            <th>Child Code</th>
                            <th>Planned Date</th>
                            <th>Material</th>
                            <th>Cut Size</th>
                            <th>Qty</th>
                            <th>Part</th>
                            <th>Model & Size</th>
                            <th>Move To</th>
                        </tr>

                    </thead>


                    <tbody
                        id="cp-parent-search-body"
                    ></tbody>

                </table>

            </div>

        </div>

    `;


    pendingTable.parentNode.insertBefore(
        panel,
        pendingTable
    );


    cpUnifiedHideOldPendingUI();

}



function renderCuttingPlanParentSearch(){

    const tbody =
        document.getElementById(
            "cp-parent-search-body"
        );


    if(!tbody){
        return;
    }


    const rows =
        window.cpSearchRows || [];


    if(!rows.length){

        tbody.innerHTML = `

            <tr>

                <td
                    colspan="10"
                    style="
                        text-align:center;
                        padding:24px;
                        color:#667085;
                    "
                >
                    No related Cutting Job Cards found.
                </td>

            </tr>

        `;


        cpSearchUpdateActions();

        return;

    }


    tbody.innerHTML =
        rows.map(
            function(row,index){

                const selectable =
                    cpSearchRowSelectable(row);


                const checked =
                    window.cpSearchSelected
                    .has(index);


                const material =
                    String(
                        row.material || ""
                    ).trim();


                const cutSize =
                    String(
                        row.cut_size || ""
                    ).trim();


                const qty =
                    Number(
                        row.planned_qty || 0
                    );


                const qtyValid =
                    Number.isInteger(qty)
                    &&
                    qty > 0;


                const disabled =
                    selectable
                    ? ""
                    : "disabled";


                const plannedDate =
                    cpFormatPlannedDate(
                        row.job_card_date,
                        "-"
                    );


                return `

                    <tr
                        style="${
                            selectable
                            ? ""
                            : "opacity:.55;background:#f8fafc;"
                        }"
                    >


                        <td style="text-align:center;">

                            <input
                                type="checkbox"

                                ${checked
                                    ? "checked"
                                    : ""
                                }

                                ${disabled}

                                onchange="
                                    cpSearchToggleRow(
                                        ${index},
                                        this.checked
                                    )
                                "
                            >

                        </td>


                        <td>

                            <div class="cp-search-v3-jc">
                                ${cpEscapeHtml(
                                    row.job_card_no || "-"
                                )}
                            </div>

                        </td>


                        <td>

                            <div class="cp-search-v3-child">
                                ${cpEscapeHtml(
                                    row.child_code || "-"
                                )}
                            </div>

                        </td>


                        <td style="white-space:nowrap;">

                            ${cpEscapeHtml(
                                plannedDate
                            )}

                        </td>


                        <td>

                            <input
                                type="text"

                                class="cp-search-v3-input ${
                                    material
                                    ? ""
                                    : "required"
                                }"

                                style="
                                    min-width:190px;
                                "

                                value="${cpEscapeHtml(
                                    material
                                )}"

                                ${disabled}

                                placeholder="Enter Material"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'material_spec',
                                        this
                                    )
                                "
                            >


                            ${!material && selectable
                                ? `
                                    <div class="cp-search-v3-warning">
                                        MATERIAL REQUIRED
                                    </div>
                                `
                                : ""
                            }

                        </td>


                        <td>

                            <input
                                type="text"

                                class="cp-search-v3-input ${
                                    cutSize
                                    ? ""
                                    : "required"
                                }"

                                style="
                                    min-width:115px;
                                "

                                value="${cpEscapeHtml(
                                    cutSize
                                )}"

                                ${disabled}

                                placeholder="Enter Cut Size"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'cut_size',
                                        this
                                    )
                                "
                            >


                            ${!cutSize && selectable
                                ? `
                                    <div class="cp-search-v3-warning">
                                        CUT SIZE REQUIRED
                                    </div>
                                `
                                : ""
                            }

                        </td>


                        <td>

                            <input
                                type="number"

                                min="1"
                                step="1"

                                class="cp-search-v3-input ${
                                    qtyValid
                                    ? ""
                                    : "required"
                                }"

                                style="
                                    width:76px;
                                    text-align:center;
                                    font-weight:600;
                                "

                                value="${
                                    qtyValid
                                    ? qty
                                    : ""
                                }"

                                ${disabled}

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'planned_qty',
                                        this
                                    )
                                "
                            >

                        </td>


                        <td style="white-space:nowrap;">

                            ${cpEscapeHtml(
                                row.part || "-"
                            )}

                        </td>


                        <td style="min-width:190px;">

                            ${cpEscapeHtml(
                                row.model_size ||
                                row.item_name ||
                                "-"
                            )}

                        </td>


                        <td>

                            ${cpSearchMovePills(
                                row,
                                index
                            )}

                        </td>


                    </tr>

                `;

            }
        )
        .join("");


    cpSearchUpdateActions();

}


/*
 * No Draft / Ready / Status label is displayed.
 * Search results are purely working Cutting Plan rows.
 */



/* ==========================================================
   CUTTING_PLAN_FINAL_LAYOUT_V4

   FINAL PAGE:
   1. Search & Prepare Cutting Plan
   2. Ready to Print Cutting Plans

   Earlier Pending UI visual style.
   ========================================================== */


function cpFinalFindOldPendingCard(){

    const body =
        document.getElementById(
            "cp-auto-body"
        );


    if(!body){
        return null;
    }


    const headings =
        Array.from(
            document.querySelectorAll(
                "h1,h2,h3,h4,h5"
            )
        );


    const heading =
        headings.find(function(el){

            const value =
                String(
                    el.textContent || ""
                ).trim();


            return (
                value ===
                    "Pending Cutting Requirements"
                ||
                value ===
                    "Search & Prepare Cutting Plan"
            );

        });


    if(!heading){

        return body.closest(
            ".cutting-auto-card, .cp-card, section"
        );

    }


    let node =
        heading.parentElement;


    while(
        node
        &&
        node !== document.body
    ){

        if(node.contains(body)){
            return node;
        }

        node =
            node.parentElement;

    }


    return null;

}



function cpFinalInstallStyle(){

    if(
        document.getElementById(
            "cp-final-layout-style-v4"
        )
    ){
        return;
    }


    const style =
        document.createElement(
            "style"
        );


    style.id =
        "cp-final-layout-style-v4";


    style.textContent = `

        /* ==============================================
           SEARCH / PREPARE CARD
           ============================================== */

        #cp-search-workspace-v4{
            background:#ffffff;
            border:1px solid #d5e2ec;
            border-radius:14px;
            overflow:hidden;
            margin-bottom:24px;
            box-shadow:0 2px 8px rgba(16,42,67,.04);
        }


        .cp-v4-header{
            padding:20px 24px;
            background:#eef8ff;
            border-bottom:1px solid #d5e2ec;

            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:18px;
            flex-wrap:wrap;
        }


        .cp-v4-eyebrow{
            color:#0065a8;
            font-size:12px;
            line-height:1;
            font-weight:800;
            letter-spacing:.06em;
            text-transform:uppercase;
            margin-bottom:8px;
        }


        .cp-v4-title{
            margin:0;
            font-size:22px;
            line-height:1.2;
            font-weight:750;
            color:#0d3158;
        }


        .cp-v4-subtitle{
            margin-top:6px;
            color:#61758a;
            font-size:14px;
        }


        .cp-v4-search{
            display:flex;
            gap:9px;
            align-items:center;
            flex-wrap:wrap;
        }


        #cp-parent-code-search{
            width:260px;
            height:42px;
            padding:8px 12px;
            border:1px solid #bacadb;
            border-radius:8px;
            background:#ffffff;
            box-sizing:border-box;
            font-size:14px;
            outline:none;
        }


        #cp-parent-code-search:focus{
            border-color:#086ba5;
            box-shadow:0 0 0 2px rgba(8,107,165,.10);
        }


        #cp-parent-search-summary{
            padding-top:7px;
            font-size:12px;
            color:#53697d;
        }


        /* ==============================================
           ACTION BAR - SAME STYLE AS OLD PENDING UI
           ============================================== */

        .cp-v4-toolbar{
            min-height:66px;
            padding:12px 20px;

            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:14px;
            flex-wrap:wrap;

            background:#ffffff;
            border-bottom:1px solid #dce5ed;
        }


        .cp-v4-selection{
            display:flex;
            align-items:center;
            gap:10px;
            color:#183b5b;
            font-size:14px;
        }


        .cp-v4-selection strong{
            font-weight:700;
        }


        #cp-parent-selected-count{
            color:#65798c;
            font-weight:400;
        }


        .cp-v4-actions{
            display:flex;
            gap:10px;
            align-items:center;
            flex-wrap:wrap;
        }


        #cp-search-existing-batch{
            height:40px;
            min-width:190px;
            padding:7px 10px;
            border:1px solid #cbd6e1;
            border-radius:8px;
            background:#ffffff;
        }


        /* ==============================================
           TABLE - SAME VISUAL LANGUAGE AS OLD PENDING
           ============================================== */

        .cp-v4-table-wrap{
            overflow-x:auto;
            width:100%;
        }


        .cp-v4-table{
            width:100%;
            min-width:1450px;
            border-collapse:collapse;
            background:#ffffff;
        }


        .cp-v4-table thead{
            background:#f0f5f9;
        }


        .cp-v4-table th{
            padding:13px 14px;
            border-bottom:1px solid #d5e0e9;

            color:#3a5268;
            font-size:12px;
            font-weight:750;
            text-align:left;
            text-transform:uppercase;
            white-space:nowrap;
        }


        .cp-v4-table td{
            padding:12px 14px;
            border-bottom:1px solid #e6edf3;
            vertical-align:middle;

            color:#173b5c;
            font-size:13px;
        }


        .cp-v4-table tbody tr:last-child td{
            border-bottom:none;
        }


        .cp-v4-table tbody tr:hover{
            background:#fbfdff;
        }


        .cp-v4-jc{
            color:#003f76;
            font-weight:750;
            white-space:nowrap;
        }


        .cp-v4-child{
            color:#173b5c;
            font-weight:650;
            white-space:nowrap;
        }


        .cp-v4-input{
            padding:7px 9px;
            border:1px solid #ccd7e2;
            border-radius:7px;
            background:#ffffff;
            box-sizing:border-box;
            font:inherit;
        }


        .cp-v4-material{
            width:100%;
            min-width:205px;
        }


        .cp-v4-cut{
            width:125px;
        }


        .cp-v4-qty{
            width:76px;
            text-align:center;
            font-weight:650;
        }


        .cp-v4-required{
            border-color:#e64b4b !important;
        }


        .cp-v4-warning{
            color:#c62828;
            font-size:10px;
            font-weight:750;
            margin-top:3px;
            white-space:nowrap;
        }


        .cp-v4-batched-note{
            margin-top:3px;
            color:#66788a;
            font-size:10px;
            white-space:nowrap;
        }


        /* Hide old statistics completely */

        .cutting-summary{
            display:none !important;
        }

    `;


    document.head.appendChild(
        style
    );

}



function cpUnifiedHideOldPendingUI(){

    const oldCard =
        cpFinalFindOldPendingCard();


    const workspace =
        document.getElementById(
            "cp-search-workspace-v4"
        );


    if(
        oldCard
        &&
        workspace
        &&
        oldCard !== workspace
    ){

        oldCard.style.display =
            "none";

    }


    /*
     * Remove previous nested search card if any.
     */

    const oldSearch =
        document.getElementById(
            "cp-parent-search-panel"
        );


    if(oldSearch){

        oldSearch.remove();

    }


    /*
     * No summary cards.
     */

    const summary =
        document.querySelector(
            ".cutting-summary"
        );


    if(summary){

        summary.style.display =
            "none";

    }


    /*
     * Bottom section title.
     */

    Array.from(
        document.querySelectorAll(
            "h1,h2,h3,h4"
        )
    )
    .forEach(function(el){

        if(
            String(
                el.textContent || ""
            ).trim()
            ===
            "Cutting Plan Batches"
        ){

            el.textContent =
                "Ready to Print Cutting Plans";

        }

    });

}



function cpInjectParentSearchUI(){

    cpFinalInstallStyle();


    if(
        document.getElementById(
            "cp-search-workspace-v4"
        )
    ){

        cpUnifiedHideOldPendingUI();
        return;

    }


    const oldCard =
        cpFinalFindOldPendingCard();


    if(!oldCard){
        return;
    }


    const workspace =
        document.createElement(
            "section"
        );


    workspace.id =
        "cp-search-workspace-v4";


    workspace.innerHTML = `

        <!-- =========================================
             HEADER
             ========================================= -->

        <div class="cp-v4-header">

            <div>

                <div class="cp-v4-eyebrow">
                    Automatic Planning
                </div>


                <h2 class="cp-v4-title">
                    Search & Prepare Cutting Plan
                </h2>


                <div class="cp-v4-subtitle">
                    Search Parent Code and prepare the required Job Cards for cutting.
                </div>


                <div
                    id="cp-parent-search-summary"
                    style="display:none;"
                ></div>

            </div>


            <div class="cp-v4-search">

                <input
                    id="cp-parent-code-search"
                    type="text"
                    placeholder="Enter Parent Code"
                    autocomplete="off"

                    onkeydown="
                        if(event.key === 'Enter'){
                            searchCuttingPlanByParentCode();
                        }
                    "
                >


                <button
                    type="button"
                    class="cp-btn cp-primary"
                    onclick="
                        searchCuttingPlanByParentCode()
                    "
                >
                    Search
                </button>


                <button
                    type="button"
                    class="cp-btn cp-secondary"
                    onclick="
                        clearCuttingPlanParentSearch()
                    "
                >
                    Clear
                </button>

            </div>

        </div>


        <!-- =========================================
             RESULTS
             ========================================= -->

        <div
            id="cp-parent-search-results"
            style="display:none;"
        >


            <!-- OLD PENDING STYLE ACTION BAR -->

            <div class="cp-v4-toolbar">

                <div class="cp-v4-selection">

                    <input
                        id="cp-parent-select-all"
                        type="checkbox"

                        onchange="
                            cpSearchToggleAll(
                                this.checked
                            )
                        "
                    >


                    <strong>
                        Select All
                    </strong>


                    <span
                        id="cp-parent-selected-count"
                    >
                        0 selected
                    </span>

                </div>


                <div class="cp-v4-actions">

                    <button
                        id="cp-search-create-batch"
                        type="button"
                        class="cp-btn cp-primary"

                        onclick="
                            cpCreateSearchBatch()
                        "

                        disabled
                    >
                        Create Batch
                    </button>


                    <select
                        id="cp-search-existing-batch"

                        onchange="
                            cpSearchUpdateActions()
                        "
                    >
                        <option value="">
                            Select Existing Batch
                        </option>
                    </select>


                    <button
                        id="cp-search-add-existing"
                        type="button"
                        class="cp-btn cp-secondary"

                        onclick="
                            cpAddSearchToExistingBatch()
                        "

                        disabled
                    >
                        Add to Existing Batch
                    </button>

                </div>

            </div>


            <!-- TABLE -->

            <div class="cp-v4-table-wrap">

                <table class="cp-v4-table">

                    <thead>

                        <tr>

                            <th
                                style="
                                    width:42px;
                                    text-align:center;
                                "
                            ></th>

                            <th>
                                Job Card
                            </th>

                            <th>
                                Child Code
                            </th>

                            <th>
                                Planned Date
                            </th>

                            <th>
                                Material
                            </th>

                            <th>
                                Cut Size
                            </th>

                            <th>
                                Qty
                            </th>

                            <th>
                                Part
                            </th>

                            <th>
                                Model & Size
                            </th>

                            <th>
                                Move To
                            </th>

                        </tr>

                    </thead>


                    <tbody
                        id="cp-parent-search-body"
                    >
                    </tbody>

                </table>

            </div>

        </div>

    `;


    oldCard.parentNode.insertBefore(
        workspace,
        oldCard
    );


    cpUnifiedHideOldPendingUI();

}



function renderCuttingPlanParentSearch(){

    const tbody =
        document.getElementById(
            "cp-parent-search-body"
        );


    if(!tbody){
        return;
    }


    const rows =
        window.cpSearchRows || [];


    if(!rows.length){

        tbody.innerHTML = `

            <tr>

                <td
                    colspan="10"
                    style="
                        padding:24px;
                        text-align:center;
                        color:#6b7f91;
                    "
                >
                    No related Cutting Job Cards found.
                </td>

            </tr>

        `;


        cpSearchUpdateActions();

        return;

    }


    tbody.innerHTML =
        rows.map(
            function(row,index){

                const selectable =
                    cpSearchRowSelectable(
                        row
                    );


                const checked =
                    window.cpSearchSelected
                    .has(index);


                const material =
                    String(
                        row.material || ""
                    ).trim();


                const cutSize =
                    String(
                        row.cut_size || ""
                    ).trim();


                const qty =
                    Number(
                        row.planned_qty || 0
                    );


                const qtyValid =
                    Number.isInteger(qty)
                    &&
                    qty > 0;


                const disabled =
                    selectable
                    ? ""
                    : "disabled";


                const plannedDate =
                    cpFormatPlannedDate(
                        row.job_card_date,
                        "-"
                    );


                const batchNote =
                    (
                        row.plan_batch_no !== null
                        &&
                        row.plan_batch_no !== undefined
                        &&
                        String(
                            row.plan_batch_no
                        ).trim() !== ""
                    )
                    ?
                    `
                        <div class="cp-v4-batched-note">
                            Batch ${cpEscapeHtml(
                                row.plan_batch_no
                            )}
                        </div>
                    `
                    :
                    "";


                return `

                    <tr
                        ${
                            selectable
                            ? ""
                            :
                            'style="opacity:.55;background:#f7f9fb;"'
                        }
                    >


                        <!-- SELECT -->

                        <td
                            style="
                                text-align:center;
                            "
                        >

                            <input
                                type="checkbox"

                                ${
                                    checked
                                    ? "checked"
                                    : ""
                                }

                                ${disabled}

                                onchange="
                                    cpSearchToggleRow(
                                        ${index},
                                        this.checked
                                    )
                                "
                            >

                        </td>


                        <!-- JC -->

                        <td>

                            <div class="cp-v4-jc">

                                ${cpEscapeHtml(
                                    row.job_card_no || "-"
                                )}

                            </div>

                            ${batchNote}

                        </td>


                        <!-- CHILD CODE -->

                        <td>

                            <div class="cp-v4-child">

                                ${cpEscapeHtml(
                                    row.child_code || "-"
                                )}

                            </div>

                        </td>


                        <!-- DATE -->

                        <td
                            style="
                                white-space:nowrap;
                            "
                        >

                            ${cpEscapeHtml(
                                plannedDate
                            )}

                        </td>


                        <!-- MATERIAL -->

                        <td>

                            <input
                                type="text"

                                class="
                                    cp-v4-input
                                    cp-v4-material
                                    ${
                                        material
                                        ? ""
                                        : "cp-v4-required"
                                    }
                                "

                                value="${cpEscapeHtml(
                                    material
                                )}"

                                ${disabled}

                                placeholder="Enter Material"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'material_spec',
                                        this
                                    )
                                "
                            >


                            ${
                                !material
                                &&
                                selectable
                                ?
                                `
                                    <div class="cp-v4-warning">
                                        MATERIAL REQUIRED
                                    </div>
                                `
                                :
                                ""
                            }

                        </td>


                        <!-- CUT SIZE -->

                        <td>

                            <input
                                type="text"

                                class="
                                    cp-v4-input
                                    cp-v4-cut
                                    ${
                                        cutSize
                                        ? ""
                                        : "cp-v4-required"
                                    }
                                "

                                value="${cpEscapeHtml(
                                    cutSize
                                )}"

                                ${disabled}

                                placeholder="Enter Cut Size"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'cut_size',
                                        this
                                    )
                                "
                            >


                            ${
                                !cutSize
                                &&
                                selectable
                                ?
                                `
                                    <div class="cp-v4-warning">
                                        CUT SIZE REQUIRED
                                    </div>
                                `
                                :
                                ""
                            }

                        </td>


                        <!-- QTY -->

                        <td>

                            <input
                                type="number"

                                min="1"
                                step="1"

                                class="
                                    cp-v4-input
                                    cp-v4-qty
                                    ${
                                        qtyValid
                                        ? ""
                                        : "cp-v4-required"
                                    }
                                "

                                value="${
                                    qtyValid
                                    ? qty
                                    : ""
                                }"

                                ${disabled}

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'planned_qty',
                                        this
                                    )
                                "
                            >

                        </td>


                        <!-- PART -->

                        <td
                            style="
                                white-space:nowrap;
                            "
                        >

                            ${cpEscapeHtml(
                                row.part || "-"
                            )}

                        </td>


                        <!-- MODEL -->

                        <td
                            style="
                                min-width:190px;
                            "
                        >

                            ${cpEscapeHtml(
                                row.model_size
                                ||
                                row.item_name
                                ||
                                "-"
                            )}

                        </td>


                        <!-- MOVE TO -->

                        <td>

                            ${cpSearchMovePills(
                                row,
                                index
                            )}

                        </td>


                    </tr>

                `;

            }
        )
        .join("");


    cpSearchUpdateActions();

}



/*
 * Run final layout after every earlier UI initializer.
 */

function cpFinalLayoutInit(){

    cpFinalInstallStyle();

    cpInjectParentSearchUI();

    cpUnifiedHideOldPendingUI();

}



if(
    document.readyState ===
    "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        cpFinalLayoutInit
    );

}
else{

    setTimeout(
        cpFinalLayoutInit,
        0
    );

}



/* ==========================================================
   CUTTING_PLAN_BLANK_PAGE_RECOVERY_V1
   ========================================================== */

/*
 * Disable the dangerous hide routine introduced by
 * the temporary UI redesign patches.
 */
cpUnifiedHideOldPendingUI = function(){
    return;
};


function cpRestoreCuttingPlanVisibility(){

    /*
     * Remove temporary redesign styles that can hide
     * or restructure the original page.
     */
    [
        "cp-final-layout-style-v4",
        "cp-unified-search-style-v3"
    ].forEach(function(id){

        const el =
            document.getElementById(id);

        if(el){
            el.remove();
        }

    });


    /*
     * Restore visibility of the real Cutting Plan
     * containers and all their ancestors.
     */
    [
        "cp-auto-body",
        "cutting-plan-body",
        "cp-parent-search-panel",
        "cp-search-workspace-v4"
    ].forEach(function(id){

        let node =
            document.getElementById(id);

        while(
            node
            &&
            node !== document.body
        ){

            node.hidden = false;

            if(
                node.style
                &&
                node.style.display === "none"
            ){
                node.style.removeProperty(
                    "display"
                );
            }

            node =
                node.parentElement;
        }

    });


    /*
     * Restore original summary/card visibility too.
     */
    document
        .querySelectorAll(
            ".cutting-summary"
        )
        .forEach(function(el){

            el.style.removeProperty(
                "display"
            );

        });

}


if(
    document.readyState === "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        function(){

            setTimeout(
                cpRestoreCuttingPlanVisibility,
                50
            );

        }
    );

}
else{

    setTimeout(
        cpRestoreCuttingPlanVisibility,
        50
    );

}


/* CUTTING_PLAN_BLANK_PAGE_RECOVERY_V1_END */



/* ==========================================================
   CUTTING_PLAN_FINAL_UI_V5
   Search + Prepare | Ready to Print
   ========================================================== */


function cpV5FindOldPendingSection(){

    const tbody =
        document.getElementById("cp-auto-body");

    if(!tbody){
        return null;
    }


    let node = tbody.parentElement;
    let candidate = null;


    while(
        node
        &&
        node !== document.body
    ){

        const hasOldSelect =
            node.querySelector(
                "#cp-auto-select-all"
            );


        const hasOldCreate =
            node.querySelector(
                "#cp-auto-create-batch-btn"
            );


        const hasPrintTable =
            node.querySelector(
                "#cutting-plan-body"
            );


        if(
            hasOldSelect
            &&
            hasOldCreate
            &&
            !hasPrintTable
        ){
            candidate = node;
        }


        node = node.parentElement;

    }


    return candidate;

}



function cpV5MovePills(row,index){

    const selected =
        String(
            row.move_to || ""
        )
        .trim()
        .toUpperCase();


    const disabled =
        !cpSearchRowSelectable(row);


    return `

        <div class="cp-v5-move">

            ${["F","SC","U1","U2"]
                .map(function(value){

                    return `

                        <button
                            type="button"

                            class="
                                cp-v5-move-btn
                                ${
                                    selected === value
                                    ? "active"
                                    : ""
                                }
                            "

                            ${disabled ? "disabled" : ""}

                            onclick="
                                cpSearchSetMove(
                                    ${index},
                                    '${value}'
                                )
                            "
                        >
                            ${value}
                        </button>

                    `;

                })
                .join("")
            }

        </div>

    `;

}



function cpV5BuildSearchWorkspace(){

    /*
     * Make sure the functional search panel exists first.
     */

    let panel =
        document.getElementById(
            "cp-parent-search-panel"
        );


    if(
        !panel
        &&
        typeof cpInjectParentSearchUI ===
            "function"
    ){

        cpInjectParentSearchUI();

        panel =
            document.getElementById(
                "cp-parent-search-panel"
            );

    }


    if(!panel){
        return;
    }


    /*
     * Find OLD Pending section safely.
     * Move search panel OUTSIDE it before hiding it.
     */

    const oldPending =
        cpV5FindOldPendingSection();


    if(
        oldPending
        &&
        oldPending.contains(panel)
    ){

        oldPending.parentNode.insertBefore(
            panel,
            oldPending
        );

    }


    if(oldPending){

        oldPending.style.display =
            "none";

    }


    /*
     * Final permanent search card.
     */

    panel.className =
        "cp-v5-search-card";


    panel.removeAttribute("style");


    panel.innerHTML = `

        <!-- HEADER -->

        <div class="cp-v5-header">

            <div>

                <div class="cp-v5-eyebrow">
                    AUTOMATIC PLANNING
                </div>

                <h2>
                    Search & Prepare Cutting Plan
                </h2>

                <p>
                    Search Parent Code and prepare required
                    Job Cards for cutting.
                </p>

            </div>


            <div class="cp-v5-search-controls">

                <input
                    id="cp-parent-code-search"
                    type="text"
                    placeholder="Enter Parent Code"
                    autocomplete="off"

                    onkeydown="
                        if(event.key === 'Enter'){
                            searchCuttingPlanByParentCode();
                        }
                    "
                >


                <button
                    type="button"
                    class="cp-btn cp-primary"
                    onclick="
                        searchCuttingPlanByParentCode()
                    "
                >
                    Search
                </button>


                <button
                    type="button"
                    class="cp-btn cp-secondary"
                    onclick="
                        clearCuttingPlanParentSearch()
                    "
                >
                    Clear
                </button>

            </div>

        </div>


        <!-- SEARCH RESULT SUMMARY -->

        <div
            id="cp-parent-search-summary"
            class="cp-v5-summary"
            style="display:none;"
        ></div>


        <!-- RESULTS -->

        <div
            id="cp-parent-search-results"
            style="display:none;"
        >


            <!-- ACTION BAR -->

            <div class="cp-v5-toolbar">

                <div class="cp-v5-select-area">

                    <input
                        id="cp-parent-select-all"
                        type="checkbox"

                        onchange="
                            cpSearchToggleAll(
                                this.checked
                            )
                        "
                    >

                    <strong>
                        Select All
                    </strong>

                    <span
                        id="cp-parent-selected-count"
                    >
                        0 selected
                    </span>

                </div>


                <div class="cp-v5-actions">

                    <button
                        id="cp-search-create-batch"
                        type="button"
                        class="cp-btn cp-primary"
                        onclick="
                            cpCreateSearchBatch()
                        "
                        disabled
                    >
                        Create Batch
                    </button>


                    <select
                        id="cp-search-existing-batch"
                        onchange="
                            cpSearchUpdateActions()
                        "
                    >
                        <option value="">
                            Select Existing Batch
                        </option>
                    </select>


                    <button
                        id="cp-search-add-existing"
                        type="button"
                        class="cp-btn cp-secondary"
                        onclick="
                            cpAddSearchToExistingBatch()
                        "
                        disabled
                    >
                        Add to Existing Batch
                    </button>

                </div>

            </div>


            <!-- WORKING TABLE -->

            <div class="cp-v5-table-scroll">

                <table class="cp-v5-table">

                    <thead>

                        <tr>

                            <th class="cp-v5-check-col"></th>

                            <th>
                                Job Card
                            </th>

                            <th>
                                Child Code
                            </th>

                            <th>
                                Planned Date
                            </th>

                            <th>
                                Material
                            </th>

                            <th>
                                Cut Size
                            </th>

                            <th>
                                Qty
                            </th>

                            <th>
                                Part
                            </th>

                            <th>
                                Model & Size
                            </th>

                            <th>
                                Move To
                            </th>

                        </tr>

                    </thead>


                    <tbody
                        id="cp-parent-search-body"
                    ></tbody>

                </table>

            </div>

        </div>

    `;


    /*
     * Remove old summary cards.
     */

    const summaryCards =
        document.querySelector(
            ".cutting-summary"
        );

    if(summaryCards){

        summaryCards.style.display =
            "none";

    }


    /*
     * Ready-to-print card.
     */

    const printBody =
        document.getElementById(
            "cutting-plan-body"
        );


    const printCard =
        printBody
        ? printBody.closest(
            ".cutting-table-card"
        )
        : null;


    if(printCard){

        printCard.classList.add(
            "cp-v5-print-card"
        );


        const title =
            printCard.querySelector("h2");


        if(title){

            title.textContent =
                "Ready to Print Cutting Plans";

        }

    }

}



renderCuttingPlanParentSearch =
function(){

    const tbody =
        document.getElementById(
            "cp-parent-search-body"
        );


    if(!tbody){
        return;
    }


    const rows =
        window.cpSearchRows || [];


    if(!rows.length){

        tbody.innerHTML = `

            <tr>

                <td
                    colspan="10"
                    class="cp-v5-empty"
                >
                    No related Cutting Job Cards found.
                </td>

            </tr>

        `;


        cpSearchUpdateActions();

        return;

    }


    tbody.innerHTML =
        rows.map(
            function(row,index){

                const selectable =
                    cpSearchRowSelectable(row);


                const checked =
                    window.cpSearchSelected
                    .has(index);


                const material =
                    String(
                        row.material || ""
                    ).trim();


                const cutSize =
                    String(
                        row.cut_size || ""
                    ).trim();


                const qty =
                    Number(
                        row.planned_qty || 0
                    );


                const qtyValid =
                    Number.isInteger(qty)
                    &&
                    qty > 0;


                const disabled =
                    selectable
                    ? ""
                    : "disabled";


                const date =
                    cpFormatPlannedDate(
                        row.job_card_date,
                        "-"
                    );


                return `

                    <tr
                        class="${
                            selectable
                            ? ""
                            : "cp-v5-row-disabled"
                        }"
                    >


                        <!-- SELECT -->

                        <td class="cp-v5-check-col">

                            <input
                                type="checkbox"

                                ${checked
                                    ? "checked"
                                    : ""
                                }

                                ${disabled}

                                onchange="
                                    cpSearchToggleRow(
                                        ${index},
                                        this.checked
                                    )
                                "
                            >

                        </td>


                        <!-- JOB CARD -->

                        <td>

                            <div class="cp-v5-jc">

                                ${cpEscapeHtml(
                                    row.job_card_no || "-"
                                )}

                            </div>


                            ${
                                row.plan_batch_no
                                ?
                                `
                                    <div class="cp-v5-subtext">
                                        Batch ${cpEscapeHtml(
                                            row.plan_batch_no
                                        )}
                                    </div>
                                `
                                :
                                ""
                            }

                        </td>


                        <!-- CHILD CODE -->

                        <td>

                            <div class="cp-v5-child">

                                ${cpEscapeHtml(
                                    row.child_code || "-"
                                )}

                            </div>

                        </td>


                        <!-- DATE -->

                        <td class="cp-v5-nowrap">

                            ${cpEscapeHtml(date)}

                        </td>


                        <!-- MATERIAL -->

                        <td>

                            <input
                                type="text"

                                class="
                                    cp-v5-input
                                    cp-v5-material
                                    ${
                                        material
                                        ? ""
                                        : "required"
                                    }
                                "

                                value="${cpEscapeHtml(
                                    material
                                )}"

                                ${disabled}

                                placeholder="Enter Material"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'material_spec',
                                        this
                                    )
                                "
                            >


                            ${
                                !material
                                &&
                                selectable
                                ?
                                `
                                    <div class="cp-v5-warning">
                                        MATERIAL REQUIRED
                                    </div>
                                `
                                :
                                ""
                            }

                        </td>


                        <!-- CUT SIZE -->

                        <td>

                            <input
                                type="text"

                                class="
                                    cp-v5-input
                                    cp-v5-cut-size
                                    ${
                                        cutSize
                                        ? ""
                                        : "required"
                                    }
                                "

                                value="${cpEscapeHtml(
                                    cutSize
                                )}"

                                ${disabled}

                                placeholder="Enter Cut Size"

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'cut_size',
                                        this
                                    )
                                "
                            >


                            ${
                                !cutSize
                                &&
                                selectable
                                ?
                                `
                                    <div class="cp-v5-warning">
                                        CUT SIZE REQUIRED
                                    </div>
                                `
                                :
                                ""
                            }

                        </td>


                        <!-- QTY -->

                        <td>

                            <input
                                type="number"

                                min="1"
                                step="1"

                                class="
                                    cp-v5-input
                                    cp-v5-qty
                                    ${
                                        qtyValid
                                        ? ""
                                        : "required"
                                    }
                                "

                                value="${
                                    qtyValid
                                    ? qty
                                    : ""
                                }"

                                ${disabled}

                                onchange="
                                    cpSearchSaveField(
                                        ${index},
                                        'planned_qty',
                                        this
                                    )
                                "
                            >

                        </td>


                        <!-- PART -->

                        <td class="cp-v5-nowrap">

                            ${cpEscapeHtml(
                                row.part || "-"
                            )}

                        </td>


                        <!-- MODEL -->

                        <td class="cp-v5-model">

                            ${cpEscapeHtml(
                                row.model_size
                                ||
                                row.item_name
                                ||
                                "-"
                            )}

                        </td>


                        <!-- MOVE TO -->

                        <td>

                            ${cpV5MovePills(
                                row,
                                index
                            )}

                        </td>


                    </tr>

                `;

            }
        )
        .join("");


    cpSearchUpdateActions();

};



function cpV5Init(){

    cpV5BuildSearchWorkspace();

}



if(
    document.readyState ===
    "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        function(){

            setTimeout(
                cpV5Init,
                80
            );

        }
    );

}
else{

    setTimeout(
        cpV5Init,
        80
    );

}


/* CUTTING_PLAN_FINAL_UI_V5_END */



/* ==========================================================
   CUTTING_PLAN_UI_CLEANUP_V6
   1. Remove old Pending Cutting Requirements card
   2. Improve search-row selection UX
   ========================================================== */


function cpV6HideLegacyPendingCard(){

    const pendingBody =
        document.getElementById(
            "cp-auto-body"
        );

    if(!pendingBody){
        return;
    }


    let node =
        pendingBody.parentElement;


    while(
        node
        &&
        node !== document.body
    ){

        const headings =
            Array.from(
                node.querySelectorAll(
                    "h1,h2,h3,h4,h5"
                )
            );


        const hasPendingHeading =
            headings.some(function(el){

                return (
                    String(
                        el.textContent || ""
                    ).trim()
                    ===
                    "Pending Cutting Requirements"
                );

            });


        const containsSearch =
            Boolean(
                node.querySelector(
                    "#cp-parent-search-panel"
                )
            );


        const containsPrint =
            Boolean(
                node.querySelector(
                    "#cutting-plan-body"
                )
            );


        if(
            hasPendingHeading
            &&
            !containsSearch
            &&
            !containsPrint
        ){

            node.style.display =
                "none";

            node.setAttribute(
                "data-cp-v6-hidden",
                "1"
            );

            return;

        }


        node =
            node.parentElement;

    }


    /*
     * Safe fallback:
     * hide only legacy table itself,
     * never a broad page container.
     */

    const table =
        pendingBody.closest("table");

    if(table){
        table.style.display = "none";
    }

}



function cpV6RefreshSelectionLook(){

    const tbody =
        document.getElementById(
            "cp-parent-search-body"
        );

    if(!tbody){
        return;
    }


    tbody
        .querySelectorAll("tr")
        .forEach(function(row){

            const checkbox =
                row.querySelector(
                    'input[type="checkbox"]'
                );


            row.classList.toggle(
                "cp-v6-selected-row",
                Boolean(
                    checkbox
                    &&
                    checkbox.checked
                )
            );

        });

}



/*
 * Extend existing action refresh.
 */

if(
    typeof cpSearchUpdateActions ===
    "function"
){

    const cpV6OriginalUpdateActions =
        cpSearchUpdateActions;


    cpSearchUpdateActions =
        function(){

            cpV6OriginalUpdateActions();

            cpV6RefreshSelectionLook();

        };

}



/*
 * Legacy pending loader is no longer part
 * of the final Cutting Plan workflow.
 */

loadPendingAutoRequirements =
    async function(){
        return;
    };



function cpV6Init(){

    cpV6HideLegacyPendingCard();

    cpV6RefreshSelectionLook();

}


/*
 * Run more than once only during initial page build because
 * older code creates some UI dynamically.
 */

if(
    document.readyState ===
    "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        function(){

            cpV6Init();

            setTimeout(
                cpV6Init,
                250
            );

            setTimeout(
                cpV6Init,
                800
            );

        }
    );

}
else{

    cpV6Init();

    setTimeout(
        cpV6Init,
        250
    );

}


/* CUTTING_PLAN_UI_CLEANUP_V6_END */



/* ==========================================================
   CUTTING_PLAN_TODAY_UI_V1

   FINAL WORKFLOW:

   Raw Material
        ?
   Cutting Plan
        ?
   Cutting

   Shows today's incoming AUTO Cutting requirements only.
   No Parent Code search.
   ========================================================== */


window.cpTodayRows = [];
window.cpTodaySelected = new Set();



function cpTodayFindLegacyPendingCard(){

    const body =
        document.getElementById(
            "cp-auto-body"
        );

    if(!body){
        return null;
    }


    let node =
        body.parentElement;


    while(
        node
        &&
        node !== document.body
    ){

        const headings =
            Array.from(
                node.querySelectorAll(
                    "h1,h2,h3,h4,h5"
                )
            );


        const hasPending =
            headings.some(function(el){

                return (
                    String(
                        el.textContent || ""
                    ).trim()
                    ===
                    "Pending Cutting Requirements"
                );

            });


        const hasPrint =
            Boolean(
                node.querySelector(
                    "#cutting-plan-body"
                )
            );


        if(
            hasPending
            &&
            !hasPrint
        ){
            return node;
        }


        node =
            node.parentElement;

    }


    return null;

}



function cpTodayBuildWorkspace(){

    let panel =
        document.getElementById(
            "cp-parent-search-panel"
        );


    const legacy =
        cpTodayFindLegacyPendingCard();


    /*
     * Create working card if earlier search card
     * does not exist.
     */

    if(!panel){

        panel =
            document.createElement(
                "section"
            );

        panel.id =
            "cp-parent-search-panel";

        panel.className =
            "cp-v5-search-card";


        if(legacy){

            legacy.parentNode.insertBefore(
                panel,
                legacy
            );

        }
        else{

            const printBody =
                document.getElementById(
                    "cutting-plan-body"
                );


            const printCard =
                printBody
                ? printBody.closest(
                    ".cutting-table-card"
                )
                : null;


            if(
                printCard
                &&
                printCard.parentNode
            ){

                printCard.parentNode.insertBefore(
                    panel,
                    printCard
                );

            }

        }

    }


    /*
     * If panel is currently nested inside
     * legacy Pending card, move it outside first.
     */

    if(
        legacy
        &&
        legacy.contains(panel)
    ){

        legacy.parentNode.insertBefore(
            panel,
            legacy
        );

    }


    if(legacy){

        legacy.style.display =
            "none";

    }


    panel.className =
        "cp-v5-search-card";


    panel.removeAttribute(
        "style"
    );


    panel.innerHTML = `

        <!-- HEADER -->

        <div class="cp-v5-header">

            <div>

                <div class="cp-v5-eyebrow">
                    AUTOMATIC PLANNING
                </div>


                <h2>
                    Today's Cutting Requirements
                </h2>


                <p>
                    Job Cards received today from Raw Material
                    for Cutting Plan preparation.
                </p>

            </div>


            <div
                style="
                    display:flex;
                    align-items:center;
                    gap:10px;
                "
            >

                <span
                    id="cp-today-count"
                    style="
                        min-width:34px;
                        height:34px;
                        padding:0 12px;
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                        border:1px solid #bdd8ea;
                        border-radius:18px;
                        background:#ffffff;
                        color:#0f5d93;
                        font-size:13px;
                        font-weight:700;
                    "
                >
                    0
                </span>


                

            </div>

        </div>


        <!-- ACTION BAR -->

        <div
            id="cp-parent-search-results"
            style="display:block;"
        >

            <div class="cp-v5-toolbar">

                <div class="cp-v5-select-area">

                    <input
                        id="cp-today-select-all"
                        type="checkbox"

                        onchange="
                            cpTodayToggleAll(
                                this.checked
                            )
                        "
                    >


                    <strong>
                        Select All
                    </strong>


                    <span
                        id="cp-today-selected-count"
                    >
                        0 selected
                    </span>

                </div>


                <div class="cp-v5-actions">

                    <button
                        id="cp-today-create-batch"
                        type="button"
                        class="cp-btn cp-primary"

                        onclick="
                            cpTodayCreateBatch()
                        "

                        disabled
                    >
                        Create Batch
                    </button>


                    <select
                        id="cp-today-existing-batch"

                        onchange="
                            cpTodayUpdateActions()
                        "
                    >

                        <option value="">
                            Select Existing Batch
                        </option>

                    </select>


                    <button
                        id="cp-today-add-existing"
                        type="button"
                        class="cp-btn cp-secondary"

                        onclick="
                            cpTodayAddToExistingBatch()
                        "

                        disabled
                    >
                        Add to Existing Batch
                    </button>

                </div>

            </div>


            <!-- TABLE -->

            <div class="cp-v5-table-scroll">

                <table class="cp-v5-table">

                    <thead>

                        <tr>

                            <th class="cp-v5-check-col">
                            </th>

                            <th>
                                Job Card
                            </th>

                            <th>
                                Child Code
                            </th>

                            <th>
                                Planned Date
                            </th>

                            <th>
                                Material
                            </th>

                            <th>
                                Cut Size
                            </th>

                            <th>
                                Qty
                            </th>

                            <th>
                                Part
                            </th>

                            <th>
                                Model & Size
                            </th>

                            <th>
                                Move To
                            </th>

                        </tr>

                    </thead>


                    <tbody
                        id="cp-today-body"
                    >
                    </tbody>

                </table>

            </div>

        </div>

    `;


    /*
     * Old top summary cards are no longer useful.
     */

    const summaryCards =
        document.querySelector(
            ".cutting-summary"
        );


    if(summaryCards){

        summaryCards.style.display =
            "none";

    }


    /*
     * Ready to Print heading.
     */

    document.querySelectorAll(
        "h1,h2,h3,h4"
    )
    .forEach(function(el){

        if(
            String(
                el.textContent || ""
            ).trim()
            ===
            "Cutting Plan Batches"
        ){

            el.textContent =
                "Ready to Print Cutting Plans";

        }

    });

}



function cpTodayMovePills(
    row
){

    const selected =
        String(
            row.move_to || ""
        )
        .trim()
        .toUpperCase();


    return `

        <div class="cp-v5-move">

            ${["F","SC","U1","U2"]
                .map(function(value){

                    return `

                        <button
                            type="button"

                            class="
                                cp-v5-move-btn
                                ${
                                    selected === value
                                    ? "active"
                                    : ""
                                }
                            "

                            onclick="
                                cpTodaySetMove(
                                    ${Number(row.id)},
                                    '${value}'
                                )
                            "
                        >
                            ${value}
                        </button>

                    `;

                })
                .join("")
            }

        </div>

    `;

}



function renderTodayCuttingRequirements(){

    const tbody =
        document.getElementById(
            "cp-today-body"
        );


    if(!tbody){
        return;
    }


    const rows =
        window.cpTodayRows || [];


    const count =
        document.getElementById(
            "cp-today-count"
        );


    if(count){

        count.textContent =
            rows.length;

    }


    if(!rows.length){

        tbody.innerHTML = `

            <tr>

                <td
                    colspan="10"
                    class="cp-v5-empty"
                >
                    No Cutting requirements received today.
                </td>

            </tr>

        `;


        window.cpTodaySelected.clear();

        cpTodayUpdateActions();

        return;

    }


    tbody.innerHTML =
        rows.map(function(row){

            const id =
                Number(row.id);


            const checked =
                window.cpTodaySelected
                .has(id);


            const material =
                String(
                    row.material_spec || ""
                ).trim();


            const cutSize =
                String(
                    row.cut_size || ""
                ).trim();


            const qty =
                Number(
                    row.planned_qty || 0
                );


            const qtyValid =
                Number.isInteger(qty)
                &&
                qty > 0;


            return `

                <tr
                    class="${
                        checked
                        ? "cp-v6-selected-row"
                        : ""
                    }"
                >


                    <td class="cp-v5-check-col">

                        <input
                            type="checkbox"

                            ${checked
                                ? "checked"
                                : ""
                            }

                            onchange="
                                cpTodayToggleRow(
                                    ${id},
                                    this.checked
                                )
                            "
                        >

                    </td>


                    <td>

                        <div class="cp-v5-jc">

                            ${cpEscapeHtml(
                                row.source_job_card_no
                                ||
                                row.job_card_no
                                ||
                                "-"
                            )}

                        </div>

                    </td>


                    <td>

                        <div class="cp-v5-child">

                            ${cpEscapeHtml(
                                row.child_code || "-"
                            )}

                        </div>

                    </td>


                    <td class="cp-v5-nowrap">

                        ${cpEscapeHtml(
                            cpFormatPlannedDate(
                                row.planned_date,
                                "-"
                            )
                        )}

                    </td>


                    <!-- MATERIAL -->

                    <td>

                        <input
                            type="text"

                            class="
                                cp-v5-input
                                cp-v5-material
                                ${
                                    material
                                    ? ""
                                    : "required"
                                }
                            "

                            value="${cpEscapeHtml(
                                material
                            )}"

                            placeholder="Enter Material"

                            onchange="
                                cpTodaySaveField(
                                    ${id},
                                    'material_spec',
                                    this
                                )
                            "
                        >


                        ${
                            !material
                            ?
                            `
                                <div class="cp-v5-warning">
                                    MATERIAL REQUIRED
                                </div>
                            `
                            :
                            ""
                        }

                    </td>


                    <!-- CUT SIZE -->

                    <td>

                        <input
                            type="text"

                            class="
                                cp-v5-input
                                cp-v5-cut-size
                                ${
                                    cutSize
                                    ? ""
                                    : "required"
                                }
                            "

                            value="${cpEscapeHtml(
                                cutSize
                            )}"

                            placeholder="Enter Cut Size"

                            onchange="
                                cpTodaySaveField(
                                    ${id},
                                    'cut_size',
                                    this
                                )
                            "
                        >


                        ${
                            !cutSize
                            ?
                            `
                                <div class="cp-v5-warning">
                                    CUT SIZE REQUIRED
                                </div>
                            `
                            :
                            ""
                        }

                    </td>


                    <!-- QTY -->

                    <td>

                        <input
                            type="number"

                            min="1"
                            step="1"

                            class="
                                cp-v5-input
                                cp-v5-qty
                                ${
                                    qtyValid
                                    ? ""
                                    : "required"
                                }
                            "

                            value="${
                                qtyValid
                                ? qty
                                : ""
                            }"

                            onchange="
                                cpTodaySaveField(
                                    ${id},
                                    'planned_qty',
                                    this
                                )
                            "
                        >

                    </td>


                    <td class="cp-v5-nowrap">

                        ${cpEscapeHtml(
                            row.part || "-"
                        )}

                    </td>


                    <td class="cp-v5-model">

                        ${cpEscapeHtml(
                            row.model_size
                            ||
                            row.item_name
                            ||
                            "-"
                        )}

                    </td>


                    <td>

                        ${cpTodayMovePills(
                            row
                        )}

                    </td>


                </tr>

            `;

        })
        .join("");


    cpTodayUpdateActions();

}



async function loadTodayCuttingRequirements(){

    try{

        const response =
            await fetch(
                "/api/cutting-plan/today-requirements"
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Unable to load today's Cutting requirements."
            );

        }


        window.cpTodayRows =
            data.plans || [];


        /*
         * Remove selections that no longer exist.
         */

        const existingIds =
            new Set(
                window.cpTodayRows.map(
                    row =>
                        Number(row.id)
                )
            );


        Array.from(
            window.cpTodaySelected
        )
        .forEach(function(id){

            if(!existingIds.has(id)){

                window.cpTodaySelected.delete(
                    id
                );

            }

        });


        renderTodayCuttingRequirements();

        await cpTodayLoadExistingBatches();

    }
    catch(error){

        console.error(
            "Today's Cutting Requirements:",
            error
        );


        showToast(
            error.message ||
            "Unable to load Cutting requirements.",
            "error"
        );

    }

}



function cpTodayToggleRow(
    planId,
    checked
){

    planId =
        Number(planId);


    if(checked){

        window.cpTodaySelected.add(
            planId
        );

    }
    else{

        window.cpTodaySelected.delete(
            planId
        );

    }


    renderTodayCuttingRequirements();

}



function cpTodayToggleAll(
    checked
){

    window.cpTodaySelected.clear();


    if(checked){

        window.cpTodayRows
            .forEach(function(row){

                window.cpTodaySelected.add(
                    Number(row.id)
                );

            });

    }


    renderTodayCuttingRequirements();

}



function cpTodayUpdateActions(){

    const selectedCount =
        window.cpTodaySelected.size;


    const count =
        document.getElementById(
            "cp-today-selected-count"
        );


    if(count){

        count.textContent =
            `${selectedCount} selected`;

    }


    const createButton =
        document.getElementById(
            "cp-today-create-batch"
        );


    if(createButton){

        createButton.disabled =
            selectedCount === 0;

    }


    const batchSelect =
        document.getElementById(
            "cp-today-existing-batch"
        );


    const addButton =
        document.getElementById(
            "cp-today-add-existing"
        );


    if(addButton){

        addButton.disabled =
            (
                selectedCount === 0
                ||
                Number(
                    batchSelect?.value || 0
                ) <= 0
            );

    }


    const selectAll =
        document.getElementById(
            "cp-today-select-all"
        );


    if(selectAll){

        selectAll.checked =
            (
                window.cpTodayRows.length > 0
                &&
                window.cpTodayRows.every(
                    row =>
                        window.cpTodaySelected.has(
                            Number(row.id)
                        )
                )
            );


        selectAll.indeterminate =
            (
                selectedCount > 0
                &&
                !selectAll.checked
            );

    }

}



async function cpTodaySaveField(
    planId,
    field,
    input
){

    planId =
        Number(planId);


    const row =
        window.cpTodayRows.find(
            item =>
                Number(item.id) === planId
        );


    if(!row){
        return;
    }


    let value;


    if(field === "planned_qty"){

        value =
            Number(
                input.value
            );


        if(
            !Number.isInteger(value)
            ||
            value <= 0
        ){

            showToast(
                "Quantity must be a whole number greater than zero.",
                "error"
            );

            renderTodayCuttingRequirements();

            return;

        }

    }
    else{

        value =
            String(
                input.value || ""
            ).trim();

    }


    input.disabled = true;


    try{

        const response =
            await fetch(
                `/api/cutting-plan/${planId}`,
                {
                    method:"PATCH",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            [field]:
                                value
                        })
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Unable to update Cutting Plan."
            );

        }


        if(data.plan){

            Object.assign(
                row,
                data.plan
            );

        }
        else{

            row[field] =
                value;

        }


        showToast(
            "Cutting Plan updated.",
            "success"
        );

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }


    renderTodayCuttingRequirements();

}



async function cpTodaySetMove(
    planId,
    moveTo
){

    const row =
        window.cpTodayRows.find(
            item =>
                Number(item.id)
                ===
                Number(planId)
        );


    if(!row){
        return;
    }


    moveTo =
        String(
            moveTo || ""
        )
        .trim()
        .toUpperCase();


    try{

        const response =
            await fetch(
                `/api/cutting-plan/${Number(planId)}`,
                {
                    method:"PATCH",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            move_to:
                                moveTo
                        })
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Unable to update Move To."
            );

        }


        row.move_to =
            moveTo;


        if(data.plan){

            Object.assign(
                row,
                data.plan
            );

        }


        renderTodayCuttingRequirements();

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }

}



function cpTodaySelectedRows(){

    return window.cpTodayRows.filter(
        row =>
            window.cpTodaySelected.has(
                Number(row.id)
            )
    );

}



function cpTodayValidateSelected(){

    const rows =
        cpTodaySelectedRows();


    if(!rows.length){

        return (
            "Select at least one Job Card."
        );

    }


    for(const row of rows){

        const jc =
            row.source_job_card_no
            ||
            row.job_card_no
            ||
            "Job Card";


        if(
            !String(
                row.material_spec || ""
            ).trim()
        ){

            return (
                `${jc}: Material is required.`
            );

        }


        if(
            !String(
                row.cut_size || ""
            ).trim()
        ){

            return (
                `${jc}: Cut Size is required.`
            );

        }


        const qty =
            Number(
                row.planned_qty || 0
            );


        if(
            !Number.isInteger(qty)
            ||
            qty <= 0
        ){

            return (
                `${jc}: Quantity must be greater than zero.`
            );

        }


        // CUTTING_PLAN_MOVE_TO_LOCAL_FRONTEND_REMOVED_V1
        // Move To is retired.

    }


    return "";

}



async function cpTodayCreateBatch(){

    const error =
        cpTodayValidateSelected();


    if(error){

        showToast(
            error,
            "error"
        );

        return;

    }


    const planIds =
        Array.from(
            window.cpTodaySelected
        );


    const button =
        document.getElementById(
            "cp-today-create-batch"
        );


    button.disabled = true;
    button.textContent =
        "Creating...";


    try{

        const response =
            await fetch(
                "/api/cutting-plan/auto-batch",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({
                            plan_ids:
                                planIds
                        })
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                (
                    Array.isArray(
                        data.validation_errors
                    )
                    &&
                    data.validation_errors.length
                )
                ?
                data.validation_errors.join(
                    " | "
                )
                :
                (
                    data.error ||
                    "Unable to create batch."
                )
            );

        }


        showToast(
            `Batch ${data.plan_batch_no} created successfully.`,
            "success"
        );


        window.cpTodaySelected.clear();


        await loadTodayCuttingRequirements();

        await loadCuttingPlans();

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }
    finally{

        button.textContent =
            "Create Batch";

        cpTodayUpdateActions();

    }

}



async function cpTodayLoadExistingBatches(){

    const select =
        document.getElementById(
            "cp-today-existing-batch"
        );


    if(!select){
        return;
    }


    const current =
        String(
            select.value || ""
        );


    try{

        const response =
            await fetch(
                "/api/cutting-plan/plans?limit=500"
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){
            return;
        }


        const batches =
            new Map();


        (data.plans || [])
        .forEach(function(plan){

            const raw =
                plan.plan_batch_no;


            if(
                raw === null
                ||
                raw === undefined
                ||
                String(raw).trim() === ""
            ){
                return;
            }


            const batchNo =
                Number(raw);


            if(!batches.has(batchNo)){

                batches.set(
                    batchNo,
                    []
                );

            }


            batches.get(
                batchNo
            ).push(plan);

        });


        select.innerHTML = `

            <option value="">
                Select Existing Batch
            </option>

        `;


        Array.from(
            batches.entries()
        )
        .sort(
            (a,b) =>
                a[0] - b[0]
        )
        .forEach(function(entry){

            const batchNo =
                entry[0];

            const rows =
                entry[1];


            const blocked =
                rows.some(function(row){

                    return [
                        "Completed",
                        "Cancelled"
                    ].includes(
                        String(
                            row.status || ""
                        ).trim()
                    );

                });


            if(blocked){
                return;
            }


            const option =
                document.createElement(
                    "option"
                );


            option.value =
                String(batchNo);


            option.textContent =
                `Batch ${batchNo} (${rows.length} JC${rows.length === 1 ? "" : "s"})`;


            select.appendChild(
                option
            );

        });


        if(
            current
            &&
            Array.from(
                select.options
            )
            .some(
                option =>
                    option.value === current
            )
        ){

            select.value =
                current;

        }


        cpTodayUpdateActions();

    }
    catch(error){

        console.error(
            error
        );

    }

}



async function cpTodayAddToExistingBatch(){

    const error =
        cpTodayValidateSelected();


    if(error){

        showToast(
            error,
            "error"
        );

        return;

    }


    const select =
        document.getElementById(
            "cp-today-existing-batch"
        );


    const batchNo =
        Number(
            select?.value || 0
        );


    if(batchNo <= 0){

        showToast(
            "Select an existing batch.",
            "error"
        );

        return;

    }


    const planIds =
        Array.from(
            window.cpTodaySelected
        );


    const button =
        document.getElementById(
            "cp-today-add-existing"
        );


    button.disabled = true;
    button.textContent =
        "Adding...";


    try{

        const response =
            await fetch(
                "/api/cutting-plan/auto-batch/add-existing",
                {
                    method:"POST",

                    headers:{
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify({

                            plan_ids:
                                planIds,

                            plan_batch_no:
                                batchNo

                        })
                }
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Unable to add to existing batch."
            );

        }


        showToast(
            data.message ||
            `Added to Batch ${batchNo}.`,
            "success"
        );


        window.cpTodaySelected.clear();


        await loadTodayCuttingRequirements();

        await loadCuttingPlans();

    }
    catch(error){

        showToast(
            error.message,
            "error"
        );

    }
    finally{

        button.textContent =
            "Add to Existing Batch";

        cpTodayUpdateActions();

    }

}



/*
 * Disable removed workflows.
 */

loadPendingAutoRequirements =
    async function(){
        return;
    };


searchCuttingPlanByParentCode =
    async function(){
        return;
    };


clearCuttingPlanParentSearch =
    function(){
        return;
    };


/*
 * Older UI initializers must now build
 * today's workspace, not Parent Search.
 */

cpInjectParentSearchUI =
    cpTodayBuildWorkspace;


if(
    typeof cpV5BuildSearchWorkspace ===
    "function"
){

    cpV5BuildSearchWorkspace =
        cpTodayBuildWorkspace;

}



/*
 * Safe legacy Pending hide.
 */

cpUnifiedHideOldPendingUI =
    function(){

        const legacy =
            cpTodayFindLegacyPendingCard();


        if(legacy){

            legacy.style.display =
                "none";

        }

    };



function cpTodayInit(){

    cpTodayBuildWorkspace();

    cpUnifiedHideOldPendingUI();

    loadTodayCuttingRequirements();

}



if(
    document.readyState ===
    "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        function(){

            setTimeout(
                cpTodayInit,
                120
            );

        }
    );

}
else{

    setTimeout(
        cpTodayInit,
        120
    );

}


/* CUTTING_PLAN_TODAY_UI_V1_END */



/* ==========================================================
   CUTTING_PLAN_UPLOADED_PENDING_UI_V1
   ========================================================== */


/*
 * Keep the current working card/layout.
 * Only change its meaning from "today" to:
 *
 * Uploaded + Cutting route + not yet batched.
 */

const cpUploadedOriginalBuildWorkspace =
    cpTodayBuildWorkspace;


cpTodayBuildWorkspace =
    function(){

        cpUploadedOriginalBuildWorkspace();


        const panel =
            document.getElementById(
                "cp-parent-search-panel"
            );


        if(!panel){
            return;
        }


        const title =
            panel.querySelector("h2");


        if(title){

            title.textContent =
                "Pending Cutting Requirements";

        }


        const subtitle =
            title
            ? title.parentElement.querySelector(
                "p"
            )
            : null;


        if(subtitle){

            subtitle.textContent =
                "Uploaded Job Cards containing Cutting process, waiting for Cutting Plan preparation.";

        }

};



/*
 * Replace TODAY endpoint with UPLOADED / UNBATCHED endpoint.
 *
 * Existing Material / Cut Size / Qty / Move To editing,
 * selection and batch functions continue unchanged.
 */

loadTodayCuttingRequirements =
    async function(){

        try{

            const response =
                await fetch(
                    "/api/cutting-plan/uploaded-requirements"
                );


            const data =
                await response.json();


            if(
                !response.ok
                ||
                !data.success
            ){

                throw new Error(
                    data.error
                    ||
                    "Unable to load Pending Cutting Requirements."
                );

            }


            window.cpTodayRows =
                data.plans || [];


            /*
             * Remove selections for rows that were
             * batched or are no longer pending.
             */

            const activeIds =
                new Set(
                    window.cpTodayRows.map(
                        row =>
                            Number(row.id)
                    )
                );


            Array.from(
                window.cpTodaySelected
            )
            .forEach(function(id){

                if(
                    !activeIds.has(
                        Number(id)
                    )
                ){

                    window.cpTodaySelected.delete(
                        id
                    );

                }

            });


            renderTodayCuttingRequirements();

            await cpTodayLoadExistingBatches();

        }
        catch(error){

            console.error(
                "Pending Cutting Requirements:",
                error
            );


            showToast(
                error.message
                ||
                "Unable to load Pending Cutting Requirements.",
                "error"
            );

        }

    };



/*
 * When user returns to this browser tab after uploading
 * Job Cards in another tab, reload automatically.
 *
 * No Refresh button is required.
 */

window.addEventListener(
    "focus",
    function(){

        const body =
            document.getElementById(
                "cp-today-body"
            );


        if(body){

            loadTodayCuttingRequirements();

        }

    }
);



/*
 * Ensure final wording after all previous initializers.
 */

function cpUploadedPendingApplyFinalLabels(){

    const panel =
        document.getElementById(
            "cp-parent-search-panel"
        );


    if(!panel){
        return;
    }


    const title =
        panel.querySelector("h2");


    if(title){

        title.textContent =
            "Pending Cutting Requirements";

    }


    const subtitle =
        title
        ? title.parentElement.querySelector(
            "p"
        )
        : null;


    if(subtitle){

        subtitle.textContent =
            "Uploaded Job Cards containing Cutting process, waiting for Cutting Plan preparation.";

    }

}



if(
    document.readyState ===
    "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        function(){

            setTimeout(
                cpUploadedPendingApplyFinalLabels,
                180
            );

        }
    );

}
else{

    setTimeout(
        cpUploadedPendingApplyFinalLabels,
        180
    );

}


/* CUTTING_PLAN_UPLOADED_PENDING_UI_V1_END */



/* ==========================================================
   CUTTING_PLAN_UPLOAD_LOCK_GUARD_V3
   Prevent overlapping automatic pending-list requests.
   ========================================================== */

window.cpUploadedRequirementsLoading = false;


const cpUploadedRequirementsOriginalLoader =
    loadTodayCuttingRequirements;


loadTodayCuttingRequirements =
    async function(){

        if(
            window.cpUploadedRequirementsLoading
        ){
            return;
        }


        window.cpUploadedRequirementsLoading =
            true;


        try{

            await cpUploadedRequirementsOriginalLoader();

        }
        finally{

            window.cpUploadedRequirementsLoading =
                false;

        }

    };


/* CUTTING_PLAN_UPLOAD_LOCK_GUARD_V3_END */



/* ==========================================================
   CUTTING_PLAN_PENDING_FILTER_UI_V1

   Pending Cutting Requirements:
   - Today
   - All Pending
   - Universal Search
   - Date Range
   - Pagination
   ========================================================== */


window.cpPendingFilterState = {
    initialized: false,
    mode: "today",
    search: "",
    from_date: "",
    to_date: "",
    page: 1,
    limit: 100,
    total: 0,
    total_pages: 0
};


window.cpPendingSearchTimer = null;
window.cpPendingListLoading = false;



function cpPendingTodayISO(){

    const now = new Date();

    const local =
        new Date(
            now.getTime()
            -
            now.getTimezoneOffset() * 60000
        );

    return local
        .toISOString()
        .slice(0,10);

}



function cpPendingInitializeState(){

    const state =
        window.cpPendingFilterState;


    if(state.initialized){
        return;
    }


    const today =
        cpPendingTodayISO();


    state.mode =
        "today";

    state.from_date =
        today;

    state.to_date =
        today;

    state.page = 1;

    state.initialized =
        true;

}



function cpPendingInjectFilterUI(){

    cpPendingInitializeState();


    const panel =
        document.getElementById(
            "cp-parent-search-panel"
        );


    if(!panel){
        return;
    }


    /*
     * FILTER BAR
     */

    if(
        !document.getElementById(
            "cp-pending-filter-bar"
        )
    ){

        const header =
            panel.querySelector(
                ".cp-v5-header"
            );


        if(header){

            const filterBar =
                document.createElement(
                    "div"
                );


            filterBar.id =
                "cp-pending-filter-bar";


            filterBar.innerHTML = `

                <!-- UNIVERSAL SEARCH -->

                <div class="cp-pending-search-wrap">

                    <span class="cp-pending-search-icon">
                        &#128269;
                    </span>

                    <input
                        id="cp-pending-search"
                        type="text"

                        placeholder="Search JC, Parent Code, Child Code, Material, Model, SO..."

                        autocomplete="off"

                        oninput="
                            cpPendingQueueSearch(
                                this.value
                            )
                        "

                        onkeydown="
                            if(event.key === 'Enter'){
                                cpPendingRunSearch();
                            }
                        "
                    >

                </div>


                <!-- QUICK DATE MODE -->

                <div class="cp-pending-mode-group">

                    <button
                        id="cp-pending-mode-today"
                        type="button"
                        class="cp-pending-mode-btn"

                        onclick="
                            cpPendingSetMode(
                                'today'
                            )
                        "
                    >
                        Today
                    </button>


                    <button
                        id="cp-pending-mode-all"
                        type="button"
                        class="cp-pending-mode-btn"

                        onclick="
                            cpPendingSetMode(
                                'all'
                            )
                        "
                    >
                        All Pending
                    </button>

                </div>


                <!-- FROM -->

                <label class="cp-pending-date-field">

                    <span>
                        From
                    </span>

                    <input
                        id="cp-pending-from-date"
                        type="date"

                        onchange="
                            cpPendingDateChanged()
                        "
                    >

                </label>


                <!-- TO -->

                <label class="cp-pending-date-field">

                    <span>
                        To
                    </span>

                    <input
                        id="cp-pending-to-date"
                        type="date"

                        onchange="
                            cpPendingDateChanged()
                        "
                    >

                </label>


                <!-- CLEAR -->

                <button
                    type="button"
                    class="cp-btn cp-secondary cp-pending-clear-btn"

                    onclick="
                        cpPendingClearFilters()
                    "
                >
                    Clear
                </button>

            `;


            header.insertAdjacentElement(
                "afterend",
                filterBar
            );

        }

    }


    /*
     * PAGINATION
     */

    if(
        !document.getElementById(
            "cp-pending-pagination"
        )
    ){

        const tableScroll =
            panel.querySelector(
                ".cp-v5-table-scroll"
            );


        if(tableScroll){

            const pager =
                document.createElement(
                    "div"
                );


            pager.id =
                "cp-pending-pagination";


            pager.innerHTML = `

                <div
                    id="cp-pending-result-info"
                    class="cp-pending-result-info"
                >
                    Showing 0 records
                </div>


                <div class="cp-pending-page-controls">

                    <button
                        id="cp-pending-prev"
                        type="button"
                        class="cp-btn cp-secondary"

                        onclick="
                            cpPendingGoPage(
                                window.cpPendingFilterState.page - 1
                            )
                        "
                    >
                        Previous
                    </button>


                    <span
                        id="cp-pending-page-info"
                        class="cp-pending-page-info"
                    >
                        Page 1
                    </span>


                    <button
                        id="cp-pending-next"
                        type="button"
                        class="cp-btn cp-secondary"

                        onclick="
                            cpPendingGoPage(
                                window.cpPendingFilterState.page + 1
                            )
                        "
                    >
                        Next
                    </button>

                </div>

            `;


            tableScroll.insertAdjacentElement(
                "afterend",
                pager
            );

        }

    }


    cpPendingSyncFilterControls();
    cpPendingRenderPagination();

}



function cpPendingSyncFilterControls(){

    const state =
        window.cpPendingFilterState;


    const search =
        document.getElementById(
            "cp-pending-search"
        );


    if(
        search
        &&
        document.activeElement !== search
    ){

        search.value =
            state.search || "";

    }


    const from =
        document.getElementById(
            "cp-pending-from-date"
        );


    if(from){

        from.value =
            state.from_date || "";

    }


    const to =
        document.getElementById(
            "cp-pending-to-date"
        );


    if(to){

        to.value =
            state.to_date || "";

    }


    const todayButton =
        document.getElementById(
            "cp-pending-mode-today"
        );


    const allButton =
        document.getElementById(
            "cp-pending-mode-all"
        );


    if(todayButton){

        todayButton.classList.toggle(
            "active",
            state.mode === "today"
        );

    }


    if(allButton){

        allButton.classList.toggle(
            "active",
            state.mode === "all"
        );

    }

}



function cpPendingRenderPagination(){

    const state =
        window.cpPendingFilterState;


    const total =
        Number(
            state.total || 0
        );


    const page =
        Number(
            state.page || 1
        );


    const limit =
        Number(
            state.limit || 100
        );


    const totalPages =
        Number(
            state.total_pages || 0
        );


    const first =
        total > 0
        ?
        (
            (page - 1) * limit
            + 1
        )
        :
        0;


    const last =
        total > 0
        ?
        Math.min(
            page * limit,
            total
        )
        :
        0;


    const resultInfo =
        document.getElementById(
            "cp-pending-result-info"
        );


    if(resultInfo){

        resultInfo.textContent =
            total > 0
            ?
            `Showing ${first}-${last} of ${total} pending Job Cards`
            :
            "No pending Job Cards found";

    }


    const pageInfo =
        document.getElementById(
            "cp-pending-page-info"
        );


    if(pageInfo){

        pageInfo.textContent =
            totalPages > 0
            ?
            `Page ${page} of ${totalPages}`
            :
            "Page 0 of 0";

    }


    const prev =
        document.getElementById(
            "cp-pending-prev"
        );


    if(prev){

        prev.disabled =
            (
                totalPages <= 1
                ||
                page <= 1
            );

    }


    const next =
        document.getElementById(
            "cp-pending-next"
        );


    if(next){

        next.disabled =
            (
                totalPages <= 1
                ||
                page >= totalPages
            );

    }


    /*
     * Header count = ALL matching records,
     * not only current page.
     */

    const count =
        document.getElementById(
            "cp-today-count"
        );


    if(count){

        count.textContent =
            total;

    }

}



function cpPendingBuildQuery(){

    const state =
        window.cpPendingFilterState;


    const params =
        new URLSearchParams();


    params.set(
        "page",
        String(
            state.page || 1
        )
    );


    params.set(
        "limit",
        String(
            state.limit || 100
        )
    );


    if(
        String(
            state.search || ""
        ).trim()
    ){

        params.set(
            "search",
            String(
                state.search
            ).trim()
        );

    }


    if(state.from_date){

        params.set(
            "from_date",
            state.from_date
        );

    }


    if(state.to_date){

        params.set(
            "to_date",
            state.to_date
        );

    }


    return params.toString();

}



/* ==========================================================
   FINAL PENDING LOADER
   ========================================================== */

loadTodayCuttingRequirements =
async function(){

    cpPendingInitializeState();
    cpPendingInjectFilterUI();


    if(
        window.cpPendingListLoading
    ){
        return;
    }


    window.cpPendingListLoading =
        true;


    const tbody =
        document.getElementById(
            "cp-today-body"
        );


    if(tbody){

        tbody.innerHTML = `

            <tr>

                <td
                    colspan="10"
                    class="cp-v5-empty"
                >
                    Loading Cutting requirements...
                </td>

            </tr>

        `;

    }


    try{

        const query =
            cpPendingBuildQuery();


        const response =
            await fetch(
                "/api/cutting-plan/uploaded-requirements?"
                +
                query
            );


        const data =
            await response.json();


        if(
            !response.ok
            ||
            !data.success
        ){

            throw new Error(
                data.error
                ||
                "Unable to load Pending Cutting Requirements."
            );

        }


        const state =
            window.cpPendingFilterState;


        state.total =
            Number(
                data.total || 0
            );


        state.total_pages =
            Number(
                data.total_pages || 0
            );


        /*
         * If batching removed the last record
         * from the current page, move to the
         * last valid page automatically.
         */

        if(
            state.total_pages > 0
            &&
            state.page > state.total_pages
        ){

            state.page =
                state.total_pages;


            window.cpPendingListLoading =
                false;


            return await loadTodayCuttingRequirements();

        }


        window.cpTodayRows =
            data.plans || [];


        /*
         * Selection belongs only to visible page.
         * Prevent batching hidden records after a filter/page change.
         */

        window.cpTodaySelected.clear();


        renderTodayCuttingRequirements();

        cpPendingSyncFilterControls();

        cpPendingRenderPagination();

        await cpTodayLoadExistingBatches();

    }
    catch(error){

        console.error(
            "Pending Cutting Requirements:",
            error
        );


        window.cpTodayRows = [];

        window.cpTodaySelected.clear();


        renderTodayCuttingRequirements();


        showToast(
            error.message
            ||
            "Unable to load Pending Cutting Requirements.",
            "error"
        );

    }
    finally{

        window.cpPendingListLoading =
            false;

    }

};



/* ==========================================================
   QUICK FILTERS
   ========================================================== */

function cpPendingSetMode(mode){

    const state =
        window.cpPendingFilterState;


    state.mode =
        mode;


    state.page =
        1;


    window.cpTodaySelected.clear();


    if(mode === "today"){

        const today =
            cpPendingTodayISO();


        state.from_date =
            today;


        state.to_date =
            today;

    }
    else{

        state.from_date =
            "";


        state.to_date =
            "";

    }


    cpPendingSyncFilterControls();

    loadTodayCuttingRequirements();

}



function cpPendingDateChanged(){

    const state =
        window.cpPendingFilterState;


    const from =
        document.getElementById(
            "cp-pending-from-date"
        );


    const to =
        document.getElementById(
            "cp-pending-to-date"
        );


    state.from_date =
        from?.value || "";


    state.to_date =
        to?.value || "";


    state.mode =
        "custom";


    state.page =
        1;


    window.cpTodaySelected.clear();


    cpPendingSyncFilterControls();

    loadTodayCuttingRequirements();

}



function cpPendingClearFilters(){

    const state =
        window.cpPendingFilterState;


    state.mode =
        "all";


    state.search =
        "";


    state.from_date =
        "";


    state.to_date =
        "";


    state.page =
        1;


    window.cpTodaySelected.clear();


    const search =
        document.getElementById(
            "cp-pending-search"
        );


    if(search){

        search.value = "";

    }


    cpPendingSyncFilterControls();

    loadTodayCuttingRequirements();

}



/* ==========================================================
   SEARCH
   ========================================================== */

function cpPendingQueueSearch(value){

    const state =
        window.cpPendingFilterState;


    state.search =
        String(
            value || ""
        );


    state.page =
        1;


    clearTimeout(
        window.cpPendingSearchTimer
    );


    window.cpPendingSearchTimer =
        setTimeout(
            function(){

                window.cpTodaySelected.clear();

                loadTodayCuttingRequirements();

            },
            400
        );

}



function cpPendingRunSearch(){

    clearTimeout(
        window.cpPendingSearchTimer
    );


    const input =
        document.getElementById(
            "cp-pending-search"
        );


    window.cpPendingFilterState.search =
        String(
            input?.value || ""
        ).trim();


    window.cpPendingFilterState.page =
        1;


    window.cpTodaySelected.clear();


    loadTodayCuttingRequirements();

}



/* ==========================================================
   PAGINATION
   ========================================================== */

function cpPendingGoPage(page){

    const state =
        window.cpPendingFilterState;


    page =
        Number(page);


    if(
        !Number.isInteger(page)
        ||
        page < 1
        ||
        page > state.total_pages
    ){
        return;
    }


    if(
        page === state.page
    ){
        return;
    }


    state.page =
        page;


    window.cpTodaySelected.clear();


    loadTodayCuttingRequirements();


    const panel =
        document.getElementById(
            "cp-parent-search-panel"
        );


    if(panel){

        panel.scrollIntoView({
            behavior: "smooth",
            block: "start"
        });

    }

}



/* ==========================================================
   INITIAL UI
   ========================================================== */

function cpPendingFilterInit(){

    cpPendingInitializeState();

    cpPendingInjectFilterUI();

}



if(
    document.readyState === "loading"
){

    document.addEventListener(
        "DOMContentLoaded",
        function(){

            setTimeout(
                cpPendingFilterInit,
                200
            );

        }
    );

}
else{

    setTimeout(
        cpPendingFilterInit,
        200
    );

}


/* CUTTING_PLAN_PENDING_FILTER_UI_V1_END */



/* ==========================================================
   CUTTING_PLAN_HISTORY_MODAL_V1

   Read-only Cutting History.
   Data loads only when the user opens the modal.
   ========================================================== */

window.cpCuttingHistoryState = {
    page: 1,
    perPage: 50,
    total: 0,
    pages: 0
};


function cpHistoryEscape(value){

    return String(
        value === null ||
        value === undefined
            ? ""
            : value
    )
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

}


function createCuttingHistoryUI(){

    if(
        document.getElementById(
            "cp-history-modal"
        )
    ){
        return;
    }


    /* ------------------------------------------------------
       HEADER BUTTON
       ------------------------------------------------------ */

    const button = document.createElement(
        "button"
    );

    button.type = "button";

    button.id =
        "cp-history-open-btn";

    button.className =
        "cp-btn cp-history-open-btn";

    button.innerHTML = `
        <i class="fa fa-history"></i>
        <span>Cutting History</span>
        <span
            id="cp-history-count-badge"
            class="cp-history-count-badge"
            style="display:none"
        ></span>
    `;

    button.addEventListener(
        "click",
        openCuttingHistory
    );


    const actions =
        document.querySelector(
            ".cutting-actions"
        );


    if(actions){

        actions.insertBefore(
            button,
            actions.firstChild
        );

    }
    else{

        const header =
            document.querySelector(
                ".cutting-header"
            );

        if(header){

            header.appendChild(
                button
            );

        }

    }


    /* ------------------------------------------------------
       MODAL
       ------------------------------------------------------ */

    const modal =
        document.createElement(
            "div"
        );

    modal.id =
        "cp-history-modal";

    modal.className =
        "cp-history-overlay";

    modal.innerHTML = `

        <div
            class="cp-history-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cp-history-title"
        >

            <div class="cp-history-header">

                <div>

                    <h2 id="cp-history-title">
                        Material Sent to Cutting
                    </h2>

                    <p>
                        History of material already committed
                        through Cutting Plans
                    </p>

                </div>


                <button
                    type="button"
                    class="cp-history-close"
                    id="cp-history-close-btn"
                    title="Close"
                >
                    &times;
                </button>

            </div>


            <div class="cp-history-filters">

                <div class="cp-history-search-wrap">

                    <i class="fa fa-search"></i>

                    <input
                        type="text"
                        id="cp-history-search"
                        placeholder="Search JC, Batch, Material, Cut Size, Part, Model..."
                        autocomplete="off"
                    >

                </div>


                <div class="cp-history-date-field">

                    <label>
                        From
                    </label>

                    <input
                        type="date"
                        id="cp-history-from"
                    >

                </div>


                <div class="cp-history-date-field">

                    <label>
                        To
                    </label>

                    <input
                        type="date"
                        id="cp-history-to"
                    >

                </div>


                <button
                    type="button"
                    class="cp-btn cp-primary"
                    id="cp-history-search-btn"
                >
                    Search
                </button>


                <button
                    type="button"
                    class="cp-btn cp-secondary"
                    id="cp-history-clear-btn"
                >
                    Clear
                </button>

            </div>


            <div class="cp-history-summary">

                <div>
                    <strong id="cp-history-total">
                        0
                    </strong>
                    record(s) sent to Cutting
                </div>

                <div id="cp-history-page-label">
                    Page 1
                </div>

            </div>


            <div class="cp-history-table-wrap">

                <table class="cp-history-table">

                    <thead>

                        <tr>
                            <th>Date</th>
                            <th>Batch No.</th>
                            <th>Job Card</th>
                            <th>Material</th>
                            <th>Cut Size</th>
                            <th>Qty</th>
                            <th>Part</th>
                            <th>Model &amp; Size</th>
                            <th>Move To</th>
                        </tr>

                    </thead>


                    <tbody id="cp-history-body">

                        <tr>
                            <td
                                colspan="9"
                                class="cp-history-empty"
                            >
                                Loading...
                            </td>
                        </tr>

                    </tbody>

                </table>

            </div>


            <div class="cp-history-footer">

                <div
                    class="cp-history-footer-info"
                    id="cp-history-footer-info"
                >
                </div>


                <div class="cp-history-pagination">

                    <button
                        type="button"
                        class="cp-btn cp-secondary"
                        id="cp-history-prev"
                    >
                        Previous
                    </button>

                    <button
                        type="button"
                        class="cp-btn cp-secondary"
                        id="cp-history-next"
                    >
                        Next
                    </button>

                </div>

            </div>

        </div>
    `;


    document.body.appendChild(
        modal
    );


    document.getElementById(
        "cp-history-close-btn"
    ).addEventListener(
        "click",
        closeCuttingHistory
    );


    document.getElementById(
        "cp-history-search-btn"
    ).addEventListener(
        "click",
        function(){

            window.cpCuttingHistoryState.page = 1;

            loadCuttingHistory();

        }
    );


    document.getElementById(
        "cp-history-clear-btn"
    ).addEventListener(
        "click",
        clearCuttingHistoryFilters
    );


    document.getElementById(
        "cp-history-prev"
    ).addEventListener(
        "click",
        function(){

            const state =
                window.cpCuttingHistoryState;

            if(state.page <= 1){
                return;
            }

            state.page -= 1;

            loadCuttingHistory();

        }
    );


    document.getElementById(
        "cp-history-next"
    ).addEventListener(
        "click",
        function(){

            const state =
                window.cpCuttingHistoryState;

            if(
                state.pages &&
                state.page >= state.pages
            ){
                return;
            }

            state.page += 1;

            loadCuttingHistory();

        }
    );


    document.getElementById(
        "cp-history-search"
    ).addEventListener(
        "keydown",
        function(event){

            if(event.key !== "Enter"){
                return;
            }

            event.preventDefault();

            window.cpCuttingHistoryState.page = 1;

            loadCuttingHistory();

        }
    );


    modal.addEventListener(
        "click",
        function(event){

            if(event.target === modal){

                closeCuttingHistory();

            }

        }
    );


    document.addEventListener(
        "keydown",
        function(event){

            if(
                event.key === "Escape" &&
                modal.classList.contains(
                    "open"
                )
            ){

                closeCuttingHistory();

            }

        }
    );

}


async function openCuttingHistory(){

    createCuttingHistoryUI();

    const modal =
        document.getElementById(
            "cp-history-modal"
        );

    if(!modal){
        return;
    }

    modal.classList.add(
        "open"
    );

    document.body.classList.add(
        "cp-history-modal-open"
    );

    window.cpCuttingHistoryState.page = 1;

    await loadCuttingHistory();

}


function closeCuttingHistory(){

    const modal =
        document.getElementById(
            "cp-history-modal"
        );

    if(modal){

        modal.classList.remove(
            "open"
        );

    }

    document.body.classList.remove(
        "cp-history-modal-open"
    );

}


function clearCuttingHistoryFilters(){

    [
        "cp-history-search",
        "cp-history-from",
        "cp-history-to"
    ].forEach(function(id){

        const element =
            document.getElementById(id);

        if(element){

            element.value = "";

        }

    });

    window.cpCuttingHistoryState.page = 1;

    loadCuttingHistory();

}


async function loadCuttingHistory(){

    const state =
        window.cpCuttingHistoryState;


    const tbody =
        document.getElementById(
            "cp-history-body"
        );


    if(!tbody){
        return;
    }


    tbody.innerHTML = `
        <tr>
            <td
                colspan="9"
                class="cp-history-empty"
            >
                Loading Cutting History...
            </td>
        </tr>
    `;


    const search =
        document.getElementById(
            "cp-history-search"
        )?.value.trim() || "";


    const fromDate =
        document.getElementById(
            "cp-history-from"
        )?.value || "";


    const toDate =
        document.getElementById(
            "cp-history-to"
        )?.value || "";


    const params =
        new URLSearchParams({
            page:
                String(state.page),

            per_page:
                String(state.perPage)
        });


    if(search){

        params.set(
            "search",
            search
        );

    }


    if(fromDate){

        params.set(
            "from_date",
            fromDate
        );

    }


    if(toDate){

        params.set(
            "to_date",
            toDate
        );

    }


    try{

        const response =
            await fetch(
                "/api/cutting-plan/history?"
                + params.toString()
            );


        const data =
            await response.json();


        if(
            !response.ok ||
            !data.success
        ){

            throw new Error(
                data.error ||
                "Unable to load Cutting History."
            );

        }


        state.total =
            Number(data.total || 0);

        state.page =
            Number(data.page || 1);

        state.pages =
            Number(data.pages || 0);


        renderCuttingHistory(
            data.rows || []
        );


        updateCuttingHistoryControls();


    }
    catch(error){

        console.error(
            "Cutting History Error",
            error
        );


        tbody.innerHTML = `
            <tr>
                <td
                    colspan="9"
                    class="cp-history-empty cp-history-error"
                >
                    ${cpHistoryEscape(
                        error.message ||
                        "Unable to load Cutting History."
                    )}
                </td>
            </tr>
        `;


        showToast(
            error.message ||
            "Unable to load Cutting History.",
            "error"
        );

    }

}


function renderCuttingHistory(rows){

    const tbody =
        document.getElementById(
            "cp-history-body"
        );


    if(!tbody){
        return;
    }


    if(!rows.length){

        tbody.innerHTML = `
            <tr>
                <td
                    colspan="9"
                    class="cp-history-empty"
                >
                    No Cutting History found.
                </td>
            </tr>
        `;

        return;

    }


    tbody.innerHTML =
        rows.map(function(row){

            return `

                <tr>

                    <td class="cp-history-date">
                        ${cpHistoryEscape(
                            row.sent_date || "-"
                        )}
                    </td>


                    <td>
                        <strong>
                            ${cpHistoryEscape(
                                row.batch_no || "-"
                            )}
                        </strong>
                    </td>


                    <td class="cp-history-jc">
                        ${cpHistoryEscape(
                            row.job_card_no || "-"
                        )}
                    </td>


                    <td class="cp-history-material">
                        ${cpHistoryEscape(
                            row.material || "-"
                        )}
                    </td>


                    <td>
                        ${cpHistoryEscape(
                            row.cut_size || "-"
                        )}
                    </td>


                    <td class="cp-history-qty">
                        ${cpHistoryEscape(
                            row.qty ?? "-"
                        )}
                    </td>


                    <td>
                        ${cpHistoryEscape(
                            row.part || "-"
                        )}
                    </td>


                    <td>
                        ${cpHistoryEscape(
                            row.model_size || "-"
                        )}
                    </td>


                    <td>
                        ${
                            row.move_to
                                ? `
                                    <span
                                        class="cp-history-move-badge"
                                    >
                                        ${cpHistoryEscape(
                                            row.move_to
                                        )}
                                    </span>
                                  `
                                : "-"
                        }
                    </td>

                </tr>

            `;

        }).join("");

}


function updateCuttingHistoryControls(){

    const state =
        window.cpCuttingHistoryState;


    const total =
        document.getElementById(
            "cp-history-total"
        );

    if(total){

        total.textContent =
            state.total;

    }


    const badge =
        document.getElementById(
            "cp-history-count-badge"
        );

    if(badge){

        badge.textContent =
            state.total;

        badge.style.display =
            state.total > 0
                ? "inline-flex"
                : "none";

    }


    const pages =
        Math.max(
            state.pages,
            1
        );


    const pageLabel =
        document.getElementById(
            "cp-history-page-label"
        );

    if(pageLabel){

        pageLabel.textContent =
            `Page ${state.page} of ${pages}`;

    }


    const start =
        state.total
            ? (
                (state.page - 1)
                * state.perPage
            ) + 1
            : 0;


    const end =
        Math.min(
            state.page
            * state.perPage,
            state.total
        );


    const info =
        document.getElementById(
            "cp-history-footer-info"
        );

    if(info){

        info.textContent =
            state.total
                ? `Showing ${start}-${end} of ${state.total}`
                : "No records";

    }


    const prev =
        document.getElementById(
            "cp-history-prev"
        );

    if(prev){

        prev.disabled =
            state.page <= 1;

    }


    const next =
        document.getElementById(
            "cp-history-next"
        );

    if(next){

        next.disabled =
            !state.pages ||
            state.page >= state.pages;

    }

}


document.addEventListener(
    "DOMContentLoaded",
    function(){

        createCuttingHistoryUI();

    }
);


/* CUTTING_PLAN_HISTORY_MODAL_V1_END */


