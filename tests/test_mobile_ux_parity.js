"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const {parseLocalDateTime,dateTimeString,localDateTimeLabel,monthCells}=
  require("../mobile/src/date-time-utils");
const app=fs.readFileSync("mobile/App.js","utf8");
const server=fs.readFileSync("mobile_learning_routes.py","utf8");
const api=fs.readFileSync("mobile/src/api.js","utf8");
const picker=fs.readFileSync("mobile/src/StudyDateTimePicker.js","utf8");
const backend=fs.readFileSync("app.py","utf8");

assert.deepEqual(parseLocalDateTime("2026-11-07T19:45"),
  {year:2026,month:11,day:7,hour:19,minute:45});
assert.equal(parseLocalDateTime("2026-02-30T19:00"),null);
assert.equal(parseLocalDateTime("2026-13-07T20:00"),null);
assert.equal(parseLocalDateTime("2026-11-07T24:00"),null);
assert.equal(dateTimeString({year:2026,month:11,day:7,hour:7,minute:5}),"2026-11-07T07:05");
assert.equal(localDateTimeLabel("2026-11-07T07:05"),"07/11/2026 · 07:05");
assert.equal(monthCells(2026,11).filter(Boolean).length,30);
assert.equal(monthCells(2026,2).filter(Boolean).length,28);
assert.equal(monthCells(2028,2).filter(Boolean).length,29);
assert(picker.includes("<Modal")&&picker.includes("onChange(dateTimeString(draft))"),
  "Date-time picker must only commit a chosen local datetime");
assert(picker.includes("accessibilityLabel") && picker.includes("animationType"),
  "Picker must remain usable with screen readers");

assert(app.includes('StudyDateTimePicker label="Ngày và giờ học"') &&
       app.includes('StudyDateTimePicker label="Hạn cần hoàn thành"'));
assert(app.includes('const completedToday = todayTasks.filter'));
const list=app.slice(app.indexOf("  const tasks = local?.tasks || [];"),
                     app.indexOf("function ProfileScreen("));
assert(!list.includes("planProgressCard")&&!list.includes("Tiến độ tuần đang chọn"),
  "Only one compact today completion summary remains");
assert(list.includes("Deadline & cảnh báo")&&list.includes("conflictingTasks"));
assert(list.includes("task.roadmap_label || task.title"),
  "Calendar labels must be verified or fall back to original task title");
assert(list.includes("task.source === 'roadmap'") && list.includes("onOpenStudy(task.id)"),
  "Roadmap completion must open verified study room, never bypass timer");
assert(!list.includes("setMode('generate')"),"Do not show parallel AI plan action");
assert(list.includes("personal_document_name"),
  "Show linked personal document in task list");
assert(app.includes("api.scheduleRoadmap(selectedId)") &&
       app.includes("Xác nhận xếp lịch"),"Roadmap importer needs explicit confirmation");
assert(api.includes("scheduleRoadmap: subjectId"));
assert(server.includes("import_roadmap_lessons") &&
       server.includes("reschedule_existing=False"),"Mobile must use safe Web scheduler");
assert(api.includes("document_id")===false ||
       app.includes("document_id:taskDocumentId"),
  "Manual study form must use server-owned doc binding");
assert(backend.includes("from manual_lesson_routes import (") &&
       backend.includes("attach_document(conn, uid, task_id"),
  "Mobile must validate and attach owned documents");
const p=app.slice(app.indexOf("function ProfileScreen("),app.indexOf("function LoginScreen("));
const expand=p.indexOf("      {showLearningSettings && <View style={styles.card}>");
const appSection=p.indexOf("      <Text style={styles.sectionTitle}>Ứng dụng</Text>");
assert(expand>=0&&expand<appSection,"Settings must expand immediately below learning group");
assert(app.includes("width: 44, height: 44") &&
       app.includes("navLabel: { fontSize: 11"),
       "Increase tap targets and navigation legibility");
console.log("Mobile UX parity static/date-time checks PASS");
