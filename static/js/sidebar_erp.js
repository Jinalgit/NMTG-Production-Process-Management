(function () {
    "use strict";

    const STORAGE_KEY = "jms_sidebar_collapsed";

    function isDesktop() {
        return window.matchMedia("(min-width: 769px)").matches;
    }

    function applyState(collapsed) {

        document.documentElement.classList.remove(
            "sidebar-collapsed-preload"
        );

        if (!isDesktop()) {
            document.body.classList.remove("sidebar-collapsed");
            return;
        }

        document.body.classList.toggle("sidebar-collapsed", collapsed);

        const icon = document.getElementById("erp-sidebar-collapse-icon");
        const btn = document.getElementById("erp-sidebar-collapse");

        if (icon) {
            icon.className = collapsed
                ? "fa fa-angle-right"
                : "fa fa-angle-left";
        }

        if (btn) {
            btn.title = collapsed
                ? "Expand sidebar"
                : "Collapse sidebar";
        }
    }

    function toggleSidebar() {

        if (!isDesktop()) return;

        const collapsed =
            !document.body.classList.contains("sidebar-collapsed");

        localStorage.setItem(
            STORAGE_KEY,
            collapsed ? "1" : "0"
        );

        applyState(collapsed);
    }

    function searchModules() {

        if (document.body.classList.contains("sidebar-collapsed")) {
            localStorage.setItem(STORAGE_KEY, "0");
            applyState(false);
        }

        const query = window.prompt("Search modules");

        if (query === null) return;

        const needle = query.trim().toLowerCase();

        if (!needle) return;

        const links = Array.from(
            document.querySelectorAll(".sidebar-links .sidebar-link")
        );

        const match = links.find(function (link) {
            return link.textContent
                .trim()
                .toLowerCase()
                .includes(needle);
        });

        if (match) {
            window.location.href = match.href;
        }
    }

    document.addEventListener("DOMContentLoaded", function () {

        const stored = localStorage.getItem(STORAGE_KEY);

        /* Default is expanded */
        applyState(stored === "1");

        const collapseBtn =
            document.getElementById("erp-sidebar-collapse");

        if (collapseBtn) {
            collapseBtn.addEventListener("click", toggleSidebar);
        }

        const searchBtn =
            document.getElementById("erp-sidebar-search-btn");

        if (searchBtn) {
            searchBtn.addEventListener("click", searchModules);
        }

    });

    document.addEventListener("keydown", function (event) {

        if (
            (event.ctrlKey || event.metaKey) &&
            event.key.toLowerCase() === "k"
        ) {
            event.preventDefault();
            searchModules();
        }
    });

    window.addEventListener("resize", function () {
        const stored = localStorage.getItem(STORAGE_KEY);
        applyState(stored === "1");
    });

})();


/* =========================================================
   COLLAPSED_DATE_FILTER_FLYOUT_V1
========================================================= */

