/* Phase 6.4: recorded, server-authoritative study timer. No client seconds
   are ever sent to the backend; only verified state transitions. */
document.addEventListener("DOMContentLoaded", () => {
  "use strict";
  const root = document.getElementById("studySessionTimer");
  if (!root) return;
  const taskId = Number(root.dataset.taskId);
  const csrf = root.dataset.csrf || "";
  const stateLabel = document.getElementById("studySessionState");
  const clock = document.getElementById("studySessionElapsed");
  const notice = document.getElementById("studySessionNotice");
  const controls = {
    start: document.getElementById("studySessionStart"),
    pause: document.getElementById("studySessionPause"),
    resume: document.getElementById("studySessionResume"),
    finish: document.getElementById("studySessionFinish")
  };
  const url = "/api/study-plan/tasks/" + taskId + "/study-session";
  let state = root.dataset.initialStatus || "idle";
  let elapsed = Math.max(0, Number(root.dataset.initialSeconds) || 0);
  let syncedAt = Date.now(), loading = true;
  let inFlight = false;
  const labels = {
    idle: "Chưa bắt đầu", running: "Đang học",
    paused: "Đã tạm dừng", completed: "Đã hoàn thành"
  };

  function timestamp(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    const pad = value => String(value).padStart(2, "0");
    return pad(Math.floor(total / 3600)) + ":" +
      pad(Math.floor(total / 60) % 60) + ":" + pad(total % 60);
  }
  function render() {
    const active = state === "running" && !document.hidden;
    // A short visual extrapolation between server heartbeats only.
    const display = elapsed + (active ? Math.min(45,
      Math.floor((Date.now() - syncedAt) / 1000)) : 0);
    clock.textContent = timestamp(display);
    stateLabel.textContent = labels[state] || "Không xác định";
    stateLabel.dataset.state = state;
    for (const [action, button] of Object.entries(controls)) {
      button.hidden = loading ||
        (action === "start" && state !== "idle") ||
        (action === "pause" && state !== "running") ||
        (action === "resume" && state !== "paused") ||
        (action === "finish" && !["running", "paused"].includes(state));
      button.disabled = inFlight;
    }
  }
  function consume(data) {
    if (!data || data.task_id !== taskId ||
        !["idle", "running", "paused", "completed"].includes(data.status) ||
        !Number.isFinite(data.elapsed_seconds) || data.elapsed_seconds < 0) {
      throw new Error("Dữ liệu phiên học không hợp lệ.");
    }
    state = data.status;
    elapsed = data.elapsed_seconds;
    syncedAt = Date.now();
    render();
  }
  async function api(action) {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...(action ? {
        method: "POST",
        headers: {"Content-Type": "application/json", "X-Study-CSRF": csrf},
        body: JSON.stringify({action})
      } : {})
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "Không thể kết nối hệ thống.");
    return body;
  }
  async function sync() {
    if (inFlight) return;
    inFlight = true; render();
    try {
      consume(await api());
      notice.textContent = state === "completed" ?
        "Buổi học đã được đánh dấu hoàn thành và đồng bộ với Kế hoạch học." :
        "Thời gian được lưu theo buổi; bạn có thể tạm dừng và tiếp tục.";
    } catch (error) {
      notice.textContent = error.message;
    } finally {
      loading = false; inFlight = false; render();
    }
  }
  async function sendAction(action) {
    if (loading || inFlight) return;
    if (action === "finish" &&
        !window.confirm("Hoàn thành buổi học này? Tiến độ trong Kế hoạch học sẽ được cập nhật.")) {
      return;
    }
    inFlight = true;
    render();
    try {
      const data = await api(action);
      consume(data);
      notice.textContent = action === "finish" ?
        "✓ Đã hoàn thành buổi học. Thời gian thực tế và tiến độ môn đã được lưu." :
        action === "start" ? "Đã bắt đầu tính thời gian học thực tế." :
        action === "pause" ? "Đã tạm dừng và lưu thời gian học." :
        action === "resume" ? "Đã tiếp tục phiên học trước đó." :
        "Đã lưu thời gian hoạt động.";
    } catch (error) {
      notice.textContent = error.message;
      // If the server detected a stale timer or changed syllabus, do not
      // keep displaying an optimistic running timer.
      await syncStatusAfterError();
    } finally {
      inFlight = false;
      render();
    }
  }
  async function syncStatusAfterError() {
    try { consume(await api()); }
    catch (_error) { state = "paused"; }
  }

  for (const action of ["start", "pause", "resume", "finish"]) {
    controls[action]?.addEventListener("click", () => sendAction(action));
  }
  window.setInterval(() => {
    if (!document.hidden && !inFlight && state === "running") sendAction("heartbeat");
  }, 15000);
  window.setInterval(render, 1000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) sync();
    else render();
  });
  window.addEventListener("focus", () => { if (!document.hidden) sync(); });
  sync();
});
