// STANDALONE_OEE_READ_ONLY_V1

let oeeFiltersLoaded = false;


function oeeEscapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}


function oeeFormatNumber(value, decimals = 2) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "-";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "-";
  }

  return number.toFixed(decimals);
}


function oeeFormatPercent(value) {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return "-";
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "-";
  }

  // Backend stores ratio values.
  // Multiplication by 100 is display formatting only.
  return (number * 100).toFixed(1) + "%";
}


function oeeFormatDate(value) {
  if (!value) {
    return "-";
  }

  const raw = String(value);

  return raw.length >= 10
    ? raw.slice(0, 10)
    : raw;
}


function populateOeeMachineFilter(rows) {
  const select = document.getElementById(
    "oee-machine-filter"
  );

  if (!select) {
    return;
  }

  const previous = select.value;

  select.innerHTML =
    '<option value="">All Machines</option>';

  (rows || []).forEach(row => {
    if (!row.machine_id) {
      return;
    }

    const option = document.createElement("option");

    option.value = String(row.machine_id);

    const no = row.machine_no || "";
    const name = row.machine_name || "";

    option.textContent =
      no && name
        ? `${no} - ${name}`
        : no || name || `Machine ${row.machine_id}`;

    select.appendChild(option);
  });

  if (
    previous &&
    Array.from(select.options).some(
      option => option.value === previous
    )
  ) {
    select.value = previous;
  }
}


function populateOeeProcessFilter(rows) {
  const select = document.getElementById(
    "oee-process-filter"
  );

  if (!select) {
    return;
  }

  const previous = select.value;

  select.innerHTML =
    '<option value="">All Processes</option>';

  (rows || []).forEach(processName => {
    if (!processName) {
      return;
    }

    const option = document.createElement("option");

    option.value = String(processName);
    option.textContent = String(processName);

    select.appendChild(option);
  });

  if (
    previous &&
    Array.from(select.options).some(
      option => option.value === previous
    )
  ) {
    select.value = previous;
  }
}


function populateOeeOperatorFilter(rows) {
  const select = document.getElementById(
    "oee-operator-filter"
  );

  if (!select) {
    return;
  }

  const previous = select.value;

  select.innerHTML =
    '<option value="">All Operators</option>';

  (rows || []).forEach(row => {
    if (!row.operator_user_id) {
      return;
    }

    const option = document.createElement("option");

    option.value = String(
      row.operator_user_id
    );

    option.textContent =
      row.operator_name ||
      `Operator ${row.operator_user_id}`;

    select.appendChild(option);
  });

  if (
    previous &&
    Array.from(select.options).some(
      option => option.value === previous
    )
  ) {
    select.value = previous;
  }
}


function populateOeeFilters(filters) {
  filters = filters || {};

  populateOeeMachineFilter(
    filters.machines || []
  );

  populateOeeProcessFilter(
    filters.processes || []
  );

  populateOeeOperatorFilter(
    filters.operators || []
  );

  oeeFiltersLoaded = true;
}


function renderOeeSummary(summary) {
  summary = summary || {};

  const values = {
    "oee-summary-oee":
      oeeFormatPercent(summary.avg_oee_ratio),

    "oee-summary-ar":
      oeeFormatPercent(summary.avg_ar_ratio),

    "oee-summary-pr":
      oeeFormatPercent(summary.avg_pr_ratio),

    "oee-summary-qr":
      oeeFormatPercent(summary.avg_qr_ratio),

    "oee-summary-plan-vs-actual":
      oeeFormatPercent(
        summary.avg_plan_vs_actual
      )
  };

  Object.entries(values).forEach(
    ([id, value]) => {
      const element =
        document.getElementById(id);

      if (element) {
        element.textContent = value;
      }
    }
  );
}


function renderOeeRows(rows) {
  const tbody =
    document.getElementById("oee-tbody");

  const table =
    document.getElementById("oee-table");

  const loading =
    document.getElementById("oee-loading");

  if (!tbody || !table || !loading) {
    return;
  }

  if (!rows || rows.length === 0) {
    tbody.innerHTML = "";

    table.style.display = "none";

    loading.style.display = "block";

    loading.textContent =
      "No active OEE records found.";

    return;
  }

  tbody.innerHTML = rows.map(row => {
    const machine =
      row.machine_no ||
      row.machine_name ||
      "-";

    return `
      <tr>
        <td>${oeeEscapeHtml(row.shift_name || "-")}</td>
        <td>${oeeEscapeHtml(machine)}</td>
        <td>${oeeEscapeHtml(row.operator_name || "-")}</td>
        <td>${oeeEscapeHtml(row.job_card_no || "-")}</td>
        <td>${oeeEscapeHtml(row.item_name || "-")}</td>
        <td>${oeeEscapeHtml(row.process_name || "-")}</td>

        <td>${oeeEscapeHtml(row.ok_qty ?? 0)}</td>
        <td>${oeeEscapeHtml(row.hold_qty ?? 0)}</td>
        <td>${oeeEscapeHtml(row.rejected_qty ?? 0)}</td>

        <td>${oeeEscapeHtml(
          oeeFormatNumber(row.planned_minutes)
        )}</td>

        <td>${oeeEscapeHtml(
          oeeFormatNumber(row.run_minutes)
        )}</td>

        <td>${oeeEscapeHtml(
          oeeFormatPercent(row.plan_vs_actual)
        )}</td>

        <td>${oeeEscapeHtml(
          oeeFormatPercent(row.detailed_ar_ratio)
        )}</td>

        <td>${oeeEscapeHtml(
          oeeFormatPercent(row.detailed_pr_ratio)
        )}</td>

        <td>${oeeEscapeHtml(
          oeeFormatPercent(row.detailed_qr_ratio)
        )}</td>

        <td>
          <strong>
            ${oeeEscapeHtml(
              oeeFormatPercent(
                row.detailed_oee_ratio
              )
            )}
          </strong>
        </td>
      </tr>
    `;
  }).join("");

  loading.style.display = "none";
  table.style.display = "table";
}


