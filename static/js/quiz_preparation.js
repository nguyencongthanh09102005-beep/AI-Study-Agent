/* Phase 7.6: submit durable server-side AI preparation job once.
   Student can navigate away or close the tab; the persistent server worker
   continues while the server runs. No browser request loop invokes the AI provider. */
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

  async function request(url, post) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...(post ? {method:"POST", headers:{
        "X-Quiz-CSRF":token, "Content-Type":"application/json"
      },body:"{}"} : {})
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Không thể chuẩn bị Quiz.");
    return data;
  }
  function report(data) {
    if (!data || !Array.isArray(data.items)) return;
    const pending = data.items.filter(item => item.status !== "ready");
    const next = pending[0];
    const state = data.job?.state || "not_started";
    const active = state === "running" || state === "queued";
    let message = "Đã chuẩn bị " + data.ready + "/" + data.total +
      " bộ Quiz";
    if (data.done) message += " · tất cả đã sẵn sàng.";
    else if (active) message +=
      " · AI đang tạo trên máy chủ. Bạn có thể chuyển trang, không làm dừng tiến trình.";
    else if (state === "paused") message +=
      " · đã tạm dừng, bấm Tiếp tục khi cần.";
    else if (state === "error") message +=
      " · lỗi: " + (data.job.message || "Cần kiểm tra nguồn rồi thử lại.");
    else if (next?.status === "blocked") message +=
      " · " + (next.reason || "Học liệu chưa được duyệt.");
    else message += " · tiếp theo: buổi " + (data.items.indexOf(next) + 1);
    label.textContent = message;
    start.textContent = data.done ? "✓ Đã chuẩn bị xong" :
      active ? "◷ AI đang tạo Quiz..." : "✦ Chuẩn bị / Tiếp tục tạo Quiz";
    start.disabled = working || active || data.done || data.total === 0;
    stop.hidden = !active;
    stop.disabled = working;
  }
  async function refresh() {
    try { report(await request(base)); }
    catch (error) { label.textContent = error.message; }
  }
  async function run() {
    if (working) return;
    working = true;
    start.disabled = true;
    try {
      const job = await request(base + "/background", true);
      if (job.accepted) {
        label.textContent = "Đã giao nhiệm vụ cho máy chủ. Bạn có thể xem Lịch học trong lúc AI chuẩn bị.";
      }
    } catch (error) {
      label.textContent = "Không bắt đầu được: " + error.message;
    } finally {
      working = false;
      await refresh();
    }
  }
  start?.addEventListener("click",run);
  stop?.addEventListener("click",async () => {
    if (working) return;
    working = true;
    try {
      await request(base + "/background/pause",true);
      label.textContent = "Đang tạm dừng sau bước AI hiện tại. Các Quiz đã lưu vẫn còn.";
    } catch(error) {
      label.textContent = error.message;
    } finally {
      working = false;
      await refresh();
    }
  });
  refresh().then(() => {
    if (root.dataset.auto === "1" && !start.disabled) run();
  });
  // Poll for display only. Backend preparation proceeds without this tab.
  window.setInterval(() => {
    if (!document.hidden) refresh();
  }, 4000);
});
