/* Regression for simplified navigation: one Week timetable with day details. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const code = fs.readFileSync(path.join(root, "static/js/study_plan.js"), "utf8");
const html = fs.readFileSync(path.join(root, "templates/study_plan.html"), "utf8");
const base = fs.readFileSync(path.join(root, "templates/base.html"), "utf8");

assert.match(html, /data-view="week" role="tab" aria-selected="true">Tuần/);
assert.doesNotMatch(html, /data-view="timetable"/);
assert.match(html, /id="weekDays" aria-live="polite" hidden/);
assert.match(html, /id="plannerTimetable" aria-label="Thời khóa biểu tuần/);
assert.match(html, /id="backToWeek" hidden/);
assert.match(html, /id="openQuickTask"/);
assert.match(code, /let currentView = "week"/);
assert.match(code, /const showTimetable = currentView === "week"/);
assert.match(code, /currentView = "day"/);
assert.match(code, /backToWeek\?\.addEventListener/);
assert.match(code, /quickTask\?\.addEventListener/);
assert.match(code, /if \(currentView === "month"\) \{\s*renderMonth\(\)/);
assert.match(code, /currentView === "list"/);
assert.doesNotMatch(code, /currentView === "timetable"/);
assert.doesNotMatch(code, /function renderWeek/);
assert.doesNotMatch(base, /id="globalSearch"/);
assert.doesNotMatch(base, /Tìm kiếm môn học, tài liệu, câu hỏi/);
assert.match(base, /topbar-mobile-account/);
console.log("Simplified weekly timetable navigation and search cleanup OK");
