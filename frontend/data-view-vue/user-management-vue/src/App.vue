<script setup>
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref
} from "vue";


/* ============================================================
   DATA
============================================================ */

const users = ref([]);
const loading = ref(true);
const loadError = ref("");

const searchText = ref("");

const roleFilter = ref("");
const statusFilter = ref("");

const groupBy = ref("");
const sortBy = ref("name");

const openMenu = ref("");

const visibleMeta = ref({
  processes: true,
  pages: true,
  lastLogin: true
});

const selectedIds = ref([]);

const editorOpen = ref(false);
const editorTab = ref("details");
const selectedUser = ref(null);

const editorDraft = ref({
  full_name: "",
  role: "",
  is_active: true
});

const permissionLoading = ref(false);
const permissionError = ref("");

const permissions = ref({
  processes: [],
  pages: [],
  fields: []
});

const newUserOpen = ref(false);

const newUserDraft = ref({
  username: "",
  full_name: "",
  role: "Operator"
});

const toast = ref({
  show: false,
  text: ""
});

let toastTimer = null;


/* ============================================================
   HELPERS
============================================================ */

function clean(value) {
  return String(value ?? "").trim();
}

function lower(value) {
  return clean(value).toLowerCase();
}

function isActive(user) {
  return Number(user?.is_active) === 1;
}

function roleLabel(role) {
  const value = lower(role);

  if (value === "admin") {
    return "Admin";
  }

  if (value === "supervisor") {
    return "Supervisor";
  }

  if (value === "operator") {
    return "Operator";
  }

  return clean(role) || "-";
}

function initials(user) {
  const source =
    clean(user?.full_name) ||
    clean(user?.username) ||
    "U";

  return source
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(
      (part) =>
        part.charAt(0).toUpperCase()
    )
    .join("");
}

function formatDate(value) {
  const text = clean(value);

  if (!text) {
    return "-";
  }

  const date = new Date(text);

  if (Number.isNaN(date.getTime())) {
    return text;
  }

  return new Intl.DateTimeFormat(
    "en-IN",
    {
      day: "2-digit",
      month: "short",
      year: "numeric"
    }
  ).format(date);
}

function formatLastLogin(value) {
  const text = clean(value);

  if (!text) {
    return "Never";
  }

  const date = new Date(text);

  if (Number.isNaN(date.getTime())) {
    return text;
  }

  const now = new Date();

  const today =
    new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate()
    );

  const target =
    new Date(
      date.getFullYear(),
      date.getMonth(),
      date.getDate()
    );

  const diff =
    Math.round(
      (today - target) /
      86400000
    );

  if (diff === 0) {
    return new Intl.DateTimeFormat(
      "en-IN",
      {
        hour: "2-digit",
        minute: "2-digit"
      }
    ).format(date);
  }

  if (diff === 1) {
    return "Yesterday";
  }

  if (diff > 1 && diff <= 7) {
    return `${diff} days ago`;
  }

  return formatDate(value);
}

function permissionName(value) {
  return clean(value)
    .replace(/_/g, " ")
    .replace(
      /\b\w/g,
      (letter) => letter.toUpperCase()
    );
}

function pageLabel(page) {
  return (
    clean(page?.label) ||
    permissionName(page?.page_name) ||
    "-"
  );
}

function fieldLabel(field) {
  const page =
    permissionName(
      field?.page_name
    );

  const fieldName =
    clean(field?.label) ||
    permissionName(
      field?.field_name
    );

  if (page && fieldName) {
    return `${page} / ${fieldName}`;
  }

  return fieldName || page || "-";
}

function processLabel(process) {
  if (
    process &&
    typeof process === "object"
  ) {
    return (
      clean(process.name) ||
      clean(process.process_name) ||
      clean(process.label) ||
      clean(process.process) ||
      "-"
    );
  }

  return clean(process) || "-";
}

function showToast(text) {
  toast.value = {
    show: true,
    text
  };

  if (toastTimer) {
    clearTimeout(toastTimer);
  }

  toastTimer =
    window.setTimeout(
      () => {
        toast.value.show = false;
      },
      2300
    );
}

function toggleMenu(menu) {
  openMenu.value =
    openMenu.value === menu
      ? ""
      : menu;
}

function closeMenus() {
  openMenu.value = "";
}


/* ============================================================
   API
============================================================ */

async function readJson(response) {
  let data = null;

  try {
    data = await response.json();
  } catch (error) {
    throw new Error(
      "Server returned an invalid response."
    );
  }

  if (
    !response.ok ||
    !data?.success
  ) {
    throw new Error(
      data?.error ||
      "Request failed."
    );
  }

  return data;
}

async function loadUsers() {
  loading.value = true;
  loadError.value = "";

  try {
    const response =
      await fetch(
        "/api/users",
        {
          headers: {
            Accept:
              "application/json"
          }
        }
      );

    const data =
      await readJson(response);

    users.value =
      Array.isArray(data.users)
        ? data.users
        : [];

  } catch (error) {
    loadError.value =
      error?.message ||
      "Could not load users.";

  } finally {
    loading.value = false;
  }
}

