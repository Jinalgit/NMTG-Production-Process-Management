(function () {
    "use strict";

    const $ = (selector, root = document) =>
        root.querySelector(selector);

    const $$ = (selector, root = document) =>
        Array.from(root.querySelectorAll(selector));


    function getCard(id) {
        const element = document.getElementById(id);

        return element
            ? element.closest(".card")
            : null;
    }


    function getFieldGroup(id) {
        const element = document.getElementById(id);

        if (!element) {
            return null;
        }

        return (
            element.closest(".form-group") ||
            element.parentElement
        );
    }


    function removePreviousGeneratedUi() {

        $$(".ppc-doc-toolbar").forEach(
            (element) => element.remove()
        );

        $$(".ppc-document-tabs").forEach(
            (element) => element.remove()
        );

        $$(".ppc-attachment-section").forEach(
            (element) => element.remove()
        );

        $$(".ppc-priority-attachment").forEach(
            (element) => element.remove()
        );

        $$(".ppc-priority-zone").forEach(
            (zone) => {

                const priority =
                    zone.querySelector(
                        ".priority-row"
                    );

                if (priority) {
                    zone.parentElement.insertBefore(
                        priority,
                        zone
                    );
                }

                zone.remove();
            }
        );
    }


    function buildToolbar(main, orderCard) {

        const save =
            document.getElementById(
                "main-save-btn"
            );

        if (!save) {
            return;
        }

        /*
         * Detach the REAL Save button before removing
         * any old generated toolbar.
         */
        save.remove();

        removePreviousGeneratedUi();


        /*
         * Hide old page-level heading/header without
         * assuming any specific class name.
         */
        const children =
            Array.from(main.children);

        const orderIndex =
            children.indexOf(orderCard);

        children.forEach(
            (child, index) => {

                if (
                    index < orderIndex &&
                    child !== orderCard &&
                    !child.classList.contains("alert") &&
                    !child.classList.contains("alert-container")
                ) {
                    child.classList.add(
                        "ppc-legacy-top-hidden"
                    );
                }
            }
        );


        const toolbar =
            document.createElement("div");

        toolbar.className =
            "ppc-doc-toolbar";

        toolbar.innerHTML = `
            <nav
                class="ppc-doc-breadcrumb"
                aria-label="PPC Job Card breadcrumb"
            >
                <a
                    href="/welcome"
                    class="ppc-home-link"
                    title="Home"
                    aria-label="Open Welcome page"
                >
                    <svg
                        viewBox="0 0 24 24"
                        aria-hidden="true"
                    >
                        <path
                            d="M3 10.8 12 3l9 7.8"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="1.7"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                        ></path>

                        <path
                            d="M5.7 9.8V21h12.6V9.8M9.2 21v-6.8h5.6V21"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="1.7"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                        ></path>
                    </svg>
                </a>

                <span class="ppc-slash">/</span>
                <span>PPC</span>
                <span class="ppc-slash">/</span>

                <strong>
                    Job Cards
                </strong>
            </nav>

            <div class="ppc-doc-actions"></div>
        `;

        main.insertBefore(
            toolbar,
            orderCard
        );


        const actions =
            $(".ppc-doc-actions", toolbar);

        actions.appendChild(save);

        save.classList.add(
            "ppc-save-action"
        );


        /*
         * ERPNext-style initial wording.
         *
         * The ID remains unchanged, therefore existing
         * page1.js can still change it to Preview & Create
         * whenever the BOM workflow requires it.
         */
        const label =
            document.getElementById(
                "main-save-label"
            );

        if (
            label &&
            (
                label.textContent.trim() ===
                "Save Job Card"
            )
        ) {
            label.textContent = "Save";
        }


        const footer =
            $(".form-footer");

        if (footer) {
            footer.classList.add(
                "ppc-old-footer-hidden"
            );
        }
    }


    function setSectionTitle(
        card,
        titleText
    ) {

        if (!card) {
            return;
        }

        card.classList.add(
            "ppc-document-section"
        );

        const title =
            $(".card-title", card);

        if (title) {
            title.textContent =
                titleText;
        }
    }


    function buildOrderLayout(orderCard) {

        if (!orderCard) {
            return;
        }


        const title =
            $(".card-title", orderCard);

        if (!title) {
            return;
        }


        const oldGrid =
            $(".ppc-final-order-grid", orderCard);

        if (oldGrid) {
            oldGrid.remove();
        }


        const grid =
            document.createElement("div");

        grid.className =
            "ppc-final-order-grid";


        const fields = [
            ["so_no", "left"],
            ["customer_name", "right"],

            ["work_order_no", "left"],
            ["delivery_date", "right"],

            ["so_date", "left"],
            ["job_card_date", "right"],

            ["work_order_date", "left"],
            ["remarks", "full"]
        ];


        fields.forEach(
            ([id, position]) => {

                const group =
                    getFieldGroup(id);

                if (!group) {
                    return;
                }

                group.classList.add(
                    "ppc-order-field",
                    `ppc-order-${position}`
                );

                grid.appendChild(group);
            }
        );


        title.insertAdjacentElement(
            "afterend",
            grid
        );


        /*
         * Remove empty layout shells left behind after
         * moving the actual field nodes.
         */
        Array.from(
            orderCard.children
        ).forEach(
            (child) => {

                if (
                    child === title ||
                    child === grid
                ) {
                    return;
                }

                const hasControl =
                    child.querySelector(
                        "input, select, textarea, button"
                    );

                if (
                    !hasControl &&
                    !child.textContent.trim()
                ) {
                    child.remove();
                }
            }
        );
    }


    function buildBomLayout(bomCard) {

        if (!bomCard) {
            return;
        }


        const title =
            $(".card-title", bomCard);

        if (!title) {
            return;
        }


        let inner =
            $(".ppc-bom-inner", bomCard);


        if (!inner) {

            inner =
                document.createElement("div");

            inner.className =
                "ppc-bom-inner";


            let node =
                title.nextSibling;

            while (node) {

                const next =
                    node.nextSibling;

                inner.appendChild(node);

                node = next;
            }


            bomCard.appendChild(inner);
        }
    }


    function buildPriorityAndAttachment(itemCard) {

        if (!itemCard) {
            return;
        }


        $$(".ppc-priority-zone", itemCard)
            .forEach(
                (zone) => {

                    const priority =
                        $(".priority-row", zone);

                    if (priority) {
                        zone.parentElement.insertBefore(
                            priority,
                            zone
                        );
                    }

                    zone.remove();
                }
            );


        const priority =
            $(".priority-row", itemCard);

        if (!priority) {
            return;
        }


        const zone =
            document.createElement("div");

        zone.className =
            "ppc-priority-zone";


        priority.parentElement.insertBefore(
            zone,
            priority
        );


        const priorityLabel =
            document.createElement("div");

        priorityLabel.className =
            "ppc-zone-label";

        priorityLabel.textContent =
            "Priority";


        zone.appendChild(
            priorityLabel
        );


        zone.appendChild(
            priority
        );


        const attachField =
            document.createElement("div");

        attachField.className =
            "ppc-priority-attachment";

        attachField.innerHTML = `
            <label>
                Job Card Attachment
            </label>

            <button
                type="button"
                class="ppc-attach-button"
            >
                Attach
            </button>
        `;


        zone.appendChild(
            attachField
        );


        $(".ppc-attach-button", attachField)
            .addEventListener(
                "click",
                function () {

                    if (
                        typeof window.openUploadModal ===
                        "function"
                    ) {
                        window.openUploadModal("jc");
                    }
                    else {
                        console.error(
                            "openUploadModal() is unavailable."
                        );
                    }
                }
            );
    }


    function styleItemSection(itemCard) {

        if (!itemCard) {
            return;
        }


        const itemRow =
            $(".item-row", itemCard);

        if (itemRow) {
            itemRow.classList.add(
                "ppc-final-item-grid"
            );
        }


        const autofill =
            document.getElementById(
                "item-autofill"
            );

        if (autofill) {

            const section =
                autofill.closest(
                    ".autofill-section"
                ) || autofill;

            section.classList.add(
                "ppc-final-autofill"
            );
        }


        const process =
            document.getElementById(
                "process-days-grid"
            );

        if (process) {

            const processContainer =
                process.parentElement;

            if (processContainer) {
                processContainer.classList.add(
                    "ppc-final-process-area"
                );
            }
        }
    }


    function enhanceUploadModal() {

        const modal =
            document.getElementById(
                "upload-modal"
            );

        const step1 =
            document.getElementById(
                "upload-step-1"
            );

        const input =
            document.getElementById(
                "upload-file-input"
            );

        const filename =
            document.getElementById(
                "upload-filename"
            );

        const mapping =
            document.getElementById(
                "so-mapping-status"
            );


        if (
            !modal ||
            !step1 ||
            !input
        ) {
            return;
        }


        const dialog =
            step1.closest(".modal");

        if (dialog) {
            dialog.classList.add(
                "ppc-upload-dialog"
            );
        }


        const title =
            document.getElementById(
                "upload-modal-title"
            );

        if (title) {
            title.textContent = "Upload";
        }


        /*
         * Remove only our previously generated shell.
         */
        $$(".ppc-upload-custom-shell", step1)
            .forEach(
                (element) => element.remove()
            );


        /*
         * Hide original first-step visual controls.
         * Functional elements remain alive in DOM.
         */
        Array.from(step1.children)
            .forEach(
                (child) => {

                    if (
                        child === input ||
                        child === filename ||
                        child === mapping
                    ) {
                        return;
                    }

                    child.classList.add(
                        "ppc-original-upload-hidden"
                    );
                }
            );


        input.hidden = true;


        const shell =
            document.createElement("div");

        shell.className =
            "ppc-upload-custom-shell";

        shell.innerHTML = `
            <div
                class="ppc-upload-dropzone"
                id="ppc-upload-dropzone"
            >
                <div class="ppc-upload-instruction">
                    Drag and drop files here or upload from
                </div>

                <button
                    type="button"
                    class="ppc-my-device"
                    id="ppc-my-device"
                >
                    <span class="ppc-computer-icon">
                        <svg
                            viewBox="0 0 24 24"
                            aria-hidden="true"
                        >
                            <rect
                                x="3.5"
                                y="4.5"
                                width="17"
                                height="12"
                                rx="1.8"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="1.6"
                            ></rect>

                            <path
                                d="M8 20h8M12 16.5V20"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="1.6"
                                stroke-linecap="round"
                            ></path>
                        </svg>
                    </span>

                    <span>
                        My Device
                    </span>
                </button>
            </div>

            <div class="ppc-upload-modal-footer">
                <button
                    type="button"
                    class="ppc-upload-black-button"
                >
                    Upload
                </button>
            </div>
        `;


        step1.insertBefore(
            shell,
            input
        );


        const dropzone =
            $("#ppc-upload-dropzone", shell);

        const device =
            $("#ppc-my-device", shell);

        const uploadButton =
            $(".ppc-upload-black-button", shell);


        if (filename) {

            filename.classList.add(
                "ppc-upload-selected-file"
            );

            dropzone.appendChild(
                filename
            );
        }


        if (mapping) {
            mapping.classList.add(
                "ppc-upload-mapping-hidden"
            );
        }


        function openFilePicker() {

            input.value = "";

            input.click();
        }


        device.addEventListener(
            "click",
            openFilePicker
        );


        uploadButton.addEventListener(
            "click",
            openFilePicker
        );


        [
            "dragenter",
            "dragover"
        ].forEach(
            (eventName) => {

                dropzone.addEventListener(
                    eventName,
                    function (event) {

                        event.preventDefault();
                        event.stopPropagation();

                        dropzone.classList.add(
                            "is-dragging"
                        );
                    }
                );
            }
        );


        [
            "dragleave",
            "drop"
        ].forEach(
            (eventName) => {

                dropzone.addEventListener(
                    eventName,
                    function (event) {

                        event.preventDefault();
                        event.stopPropagation();

                        dropzone.classList.remove(
                            "is-dragging"
                        );
                    }
                );
            }
        );


        dropzone.addEventListener(
            "drop",
            function (event) {

                const files =
                    event.dataTransfer
                        ? event.dataTransfer.files
                        : null;


                if (
                    !files ||
                    files.length === 0
                ) {
                    return;
                }


                if (
                    typeof window.handleFileSelect !==
                    "function"
                ) {
                    console.error(
                        "handleFileSelect() is unavailable."
                    );

                    return;
                }


                window.handleFileSelect({
                    target: {
                        files: files
                    }
                });
            }
        );
    }


    function initPpcFinalLayout() {

        const main =
            $(".main");

        const orderCard =
            getCard("so_no");

        const bomCard =
            getCard("parent_code");

        const itemCard =
            getCard("job_card_no") ||
            getCard("item_name");


        if (
            !main ||
            !orderCard ||
            !bomCard ||
            !itemCard
        ) {
            console.error(
                "PPC final layout: required sections were not found."
            );

            return;
        }


        buildToolbar(
            main,
            orderCard
        );


        setSectionTitle(
            orderCard,
            "Order Information"
        );


        setSectionTitle(
            bomCard,
            "BOM / Semi-Finished Goods"
        );


        setSectionTitle(
            itemCard,
            "Job Card & Item Information"
        );


        buildOrderLayout(
            orderCard
        );


        buildBomLayout(
            bomCard
        );


        styleItemSection(
            itemCard
        );


        buildPriorityAndAttachment(
            itemCard
        );


        enhanceUploadModal();
    }


    if (
        document.readyState ===
        "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            initPpcFinalLayout,
            {
                once: true
            }
        );
    }
    else {
        initPpcFinalLayout();
    }

})();