(function () {
    "use strict";

    const FILTER_KEY = "jms_filter_date";


    function getElements() {
        return {
            root:
                document.getElementById(
                    "sidebar-date-filter"
                ),

            toggle:
                document.getElementById(
                    "erp-date-filter-toggle"
                ),

            popover:
                document.getElementById(
                    "erp-date-filter-popover"
                ),

            input:
                document.getElementById(
                    "global-date-filter"
                ),

            clear:
                document.querySelector(
                    "#sidebar-date-filter .sidebar-date-clear"
                ),

            dot:
                document.getElementById(
                    "erp-date-active-dot"
                )
        };
    }


    function sidebarIsCollapsed() {
        return (
            window.matchMedia(
                "(min-width: 769px)"
            ).matches &&
            document.body.classList.contains(
                "sidebar-collapsed"
            )
        );
    }


    function closeDateFlyout() {

        const el = getElements();

        if (!el.root) {
            return;
        }

        el.root.classList.remove(
            "date-flyout-open"
        );

        if (el.toggle) {
            el.toggle.setAttribute(
                "aria-expanded",
                "false"
            );
        }
    }


    function openDateFlyout() {

        const el = getElements();

        if (
            !el.root ||
            !el.toggle ||
            !sidebarIsCollapsed()
        ) {
            return;
        }

        el.root.classList.add(
            "date-flyout-open"
        );

        el.toggle.setAttribute(
            "aria-expanded",
            "true"
        );


        /*
         * Put keyboard focus directly onto the
         * existing date field.
         */
        window.setTimeout(function () {

            if (el.input) {
                el.input.focus();
            }

        }, 40);
    }


    function toggleDateFlyout() {

        const el = getElements();

        if (!el.root) {
            return;
        }

        if (
            el.root.classList.contains(
                "date-flyout-open"
            )
        ) {
            closeDateFlyout();
        }
        else {
            openDateFlyout();
        }
    }


    function syncDateIndicator() {

        const el = getElements();

        if (!el.root) {
            return;
        }

        let value = "";

        if (
            el.input &&
            el.input.value
        ) {
            value = el.input.value;
        }
        else {
            try {
                value =
                    localStorage.getItem(
                        FILTER_KEY
                    ) || "";
            }
            catch (error) {
                value = "";
            }
        }


        const active = Boolean(value);


        el.root.classList.toggle(
            "has-active-date",
            active
        );


        if (el.dot) {
            el.dot.hidden = !active;
        }


        if (el.toggle) {

            el.toggle.title = active
                ? "Date filter active: " + value
                : "Filter by date";

        }
    }


    /*
     * Public helper.
     * Existing filter logic does not depend on this,
     * but it allows indicator refresh when needed.
     */
    window.updateSidebarDateFilterIndicator =
        syncDateIndicator;


    document.addEventListener(
        "DOMContentLoaded",
        function () {

            const el = getElements();

            /*
             * Pages without the sidebar date filter
             * require no further work.
             */
            if (!el.root) {
                return;
            }


            if (el.toggle) {

                el.toggle.addEventListener(
                    "click",
                    function (event) {

                        event.preventDefault();
                        event.stopPropagation();

                        toggleDateFlyout();

                    }
                );

            }


            if (el.popover) {

                el.popover.addEventListener(
                    "click",
                    function (event) {

                        /*
                         * Clicking inside the flyout
                         * must not close it.
                         */
                        event.stopPropagation();

                    }
                );

            }


            if (el.input) {

                el.input.addEventListener(
                    "change",
                    function () {

                        /*
                         * Existing inline onchange first
                         * updates the actual filter.
                         * Indicator refreshes afterwards.
                         */
                        window.setTimeout(
                            syncDateIndicator,
                            0
                        );

                    }
                );

            }


            if (el.clear) {

                el.clear.addEventListener(
                    "click",
                    function () {

                        window.setTimeout(
                            syncDateIndicator,
                            0
                        );

                    }
                );

            }


            /*
             * Click outside closes the flyout.
             */
            document.addEventListener(
                "click",
                function () {

                    closeDateFlyout();

                }
            );


            /*
             * Escape closes the flyout.
             */
            document.addEventListener(
                "keydown",
                function (event) {

                    if (event.key === "Escape") {
                        closeDateFlyout();
                    }

                }
            );


            /*
             * Initial active-date indicator.
             */
            window.setTimeout(
                syncDateIndicator,
                0
            );

        }
    );


    /*
     * If sidebar is expanded while the date
     * flyout is open, close the floating state.
     */
    window.addEventListener(
        "resize",
        function () {

            if (!sidebarIsCollapsed()) {
                closeDateFlyout();
            }

        }
    );

})();

/* =========================================================
   ERP_COMMAND_PALETTE_V1
========================================================= */

