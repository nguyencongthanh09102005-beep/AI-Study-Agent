/* The floating Chat retains its existing UI but mirrors full Web Chat's
   subject and verified chapter scope, never trusts unverified client state.
   Client contract test; real Gemini API calls are not made here. */
"use strict";
const fs = require("fs");
const assert = require("assert");

const full = fs.readFileSync("static/js/chat.js", "utf8");
const bubble = fs.readFileSync("static/js/ai_bubble.js", "utf8");
const template = fs.readFileSync("templates/base.html", "utf8");
const backend = fs.readFileSync("app.py", "utf8");

for (const unwanted of [
  "floatingAiLearningMode", "floatingAiFreeMode",
  "floatingAiChapterMode", "floatingAiChapterLabel", "floatingAiChapter"
]) {
  assert(!template.includes('id="' + unwanted + '"'),
    "Floating Chat must not add a mode/chapter control: " + unwanted);
}
assert(template.includes('id="floatingAiCourse"'),
  "Keep original course selector");
assert(template.includes('id="floatingAiTabSupport"'),
  "Do not change schedule support tab");
assert(full.includes('api("/api/chat"'), "Full Web Chat uses /api/chat");
assert(bubble.includes('api("/api/chat"'), "Floating Chat uses same /api/chat");
assert(full.includes('lessonMode.chapter_number'), "Full Web Chat passes chapter");
assert(full.includes('"ai-study-chat-chapter-v1:" + subjectId'),
  "Full Web Chat remembers approved chapter for the floating Chat");
assert(full.includes('"ai-study-active-subject-v1"'),
  "Full Web Chat remembers current subject");
assert(bubble.includes('CHAPTER_KEY_PREFIX + expectedSubject'),
  "Floating Chat loads chapter of current subject, not another subject");
assert(bubble.includes('readSessionNumber(ACTIVE_SUBJECT_KEY)'),
  "Floating Chat restores Web Chat's selected course");
assert(bubble.includes('"/api/chat/lesson-context?"'),
  "Floating Chat revalidates saved chapter on server");
assert(bubble.includes('token !== requestToken || subjectId !== expectedSubject'),
  "Late validation response must not switch selected subjects");
assert(bubble.includes('lesson:{chapter_number:selectedChapter}'),
  "Floating Chat sends same chapter argument as full Chat");
assert(bubble.includes('data.source_mode !== "chapter"'),
  "Bubble must reject a response outside verified chapter scope");
assert(bubble.includes('syncedChapter = null;') &&
  bubble.includes('enable(false);'),
  "Failed chapter validation must not downgrade silently");
assert(!bubble.includes("floatingAiLearningMode") &&
  !bubble.includes("floatingAiChapterMode"),
  "Bubble JavaScript must not rely on unwanted UI controls");
assert(backend.includes('requested_lesson = payload.get("lesson")'),
  "Server remains the source of truth for chapter authorization");
console.log("Floating/full Chat parity PASS: original UI, same subject/chapter/backend");
