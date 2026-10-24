document.addEventListener("DOMContentLoaded", function () {
  var globalSearch = document.getElementById("globalSearch");
  if (globalSearch) {
    globalSearch.addEventListener("input", function () {
      var q = globalSearch.value.trim().toLowerCase();
      document.querySelectorAll("[data-searchable]").forEach(function (el) {
        el.style.display = !q || (el.dataset.searchable || "").toLowerCase().includes(q) ? "" : "none";
      });
    });
  }

  var modal = document.getElementById("addSubjectModal");
  document.querySelectorAll(".add-subject-open").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (!modal) return;
      modal.classList.add("show");
      modal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    });
  });
  document.querySelectorAll("[data-close-subject-modal]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (!modal) return;
      modal.classList.remove("show");
      modal.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";
    });
  });

  var subjectSearch = document.getElementById("subjectSearch");
  var subjectCards = Array.from(document.querySelectorAll("[data-subject-card]"));
  var subjectFilter = "all";
  function filterSubjects() {
    var q = subjectSearch ? subjectSearch.value.trim().toLowerCase() : "";
    subjectCards.forEach(function (card) {
      var text = (card.dataset.searchable || "").toLowerCase();
      var status = card.dataset.status || "active";
      var show = (!q || text.includes(q)) && (subjectFilter === "all" || status === subjectFilter);
      card.style.display = show ? "" : "none";
    });
  }
  if (subjectSearch) subjectSearch.addEventListener("input", filterSubjects);
  document.querySelectorAll("#subjectFilters [data-filter]").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll("#subjectFilters [data-filter]").forEach(function (b) { b.classList.remove("active"); });
      button.classList.add("active");
      subjectFilter = button.dataset.filter;
      filterSubjects();
    });
  });

  var docSearch = document.getElementById("documentSearch");
  var docCards = Array.from(document.querySelectorAll("[data-document-card]"));
  var docType = "all";
  function filterDocs() {
    var q = docSearch ? docSearch.value.trim().toLowerCase() : "";
    docCards.forEach(function (card) {
      var type = (card.dataset.type || "").toLowerCase();
      var text = (card.dataset.searchable || "").toLowerCase();
      card.style.display = (!q || text.includes(q)) && (docType === "all" || type === docType) ? "" : "none";
    });
  }
  if (docSearch) docSearch.addEventListener("input", filterDocs);
  document.querySelectorAll("[data-doc-filter]").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll("[data-doc-filter]").forEach(function (b) { b.classList.remove("active"); });
      button.classList.add("active");
      docType = button.dataset.docFilter;
      filterDocs();
    });
  });

  var fileInput = document.getElementById("documentFileInput");
  var fileName = document.getElementById("selectedFileName");
  if (fileInput && fileName) {
    var uploadForm = document.getElementById("uploadForm");
    var uploadError = document.getElementById("uploadSizeError");
    var uploadButton = uploadForm ? uploadForm.querySelector('button[type="submit"]') : null;
    var maxMb = Number(uploadForm && uploadForm.dataset.uploadMaxMb) || 50;
    function validateUploadSize() {
      var selected = fileInput.files && fileInput.files[0];
      fileName.textContent = selected ? selected.name : "Chưa chọn file";
      // Một request multipart có thêm dữ liệu bao ngoài file nên cần chừa ít dư địa.
      var tooLarge = !!(selected && selected.size > (maxMb * 1024 * 1024 - 64 * 1024));
      if (uploadError) {
        uploadError.hidden = !tooLarge;
        uploadError.textContent = tooLarge
          ? "Tệp quá lớn (" + (selected.size / (1024 * 1024)).toFixed(1) +
            " MB). Giới hạn tải lên " + maxMb + " MB. Hãy nén hoặc chia PDF thành các tệp nhỏ hơn."
          : "";
      }
      if (uploadButton) uploadButton.disabled = tooLarge;
      return !tooLarge;
    }
    fileInput.addEventListener("change", validateUploadSize);
    if (uploadForm) uploadForm.addEventListener("submit", function (event) {
      if (!validateUploadSize()) event.preventDefault();
    });
  }

  document.querySelectorAll(".quiz-picker").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll(".quiz-picker").forEach(function (b) { b.classList.remove("active"); });
      document.querySelectorAll(".quiz-card").forEach(function (card) { card.classList.remove("active-workspace"); });
      button.classList.add("active");
      var target = document.getElementById(button.dataset.quizTarget);
      if (target) {
        target.classList.add("active-workspace");
        target.scrollIntoView({behavior:"smooth", block:"nearest"});
      }
    });
  });

  document.querySelectorAll(".quiz-card").forEach(function (card) {
    var questions = Array.from(card.querySelectorAll(".quiz-question-card"));
    var prev = card.querySelector(".quiz-prev-btn");
    var next = card.querySelector(".quiz-next-btn");
    var submit = card.querySelector(".quiz-submit-btn");
    var current = 0;
    function renderStep() {
      questions.forEach(function (q, index) { q.style.display = index === current ? "" : "none"; });
      if (prev) prev.disabled = current === 0;
      if (next) next.style.display = current >= questions.length - 1 ? "none" : "";
      if (submit) submit.style.display = current >= questions.length - 1 ? "" : "none";
      var label = card.querySelector(".quiz-progress-info span");
      if (label && questions.length) label.textContent = "Câu " + (current + 1) + " / " + questions.length;
    }
    if (prev) prev.addEventListener("click", function () { if (current > 0) { current -= 1; renderStep(); } });
    if (next) next.addEventListener("click", function () { if (current < questions.length - 1) { current += 1; renderStep(); } });
    var reset = card.querySelector(".quiz-reset-btn");
    if (reset) reset.addEventListener("click", function () { current = 0; setTimeout(renderStep, 0); });
    renderStep();
  });

  document.querySelectorAll("[data-chat-prompt]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById("chatInput");
      if (!input) return;
      input.value = button.dataset.chatPrompt || "";
      input.dispatchEvent(new Event("input", {bubbles:true}));
      input.focus();
    });
  });

  var weekDates = document.querySelectorAll(".week-date");
  if (weekDates.length) {
    var today = new Date();
    var monday = new Date(today);
    var day = today.getDay();
    var diff = day === 0 ? -6 : 1 - day;
    monday.setDate(today.getDate() + diff);
    var end = new Date(monday);
    end.setDate(monday.getDate() + 6);
    weekDates.forEach(function (el, index) {
      var d = new Date(monday);
      d.setDate(monday.getDate() + index);
      el.textContent = String(d.getDate()).padStart(2,"0") + "/" + String(d.getMonth()+1).padStart(2,"0");
    });
    var label = document.getElementById("weekRangeLabel");
    if (label) label.textContent = String(monday.getDate()).padStart(2,"0") + "/" + String(monday.getMonth()+1).padStart(2,"0") + " – " + String(end.getDate()).padStart(2,"0") + "/" + String(end.getMonth()+1).padStart(2,"0");
    document.querySelectorAll(".week-day").forEach(function (btn, index) {
      var d = new Date(monday); d.setDate(monday.getDate()+index);
      btn.classList.toggle("active", d.toDateString() === today.toDateString());
    });
  }
});