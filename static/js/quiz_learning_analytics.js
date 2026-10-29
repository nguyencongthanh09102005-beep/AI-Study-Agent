/* Phase 7.5.2: render only aggregate learning statistics from the backend.
   Never inject untrusted chapter/topic labels as HTML; use textContent. */
window.QuizLearningAnalytics = Object.freeze({
  render(panel, payload) {
    if (!panel || !payload || !payload.analysis) return;
    const analysis = payload.analysis;
    panel.replaceChildren();
    panel.hidden = false;

    function node(parent, tag, text, css) {
      const element = document.createElement(tag);
      if (css) element.className = css;
      element.textContent = String(text ?? "");
      parent.appendChild(element);
      return element;
    }

    node(panel, "h4", "📊 Phân tích kiến thức sau Quiz", "quiz-analysis-heading");
    const counts = node(panel, "div", "", "quiz-analysis-metrics");
    for (const [label, value] of [
      ["Đúng", analysis.correct || 0],
      ["Sai", analysis.incorrect || 0],
      ["Điểm", String(payload.score ?? 0) + "%"]
    ]) {
      const card = node(counts, "div", "", "quiz-analysis-metric");
      node(card, "strong", value);
      node(card, "small", label);
    }
    const unverifiable = Number(analysis.unverifiable || 0);
    if (unverifiable) {
      node(panel, "p",
        unverifiable + " câu không đủ dữ liệu để phân tích theo đáp án; " +
        "không được tự xem là điểm yếu.",
        "quiz-analysis-note");
    }

    function breakdown(title, rows, kind) {
      if (!Array.isArray(rows) || !rows.length) return;
      const section = node(panel, "section", "", "quiz-analysis-section");
      node(section, "h5", title);
      for (const item of rows) {
        const row = node(section, "div", "", "quiz-analysis-row");
        const info = node(row, "div", "", "quiz-analysis-label");
        const name = item.chapter && kind === "topic"
          ? item.chapter + " · " + item.name : item.name;
        node(info, "span", name || "Chưa phân loại");
        node(info, "strong", String(item.correct || 0) + "/" + String(item.total || 0) +
          " · " + String(item.percent ?? 0) + "%" +
          (kind === "topic" && Number(item.total) === 1 ? " · 1 câu" : ""));
        const track = node(row, "div", "", "quiz-analysis-track");
        const fill = node(track, "div", "", "quiz-analysis-fill");
        const percent = Math.max(0, Math.min(100, Number(item.percent) || 0));
        fill.style.width = percent + "%";
        fill.classList.add(percent >= 80 ? "strong" :
          percent >= 60 ? "medium" : "review");
      }
    }
    breakdown("Theo chương", analysis.chapters, "chapter");
    breakdown("Theo chủ đề · ưu tiên phần sai nhiều", analysis.topics, "topic");

    const reviewRows = Array.isArray(analysis.needs_review)
      ? analysis.needs_review.filter(r => r.topic &&
          !String(r.topic).startsWith("Chưa xác định"))
      : [];
    const review = node(panel, "div", "", "quiz-analysis-review");
    node(review, "strong", reviewRows.length ?
      "📚 Những nội dung nên ôn lại" : "✓ Không có chủ đề sai cần ưu tiên trong lượt này");
    if (reviewRows.length) {
      const ul = node(review, "ul", "");
      for (const row of reviewRows.slice(0, 6)) {
        node(ul, "li", row.chapter + " · " + row.topic +
          " (" + row.incorrect + "/" + row.total + " câu sai)");
      }
    }
    if (Number(payload.subject_id) > 0) {
      const actions = node(review, "div", "", "quiz-analysis-actions");
      const reviewLink = node(actions, "a", "Ôn điểm yếu →");
      reviewLink.href = "/quiz?mode=weakness&subject_id=" +
        encodeURIComponent(String(payload.subject_id));
      const planLink = node(actions, "a", "Xem kế hoạch học →");
      planLink.href = "/study-plan?subject_id=" +
        encodeURIComponent(String(payload.subject_id));
    }
    node(panel, "p",
      "Thống kê theo lần làm Quiz này, không cộng dồn nhiều lượt. " +
      "Một chủ đề chỉ có 1 câu là dấu hiệu cần xem lại, chưa đủ kết luận năng lực. " +
      "Điểm yếu dài hạn và lịch ôn được hệ thống cập nhật riêng.",
      "quiz-analysis-note");
  }
});
