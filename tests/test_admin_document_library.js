/* Client regression for the compact Admin shared document library. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function el(id) {
  return {
    id, hidden:false, open:false, textContent:"", value:"",
    dataset:{}, handlers:{},
    addEventListener(type, callback) {
      (this.handlers[type] ||= []).push(callback);
    },
    fire(type, event = {}) {
      for (const callback of this.handlers[type] || []) callback(event);
    },
    focus() { this.focused = true; },
  };
}
function row(name, kind) {
  const result = el("row");
  result.dataset.search = name;
  result.dataset.kind = kind;
  return result;
}
function group(id, rows, initiallyOpen) {
  const result = el(id);
  result.open = initiallyOpen;
  result.badge = el("badge");
  result.rows = rows;
  result.querySelectorAll = selector => {
    assert.equal(selector, "[data-admin-doc-row]");
    return rows;
  };
  result.querySelector = selector => {
    assert.equal(selector, "[data-admin-doc-count]");
    return result.badge;
  };
  return result;
}
function menu(id) {
  const result = el(id);
  result.trigger = el("summary");
  result.querySelector = selector => {
    assert.equal(selector, "summary");
    return result.trigger;
  };
  return result;
}

const search = el("adminDocSearch");
const filter = el("adminDocFilter");
filter.value = "all";
const empty = el("adminDocEmpty");
const status = el("adminDocStatus");

const oop = group("oop", [
  row("Tư duy thiết kế OOP-TEST-2026 Đề cương chi tiết", "syllabus"),
  row("Tư duy thiết kế OOP-TEST-2026 Chương 1 Thấu cảm", "material")
], true);
const history = group("history", [
  row("Lịch sử Đảng 68209281 Chương 1 Sự ra đời", "material"),
  row("Lịch sử Đảng 68209281 Chương 2 bản scan", "unextracted")
], false);
const menus = [menu("menu1"),menu("menu2")];
const groups = [oop,history];
const root = {
  querySelectorAll(selector) {
    if (selector === "[data-admin-document-group]") return groups;
    if (selector === "[data-admin-doc-menu]") return menus;
    if (selector === "[data-admin-doc-row]") return groups.flatMap(group=>group.rows);
    throw new Error("Unexpected selector: " + selector);
  }
};
const documentHandlers={};
const doc={
  readyState:"complete",
  getElementById(id) {
    return ({
      adminDocumentLibrary:root,adminDocSearch:search,adminDocFilter:filter,
      adminDocEmpty:empty,adminDocStatus:status
    })[id]||null;
  },
  addEventListener(type,callback) { (documentHandlers[type] ||= []).push(callback); }
};
vm.runInNewContext(fs.readFileSync(
  path.join(__dirname,"../static/js/admin_document_library.js"),"utf8"
),{document:doc});

assert.equal(status.textContent,"Đang hiển thị 4/4 tài liệu gần đây.");
assert.equal(oop.open,true);
assert.equal(history.open,false);
assert.equal(history.badge.textContent,"2 file");

search.value="LICH SU DANG";
search.fire("input");
assert.equal(oop.hidden,true,"Other course should hide");
assert.equal(history.hidden,false);
assert.equal(history.open,true,"Matching collapsed course should open");
assert.equal(history.rows[0].hidden,false,"Accent-insensitive search");
assert.equal(status.textContent,"Đang hiển thị 2/4 tài liệu gần đây.");

search.value="";
filter.value="syllabus";
filter.fire("change");
assert.equal(oop.hidden,false);
assert.equal(oop.rows[0].hidden,false);
assert.equal(oop.rows[1].hidden,true);
assert.equal(history.hidden,true);
assert.equal(oop.badge.textContent,"1 file");
assert.equal(status.textContent,"Đang hiển thị 1/4 tài liệu gần đây.");

filter.value="all";
filter.fire("change");
assert.equal(oop.open,true);
assert.equal(history.open,false,"Reset must restore original disclosure state");
assert.equal(empty.hidden,true);
assert.equal(status.textContent,"Đang hiển thị 4/4 tài liệu gần đây.");

search.value="unrelated";
search.fire("input");
assert.equal(empty.hidden,false);
assert.equal(oop.hidden,true);
assert.equal(history.hidden,true);
search.value="";
search.fire("input");

menus[0].open=true;
menus[0].fire("toggle");
menus[1].open=true;
menus[1].fire("toggle");
assert.equal(menus[0].open,false,"Only one menu remains open");
assert.equal(menus[1].open,true);
for(const cb of documentHandlers.keydown || []) cb({key:"Escape"});
assert.equal(menus[1].open,false);
assert.equal(menus[1].trigger.focused,true,"Escape restores keyboard focus");

console.log("Admin shared document groups PASS: search, filters, counts, disclosures and menu keyboard");