async function loadPermissions(userId) {
  permissionLoading.value = true;
  permissionError.value = "";

  permissions.value = {
    processes: [],
    pages: [],
    fields: []
  };

  try {
    const response =
      await fetch(
        `/api/user-management/permissions/${userId}`,
        {
          headers: {
            Accept:
              "application/json"
          }
        }
      );

    const data =
      await readJson(response);

    permissions.value = {
      processes:
        Array.isArray(data.processes)
          ? data.processes
          : [],

      pages:
        Array.isArray(data.pages)
          ? data.pages
          : [],

      fields:
        Array.isArray(data.fields)
          ? data.fields
          : []
    };

  } catch (error) {
    permissionError.value =
      error?.message ||
      "Could not load permissions.";

  } finally {
    permissionLoading.value = false;
  }
}


/* ============================================================
   FILTER / SORT / GROUP
============================================================ */

const filteredUsers = computed(() => {
  const query =
    lower(searchText.value);

  let result =
    users.value.filter(
      (user) => {
        if (
          roleFilter.value &&
          lower(user.role) !==
            lower(roleFilter.value)
        ) {
          return false;
        }

        if (
          statusFilter.value ===
            "active" &&
          !isActive(user)
        ) {
          return false;
        }

        if (
          statusFilter.value ===
            "inactive" &&
          isActive(user)
        ) {
          return false;
        }

        if (!query) {
          return true;
        }

        const haystack =
          [
            user.username,
            user.full_name,
            user.role
          ]
            .map(lower)
            .join(" ");

        return haystack.includes(
          query
        );
      }
    );


  result =
    [...result].sort(
      (a, b) => {
        if (sortBy.value === "username") {
          return clean(a.username)
            .localeCompare(
              clean(b.username)
            );
        }

        if (sortBy.value === "role") {
          return roleLabel(a.role)
            .localeCompare(
              roleLabel(b.role)
            );
        }

        if (sortBy.value === "status") {
          return Number(
            isActive(b)
          ) -
          Number(
            isActive(a)
          );
        }

        if (sortBy.value === "login") {
          const aDate =
            new Date(
              a.last_login || 0
            ).getTime();

          const bDate =
            new Date(
              b.last_login || 0
            ).getTime();

          return bDate - aDate;
        }

        return (
          clean(a.full_name) ||
          clean(a.username)
        ).localeCompare(
          clean(b.full_name) ||
          clean(b.username)
        );
      }
    );

  return result;
});


const displayGroups = computed(() => {
  if (groupBy.value !== "role") {
    return [
      {
        key: "all",
        title: "",
        users:
          filteredUsers.value
      }
    ];
  }

  const groups = {};

  filteredUsers.value.forEach(
    (user) => {
      const role =
        roleLabel(user.role);

      if (!groups[role]) {
        groups[role] = [];
      }

      groups[role].push(user);
    }
  );

  return Object.keys(groups)
    .sort()
    .map(
      (key) => ({
        key,
        title: key,
        users: groups[key]
      })
    );
});


const activeFilterCount = computed(() => {
  let count = 0;

  if (roleFilter.value) {
    count += 1;
  }

  if (statusFilter.value) {
    count += 1;
  }

  return count;
});


function clearFilters() {
  roleFilter.value = "";
  statusFilter.value = "";
  closeMenus();
}


/* ============================================================
   SELECTION
============================================================ */

function isSelected(id) {
  return selectedIds.value.includes(
    id
  );
}

function toggleSelected(id) {
  if (isSelected(id)) {
    selectedIds.value =
      selectedIds.value.filter(
        (item) => item !== id
      );
  } else {
    selectedIds.value = [
      ...selectedIds.value,
      id
    ];
  }
}

const allVisibleSelected =
  computed(() => {
    const ids =
      filteredUsers.value.map(
        (user) => user.id
      );

    return (
      ids.length > 0 &&
      ids.every(
        (id) =>
          selectedIds.value.includes(
            id
          )
      )
    );
  });

function toggleAllVisible() {
  const ids =
    filteredUsers.value.map(
      (user) => user.id
    );

  if (allVisibleSelected.value) {
    selectedIds.value =
      selectedIds.value.filter(
        (id) =>
          !ids.includes(id)
      );
  } else {
    selectedIds.value =
      Array.from(
        new Set([
          ...selectedIds.value,
          ...ids
        ])
      );
  }
}

function clearSelection() {
  selectedIds.value = [];
}

function reviewSelected() {
  const firstId =
    selectedIds.value[0];

  if (!firstId) {
    return;
  }

  const user =
    users.value.find(
      (item) =>
        item.id === firstId
    );

  if (user) {
    openEditor(user);
  }
}


/* ============================================================
   EDITOR
============================================================ */

