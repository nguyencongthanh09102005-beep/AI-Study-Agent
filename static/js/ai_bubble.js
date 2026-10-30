/* Phase 6.3.3 — one floating, draggable assistant across student pages.
   Uses the existing /api/chat and conversation records. No other chat backend.
   Verified lesson mode is never silently downgraded to free chat. */
document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("floatingAiRoot");
  if (!root) return;
  const bubble = document.getElementById("floatingAiBubble");
  const panel = document.getElementById("floatingAiPanel");
  const close = document.getElementById("floatingAiClose");
  const expandButton = document.getElementById("floatingAiExpand");
  const resetSizeButton = document.getElementById("floatingAiResetSize");
  const resizeHandle = document.getElementById("floatingAiResize");
  const scope = document.getElementById("floatingAiScope");
  const mode = document.getElementById("floatingAiMode");
  const courseLabel = document.getElementById("floatingAiCourseLabel");
  const courseSelect = document.getElementById("floatingAiCourse");
  const messages = document.getElementById("floatingAiMessages");
  const form = document.getElementById("floatingAiForm");
  const input = document.getElementById("floatingAiInput");
  const send = document.getElementById("floatingAiSend");
  const status = document.getElementById("floatingAiStatus");
  const fullLink = document.getElementById("floatingAiFullChat");
  const lessonNode = document.getElementById("studyRoomAiContext");
  const isLesson = !!lessonNode;
  const lesson = isLesson ? {
    taskId: Number(lessonNode.dataset.taskId),
    subjectId: Number(lessonNode.dataset.subjectId),
    chapter: Number(lessonNode.dataset.chapterNumber),
    title: lessonNode.dataset.lessonTitle || "Buổi học",
    ready: lessonNode.dataset.chatEnabled === "1"
  } : null;

  const STORAGE_KEY = "ai-study-floating-position-v1";
  const SIZE_KEY = "ai-study-floating-size-v1";
  let position = null, pointer = null, ignoreClick = false;
  let panelSize = {width: 420, height: 640}, expanded = false, resizePointer = null;
  let loaded = false, busy = false, disabled = true, requestToken = 0;
  let conversationId = null, subjectId = null;
  let courses = [], approvedSourceNames = [];

  const number = n => Number.isSafeInteger(n) && n > 0;
  function setStatus(value) { status.textContent = value; }
  function setMode(value, warning = false) {
    mode.textContent = value;
    mode.classList.toggle("warning", warning);
  }
  function enable(value) {
    disabled = !value;
    input.disabled = disabled || busy;
    send.disabled = disabled || busy;
    courseSelect.disabled = busy;
  }
  async function api(url, options = {}) {
    const response = await fetch(url, {credentials: "same-origin", ...options});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "Không thể kết nối Chat AI.");
    return body;
  }
  function clear() { messages.replaceChildren(); }
  function empty(value) {
    clear();
    const el = document.createElement("p");
    el.className = "floating-ai-empty";
    el.textContent = value;
    messages.appendChild(el);
  }
  function appendMessage(role, value) {
    messages.querySelector(".floating-ai-empty")?.remove();
    const box = document.createElement("article");
    box.className = "floating-ai-message " + role;
    const heading = document.createElement("strong");
    heading.textContent = role === "user" ? "Bạn" : role === "error" ? "Thông báo" : "AI Study Agent";
    const body = document.createElement("div");
    body.className = "floating-ai-message-body" +
      (role === "assistant" ? " chat-markdown" : "");
    // Only the application's shared escape-first renderer may create markup.
    // Neither user text nor untrusted file/model HTML is used as raw HTML.
    if (role === "assistant" && window.ChatMarkdown?.render) {
      body.innerHTML = window.ChatMarkdown.render(String(value || ""));
    } else {
      body.textContent = String(value || "");
    }
    box.append(heading, body);
    if (role === "assistant" && isLesson && approvedSourceNames.length) {
      const references = document.createElement("div");
      references.className = "floating-ai-sources";
      const title = document.createElement("strong");
      title.textContent = "Học liệu đã xác thực:";
      references.appendChild(title);
      for (const name of approvedSourceNames) {
        const link = [...document.querySelectorAll("[data-ai-approved-source]")].find(
          item => item.dataset.aiApprovedSource === name
        );
        if (!link) continue;
        const anchor = document.createElement("a");
        anchor.href = link.href;  // URL comes from the server-rendered approved document.
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        anchor.textContent = name + " ↗";
        references.appendChild(anchor);
      }
      if (references.querySelector("a")) box.appendChild(references);
    }
    messages.appendChild(box);
    messages.scrollTop = messages.scrollHeight;
  }
  const scheduleFeature = window.FloatingAiSchedule?.attach({
    messages,
    actionButton: document.getElementById("floatingAiScheduleButton"),
    getConversationId: () => conversationId,
    getSubjectId: () => subjectId || (isLesson ? lesson.subjectId : null),
    appendMessage,
    setStatus
  });

  function renderHistory(rows) {
    clear();
    if (!Array.isArray(rows) || !rows.length) {
      empty(isLesson
        ? "Hỏi AI về nội dung của buổi học này. AI chỉ sử dụng học liệu chung đã được duyệt."
        : "Bắt đầu trò chuyện về môn học đã chọn.");
      return;
    }
    rows.forEach(item => appendMessage(item.role === "user" ? "user" : "assistant", item.content));
  }
  function fullChatFor(id, chapter) {
    const params = new URLSearchParams();
    if (number(id)) params.set("subject_id", String(id));
    if (number(chapter)) params.set("chapter_number", String(chapter));
    fullLink.href = "/chat" + (params.size ? "?" + params : "");
  }

  async function loadLesson() {
    courseLabel.hidden = true;
    scope.textContent = lesson.title + " · Chương " + lesson.chapter;
    // If chapter sources are unavailable, the full Chat link opens free mode.
    fullChatFor(lesson.subjectId, lesson.ready ? lesson.chapter : null);
    if (!lesson.ready) {
      enable(false);
      setMode("Chưa đủ học liệu chung được Admin duyệt. Chat theo buổi không khả dụng; có thể mở Chat AI đầy đủ.", true);
      setStatus("Chưa có nguồn được duyệt");
      empty("Tài liệu cá nhân vẫn có thể đọc trong Không gian học tập. Chat theo buổi sẽ bật khi có học liệu chung được duyệt.");
      return;
    }
    if (![lesson.taskId, lesson.subjectId, lesson.chapter].every(number)) {
      enable(false); setStatus("Mã buổi học không hợp lệ");
      return;
    }
    const token = ++requestToken;
    enable(false);
    setMode("Đang kiểm tra học liệu và quyền truy cập của buổi học...");
    setStatus("Đang tải...");
    try {
      const data = await api("/api/study-plan/tasks/" + lesson.taskId + "/chat-history");
      if (token !== requestToken) return;
      if (data.session_task_id !== lesson.taskId ||
          data.subject_id !== lesson.subjectId ||
          data.chapter_number !== lesson.chapter ||
          !number(data.conversation_id)) {
        throw new Error("Phản hồi không khớp môn, chương hoặc buổi học.");
      }
      conversationId = data.conversation_id;
      subjectId = data.subject_id;
      approvedSourceNames = Array.isArray(data.source_names) ? data.source_names : [];
      renderHistory(data.messages);
      setMode("✓ Học theo buổi · Nguồn chung đã duyệt · Có dẫn chứng");
      setStatus("Sẵn sàng");
      enable(true);
    } catch (error) {
      conversationId = null;
      approvedSourceNames = [];
      enable(false);
      setMode("Không thể xác thực nguồn buổi học.", true);
      empty(error.message + " Hãy rà soát đề cương hoặc tài liệu chương.");
      setStatus("Tạm khóa để bảo vệ nguồn");
    }
  }

  function pageSubjectHint() {
    const match = location.pathname.match(/\/subjects\/(\d+)(?:\/|$)/);
    const query = new URLSearchParams(location.search).get("subject_id");
    const parsed = Number(match?.[1] || query);
    return number(parsed) ? parsed : null;
  }
  async function selectCourse(id) {
    scheduleFeature?.reset();
    const chosen = courses.find(c => Number(c.subject_id) === Number(id));
    const token = ++requestToken;
    conversationId = null;
    enable(false);
    clear();
    if (!chosen) {
      setMode("Hãy chọn một môn học để hỏi AI.", true);
      empty("Chưa chọn môn học.");
      setStatus("Chưa chọn môn");
      fullChatFor(null, null);
      return;
    }
    subjectId = chosen.subject_id;
    scope.textContent = chosen.title;
    courseSelect.value = String(subjectId);
    fullChatFor(subjectId, null);
    setMode("Hỏi đáp tự do trong môn " + chosen.title + ". Không tự sửa kế hoạch học.");
    setStatus("Đang tải lịch sử...");
    try {
      const history = await api("/api/chats/" + chosen.id + "/messages");
      if (token !== requestToken) return;
      conversationId = chosen.id;
      renderHistory(history);
      setStatus("Sẵn sàng");
      enable(true);
    } catch (error) {
      if (token !== requestToken) return;
      empty(error.message);
      setStatus("Không tải được Chat");
    }
  }
  async function loadGeneral() {
    courseLabel.hidden = false;
    enable(false);
    setStatus("Đang tải môn...");
    setMode("Chọn môn học. Chat nhanh dùng chung cuộc hội thoại với trang Chat AI.");
    try {
      const data = await api("/api/chats");
      courses = Array.isArray(data) ? data.filter(c => number(c.id) && number(c.subject_id)) : [];
      courseSelect.replaceChildren();
      if (!courses.length) {
        empty("Bạn chưa có môn học. Hãy tạo môn trước khi hỏi AI.");
        setMode("Chưa có môn học.", true);
        return;
      }
      for (const course of courses) {
        const option = document.createElement("option");
        option.value = String(course.subject_id);
        option.textContent = course.title;
        courseSelect.appendChild(option);
      }
      const match = courses.find(c => c.subject_id === pageSubjectHint());
      await selectCourse(match?.subject_id || courses[0].subject_id);
    } catch (error) {
      empty(error.message);
      setStatus("Không tải được môn");
    }
  }
  async function initialize() {
    if (loaded) return;
    loaded = true;
    if (isLesson) await loadLesson();
    else await loadGeneral();
  }

  function openPanel() {
    applyPanelSize();
    bubble.hidden = true;
    panel.hidden = false;
    bubble.setAttribute("aria-expanded", "true");
    root.dataset.side = (position?.x || 0) + 70 < window.innerWidth / 2 ? "left" : "right";
    initialize();
    window.requestAnimationFrame(() => {
      if (!input.disabled) input.focus({preventScroll:true});
      else close.focus({preventScroll:true});
    });
  }
  function closePanel() {
    panel.hidden = true;
    bubble.hidden = false;
    bubble.setAttribute("aria-expanded", "false");
    bubble.focus({preventScroll:true});
  }
  close.addEventListener("click", closePanel);
  window.addEventListener("keydown", e => {
    if (e.key === "Escape" && !panel.hidden) closePanel();
  });
  document.querySelectorAll("[data-open-floating-ai]").forEach(button =>
    button.addEventListener("click", openPanel)
  );

  function clamp(n, min, max) { return Math.max(min, Math.min(max, n)); }

  // The popup is always viewport-bounded. On small screens it is fullscreen,
  // and we keep the custom desktop dimensions for when the screen grows again.
  function mobilePanel() { return window.innerWidth <= 600; }
  function boundedPanelSize(size) {
    const maxWidth = Math.max(1, window.innerWidth - 32);
    const maxHeight = Math.max(1, window.innerHeight - 32);
    return {
      width: Math.round(clamp(size.width, Math.min(340, maxWidth), maxWidth)),
      height: Math.round(clamp(size.height, Math.min(310, maxHeight), maxHeight))
    };
  }
  function savePanelSize() {
    try {
      localStorage.setItem(SIZE_KEY, JSON.stringify({
        width: panelSize.width, height: panelSize.height, expanded
      }));
    } catch (_error) { /* Privacy mode: resize still works for this page. */ }
  }
  function applyPanelSize() {
    if (mobilePanel()) {
      panel.style.removeProperty("width");
      panel.style.removeProperty("height");
    } else {
      const chosen = expanded
        ? {width: Math.min(1100, window.innerWidth - 32),
           height: window.innerHeight - 32}
        : panelSize;
      const size = boundedPanelSize(chosen);
      panel.style.width = size.width + "px";
      panel.style.height = size.height + "px";
    }
    expandButton?.setAttribute("aria-pressed", String(expanded));
    if (expandButton) {
      expandButton.textContent = expanded ? "▢" : "⛶";
      expandButton.setAttribute("aria-label", expanded
        ? "Trở về kích thước Chat AI tùy chỉnh" : "Mở rộng cửa sổ Chat AI");
      expandButton.title = expanded ? "Trở về kích thước trước" : "Mở rộng để đọc bảng";
    }
  }
  function usePanelSize(width, height) {
    expanded = false;
    const size = boundedPanelSize({width, height});
    panelSize = size;
    applyPanelSize();
  }
  try {
    const saved = JSON.parse(localStorage.getItem(SIZE_KEY));
    if (Number.isFinite(saved?.width) && Number.isFinite(saved?.height) &&
        saved.width >= 300 && saved.height >= 280 &&
        saved.width <= 10000 && saved.height <= 10000) {
      panelSize = {width: saved.width, height: saved.height};
      expanded = saved.expanded === true;
    }
  } catch (_error) { /* Stored dimensions may be unavailable or malformed. */ }
  applyPanelSize();

  expandButton?.addEventListener("click", () => {
    if (mobilePanel()) return;
    expanded = !expanded;
    applyPanelSize();
    savePanelSize();
  });
  resetSizeButton?.addEventListener("click", () => {
    if (mobilePanel()) return;
    panelSize = {width: 420, height: 640};
    expanded = false;
    applyPanelSize();
    savePanelSize();
  });
  resizeHandle?.addEventListener("pointerdown", event => {
    if (event.button !== 0 || mobilePanel()) return;
    const bounds = panel.getBoundingClientRect();
    resizePointer = {
      id: event.pointerId, x: event.clientX, y: event.clientY,
      width: bounds.width, height: bounds.height,
      leftSide: root.dataset.side === "left", moved: false
    };
    resizeHandle.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });
  resizeHandle?.addEventListener("pointermove", event => {
    if (!resizePointer || resizePointer.id !== event.pointerId) return;
    const dx = event.clientX - resizePointer.x;
    const dy = event.clientY - resizePointer.y;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) resizePointer.moved = true;
    if (!resizePointer.moved) return;
    event.preventDefault();
    usePanelSize(
      resizePointer.width + (resizePointer.leftSide ? dx : -dx),
      resizePointer.height - dy
    );
  });
  function finishResize(event) {
    if (!resizePointer || resizePointer.id !== event.pointerId) return;
    if (resizePointer.moved) savePanelSize();
    if (resizeHandle?.hasPointerCapture?.(event.pointerId)) {
      resizeHandle.releasePointerCapture(event.pointerId);
    }
    resizePointer = null;
  }
  resizeHandle?.addEventListener("pointerup", finishResize);
  resizeHandle?.addEventListener("pointercancel", finishResize);
  resizeHandle?.addEventListener("keydown", event => {
    if (mobilePanel()) return;
    const step = event.shiftKey ? 64 : 24;
    const keys = {
      ArrowRight: [step, 0], ArrowLeft: [-step, 0],
      ArrowUp: [0, step], ArrowDown: [0, -step]
    };
    if (event.key === "Home") {
      event.preventDefault();
      panelSize = {width: 420, height: 640};
      expanded = false;
      applyPanelSize();
      savePanelSize();
      return;
    }
    if (!keys[event.key]) return;
    event.preventDefault();
    const current = panel.getBoundingClientRect();
    usePanelSize(current.width + keys[event.key][0],
                 current.height + keys[event.key][1]);
    savePanelSize();
  });

  function place(x, y) {
    const edge = 10;
    const size = bubble.offsetWidth || 62;
    const maxX = Math.max(edge, innerWidth - size - edge);
    const maxY = Math.max(edge, innerHeight - size - edge);
    position = { x: clamp(x, edge, maxX), y: clamp(y, edge, maxY) };
    bubble.style.left = position.x + "px";
    bubble.style.top = position.y + "px";
    bubble.style.right = "auto";
    bubble.style.bottom = "auto";
    root.dataset.side = position.x + size/2 < innerWidth/2 ? "left" : "right";
  }
  function remember() {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(position)); }
    catch (_error) { /* Restricted storage: dragging still works. */ }
  }
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY));
    if (Number.isFinite(saved?.x) && Number.isFinite(saved?.y)) place(saved.x,saved.y);
  } catch (_error) { /* Fresh session or restricted storage */ }
  if (!position) place(innerWidth - (bubble.offsetWidth || 62) - 22,
                        innerHeight - (bubble.offsetHeight || 62) - 22);

  bubble.addEventListener("pointerdown", e => {
    if (e.button !== 0 || !panel.hidden) return;
    pointer = {id:e.pointerId, x:e.clientX, y:e.clientY,
               originX:position.x, originY:position.y, moved:false};
    bubble.setPointerCapture?.(e.pointerId);
  });
  bubble.addEventListener("pointermove", e => {
    if (!pointer || pointer.id !== e.pointerId) return;
    const dx = e.clientX-pointer.x, dy=e.clientY-pointer.y;
    if (Math.hypot(dx,dy)>6) pointer.moved=true;
    if (pointer.moved) {
      e.preventDefault();
      place(pointer.originX + dx, pointer.originY + dy);
    }
  });
  function finishPointer(e) {
    if (!pointer || pointer.id!==e.pointerId) return;
    if (pointer.moved) {
      ignoreClick=true;
      const size=bubble.offsetWidth || 62;
      place(position.x+size/2 < innerWidth/2 ? 12 : innerWidth-size-12, position.y);
      remember();
    }
    if (bubble.hasPointerCapture?.(e.pointerId)) bubble.releasePointerCapture(e.pointerId);
    pointer=null;
  }
  bubble.addEventListener("pointerup", finishPointer);
  bubble.addEventListener("pointercancel", finishPointer);
  bubble.addEventListener("click", e => {
    if (ignoreClick) {
      ignoreClick=false; e.preventDefault(); return;
    }
    if (!pointer) openPanel();
  });
  window.addEventListener("resize", () => {
    if (position) place(position.x,position.y);
    applyPanelSize();
  });
  courseSelect.addEventListener("change", () => {
    if (!busy && !isLesson) selectCourse(Number(courseSelect.value));
  });

  form.addEventListener("submit", async e => {
    e.preventDefault();
    const question = input.value.trim();
    if (busy || disabled || !number(conversationId) || !question) return;
    if (scheduleFeature?.isRequest(question)) {
      appendMessage("user", question);
      input.value = "";
      await scheduleFeature.open();
      return;
    }
    const canResume = !disabled;
    let invalidated = false;
    busy = true; enable(false);
    const conversation = conversationId;
    const sentFor = subjectId;
    appendMessage("user",question);
    input.value="";
    setStatus("AI đang trả lời...");
    try {
      const payload = {
        conversation_id:conversation, question,
        ...(isLesson ? {lesson:{chapter_number:lesson.chapter,task_id:lesson.taskId}} : {})
      };
      const data = await api("/api/chat", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload)
      });
      if (isLesson && (data.source_mode!=="chapter" ||
          data.lesson?.session_task_id !== lesson.taskId ||
          data.lesson?.chapter_number !== lesson.chapter)) {
        throw new Error("Phản hồi không được xác thực cho đúng buổi học.");
      }
      if (sentFor !== subjectId || conversation !== conversationId) return;
      appendMessage("assistant", data.answer || "Chưa có câu trả lời.");
      setStatus("Sẵn sàng");
    } catch (error) {
      appendMessage("error",error.message);
      setStatus("Không gửi được câu hỏi");
      if (isLesson && /nguồn|thay đổi|đề cương|học liệu|chương/i.test(error.message)) {
        invalidated = true;
        setMode("Nguồn học liệu có thể đã thay đổi. Hãy tải lại phòng học.",true);
      }
    } finally {
      busy=false;
      enable(canResume && !invalidated);
      if (!input.disabled && !panel.hidden) input.focus({preventScroll:true});
    }
  });
});
