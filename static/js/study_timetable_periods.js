/* Group timetable activities by parts of the day, independent of browser locale. */
(function (root) {
  "use strict";
  const PERIODS = Object.freeze([
    { id: "dawn", title: "Khuya", time: "00:00–04:59", start: 0, end: 4, optional: true },
    { id: "morning", title: "Sáng", time: "05:00–10:59", start: 5, end: 10 },
    { id: "noon", title: "Trưa", time: "11:00–13:59", start: 11, end: 13 },
    { id: "afternoon", title: "Chiều", time: "14:00–17:59", start: 14, end: 17 },
    { id: "evening", title: "Tối", time: "18:00–23:59", start: 18, end: 23 }
  ]);

  function parseStudyTime(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(String(value || ""));
    if (!match) return null;
    const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
    const hour = Number(match[4]), minute = Number(match[5]);
    const date = new Date(year, month - 1, day, hour, minute);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 ||
        date.getDate() !== day || date.getHours() !== hour || date.getMinutes() !== minute)
      return null;
    return { date, hour, minute, timeOfDay: hour * 60 + minute };
  }

  function periodForHour(hour) {
    return PERIODS.find(p => hour >= p.start && hour <= p.end) || null;
  }

  function formatStudyTimeRange(startValue, durationMinutes) {
    const parsed = parseStudyTime(startValue);
    const duration = Number(durationMinutes);
    if (!parsed || !Number.isFinite(duration) || duration <= 0) return "";
    const end = new Date(parsed.date.getTime() + duration * 60000);
    const pad = n => String(n).padStart(2, "0");
    const clock = d => pad(d.getHours()) + ":" + pad(d.getMinutes());
    const crossedDay = end.getFullYear() !== parsed.date.getFullYear() ||
      end.getMonth() !== parsed.date.getMonth() || end.getDate() !== parsed.date.getDate();
    return clock(parsed.date) + "–" + clock(end) + (crossedDay ? " (+1 ngày)" : "");
  }

  const api = { PERIODS, parseStudyTime, periodForHour, formatStudyTimeRange };
  root.StudyTimetablePeriods = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
