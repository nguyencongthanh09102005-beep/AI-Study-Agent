/* Full Chat and floating Chat share the same source-backed API and chapter choice.
   Static client-contract regression; real API and authorization remain server-side. */
"use strict";
const fs = require("fs");
const assert = require("assert");

const full = fs.readFileSync("static/js/chat.js", "utf8");
const bubble = fs.readFileSync("static/js/ai_bubble.js", "utf8");
const template = fs.readFileSync("templates/base.html", "utf8");
const backend = fs.readFileSync("app.py", "utf8");

for (const id of [
  "floatingAiLearningMode", "floatingAiFreeMode",
  "floatingAiChapterMode", "floatingAiChapterLabel", "floatingAiChapter"
]) {
  assert(template.includes('id="' + id + '"'), "Missing floating Chat control: " + id);
}
assert(full.includes('api("/api/chat"'), "Full Web Chat must use /api/chat");
assert(bubble.includes('api("/api/chat"'), "Floating Chat must use /api/chat");
assert(full.includes('lesson: {') && full.includes('lessonMode.chapter_number'),
  "Full Web Chat must submit verified chapter number");
assert(bubble.includes('lesson:{chapter_number:requestedChapter}'),
  "Floating Chat must submit chapter number when guided mode is enabled");
assert(bubble.includes('"/api/chat/course-outline?subject_id="'),
  "Floating Chat must list actual confirmed chapters");
assert(bubble.includes('"/api/chat/lesson-context?"'),
  "Floating Chat must authorize and validate the chosen chapter");
assert(bubble.includes('if (token !== requestToken || scopedSubject !== subjectId) return'),
  "Late chapter replies cannot change another selected course");
assert(bubble.includes('chapterScope = null;') && bubble.includes('enable(false);'),
  "Chapter verification failures must disable Chat rather than switch to free");
assert(full.includes('"ai-study-chat-chapter-v1:" + subjectId'),
  "Full Chat must remember the chapter for the floating Chat");
assert(bubble.includes('"ai-study-chat-chapter-v1:" + id'),
  "Floating Chat must restore the same chapter for the chosen course");
assert(bubble.includes('data.source_mode !== "chapter"'),
  "The bubble must reject mismatched response mode");
assert(backend.includes('requested_lesson = payload.get("lesson")'),
  "The server must validate the lesson scope from either Chat surface");
console.log("Floating/full Chat parity PASS: one /api/chat, shared chapter selection, scoped sources");
