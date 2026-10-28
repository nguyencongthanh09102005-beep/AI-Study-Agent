/* 7.2: resume-safe, client-driven, one AI preparation step per request.
   Closing the tab stops work; saved Quiz and final-exam parts remain in SQLite. */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const root = document.getElementById("quizPreparation");
  if (!root) return;
  const subjectId = Number(root.dataset.subjectId);
  const token = root.dataset.csrf || "";
  const start = document.getElementById("quizPreparationStart");
  const stop = document.getElementById("quizPreparationStop");
  const label = document.getElementById("quizPreparationStatus");
  if (!Number.isInteger(subjectId) || subjectId <= 0 || !token) return;
  const base = "/api/subjects/" + subjectId + "/quiz-preparation";
  let working = false;
  let aborted = false;

  async function request(url, post) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...(post ? {method: "POST",
        headers: {"X-Quiz-CSRF": token, "Content-Type": "application/json"},
        body: "{}"} : {})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Không thể chuẩn bị Quiz.");
    return data;
  }
  function report(data) {
    if (!data || !Array.isArray(data.items)) return;
    const incomplete = data.items.filter(item => item.status !== "ready");
    label.textContent = "Đã chuẩn bị " + data.ready + "/" + data.total +
      " bộ Quiz" + (incomplete.length
        ? " · tiếp theo: buổi " + (data.items.indexOf(incomplete[0]) + 1)
        : " · tất cả đã sẵn sàng.");
    const blocked = incomplete.find(item => item.status === "blocked");
    if (blocked) label.textContent += " · " + blocked.reason;
    start.textContent = data.done ? "✓ Đã chuẩn bị xong" :
      "✦ Chuẩn bị / Tiếp tục tạo Quiz";
    start.disabled = working || data.done || data.total === 0;
  }
  async function refresh() {
    try { report(await request(base)); }
    catch (error) { label.textContent = error.message; }
  }
  async function run() {
    if (working) return;
    working = true;
    aborted = false;
    stop.hidden = false;
    start.disabled = true;
    try {
      for (let i = 0; i < 240 && !aborted; i++) {
        const progress = await request(base);
        report(progress);
        if (progress.done) break;
        const nextPending = progress.items.find(item => item.status !== "ready");
        if (nextPending && nextPending.status === "blocked") {
          label.textContent += " · Cần bổ sung/duyệt học liệu cho buổi tiếp theo.";
          break;
        }
        label.textContent = "Đang chuẩn bị theo từng bước... " + progress.ready +
          "/" + progress.total + " bộ đã sẵn sàng. Có thể tạm dừng bất cứ lúc nào.";
        const step = await request(base + "/next", true);
        if (step.done) break;
      }
    } catch (error) {
      label.textContent = "Chưa hoàn tất: " + error.message +
        " Bạn có thể bấm Tiếp tục, dữ liệu đã lưu vẫn còn.";
    } finally {
      working = false;
      stop.hidden = true;
      await refresh();
    }
  }
  start?.addEventListener("click", run);
  stop?.addEventListener("click", () => {
    aborted = true;
    label.textContent = "Đang tạm dừng sau bước hiện tại; phần đã tạo được giữ lại.";
  });
  refresh().then(() => {
    if (root.dataset.auto === "1" && !start.disabled) run();
  });
});
