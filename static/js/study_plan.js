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

  // Đưa modal ra trực tiếp dưới <body> như một "portal".
  // Nhờ vậy position: fixed luôn tính theo viewport thật của trình duyệt,
  // không bị lệch khi zoom 80% / 100% / 125% hoặc khi ancestor có transform.
  [aiPlannerModal, taskModal, reminderModal].forEach((modal) => {
    if (modal && modal.parentElement !== body) {
      body.appendChild(modal);
    }
  });

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
    toggleEditPlan.textContent = editing ? "✓ Xong chỉnh sửa" : "✎ Chỉnh sửa";
    toggleEditPlan.setAttribute("aria-pressed", editing ? "true" : "false");
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

    // Khi đang xem một ngày khác trên lịch, tạo task mặc định đúng ngày đó.
    // plannerDatePicker luôn được calendar đồng bộ với ngày đang chọn.
    const selectedDateValue =
      document.getElementById("plannerDatePicker")?.value || "";
    const selectedParts = selectedDateValue.split("-").map(Number);
    if (
      selectedParts.length === 3 &&
      selectedParts.every(Number.isFinite)
    ) {
      date.setFullYear(
        selectedParts[0],
        selectedParts[1] - 1,
        selectedParts[2]
      );
    }

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


/* =====================================================
   INTERACTIVE CALENDAR V2
   - Tuần / Tháng / Danh sách
   - Chọn trực tiếp ngày-tháng-năm
   - Chuyển lịch nhiệm vụ
===================================================== */
document.addEventListener("DOMContentLoaded", () => {
  const weekDays = document.getElementById("weekDays");
  const rangeLabel = document.getElementById("weekRangeLabel");
  const datePicker = document.getElementById("plannerDatePicker");
  const dateJumpButton = document.getElementById("dateJumpButton");
  const todayButton = document.getElementById("goToday");
  const prevButton = document.getElementById("prevPeriod");
  const nextButton = document.getElementById("nextPeriod");
  const viewTabs = document.getElementById("plannerViewTabs");
  const scheduleTitle = document.getElementById("scheduleTitle");
  const scheduleViewLabel = document.getElementById("scheduleViewLabel");
  const emptyState = document.getElementById("scheduleFilterEmpty");
  const scheduleItems = [...document.querySelectorAll(".schedule-item-new[data-task-date]")];
  const timetable = document.getElementById("plannerTimetable");
  const timetableGrid = document.getElementById("plannerTimetableGrid");
  const timetableEmpty = document.getElementById("plannerTimetableEmpty");
  const agendaCard = document.querySelector(".day-schedule-card");

  if (!weekDays || !datePicker) return;

  const pad = (n) => String(n).padStart(2, "0");
  const toIso = (date) =>
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

  const fromIso = (value) => {
    const parts = String(value || "").split("-").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return new Date();
    return new Date(parts[0], parts[1] - 1, parts[2]);
  };

  const cloneDate = (date) =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate());

  const startOfWeek = (date) => {
    const d = cloneDate(date);
    const weekday = d.getDay();
    const offset = weekday === 0 ? -6 : 1 - weekday;
    d.setDate(d.getDate() + offset);
    return d;
  };

  const addDays = (date, amount) => {
    const d = cloneDate(date);
    d.setDate(d.getDate() + amount);
    return d;
  };

  const formatShort = (date) =>
    `${pad(date.getDate())}/${pad(date.getMonth() + 1)}`;

  const formatFull = (date) =>
    `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;

  const weekdayName = (date) =>
    ["Chủ nhật", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7"][date.getDay()];

  const monthName = (date) =>
    `Tháng ${date.getMonth() + 1}, ${date.getFullYear()}`;

  const countsByDate = scheduleItems.reduce((acc, item) => {
    const key = item.dataset.taskDate;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});

  let selectedDate = fromIso(datePicker.value);
  let currentView = "week";

  // Phase 6.2.1: read-only weekly hour timetable from the existing study_tasks DOM.
  // No database writes and no second copy of the learning sessions.
  function renderTimetable() {
    if (!timetableGrid) return;
    const start = startOfWeek(selectedDate);
    const days = Array.from({ length: 7 }, (_, i) => addDays(start, i));
    const keys = days.map(toIso);
    const events = new Map();
    let firstHour = 7;
    let lastHour = 22;
    let total = 0;

    scheduleItems.forEach((item) => {
      const dayIndex = keys.indexOf(item.dataset.taskDate);
      if (dayIndex === -1) return;
      const match = /T(\\d{2}):(\\d{2})/.exec(item.dataset.taskDatetime || "");
      if (!match) return;
      const hour = Number(match[1]);
      const minute = Number(match[2]);
      if (hour > 23 || minute > 59) return;
      firstHour = Math.min(firstHour, hour);
      lastHour = Math.max(lastHour, hour);
      const key = dayIndex + ":" + hour;
      if (!events.has(key)) events.set(key, []);
      events.get(key).push({ item, hour, minute });
      total += 1;
    });
    events.forEach((entries) => entries.sort((a, b) => a.minute - b.minute));
    timetableGrid.replaceChildren();

    const makeDiv = (cls, value) => {
      const el = document.createElement("div");
      el.className = cls;
      if (value !== undefined) el.textContent = value;
      return el;
    };
    timetableGrid.appendChild(makeDiv("study-hour-corner", "Giờ"));
    days.forEach((day) => {
      const header = makeDiv("study-hour-day");
      header.appendChild(makeDiv("study-hour-dayname", ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][day.getDay()]));
      header.appendChild(makeDiv("study-hour-daydate", formatShort(day)));
      if (toIso(day) === toIso(new Date())) header.classList.add("today");
      timetableGrid.appendChild(header);
    });

    for (let hour = firstHour; hour <= lastHour; hour += 1) {
      timetableGrid.appendChild(makeDiv("study-hour-label", pad(hour) + ":00"));
      for (let dayIndex = 0; dayIndex < 7; dayIndex += 1) {
        const cell = makeDiv("study-hour-cell");
        const inCell = events.get(dayIndex + ":" + hour) || [];
        inCell.forEach(({ item, minute }) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "study-hour-event";
          if (item.dataset.taskDone === "1") button.classList.add("done");
          button.dataset.date = item.dataset.taskDate;
          const timeText = pad(hour) + ":" + pad(minute);
          const subject = item.dataset.subjectName || "Học tập";
          const title = item.dataset.taskTitle || "Buổi học";
          const duration = item.dataset.taskDuration || "45";
          button.appendChild(makeDiv("study-hour-event-time", timeText + " · " + duration + " phút"));
          button.appendChild(makeDiv("study-hour-event-subject", subject));
          button.appendChild(makeDiv("study-hour-event-title", title));
          if (item.dataset.taskSource === "roadmap") button.appendChild(makeDiv("study-hour-event-tag", "Từ lộ trình"));
          if (item.dataset.taskDone === "1") button.appendChild(makeDiv("study-hour-event-tag", "Đã hoàn thành"));
          button.setAttribute("aria-label", timeText + ", " + subject + ", " + title + ". Mở lịch ngày.");
          cell.appendChild(button);
        });
        timetableGrid.appendChild(cell);
      }
    }
    if (timetableEmpty) timetableEmpty.hidden = total !== 0;
  }


  function animateSurface() {
    const surfaces = [
      weekDays,
      document.querySelector(".day-schedule-card")
    ].filter(Boolean);

    surfaces.forEach((surface) => {
      if (typeof surface.animate !== "function") return;
      surface.animate(
        [
          { opacity: 0.45, transform: "translateY(5px)" },
          { opacity: 1, transform: "translateY(0)" }
        ],
        { duration: 220, easing: "cubic-bezier(.2,.8,.2,1)" }
      );
    });
  }

  function updateHeader() {
    const selectedKey = toIso(selectedDate);
    if (currentView === "list") {
      rangeLabel.textContent = "Tất cả nhiệm vụ";
      if (scheduleTitle) scheduleTitle.innerHTML = "◷ &nbsp; Danh sách nhiệm vụ";
      if (scheduleViewLabel) {
        scheduleViewLabel.textContent = `${scheduleItems.length} nhiệm vụ trong kế hoạch`;
      }
      return;
    }

    if (currentView === "month") {
      rangeLabel.textContent = monthName(selectedDate);
    } else {
      const start = startOfWeek(selectedDate);
      const end = addDays(start, 6);
      rangeLabel.textContent =
        `${formatShort(start)} – ${formatShort(end)} · ${end.getFullYear()}`;
    }

    if (scheduleTitle) {
      scheduleTitle.innerHTML =
        `◷ &nbsp; Lịch học ngày ${formatFull(selectedDate)}`;
    }
    if (scheduleViewLabel) {
      const count = countsByDate[toIso(selectedDate)] || 0;
      scheduleViewLabel.textContent =
        `${weekdayName(selectedDate)} · ${count} nhiệm vụ`;
    }
  }

  function filterTasks() {
    let visibleCount = 0;
    const selectedKey = toIso(selectedDate);

    scheduleItems.forEach((item) => {
      const visible =
        currentView === "list" || item.dataset.taskDate === selectedKey;
      item.hidden = !visible;
      if (visible) visibleCount += 1;
    });

    if (emptyState) {
      emptyState.hidden = visibleCount !== 0;
      emptyState.textContent = currentView === "list"
        ? "Chưa có nhiệm vụ trong kế hoạch. Hãy chọn Tạo kế hoạch mới để bắt đầu."
        : `Ngày ${formatShort(selectedDate)} chưa có buổi học. Bạn có thể chọn ngày khác hoặc tạo kế hoạch mới.`;
    }
  }

  function createDayButton(date, options = {}) {
    const key = toIso(date);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "week-day";
    button.dataset.date = key;

    if (options.monthCell) button.classList.add("month-day");
    if (key === toIso(selectedDate)) button.classList.add("active");
    if (key === toIso(new Date())) button.classList.add("today");

    const count = countsByDate[key] || 0;
    const dayLabel = options.monthCell
      ? String(date.getDate())
      : ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][date.getDay()];

    button.innerHTML = options.monthCell
      ? `<b>${dayLabel}</b><small>${count ? `${count} task` : "Trống"}</small>`
      : `<b>${dayLabel}</b><span class="week-date">${formatShort(date)}</span><small>${count} task</small>`;

    return button;
  }

  function renderWeek() {
    weekDays.hidden = false;
    weekDays.classList.remove("month-grid");
    weekDays.innerHTML = "";
    const start = startOfWeek(selectedDate);
    for (let i = 0; i < 7; i += 1) {
      weekDays.appendChild(createDayButton(addDays(start, i)));
    }
  }

  function renderMonth() {
    weekDays.hidden = false;
    weekDays.classList.add("month-grid");
    weekDays.innerHTML = "";

    ["T2", "T3", "T4", "T5", "T6", "T7", "CN"].forEach((label) => {
      const head = document.createElement("span");
      head.className = "month-weekday";
      head.textContent = label;
      weekDays.appendChild(head);
    });

    const first = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1);
    const last = new Date(selectedDate.getFullYear(), selectedDate.getMonth() + 1, 0);
    const leading = first.getDay() === 0 ? 6 : first.getDay() - 1;

    for (let i = 0; i < leading; i += 1) {
      const blank = document.createElement("span");
      blank.className = "month-blank";
      weekDays.appendChild(blank);
    }

    for (let day = 1; day <= last.getDate(); day += 1) {
      const date = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), day);
      weekDays.appendChild(createDayButton(date, { monthCell: true }));
    }
  }

  function renderView({ animate = true } = {}) {
    datePicker.value = toIso(selectedDate);

    if (currentView === "week") renderWeek();
    if (currentView === "month") renderMonth();
    if (currentView === "list" || currentView === "timetable") {
      weekDays.hidden = true;
      weekDays.classList.remove("month-grid");
    }
    const showTimetable = currentView === "timetable";
    if (timetable) timetable.hidden = !showTimetable;
    if (agendaCard) agendaCard.hidden = showTimetable;
    if (showTimetable) renderTimetable();

    updateHeader();
    filterTasks();

    [prevButton, nextButton].forEach((button) => {
      if (button) button.disabled = currentView === "list";
    });

    viewTabs?.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === currentView;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });

    if (animate) animateSurface();
  }

  weekDays.addEventListener("click", (event) => {
    const button = event.target.closest("[data-date]");
    if (!button) return;
    selectedDate = fromIso(button.dataset.date);
    renderView();
  });

  viewTabs?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-view]");
    if (!button) return;
    currentView = button.dataset.view;
    renderView();
  });

  timetable?.addEventListener("click", (event) => {
    const button = event.target.closest(".study-hour-event[data-date]");
    if (!button) return;
    selectedDate = fromIso(button.dataset.date);
    currentView = "week";
    renderView();
  });

  todayButton?.addEventListener("click", () => {
    selectedDate = cloneDate(new Date());
    renderView();
  });

  prevButton?.addEventListener("click", () => {
    if (currentView === "month") {
      selectedDate = new Date(
        selectedDate.getFullYear(),
        selectedDate.getMonth() - 1,
        Math.min(selectedDate.getDate(), 28)
      );
    } else if (currentView === "week" || currentView === "timetable") {
      selectedDate = addDays(selectedDate, -7);
    }
    renderView();
  });

  nextButton?.addEventListener("click", () => {
    if (currentView === "month") {
      selectedDate = new Date(
        selectedDate.getFullYear(),
        selectedDate.getMonth() + 1,
        Math.min(selectedDate.getDate(), 28)
      );
    } else if (currentView === "week" || currentView === "timetable") {
      selectedDate = addDays(selectedDate, 7);
    }
    renderView();
  });

  datePicker.addEventListener("change", () => {
    selectedDate = fromIso(datePicker.value);
    if (currentView === "list") currentView = "week";
    renderView();
  });

  dateJumpButton?.addEventListener("click", () => {
    if (typeof datePicker.showPicker === "function") {
      datePicker.showPicker();
    } else {
      datePicker.focus();
      datePicker.click();
    }
  });

  // Chuyển lịch nhanh: dùng lại modal chỉnh task nhưng đưa người dùng
  // thẳng tới trường ngày/giờ để đổi lịch, không cần sửa nội dung nhiệm vụ.
  document.querySelectorAll(".move-task-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const modal = document.getElementById("taskModal");
      const form = document.getElementById("taskForm");
      const modalTitle = document.getElementById("taskModalTitle");
      const title = document.getElementById("taskTitle");
      const subject = document.getElementById("taskSubject");
      const studyAt = document.getElementById("taskStudyAt");
      const duration = document.getElementById("taskDuration");
      const note = document.getElementById("taskNote");

      if (!modal || !form || !studyAt) return;

      modalTitle.textContent = "Chuyển lịch nhiệm vụ";
      form.action = `/study-plan/tasks/${button.dataset.id}/update`;
      title.value = button.dataset.title || "";
      subject.value = button.dataset.subjectId || "";
      studyAt.value = button.dataset.studyAt || "";
      duration.value = button.dataset.duration || "45";
      note.value = button.dataset.note || "";

      modal.classList.add("show");
      modal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";

      setTimeout(() => {
        studyAt.focus();
        if (typeof studyAt.showPicker === "function") {
          try { studyAt.showPicker(); } catch (error) {}
        }
      }, 100);
    });
  });

  renderView({ animate: false });
});
