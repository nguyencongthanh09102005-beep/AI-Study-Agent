document.addEventListener("DOMContentLoaded", () => {
  const body = document.body;
  const openAiPlanner = document.getElementById("openAiPlanner");
  const aiPlannerModal = document.getElementById("aiPlannerModal");
  const aiPlannerForm = document.getElementById("aiPlannerForm");
  const generatePlanButton = document.getElementById("generatePlanButton");

  const toggleEditPlan = document.getElementById("toggleEditPlan");
  const addTaskButton = document.getElementById("addTaskButton");
  const taskModal = document.getElementById("taskModal");
  const taskForm = document.getElementById("taskForm");
  const taskModalTitle = document.getElementById("taskModalTitle");
  const taskTitle = document.getElementById("taskTitle");
  const taskSubject = document.getElementById("taskSubject");
  const taskStudyAt = document.getElementById("taskStudyAt");
  const taskDuration = document.getElementById("taskDuration");
  const taskNote = document.getElementById("taskNote");

  const reminderModal = document.getElementById("reminderModal");
  const reminderForm = document.getElementById("reminderForm");
  const reminderTitle = document.getElementById("reminderTitle");
  const reminderDueAt = document.getElementById("reminderDueAt");
  const deleteReminderForm = document.getElementById("deleteReminderForm");

  function openModal(modal) {
    if (!modal) return;
    modal.classList.add("show");
    modal.setAttribute("aria-hidden", "false");
    body.style.overflow = "hidden";
  }

  function closeModal(modal) {
    if (!modal) return;
    modal.classList.remove("show");
    modal.setAttribute("aria-hidden", "true");
    if (!document.querySelector(".planner-modal.show")) {
      body.style.overflow = "";
    }
  }

  openAiPlanner?.addEventListener("click", () => openModal(aiPlannerModal));
  document.querySelectorAll("[data-close-modal]").forEach((el) => el.addEventListener("click", () => closeModal(aiPlannerModal)));
  document.querySelectorAll("[data-close-task-modal]").forEach((el) => el.addEventListener("click", () => closeModal(taskModal)));
  document.querySelectorAll("[data-close-reminder-modal]").forEach((el) => el.addEventListener("click", () => closeModal(reminderModal)));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeModal(aiPlannerModal);
    closeModal(taskModal);
    closeModal(reminderModal);
  });

  aiPlannerForm?.addEventListener("submit", () => {
    if (!generatePlanButton) return;
    generatePlanButton.disabled = true;
    generatePlanButton.textContent = "⏳ AI đang tạo kế hoạch...";
  });

  toggleEditPlan?.addEventListener("click", () => {
    body.classList.toggle("planner-edit-mode");
    const editing = body.classList.contains("planner-edit-mode");
    toggleEditPlan.textContent = editing ? "✓ Xong chỉnh sửa" : "✎ Chỉnh sửa kế hoạch";
  });

  function localDateTimeValue(date = new Date()) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }

  addTaskButton?.addEventListener("click", () => {
    if (!taskForm) return;
    taskModalTitle.textContent = "Thêm buổi học";
    taskForm.action = "/study-plan/tasks/create";
    taskForm.reset();
    taskDuration.value = "45";
    const date = new Date();
    date.setMinutes(0, 0, 0);
    date.setHours(date.getHours() + 1);
    taskStudyAt.value = localDateTimeValue(date);
    openModal(taskModal);
  });

  document.querySelectorAll(".edit-task-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.id;
      taskModalTitle.textContent = "Sửa buổi học";
      taskForm.action = `/study-plan/tasks/${id}/update`;
      taskTitle.value = button.dataset.title || "";
      taskSubject.value = button.dataset.subjectId || "";
      taskStudyAt.value = button.dataset.studyAt || "";
      taskDuration.value = button.dataset.duration || "45";
      taskNote.value = button.dataset.note || "";
      openModal(taskModal);
    });
  });

  document.querySelectorAll(".edit-reminder-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.id;
      reminderForm.action = `/study-plan/reminders/${id}/update`;
      deleteReminderForm.action = `/study-plan/reminders/${id}/delete`;
      reminderTitle.value = button.dataset.title || "";
      reminderDueAt.value = button.dataset.dueAt || "";
      openModal(reminderModal);
    });
  });

  // =====================================================
  // THÔNG BÁO DEADLINE CÒN <= 2 NGÀY
  // Chỉ hiển thị khi người dùng mở website.
  // Mỗi deadline chỉ hiện 1 lần/ngày trên trình duyệt này.
  // =====================================================
  const urgentItems = [...document.querySelectorAll('.deadline-item[data-urgent="true"]')];
  const toast = document.getElementById("deadlineToast");
  const toastText = document.getElementById("deadlineToastText");
  const closeToast = document.getElementById("closeDeadlineToast");

  if (urgentItems.length && toast && toastText) {
    const todayKey = new Date().toISOString().slice(0, 10);
    const firstUnseen = urgentItems.find((item) => {
      const key = `studyDeadlineNotice:${item.dataset.reminderId}:${todayKey}`;
      return !localStorage.getItem(key);
    });

    if (firstUnseen) {
      const title = firstUnseen.dataset.reminderTitle || "Một deadline";
      const badge = firstUnseen.querySelector(".deadline-badge")?.textContent?.trim() || "sắp đến hạn";
      toastText.textContent = `${title} — ${badge}.`;
      toast.hidden = false;
      localStorage.setItem(`studyDeadlineNotice:${firstUnseen.dataset.reminderId}:${todayKey}`, "1");
    }
  }

  closeToast?.addEventListener("click", () => {
    if (toast) toast.hidden = true;
  });
});
