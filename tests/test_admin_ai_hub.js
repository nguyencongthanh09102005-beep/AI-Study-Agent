/* Verify Admin's shared subject picker and both *navigation-only* actions. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const handlers = {};
function element(id) {
  return {
    id,
    disabled:false,
    textContent:"",
    listeners:{},
    addEventListener(type,fn) { this.listeners[type]=fn; },
    focus() { this.focused=true; },
    click() { this.listeners.click?.(); },
  };
}
const select = element("adminAiSubject");
const syllabus = element("adminAiSyllabus");
const bulk = element("adminAiBulk");
const sState = element("adminAiSyllabusState");
const bState = element("adminAiBulkState");
const help = element("adminAiHelp");
const els = {
  adminAiSubject:select, adminAiSyllabus:syllabus, adminAiBulk:bulk,
  adminAiSyllabusState:sState, adminAiBulkState:bState, adminAiHelp:help
};
select.selectedIndex=0;
select.options=[
  {value:"",dataset:{}},
  {value:"17",dataset:{
    syllabusUrl:"/admin/subjects/17/syllabus-analysis",
    bulkUrl:"/admin/subjects/17/chapters/bulk",
    hasSyllabus:"1",documentCount:"6"
  }},
  {value:"18",dataset:{
    syllabusUrl:"/admin/subjects/18/syllabus-analysis",
    bulkUrl:"/admin/subjects/18/chapters/bulk",
    hasSyllabus:"0",documentCount:"0"
  }},
  {value:"19",dataset:{
    syllabusUrl:"https://malicious.test",bulkUrl:"//malicious.test",
    hasSyllabus:"1",documentCount:"1"
  }}
];
const locations=[];
const ctx={
  document:{getElementById:id=>els[id]||null},
  window:{location:{assign:url=>locations.push(url)}},
};
vm.runInNewContext(fs.readFileSync(
  path.join(__dirname,"../static/js/admin_ai_hub.js"),"utf8"),ctx);
assert.equal(syllabus.disabled,true);
assert.equal(bulk.disabled,true);
assert.match(help.textContent,/Chọn môn học/);
select.selectedIndex=1;
select.listeners.change();
assert.equal(syllabus.disabled,false);
assert.equal(bulk.disabled,false);
assert.match(sState.textContent,/Đã có đề cương/);
assert.match(bState.textContent,/6 tài liệu/);
syllabus.click();
bulk.click();
assert.deepEqual(locations,[
  "/admin/subjects/17/syllabus-analysis",
  "/admin/subjects/17/chapters/bulk"
]);
select.selectedIndex=2;
select.listeners.change();
assert.match(help.textContent,/tải đề cương chuẩn/);
assert.match(bState.textContent,/Chưa có tài liệu/);
bulk.click();
assert.equal(locations.at(-1),"/admin/subjects/18/chapters/bulk");
// Never follow a provider-external or protocol-relative URL even if DOM changed.
select.selectedIndex=3;
select.listeners.change();
const count=locations.length;
syllabus.click();bulk.click();
assert.equal(locations.length,count);
console.log("Admin AI hub selector PASS: states, 2 routes, empty course and safe URLs");