(function () {
    "use strict";

    let selectedIndex = 0;
    let visibleCommands = [];


    function getElements() {

        return {
            overlay:
                document.getElementById(
                    "erp-command-overlay"
                ),

            input:
                document.getElementById(
                    "erp-command-input"
                ),

            list:
                document.getElementById(
                    "erp-command-list"
                )
        };

    }


    function getCommands() {

        const links = Array.from(
            document.querySelectorAll(
                ".sidebar-links .sidebar-link"
            )
        );


        return links
            .map(function (link) {

                const textNode =
                    link.querySelector(
                        ".sidebar-text"
                    );

                const name = textNode
                    ? textNode.textContent.trim()
                    : link.textContent.trim();


                return {
                    name: name,
                    url: link.href
                };

            })
            .filter(function (command) {

                return (
                    command.name &&
                    command.url
                );

            });

    }


    function selectIndex(index) {

        const el = getElements();

        if (!el.list || !visibleCommands.length) {
            return;
        }


        if (index < 0) {
            index = visibleCommands.length - 1;
        }


        if (index >= visibleCommands.length) {
            index = 0;
        }


        selectedIndex = index;


        const items = Array.from(
            el.list.querySelectorAll(
                ".erp-command-item"
            )
        );


        items.forEach(
            function (item, itemIndex) {

                const selected =
                    itemIndex === selectedIndex;

                item.classList.toggle(
                    "is-selected",
                    selected
                );

                item.setAttribute(
                    "aria-selected",
                    selected ? "true" : "false"
                );

            }
        );


        const current =
            items[selectedIndex];

        if (current) {

            current.scrollIntoView({
                block: "nearest"
            });

        }

    }


    function renderCommands(query) {

        const el = getElements();

        if (!el.list) {
            return;
        }


        const needle =
            (query || "")
                .trim()
                .toLowerCase();


        visibleCommands =
            getCommands().filter(
                function (command) {

                    return (
                        !needle ||
                        command.name
                            .toLowerCase()
                            .includes(needle)
                    );

                }
            );


        el.list.innerHTML = "";


        if (!visibleCommands.length) {

            const empty =
                document.createElement("div");

            empty.className =
                "erp-command-empty";

            empty.textContent =
                "No matching module found";

            el.list.appendChild(empty);

            selectedIndex = -1;

            return;

        }


        visibleCommands.forEach(
            function (command, index) {

                const button =
                    document.createElement("button");

                button.type = "button";

                button.className =
                    "erp-command-item";

                button.setAttribute(
                    "role",
                    "option"
                );


                const name =
                    document.createElement("span");

                name.className =
                    "erp-command-item-name";

                name.textContent =
                    command.name;


                const type =
                    document.createElement("span");

                type.className =
                    "erp-command-item-type";

                type.textContent =
                    "Module";


                button.appendChild(name);
                button.appendChild(type);


                button.addEventListener(
                    "mouseenter",
                    function () {

                        selectIndex(index);

                    }
                );


                button.addEventListener(
                    "click",
                    function () {

                        window.location.href =
                            command.url;

                    }
                );


                el.list.appendChild(button);

            }
        );


        selectIndex(0);

    }


    function openCommandPalette() {

        const el = getElements();

        if (
            !el.overlay ||
            !el.input ||
            !el.list
        ) {
            return;
        }


        el.overlay.hidden = false;

        el.overlay.setAttribute(
            "aria-hidden",
            "false"
        );


        el.input.value = "";

        renderCommands("");


        window.setTimeout(
            function () {

                el.input.focus();

            },
            20
        );

    }


    function closeCommandPalette() {

        const el = getElements();

        if (!el.overlay) {
            return;
        }


        el.overlay.hidden = true;

        el.overlay.setAttribute(
            "aria-hidden",
            "true"
        );

    }


    function chooseCurrentCommand() {

        if (
            selectedIndex < 0 ||
            selectedIndex >= visibleCommands.length
        ) {
            return;
        }


        const command =
            visibleCommands[selectedIndex];


        if (command && command.url) {

            window.location.href =
                command.url;

        }

    }


    function initializePalette() {

        const el = getElements();

        if (
            !el.overlay ||
            !el.input ||
            !el.list
        ) {
            return;
        }


        el.input.addEventListener(
            "input",
            function () {

                renderCommands(
                    el.input.value
                );

            }
        );


        el.input.addEventListener(
            "keydown",
            function (event) {

                if (event.key === "ArrowDown") {

                    event.preventDefault();

                    selectIndex(
                        selectedIndex + 1
                    );

                    return;

                }


                if (event.key === "ArrowUp") {

                    event.preventDefault();

                    selectIndex(
                        selectedIndex - 1
                    );

                    return;

                }


                if (event.key === "Enter") {

                    event.preventDefault();

                    chooseCurrentCommand();

                    return;

                }


                if (event.key === "Escape") {

                    event.preventDefault();

                    closeCommandPalette();

                }

            }
        );


        el.overlay.addEventListener(
            "mousedown",
            function (event) {

                if (event.target === el.overlay) {

                    closeCommandPalette();

                }

            }
        );

    }


    /*
     * CAPTURE click before the older sidebar search
     * listener can run window.prompt().
     */
    document.addEventListener(
        "click",
        function (event) {

            const button =
                event.target.closest(
                    "#erp-sidebar-search-btn"
                );


            if (!button) {
                return;
            }


            event.preventDefault();

            event.stopImmediatePropagation();

            openCommandPalette();

        },
        true
    );


    /*
     * CAPTURE Ctrl+K before the legacy handler.
     */
    document.addEventListener(
        "keydown",
        function (event) {

            if (
                (event.ctrlKey || event.metaKey) &&
                event.key.toLowerCase() === "k"
            ) {

                event.preventDefault();

                event.stopImmediatePropagation();

                openCommandPalette();

            }

        },
        true
    );


    /*
     * ESC also works when focus is elsewhere.
     */
    document.addEventListener(
        "keydown",
        function (event) {

            const el = getElements();

            if (
                event.key === "Escape" &&
                el.overlay &&
                !el.overlay.hidden
            ) {

                event.preventDefault();

                closeCommandPalette();

            }

        }
    );


    if (document.readyState === "loading") {

        document.addEventListener(
            "DOMContentLoaded",
            initializePalette
        );

    }
    else {

        initializePalette();

    }

})();

