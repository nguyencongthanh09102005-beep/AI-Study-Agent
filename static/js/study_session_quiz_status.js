/* Lightweight, read-only status refresh; server controls Quiz access. */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const root = document.getElementById("studyRoomQuiz");
  if (!root) return;
  const status = document.getElementById("studyRoomQuizStatus");
  const detail = document.getElementById("studyRoomQuizDetail");
  const score = document.getElementById("studyRoomQuizScore");
  const go = document.getElementById("studyRoomQuizGo");
  const endpoint = root.dataset.statusUrl;
  if (!status || !detail || !score || !go || !endpoint) return;
  let inFlight = false;

  function render(data) {
    if (!data || !data.state) return;
    const state = data.state;
    const count = Number(data.count) || 0;
    const label = count ? count + " câu. " : "";
    if (state === "blocked") {
      status.textContent = "⚠ Chưa đủ điều kiện chuẩn bị Quiz";
      detail.textContent = data.reason || "Học liệu chưa được duyệt.";
      go.textContent = "Xem ngữ cảnh Quiz";
    } else if (state === "unprepared") {
      status.textContent = "◷ Quiz chưa chuẩn bị xong";
      detail.textContent = data.total_parts
        ? "Bài tổng hợp đang chuẩn bị " + data.prepared_parts + "/" +
          data.total_parts + " phần. Vào Lộ trình theo chương để tiếp tục."
        : "Vào Lộ trình theo chương → Chuẩn bị / Tiếp tục tạo Quiz.";
      go.textContent = "Xem ngữ cảnh Quiz";
    } else if (state === "active") {
      status.textContent = "✓ Quiz " + label + "đang được mở";
      detail.textContent = "Có thể vào bài kiểm tra và nộp kết quả.";
      go.textContent = "▶ Làm Quiz theo buổi";
    } else if (state === "available") {
      status.textContent = "✓ Đã đến giờ mở Quiz " + label;
      detail.textContent = "Bạn có thể bấm Bắt đầu Quiz tại trang Quiz.";
      go.textContent = "▶ Làm Quiz theo buổi";
    } else {
      status.textContent = "🔒 Quiz " + label + "đã chuẩn bị và đang khóa";
      detail.textContent = "Giờ kiểm tra theo lịch mới nhất: " +
        (data.study_at || "chưa xác định") + " – " +
        (data.ends_at || "chưa xác định") +
        ". Đổi lịch học sẽ tự đổi giờ mở Quiz.";
      go.textContent = "🔒 Xem lịch mở Quiz";
    }
    const times = Number(data.attempt_count) || 0;
    if (times > 0) {
      score.hidden = false;
      score.textContent = "Đã làm " + times + " lượt · Điểm cao nhất " +
        Number(data.best_score || 0).toFixed(1) + "%";
    } else {
      score.hidden = true;
    }
  }

  async function refresh() {
    if (inFlight || document.hidden) return;
    inFlight = true;
    try {
      const res = await fetch(endpoint, {
        method: "GET", credentials: "same-origin",
        headers: {"Accept": "application/json"}
      });
      if (res.ok) render(await res.json());
    } catch (_) {
      // Keep initial server-rendered, source-verified status if offline.
    } finally {
      inFlight = false;
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  window.addEventListener("focus", refresh);
  window.setInterval(refresh, 30000);
  refresh();
});
