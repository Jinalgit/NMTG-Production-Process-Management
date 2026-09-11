(function () {
    "use strict";

    const trigger = document.getElementById("welcome-search-trigger");
    const overlay = document.getElementById("command-overlay");
    const palette = document.getElementById("command-palette");
    const input = document.getElementById("command-search-input");
    const resultsContainer = document.getElementById("command-results");

    if (!trigger || !overlay || !palette || !input || !resultsContainer) {
        return;
    }

    /*
     * Build the command list directly from the launcher modules.
     *
     * This means search and launcher navigation cannot drift apart.
     * If a module is later removed by permissions, search will also
     * automatically stop showing it.
     */
    const commands = Array.from(document.querySelectorAll(".module"))
        .map(function (module) {
            const nameElement = module.querySelector(".module-name");

            return {
                name: nameElement ? nameElement.textContent.trim() : "",
                search: (module.dataset.search || "").trim(),
                url: module.getAttribute("href") || ""
            };
        })
        .filter(function (command) {
            return command.name && command.url;
        });


    let filteredCommands = commands.slice();
    let selectedIndex = 0;


    function openPalette() {
        overlay.classList.add("open");
        overlay.setAttribute("aria-hidden", "false");

        input.value = "";

        filteredCommands = commands.slice();
        selectedIndex = 0;

        renderResults();

        requestAnimationFrame(function () {
            input.focus();
        });
    }


    function closePalette() {
        overlay.classList.remove("open");
        overlay.setAttribute("aria-hidden", "true");

        input.value = "";

        selectedIndex = 0;

        trigger.focus();
    }


    function filterCommands() {
        const query = input.value
            .trim()
            .toLowerCase();

        if (!query) {
            filteredCommands = commands.slice();
        } else {
            filteredCommands = commands.filter(function (command) {
                const searchableText =
                    command.name + " " + command.search;

                return searchableText
                    .toLowerCase()
                    .includes(query);
            });
        }

        selectedIndex = 0;

        renderResults();
    }


    function renderResults() {
        resultsContainer.innerHTML = "";

        if (!filteredCommands.length) {
            const empty = document.createElement("div");

            empty.className = "command-empty";
            empty.textContent = "No matching module found";

            resultsContainer.appendChild(empty);

            return;
        }


        filteredCommands.forEach(function (command, index) {
            const result = document.createElement("div");

            result.className = "command-result";

            if (index === selectedIndex) {
                result.classList.add("active");
            }

            result.dataset.index = String(index);


            const name = document.createElement("span");

            name.className = "command-result-name";
            name.textContent = command.name;


            const suffix = document.createElement("span");

            suffix.className = "command-result-suffix";
            suffix.textContent = "Module";


            result.appendChild(name);
            result.appendChild(suffix);


            result.addEventListener("mouseenter", function () {
                selectedIndex = index;
                updateActiveResult();
            });


            result.addEventListener("click", function () {
                navigateToCommand(index);
            });


            resultsContainer.appendChild(result);
        });


        ensureSelectedVisible();
    }


    function updateActiveResult() {
        const results =
            resultsContainer.querySelectorAll(".command-result");

        results.forEach(function (result, index) {
            result.classList.toggle(
                "active",
                index === selectedIndex
            );
        });

        ensureSelectedVisible();
    }


    function ensureSelectedVisible() {
        const selected =
            resultsContainer.querySelector(".command-result.active");

        if (!selected) {
            return;
        }

        selected.scrollIntoView({
            block: "nearest"
        });
    }


    function moveSelection(direction) {
        if (!filteredCommands.length) {
            return;
        }

        selectedIndex += direction;

        if (selectedIndex < 0) {
            selectedIndex = filteredCommands.length - 1;
        }

        if (selectedIndex >= filteredCommands.length) {
            selectedIndex = 0;
        }

        updateActiveResult();
    }


    function navigateToCommand(index) {
        const command = filteredCommands[index];

        if (!command || !command.url) {
            return;
        }

        window.location.href = command.url;
    }


    /*
     * Mouse
     */
    trigger.addEventListener("click", openPalette);


    overlay.addEventListener("mousedown", function (event) {
        if (event.target === overlay) {
            closePalette();
        }
    });


    palette.addEventListener("mousedown", function (event) {
        event.stopPropagation();
    });


    /*
     * Search input
     */
    input.addEventListener("input", filterCommands);


    input.addEventListener("keydown", function (event) {

        if (event.key === "ArrowDown") {
            event.preventDefault();
            moveSelection(1);
            return;
        }

        if (event.key === "ArrowUp") {
            event.preventDefault();
            moveSelection(-1);
            return;
        }

        if (event.key === "Enter") {
            event.preventDefault();

            if (filteredCommands.length) {
                navigateToCommand(selectedIndex);
            }

            return;
        }

        if (event.key === "Escape") {
            event.preventDefault();
            closePalette();
        }

    });


    /*
     * Global keyboard shortcuts
     */
    document.addEventListener("keydown", function (event) {

        const ctrlOrMeta = event.ctrlKey || event.metaKey;

        if (
            ctrlOrMeta &&
            event.key.toLowerCase() === "k"
        ) {
            event.preventDefault();

            if (overlay.classList.contains("open")) {
                input.focus();
                input.select();
            } else {
                openPalette();
            }

            return;
        }


        if (
            event.key === "Escape" &&
            overlay.classList.contains("open")
        ) {
            event.preventDefault();
            closePalette();
        }

    });

})();