function openEditor(
  user,
  tab = "details"
) {
  selectedUser.value = user;

  editorDraft.value = {
    full_name:
      clean(user.full_name),

    role:
      roleLabel(user.role),

    is_active:
      isActive(user)
  };

  editorTab.value = tab;
  editorOpen.value = true;
  closeMenus();

  loadPermissions(user.id);
}

function closeEditor() {
  editorOpen.value = false;
}

function discardEditorChanges() {
  if (!selectedUser.value) {
    return;
  }

  editorDraft.value = {
    full_name:
      clean(
        selectedUser.value.full_name
      ),

    role:
      roleLabel(
        selectedUser.value.role
      ),

    is_active:
      isActive(
        selectedUser.value
      )
  };

  showToast(
    "Draft changes discarded"
  );
}

const editorDirty = computed(() => {
  if (!selectedUser.value) {
    return false;
  }

  return (
    clean(editorDraft.value.full_name) !==
      clean(
        selectedUser.value.full_name
      )
    ||
    lower(editorDraft.value.role) !==
      lower(
        selectedUser.value.role
      )
    ||
    Boolean(
      editorDraft.value.is_active
    ) !==
      isActive(
        selectedUser.value
      )
  );
});

function previewSave() {
  showToast(
    "UI approved first — save connection comes next"
  );
}


/* ============================================================
   PERMISSION COMPUTED
============================================================ */

const grantedPages = computed(() => {
  return (
    permissions.value.pages || []
  ).filter(
    (item) =>
      Number(
        item.can_access
      ) === 1
  );
});

const editableFields = computed(() => {
  return (
    permissions.value.fields || []
  ).filter(
    (item) =>
      Number(
        item.can_edit
      ) === 1
  );
});


/* ============================================================
   NEW USER PREVIEW
============================================================ */

function openNewUser() {
  newUserDraft.value = {
    username: "",
    full_name: "",
    role: "Operator"
  };

  newUserOpen.value = true;
  closeMenus();
}

function previewCreateUser() {
  showToast(
    "Create User will be connected after UI approval"
  );
}


/* ============================================================
   GLOBAL KEYBOARD
============================================================ */

function handleKeydown(event) {
  if (event.key !== "Escape") {
    return;
  }

  if (newUserOpen.value) {
    newUserOpen.value = false;
    return;
  }

  if (editorOpen.value) {
    closeEditor();
    return;
  }

  closeMenus();
}


onMounted(() => {
  loadUsers();

  window.addEventListener(
    "keydown",
    handleKeydown
  );
});


onBeforeUnmount(() => {
  window.removeEventListener(
    "keydown",
    handleKeydown
  );

  if (toastTimer) {
    clearTimeout(toastTimer);
  }
});
</script>


