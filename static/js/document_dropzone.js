"use strict";

// Only affects the personal-document uploader. File validation, upload,
// course grouping, search and permissions retain their existing handlers.
(function () {
  function init() {
    var zone = document.getElementById("documentDropzone");
    var input = document.getElementById("documentFileInput");
    var error = document.getElementById("uploadSizeError");
    var form = document.getElementById("uploadForm");
    if (!zone || !input || !form) return;

    function showError(message) {
      if (error) {
        error.textContent = message;
        error.hidden = false;
      }
    }
    function clearDragState() {
      zone.classList.remove("is-drag-over");
    }
    zone.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        input.click();
      }
    });
    zone.addEventListener("dragenter", function (event) {
      event.preventDefault();
      zone.classList.add("is-drag-over");
    });
    zone.addEventListener("dragover", function (event) {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      zone.classList.add("is-drag-over");
    });
    zone.addEventListener("dragleave", function (event) {
      if (!event.relatedTarget || !zone.contains(event.relatedTarget)) {
        clearDragState();
      }
    });
    zone.addEventListener("drop", function (event) {
      event.preventDefault();
      clearDragState();
      var files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;

      var file = files[0];
      if (!/\.(pdf|docx|txt|md)$/i.test(file.name || "")) {
        input.value = "";
        input.dispatchEvent(new Event("change", {bubbles: true}));
        showError("Chỉ hỗ trợ file PDF, DOCX, TXT hoặc MD.");
        return;
      }
      try {
        // Restrict the existing single-file upload to the first dropped file.
        var transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", {bubbles: true}));
      } catch (error) {
        showError("Trình duyệt không hỗ trợ thả file tại đây. Hãy nhấn vào khung để chọn file.");
      }
    });
    window.addEventListener("dragend", clearDragState);
    window.addEventListener("drop", clearDragState);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