/* =========================================================
   ERP_DYNAMIC_PAGE_HEADER_V1
========================================================= */

(function () {
    "use strict";


    function syncSidebarPageHeader() {

        const headerIcon =
            document.getElementById(
                "erp-current-page-icon"
            );

        const headerName =
            document.getElementById(
                "erp-current-page-name"
            );


        if (!headerIcon || !headerName) {
            return;
        }


        /*
         * The active navigation item is already determined
         * by the existing Jinja/sidebar permission logic.
         */
        const activeLink =
            document.querySelector(
                ".sidebar-links .sidebar-link.active"
            );


        if (!activeLink) {

            headerName.textContent = "NMTG";

            headerIcon.innerHTML =
                '<i class="fa fa-industry" aria-hidden="true"></i>';

            return;
        }


        const activeText =
            activeLink.querySelector(
                ".sidebar-text"
            );


        const activeIcon =
            activeLink.querySelector(
                ".sidebar-icon"
            );


        /*
         * Page name
         */
        if (activeText) {

            headerName.textContent =
                activeText.textContent.trim();

        }
        else {

            headerName.textContent =
                activeLink.textContent.trim();

        }


        /*
         * Reuse the exact same icon already shown
         * beside the active navigation item.
         */
        if (activeIcon) {

            headerIcon.innerHTML =
                activeIcon.innerHTML;

        }
        else {

            headerIcon.innerHTML =
                '<i class="fa fa-file-o" aria-hidden="true"></i>';

        }

    }


    if (document.readyState === "loading") {

        document.addEventListener(
            "DOMContentLoaded",
            syncSidebarPageHeader
        );

    }
    else {

        syncSidebarPageHeader();

    }


    /*
     * Public helper in case a future page changes
     * its active navigation state dynamically.
     */
    window.syncSidebarPageHeader =
        syncSidebarPageHeader;

})();