/* ============================================================
   PPC_HEADER_MODAL_FINAL_V6
   Final polish only:
   - one unified document header
   - compact ERPNext-style upload modal
============================================================ */

(function () {
    "use strict";

    function finaliseUploadModal() {

        const modal =
            document.getElementById("upload-modal");

        const title =
            document.getElementById("upload-modal-title");

        if (!modal) {
            return;
        }


        function applyModalUi() {

            if (title && title.textContent.trim() !== "Upload") {
                title.textContent = "Upload";
            }


            const closeButton =
                modal.querySelector(
                    'button[onclick*="closeUploadModal"],' +
                    '.modal-close,' +
                    '.close'
                );


            if (closeButton) {

                closeButton.textContent = "×";

                closeButton.classList.add(
                    "ppc-final-upload-close"
                );

                closeButton.setAttribute(
                    "aria-label",
                    "Close"
                );
            }


            const dialog =
                modal.querySelector(".modal");

            if (dialog) {
                dialog.classList.add(
                    "ppc-final-upload-dialog"
                );
            }
        }


        applyModalUi();


        /*
         * Existing upload.js changes the title whenever
         * openUploadModal() runs.
         *
         * Observe that change and restore the approved UI title.
         */
        if (title) {

            const titleObserver =
                new MutationObserver(function () {

                    if (
                        title.textContent.trim() !==
                        "Upload"
                    ) {
                        title.textContent =
                            "Upload";
                    }
                });


            titleObserver.observe(
                title,
                {
                    childList: true,
                    characterData: true,
                    subtree: true
                }
            );
        }


        /*
         * Also react when the existing modal is opened.
         */
        const modalObserver =
            new MutationObserver(function () {

                applyModalUi();
            });


        modalObserver.observe(
            modal,
            {
                attributes: true,
                attributeFilter: [
                    "class",
                    "style"
                ]
            }
        );
    }


    if (
        document.readyState ===
        "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            finaliseUploadModal,
            {
                once: true
            }
        );
    }
    else {

        finaliseUploadModal();
    }

})();

