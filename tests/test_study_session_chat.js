/* Embedded tutor must only reuse verified lesson mode, with no HTML injection. */
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "..");
const js = fs.readFileSync(path.join(root,"static/js/study_session_chat.js"),"utf8");
const room = fs.readFileSync(path.join(root,"templates/study_session.html"),"utf8");
assert.match(room,/data-chat-enabled="{{ '1' if chat_ready else '0' }}"/);
assert.match(room,/studyRoomChatForm/);
assert.match(room,/{% block scripts %}/);
assert.match(js,/\/api\/study-plan\/tasks\/.*\/chat-history/);
assert.match(js,/\/api\/chat/);
assert.match(js,/lesson: \{chapter_number: chapterNumber, task_id: taskId\}/);
assert.match(js,/body\.textContent/);
assert.doesNotMatch(js,/innerHTML|outerHTML|insertAdjacentHTML/);
assert.doesNotMatch(js,/\/api\/mobile\/chat/);
assert.match(room,/Mở Chat AI thông thường/);
console.log("6.3.2 embedded verified chat frontend checks OK");
