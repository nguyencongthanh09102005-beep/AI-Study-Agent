"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const chart = fs.readFileSync("static/js/weekly-progress.js", "utf8");
const dashboard = fs.readFileSync("templates/dashboard.html", "utf8");
const roadmap = fs.readFileSync("templates/course_learning_path.html", "utf8");
const documents = fs.readFileSync("templates/documents.html", "utf8");

assert(dashboard.includes('id="weeklyChartFallback"'));
assert(dashboard.includes("thời gian timer ghi nhận"));
for (const title of ["Chưa xếp lịch", "Đã hoàn thành buổi học",
                     "Đã lên lịch · Chưa hoàn thành",
                     "Lộ trình mới khác lịch đã lưu"]) {
  assert(roadmap.includes(title), "Missing roadmap state: " + title);
}
assert(roadmap.includes("{% if schedule_status.get(lesson.session_id) == 'changed' %}"),
  "Stale source must take priority over a done flag");

const personal = documents.slice(documents.indexOf('id="personalLibraryPanel"'),
  documents.indexOf('id="sharedLibraryPanel"'));
const shared = documents.slice(documents.indexOf('id="sharedLibraryPanel"'));
assert.equal((personal.match(/\?download=1/g) || []).length, 1,
  "Private file direct download must appear exactly once");
assert(shared.includes('shared_document_file'));
assert(shared.includes('?download=1'));
assert(personal.indexOf('↓ Tải file') < personal.indexOf('<details class="library-file-more">'),
  "Private file download must be outside advanced-options menu");
assert(personal.includes('personal_document_file'));

let handlers = {};
const canvas = {hidden:false};
const fallback = {hidden:true};
const dom = {
  addEventListener(name, callback) { handlers[name] = callback; },
  getElementById(id) {
    return id === "weeklyStudyChart" ? canvas :
      id === "weeklyChartFallback" ? fallback : null;
  },
};
vm.runInNewContext(chart, { document:dom, window:{ weeklyStudyData:[0,1,0,0,0,0,0] } });
handlers.DOMContentLoaded();
assert(canvas.hidden && !fallback.hidden,
  "Without Chart.js the dashboard must render weekly totals instead of blank canvas");
console.log("Web final UI PASS: offline chart, roadmap statuses, direct document download");
