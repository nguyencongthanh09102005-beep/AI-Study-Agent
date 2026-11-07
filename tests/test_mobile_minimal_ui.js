/* Four-tab student Mobile UX: simplify navigation without losing Chat, Quiz,
   course syllabus, timer, profile preferences or server configuration. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const app = fs.readFileSync("mobile/App.js","utf8");
const connection=fs.readFileSync("mobile/src/ConnectionSettings.js","utf8");
const client=fs.readFileSync("mobile/src/api.js","utf8");
const bubble=fs.readFileSync("mobile/src/FloatingStudyChat.js","utf8");

const tabBlock = app.match(/const tabs = \[([\s\S]*?)\];/);
assert(tabBlock, "Bottom tab definition missing");
const tabs=[...tabBlock[1].matchAll(/\['([^']+)',/g)].map(m=>m[1]);
assert.deepEqual(tabs,["home","subjects","plan","profile"]);
assert(!tabs.includes("agent")&&!tabs.includes("quiz"));
assert(app.includes("<FloatingStudyChat subjects={subjects} lesson={activeLesson}"),
  "Keep floating AI globally accessible");
assert(bubble.includes("api.studyChat"),"Keep verified session Chat");
assert(app.includes("onOpenQuiz={openQuiz}"),"Quiz entry point in course details");
assert(app.includes("onOpenQuiz={() => openQuiz(null)}"),
  "Quiz history and weaknesses entry point in Profile");
assert(app.includes("info?.subjectId || activeLesson?.subjectId") &&
  app.includes("info?.quizId || null"),
  "Session Quiz must retain course and server-issued quiz ID");
assert(app.includes("if (tab === 'quiz') return <QuizScreen"),
  "Quiz remains fully accessible by secondary navigation");
assert(app.includes("if (tab === 'plan') return <PlanScreen"),
  "Timetable must remain accessible");
assert(app.includes("api.scheduleRoadmap(selectedId)"),
  "Official roadmap sessions must be schedulable on Mobile");
assert(app.includes("onOpenSubjectJourney(item.subject_id || null, 'roadmap')"),
  "Learning plan suggestions must open the verified roadmap");

assert(app.includes("setShowLearningSettings(v => !v)"),
  "Advanced learning preferences should be disclosed on demand");
assert(app.includes("onOpenConnection={() => setShowConnectionSettings(true)}"),
  "Signed-in account settings can open connection screen");
assert(app.includes("onOpenConnection={() => setShowConnectionSettings(true)}"),
  "Login connection shortcut must exist");
const login=app.slice(app.indexOf("function LoginScreen("),
  app.indexOf("export default function App()"));
assert(!login.includes("API_BASE_URL"),"IP must not appear on main login screen");
assert(!login.includes("authSegmentButton"),"Signup must be a small link not a large tab");
assert(login.includes("Đăng ký sinh viên"),"Signup remains available");
assert(login.includes("secureTextEntry={!showPassword}"),"Password visibility retained");
assert(login.includes("secureTextEntry={!showConfirm}"),"Signup confirmation retained");
assert(connection.includes("testApiConnection(address)"),
  "Check Flask before changing server URL");
assert(connection.includes("persistServerAddress(address)"),"Validated Flask URL must persist on device");
assert(connection.includes("Địa chỉ đã kiểm tra được lưu trên điện thoại"),
  "Connection settings should explain persistent origin and required Flask server");
assert(client.includes("fetch(value + '/api/mobile/session'"),
  "The URL probe must check real Flask API");
assert(client.includes("response.status !== 401"),
  "HTTP 401 from unauthenticated server is successful connectivity");
assert(client.includes("fetch(`${activeBaseUrl}${path}`"),
  "All Mobile API requests use the same selected URL");
console.log("Mobile minimal UX PASS: four tabs, nested Quiz, bubble, login, server settings");
