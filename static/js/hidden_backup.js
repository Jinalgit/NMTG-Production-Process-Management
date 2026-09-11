(function () {
  if (window.__hiddenBackupShortcutInstalled) return;
  window.__hiddenBackupShortcutInstalled = true;

  function ensureBackupModal() {
    if (document.getElementById("hidden-backup-modal")) return;

    var style = document.createElement("style");
    style.textContent = `
      #hidden-backup-modal {
        display: none;
        position: fixed;
        inset: 0;
        z-index: 99999;
        background: rgba(15, 23, 42, 0.55);
        align-items: center;
        justify-content: center;
      }

      #hidden-backup-modal.active {
        display: flex;
      }

      .hidden-backup-box {
        width: 420px;
        max-width: calc(100vw - 32px);
        background: #ffffff;
        border-radius: 14px;
        box-shadow: 0 20px 50px rgba(15, 23, 42, 0.25);
        padding: 22px;
        font-family: inherit;
      }

      .hidden-backup-title {
        margin: 0 0 8px;
        font-size: 18px;
        font-weight: 800;
        color: #0f172a;
      }

      .hidden-backup-text {
        margin: 0 0 16px;
        font-size: 13px;
        color: #64748b;
        line-height: 1.5;
      }

      .hidden-backup-input {
        width: 100%;
        box-sizing: border-box;
        padding: 11px 12px;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        font-size: 14px;
        outline: none;
      }

      .hidden-backup-input:focus {
        border-color: #2563eb;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
      }

      .hidden-backup-actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 18px;
      }

      .hidden-backup-btn {
        border: 0;
        border-radius: 8px;
        padding: 9px 14px;
        font-size: 13px;
        font-weight: 700;
        cursor: pointer;
      }

      .hidden-backup-cancel {
        background: #f1f5f9;
        color: #334155;
      }

      .hidden-backup-download {
        background: #2563eb;
        color: #ffffff;
      }

      .hidden-backup-download:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }
    `;
    document.head.appendChild(style);

    var modal = document.createElement("div");
    modal.id = "hidden-backup-modal";
    modal.innerHTML = `
      <div class="hidden-backup-box">
        <h3 class="hidden-backup-title">Secure Database Backup</h3>
        <p class="hidden-backup-text">
          Enter backup code to download the current SQL backup.
        </p>

        <input
          type="password"
          id="hidden-backup-code"
          class="hidden-backup-input"
          placeholder="Enter backup code"
          autocomplete="off"
        />

        <div id="hidden-backup-status" style="margin-top:10px;font-size:13px;font-weight:700;"></div>

        <div class="hidden-backup-actions">
          <button type="button" class="hidden-backup-btn hidden-backup-cancel" id="hidden-backup-cancel">
            Cancel
          </button>
          <button type="button" class="hidden-backup-btn hidden-backup-download" id="hidden-backup-download">
            Download Backup
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    document.getElementById("hidden-backup-cancel").addEventListener("click", closeBackupModal);
    document.getElementById("hidden-backup-download").addEventListener("click", downloadBackup);

    document.getElementById("hidden-backup-code").addEventListener("keydown", function (e) {
      if (e.key === "Enter") downloadBackup();
      if (e.key === "Escape") closeBackupModal();
    });

    modal.addEventListener("click", function (e) {
      if (e.target === modal) closeBackupModal();
    });
  }

  function openBackupModal() {
    ensureBackupModal();

    var modal = document.getElementById("hidden-backup-modal");
    var input = document.getElementById("hidden-backup-code");

    input.value = "";
    var status = document.getElementById("hidden-backup-status");
    if (status) {
      status.textContent = "";
      status.style.color = "";
    }
    modal.classList.add("active");

    setTimeout(function () {
      input.focus();
    }, 50);
  }

  function closeBackupModal() {
    var modal = document.getElementById("hidden-backup-modal");
    if (modal) modal.classList.remove("active");
  }

  async function downloadBackup() {
    var input = document.getElementById("hidden-backup-code");
    var btn = document.getElementById("hidden-backup-download");

    var code = (input.value || "").trim();
    if (!code) {
      alert("Please enter backup code.");
      input.focus();
      return;
    }

    try {
      btn.disabled = true;
      btn.textContent = "Preparing...";

      var res = await fetch("/api/system/hidden-db-backup", {
        method: "POST",
        headers: {
          "X-Backup-Code": code
        },
        credentials: "same-origin"
      });

      if (!res.ok) {
        var msg = "Backup failed.";
        try {
          var err = await res.json();
          msg = err.error || msg;
        } catch (_) {}
        alert(msg);
        return;
      }

      var blob = await res.blob();

      var filename = "jms_demo2_backup.sql";
      var cd = res.headers.get("Content-Disposition") || "";
      var match = cd.match(/filename="([^"]+)"/);
      if (match) filename = match[1];

      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();

      setTimeout(function () {
        URL.revokeObjectURL(url);
        a.remove();
      }, 1000);

      var status = document.getElementById("hidden-backup-status");
      if (status) {
        status.textContent = "Backup downloaded successfully.";
        status.style.color = "#15803d";
      }

      setTimeout(function () {
        closeBackupModal();
      }, 1200);
    } catch (err) {
      alert("Backup failed: " + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Download Backup";
    }
  }

  document.addEventListener("keydown", function (e) {
    if (!(e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "b")) return;
    e.preventDefault();
    openBackupModal();
  });
})();
