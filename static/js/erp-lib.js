/* ==========================================================================
   erp-lib.js - Global JS helpers (namespace: ERP.*)
   Loaded from templates/base.html after base.js.
   Backward-compat: window.showToast still works (shims to ERP.toast).
   ========================================================================== */
(function (window, document) {
  "use strict";
  var ERP = window.ERP || {};

  ERP.$  = function (sel, root) { return (root || document).querySelector(sel); };
  ERP.$$ = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  ERP.fmt = function (n, decimals) {
    if (n === null || n === undefined || n === "") return "\u2013";
    var num = Number(n);
    if (isNaN(num)) return String(n);
    var d = decimals === undefined ? 0 : decimals;
    return num.toLocaleString("en-IN",
      { minimumFractionDigits: d, maximumFractionDigits: d });
  };

  ERP.esc = function (s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  ERP.fmtDate = function (v, fmt) {
    if (!v) return "";
    var d = (v instanceof Date) ? v : new Date(String(v).replace(" ", "T"));
    if (isNaN(d.getTime())) return String(v);
    var dd = String(d.getDate()).padStart(2, "0");
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    var yyyy = d.getFullYear();
    var hh = String(d.getHours()).padStart(2, "0");
    var mi = String(d.getMinutes()).padStart(2, "0");
    fmt = fmt || "dd-mm-yyyy";
    return fmt.replace("yyyy", yyyy).replace("mm", mm)
              .replace("dd", dd).replace("HH", hh).replace("MM", mi);
  };

  function _ensureStack() {
    var st = document.getElementById("erp-toast-stack");
    if (!st) {
      st = document.createElement("div");
      st.id = "erp-toast-stack";
      st.className = "erp-toast-stack";
      document.body.appendChild(st);
    }
    return st;
  }
  var _iconByType = {
    success: "fa-check-circle", ok: "fa-check-circle",
    warn: "fa-exclamation-triangle", warning: "fa-exclamation-triangle",
    error: "fa-times-circle", err: "fa-times-circle",
    info: "fa-info-circle"
  };
  ERP.toast = function (msg, type, opts) {
    opts = opts || {};
    var stack = _ensureStack();
    var t = document.createElement("div");
    t.className = "erp-toast";
    t.setAttribute("data-type", type || "info");
    var icon = _iconByType[type] || "fa-info-circle";
    t.innerHTML =
      '<i class="fa ' + icon + ' erp-toast-icon"></i>' +
      '<button class="erp-toast-close" aria-label="Close">&times;</button>' +
      '<div class="erp-toast-msg">' + ERP.esc(msg) + '</div>';
    stack.appendChild(t);
    var timeout = opts.timeout === undefined ? 3500 : opts.timeout;
    var timer = null;
    function close() {
      if (timer) clearTimeout(timer);
      t.style.opacity = "0"; t.style.transform = "translateX(20px)";
      t.style.transition = "opacity 0.18s, transform 0.18s";
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 200);
    }
    t.querySelector(".erp-toast-close").addEventListener("click", close);
    if (timeout > 0) timer = setTimeout(close, timeout);
    return { close: close };
  };

  ERP.copy = function (text, opts) {
    opts = opts || {};
    var label = opts.label || "Copied";
    function done(ok) {
      if (opts.silent) return;
      if (ok) ERP.toast(label + ": " + text, "success", { timeout: 2000 });
      else    ERP.toast("Copy failed", "error");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () { done(true); }, function () { done(false); });
    } else {
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.left = "-9999px";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(true); }
      catch (e) { done(false); }
      finally { document.body.removeChild(ta); }
    }
  };

  ERP.statusBadge = function (status, opts) {
    opts = opts || {};
    var s = String(status || "").trim();
    if (!s) return '<span class="erp-badge" data-status="muted">\u2013</span>';
    var label = opts.label || s;
    var icon = opts.icon ? '<i class="fa ' + opts.icon + '"></i>' : '';
    return '<span class="erp-badge" data-status="' + ERP.esc(s.toLowerCase()) + '">'
           + icon + ERP.esc(label) + '</span>';
  };

  ERP.emptyMini = function (elemOrId, msg, hint, icon) {
    var el = typeof elemOrId === "string" ? document.getElementById(elemOrId) : elemOrId;
    if (!el) return;
    el.innerHTML =
      '<div class="erp-empty-mini">' +
        '<i class="fa fa-' + (icon || "inbox") + '"></i>' +
        '<div>' + ERP.esc(msg) + '</div>' +
        (hint ? '<div class="hint">' + ERP.esc(hint) + '</div>' : '') +
      '</div>';
  };

  ERP.openDrawer = function (panelId, overlayId) {
    var p = document.getElementById(panelId);
    var o = overlayId ? document.getElementById(overlayId) : null;
    if (p) { p.classList.add("open"); p.setAttribute("aria-hidden", "false"); }
    if (o) { o.classList.add("open"); }
  };
  ERP.closeDrawer = function (panelId, overlayId) {
    var p = document.getElementById(panelId);
    var o = overlayId ? document.getElementById(overlayId) : null;
    if (p) { p.classList.remove("open"); p.setAttribute("aria-hidden", "true"); }
    if (o) { o.classList.remove("open"); }
  };

  ERP.skeleton = {
    show: function (target, rows) {
      var el = typeof target === "string" ? document.getElementById(target) : target;
      if (!el) return;
      rows = rows || 6;
      var html = "";
      for (var i = 0; i < rows; i++) {
        var w = 60 + Math.round(Math.random() * 30);
        html += '<div class="skeleton-line" style="width:' + w + '%;margin:8px 0;"></div>';
      }
      el.innerHTML = html;
    },
    hide: function (target) {
      var el = typeof target === "string" ? document.getElementById(target) : target;
      if (el) el.innerHTML = "";
    }
  };

  // Backward-compat: window.showToast still works, routes to ERP.toast.
  // The existing base.js showToast will be replaced by this shim on load.
  window.showToast = function (msg, type) { ERP.toast(msg, type); };

  window.ERP = ERP;
  console.log("[erp-lib] ready. Helpers:", Object.keys(ERP).join(", "));
})(window, document);
