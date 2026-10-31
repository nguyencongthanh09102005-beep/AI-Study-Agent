/* One branded confirmation dialog for Student Web and Admin.
   Never use browser confirm/alert and never bypass the original form's hidden
   CSRF token, HTTP method, submitter or browser validity checks.
*/
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const modal = document.getElementById("appConfirmModal");
  const confirmForm = document.getElementById("appConfirmForm");
  const title = document.getElementById("appConfirmTitle");
  const message = document.getElementById("appConfirmMessage");
  const confirmButton = document.getElementById("appConfirmDeleteButton");
  const icon = modal?.querySelector(".app-confirm-icon");
  const dialog = modal?.querySelector(".app-confirm-dialog");
  const cancelButton = modal?.querySelector(".app-confirm-cancel");
  if (!modal || !confirmForm || !title || !message || !confirmButton) return;

  let pending = null;
  let lastFocus = null;
  let previousOverflow = "";
  const approvedForms = new WeakSet();

  function dismiss(accepted) {
    if (!pending) return;
    const done = pending;
    pending = null;
    modal.classList.remove("show");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = previousOverflow;
    confirmButton.disabled = false;
    if (lastFocus && lastFocus.isConnected) lastFocus.focus({preventScroll:true});
    lastFocus = null;
    done.resolve(accepted);
  }

  function openConfirm({title: heading = "Xác nhận thao tác",
                        message: body = "Bạn có muốn tiếp tục?",
                        confirmLabel = "Xác nhận",
                        kind = "warning"} = {}) {
    return new Promise((resolve) => {
      // Do not replace an unresolved decision or submit twice.
      if (pending) { resolve(false); return; }
      pending = {resolve};
      lastFocus = document.activeElement;
      previousOverflow = document.body.style.overflow;
      title.textContent = String(heading);
      message.textContent = String(body);
      confirmButton.textContent = String(confirmLabel);
      confirmButton.disabled = false;
      modal.dataset.kind = kind === "danger" ? "danger" : "warning";
      if (icon) icon.textContent = kind === "danger" ? "🗑️" : "⚠️";
      modal.classList.add("show");
      modal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
      window.requestAnimationFrame(() => cancelButton?.focus({preventScroll:true}));
    });
  }

  window.AppDialogs = Object.freeze({confirm: openConfirm});

  // Delegate, so later-added forms work too. Submit ORIGINAL form on approval:
  // unlike submitting appConfirmForm, this sends confirm_code and CSRF fields.
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) ||
        !form.matches("form[data-confirm-message]") ||
        approvedForms.has(form)) return;
    event.preventDefault();
    const submitter = event.submitter;
    const options = {
      title: form.dataset.confirmTitle || "Xác nhận thao tác",
      message: form.dataset.confirmMessage || "Bạn có muốn tiếp tục?",
      confirmLabel: form.dataset.confirmLabel || "Xác nhận",
      kind: form.dataset.confirmKind || "danger"
    };
    void openConfirm(options).then((accepted) => {
      if (!accepted || !form.isConnected) return;
      approvedForms.add(form);
      try {
        if (submitter && submitter.form === form) form.requestSubmit(submitter);
        else form.requestSubmit();
      } finally {
        approvedForms.delete(form);
      }
    });
  }, true);

  confirmForm.addEventListener("submit", (event) => {
    event.preventDefault();
    dismiss(true);
  });
  modal.querySelectorAll("[data-confirm-close]").forEach(element =>
    element.addEventListener("click", () => dismiss(false))
  );
  document.addEventListener("keydown", event => {
    if (!pending) return;
    if (event.key === "Escape") {
      event.preventDefault();
      dismiss(false);
    } else if (event.key === "Tab" && dialog) {
      const controls = [cancelButton, confirmButton].filter(Boolean);
      if (!controls.length) return;
      if (event.shiftKey && document.activeElement === controls[0]) {
        event.preventDefault();
        controls[controls.length - 1].focus();
      } else if (!event.shiftKey &&
                 document.activeElement === controls[controls.length - 1]) {
        event.preventDefault();
        controls[0].focus();
      }
    }
  });
});