<template>
  <div
    class="um2-page"
    @click.self="closeMenus"
  >

    <!-- ======================================================
         PAGE HEADER
    ======================================================= -->

    <header class="um2-header">

      <div class="um2-header-left">

        <div class="um2-breadcrumb">
          <a href="/welcome">
            <i
              class="fa fa-home"
              aria-hidden="true"
            ></i>
          </a>

          <i
            class="fa fa-angle-right"
            aria-hidden="true"
          ></i>

          <span>
            Administration
          </span>

          <i
            class="fa fa-angle-right"
            aria-hidden="true"
          ></i>

          <strong>
            Users
          </strong>
        </div>


        <div class="um2-title-line">
          <h1>
            Users
          </h1>

          <span class="um2-title-count">
            {{ users.length }}
          </span>
        </div>

        <p>
          Manage users, roles and system access.
        </p>

      </div>


      <button
        type="button"
        class="um2-btn um2-btn-primary"
        @click="openNewUser"
      >
        <i
          class="fa fa-plus"
          aria-hidden="true"
        ></i>

        New User
      </button>

    </header>


    <!-- ======================================================
         TOOLBAR
    ======================================================= -->

    <section class="um2-command-bar">

      <div class="um2-search">

        <i
          class="fa fa-search"
          aria-hidden="true"
        ></i>

        <input
          v-model="searchText"
          type="search"
          placeholder="Search users..."
          autocomplete="off"
        />

        <kbd v-if="!searchText">
          /
        </kbd>

      </div>


      <!-- FILTER -->

      <div class="um2-menu-wrap">

        <button
          type="button"
          class="um2-command-btn"
          :class="{
            active:
              openMenu === 'filter' ||
              activeFilterCount
          }"
          @click.stop="toggleMenu('filter')"
        >
          <i
            class="fa fa-filter"
            aria-hidden="true"
          ></i>

          Filter

          <span
            v-if="activeFilterCount"
            class="um2-count-dot"
          >
            {{ activeFilterCount }}
          </span>
        </button>


        <div
          v-if="openMenu === 'filter'"
          class="um2-popover um2-filter-popover"
          @click.stop
        >

          <div class="um2-popover-title">
            Filter Users
          </div>


          <label class="um2-field">
            <span>
              Role
            </span>

            <select v-model="roleFilter">
              <option value="">
                All Roles
              </option>

              <option value="Admin">
                Admin
              </option>

              <option value="Supervisor">
                Supervisor
              </option>

              <option value="Operator">
                Operator
              </option>
            </select>
          </label>


          <label class="um2-field">
            <span>
              Status
            </span>

            <select v-model="statusFilter">
              <option value="">
                All Status
              </option>

              <option value="active">
                Active
              </option>

              <option value="inactive">
                Inactive
              </option>
            </select>
          </label>


          <div class="um2-popover-footer">

            <button
              type="button"
              class="um2-link-btn"
              @click="clearFilters"
            >
              Clear
            </button>

            <button
              type="button"
              class="um2-btn um2-btn-small"
              @click="closeMenus"
            >
              Apply
            </button>

          </div>

        </div>

      </div>


      <!-- GROUP BY -->

      <div class="um2-menu-wrap">

        <button
          type="button"
          class="um2-command-btn"
          :class="{
            active:
              openMenu === 'group' ||
              groupBy
          }"
          @click.stop="toggleMenu('group')"
        >
          <i
            class="fa fa-layer-group"
            aria-hidden="true"
          ></i>

          Group By

          <i
            class="fa fa-angle-down"
            aria-hidden="true"
          ></i>
        </button>


        <div
          v-if="openMenu === 'group'"
          class="um2-popover um2-choice-popover"
          @click.stop
        >

          <button
            type="button"
            :class="{
              selected:
                groupBy === ''
            }"
            @click="
              groupBy = '';
              closeMenus()
            "
          >
            <i
              class="fa fa-list"
              aria-hidden="true"
            ></i>

            No grouping
          </button>


          <button
            type="button"
            :class="{
              selected:
                groupBy === 'role'
            }"
            @click="
              groupBy = 'role';
              closeMenus()
            "
          >
            <i
              class="fa fa-users"
              aria-hidden="true"
            ></i>

            Role
          </button>

        </div>

      </div>


      <!-- SORT -->

      <div class="um2-menu-wrap">

        <button
          type="button"
          class="um2-command-btn"
          :class="{
            active:
              openMenu === 'sort'
          }"
          @click.stop="toggleMenu('sort')"
        >
          <i
            class="fa fa-sort-amount-asc"
            aria-hidden="true"
          ></i>

          Sort

          <i
            class="fa fa-angle-down"
            aria-hidden="true"
          ></i>
        </button>


        <div
          v-if="openMenu === 'sort'"
          class="um2-popover um2-choice-popover"
          @click.stop
        >

          <button
            v-for="option in [
              ['name', 'Full Name'],
              ['username', 'Username'],
              ['role', 'Role'],
              ['status', 'Status'],
              ['login', 'Last Login']
            ]"
            :key="option[0]"
            type="button"
            :class="{
              selected:
                sortBy === option[0]
            }"
            @click="
              sortBy = option[0];
              closeMenus()
            "
          >
            <i
              v-if="sortBy === option[0]"
              class="fa fa-check"
              aria-hidden="true"
            ></i>

            <span
              v-else
              class="um2-menu-icon-space"
            ></span>

            {{ option[1] }}
          </button>

        </div>

      </div>


      <!-- COLUMNS -->

      <div class="um2-menu-wrap">

        <button
          type="button"
          class="um2-command-btn"
          :class="{
            active:
              openMenu === 'columns'
          }"
          @click.stop="toggleMenu('columns')"
        >
          <i
            class="fa fa-columns"
            aria-hidden="true"
          ></i>

          Columns
        </button>


        <div
          v-if="openMenu === 'columns'"
          class="um2-popover um2-columns-popover"
          @click.stop
        >

          <div class="um2-popover-title">
            Row Information
          </div>


          <label>
            <input
              v-model="visibleMeta.processes"
              type="checkbox"
            />

            Process Access
          </label>


          <label>
            <input
              v-model="visibleMeta.pages"
              type="checkbox"
            />

            Page Access
          </label>


          <label>
            <input
              v-model="visibleMeta.lastLogin"
              type="checkbox"
            />

            Last Login
          </label>

        </div>

      </div>


      <div class="um2-toolbar-spacer"></div>


      <button
        type="button"
        class="um2-icon-btn"
        title="Refresh"
        :disabled="loading"
        @click="loadUsers"
      >
        <i
          class="fa fa-refresh"
          :class="{
            'fa-spin':
              loading
          }"
          aria-hidden="true"
        ></i>
      </button>

    </section>


    <!-- ======================================================
         ACTIVE FILTER CHIPS
    ======================================================= -->

    <div
      v-if="
        roleFilter ||
        statusFilter
      "
      class="um2-active-filters"
    >

      <span>
        Filters:
      </span>


      <button
        v-if="roleFilter"
        type="button"
        @click="roleFilter = ''"
      >
        Role:
        <strong>
          {{ roleFilter }}
        </strong>

        <i
          class="fa fa-times"
          aria-hidden="true"
        ></i>
      </button>


      <button
        v-if="statusFilter"
        type="button"
        @click="statusFilter = ''"
      >
        Status:
        <strong>
          {{
            statusFilter === 'active'
              ? 'Active'
              : 'Inactive'
          }}
        </strong>

        <i
          class="fa fa-times"
          aria-hidden="true"
        ></i>
      </button>


      <button
        type="button"
        class="um2-clear-filter"
        @click="clearFilters"
      >
        Clear all
      </button>

    </div>


    <!-- ======================================================
         BULK SELECTION BAR
    ======================================================= -->

    <div
      v-if="selectedIds.length"
      class="um2-selection-bar"
    >

      <button
        type="button"
        class="um2-selection-close"
        @click="clearSelection"
      >
        <i
          class="fa fa-times"
          aria-hidden="true"
        ></i>
      </button>


      <strong>
        {{ selectedIds.length }}
        selected
      </strong>


      <div class="um2-selection-spacer"></div>


      <button
        type="button"
        class="um2-btn um2-btn-small"
        @click="reviewSelected"
      >
        Review Access
      </button>

    </div>


    <!-- ======================================================
         LIST VIEW
    ======================================================= -->

    <section class="um2-list-shell">

      <div class="um2-list-head">

        <label class="um2-check">
          <input
            type="checkbox"
            :checked="allVisibleSelected"
            @change="toggleAllVisible"
          />

          <span></span>
        </label>


        <span>
          User
        </span>


        <span>
          Access
        </span>


        <span>
          Status
        </span>


        <span class="um2-head-actions">
          {{ filteredUsers.length }}
          record{{ filteredUsers.length === 1 ? '' : 's' }}
        </span>

      </div>


      <!-- ERROR -->

      <div
        v-if="loadError"
        class="um2-state um2-state-error"
      >
        <i
          class="fa fa-exclamation-circle"
          aria-hidden="true"
        ></i>

        <h3>
          Could not load users
        </h3>

        <p>
          {{ loadError }}
        </p>

        <button
          type="button"
          class="um2-btn"
          @click="loadUsers"
        >
          Retry
        </button>
      </div>


      <!-- LOADING -->

      <div
        v-else-if="loading"
        class="um2-loading"
      >
        <div
          v-for="index in 7"
          :key="index"
          class="um2-skeleton"
        >
          <span></span>
          <span></span>
          <span></span>
          <span></span>
        </div>
      </div>


      <!-- EMPTY -->

      <div
        v-else-if="!filteredUsers.length"
        class="um2-state"
      >
        <div class="um2-empty-icon">
          <i
            class="fa fa-search"
            aria-hidden="true"
          ></i>
        </div>

        <h3>
          No users found
        </h3>

        <p>
          Try changing your search or filters.
        </p>
      </div>


      <!-- GROUPS -->

      <template v-else>

        <section
          v-for="group in displayGroups"
          :key="group.key"
          class="um2-group"
        >

          <div
            v-if="group.title"
            class="um2-group-heading"
          >
            <span>
              {{ group.title }}
            </span>

            <strong>
              {{ group.users.length }}
            </strong>
          </div>


          <article
            v-for="user in group.users"
            :key="user.id"
            class="um2-user-row"
            :class="{
              selected:
                isSelected(user.id)
            }"
            tabindex="0"
            @click="openEditor(user)"
            @keydown.enter="openEditor(user)"
          >

            <!-- SELECT -->

            <div
              class="um2-row-select"
              @click.stop
            >
              <label class="um2-check">
                <input
                  type="checkbox"
                  :checked="
                    isSelected(user.id)
                  "
                  @change="
                    toggleSelected(user.id)
                  "
                />

                <span></span>
              </label>
            </div>


            <!-- USER IDENTITY -->

            <div class="um2-user-main">

              <div class="um2-mini-avatar">
                {{ initials(user) }}
              </div>


              <div class="um2-user-text">

                <div class="um2-user-primary">

                  <strong>
                    {{
                      user.full_name ||
                      user.username
                    }}
                  </strong>


                  <span
                    class="um2-role-pill"
                    :class="
                      `role-${lower(user.role)}`
                    "
                  >
                    {{ roleLabel(user.role) }}
                  </span>

                </div>


                <div class="um2-username">
                  @{{ user.username }}
                </div>


                <div class="um2-user-mobile-status">

                  <span
                    class="um2-status"
                    :class="
                      isActive(user)
                        ? 'active'
                        : 'inactive'
                    "
                  >
                    <span></span>

                    {{
                      isActive(user)
                        ? 'Active'
                        : 'Inactive'
                    }}
                  </span>

                </div>

              </div>

            </div>


            <!-- ACCESS INFO -->

            <div class="um2-access-summary">

              <div
                v-if="visibleMeta.processes"
                class="um2-access-line"
              >
                <i
                  class="fa fa-cogs"
                  aria-hidden="true"
                ></i>

                <span>
                  Process access
                </span>
              </div>


              <div
                v-if="visibleMeta.pages"
                class="um2-access-line"
              >
                <i
                  class="fa fa-key"
                  aria-hidden="true"
                ></i>

                <span>
                  Click to review permissions
                </span>
              </div>


              <div
                v-if="visibleMeta.lastLogin"
                class="um2-access-line um2-mobile-last-login"
              >
                <i
                  class="fa fa-clock-o"
                  aria-hidden="true"
                ></i>

                <span>
                  {{ formatLastLogin(user.last_login) }}
                </span>
              </div>

            </div>


            <!-- STATUS -->

            <div class="um2-row-status">

              <span
                class="um2-status"
                :class="
                  isActive(user)
                    ? 'active'
                    : 'inactive'
                "
              >
                <span></span>

                {{
                  isActive(user)
                    ? 'Active'
                    : 'Inactive'
                }}
              </span>


              <small
                v-if="visibleMeta.lastLogin"
              >
                Last login

                <strong>
                  {{
                    formatLastLogin(
                      user.last_login
                    )
                  }}
                </strong>
              </small>

            </div>


            <!-- HOVER ACTIONS -->

            <div
              class="um2-row-actions"
              @click.stop
            >

              <button
                type="button"
                title="Edit user"
                @click="
                  openEditor(
                    user,
                    'details'
                  )
                "
              >
                <i
                  class="fa fa-pencil"
                  aria-hidden="true"
                ></i>

                Edit
              </button>


              <button
                type="button"
                title="Permissions"
                @click="
                  openEditor(
                    user,
                    'permissions'
                  )
                "
              >
                <i
                  class="fa fa-key"
                  aria-hidden="true"
                ></i>

                Access
              </button>


              <button
                type="button"
                class="um2-chevron"
                title="Open"
                @click="openEditor(user)"
              >
                <i
                  class="fa fa-chevron-right"
                  aria-hidden="true"
                ></i>
              </button>

            </div>

          </article>

        </section>

      </template>

    </section>


    <!-- ======================================================
         EDITOR OVERLAY
    ======================================================= -->

    <div
      class="um2-overlay"
      :class="{
        open:
          editorOpen
      }"
      @click="closeEditor"
    ></div>


    <!-- ======================================================
         USER EDITOR
    ======================================================= -->

    <aside
      class="um2-editor"
      :class="{
        open:
          editorOpen
      }"
    >

      <template v-if="selectedUser">

        <header class="um2-editor-header">

          <div class="um2-editor-heading">

            <div class="um2-editor-avatar">
              {{ initials(selectedUser) }}
            </div>


            <div>

              <div class="um2-editor-name-line">

                <h2>
                  {{
                    selectedUser.full_name ||
                    selectedUser.username
                  }}
                </h2>


                <span
                  class="um2-status"
                  :class="
                    editorDraft.is_active
                      ? 'active'
                      : 'inactive'
                  "
                >
                  <span></span>

                  {{
                    editorDraft.is_active
                      ? 'Active'
                      : 'Inactive'
                  }}
                </span>

              </div>


              <p>
                @{{ selectedUser.username }}
                ·
                {{ roleLabel(selectedUser.role) }}
              </p>

            </div>

          </div>


          <button
            type="button"
            class="um2-editor-close"
            @click="closeEditor"
          >
            <i
              class="fa fa-times"
              aria-hidden="true"
            ></i>
          </button>

        </header>


        <div
          v-if="editorDirty"
          class="um2-unsaved"
        >
          <span class="um2-unsaved-dot"></span>

          Unsaved changes

          <button
            type="button"
            @click="discardEditorChanges"
          >
            Discard
          </button>
        </div>


        <!-- TABS -->

        <nav class="um2-editor-tabs">

          <button
            type="button"
            :class="{
              active:
                editorTab === 'details'
            }"
            @click="editorTab = 'details'"
          >
            Details
          </button>


          <button
            type="button"
            :class="{
              active:
                editorTab === 'permissions'
            }"
            @click="editorTab = 'permissions'"
          >
            Permissions
          </button>


          <button
            type="button"
            :class="{
              active:
                editorTab === 'processes'
            }"
            @click="editorTab = 'processes'"
          >
            Processes
          </button>


          <button
            type="button"
            :class="{
              active:
                editorTab === 'activity'
            }"
            @click="editorTab = 'activity'"
          >
            Activity
          </button>

        </nav>


        <div class="um2-editor-body">

          <!-- ================================================
               DETAILS
          ================================================= -->

          <section
            v-if="editorTab === 'details'"
            class="um2-editor-section"
          >

            <div class="um2-section-title">
              <div>
                <h3>
                  Account Details
                </h3>

                <p>
                  Basic user information and account status.
                </p>
              </div>
            </div>


            <div class="um2-form-grid">

              <label class="um2-field">
                <span>
                  Username
                </span>

                <input
                  :value="selectedUser.username"
                  type="text"
                  disabled
                />

                <small>
                  Username cannot be changed here.
                </small>
              </label>


              <label class="um2-field">
                <span>
                  Full Name
                </span>

                <input
                  v-model="editorDraft.full_name"
                  type="text"
                />
              </label>


              <label class="um2-field">
                <span>
                  Role
                </span>

                <select v-model="editorDraft.role">
                  <option>
                    Admin
                  </option>

                  <option>
                    Supervisor
                  </option>

                  <option>
                    Operator
                  </option>
                </select>
              </label>


              <div class="um2-field">
                <span>
                  Status
                </span>

                <button
                  type="button"
                  class="um2-status-toggle"
                  :class="{
                    on:
                      editorDraft.is_active
                  }"
                  @click="
                    editorDraft.is_active =
                      !editorDraft.is_active
                  "
                >
                  <span class="um2-switch">
                    <i></i>
                  </span>

                  <strong>
                    {{
                      editorDraft.is_active
                        ? 'Active'
                        : 'Inactive'
                    }}
                  </strong>
                </button>
              </div>

            </div>


            <div class="um2-form-separator"></div>


            <div class="um2-section-title compact">

              <div>
                <h3>
                  Account Information
                </h3>
              </div>

            </div>


            <div class="um2-info-grid">

              <div>
                <span>
                  Created
                </span>

                <strong>
                  {{
                    formatDate(
                      selectedUser.created_at
                    )
                  }}
                </strong>
              </div>


              <div>
                <span>
                  Last Login
                </span>

                <strong>
                  {{
                    formatLastLogin(
                      selectedUser.last_login
                    )
                  }}
                </strong>
              </div>


              <div>
                <span>
                  User ID
                </span>

                <strong>
                  {{ selectedUser.id }}
                </strong>
              </div>

            </div>

          </section>


          <!-- ================================================
               PERMISSIONS
          ================================================= -->

          <section
            v-else-if="
              editorTab === 'permissions'
            "
            class="um2-editor-section"
          >

            <div class="um2-section-title">

              <div>
                <h3>
                  Page Access
                </h3>

                <p>
                  Current page permissions for this user.
                </p>
              </div>


              <span class="um2-section-count">
                {{ grantedPages.length }}
              </span>

            </div>


            <div
              v-if="permissionLoading"
              class="um2-inline-loading"
            >
              <i
                class="fa fa-circle-o-notch fa-spin"
                aria-hidden="true"
              ></i>

              Loading permissions...
            </div>


            <div
              v-else-if="permissionError"
              class="um2-inline-error"
            >
              {{ permissionError }}
            </div>


            <template v-else>

              <div
                v-if="permissions.pages.length"
                class="um2-permission-matrix"
              >

                <div class="um2-matrix-head">
                  <span>
                    Page
                  </span>

                  <span>
                    Access
                  </span>
                </div>


                <div
                  v-for="page in permissions.pages"
                  :key="page.page_name"
                  class="um2-matrix-row"
                >

                  <div>
                    <strong>
                      {{ pageLabel(page) }}
                    </strong>

                    <small>
                      {{ page.page_name }}
                    </small>
                  </div>


                  <span
                    class="um2-access-state"
                    :class="{
                      granted:
                        Number(
                          page.can_access
                        ) === 1
                    }"
                  >
                    <i
                      :class="
                        Number(
                          page.can_access
                        ) === 1
                          ? 'fa fa-check'
                          : 'fa fa-minus'
                      "
                      aria-hidden="true"
                    ></i>

                    {{
                      Number(
                        page.can_access
                      ) === 1
                        ? 'Allowed'
                        : 'No Access'
                    }}
                  </span>

                </div>

              </div>


              <div class="um2-subsection">

                <div class="um2-section-title compact">

                  <div>
                    <h3>
                      Field Edit Rights
                    </h3>

                    <p>
                      Editable fields assigned to this user.
                    </p>
                  </div>


                  <span class="um2-section-count">
                    {{ editableFields.length }}
                  </span>

                </div>


                <div
                  v-if="editableFields.length"
                  class="um2-rights-list"
                >

                  <div
                    v-for="field in editableFields"
                    :key="
                      `${field.page_name}-${field.field_name}`
                    "
                  >
                    <i
                      class="fa fa-pencil"
                      aria-hidden="true"
                    ></i>

                    <span>
                      {{ fieldLabel(field) }}
                    </span>
                  </div>

                </div>


                <div
                  v-else
                  class="um2-soft-empty"
                >
                  No field edit rights assigned.
                </div>

              </div>

            </template>

          </section>


          <!-- ================================================
               PROCESSES
          ================================================= -->

          <section
            v-else-if="
              editorTab === 'processes'
            "
            class="um2-editor-section"
          >

            <div class="um2-section-title">

              <div>
                <h3>
                  Process Access
                </h3>

                <p>
                  Shop-floor processes assigned to this user.
                </p>
              </div>


              <span class="um2-section-count">
                {{ permissions.processes.length }}
              </span>

            </div>


            <div
              v-if="permissionLoading"
              class="um2-inline-loading"
            >
              <i
                class="fa fa-circle-o-notch fa-spin"
                aria-hidden="true"
              ></i>

              Loading processes...
            </div>


            <div
              v-else-if="
                permissions.processes.length
              "
              class="um2-process-grid"
            >

              <div
                v-for="(
                  process,
                  index
                ) in permissions.processes"
                :key="index"
                class="um2-process-card"
              >
                <div class="um2-process-check">
                  <i
                    class="fa fa-check"
                    aria-hidden="true"
                  ></i>
                </div>

                <span>
                  {{ processLabel(process) }}
                </span>
              </div>

            </div>


            <div
              v-else
              class="um2-soft-empty large"
            >
              <i
                class="fa fa-cogs"
                aria-hidden="true"
              ></i>

              <strong>
                No process access assigned
              </strong>

              <span>
                This user does not currently have a shop-floor process assignment.
              </span>
            </div>

          </section>


          <!-- ================================================
               ACTIVITY
          ================================================= -->

          <section
            v-else
            class="um2-editor-section"
          >

            <div class="um2-section-title">
              <div>
                <h3>
                  Account Activity
                </h3>

                <p>
                  Available account timeline information.
                </p>
              </div>
            </div>


            <div class="um2-timeline">

              <div class="um2-timeline-item">
                <span class="um2-timeline-dot active"></span>

                <div>
                  <strong>
                    Last Login
                  </strong>

                  <p>
                    {{
                      formatLastLogin(
                        selectedUser.last_login
                      )
                    }}
                  </p>

                  <small>
                    {{
                      formatDate(
                        selectedUser.last_login
                      )
                    }}
                  </small>
                </div>
              </div>


              <div class="um2-timeline-item">
                <span class="um2-timeline-dot"></span>

                <div>
                  <strong>
                    Account Created
                  </strong>

                  <p>
                    User account created in JMS.
                  </p>

                  <small>
                    {{
                      formatDate(
                        selectedUser.created_at
                      )
                    }}
                  </small>
                </div>
              </div>

            </div>

          </section>

        </div>


        <!-- EDITOR FOOTER -->

        <footer class="um2-editor-footer">

          <div class="um2-preview-note">
            <i
              class="fa fa-shield"
              aria-hidden="true"
            ></i>

            UI preview — backend save connection is unchanged.
          </div>


          <button
            v-if="editorDirty"
            type="button"
            class="um2-btn"
            @click="discardEditorChanges"
          >
            Discard
          </button>


          <button
            type="button"
            class="um2-btn um2-btn-primary"
            :class="{
              disabled:
                !editorDirty
            }"
            @click="previewSave"
          >
            Save Changes
          </button>

        </footer>

      </template>

    </aside>


    <!-- ======================================================
         NEW USER MODAL
    ======================================================= -->

    <div
      class="um2-modal-overlay"
      :class="{
        open:
          newUserOpen
      }"
      @click.self="
        newUserOpen = false
      "
    >

      <section
        v-if="newUserOpen"
        class="um2-modal"
      >

        <header>

          <div>
            <h2>
              New User
            </h2>

            <p>
              Create a new JMS user account.
            </p>
          </div>


          <button
            type="button"
            @click="
              newUserOpen = false
            "
          >
            <i
              class="fa fa-times"
              aria-hidden="true"
            ></i>
          </button>

        </header>


        <div class="um2-modal-body">

          <div class="um2-form-grid">

            <label class="um2-field">
              <span>
                Username
              </span>

              <input
                v-model="newUserDraft.username"
                type="text"
                placeholder="e.g. operator01"
              />
            </label>


            <label class="um2-field">
              <span>
                Full Name
              </span>

              <input
                v-model="newUserDraft.full_name"
                type="text"
                placeholder="Employee name"
              />
            </label>


            <label class="um2-field">
              <span>
                Role
              </span>

              <select v-model="newUserDraft.role">
                <option>
                  Admin
                </option>

                <option>
                  Supervisor
                </option>

                <option>
                  Operator
                </option>
              </select>
            </label>

          </div>


          <div class="um2-modal-info">

            <i
              class="fa fa-info-circle"
              aria-hidden="true"
            ></i>

            This V2 pass is for UI approval. Existing user-creation logic will be connected after the layout is approved.

          </div>

        </div>


        <footer>

          <button
            type="button"
            class="um2-btn"
            @click="
              newUserOpen = false
            "
          >
            Cancel
          </button>


          <button
            type="button"
            class="um2-btn um2-btn-primary"
            @click="previewCreateUser"
          >
            Create User
          </button>

        </footer>

      </section>

    </div>


    <!-- ======================================================
         TOAST
    ======================================================= -->

    <div
      class="um2-toast"
      :class="{
        show:
          toast.show
      }"
    >
      <i
        class="fa fa-info-circle"
        aria-hidden="true"
      ></i>

      {{ toast.text }}
    </div>

  </div>
</template>