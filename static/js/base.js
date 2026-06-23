// Shows a toast notification message at the bottom right of the screen.
// type can be 'success' (green) or 'error' (red)
function showToast(msg, type) {
  const t = document.getElementById("toast");
  if (!t) return;

  t.textContent = msg;
  t.className = `toast ${type}`;
  t.style.display = "block";

  setTimeout(() => {
    t.style.display = "none";
  }, 3500);
}

function formatDateForDisplay(value) {
  if (!value) return "";

  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return "";
    const dd = String(value.getDate()).padStart(2, "0");
    const mm = String(value.getMonth() + 1).padStart(2, "0");
    const yyyy = value.getFullYear();
    return `${dd}-${mm}-${yyyy}`;
  }

  const raw = String(value).trim();
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/);
  if (!match) return raw;

  const formatted = `${match[3]}-${match[2]}-${match[1]}`;
  const timeMatch = match[4]?.match(/\s+(\d{2}:\d{2})/);
  return timeMatch ? `${formatted} ${timeMatch[1]}` : formatted;
}

function openTraceability(jobCardNo) {
  if (!jobCardNo) return;
  window.location.href = `/page3?jc=${encodeURIComponent(jobCardNo)}`;
}


// =====================================================
// OLD MOBILE NAVIGATION SUPPORT
// Safe fallback for pages/components using old nav classes
// =====================================================
function setMobileMenuState(isOpen) {
  const possibleMenus = [
    document.querySelector(".nav-links"),
    document.querySelector(".navbar-links"),
    document.querySelector(".menu"),
    document.querySelector(".nav-menu")
  ];

  const menu = possibleMenus.find(Boolean);
  const button = document.querySelector(".mobile-menu-btn");

  if (!menu || !button) return;

  menu.classList.toggle("mobile-open", isOpen);
  button.classList.toggle("is-open", isOpen);
  button.setAttribute("aria-expanded", String(isOpen));
  button.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
}

function toggleMobileMenu() {
  const menu = document.querySelector(".nav-links, .navbar-links, .menu, .nav-menu");
  setMobileMenuState(!menu?.classList.contains("mobile-open"));
}

document.addEventListener("click", function (event) {
  const btn = event.target.closest(".mobile-menu-btn");
  const menu = document.querySelector(".nav-links, .navbar-links, .menu, .nav-menu");

  if (!menu) return;
  if (btn) return;

  if (window.innerWidth <= 768 && !menu.contains(event.target)) {
    setMobileMenuState(false);
  }
});

document.addEventListener("click", function (event) {
  const navLink = event.target.closest(".nav-links a, .navbar-links a, .menu a, .nav-menu a");

  if (window.innerWidth <= 768 && navLink) {
    setMobileMenuState(false);
  }
});


// =====================================================
// SIDEBAR NAVIGATION
// =====================================================
function toggleSidebarMobile() {
  document.body.classList.toggle("sidebar-open");
}

function closeSidebarMobile() {
  if (window.innerWidth <= 768) {
    document.body.classList.remove("sidebar-open");
  }
}



document.addEventListener("click", function (event) {
  const sidebarLink = event.target.closest(".sidebar-link, .sidebar-logout");

  if (sidebarLink && window.innerWidth <= 768) {
    closeSidebarMobile();
  }
});

window.addEventListener("resize", function () {
  if (window.innerWidth <= 768) {
    setMobileMenuState(false);
  } else {
    document.body.classList.remove("sidebar-open");
  }
});


// =====================================================
// WELCOME / LOGOUT CONFIRMATION MODALS
// =====================================================
function closeWelcomeModal() {
  const modal = document.getElementById("welcome-modal");
  if (modal) modal.classList.remove("open");
}

function openLogoutModal(event) {
  const modal = document.getElementById("logout-modal");
  if (!modal) return true; // no modal rendered — follow the link normally

  if (event) event.preventDefault();
  modal.classList.add("open");
  return false;
}

function closeLogoutModal() {
  const modal = document.getElementById("logout-modal");
  if (modal) modal.classList.remove("open");
}

document.addEventListener("click", function (event) {
  const overlay = event.target.closest(".auth-modal-overlay.open");
  if (overlay && event.target === overlay) {
    overlay.classList.remove("open");
  }
});

document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") return;

  document.querySelectorAll(".auth-modal-overlay.open").forEach(function (overlay) {
    overlay.classList.remove("open");
  });
});

// =====================================================
// SHARED MODAL DISMISSAL
// =====================================================
(function () {
  const modalSelector = ".modal-overlay.open, .bulk-modal-overlay.open, .pm-bulk-overlay.open";

  const closeHandlers = {
    "upload-modal": "closeUploadModal",
    "bulk-modal": "closeBulkModal",
    "pm-bulk-modal": "closeBulkModal",
    "view-detail-modal": "closeProcessDetailModal",
    "delete-modal": "closeDeleteModal",
    "add-modal": "closeAddModal",
    "edit-modal": "closeEditModal",
    "stage-modal": "closeStageModal"
  };

  function closeModalOverlay(overlay) {
    if (!overlay) return;

    const handlerName = closeHandlers[overlay.id];

    if (handlerName && typeof window[handlerName] === "function") {
      window[handlerName]();
      return;
    }

    overlay.classList.remove("open");
  }

  document.addEventListener("click", function (event) {
    const overlay = event.target.closest(".modal-overlay, .bulk-modal-overlay, .pm-bulk-overlay");

    if (!overlay || event.target !== overlay || !overlay.classList.contains("open")) {
      return;
    }

    closeModalOverlay(overlay);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;

    const openModals = Array.from(document.querySelectorAll(modalSelector));
    if (!openModals.length) return;

    closeModalOverlay(openModals[openModals.length - 1]);
  });
})();
