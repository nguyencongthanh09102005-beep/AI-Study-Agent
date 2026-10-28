document.addEventListener("DOMContentLoaded", () => {
  const messagesBox = document.getElementById("chatMessages");
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("chatSendButton");
  const historyList = document.querySelector(".sidebar-course-list .chat-history-list");
  const mobileSubjectPicker = document.getElementById("chatMobileSubject");
  const subjectNameEl = document.getElementById("chatSubjectName");
  const contextStatusEl = document.getElementById("chatContextStatus");
  const lessonBanner = document.getElementById("lessonModeBanner");
  const lessonTitle = document.getElementById("lessonModeTitle");
  const lessonSources = document.getElementById("lessonModeSources");
  const modeFreeButton = document.getElementById("chatModeFree");
  const modeChapterButton = document.getElementById("chatModeChapter");
  const chapterControls = document.getElementById("chatChapterControls");
  const modeNotice = document.getElementById("chatModeNotice");
  const courseSelector = document.getElementById("chatCourseSelect");
  const chapterSelector = document.getElementById("chatChapterSelect");
  const topicSelector = document.getElementById("chatTopicSelect");

  let chats = [];
  let currentChatId = null;
  let currentMessages = [];
  let sending = false;
  let lessonMode = null;
  let chatMode = "free";
  let chapterOptions = [];
  let modeError = "";
  let modeSeq = 0;

  function updateLessonUI() {
    const current = getCurrentChat();
    const active = chatMode === "chapter" && lessonMode && current &&
      Number(current.subject_id) === Number(lessonMode.subject_id);
    modeFreeButton?.classList.toggle("active", chatMode === "free");
    modeChapterButton?.classList.toggle("active", chatMode === "chapter");
    modeFreeButton?.setAttribute("aria-pressed", String(chatMode === "free"));
    modeChapterButton?.setAttribute("aria-pressed", String(chatMode === "chapter"));
    if (chapterControls) chapterControls.hidden = chatMode !== "chapter";
    if (lessonBanner) lessonBanner.hidden = !active;
    if (active) {
      if (lessonTitle) lessonTitle.textContent =
        lessonMode.chapter + " · " + lessonMode.topic;
      if (lessonSources) lessonSources.textContent =
        "Học liệu đã duyệt: " + lessonMode.source_names.join(", ");
    }
    if (modeNotice) {
      modeNotice.hidden = chatMode !== "chapter" || !modeError;
      modeNotice.textContent = modeError;
    }
    if (modeFreeButton) modeFreeButton.disabled = sending;
    if (modeChapterButton) modeChapterButton.disabled = sending;
    for (const selector of [courseSelector,chapterSelector,topicSelector]) {
      if (selector) selector.disabled = sending ||
        (selector !== courseSelector && !chapterOptions.length);
    }
    if (chatMode === "chapter" && !active) {
      if (input) input.disabled = true;
      if (sendBtn) sendBtn.disabled = true;
    }
  }

  function clearLessonMode() {
    modeSeq += 1;
    chatMode = "free";
    lessonMode = null;
    modeError = "";
    chapterOptions = [];
    const url = new URL(window.location.href);
    url.searchParams.delete("chapter_number");
    url.searchParams.delete("topic_index");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    updateChatHeader();
    updateLessonUI();
  }

  function updateLessonUrl() {
    if (!lessonMode) return;
    const url = new URL(window.location.href);
    url.searchParams.set("subject_id", String(lessonMode.subject_id));
    url.searchParams.set("chapter_number", String(lessonMode.chapter_number));
    url.searchParams.set("topic_index", String(lessonMode.topic_index));
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  function fillSelect(selector, items, selected) {
    if (!selector) return;
    selector.replaceChildren();
    items.forEach(item => {
      const option = document.createElement("option");
      option.value = String(item.value);
      option.textContent = item.label;
      selector.appendChild(option);
    });
    if (selected != null && items.some(x => String(x.value) === String(selected))) {
      selector.value = String(selected);
    }
  }

  function renderModeCourses() {
    fillSelect(courseSelector, chats.map(item => ({
      value: item.id, label: item.title
    })), currentChatId);
  }

  function renderChapterOptions(requested) {
    const chapters = chapterOptions;
    const chosen = chapters.find(x => x.chapter_number === Number(requested)) ||
      chapters.find(x => x.available) || chapters[0];
    fillSelect(chapterSelector, chapters.map(c => ({
      value: c.chapter_number,
      label: c.title + (c.available ? "" : " · Chưa có học liệu")
    })), chosen?.chapter_number);
    return chosen;
  }

  function renderTopicOptions(requested) {
    const chapter = chapterOptions.find(
      item => item.chapter_number === Number(chapterSelector?.value)
    );
    const topics = chapter?.topics || [];
    fillSelect(topicSelector, topics.map((title, i) => ({
      value: i, label: title
    })), requested);
  }

  async function validateSelectedLesson() {
    if (chatMode !== "chapter" || sending) return;
    const seq = ++modeSeq;
    lessonMode = null;
    modeError = "";
    const current = getCurrentChat();
    const chapterNumber = Number(chapterSelector?.value);
    const topicIndex = Number(topicSelector?.value);
    const chosen = chapterOptions.find(c => c.chapter_number === chapterNumber);
    if (!current || !chosen) {
      modeError = "Môn này chưa có chương đã xác nhận.";
      updateChatHeader(); updateLessonUI();
      return;
    }
    if (!chosen.available) {
      modeError = "Chương này chưa có học liệu được Admin duyệt. Hãy chọn chương khác hoặc yêu cầu Admin bổ sung.";
      updateChatHeader(); updateLessonUI();
      return;
    }
    const params = new URLSearchParams({
      subject_id: String(current.subject_id),
      chapter_number: String(chapterNumber),
      topic_index: String(topicIndex)
    });
    try {
      const detail = await api("/api/chat/lesson-context?" + params.toString());
      if (seq !== modeSeq || chatMode !== "chapter" ||
          getCurrentChat()?.subject_id !== detail.subject_id) return;
      lessonMode = detail;
      updateLessonUrl();
      modeError = "";
    } catch (error) {
      if (seq !== modeSeq) return;
      modeError = error.message;
    }
    updateChatHeader();
    updateLessonUI();
  }

  async function enterChapterMode(requestedChapter = null, requestedTopic = 0) {
    if (sending) return;
    chatMode = "chapter";
    lessonMode = null;
    chapterOptions = [];
    modeError = "";
    const seq = ++modeSeq;
    const current = getCurrentChat();
    updateChatHeader();
    updateLessonUI();
    if (!current) {
      modeError = "Hãy tạo hoặc chọn một môn học trước.";
      updateLessonUI();
      return;
    }
    renderModeCourses();
    try {
      const data = await api("/api/chat/course-outline?subject_id=" +
        encodeURIComponent(current.subject_id));
      if (seq !== modeSeq || chatMode !== "chapter" ||
          getCurrentChat()?.subject_id !== data.subject_id) return;
      chapterOptions = data.chapters || [];
      renderChapterOptions(requestedChapter);
      renderTopicOptions(requestedTopic);
      await validateSelectedLesson();
    } catch (error) {
      if (seq !== modeSeq) return;
      modeError = error.message;
      updateChatHeader(); updateLessonUI();
    }
  }

  async function initLessonMode() {
    const params = new URLSearchParams(window.location.search);
    if (!params.has("chapter_number")) {
      updateLessonUI();
      return;
    }
    await enterChapterMode(
      Number(params.get("chapter_number")),
      Number(params.get("topic_index") || 0)
    );
  }

  modeFreeButton?.addEventListener("click", () => {
    if (!sending) clearLessonMode();
  });
  modeChapterButton?.addEventListener("click", () => {
    if (!sending) enterChapterMode();
  });
  courseSelector?.addEventListener("change", async () => {
    const choice = chats.find(item => item.id === Number(courseSelector.value));
    if (!choice) return;
    try {
      await switchToChat(choice);
    } catch (error) {
      modeError = error.message;
      updateLessonUI();
    }
  });
  chapterSelector?.addEventListener("change", () => {
    renderTopicOptions(0);
    validateSelectedLesson();
  });
  topicSelector?.addEventListener("change", validateSelectedLesson);

  async function api(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;

    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }

    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }

    return data;
  }

  function getCurrentChat() {
    return chats.find(chat => chat.id === Number(currentChatId));
  }

  function focusInputWithoutScroll() {
    if (!input || input.disabled) return;

    try {
      input.focus({ preventScroll: true });
    } catch (error) {
      input.focus();
    }
  }

  function updateChatHeader() {
    const chat = getCurrentChat();

    if (!chat) {
      if (subjectNameEl) subjectNameEl.textContent = "AI Study Agent";
      if (contextStatusEl) {
        contextStatusEl.innerHTML = "<i></i> Chọn một môn học để bắt đầu";
      }
      if (input) {
        input.disabled = true;
        input.placeholder = "Chưa có môn học để trò chuyện...";
      }
      if (sendBtn) sendBtn.disabled = true;
      updateLessonUI();
      return;
    }

    if (subjectNameEl) {
      subjectNameEl.textContent = `AI Chat · ${chat.title}`;
    }
    if (lessonMode && Number(chat.subject_id) === Number(lessonMode.subject_id)) {
      if (contextStatusEl) {
        contextStatusEl.textContent = "Đang học · " + lessonMode.chapter +
          " · " + lessonMode.topic;
      }
      if (input) {
        input.disabled = false;
        input.placeholder = "Nhập tin nhắn...";
      }
      if (sendBtn) sendBtn.disabled = false;
      updateLessonUI();
      return;
    }

    if (chatMode === "chapter") {
      if (contextStatusEl) contextStatusEl.textContent =
        "Học theo chương · Chọn chương và tiểu mục";
      if (input) input.disabled = true;
      if (sendBtn) sendBtn.disabled = true;
      updateLessonUI();
      return;
    }

    if (contextStatusEl) {
      if (chat.document_count > 0) {
        contextStatusEl.innerHTML =
          `<i></i> ${chat.document_count} tài liệu · ưu tiên tài liệu của môn này`;
      } else {
        contextStatusEl.innerHTML =
          "<i></i> Chưa có tài liệu · trả lời bằng kiến thức chung";
      }
    }

    if (input) {
      input.disabled = false;
      input.placeholder = "Nhập tin nhắn...";
    }

    if (sendBtn) sendBtn.disabled = false;
    updateLessonUI();
  }

  function welcomeForCurrentSubject() {
    const chat = getCurrentChat();

    if (!chat) {
      return {
        role: "assistant",
        content:
          "Bạn chưa có môn học nào. Hãy tạo môn học trước; hệ thống sẽ tự tạo một không gian AI Chat cùng tên môn."
      };
    }

    if (chat.document_count > 0) {
      return {
        role: "assistant",
        content:
          `Đây là AI Chat của môn ${chat.title}. Hiện có ${chat.document_count} tài liệu được gắn với môn này. Khi tài liệu hỗ trợ câu hỏi, mình sẽ ưu tiên trả lời dựa trên tài liệu và ghi rõ tên file; nếu tài liệu không đủ, mình sẽ trả lời bằng kiến thức chung.`
      };
    }

    return {
      role: "assistant",
      content:
        `Đây là AI Chat của môn ${chat.title}. Môn này chưa có tài liệu, nên hiện tại mình sẽ trả lời bằng kiến thức chung. Khi bạn tải tài liệu và gắn vào ${chat.title}, mình sẽ tự ưu tiên nội dung trong các file đó.`
    };
  }

  async function loadChats(selectId = null) {
    chats = await api("/api/chats");

    const requestedSubjectId = Number(
      new URLSearchParams(window.location.search).get("subject_id")
    );

    if (selectId && chats.some(chat => chat.id === Number(selectId))) {
      currentChatId = Number(selectId);
    } else if (
      requestedSubjectId &&
      chats.some(chat => chat.subject_id === requestedSubjectId)
    ) {
      currentChatId = chats.find(chat => chat.subject_id === requestedSubjectId).id;
    } else if (!chats.some(chat => chat.id === Number(currentChatId))) {
      currentChatId = chats[0]?.id || null;
    }

    renderSubjectChats();
    renderModeCourses();
    updateChatHeader();

    if (currentChatId) {
      await loadMessages(currentChatId);
    } else {
      currentMessages = [];
      renderCurrentChat();
    }
  }

  async function loadMessages(chatId) {
    const messages = await api(`/api/chats/${chatId}/messages`);
    if (Number(currentChatId) !== Number(chatId)) return;
    currentMessages = messages;
    renderCurrentChat();
  }

  function rememberSelectedSubject(subjectId) {
    const url = new URL(window.location.href);
    url.searchParams.set("subject_id", String(subjectId));
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  async function switchToChat(chat) {
    if (!chat || sending) return;
    const moving = getCurrentChat()?.subject_id !== chat.subject_id;
    const preserveChapterMode = chatMode === "chapter";
    if (moving) {
      modeSeq += 1;
      lessonMode = null;
      chapterOptions = [];
      modeError = "";
      const url = new URL(window.location.href);
      url.searchParams.delete("chapter_number");
      url.searchParams.delete("topic_index");
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    }
    currentChatId = chat.id;
    rememberSelectedSubject(chat.subject_id);
    messagesBox?.classList.remove("chat-subject-enter");
    renderSubjectChats();
    updateChatHeader();
    await loadMessages(chat.id);
    if (getCurrentChat()?.id === chat.id) {
      messagesBox?.classList.add("chat-subject-enter");
    }
    if (preserveChapterMode && moving) await enterChapterMode();
    else renderModeCourses();
    focusInputWithoutScroll();
  }

  function renderMobileSubjectPicker() {
    if (!mobileSubjectPicker) return;
    mobileSubjectPicker.replaceChildren();
    for (const chat of chats) {
      const option = document.createElement("option");
      option.value = String(chat.id);
      option.textContent = chat.title;
      mobileSubjectPicker.appendChild(option);
    }
    if (currentChatId != null) {
      mobileSubjectPicker.value = String(currentChatId);
    }
    mobileSubjectPicker.disabled = !chats.length || sending;
  }

  mobileSubjectPicker?.addEventListener("change", async () => {
    const chat = chats.find(item => item.id === Number(mobileSubjectPicker.value));
    try {
      await switchToChat(chat);
    } catch (error) {
      console.error("Không chuyển được môn Chat AI:", error);
      renderMobileSubjectPicker();
    }
  });

  function renderSubjectChats() {
    if (!historyList) return;
    historyList.innerHTML = "";

    if (!chats.length) {
      renderMobileSubjectPicker();
      historyList.innerHTML = `
        <div class="subject-chat-empty">
          <span>📘</span>
          <strong>Chưa có môn học</strong>
          <small>Tạo môn ở trang Môn học để bắt đầu Chat AI.</small>
          <a href="/subjects">Tạo môn học</a>
        </div>
      `;
      return;
    }

    chats.forEach(chat => {
      const item = document.createElement("button");
      item.type = "button";
      item.className =
        "chat-history-item subject-chat-item" +
        (chat.id === Number(currentChatId) ? " active" : "");

      item.innerHTML = `
        <span class="history-icon">📘</span>
        <span class="history-text">
          <strong>${escapeHtml(chat.title)}</strong>
          <small>
            ${chat.document_count} tài liệu
            ${chat.message_count ? ` · ${chat.message_count} tin nhắn` : ""}
          </small>
        </span>
      `;

      item.addEventListener("click", async () => {
        try {
          await switchToChat(chat);
        } catch (error) {
          console.error("Không chuyển được môn Chat AI:", error);
        }
      });

      historyList.appendChild(item);
    });
    renderMobileSubjectPicker();
    renderModeCourses();
  }

  function renderCurrentChat() {
    if (!messagesBox) return;
    messagesBox.innerHTML = "";

    const messages = currentMessages.length
      ? currentMessages
      : [welcomeForCurrentSubject()];

    messages.forEach(message => {
      const wrapper = document.createElement("div");

      if (message.role === "user") {
        wrapper.className = "chat-message user-message";
        wrapper.innerHTML = `
          <div class="message-body">
            <div class="message-name">Bạn</div>
            <div class="message-bubble">${escapeHtml(message.content)}</div>
          </div>
          <div class="message-avatar user-avatar">👤</div>
        `;
      } else {
        wrapper.className = "chat-message ai-message";
        wrapper.innerHTML = `
          <div class="message-avatar">🤖</div>
          <div class="message-body">
            <div class="message-name">AI Study Agent</div>
            <div class="message-bubble chat-markdown">${window.ChatMarkdown?.render(message.content) ?? escapeHtml(message.content)}</div>
            ${currentMessages.length ? `
              <div class="message-tools">
                <button type="button" class="copy-message">📋 Sao chép</button>
              </div>
            ` : ""}
          </div>
        `;
      }

      messagesBox.appendChild(wrapper);
    });

    requestAnimationFrame(() => {
      messagesBox.scrollTop = messagesBox.scrollHeight;
    });

    bindCopyButtons();
  }

  function showLoading() {
    const loading = document.createElement("div");
    loading.className = "chat-message ai-message";
    loading.id = "aiLoading";
    loading.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-body">
        <div class="message-name">AI Study Agent</div>
        <div class="message-bubble typing-bubble">
          <span></span><span></span><span></span>
        </div>
      </div>
    `;
    messagesBox?.appendChild(loading);

    requestAnimationFrame(() => {
      if (messagesBox) messagesBox.scrollTop = messagesBox.scrollHeight;
    });
  }

  async function sendMessage() {
    if (!input || sending || !currentChatId) return;

    const text = input.value.trim();
    if (!text) return;

    sending = true;
    if (sendBtn) sendBtn.disabled = true;
    if (mobileSubjectPicker) mobileSubjectPicker.disabled = true;
    updateLessonUI();
    historyList?.querySelectorAll("button.subject-chat-item").forEach(button => {
      button.disabled = true;
    });

    input.value = "";
    input.style.height = "auto";

    currentMessages.push({ role: "user", content: text });
    renderCurrentChat();
    showLoading();

    try {
      const data = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: currentChatId,
          question: text,
          ...(lessonMode ? {
            lesson: {
              chapter_number: lessonMode.chapter_number,
              topic_index: lessonMode.topic_index
            }
          } : {})
        })
      });

      document.getElementById("aiLoading")?.remove();

      currentMessages.push({
        role: "assistant",
        content: data.answer || "AI chưa trả về nội dung."
      });

      renderCurrentChat();

      // Refresh số tài liệu/tin nhắn nhưng vẫn giữ đúng môn đang chat.
      await loadChats(currentChatId);
    } catch (error) {
      document.getElementById("aiLoading")?.remove();

      currentMessages.push({
        role: "assistant",
        content: `Không thể gửi câu hỏi lúc này. ${error.message}`
      });

      renderCurrentChat();
    } finally {
      sending = false;
      if (sendBtn && currentChatId) sendBtn.disabled = false;
      renderSubjectChats();
      updateChatHeader();
      updateLessonUI();
      focusInputWithoutScroll();
    }
  }

  function bindCopyButtons() {
    document.querySelectorAll(".copy-message").forEach(button => {
      button.addEventListener("click", async () => {
        const bubble = button
          .closest(".message-body")
          ?.querySelector(".message-bubble");

        if (!bubble) return;

        try {
          await navigator.clipboard.writeText(bubble.innerText);
          button.textContent = "✓ Đã sao chép";
          setTimeout(() => {
            button.textContent = "📋 Sao chép";
          }, 1200);
        } catch (error) {
          console.error("Không thể sao chép:", error);
        }
      });
    });
  }

  input?.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  });

  input?.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });

  sendBtn?.addEventListener("click", sendMessage);

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text ?? "";
    return div.innerHTML;
  }

  (async function initChat() {
    try {
      await loadChats();
      await initLessonMode();
    } catch (error) {
      console.error("Không tải được Chat theo môn:", error);

      if (historyList) {
        historyList.innerHTML =
          '<p class="muted">Không tải được danh sách môn học.</p>';
      }

      currentMessages = [];
      currentChatId = null;
      updateChatHeader();
      renderCurrentChat();
    }
  })();
});
