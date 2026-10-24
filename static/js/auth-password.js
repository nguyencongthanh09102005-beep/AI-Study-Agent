// Show/hide password for Web login + signup, without interfering with form submit.
(function () {
  "use strict";
  function setupPasswordToggles(root) {
    if (!root || typeof root.querySelectorAll !== "function") return;
    root.querySelectorAll(".auth-password-field .password-toggle").forEach(function (button) {
      var targetId = button.getAttribute("data-target");
      var input = targetId && root.getElementById(targetId);
      if (!input || input.type !== "password" || button.dataset.initialized === "true") return;

      button.dataset.initialized = "true";
      button.addEventListener("click", function () {
        var visible = input.type === "password";
        input.type = visible ? "text" : "password";
        var label = button.getAttribute("data-label") || "mật khẩu";
        button.setAttribute("aria-pressed", String(visible));
        button.setAttribute("aria-label", (visible ? "Ẩn " : "Hiện ") + label);
        button.setAttribute("title", (visible ? "Ẩn " : "Hiện ") + label);
        button.classList.toggle("is-visible", visible);
      });
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { setupPasswordToggles: setupPasswordToggles };
  }
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () {
        setupPasswordToggles(document);
      });
    } else {
      setupPasswordToggles(document);
    }
  }
})();