async function loadOeeResults() {
  const loading =
    document.getElementById("oee-loading");

  const table =
    document.getElementById("oee-table");

  if (loading) {
    loading.style.display = "block";
    loading.textContent =
      "Loading OEE records...";
  }

  if (table) {
    table.style.display = "none";
  }

  const params = new URLSearchParams();

  const fromDate =
    document.getElementById(
      "oee-from-date"
    )?.value || "";

  const toDate =
    document.getElementById(
      "oee-to-date"
    )?.value || "";

  const machineId =
    document.getElementById(
      "oee-machine-filter"
    )?.value || "";

  const processName =
    document.getElementById(
      "oee-process-filter"
    )?.value || "";

  const operatorUserId =
    document.getElementById(
      "oee-operator-filter"
    )?.value || "";

  const search =
    document.getElementById(
      "oee-search"
    )?.value.trim() || "";

  if (fromDate) {
    params.set("from_date", fromDate);
  }

  if (toDate) {
    params.set("to_date", toDate);
  }

  if (machineId) {
    params.set("machine_id", machineId);
  }

  if (processName) {
    params.set(
      "process_name",
      processName
    );
  }

  if (operatorUserId) {
    params.set(
      "operator_user_id",
      operatorUserId
    );
  }

  if (search) {
    params.set("search", search);
  }

  params.set("page", "1");
  params.set("per_page", "200");

  try {
    // OEE_SIDEBAR_DATE_FILTER_V1
    // Date filtering for OEE comes only from the
    // common sidebar date filter used by Analytics/Data View.
    params.delete("from_date");
    params.delete("to_date");

    const globalDateInput =
      document.getElementById(
        "global-date-filter"
      );

    const globalDate =
      (
        globalDateInput?.value
        || localStorage.getItem(
          "jms_filter_date"
        )
        || ""
      ).trim();

    if (globalDate) {
      params.set(
        "from_date",
        globalDate
      );

      params.set(
        "to_date",
        globalDate
      );
    }

    const response = await fetch(
      "/api/oee/results?" +
        params.toString(),
      {
        method: "GET",
        credentials: "same-origin"
      }
    );

    const data =
      await response.json();

    if (
      !response.ok ||
      !data.success
    ) {
      throw new Error(
        data.error ||
        "Unable to load OEE records."
      );
    }

    if (!oeeFiltersLoaded) {
      populateOeeFilters(
        data.filters || {}
      );
    }

    renderOeeSummary(
      data.summary || {}
    );

    renderOeeRows(
      data.data || []
    );

  } catch (error) {
    renderOeeSummary({
      entry_count: 0,
      avg_ar_ratio: null,
      avg_pr_ratio: null,
      avg_qr_ratio: null,
      avg_oee_ratio: null
    });

    if (table) {
      table.style.display = "none";
    }

    if (loading) {
      loading.style.display = "block";
      loading.textContent =
        error?.message ||
        "Unable to load OEE records.";
    }

    console.error(
      "OEE load failed:",
      error
    );
  }
}


function initOeePage() {
  const role = String(
    window.JMS_USER_ROLE || ""
  ).trim().toLowerCase();

  // Operator already receives only their own rows
  // from the backend, so operator filter is unnecessary.
  if (role === "operator") {
    const wrap = document.getElementById(
      "oee-operator-filter-wrap"
    );

    if (wrap) {
      wrap.style.display = "none";
    }
  }

  const apply =
    document.getElementById(
      "oee-apply-btn"
    );

  if (apply) {
    apply.addEventListener(
      "click",
      loadOeeResults
    );
  }

  const search =
    document.getElementById(
      "oee-search"
    );

  if (search) {
    search.addEventListener(
      "keydown",
      event => {
        if (event.key === "Enter") {
          loadOeeResults();
        }
      }
    );
  }

  loadOeeResults();
}


if (document.readyState === "loading") {
  document.addEventListener(
    "DOMContentLoaded",
    initOeePage
  );
} else {
  initOeePage();
}



// OEE_HIDE_LEGACY_DATE_FILTERS_V1
(function () {

  function hideLegacyOeeDateFilters() {

    [
      "oee-from-date",
      "oee-to-date"
    ].forEach(id => {

      const input =
        document.getElementById(id);

      if (!input) {
        return;
      }

      let container =
        input.parentElement;

      // Usually the date input is inside
      // its own filter-field wrapper.
      if (
        container
        && container.parentElement
      ) {
        const txt =
          (
            container.textContent
            || ""
          )
            .trim()
            .toLowerCase();

        if (
          txt.includes("from date")
          || txt.includes("to date")
          || txt === "from"
          || txt === "to"
        ) {
          container.style.display =
            "none";
        }
      }

      input.value = "";
    });
  }


  if (
    document.readyState === "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      hideLegacyOeeDateFilters
    );
  } else {
    hideLegacyOeeDateFilters();
  }

})();


