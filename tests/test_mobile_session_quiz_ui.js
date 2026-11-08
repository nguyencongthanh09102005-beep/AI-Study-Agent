"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const app=fs.readFileSync("mobile/App.js","utf8");
const room=fs.readFileSync("mobile/src/StudyRoom.js","utf8");
const client=fs.readFileSync("mobile/src/api.js","utf8");
const server=fs.readFileSync("mobile_learning_routes.py","utf8");
const back=fs.readFileSync("study_session_quiz_runtime.py","utf8");

for(const apiName of [
  "sessionQuizStatus","sessionQuizStart","quizPreparation",
  "quizPreparationAction","quizReview"
]) assert(client.includes(apiName+":"),"Missing Mobile API: "+apiName);
for(const route of ["quiz-status","quiz-start","quiz-preparation","review"])
  assert(server.includes(route),"Missing Mobile Flask route: "+route);
assert(server.includes("start_quiz(conn,project,uid,quiz_id)"),
  "Mobile Quiz must use same verified, time-gated Web start function");
assert(server.includes("per_lesson_quiz_status(conn,project,uid,task_id)"),
  "Mobile Quiz must be backed by source-verified server status");
assert(server.includes("secrets.compare_digest(expected, supplied)"),
  "Queue/start actions must require CSRF");
assert(server.includes('action not in ("start","pause")'),
  "Only explicitly approved prep actions are accepted");
assert(server.includes("start_local_worker(project)"),
  "Background queue must use existing Quiz worker");
assert(server.includes('if not attempt:') &&
  server.includes('Chỉ được xem đáp án sau khi nộp bài'),
  "Review must require a real submitted attempt");
assert(server.includes('quiz_access(conn,project,uid,quiz_id)'),
  "Review must preserve stale-source restrictions");
assert(back.includes('if at >= start:'),
  "Quiz must stay accessible after its first opening time");
assert(back.includes('datetime.fromisoformat(grant["started_at"]) <= at'),
  "Earlier grants must not expire when the study window ends");
assert(back.includes('review_unlocked'),
  "Submitted Quiz revision remains available");
assert(room.includes("api.sessionQuizStatus(taskId)"),
  "Mobile study room must show actual Quiz status");
assert(room.includes("api.quizPreparationAction("),
  "Student must opt in to preparation");
assert(room.includes("api.sessionQuizStart(taskId,quizCsrf.current)"),
  "Open session Quiz via server time gate");
assert(room.includes("sessionQuiz?.is_final?'Buổi tổng hợp · 60 câu'"),
  "Final session must distinguish 60 questions");
assert(room.includes("sessionQuiz?.count"),"Lesson count from server");
assert(app.includes("initialQuizId={quizToOpenId}"),
  "Pass server-selected prepared Quiz to QuizScreen");
assert(app.includes("api.quizDetail(initialQuizId)"),
  "Read questions after server opens Quiz");
assert(app.includes("ref={quizScrollRef}") &&
  app.includes("quizScrollRef.current?.scrollTo({ y: 0, animated: false })"),
  "Opening a saved Quiz must reset its old list scroll offset");
assert(app.includes("listQuizError?.id === item.id") &&
  app.includes("setListQuizError({ id, message:"),
  "A saved Quiz access error must appear beside the tapped item");
assert(app.includes("api.quizReview(id)"),
  "Previously submitted answers must be reviewable");
assert(app.includes("api.quizSubmit(quiz.quiz_id,answers,submitKey.current)"),
  "Quiz submit should be idempotent");
assert(app.includes("quiz.questions?.slice(currentQuestion,currentQuestion+1)"),
  "Show one question at a time for 15/60 question UX");
assert(app.includes("Vui lòng trả lời đủ"),
  "Cannot submit incomplete Quiz");
assert(app.includes("Xác nhận nộp Quiz"),
  "Explicit submission, do not auto-submit on last question");
assert(!client.includes("correct_answers:"),
  "Never construct answer keys in Mobile requests");
console.log("Mobile session Quiz PASS: locked 15/60, queued prep, submission, safe review, pagination");
