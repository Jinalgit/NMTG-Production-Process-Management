from pathlib import Path
import shutil
import subprocess
import tempfile

TARGET = Path(r"static\js\oee_machine_operator.js")

if not TARGET.exists():
    raise SystemExit(
        "ERROR: static/js/oee_machine_operator.js not found. No file changed."
    )

text = TARGET.read_text(encoding="utf-8")

if "OEE_TOOL_PERSISTENCE_UI_V5" not in text:
    raise SystemExit(
        "ERROR: Tooling V5 is not present. No file changed."
    )

if "OEE_TOOL_SAVE_MESSAGE_V6" in text:
    print("ALREADY APPLIED: OEE_TOOL_SAVE_MESSAGE_V6")
    raise SystemExit(0)

anchor_helper = '''        return await machineOeeToolReadApiV5(
            response,
            "Save Tool Position entries"
        );
'''

replacement_helper = '''        const result =
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
'''

anchor_loss_save = '''        try {

            await window
                .machineOeeDirectSaveMachineLossesV13();


            /* OEE_NO_JC_LOSS_TOAST_V52 */

            if (
                typeof showToast
                === "function"
            ) {

                showToast(
                    "Machine losses saved",
                    "success"
                );
            }


            if (feedback) {

                feedback.style.color =
                    "#16833a";

                feedback.textContent =
                    "Machine losses saved";
            }
'''

replacement_loss_save = '''        try {

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
'''

anchor_observer = '''                machineLoss.innerHTML = `

                    <i
                        class="fa fa-check-circle"
                        aria-hidden="true"
                    ></i>

                    <span>
                        Machine losses saved to database
                    </span>
                `;


                machineOeeShowDbToastV32(
                    "Losses Saved",
                    "Machine loss entries were saved to database."
                );
'''

replacement_observer = '''                const toolCountV6 =
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
'''

checks = (
    ("Tooling V5 save helper", anchor_helper),
    ("Machine loss success block", anchor_loss_save),
    ("Database confirmation observer", anchor_observer),
)

for name, anchor in checks:
    count = text.count(anchor)
    if count != 1:
        raise SystemExit(
            f"ERROR: {name} anchor count is {count}, expected 1. No file changed."
        )

new_text = text.replace(anchor_helper, replacement_helper, 1)
new_text = new_text.replace(anchor_loss_save, replacement_loss_save, 1)
new_text = new_text.replace(anchor_observer, replacement_observer, 1)

new_text += '''

/* OEE_TOOL_SAVE_MESSAGE_V6
 *
 * Activity/no-JC save feedback now reports the actual number
 * of Tool Position records persisted by Tooling V5.
 *
 * No database logic is changed here.
 */
/* OEE_TOOL_SAVE_MESSAGE_V6_END */
'''

node = shutil.which("node")

if node:
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".js",
            encoding="utf-8",
            delete=False,
        ) as temp_file:
            temp_file.write(new_text)
            temp_name = temp_file.name

        result = subprocess.run(
            [node, "--check", temp_name],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise SystemExit(
                "ERROR: JavaScript syntax validation failed. No file changed.\n"
                + (result.stderr or result.stdout)
            )
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)

TARGET.write_text(new_text, encoding="utf-8")

print("PATCH APPLIED: OEE_TOOL_SAVE_MESSAGE_V6")
print("Activity save message now confirms Tool Position record count.")
print("No database logic or existing DB data was changed.")
