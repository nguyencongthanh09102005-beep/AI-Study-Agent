"use strict";
(function () {
  function initialize() {
    const form = document.getElementById("taskForm");
    const section = document.getElementById("manualTaskDocumentSection");
    const subject = document.getElementById("taskSubject");
    const select = document.getElementById("taskPersonalDocument");
    const checkbox = document.getElementById("taskPrepareQuiz");
    const hint = document.getElementById("manualTaskDocHint");
    if (!form || !section || !subject || !select || !checkbox) return;

    const options = Array.from(select.querySelectorAll("option")).filter(x => x.value);
    function refresh() {
      const isCreate = /\/study-plan\/tasks\/create(?:\?.*)?$/.test(form.action);
      section.hidden = !isCreate;
      // The legacy edit/move form intentionally does not change existing
      // personal-document attachments or regenerate Quiz.
      if (!isCreate) {
        select.value = "";
        checkbox.checked = false;
        return;
      }
      const targetSubject = subject.value;
      let count = 0;
      options.forEach(opt => {
        const valid = Boolean(targetSubject) && opt.dataset.subjectId === targetSubject;
        opt.hidden = !valid;
        opt.disabled = !valid;
        if (valid) count++;
      });
      if (!select.selectedOptions.length || select.selectedOptions[0].disabled) {
        select.value = "";
      }
      checkbox.disabled = !select.value;
      if (checkbox.disabled) checkbox.checked = false;
      if (hint) hint.textContent = count
        ? "Chọn file của môn học. Buổi thủ công sẽ có Không gian học cá nhân riêng."
        : "Môn này chưa có tài liệu cá nhân trích xuất đủ chữ. Có thể thêm buổi học mà không chọn file.";
    }

    subject.addEventListener("change", () => {
      select.value = "";
      refresh();
    });
    select.addEventListener("change", refresh);
    form.addEventListener("submit", event => {
      if (section.hidden) return;
      if (select.value && (!subject.value || select.selectedOptions[0]?.dataset.subjectId !== subject.value)) {
        event.preventDefault();
        if (hint) hint.textContent = "Tài liệu phải thuộc đúng môn học đã chọn.";
      }
    });
    // Existing code assigns the create/edit action inside click handlers.
    // Register an extra listener on the form openers and run after those handlers.
    const triggers = [
      document.getElementById("openQuickTask"),
      document.getElementById("addTaskButton"),
      ...document.querySelectorAll(".move-task-btn, .edit-task-btn")
    ];
    triggers.filter(Boolean).forEach(btn => {
      btn.addEventListener("click", () => window.setTimeout(refresh, 0));
    });
    refresh();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
  } else {
    initialize();
  }
})();
