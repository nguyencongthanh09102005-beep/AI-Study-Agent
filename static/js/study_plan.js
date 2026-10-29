document.addEventListener("DOMContentLoaded", () => {
  const body = document.body;
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

  // Conflict preview for create/edit/move; data is read from the current page.
  // Never modifies tasks unless the student chooses to save the form.
  const conflictNotice = document.getElementById("taskScheduleWarning");
  const conflictText = document.getElementById("taskScheduleWarningText");
  const suggestButton = document.getElementById("suggestTimeButton");
  function inspectTime() {
    const at = new Date(taskStudyAt?.value || "");
    const dur = Number(taskDuration?.value);
    if (!Number.isFinite(at.getTime()) || !Number.isFinite(dur) || dur < 1)
      return { conflicts: [], suggestion: "" };
    const currentId = /\/tasks\/(\d+)\/update$/.exec(taskForm?.action || "")?.[1] || "";
    const all = [...document.querySelectorAll(".schedule-item-new[data-task-datetime]")]
      .map((el) => ({
        id: el.dataset.taskId,
        title: el.dataset.taskTitle || "Buổi học",
        start: new Date(el.dataset.taskDatetime).getTime(),
        duration: Number(el.dataset.taskDuration || 45)
      }))
      .filter((x) => x.id !== currentId && Number.isFinite(x.start) && x.duration > 0)
      .map((x) => ({...x, end: x.start + x.duration * 60000}));
    const begin = at.getTime(), end = begin + dur * 60000;
    const conflicts = all.filter((x) => begin < x.end && x.start < end);
    if (!conflicts.length) return {conflicts, suggestion: ""};
    let candidate = begin, suggestion = "";
    const tomorrow = new Date(at.getFullYear(), at.getMonth(), at.getDate() + 1).getTime();
    for (let n = 0; n < 200 && candidate + dur * 60000 <= tomorrow; n++) {
      const colliding = all.filter((x) => candidate < x.end && x.start < candidate + dur * 60000);
      if (!colliding.length) {
        const d = new Date(candidate), pad = x => String(x).padStart(2, "0");
        suggestion = d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" +
          pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
        break;
      }
      candidate = Math.ceil((Math.max(...colliding.map(x => x.end)) + 900000) / 900000) * 900000;
    }
    return {conflicts, suggestion};
  }
  function showConflictNotice() {
    if (!conflictNotice || !conflictText || !suggestButton) return;
    const {conflicts, suggestion} = inspectTime();
    conflictNotice.hidden = conflicts.length === 0;
    suggestButton.hidden = !suggestion;
    suggestButton.dataset.value = suggestion;
    if (conflicts.length) {
      conflictText.textContent = "⚠ Giờ này trùng với " + conflicts.length +
        " buổi: " + conflicts.slice(0,3).map(x => x.title).join(", ") +
        ". Bạn có thể đổi giờ hoặc giữ giờ hiện tại nếu cố ý.";
      if (suggestion) suggestButton.textContent = "Chọn giờ trống gợi ý: " + suggestion.slice(11);
    }
  }
  taskStudyAt?.addEventListener("input", showConflictNotice);
  taskDuration?.addEventListener("input", showConflictNotice);
  suggestButton?.addEventListener("click", () => {
    if (!suggestButton.dataset.value) return;
    taskStudyAt.value = suggestButton.dataset.value;
    showConflictNotice();
    taskStudyAt.focus();
  });
  taskForm?.addEventListener("submit", (event) => {
    const {conflicts} = inspectTime();
    if (conflicts.length && !window.confirm("Có " + conflicts.length +
      " buổi bị trùng giờ. Bạn có chắc muốn giữ khung giờ này?")) event.preventDefault();
  });


  const reminderModal = document.getElementById("reminderModal");
  const reminderForm = document.getElementById("reminderForm");
  const reminderTitle = document.getElementById("reminderTitle");
  const reminderDueAt = document.getElementById("reminderDueAt");
  const deleteReminderForm = document.getElementById("deleteReminderForm");

  // Đưa modal ra trực tiếp dưới <body> như một "portal".
  // Nhờ vậy position: fixed luôn tính theo viewport thật của trình duyệt,
  // không bị lệch khi zoom 80% / 100% / 125% hoặc khi ancestor có transform.
  [taskModal, reminderModal].forEach((modal) => {
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

  document.querySelectorAll("[data-close-task-modal]").forEach((el) => el.addEventListener("click", () => closeModal(taskModal)));
  document.querySelectorAll("[data-close-reminder-modal]").forEach((el) => el.addEventListener("click", () => closeModal(reminderModal)));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeModal(taskModal);
    closeModal(reminderModal);
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
    showConflictNotice();
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
      showConflictNotice();
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
  const backToWeek = document.getElementById("backToWeek");
  const scheduleTitle = document.getElementById("scheduleTitle");
  const scheduleViewLabel = document.getElementById("scheduleViewLabel");
  const emptyState = document.getElementById("scheduleFilterEmpty");
  const scheduleItems = [...document.querySelectorAll(".schedule-item-new[data-task-date]")];
  const timetable = document.getElementById("plannerTimetable");
  const timetableGrid = document.getElementById("plannerTimetableGrid");
  const timetableEmpty = document.getElementById("plannerTimetableEmpty");
  const agendaCard = document.querySelector(".day-schedule-card");
  const quickTask = document.getElementById("openQuickTask");
  quickTask?.addEventListener("click", () => document.getElementById("addTaskButton")?.click());

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

  // Compact timetable: 4 fixed day parts (plus Khuya only when scheduled).
  // Events still come from the existing study_tasks, with no duplicated records.
  function renderTimetable() {
    if (!timetableGrid) return;
    const calendar = window.StudyTimetablePeriods;
    if (!calendar) return;
    const start = startOfWeek(selectedDate);
    const days = Array.from({ length: 7 }, (_, i) => addDays(start, i));
    const keys = days.map(toIso);
    const events = new Map();
    let total = 0;

    scheduleItems.forEach((item) => {
      const dayIndex = keys.indexOf(item.dataset.taskDate);
      if (dayIndex === -1) return;
      const parsed = calendar.parseStudyTime(item.dataset.taskDatetime);
      if (!parsed) return;
      const period = calendar.periodForHour(parsed.hour);
      if (!period) return;
      const key = dayIndex + ":" + period.id;
      if (!events.has(key)) events.set(key, []);
      events.get(key).push({ item, timeOfDay: parsed.timeOfDay });
      total += 1;
    });
    events.forEach(list => list.sort((a, b) =>
      a.timeOfDay - b.timeOfDay ||
      Number(a.item.dataset.taskId) - Number(b.item.dataset.taskId)
    ));
    timetableGrid.replaceChildren();

    const makeDiv = (cls, value) => {
      const el = document.createElement("div");
      el.className = cls;
      if (value !== undefined) el.textContent = value;
      return el;
    };

    timetableGrid.appendChild(makeDiv("study-hour-corner", "Buổi"));
    days.forEach((day) => {
      const header = makeDiv("study-hour-day");
      header.appendChild(makeDiv("study-hour-dayname", ["CN", "T2", "T3", "T4", "T5", "T6", "T7"][day.getDay()]));
      header.appendChild(makeDiv("study-hour-daydate", formatShort(day)));
      if (toIso(day) === toIso(new Date())) header.classList.add("today");
      timetableGrid.appendChild(header);
    });

    const periods = calendar.PERIODS.filter(period =>
      !period.optional || days.some((_, dayIndex) => events.has(dayIndex + ":" + period.id))
    );
    periods.forEach((period) => {
      const label = makeDiv("study-hour-label");
      label.appendChild(makeDiv("study-hour-period-name", period.title));
      label.appendChild(makeDiv("study-hour-period-range", period.time));
      timetableGrid.appendChild(label);

      for (let dayIndex = 0; dayIndex < 7; dayIndex += 1) {
        const cell = makeDiv("study-hour-cell");
        const inCell = events.get(dayIndex + ":" + period.id) || [];
        if (!inCell.length) cell.classList.add("study-hour-cell-empty");
        inCell.forEach(({ item }) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "study-hour-event";
          button.dataset.date = item.dataset.taskDate;
          if (item.dataset.taskDone === "1") button.classList.add("done");

          const subject = item.dataset.subjectName || "Học tập";
          const title = item.dataset.taskTitle || "Buổi học";
          const timeText = calendar.formatStudyTimeRange(
            item.dataset.taskDatetime, item.dataset.taskDuration
          );
          button.appendChild(makeDiv("study-hour-event-time", timeText));
          button.appendChild(makeDiv("study-hour-event-subject", subject));
          const titleEl = makeDiv("study-hour-event-title", title);
          titleEl.title = title;
          button.appendChild(titleEl);
          if (item.dataset.taskSource === "roadmap") {
            button.appendChild(makeDiv("study-hour-event-tag", "Từ lộ trình"));
          }
          if (item.dataset.taskConflict === "1") {
            button.classList.add("conflict");
            button.appendChild(makeDiv("study-hour-event-conflict", "⚠ Trùng giờ"));
          }
          if (item.dataset.taskDone === "1") {
            button.appendChild(makeDiv("study-hour-event-tag", "Đã hoàn thành"));
          }
          button.setAttribute("aria-label",
            timeText + ", " + subject + ", " + title + ". Mở lịch ngày.");
          // Independent link: the lesson button still opens the selected day.
          // Only scheduled roadmap sessions have a Study Session (6.3.1).
          const card = makeDiv("study-hour-event-shell");
          card.appendChild(button);
          if (item.dataset.taskSource === "roadmap" &&
              /^\d+$/.test(item.dataset.taskId || "")) {
            const launch = document.createElement("a");
            launch.className = "study-hour-launch";
            launch.href = "/study-plan/tasks/" + item.dataset.taskId + "/learn";
            launch.textContent = item.dataset.taskDone === "1"
              ? "Xem lại buổi học →" : "▶ Bắt đầu học";
            card.appendChild(launch);
          }
          cell.appendChild(card);
        });
        timetableGrid.appendChild(cell);
      }
    });
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
        ? "Chưa có buổi học. Mở Môn học → Đề cương & lộ trình để xếp buổi học vào lịch, hoặc thêm buổi thủ công."
        : `Ngày ${formatShort(selectedDate)} chưa có buổi học. Bạn có thể chọn ngày khác hoặc thêm buổi thủ công.`;
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

    if (currentView === "month") {
      renderMonth();
    } else {
      weekDays.hidden = true;
      weekDays.classList.remove("month-grid");
    }
    // 'week' is now the compact weekly timetable; 'day' opens its task details.
    const showTimetable = currentView === "week";
    if (timetable) timetable.hidden = !showTimetable;
    if (agendaCard) agendaCard.hidden = showTimetable;
    if (backToWeek) backToWeek.hidden = currentView !== "day";
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
    currentView = "day";
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
    currentView = "day";
    renderView();
  });

  backToWeek?.addEventListener("click", () => {
    currentView = "week";
    renderView();
  });

  todayButton?.addEventListener("click", () => {
    selectedDate = cloneDate(new Date());
    currentView = "week";
    renderView();
  });

  prevButton?.addEventListener("click", () => {
    if (currentView === "month") {
      selectedDate = new Date(
        selectedDate.getFullYear(),
        selectedDate.getMonth() - 1,
        Math.min(selectedDate.getDate(), 28)
      );
    } else if (currentView === "week") {
      selectedDate = addDays(selectedDate, -7);
    } else if (currentView === "day") {
      selectedDate = addDays(selectedDate, -1);
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
    } else if (currentView === "week") {
      selectedDate = addDays(selectedDate, 7);
    } else if (currentView === "day") {
      selectedDate = addDays(selectedDate, 1);
    }
    renderView();
  });

  datePicker.addEventListener("change", () => {
    selectedDate = fromIso(datePicker.value);
    if (currentView === "list" || currentView === "day") currentView = "week";
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
      // Second DOMContentLoaded handler: notify the first handler via input event.
      studyAt.dispatchEvent(new Event("input", { bubbles: true }));

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