/* ============================================================
   PPC_BOM_TWO_COLUMN_V8
   Finished Goods + Semi-Finished Goods in one row
============================================================ */

(function () {
    "use strict";

    function applyBomTwoColumnLayout() {

        const parentInput =
            document.getElementById("parent_code");

        const childInput =
            document.getElementById("child_code_manual");

        if (!parentInput || !childInput) {
            return;
        }

        const bomCard =
            parentInput.closest(".ppc-document-section") ||
            parentInput.closest(".card");

        if (!bomCard) {
            return;
        }

        const bomInner =
            bomCard.querySelector(".ppc-bom-inner");

        if (!bomInner) {
            return;
        }


        function topLevelChild(element) {

            let current = element;

            while (
                current.parentElement &&
                current.parentElement !== bomInner
            ) {
                current = current.parentElement;
            }

            return (
                current.parentElement === bomInner
                    ? current
                    : null
            );
        }


        const parentBlock =
            topLevelChild(parentInput);

        const childBlock =
            topLevelChild(childInput);


        if (!parentBlock || !childBlock) {
            return;
        }


        bomInner.classList.add(
            "ppc-bom-two-column-grid"
        );


        parentBlock.classList.add(
            "ppc-bom-parent-column"
        );


        childBlock.classList.add(
            "ppc-bom-child-column"
        );
    }


    if (document.readyState === "loading") {

        document.addEventListener(
            "DOMContentLoaded",
            applyBomTwoColumnLayout,
            { once: true }
        );

    } else {

        applyBomTwoColumnLayout();
    }

})();

