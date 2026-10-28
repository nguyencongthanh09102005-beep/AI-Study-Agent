/* Node regression: compact weekly timetable, explicit period boundaries. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {
  PERIODS, parseStudyTime, periodForHour, formatStudyTimeRange
} = require("../static/js/study_timetable_periods.js");

const names = ["Khuya", "Sáng", "Trưa", "Chiều", "Tối"];
assert.deepEqual(PERIODS.map(p => p.title), names);
for (const [hour, expected] of [[0,"Khuya"],[4,"Khuya"],[5,"Sáng"],[10,"Sáng"],
  [11,"Trưa"],[13,"Trưa"],[14,"Chiều"],[17,"Chiều"],[18,"Tối"],[23,"Tối"]]) {
  assert.equal(periodForHour(hour)?.title, expected);
}
assert.equal(parseStudyTime("2026-11-02T19:30").timeOfDay, 19*60+30);
assert.equal(parseStudyTime("2026-11-02T24:00"), null);
assert.equal(parseStudyTime("2026-02-30T19:00"), null);
assert.equal(parseStudyTime("bad"), null);
assert.equal(formatStudyTimeRange("2026-11-02T19:00",45), "19:00–19:45");
assert.equal(formatStudyTimeRange("2026-11-02T19:30",90), "19:30–21:00");
assert.equal(formatStudyTimeRange("2026-11-02T23:45",45), "23:45–00:30 (+1 ngày)");
assert.equal(formatStudyTimeRange("bad",45), "");

const js=fs.readFileSync(path.join(__dirname,"../static/js/study_plan.js"),"utf8");
assert.match(js, /function renderTimetable\(\)/);
assert.match(js, /StudyTimetablePeriods/);
assert.match(js, /periodForHour/);
assert.match(js, /formatStudyTimeRange/);
assert.match(js, /dayIndex \+ ":" \+ period.id/);
assert.match(js, /events\.get\(dayIndex \+ ":" \+ period\.id\)/);
assert.match(js, /dataset\.taskConflict === "1"/);
assert.match(js, /currentView = "week"/);
assert.doesNotMatch(js, /for \(let hour = firstHour/);
console.log("Compact timetable by Sáng/Trưa/Chiều/Tối tests passed");
