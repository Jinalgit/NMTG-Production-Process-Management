// ── User Management ─────────────────────────────────────────────────────────
let allUsers = [];
let currentUserId = null; // populated from a hidden marker if needed
let viewingUserId = null;
let pendingRoleChange = null; // { fromRole, toRole }
let permissionMaster = { processes: [], pages: [], fields: [] };
let viewingPermissions = { processes: [], pages: [], fields: [] };

// ── Load users ───────────────────────────────────────────────────────────────
async function loadUsers() {
  document.getElementById("users-table-body").innerHTML =
    `<tr><td colspan="60">${renderTableSkeleton(5)}</td></tr>`;
  try {
    const res = await fetch("/api/users");
    const data = await res.json();
    if (!data.success) { showToast(data.error || "Load failed", "error"); return; }

    allUsers = data.users;
    renderUsersTable(allUsers);
  } catch (e) {
    showToast("Server error", "error");
  }
}

async function loadPermissionMaster() {
  try {
    const res = await fetch("/api/user-management/permission-master");
    const data = await res.json();
    if (data.success) permissionMaster = data;
  } catch (e) {
    // Keep the existing user list usable even if permission metadata fails.
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderUsersTable(users) {
  const tbody = document.getElementById("users-table-body");
  if (!users.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6">No users found</td></tr>';
    return;
  }

  tbody.innerHTML = users.map(u => {
    const isActive = u.is_active === 1;
    const statusBadge = isActive
      ? '<span class="status-badge active">Active</span>'
      : '<span class="status-badge inactive">Inactive</span>';
    const toggleLabel = isActive ? "Deactivate" : "Activate";
    const toggleClass = isActive ? "" : "reactivate";

    return `<tr style="cursor:pointer" onclick="openUserDetail(${u.id})">
      <td>${escapeHtml(u.username)}</td>
      <td>${escapeHtml(u.full_name || "-")}</td>
      <td><span class="role-badge ${escapeHtml(u.role)}">${escapeHtml(u.role)}</span></td>
      <td>${statusBadge}</td>
      <td style="font-size:12px;color:var(--muted)">${escapeHtml(u.created_at)}</td>
      <td>
        <button class="btn-toggle-active ${toggleClass}" onclick="event.stopPropagation(); toggleUserActive(${u.id})">
          ${toggleLabel}
        </button>
      </td>
    </tr>`;
  }).join("");
}

// ── Add User Modal ────────────────────────────────────────────────────────────
function openAddUserModal() {
  document.getElementById("u-username").value = "";
  document.getElementById("u-password").value = "";
  document.getElementById("u-full-name").value = "";
  document.getElementById("u-role").value = "";
  document.getElementById("add-user-modal").classList.add("open");
}

function closeAddUserModal() {
  document.getElementById("add-user-modal").classList.remove("open");
}

async function saveNewUser() {
  const username = document.getElementById("u-username").value.trim();
  const password = document.getElementById("u-password").value;
  const fullName = document.getElementById("u-full-name").value.trim();
  const role = document.getElementById("u-role").value;

  if (!username) { showToast("Username is required!", "error"); return; }
  if (!password || password.length < 6) { showToast("Password must be at least 6 characters!", "error"); return; }
  if (!role) { showToast("Please select a role!", "error"); return; }

  const btn = document.getElementById("add-user-save-btn");
  btn.disabled = true;
  btn.textContent = "Creating...";

  try {
    const res = await fetch("/api/users/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, full_name: fullName, role })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      closeAddUserModal();
      loadUsers();
    } else {
      showToast(data.error, "error");
    }
  } catch (e) {
    showToast("Server error", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Create User";
  }
}

// ── Toggle Active/Inactive ────────────────────────────────────────────────────
async function toggleUserActive(userId) {
  try {
    const res = await fetch(`/api/users/${userId}/toggle-active`, { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      loadUsers();
    } else {
      showToast(data.error, "error");
    }
  } catch (e) {
    showToast("Server error", "error");
  }
}

// ── User Detail Modal ─────────────────────────────────────────────────────────
function openUserDetail(userId) {
  const u = allUsers.find(u => u.id === userId);
  if (!u) return;
  viewingUserId = userId;
  document.getElementById("ud-username").textContent = u.username;
  document.getElementById("ud-full-name").textContent = u.full_name || "—";
  document.getElementById("ud-role").innerHTML = `<span class="role-badge ${escapeHtml(u.role)}">${escapeHtml(u.role)}</span>`;
  document.getElementById("ud-status").innerHTML = u.is_active === 1
    ? '<span class="status-badge active">Active</span>'
    : '<span class="status-badge inactive">Inactive</span>';
  document.getElementById("ud-created").textContent = u.created_at;
  hideEditRole();
  loadAndRenderPermissions(userId);
  document.getElementById("user-detail-modal").classList.add("open");
}

function closeUserDetail() {
  document.getElementById("user-detail-modal").classList.remove("open");
  viewingUserId = null;
  viewingPermissions = { processes: [], pages: [], fields: [] };
}

async function loadAndRenderPermissions(userId) {
  const section = document.getElementById("permissions-section");
  if (section) section.style.display = "block";
  try {
    if (!(permissionMaster.processes || []).length && !(permissionMaster.fields || []).length) {
      await loadPermissionMaster();
    }
    const res = await fetch(`/api/user-management/permissions/${userId}`);
    const data = await res.json();
    if (!data.success) {
      showToast(data.error || "Could not load permissions", "error");
      return;
    }
    viewingPermissions = data;
    renderPermissionEditor();
  } catch (e) {
    showToast("Server error", "error");
  }
}

function permissionLabel(text) {
  return escapeHtml(String(text || "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()));
}

function renderPermissionEditor() {
  const processSet = new Set(viewingPermissions.processes || []);
  const pageSet = new Set((viewingPermissions.pages || []).filter(p => Number(p.can_access) === 1).map(p => p.page_name));
  const fieldSet = new Set((viewingPermissions.fields || []).filter(f => Number(f.can_edit) === 1).map(f => `${f.page_name}::${f.field_name}`));

  const processHost = document.getElementById("permission-process-list");
  if (processHost) {
    processHost.innerHTML = (permissionMaster.processes || []).map(proc => `
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:8px;cursor:pointer">
        <input type="checkbox" data-permission-kind="process" value="${escapeHtml(proc)}" ${processSet.has(proc) ? "checked" : ""}>
        <span>${escapeHtml(proc)}</span>
      </label>
    `).join("") || `<div style="font-size:13px;color:var(--muted)">No processes found</div>`;
  }

  const pageHost = document.getElementById("permission-page-list");
  if (pageHost) {
    pageHost.innerHTML = (permissionMaster.pages || []).map(page => `
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:8px;cursor:pointer">
        <input type="checkbox" data-permission-kind="page" value="${escapeHtml(page.page_name)}" ${pageSet.has(page.page_name) ? "checked" : ""}>
        <span>${escapeHtml(page.label || page.page_name)}</span>
      </label>
    `).join("") || `<div style="font-size:13px;color:var(--muted)">No pages found</div>`;
  }

  const fieldHost = document.getElementById("permission-field-list");
  if (fieldHost) {
    fieldHost.innerHTML = (permissionMaster.fields || []).map(field => {
      const key = `${field.page_name}::${field.field_name}`;
      return `<label style="display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:8px;cursor:pointer">
        <input type="checkbox" data-permission-kind="field" data-page-name="${escapeHtml(field.page_name)}" data-field-name="${escapeHtml(field.field_name)}" ${fieldSet.has(key) ? "checked" : ""}>
        <span>${escapeHtml(field.page_name)} / ${permissionLabel(field.label || field.field_name)}</span>
      </label>`;
    }).join("") || `<div style="font-size:13px;color:var(--muted)">No fields found</div>`;
  }
}

async function savePermissions() {
  if (!viewingUserId) return;

  const processes = Array.from(document.querySelectorAll('[data-permission-kind="process"]:checked')).map(el => el.value);
  const pages = Array.from(document.querySelectorAll('[data-permission-kind="page"]')).map(el => ({
    page_name: el.value,
    can_access: el.checked ? 1 : 0
  }));
  const fields = Array.from(document.querySelectorAll('[data-permission-kind="field"]')).map(el => ({
    page_name: el.dataset.pageName,
    field_name: el.dataset.fieldName,
    can_view: 1,
    can_edit: el.checked ? 1 : 0
  }));

  const btn = document.getElementById("permissions-save-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Saving...";
  }

  try {
    const res = await fetch("/api/user-management/save-permissions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: viewingUserId, processes, pages, fields })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || "Permissions saved", "success");
      loadAndRenderPermissions(viewingUserId);
    } else {
      showToast(data.error || "Save failed", "error");
    }
  } catch (e) {
    showToast("Server error", "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Save Rights";
    }
  }
}

function showEditRole() {
  const u = allUsers.find(u => u.id === viewingUserId);
  if (!u) return;
  highlightRolePill(u.role);
  document.getElementById("edit-role-section").style.display = "block";
  document.getElementById("detail-modal-footer").style.display = "none";
}

function hideEditRole() {
  document.getElementById("edit-role-section").style.display = "none";
  document.getElementById("detail-modal-footer").style.display = "flex";
}

function highlightRolePill(role) {
  ["admin", "supervisor", "operator"].forEach(r => {
    document.getElementById(`role-pill-${r}`).classList.toggle("selected", r === role);
  });
}

function selectRolePill(newRole) {
  const u = allUsers.find(u => u.id === viewingUserId);
  if (!u || newRole === u.role) return; // clicking the current role is a no-op
  pendingRoleChange = { fromRole: u.role, toRole: newRole };
  highlightRolePill(newRole); // preview the selection visually
  document.getElementById("role-confirm-msg").innerHTML =
    `Change <strong>${escapeHtml(u.username)}</strong>'s role from ` +
    `<span class="role-badge ${escapeHtml(u.role)}">${escapeHtml(u.role)}</span> to ` +
    `<span class="role-badge ${escapeHtml(newRole)}">${escapeHtml(newRole)}</span>?`;
  document.getElementById("role-confirm-modal").classList.add("open");
}

function cancelRoleChange() {
  document.getElementById("role-confirm-modal").classList.remove("open");
  const u = allUsers.find(u => u.id === viewingUserId);
  if (u) highlightRolePill(u.role); // revert pill highlight to actual current role
  pendingRoleChange = null;
}

async function confirmRoleChange() {
  if (!pendingRoleChange || !viewingUserId) return;
  const { toRole } = pendingRoleChange;
  const btn = document.getElementById("role-confirm-btn");
  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    const res = await fetch(`/api/users/${viewingUserId}/update-role`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: toRole })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, "success");
      document.getElementById("role-confirm-modal").classList.remove("open");
      closeUserDetail();
      loadUsers();
    } else {
      showToast(data.error, "error");
    }
  } catch (e) {
    showToast("Server error", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirm";
    pendingRoleChange = null;
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadPermissionMaster();
loadUsers();

function renderTableSkeleton(rowCount = 1) {
  let rows = "";
  for (let i = 0; i < rowCount; i++) {
    rows += `<div class="skeleton-table-row">
      <div class="skeleton-line short"></div>
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line short"></div>
    </div>`;
  }
  return `<div class="skeleton-wrap">${rows}</div>`;
}
