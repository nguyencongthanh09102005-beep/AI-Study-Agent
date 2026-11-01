"use strict";
/* Mobile feature parity contract. Expo export validates actual RN/JSX.
   No fabricated content, no additional mobile chatbot backend. */
const assert=require("node:assert/strict");
const fs=require("node:fs");
const read=x=>fs.readFileSync(x,"utf8");
const app=read("mobile/App.js");
const bubble=read("mobile/src/FloatingStudyChat.js");
const room=read("mobile/src/StudyRoom.js");
const client=read("mobile/src/api.js");
const server=read("mobile_learning_routes.py");
const flask=read("app.py");
for(const keyword of [
  "import FloatingStudyChat", "import StudyRoom",
  "onOpenStudy", "onContext={setActiveLesson}",
  "<FloatingStudyChat subjects={subjects} lesson={activeLesson}",
  "api.roadmap(id)", "roadmap?.sessions",
  "findTaskConflicts", "Tạo Quiz ôn điểm yếu",
])assert(app.includes(keyword),"Missing Mobile integration: "+keyword);
assert(bubble.includes("PanResponder.create"),"Floating Chat must be draggable");
assert(bubble.includes("<Modal"),"Floating Chat should stay within Expo Go");
assert(bubble.includes("api.chatHistory(scopedId)"),"Reuse one chat history");
assert(bubble.includes("api.studyChat"),"Verified lesson route when in study room");
assert(bubble.includes("api.chat(scopedId"),"Same subject Chat outside study room");
assert(bubble.includes("MÔN ĐANG HỎI") && bubble.includes("currentSubject?.name"),
  "Selected subject must remain identifiable by its full course name");
assert(bubble.includes("showSubjectPicker") && bubble.includes("Đổi môn học trong Chat AI"),
  "Course selector must open an accessible course picker");
assert(bubble.includes("{s.name}") && bubble.includes("subjectOptionName"),
  "Every selectable subject shows its full name, not a truncated chip");
assert(bubble.includes("subjectOptionsScroll:{maxHeight:210}"),
  "Long subject lists must scroll within the panel");
assert(bubble.includes("setShowSubjectPicker(false);") &&
  bubble.includes("setSubjectId(id);"),
  "Selecting a new subject closes the picker and reloads scoped history");
assert(!bubble.includes("subjectList:{maxHeight:54"),
  "Clipped horizontal course chips must not reappear");

assert(bubble.includes("lessonHasSources"),"Never claim unapproved lesson sources");
assert(room.includes("api.studyRoom(taskId)"),"Load server-owned lesson");
assert(room.includes("clo_refs"),"Display official CLO references");
assert(room.includes("api.studyTimer("),"Use server timer, not device duration");
assert(room.includes("'heartbeat'"),"Keep server duration authoritative");
assert(room.includes("Alert.alert('Hoàn thành buổi học?'"),"Explicit finish");
assert(!room.includes("api.toggleTask(taskId)"),
  "Do not bypass server timer by marking task done");
assert(client.includes("'/api/chat'"),"Web-grade source verification is reused");
assert(client.includes("conversation_id: conversationId"),
  "Server must own the chat conversation ID");
assert(client.includes("/api/mobile/study-room/"),"Room is server backed");
assert(flask.includes("app.register_blueprint(mobile_learning_bp)"));
assert(server.includes("verified_roadmap_task"),"Ownership and stale guard");
assert(server.includes("secrets.compare_digest"),"CSRF for timer writes");
assert(server.includes("approved_document_rows"),"No fake PDF references");
assert(server.includes("session_signature"),"No stale lesson schedule");
assert(!server.includes("gemini_generate"),"No second AI generation path");
console.log("Mobile feature parity PASS: bubble, roadmap, room, timer, CLO, quiz, ACL");