/* ============================================================
   PPC_BOM_ROW_FIX_V9
   Correct BOM 50/50 row without breaking existing BOM logic
============================================================ */

(function () {
    "use strict";

    function fixBomRow() {

        const parentInput =
            document.getElementById("parent_code");

        const childInput =
            document.getElementById("child_code_manual");

        const manualSection =
            document.getElementById("manual-child-section");


        if (!parentInput || !childInput) {
            return;
        }


        const bomCard =
            parentInput.closest(".ppc-document-section") ||
            parentInput.closest(".card");


        if (!bomCard) {
            return;
        }


        const bomInner =
            bomCard.querySelector(".ppc-bom-inner");


        if (!bomInner) {
            return;
        }


        /*
         * Disable the previous V8 grid because it grouped
         * both controls inside the same top-level wrapper.
         */
        bomInner.classList.remove(
            "ppc-bom-two-column-grid"
        );


        bomInner
            .querySelectorAll(
                ".ppc-bom-parent-column, .ppc-bom-child-column"
            )
            .forEach(function (element) {

                element.classList.remove(
                    "ppc-bom-parent-column",
                    "ppc-bom-child-column"
                );
            });


        /*
         * Finished Goods field.
         */
        const parentGroup =
            parentInput.closest(".form-group") ||
            parentInput.parentElement;


        /*
         * Keep the COMPLETE manual child section intact.
         * This preserves existing JMS show/hide behaviour.
         */
        const childBlock =
            manualSection ||
            childInput.closest(".form-group") ||
            childInput.parentElement;


        if (!parentGroup || !childBlock) {
            return;
        }


        /*
         * If already fixed, do nothing.
         */
        let row =
            bomInner.querySelector(
                ".ppc-bom-code-row-v9"
            );


        if (!row) {

            row =
                document.createElement("div");

            row.className =
                "ppc-bom-code-row-v9";


            /*
             * Find the current top-level BOM block containing
             * the parent field so the new row appears in the
             * same logical position.
             */
            let insertionPoint =
                parentGroup;


            while (
                insertionPoint.parentElement &&
                insertionPoint.parentElement !== bomInner
            ) {

                insertionPoint =
                    insertionPoint.parentElement;
            }


            bomInner.insertBefore(
                row,
                insertionPoint
            );
        }


        parentGroup.classList.add(
            "ppc-bom-left-v9"
        );


        childBlock.classList.add(
            "ppc-bom-right-v9"
        );


        /*
         * Move the functional DOM nodes themselves.
         * IDs and existing JS event handlers remain unchanged.
         */
        row.appendChild(
            parentGroup
        );


        row.appendChild(
            childBlock
        );
    }


    if (
        document.readyState ===
        "loading"
    ) {

        document.addEventListener(
            "DOMContentLoaded",
            fixBomRow,
            {
                once: true
            }
        );

    } else {

        fixBomRow();
    }

})();
