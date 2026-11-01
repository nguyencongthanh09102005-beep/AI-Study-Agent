"use strict";
// Exercise Mobile's API service in a JS sandbox without Expo, Gemini or Flask.
// Verifies that all student Chat requests share Web's grounded endpoint.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const code = fs.readFileSync("mobile/src/api.js","utf8")
  .replace(/export const /g, "const ")
  .replace(/export function /g, "function ");
let calls=[];
let conversationId=73;
function reply(data, status=200) {
  return {ok:status>=200&&status<300,status,
    text:async()=>JSON.stringify(data)};
}
const sandbox={
  process:{env:{EXPO_PUBLIC_API_URL:"http://127.0.0.1:5000"}},
  FormData:class FormData {},
  fetch:async(url,options={})=>{
    calls.push({url,options});
    if(url.endsWith("/api/mobile/chat/31"))
      return reply({conversation_id:conversationId,messages:[]});
    if(url.endsWith("/api/chat"))
      return reply({answer:"Theo tài liệu đã xác minh.",source_mode:"chapter",
        lesson:{chapter_number:2}});
    throw Error("Unexpected API "+url);
  }
};
vm.runInNewContext(code+"\n;this.api=api;this.setApiBaseUrl=setApiBaseUrl;",sandbox);
(async()=>{
  const api=sandbox.api;
  const free=await api.chat(31,"Giải thích cây nhị phân");
  assert.equal(free.answer,"Theo tài liệu đã xác minh.");
  assert.equal(calls.length,2);
  assert(calls[0].url.endsWith("/api/mobile/chat/31"));
  assert(calls[1].url.endsWith("/api/chat"));
  assert.equal(calls[1].options.credentials,"include");
  assert.deepEqual(JSON.parse(calls[1].options.body),{
    conversation_id:73,question:"Giải thích cây nhị phân"
  });
  calls=[];
  await api.studyChat(31,"Bài học hôm nay?",82,2);
  assert.equal(calls.length,2);
  assert.deepEqual(JSON.parse(calls[1].options.body),{
    conversation_id:73,question:"Bài học hôm nay?",
    lesson:{chapter_number:2,task_id:82}
  });
  calls=[];
  conversationId=null;
  await assert.rejects(api.chat(31,"Không có lịch sử"),
    /Không xác định được hội thoại/);
  assert.equal(calls.length,1,"No AI generation when no owned conversation");
  calls=[];
  conversationId=73;
  sandbox.setApiBaseUrl("http://192.168.1.23:5000");
  await api.chat(31,"Chuyển địa chỉ kết nối");
  assert(calls.every(c=>c.url.startsWith("http://192.168.1.23:5000/")));
  console.log("Mobile Chat parity PASS: owner scoped /api/chat, lesson context, IP switch");
})().catch(e=>{console.error(e);process.exitCode=1;});
