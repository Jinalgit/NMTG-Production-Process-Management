/* ============================================================
   PROCESS MASTER - ERPNEXT DRAFT 2
   PPC HEADER + ERPNEXT EQUALS-ONLY FILTER + PAGINATION
============================================================ */

(function () {
  "use strict";


  const PAGE_SIZE_KEY =
    "pm_rows_per_page";


  const PAGE_SIZES = [
    25,
    50,
    100,
    250
  ];


  const FILTER_DEFS = [
    {
      id:
        "pm-filter-bom-level",

      label:
        "BOM Level",

      defaultValue:
        "top"
    },

    {
      id:
        "pm-filter-make-buy",

      label:
        "Make / Buy",

      defaultValue:
        ""
    },

    {
      id:
        "pm-filter-process-status",

      label:
        "Process Status",

      defaultValue:
        ""
    },

    {
      id:
        "pm-filter-raw-material",

      label:
        "Raw Material",

      defaultValue:
        ""
    },

    {
      id:
        "pm-filter-item-type",

      label:
        "Item Type",

      defaultValue:
        ""
    },

    {
      id:
        "pm-filter-process-name",

      label:
        "Process",

      defaultValue:
        ""
    },

    {
      id:
        "pm-filter-material",

      label:
        "Material",

      defaultValue:
        ""
    },

    {
      id:
        "pm-filter-size",

      label:
        "Size",

      defaultValue:
        ""
    },

    {
      id:
        "pm-filter-updated",

      label:
        "Updated",

      defaultValue:
        ""
    }
  ];


  let booted =
    false;


  let availableFilters =
    [];


  let appliedFilters =
    [];


  let draftFilters =
    [];


  let popover =
    null;


  let filterButton =
    null;


  let activeFilterHost =
    null;


  let paginationObserver =
    null;


  function byId(id) {

    return document.getElementById(
      id
    );
  }


  function clean(value) {

    return String(
      value === null ||
      value === undefined
        ? ""
        : value
    )
      .replace(
        /\s+/g,
        " "
      )
      .trim();
  }


  function escapeHtml(value) {

    return clean(value)
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


  /* ==========================================================
     PAGE HEADER
  ========================================================== */

  function buildPpcHeader() {

    const page =
      document.querySelector(
        ".pm-page"
      );


    if (!page) {
      return;
    }


    page.classList.add(
      "pm2-ready"
    );


    document
      .querySelectorAll(
        ".pm2-page-header"
      )
      .forEach(
        function (element) {

          element.remove();
        }
      );


    document
      .querySelectorAll(
        ".pm-erp-headbar"
      )
      .forEach(
        function (element) {

          element.remove();
        }
      );


    const header =
      document.createElement(
        "header"
      );


    header.className =
      "pm2-page-header";


    header.innerHTML = `

      <nav
        class="pm2-breadcrumb"
        aria-label="Process Master breadcrumb"
      >

        <a
          href="/welcome"
          class="pm2-breadcrumb-home"
          title="Home"
        >
          <i
            class="fa fa-home"
            aria-hidden="true"
          ></i>
        </a>

        <span
          class="pm2-breadcrumb-separator"
        >
          /
        </span>

        <span
          class="pm2-breadcrumb-current"
        >
          Process Master
        </span>

      </nav>
    `;


    page.insertBefore(
      header,
      page.firstChild
    );
  }


  /* ==========================================================
     FILTER DEFINITIONS
  ========================================================== */

  function buildAvailableFilters() {

    availableFilters =
      FILTER_DEFS
        .map(
          function (definition) {

            const control =
              byId(
                definition.id
              );


            if (!control) {
              return null;
            }


            return {
              id:
                definition.id,

              label:
                definition.label,

              defaultValue:
                String(
                  definition.defaultValue
                  || ""
                ),

              type:
                control.tagName ===
                "SELECT"
                  ? "select"
                  : "input",

              control:
                control
            };
          }
        )
        .filter(Boolean);
  }


  function displayValue(
    definition,
    value
  ) {

    if (!definition) {
      return clean(value);
    }


    if (
      definition.type ===
      "select"
    ) {

      const option =
        Array.from(
          definition
            .control
            .options
        )
        .find(
          function (item) {

            return (
              String(
                item.value
              ) ===
              String(
                value
              )
            );
          }
        );


      return clean(
        option?.textContent
        ||
        value
      );
    }


    return clean(value);
  }


  function readExistingFilters() {

    appliedFilters =
      [];


    availableFilters.forEach(
      function (definition) {

        const value =
          String(
            definition
              .control
              .value
            || ""
          );


        if (
          !value
          ||
          value ===
            definition.defaultValue
        ) {
          return;
        }


        appliedFilters.push({
          field:
            definition.id,

          value:
            value
        });
      }
    );
  }


  /* ==========================================================
     TOOLBAR
  ========================================================== */

  function buildToolbar() {

    const toolbar =
      document.querySelector(
        ".pm-page .pm-toolbar"
      );


    if (!toolbar) {
      return;
    }


    toolbar
      .querySelectorAll(
        ".pm2-toolbar-generated"
      )
      .forEach(
        function (element) {

          element.remove();
        }
      );


    const spacer =
      document.createElement(
        "div"
      );


    spacer.className =
      "pm2-toolbar-spacer pm2-toolbar-generated";


    toolbar.appendChild(
      spacer
    );


    filterButton =
      document.createElement(
        "button"
      );


    filterButton.type =
      "button";


    filterButton.className =
      "pm2-filter-button pm2-toolbar-generated";


    filterButton.innerHTML = `

      <i
        class="fa fa-filter"
        aria-hidden="true"
      ></i>

      <span>
        Filter
      </span>

      <span
        class="pm2-filter-badge"
        id="pm2-filter-badge"
        hidden
      >
        0
      </span>
    `;


    toolbar.appendChild(
      filterButton
    );


    const refresh =
      document.createElement(
        "button"
      );


    refresh.type =
      "button";


    refresh.className =
      "pm2-refresh-button pm2-toolbar-generated";


    refresh.title =
      "Refresh Process Master";


    refresh.innerHTML = `

      <i
        class="fa fa-refresh"
        aria-hidden="true"
      ></i>
    `;


    refresh.addEventListener(
      "click",
      function () {

        if (
          typeof resetAndLoad ===
          "function"
        ) {

          resetAndLoad();
        }
      }
    );


    toolbar.appendChild(
      refresh
    );


    activeFilterHost =
      byId(
        "pm2-active-filters"
      );


    if (!activeFilterHost) {

      activeFilterHost =
        document.createElement(
          "div"
        );


      activeFilterHost.id =
        "pm2-active-filters";


      activeFilterHost.className =
        "pm2-active-filters";


      activeFilterHost.hidden =
        true;


      toolbar.insertAdjacentElement(
        "afterend",
        activeFilterHost
      );
    }


    filterButton.addEventListener(
      "click",
      function (event) {

        event.stopPropagation();

        togglePopover();
      }
    );
  }


  /* ==========================================================
     FILTER POPOVER
  ========================================================== */

  function buildPopover() {

    document
      .querySelectorAll(
        ".pm2-filter-popover"
      )
      .forEach(
        function (element) {

          element.remove();
        }
      );


    popover =
      document.createElement(
        "section"
      );


    popover.className =
      "pm2-filter-popover";


    popover.innerHTML = `

      <div
        class="pm2-filter-rows"
        id="pm2-filter-rows"
      ></div>

      <div
        class="pm2-filter-divider"
      ></div>

      <div
        class="pm2-filter-footer"
      >

        <button
          type="button"
          class="pm2-add-filter"
          id="pm2-add-filter"
        >
          + Add a Filter
        </button>

        <div
          class="pm2-filter-footer-spacer"
        ></div>

        <button
          type="button"
          class="pm2-clear-filters"
          id="pm2-clear-filters"
        >
          Clear Filters
        </button>

        <button
          type="button"
          class="pm2-apply-filters"
          id="pm2-apply-filters"
        >
          Apply Filters
        </button>

      </div>
    `;


    document.body.appendChild(
      popover
    );


    byId(
      "pm2-add-filter"
    )?.addEventListener(
      "click",
      function () {

        addFilterRow();
      }
    );


    byId(
      "pm2-clear-filters"
    )?.addEventListener(
      "click",
      function () {

        clearAppliedFilters();
      }
    );


    byId(
      "pm2-apply-filters"
    )?.addEventListener(
      "click",
      function () {

        applyFilters();
      }
    );


    popover.addEventListener(
      "click",
      function (event) {

        event.stopPropagation();
      }
    );
  }


  function positionPopover() {

    if (
      !popover
      ||
      !filterButton
    ) {
      return;
    }


    const rect =
      filterButton
        .getBoundingClientRect();


    const width =
      Math.min(
        585,
        window.innerWidth - 30
      );


    let left =
      rect.right -
      width;


    left =
      Math.max(
        15,
        Math.min(
          left,
          window.innerWidth -
          width -
          15
        )
      );


    let top =
      rect.bottom +
      7;


    const estimatedHeight =
      Math.min(
        380,
        90 +
        (
          Math.max(
            1,
            draftFilters.length
          ) *
          45
        )
      );


    if (
      top +
      estimatedHeight >
      window.innerHeight -
      12
    ) {

      top =
        Math.max(
          12,
          rect.top -
          estimatedHeight -
          7
        );
    }


    popover.style.left =
      `${left}px`;


    popover.style.top =
      `${top}px`;
  }


  function openPopover() {

    if (!popover) {
      return;
    }


    draftFilters =
      appliedFilters.map(
        function (filter) {

          return {
            field:
              filter.field,

            value:
              filter.value
          };
        }
      );


    if (
      !draftFilters.length
    ) {

      addDefaultDraftFilter();
    }


    renderFilterRows();

    positionPopover();


    popover.classList.add(
      "open"
    );


    filterButton?.classList.add(
      "active"
    );
  }


  function closePopover() {

    popover?.classList.remove(
      "open"
    );


    filterButton?.classList.remove(
      "active"
    );
  }


  function togglePopover() {

    if (
      popover?.classList.contains(
        "open"
      )
    ) {

      closePopover();

    } else {

      openPopover();
    }
  }


  function addDefaultDraftFilter() {

    if (!availableFilters.length) {
      return;
    }


    const used =
      new Set(
        draftFilters.map(
          function (filter) {

            return filter.field;
          }
        )
      );


    const definition =
      availableFilters.find(
        function (filter) {

          return !used.has(
            filter.id
          );
        }
      )
      ||
      availableFilters[0];


    draftFilters.push({
      field:
        definition.id,

      value:
        ""
    });
  }


  function addFilterRow() {

    addDefaultDraftFilter();

    renderFilterRows();

    positionPopover();
  }


  function fieldOptionsHtml(
    selectedField
  ) {

    return availableFilters
      .map(
        function (definition) {

          return `

            <option
              value="${escapeHtml(
                definition.id
              )}"
              ${
                definition.id ===
                selectedField
                  ? "selected"
                  : ""
              }
            >
              ${escapeHtml(
                definition.label
              )}
            </option>
          `;
        }
      )
      .join("");
  }


  function valueControlHtml(
    definition,
    value,
    index
  ) {

    if (!definition) {
      return `
        <input
          type="text"
          data-filter-value="${index}"
          value=""
        >
      `;
    }


    if (
      definition.type ===
      "select"
    ) {

      const options =
        Array.from(
          definition
            .control
            .options
        )
        .map(
          function (option) {

            const optionValue =
              String(
                option.value
              );


            return `

              <option
                value="${escapeHtml(
                  optionValue
                )}"
                ${
                  optionValue ===
                  String(value)
                    ? "selected"
                    : ""
                }
              >
                ${escapeHtml(
                  option.textContent
                )}
              </option>
            `;
          }
        )
        .join("");


      return `

        <select
          data-filter-value="${index}"
        >
          ${options}
        </select>
      `;
    }


    return `

      <input
        type="text"
        data-filter-value="${index}"
        value="${escapeHtml(value)}"
      >
    `;
  }


  function renderFilterRows() {

    const host =
      byId(
        "pm2-filter-rows"
      );


    if (!host) {
      return;
    }


    if (!draftFilters.length) {

      host.innerHTML =
        "";

      return;
    }


    host.innerHTML =
      draftFilters
        .map(
          function (
            filter,
            index
          ) {

            const definition =
              availableFilters.find(
                function (item) {

                  return (
                    item.id ===
                    filter.field
                  );
                }
              );


            return `

              <div
                class="pm2-filter-row"
                data-filter-row="${index}"
              >

                <select
                  data-filter-field="${index}"
                  aria-label="Filter field"
                >
                  ${fieldOptionsHtml(
                    filter.field
                  )}
                </select>


                <div
                  class="pm2-equals-box"
                  aria-label="Filter condition"
                >
                  Equals
                </div>


                ${valueControlHtml(
                  definition,
                  filter.value,
                  index
                )}


                <button
                  type="button"
                  class="pm2-filter-remove"
                  data-filter-remove="${index}"
                  title="Remove filter"
                >
                  <i
                    class="fa fa-times"
                    aria-hidden="true"
                  ></i>
                </button>

              </div>
            `;
          }
        )
        .join("");


    host
      .querySelectorAll(
        "[data-filter-field]"
      )
      .forEach(
        function (select) {

          select.addEventListener(
            "change",
            function () {

              const index =
                Number(
                  select.dataset
                    .filterField
                );


              draftFilters[index] = {
                field:
                  select.value,

                value:
                  ""
              };


              renderFilterRows();

              positionPopover();
            }
          );
        }
      );


    host
      .querySelectorAll(
        "[data-filter-value]"
      )
      .forEach(
        function (control) {

          const eventName =
            control.tagName ===
            "SELECT"
              ? "change"
              : "input";


          control.addEventListener(
            eventName,
            function () {

              const index =
                Number(
                  control.dataset
                    .filterValue
                );


              if (
                draftFilters[index]
              ) {

                draftFilters[index]
                  .value =
                  control.value;
              }
            }
          );
        }
      );


    host
      .querySelectorAll(
        "[data-filter-remove]"
      )
      .forEach(
        function (button) {

          button.addEventListener(
            "click",
            function () {

              const index =
                Number(
                  button.dataset
                    .filterRemove
                );


              draftFilters.splice(
                index,
                1
              );


              renderFilterRows();

              positionPopover();
            }
          );
        }
      );
  }


  /* ==========================================================
     APPLY FILTERS
  ========================================================== */

  function resetUnderlyingFilters() {

    availableFilters.forEach(
      function (definition) {

        definition.control.value =
          definition.defaultValue;
      }
    );
  }


  function applyFilters() {

    appliedFilters =
      draftFilters
        .filter(
          function (filter) {

            return Boolean(
              clean(
                filter.value
              )
            );
          }
        )
        .map(
          function (filter) {

            return {
              field:
                filter.field,

              value:
                filter.value
            };
          }
        );


    resetUnderlyingFilters();


    appliedFilters.forEach(
      function (filter) {

        const definition =
          availableFilters.find(
            function (item) {

              return (
                item.id ===
                filter.field
              );
            }
          );


        if (!definition) {
          return;
        }


        definition.control.value =
          filter.value;
      }
    );


    renderAppliedFilters();

    closePopover();


    if (
      typeof resetAndLoad ===
      "function"
    ) {

      resetAndLoad();
    }
  }


  function clearAppliedFilters() {

    appliedFilters =
      [];


    draftFilters =
      [];


    resetUnderlyingFilters();

    renderAppliedFilters();

    closePopover();


    if (
      typeof resetAndLoad ===
      "function"
    ) {

      resetAndLoad();
    }
  }


  function removeAppliedFilter(
    index
  ) {

    appliedFilters.splice(
      index,
      1
    );


    resetUnderlyingFilters();


    appliedFilters.forEach(
      function (filter) {

        const definition =
          availableFilters.find(
            function (item) {

              return (
                item.id ===
                filter.field
              );
            }
          );


        if (definition) {

          definition.control.value =
            filter.value;
        }
      }
    );


    renderAppliedFilters();


    if (
      typeof resetAndLoad ===
      "function"
    ) {

      resetAndLoad();
    }
  }


  function renderAppliedFilters() {

    if (!activeFilterHost) {
      return;
    }


    const badge =
      byId(
        "pm2-filter-badge"
      );


    if (badge) {

      badge.textContent =
        String(
          appliedFilters.length
        );


      badge.hidden =
        appliedFilters.length === 0;
    }


    if (
      !appliedFilters.length
    ) {

      activeFilterHost.innerHTML =
        "";


      activeFilterHost.hidden =
        true;


      return;
    }


    activeFilterHost.hidden =
      false;


    activeFilterHost.innerHTML =
      appliedFilters
        .map(
          function (
            filter,
            index
          ) {

            const definition =
              availableFilters.find(
                function (item) {

                  return (
                    item.id ===
                    filter.field
                  );
                }
              );


            const label =
              definition?.label
              ||
              filter.field;


            const value =
              displayValue(
                definition,
                filter.value
              );


            return `

              <span
                class="pm2-active-filter"
              >

                <strong>
                  ${escapeHtml(label)}
                </strong>

                <span>
                  =
                </span>

                <span>
                  ${escapeHtml(value)}
                </span>

                <button
                  type="button"
                  data-remove-applied="${index}"
                  title="Remove filter"
                >
                  <i
                    class="fa fa-times"
                    aria-hidden="true"
                  ></i>
                </button>

              </span>
            `;
          }
        )
        .join("");


    activeFilterHost
      .querySelectorAll(
        "[data-remove-applied]"
      )
      .forEach(
        function (button) {

          button.addEventListener(
            "click",
            function () {

              removeAppliedFilter(
                Number(
                  button.dataset
                    .removeApplied
                )
              );
            }
          );
        }
      );
  }


  /* ==========================================================
     PAGINATION
  ========================================================== */

  function buildPagination() {

    document
      .querySelectorAll(
        ".pm2-pagination"
      )
      .forEach(
        function (element) {

          element.remove();
        }
      );


    const tree =
      byId(
        "pm-tree"
      );


    if (!tree) {
      return;
    }


    const oldLoadMore =
      byId(
        "pm-load-more"
      );


    const pagination =
      document.createElement(
        "footer"
      );


    pagination.className =
      "pm2-pagination";


    pagination.innerHTML = `

      <div
        class="pm2-pagination-summary"
        id="pm2-pagination-summary"
      >
        Loading...
      </div>


      <div
        class="pm2-pagination-pages"
        id="pm2-pagination-pages"
      ></div>


      <label
        class="pm2-page-size"
      >

        <span>
          Rows per page
        </span>

        <select
          id="pm2-page-size"
        >

          <option value="25">
            25
          </option>

          <option value="50">
            50
          </option>

          <option value="100">
            100
          </option>

          <option value="250">
            250
          </option>

        </select>

      </label>
    `;


    if (oldLoadMore) {

      oldLoadMore.insertAdjacentElement(
        "afterend",
        pagination
      );

    } else {

      tree.insertAdjacentElement(
        "afterend",
        pagination
      );
    }


    const select =
      byId(
        "pm2-page-size"
      );


    if (select) {

      select.value =
        String(
          PM_PER
        );


      select.addEventListener(
        "change",
        function () {

          const size =
            Number(
              select.value
            );


          if (
            !PAGE_SIZES.includes(
              size
            )
          ) {
            return;
          }


          PM_PER =
            size;


          try {

            localStorage.setItem(
              PAGE_SIZE_KEY,
              String(size)
            );

          } catch (_) {
          }


          goToPage(
            1
          );
        }
      );
    }


    byId(
      "pm2-pagination-pages"
    )?.addEventListener(
      "click",
      function (event) {

        const button =
          event.target.closest(
            "[data-page]"
          );


        if (
          !button
          ||
          button.disabled
        ) {
          return;
        }


        goToPage(
          Number(
            button.dataset.page
          )
        );
      }
    );


    observeTree();

    renderPagination();
  }


  function pageTokens(
    current,
    totalPages
  ) {

    if (
      totalPages <= 7
    ) {

      return Array.from(
        {
          length:
            totalPages
        },
        function (_, index) {

          return index + 1;
        }
      );
    }


    const candidates =
      new Set([
        1,
        totalPages,
        current - 1,
        current,
        current + 1
      ]);


    const pages =
      Array.from(
        candidates
      )
        .filter(
          function (page) {

            return (
              page >= 1
              &&
              page <= totalPages
            );
          }
        )
        .sort(
          function (a, b) {

            return a - b;
          }
        );


    const result =
      [];


    pages.forEach(
      function (
        page,
        index
      ) {

        if (
          index > 0
          &&
          page -
          pages[index - 1] >
          1
        ) {

          result.push(
            null
          );
        }


        result.push(
          page
        );
      }
    );


    return result;
  }


  function renderPagination() {

    const summary =
      byId(
        "pm2-pagination-summary"
      );


    const pagesHost =
      byId(
        "pm2-pagination-pages"
      );


    if (
      !summary
      ||
      !pagesHost
    ) {
      return;
    }


    const total =
      Math.max(
        0,
        Number(
          typeof pmTotal !==
            "undefined"
            ? pmTotal
            : 0
        )
      );


    const per =
      Math.max(
        1,
        Number(
          PM_PER
          || 50
        )
      );


    const totalPages =
      Math.max(
        1,
        Math.ceil(
          total /
          per
        )
      );


    let current =
      Number(
        typeof pmPage !==
          "undefined"
          ? pmPage
          : 1
      );


    current =
      Math.max(
        1,
        Math.min(
          current,
          totalPages
        )
      );


    if (
      total === 0
    ) {

      summary.innerHTML =
        "No records found";

    } else {

      const start =
        (
          (current - 1) *
          per
        ) + 1;


      const end =
        Math.min(
          current * per,
          total
        );


      summary.innerHTML = `

        Showing

        <strong>
          ${start}-${end}
        </strong>

        of

        <strong>
          ${total.toLocaleString()}
        </strong>

        records
      `;
    }


    const tokens =
      pageTokens(
        current,
        totalPages
      );


    let html = `

      <button
        type="button"
        class="pm2-page-arrow"
        data-page="${current - 1}"
        ${
          current <= 1
            ? "disabled"
            : ""
        }
        title="Previous page"
      >
        <i
          class="fa fa-chevron-left"
          aria-hidden="true"
        ></i>
      </button>
    `;


    tokens.forEach(
      function (token) {

        if (
          token === null
        ) {

          html += `

            <span
              class="pm2-page-ellipsis"
            >
              ...
            </span>
          `;


          return;
        }


        html += `

          <button
            type="button"
            class="pm2-page-button ${
              token === current
                ? "active"
                : ""
            }"
            data-page="${token}"
          >
            ${token}
          </button>
        `;
      }
    );


    html += `

      <button
        type="button"
        class="pm2-page-arrow"
        data-page="${current + 1}"
        ${
          current >=
          totalPages
            ? "disabled"
            : ""
        }
        title="Next page"
      >
        <i
          class="fa fa-chevron-right"
          aria-hidden="true"
        ></i>
      </button>
    `;


    pagesHost.innerHTML =
      html;
  }


  function clearTree() {

    const tree =
      byId(
        "pm-tree"
      );


    if (!tree) {
      return;
    }


    Array.from(
      tree.children
    )
      .forEach(
        function (child) {

          if (
            child.id ===
              "pm-loading"
            ||
            child.id ===
              "pm-empty"
          ) {
            return;
          }


          child.remove();
        }
      );


    const loading =
      byId(
        "pm-loading"
      );


    if (loading) {

      loading.style.display =
        "";
    }


    const empty =
      byId(
        "pm-empty"
      );


    if (empty) {

      empty.style.display =
        "none";
    }
  }


  async function goToPage(
    page
  ) {

    if (
      typeof loadBom !==
      "function"
    ) {
      return;
    }


    const total =
      Math.max(
        0,
        Number(
          typeof pmTotal !==
            "undefined"
            ? pmTotal
            : 0
        )
      );


    const totalPages =
      Math.max(
        1,
        Math.ceil(
          total /
          Math.max(
            1,
            Number(
              PM_PER
              || 50
            )
          )
        )
      );


    const next =
      Math.max(
        1,
        Math.min(
          Number(page || 1),
          totalPages
        )
      );


    pmPage =
      next;


    clearTree();


    await loadBom();


    window.setTimeout(
      renderPagination,
      20
    );


    const tree =
      byId(
        "pm-tree"
      );


    tree?.scrollIntoView({
      behavior:
        "smooth",

      block:
        "start"
    });
  }


  function observeTree() {

    if (paginationObserver) {
      return;
    }


    const tree =
      byId(
        "pm-tree"
      );


    if (!tree) {
      return;
    }


    paginationObserver =
      new MutationObserver(
        function () {

          window.setTimeout(
            renderPagination,
            30
          );
        }
      );


    paginationObserver.observe(
      tree,
      {
        childList:
          true,

        subtree:
          false
      }
    );
  }


  /* ==========================================================
     GLOBAL EVENTS
  ========================================================== */

  function bindGlobalEvents() {

    document.addEventListener(
      "click",
      function () {

        closePopover();
      }
    );


    window.addEventListener(
      "resize",
      function () {

        if (
          popover?.classList.contains(
            "open"
          )
        ) {

          positionPopover();
        }
      },
      {
        passive:
          true
      }
    );


    window.addEventListener(
      "scroll",
      function () {

        if (
          popover?.classList.contains(
            "open"
          )
        ) {

          positionPopover();
        }
      },
      {
        passive:
          true,

        capture:
          true
      }
    );


    document.addEventListener(
      "keydown",
      function (event) {

        if (
          event.key ===
          "Escape"
        ) {

          closePopover();
        }
      }
    );
  }


  /* ==========================================================
     INIT
  ========================================================== */

  function init() {

    if (booted) {
      return;
    }


    const page =
      document.querySelector(
        ".pm-page"
      );


    if (!page) {
      return;
    }


    if (
      typeof PM_PER ===
      "undefined"
    ) {
      return;
    }


    booted =
      true;


    buildPpcHeader();

    buildAvailableFilters();

    readExistingFilters();

    buildToolbar();

    buildPopover();

    renderAppliedFilters();

    buildPagination();

    bindGlobalEvents();


    window.setTimeout(
      renderPagination,
      350
    );


    window.setTimeout(
      renderPagination,
      900
    );
  }


  let attempts =
    0;


  function boot() {

    attempts +=
      1;


    if (
      document.querySelector(
        ".pm-page"
      )
      &&
      typeof PM_PER !==
        "undefined"
    ) {

      init();

      return;
    }


    if (
      attempts < 120
    ) {

      window.setTimeout(
        boot,
        50
      );
    }
  }


  if (
    document.readyState ===
    "loading"
  ) {

    document.addEventListener(
      "DOMContentLoaded",
      boot,
      {
        once:
          true
      }
    );

  } else {

    boot();
  }

})();

/* PROCESS_MASTER_ERPNEXT_DRAFT_2_END */

/* ============================================================
   PROCESS_MASTER_DRAFT2_ALIGNMENT_FIX_V1
============================================================ */

(function () {
    "use strict";


    let fixedV1 =
        false;


    function textV1(value) {

        return String(
            value || ""
        )
        .replace(
            /\s+/g,
            " "
        )
        .trim();
    }


    function findClearButtonV1(
        toolbar
    ) {

        if (!toolbar) {
            return null;
        }


        const buttons =
            Array.from(
                toolbar.querySelectorAll(
                    "button"
                )
            );


        return buttons.find(
            function (button) {

                const value =
                    textV1(
                        button.textContent
                    ).toLowerCase();


                return (
                    value === "clear"
                    ||
                    value === "clear search"
                );
            }
        ) || null;
    }


    function moveHeaderV1(
        page
    ) {

        if (!page) {
            return;
        }


        const header =
            document.querySelector(
                ".pm2-page-header"
            );


        if (!header) {
            return;
        }


        /*
         * PPC header is NOT inside the page's padded content.
         *
         * Move Process Master header to the same structural
         * level so it can use the full content width.
         */
        if (
            header.parentElement ===
            page
        ) {

            page.parentElement.insertBefore(
                header,
                page
            );
        }


        header.classList.add(
            "pm2-header-corrected-v1"
        );
    }


    function buildToolbarV1(
        page
    ) {

        if (!page) {
            return false;
        }


        const oldToolbar =
            page.querySelector(
                ".pm-toolbar"
            );


        const left =
            page.querySelector(
                ".pm-left"
            );


        if (
            !oldToolbar
            ||
            !left
        ) {
            return false;
        }


        let toolbar =
            page.querySelector(
                ".pm2-list-toolbar-v1"
            );


        if (!toolbar) {

            toolbar =
                document.createElement(
                    "div"
                );


            toolbar.className =
                "pm2-list-toolbar-v1";


            oldToolbar.parentNode.insertBefore(
                toolbar,
                oldToolbar
            );
        }


        /*
         * MOVE the existing search control.
         *
         * Moving the DOM element keeps all of page2.js's
         * existing search listeners/functionality.
         */
        const searchWrap =
            oldToolbar.querySelector(
                ".pm-search-wrap"
            );


        if (
            searchWrap
            &&
            searchWrap.parentElement !==
                toolbar
        ) {

            toolbar.appendChild(
                searchWrap
            );
        }


        /*
         * Existing Clear button.
         */
        const clearButton =
            findClearButtonV1(
                oldToolbar
            )
            ||
            findClearButtonV1(
                toolbar
            );


        if (clearButton) {

            clearButton.classList.add(
                "pm2-search-clear-v1"
            );


            if (
                clearButton.parentElement !==
                toolbar
            ) {

                toolbar.appendChild(
                    clearButton
                );
            }
        }


        /*
         * Existing Draft-2 filter button.
         *
         * Its click event / popup already exists.
         * Only move it to the correct horizontal toolbar.
         */
        const filterButton =
            oldToolbar.querySelector(
                ".pm2-filter-button"
            )
            ||
            page.querySelector(
                ".pm2-filter-button"
            );


        if (filterButton) {

            if (
                filterButton.parentElement !==
                toolbar
            ) {

                toolbar.appendChild(
                    filterButton
                );
            }
        }


        /*
         * Refresh was not part of the requested Process Master
         * layout. Keep functionality available in source but
         * remove it visually from Draft 2.
         */
        const refresh =
            oldToolbar.querySelector(
                ".pm2-refresh-button"
            )
            ||
            page.querySelector(
                ".pm2-refresh-button"
            );


        if (refresh) {

            refresh.classList.add(
                "pm2-refresh-hidden-v1"
            );
        }


        /*
         * Existing original Process Master toolbar remains in
         * DOM because it contains hidden legacy filter controls.
         *
         * Do NOT delete it.
         */
        oldToolbar.classList.add(
            "pm2-legacy-toolbar-v1"
        );


        /*
         * Put applied filters immediately under the new toolbar.
         */
        const activeFilters =
            page.querySelector(
                "#pm2-active-filters"
            );


        if (
            activeFilters
            &&
            activeFilters.previousElementSibling !==
                toolbar
        ) {

            toolbar.insertAdjacentElement(
                "afterend",
                activeFilters
            );
        }


        return Boolean(
            searchWrap
            &&
            filterButton
        );
    }


    function fixLayoutV1() {

        const page =
            document.querySelector(
                ".pm-page"
            );


        if (!page) {
            return;
        }


        moveHeaderV1(
            page
        );


        const ready =
            buildToolbarV1(
                page
            );


        if (ready) {

            page.classList.add(
                "pm2-alignment-fixed-v1"
            );


            fixedV1 =
                true;
        }
    }


    /*
     * Existing Draft-2 JS initializes shortly after page load.
     * Run several safe passes so we attach after its generated
     * Filter button exists.
     */
    window.setTimeout(
        fixLayoutV1,
        20
    );


    window.setTimeout(
        fixLayoutV1,
        150
    );


    window.setTimeout(
        fixLayoutV1,
        450
    );


    window.setTimeout(
        fixLayoutV1,
        900
    );


    /*
     * One observer only until the corrected toolbar exists.
     */
    const observerV1 =
        new MutationObserver(
            function () {

                if (fixedV1) {

                    observerV1.disconnect();

                    return;
                }


                fixLayoutV1();
            }
        );


    observerV1.observe(
        document.documentElement,
        {
            childList:
                true,

            subtree:
                true
        }
    );

})();

/* PROCESS_MASTER_DRAFT2_ALIGNMENT_FIX_V1_END */

/* ============================================================
   PROCESS_MASTER_STABLE_FILTER_V5

   Stable toolbar only.

   IMPORTANT:
   - No MutationObserver.
   - No polling after initialization.
   - Does not call loadBom().
   - Does not call resetAndLoad().
   - Existing Process Master filter logic stays authoritative.
============================================================ */

(function () {
    "use strict";


    function cleanV5(value) {

        return String(
            value || ""
        )
        .replace(/\s+/g, " ")
        .trim();
    }


    function toolbarV5() {

        return document.querySelector(
            ".pm2-list-toolbar-v1"
        );
    }


    function activeFiltersV5() {

        return document.getElementById(
            "pm2-active-filters"
        );
    }


    function findOldSearchClearV5(
        toolbar
    ) {

        if (!toolbar) {
            return null;
        }


        return (
            toolbar.querySelector(
                ".pm2-search-clear-v1"
            )
            ||
            Array.from(
                toolbar.querySelectorAll(
                    "button"
                )
            )
            .find(
                function (button) {

                    return (
                        cleanV5(
                            button.textContent
                        )
                        .toLowerCase()
                        === "clear"
                    );
                }
            )
            ||
            null
        );
    }


    function syncSearchClearV5() {

        const search =
            document.getElementById(
                "pm-search"
            );


        const clear =
            document.getElementById(
                "pm5-search-clear"
            );


        if (
            !search
            ||
            !clear
        ) {
            return;
        }


        clear.hidden =
            cleanV5(
                search.value
            ) === "";
    }


    function syncFilterClearV5() {

        const host =
            activeFiltersV5();


        const clear =
            document.getElementById(
                "pm5-clear-filters"
            );


        if (!clear) {
            return;
        }


        const hasFilters =
            Boolean(
                host
                &&
                !host.hidden
                &&
                host.querySelector(
                    ".pm2-active-filter"
                )
            );


        clear.hidden =
            !hasFilters;
    }


    function installSearchClearV5(
        toolbar
    ) {

        const wrap =
            toolbar.querySelector(
                ".pm-search-wrap"
            );


        const search =
            document.getElementById(
                "pm-search"
            );


        if (
            !wrap
            ||
            !search
        ) {
            return;
        }


        const oldClear =
            findOldSearchClearV5(
                toolbar
            );


        if (oldClear) {

            oldClear.classList.add(
                "pm5-old-clear-hidden"
            );
        }


        let clear =
            document.getElementById(
                "pm5-search-clear"
            );


        if (!clear) {

            clear =
                document.createElement(
                    "button"
                );


            clear.type =
                "button";


            clear.id =
                "pm5-search-clear";


            clear.className =
                "pm5-search-clear";


            clear.title =
                "Clear search";


            clear.setAttribute(
                "aria-label",
                "Clear search"
            );


            clear.innerHTML = `

                <i
                    class="fa fa-times"
                    aria-hidden="true"
                ></i>
            `;


            wrap.appendChild(
                clear
            );


            clear.addEventListener(
                "click",
                function () {

                    /*
                     * Reuse the OLD Clear button if available.
                     * This preserves the existing Process Master
                     * search/reset behavior.
                     */
                    const nativeClear =
                        findOldSearchClearV5(
                            toolbar
                        );


                    if (
                        nativeClear
                        &&
                        nativeClear !== clear
                    ) {

                        nativeClear.click();

                    } else {

                        search.value =
                            "";


                        search.dispatchEvent(
                            new Event(
                                "input",
                                {
                                    bubbles:
                                        true
                                }
                            )
                        );
                    }


                    search.focus();

                    window.setTimeout(
                        syncSearchClearV5,
                        20
                    );
                }
            );


            search.addEventListener(
                "input",
                syncSearchClearV5
            );
        }


        syncSearchClearV5();
    }


    function installClearFiltersV5(
        toolbar
    ) {

        const filterButton =
            toolbar.querySelector(
                ".pm2-filter-button"
            );


        if (!filterButton) {
            return;
        }


        let clear =
            document.getElementById(
                "pm5-clear-filters"
            );


        if (!clear) {

            clear =
                document.createElement(
                    "button"
                );


            clear.type =
                "button";


            clear.id =
                "pm5-clear-filters";


            clear.className =
                "pm5-clear-filters";


            clear.title =
                "Clear all filters";


            clear.setAttribute(
                "aria-label",
                "Clear all filters"
            );


            clear.innerHTML = `

                <i
                    class="fa fa-times"
                    aria-hidden="true"
                ></i>
            `;


            clear.addEventListener(
                "click",
                function () {

                    const nativeClear =
                        document.getElementById(
                            "pm2-clear-filters"
                        );


                    if (nativeClear) {

                        nativeClear.click();
                    }


                    window.setTimeout(
                        syncFilterClearV5,
                        30
                    );
                }
            );
        }


        /*
         * Install ONCE.
         * No observer moves this element later.
         */
        if (
            clear.parentElement !==
                toolbar
        ) {

            filterButton.insertAdjacentElement(
                "afterend",
                clear
            );
        }


        syncFilterClearV5();
    }


    function positionAppliedFiltersV5(
        toolbar
    ) {

        const host =
            activeFiltersV5();


        if (!host) {
            return;
        }


        /*
         * ONE location only:
         *
         * Toolbar
         * Applied filter row
         * Records
         */
        if (
            toolbar.nextElementSibling !==
                host
        ) {

            toolbar.insertAdjacentElement(
                "afterend",
                host
            );
        }


        host.classList.remove(
            "pm3-toolbar-filters",
            "pm4-filter-row"
        );


        host.classList.add(
            "pm5-filter-row"
        );
    }


    function cleanOldClassesV5(
        toolbar
    ) {

        toolbar.classList.remove(
            "pm3-toolbar-ready",
            "pm4-full-width-toolbar"
        );


        toolbar.classList.add(
            "pm5-stable-toolbar"
        );


        const badge =
            document.getElementById(
                "pm2-filter-badge"
            );


        if (badge) {

            badge.hidden =
                true;
        }
    }


    function bindFilterStateEventsV5() {

        /*
         * These events update only the small clear-X visibility.
         * They DO NOT reload data.
         */
        document.addEventListener(
            "click",
            function (event) {

                if (
                    event.target.closest(
                        "#pm2-apply-filters"
                    )
                    ||
                    event.target.closest(
                        "#pm2-clear-filters"
                    )
                    ||
                    event.target.closest(
                        "[data-remove-applied]"
                    )
                ) {

                    window.setTimeout(
                        syncFilterClearV5,
                        30
                    );
                }
            }
        );
    }


    function initV5() {

        const toolbar =
            toolbarV5();


        const filterButton =
            toolbar?.querySelector(
                ".pm2-filter-button"
            );


        if (
            !toolbar
            ||
            !filterButton
        ) {

            return false;
        }


        cleanOldClassesV5(
            toolbar
        );


        installSearchClearV5(
            toolbar
        );


        positionAppliedFiltersV5(
            toolbar
        );


        installClearFiltersV5(
            toolbar
        );


        bindFilterStateEventsV5();


        window.setTimeout(
            syncFilterClearV5,
            50
        );


        return true;
    }


    /*
     * Draft-2 creates its toolbar after the base page starts.
     * Bounded startup retry only.
     *
     * This stops permanently after initialization.
     */
    let attemptsV5 =
        0;


    const bootV5 =
        window.setInterval(
            function () {

                attemptsV5 +=
                    1;


                if (
                    initV5()
                    ||
                    attemptsV5 >= 40
                ) {

                    window.clearInterval(
                        bootV5
                    );
                }

            },
            50
        );

})();

/* PROCESS_MASTER_STABLE_FILTER_V5_END */

/* ============================================================
   PROCESS_MASTER_FILTER_LAYOUT_V6
   Final toolbar alignment correction
============================================================ */

(function () {
    "use strict";


    function cleanV6(value) {

        return String(value || "")
            .replace(/\s+/g, " ")
            .trim();
    }


    function findToolbarV6() {

        return document.querySelector(
            ".pm2-list-toolbar-v1"
        );
    }


    function hideLargeClearV6(toolbar) {

        if (!toolbar) {
            return;
        }


        Array.from(
            toolbar.querySelectorAll(
                "button"
            )
        ).forEach(
            function (button) {

                if (
                    button.classList.contains(
                        "pm2-filter-button"
                    )
                    ||
                    button.id ===
                        "pm6-clear-filters"
                    ||
                    button.id ===
                        "pm5-search-clear"
                ) {
                    return;
                }


                const label =
                    cleanV6(
                        button.textContent
                    ).toLowerCase();


                if (
                    label === "clear"
                    ||
                    label === "clear search"
                ) {

                    button.classList.add(
                        "pm6-hide-large-clear"
                    );
                }
            }
        );
    }


    function hasAppliedFiltersV6() {

        const host =
            document.getElementById(
                "pm2-active-filters"
            );


        return Boolean(
            host
            &&
            !host.hidden
            &&
            host.querySelector(
                ".pm2-active-filter"
            )
        );
    }


    function syncClearXVisibilityV6() {

        const button =
            document.getElementById(
                "pm6-clear-filters"
            );


        if (!button) {
            return;
        }


        button.hidden =
            !hasAppliedFiltersV6();
    }


    function createClearXV6(toolbar) {

        const filterButton =
            toolbar?.querySelector(
                ".pm2-filter-button"
            );


        if (!filterButton) {
            return;
        }


        let clearButton =
            document.getElementById(
                "pm6-clear-filters"
            );


        if (!clearButton) {

            clearButton =
                document.createElement(
                    "button"
                );


            clearButton.type =
                "button";


            clearButton.id =
                "pm6-clear-filters";


            clearButton.className =
                "pm6-clear-filters";


            clearButton.title =
                "Clear Filters";


            clearButton.setAttribute(
                "aria-label",
                "Clear Filters"
            );


            clearButton.innerHTML = `

                <i
                    class="fa fa-times"
                    aria-hidden="true"
                ></i>
            `;


            clearButton.addEventListener(
                "click",
                function () {

                    const popupClear =
                        document.getElementById(
                            "pm2-clear-filters"
                        );


                    if (popupClear) {

                        popupClear.click();
                    }


                    window.setTimeout(
                        syncClearXVisibilityV6,
                        50
                    );
                }
            );
        }


        if (
            clearButton.previousElementSibling !==
                filterButton
        ) {

            filterButton.insertAdjacentElement(
                "afterend",
                clearButton
            );
        }


        syncClearXVisibilityV6();
    }


    function positionAppliedFiltersV6() {

        const page =
            document.querySelector(
                ".pm-page"
            );


        const host =
            document.getElementById(
                "pm2-active-filters"
            );


        const tree =
            document.getElementById(
                "pm-tree"
            );


        const treeWrap =
            tree?.closest(
                ".pm-tree-wrap"
            )
            ||
            document.querySelector(
                ".pm-tree-wrap"
            );


        if (
            !page
            ||
            !host
            ||
            !treeWrap
        ) {
            return;
        }


        host.classList.remove(
            "pm3-toolbar-filters",
            "pm4-filter-row",
            "pm5-filter-row"
        );


        host.classList.add(
            "pm6-filter-row"
        );


        /*
         * Critical fix:
         * Put applied filters directly BEFORE the records area.
         * This gives the chips their own normal-flow height,
         * so the BOM list can never cover them.
         */
        if (
            host.nextElementSibling !==
                treeWrap
        ) {

            treeWrap.parentElement.insertBefore(
                host,
                treeWrap
            );
        }
    }


    function bindFilterActionsV6() {

        document.addEventListener(
            "click",
            function (event) {

                if (
                    event.target.closest(
                        "#pm2-apply-filters"
                    )
                    ||
                    event.target.closest(
                        "#pm2-clear-filters"
                    )
                    ||
                    event.target.closest(
                        "[data-remove-applied]"
                    )
                ) {

                    window.setTimeout(
                        function () {

                            positionAppliedFiltersV6();

                            syncClearXVisibilityV6();
                        },
                        50
                    );
                }
            }
        );
    }


    function initV6() {

        const toolbar =
            findToolbarV6();


        if (!toolbar) {
            return false;
        }


        toolbar.classList.add(
            "pm6-toolbar"
        );


        hideLargeClearV6(
            toolbar
        );


        createClearXV6(
            toolbar
        );


        positionAppliedFiltersV6();


        bindFilterActionsV6();


        return true;
    }


    /*
     * Bounded startup only.
     * No MutationObserver and no permanent polling.
     */
    let triesV6 =
        0;


    const timerV6 =
        window.setInterval(
            function () {

                triesV6 += 1;


                if (
                    initV6()
                    ||
                    triesV6 >= 40
                ) {

                    window.clearInterval(
                        timerV6
                    );
                }

            },
            50
        );

})();

/* PROCESS_MASTER_FILTER_LAYOUT_V6_END */
