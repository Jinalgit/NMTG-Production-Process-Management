
(function () {
  "use strict";

  let users = [];

  // LOGIN_ACTIVITY_EXCEL_JS_V4
  let activeUserId = null;

  const body =
    document.getElementById(
      "login-activity-users-body"
    );

  const search =
    document.getElementById(
      "login-activity-search"
    );


  const fromDate =
    document.getElementById(
      "login-activity-from-date"
    );

  const toDate =
    document.getElementById(
      "login-activity-to-date"
    );

  const clearDates =
    document.getElementById(
      "login-activity-clear-dates"
    );


  const exportAllButton =
    document.getElementById(
      "login-activity-export-all"
    );

  const exportUserButton =
    document.getElementById(
      "login-activity-export-user"
    );


  function activityDateParams() {

    const params =
      new URLSearchParams();

    if (fromDate?.value) {
      params.set(
        "from_date",
        fromDate.value
      );
    }

    if (toDate?.value) {
      params.set(
        "to_date",
        toDate.value
      );
    }

    return params;
  }



  function buildExcelExportUrl(
    userId
  ) {

    const params =
      activityDateParams();


    if (userId) {

      params.set(
        "user_id",
        userId
      );

    } else {

      const searchValue =
        (search?.value || "")
        .trim();

      if (searchValue) {

        params.set(
          "search",
          searchValue
        );
      }
    }


    const query =
      params.toString();


    return (
      "/api/login-activity/export-excel"
      + (
        query
          ? "?" + query
          : ""
      )
    );
  }

  const modal =
    document.getElementById(
      "login-activity-modal"
    );

  const modalTitle =
    document.getElementById(
      "login-activity-modal-title"
    );

  const modalSubtitle =
    document.getElementById(
      "login-activity-modal-subtitle"
    );

  const detailLoading =
    document.getElementById(
      "login-activity-detail-loading"
    );

  const detailWrap =
    document.getElementById(
      "login-activity-detail-wrap"
    );

  const detailBody =
    document.getElementById(
      "login-activity-detail-body"
    );


  function roleLabel(role) {
    if (role === "plant_head") {
      return "Plant Head";
    }

    if (!role) {
      return "-";
    }

    return (
      role.charAt(0).toUpperCase()
      + role.slice(1)
    );
  }


  function makeTextCell(text, className) {
    const td =
      document.createElement("td");

    td.textContent =
      text === null
      || text === undefined
      || text === ""
        ? "-"
        : text;

    if (className) {
      td.className = className;
    }

    return td;
  }


  function renderUsers() {

    const query =
      (search?.value || "")
      .trim()
      .toLowerCase();

    const filtered =
      users.filter(function (user) {

        const haystack = [
          user.username,
          user.full_name,
          user.role,
        ]
          .join(" ")
          .toLowerCase();

        return !query
          || haystack.includes(query);
      });

    body.innerHTML = "";

    if (!filtered.length) {

      const tr =
        document.createElement("tr");

      const td =
        document.createElement("td");

      td.colSpan = 7;

      td.className =
        "login-activity-empty";

      td.textContent =
        "No users found.";

      tr.appendChild(td);
      body.appendChild(tr);

      return;
    }


    filtered.forEach(
      function (user) {

        const tr =
          document.createElement("tr");

        tr.appendChild(
          makeTextCell(
            user.username,
            "login-activity-user"
          )
        );

        tr.appendChild(
          makeTextCell(
            user.full_name
          )
        );

        tr.appendChild(
          makeTextCell(
            roleLabel(user.role),
            "login-activity-role"
          )
        );

        tr.appendChild(
          makeTextCell(
            user.last_login_display
          )
        );

        tr.appendChild(
          makeTextCell(
            user.login_count ?? 0,
            "login-activity-count"
          )
        );


        const statusTd =
          document.createElement("td");

        const status =
          document.createElement("span");

        const isOnline =
          user.login_status === "Online";

        status.textContent =
          isOnline
            ? "Online"
            : "Offline";

        status.className =
          isOnline
            ? "login-activity-login-online"
            : "login-activity-login-offline";

        statusTd.appendChild(status);

        tr.appendChild(statusTd);


        const actionTd =
          document.createElement("td");

        const button =
          document.createElement("button");

        button.type = "button";

        button.className =
          "login-activity-btn";

        button.textContent =
          "View Activity";

        button.addEventListener(
          "click",
          function () {
            openActivity(
              user.id
            );
          }
        );

        actionTd.appendChild(button);

        tr.appendChild(actionTd);

        body.appendChild(tr);
      }
    );
  }


  async function loadUsers() {

    try {

      const params =
        activityDateParams();

      const query =
        params.toString();

      const response =
        await fetch(
          "/api/login-activity/users"
          + (query ? "?" + query : ""),
          {
            credentials: "same-origin",
          }
        );

      const data =
        await response.json();

      if (
        !response.ok
        || !data.success
      ) {
        throw new Error(
          data.error
          || "Unable to load users."
        );
      }

      users =
        data.users || [];

      renderUsers();

    } catch (error) {

      body.innerHTML = "";

      const tr =
        document.createElement("tr");

      const td =
        document.createElement("td");

      td.colSpan = 7;

      td.className =
        "login-activity-empty";

      td.textContent =
        error.message
        || "Unable to load users.";

      tr.appendChild(td);
      body.appendChild(tr);
    }
  }


  function statusClass(status) {

    if (status === "Active") {
      return (
        "login-status "
        + "login-status-active"
      );
    }

    if (status === "Logged Out") {
      return (
        "login-status "
        + "login-status-logged-out"
      );
    }

    return (
      "login-status "
      + "login-status-session-ended"
    );
  }


  async function openActivity(userId) {

    activeUserId = userId;

    modal.hidden = false;

    detailLoading.hidden = false;

    detailLoading.textContent =
      "Loading activity...";

    detailWrap.hidden = true;

    detailBody.innerHTML = "";

    modalTitle.textContent =
      "Login Activity";

    modalSubtitle.textContent =
      "";


    try {

      const params =
        activityDateParams();

      const query =
        params.toString();

      const response =
        await fetch(
          "/api/login-activity/users/"
          + encodeURIComponent(userId)
          + (query ? "?" + query : ""),
          {
            credentials: "same-origin",
          }
        );

      const data =
        await response.json();

      if (
        !response.ok
        || !data.success
      ) {
        throw new Error(
          data.error
          || "Unable to load activity."
        );
      }


      const user =
        data.user;

      modalTitle.textContent =
        user.username
        + " - Login Activity";

      const subtitleParts = [];

      if (user.full_name) {
        subtitleParts.push(
          user.full_name
        );
      }

      subtitleParts.push(
        roleLabel(user.role)
      );

      subtitleParts.push(
        "Last Login: "
        + user.last_login_display
      );

      modalSubtitle.textContent =
        subtitleParts.join(" | ");


      detailLoading.hidden = true;

      detailWrap.hidden = false;


      const rows =
        data.activity || [];

      if (!rows.length) {

        const tr =
          document.createElement("tr");

        const td =
          document.createElement("td");

        td.colSpan = 6;

        td.className =
          "login-activity-empty";

        td.textContent =
          "No login activity recorded for this user.";

        tr.appendChild(td);

        detailBody.appendChild(tr);

        return;
      }


      rows.forEach(
        function (row) {

          const tr =
            document.createElement("tr");

          tr.appendChild(
            makeTextCell(
              row.device_name
            )
          );

          tr.appendChild(
            makeTextCell(
              row.ip_address
            )
          );

          tr.appendChild(
            makeTextCell(
              row.login_at_display
            )
          );

          tr.appendChild(
            makeTextCell(
              row.last_seen_at_display
            )
          );

          tr.appendChild(
            makeTextCell(
              row.logout_at_display
            )
          );


          const statusTd =
            document.createElement("td");

          const badge =
            document.createElement("span");

          badge.textContent =
            row.status;

          badge.className =
            statusClass(
              row.status
            );

          statusTd.appendChild(
            badge
          );

          tr.appendChild(
            statusTd
          );

          detailBody.appendChild(
            tr
          );
        }
      );


    } catch (error) {

      detailWrap.hidden = true;

      detailLoading.hidden = false;

      detailLoading.textContent =
        error.message
        || "Unable to load activity.";
    }
  }


  function closeActivity() {
    modal.hidden = true;
    activeUserId = null;
  }


  document
    .querySelectorAll(
      "[data-close-login-activity]"
    )
    .forEach(
      function (element) {

        element.addEventListener(
          "click",
          closeActivity
        );
      }
    );


  document.addEventListener(
    "keydown",
    function (event) {

      if (
        event.key === "Escape"
        && !modal.hidden
      ) {
        closeActivity();
      }
    }
  );


  if (search) {
    search.addEventListener(
      "input",
      renderUsers
    );
  }


  if (fromDate) {
    fromDate.addEventListener(
      "change",
      loadUsers
    );
  }


  if (toDate) {
    toDate.addEventListener(
      "change",
      loadUsers
    );
  }


  if (clearDates) {
    clearDates.addEventListener(
      "click",
      function () {

        if (fromDate) {
          fromDate.value = "";
        }

        if (toDate) {
          toDate.value = "";
        }

        loadUsers();
      }
    );
  }


  if (exportAllButton) {

    exportAllButton.addEventListener(
      "click",
      function () {

        window.location.href =
          buildExcelExportUrl(
            null
          );
      }
    );
  }


  if (exportUserButton) {

    exportUserButton.addEventListener(
      "click",
      function () {

        if (!activeUserId) {
          return;
        }

        window.location.href =
          buildExcelExportUrl(
            activeUserId
          );
      }
    );
  }


  loadUsers();

})();
