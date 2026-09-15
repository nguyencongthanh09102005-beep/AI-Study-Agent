document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("appConfirmModal");
  const confirmForm = document.getElementById("appConfirmForm");
  const title = document.getElementById("appConfirmTitle");
  const message = document.getElementById("appConfirmMessage");
  const deleteButton = document.getElementById("appConfirmDeleteButton");

  if (!modal || !confirmForm) return;

  let sourceForm = null;

  function openConfirm(form) {
    sourceForm = form;

    title.textContent =
      form.dataset.confirmTitle ||
      "Xác nhận xóa";

    message.textContent =
      form.dataset.confirmMessage ||
      "Bạn có chắc muốn xóa mục này?";

    deleteButton.textContent =
      form.dataset.confirmLabel ||
      "Xóa";

    confirmForm.action = form.action;

    modal.classList.add("show");
    modal.setAttribute("aria-hidden", "false");

    document.body.style.overflow = "hidden";

    requestAnimationFrame(() => {
      const cancelButton =
        modal.querySelector(".app-confirm-cancel");

      cancelButton?.focus();
    });
  }

  function closeConfirm() {
    modal.classList.remove("show");
    modal.setAttribute("aria-hidden", "true");

    document.body.style.overflow = "";

    sourceForm = null;
  }

  document
    .querySelectorAll(
      "form[data-confirm-message]"
    )
    .forEach((form) => {
      form.addEventListener(
        "submit",
        (event) => {
          event.preventDefault();
          openConfirm(form);
        }
      );
    });

  modal
    .querySelectorAll("[data-confirm-close]")
    .forEach((button) => {
      button.addEventListener(
        "click",
        closeConfirm
      );
    });

  document.addEventListener(
    "keydown",
    (event) => {
      if (
        event.key === "Escape" &&
        modal.classList.contains("show")
      ) {
        closeConfirm();
      }
    }
  );

  confirmForm.addEventListener(
    "submit",
    () => {
      deleteButton.disabled = true;
      deleteButton.textContent = "Đang xóa...";
    }
  );
});
