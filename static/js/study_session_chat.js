/* Phase 6.3.2: in-room Chat AI. Uses the existing /api/chat service and
   its per-subject conversation; backend authenticates task, syllabus, materials,
   and source version for EVERY question. Never fall back to unscoped AI. */
document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("studyRoomChat");
  if (!root || root.dataset.chatEnabled !== "1") return;
  const taskId = Number(root.dataset.taskId);
  const subjectId = Number(root.dataset.subjectId);
  const chapterNumber = Number(root.dataset.chapterNumber);
  const messages = document.getElementById("studyRoomChatMessages");
  const form = document.getElementById("studyRoomChatForm");
  const field = document.getElementById("studyRoomChatQuestion");
  const sendButton = document.getElementById("studyRoomChatSend");
  const status = document.getElementById("studyRoomChatStatus");
  let conversationId = null;
  let busy = false;

  function setStatus(message) {
    if (status) status.textContent = message;
  }
  function addMessage(role, value) {
    if (!messages) return;
    messages.querySelector(".study-room-chat-empty")?.remove();
    const bubble = document.createElement("div");
    bubble.className = "study-room-chat-bubble " + role;
    const heading = document.createElement("strong");
    heading.textContent = role === "user" ? "Bạn" : role === "error" ? "Thông báo" : "AI Study Agent";
    const body = document.createElement("div");
    // All text from the model/user stays text, not HTML.
    body.textContent = String(value || "");
    bubble.append(heading, body);
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
  }
  async function api(url, options) {
    const response = await fetch(url, {
      credentials: "same-origin", ...options
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || "Không thể kết nối với Chat AI.");
    return body;
  }

  async function loadHistory() {
    if (!Number.isSafeInteger(taskId) || taskId <= 0) return;
    try {
      const data = await api("/api/study-plan/tasks/" + taskId + "/chat-history");
      if (data.session_task_id !== taskId || data.subject_id !== subjectId ||
          data.chapter_number !== chapterNumber) {
        throw new Error("Ngữ cảnh Chat AI không khớp buổi học.");
      }
      conversationId = data.conversation_id;
      messages.replaceChildren();
      if (data.messages.length) {
        data.messages.forEach(item => addMessage(item.role === "user" ? "user" : "assistant", item.content));
      } else {
        const empty = document.createElement("p");
        empty.className = "study-room-chat-empty";
        empty.textContent = "Bạn có thể hỏi AI về các tiểu mục và hoạt động trong buổi này. Chỉ nguồn học liệu đã duyệt được trích dẫn.";
        messages.appendChild(empty);
      }
      field.disabled = false;
      sendButton.disabled = false;
      setStatus("Đã xác thực · Có dẫn nguồn");
    } catch (error) {
      setStatus("Chưa thể sử dụng");
      messages.replaceChildren();
      addMessage("error", error.message + " Hãy tải lại trang hoặc rà soát học liệu chương.");
      field.disabled = true;
      sendButton.disabled = true;
    }
  }

  form?.addEventListener("submit", async event => {
    event.preventDefault();
    const question = field.value.trim();
    if (busy || !conversationId || !question) return;
    if (question.length > 500) {
      setStatus("Câu hỏi vượt quá 500 ký tự");
      return;
    }
    busy = true;
    field.disabled = true;
    sendButton.disabled = true;
    addMessage("user", question);
    field.value = "";
    setStatus("AI đang đọc học liệu đã duyệt...");
    try {
      const result = await api("/api/chat", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          conversation_id: conversationId,
          question,
          lesson: {chapter_number: chapterNumber, task_id: taskId}
        })
      });
      if (result.source_mode !== "chapter" ||
          result.lesson?.session_task_id !== taskId) {
        throw new Error("Phản hồi không được xác thực theo buổi học.");
      }
      addMessage("assistant", result.answer || "Chưa có câu trả lời.");
      setStatus("Đã xác thực · Có dẫn nguồn");
    } catch (error) {
      // Errors are not treated as answers and do not save fake progress.
      addMessage("error", error.message);
      setStatus("Không gửi được câu hỏi");
    } finally {
      busy = false;
      field.disabled = false;
      sendButton.disabled = false;
      field.focus({preventScroll: true});
    }
  });
  loadHistory();
});