/* =========================================================
   ERP_HEADER_MENU_THEME_V1
========================================================= */

(function () {
    "use strict";

    const THEME_KEY = "jms_theme";


    function elements() {

        return {
            header:
                document.querySelector(
                    ".erp-current-page"
                ),

            menu:
                document.getElementById(
                    "erp-header-menu"
                ),

            reload:
                document.getElementById(
                    "erp-header-reload"
                ),

            theme:
                document.getElementById(
                    "erp-header-theme-toggle"
                ),

            themeIcon:
                document.getElementById(
                    "erp-header-theme-icon"
                )
        };

    }


    function menuIsOpen() {

        const el = elements();

        return Boolean(
            el.menu &&
            !el.menu.hidden
        );

    }


    function openMenu() {

        const el = elements();

        if (!el.menu || !el.header) {
            return;
        }

        el.menu.hidden = false;

        el.header.setAttribute(
            "aria-expanded",
            "true"
        );

    }


    function closeMenu() {

        const el = elements();

        if (!el.menu || !el.header) {
            return;
        }

        el.menu.hidden = true;

        el.header.setAttribute(
            "aria-expanded",
            "false"
        );

    }


    function toggleMenu() {

        if (menuIsOpen()) {
            closeMenu();
        }
        else {
            openMenu();
        }

    }


    function isDark() {

        return document.documentElement
            .classList
            .contains("jms-dark-theme");

    }


    function syncThemeIcon() {

        const el = elements();

        if (!el.themeIcon) {
            return;
        }

        el.themeIcon.className =
            isDark()
                ? "fa fa-sun-o"
                : "fa fa-moon-o";

    }


    function toggleTheme() {

        const nextDark = !isDark();

        document.documentElement
            .classList
            .toggle(
                "jms-dark-theme",
                nextDark
            );

        try {

            localStorage.setItem(
                THEME_KEY,
                nextDark ? "dark" : "light"
            );

        }
        catch (error) {}

        syncThemeIcon();

        closeMenu();

    }


    function initializeHeaderMenu() {

        const el = elements();

        if (!el.header || !el.menu) {
            return;
        }


        /*
         * Existing dynamic page header stays unchanged.
         * We only make the whole header clickable.
         */
        el.header.setAttribute(
            "role",
            "button"
        );

        el.header.setAttribute(
            "tabindex",
            "0"
        );

        el.header.setAttribute(
            "aria-haspopup",
            "menu"
        );

        el.header.setAttribute(
            "aria-expanded",
            "false"
        );


        el.header.addEventListener(
            "click",
            function (event) {

                event.stopPropagation();

                toggleMenu();

            }
        );


        el.header.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Enter" ||
                    event.key === " "
                ) {

                    event.preventDefault();

                    toggleMenu();

                }

                if (event.key === "Escape") {

                    closeMenu();

                }

            }
        );


        el.menu.addEventListener(
            "click",
            function (event) {

                event.stopPropagation();

            }
        );


        if (el.reload) {

            el.reload.addEventListener(
                "click",
                function () {

                    window.location.reload();

                }
            );

        }


        if (el.theme) {

            el.theme.addEventListener(
                "click",
                toggleTheme
            );

        }


        document.addEventListener(
            "click",
            closeMenu
        );


        document.addEventListener(
            "keydown",
            function (event) {

                if (event.key === "Escape") {
                    closeMenu();
                }

            }
        );


        syncThemeIcon();

    }


    if (document.readyState === "loading") {

        document.addEventListener(
            "DOMContentLoaded",
            initializeHeaderMenu
        );

    }
    else {

        initializeHeaderMenu();

    }


    window.syncJmsThemeIcon =
        syncThemeIcon;

})();
