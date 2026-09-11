from pathlib import Path
import shutil
import subprocess
import tempfile

PATH = Path(r"static/js/oee_machine_operator.js")
MARKER = "MACHINE_OEE_TOOL_PERSISTENCE_UI_V5"

if not PATH.exists():
    raise SystemExit(
        r"ERROR: static\js\oee_machine_operator.js not found. "
        r"Run this from D:\Het\demo2."
    )

text = PATH.read_text(encoding="utf-8")

if MARKER in text:
    raise SystemExit(
        "ERROR: Tooling frontend persistence V5 is already present. No file changed."
    )

required_markers = [
    "MACHINE_OEE_TOOL_DB_MASTER_V3",
    "window.machineOeeGetToolRowsV1",
    "async function saveSelectedActivityV91",
    "async function directSaveAllV3",
    "async function machineOeeCompleteOperationV1",
]

for marker in required_markers:
    if marker not in text:
        raise SystemExit(
            f"ERROR: Required anchor not found: {marker}. No file changed."
        )

# ------------------------------------------------------------
# 1. Add Tooling save/load helpers inside the existing Tool IIFE.
# ------------------------------------------------------------
anchor_tool_end = '''        };

})();

/* MACHINE_OEE_TOOL_ENTRY_V1_END */'''

if text.count(anchor_tool_end) != 1:
    raise SystemExit(
        "ERROR: Tool Entry end anchor is not unique. No file changed."
    )

v5_block = r'''

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


        if (
            (runId > 0)
            ===
            (activityRunId > 0)
        ) {

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


        const payload = {
            tool_rows:
                window.machineOeeGetToolRowsV1()
        };


        if (runId > 0) {

            payload.run_id =
                runId;

        } else {

            payload.activity_run_id =
                activityRunId;
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


        return await machineOeeToolReadApiV5(
            response,
            "Save Tool Position entries"
        );
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
'''

text = text.replace(
    anchor_tool_end,
    "        };\n" + v5_block + "\n\n})();\n\n/* MACHINE_OEE_TOOL_ENTRY_V1_END */",
    1,
)

# ------------------------------------------------------------
# 2. Production Save Progress: save Tool Position rows too.
# ------------------------------------------------------------
anchor_save_progress = '''            await directSaveProductionV3();

            if (
                directLossCurrentTotalV16()
                > 0
            ) {'''

if text.count(anchor_save_progress) != 1:
    raise SystemExit(
        "ERROR: Save Progress anchor is not unique. No file changed."
    )

replace_save_progress = '''            await directSaveProductionV3();

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
            ) {'''

text = text.replace(
    anchor_save_progress,
    replace_save_progress,
    1,
)

# ------------------------------------------------------------
# 3. Tool Room / Development: save Tool Position rows while the
#    activity is RUNNING, before losses + completion.
# ------------------------------------------------------------
anchor_activity = '''        if (!activityRunId) {

            throw new Error(
                "Activity run ID was not returned."
            );
        }


        /*
         * Save A1-A27 using the same visible loss grid,'''

if text.count(anchor_activity) != 1:
    raise SystemExit(
        "ERROR: Activity Tooling save anchor is not unique. No file changed."
    )

replace_activity = '''        if (!activityRunId) {

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
         * Save A1-A27 using the same visible loss grid,'''

text = text.replace(
    anchor_activity,
    replace_activity,
    1,
)

# ------------------------------------------------------------
# 4. Complete Job: persist Tool Position rows before Traceability
#    moves the JC and closes the machine run.
# ------------------------------------------------------------
anchor_complete = '''        await window
            .machineOeeSaveCurrentRunLossesCoreV44();


        /*
         * 2. Get Traceability's real next process.
         */'''

if text.count(anchor_complete) != 1:
    raise SystemExit(
        "ERROR: Complete Job Tooling anchor is not unique. No file changed."
    )

replace_complete = '''        await window
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
         */'''

text = text.replace(
    anchor_complete,
    replace_complete,
    1,
)

# Final in-memory checks before writing.
checks = [
    MARKER,
    "window.machineOeeSaveToolRowsV5",
    "activity_run_id:",
    "run_id:",
    "/api/oee-machine/tooling-entries",
]

for check in checks:
    if check not in text:
        raise SystemExit(
            f"ERROR: Final validation failed for {check}. No file changed."
        )

# Use Node syntax validation when available. The real file is not touched
# unless the complete transformed JS parses successfully.
node = shutil.which("node")

if node:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".js",
        delete=False,
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            [node, "--check", str(tmp_path)],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise SystemExit(
                "ERROR: JavaScript syntax validation failed. No file changed.\n"
                + (result.stderr or result.stdout)
            )
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

PATH.write_text(text, encoding="utf-8")

print("PATCH APPLIED: OEE_TOOL_PERSISTENCE_UI_V5")
print("Tool Position rows now save with Production and Activity workflows.")
print("Saved Production Tool Position rows restore after page refresh.")
print("No existing Tooling transaction data was changed by this patch script.")
