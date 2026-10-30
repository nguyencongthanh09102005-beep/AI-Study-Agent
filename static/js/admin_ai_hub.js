/* Single subject picker for the two existing Admin AI approval workflows. */
(function () {
  "use strict";
  const select = document.getElementById("adminAiSubject");
  const syllabus = document.getElementById("adminAiSyllabus");
  const bulk = document.getElementById("adminAiBulk");
  const syllabusState = document.getElementById("adminAiSyllabusState");
  const bulkState = document.getElementById("adminAiBulkState");
  const help = document.getElementById("adminAiHelp");
  if (!select || !syllabus || !bulk || !syllabusState || !bulkState || !help) return;

  function chosen() {
    const option = select.options[select.selectedIndex];
    if (!option || !option.value) return null;
    return {
      syllabusUrl: option.dataset.syllabusUrl || "",
      bulkUrl: option.dataset.bulkUrl || "",
      hasSyllabus: option.dataset.hasSyllabus === "1",
      documents: Math.max(0, Number(option.dataset.documentCount || 0) || 0)
    };
  }

  function refresh() {
    const course = chosen();
    syllabus.disabled = !course || !course.syllabusUrl;
    bulk.disabled = !course || !course.bulkUrl;

    if (!course) {
      syllabusState.textContent = "Chưa chọn môn học";
      bulkState.textContent = "Chưa chọn môn học";
      help.textContent = "Chọn môn học để xem các bước quản lý học liệu.";
      return;
    }

    syllabusState.textContent = course.hasSyllabus
      ? "✓ Đã có đề cương — xem lại hoặc phân tích"
      : "Chưa có đề cương — tải lên ở bên dưới";
    bulkState.textContent = course.documents
      ? course.documents + " tài liệu trong kho — cần kiểm tra liên kết chương"
      : "Chưa có tài liệu — tải lên ở bên dưới";
    help.textContent = !course.hasSyllabus
      ? "Hãy tải đề cương chuẩn trước khi phân tích và phân loại học liệu."
      : "AI chỉ đưa ra gợi ý. Kết quả chỉ được sử dụng sau khi Admin kiểm tra và xác nhận.";
  }

  function go(which) {
    const course = chosen();
    if (!course) {
      select.focus();
      return;
    }
    const destination = which === "syllabus" ? course.syllabusUrl : course.bulkUrl;
    // URLs are emitted server-side via url_for for authorized Admin routes.
    if (destination && destination.charAt(0) === "/" &&
        destination.charAt(1) !== "/") {
      window.location.assign(destination);
    }
  }

  select.addEventListener("change", refresh);
  syllabus.addEventListener("click", function () { go("syllabus"); });
  bulk.addEventListener("click", function () { go("bulk"); });
  refresh();
})();
