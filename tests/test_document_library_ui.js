"use strict";
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function eventNode(dataset, props) {
  const handlers = {};
  return Object.assign({
    dataset: dataset || {},
    handlers,
    attrs: {},
    hidden: false,
    tabIndex: -1,
    addEventListener(name, fn) { handlers[name] = fn; },
    setAttribute(key, value) { this.attrs[key] = value; },
    focus() { this.focused = true; }
  }, props || {});
}

const tabs = [
  eventNode({libraryTab: "personal"}),
  eventNode({libraryTab: "shared"})
];
const file1 = eventNode({searchable: "Đề cương chuẩn lịch sử"});
const file2 = eventNode({searchable: "Bài giảng chương 1"});
const file3 = eventNode({searchable: "Tài liệu Đại số"});
const pHistory = eventNode({folderName: "Lịch sử Đảng HIS102"}, {
  open: false,
  querySelectorAll(selector) { return selector === "[data-library-file]" ? [file1, file2] : []; }
});
const pMath = eventNode({folderName: "Đại số tuyến tính MATH1"}, {
  open: true,
  querySelectorAll(selector) { return selector === "[data-library-file]" ? [file3] : []; }
});
const sHistory = eventNode({folderName: "Lịch sử Đảng HIS102"}, {
  open: false,
  querySelectorAll(selector) { return selector === "[data-library-file]" ? [file1] : []; }
});
const panels = [
  eventNode({libraryPanel: "personal"}, {
    querySelectorAll(selector) { return selector === "[data-library-folder]" ? [pHistory,pMath] : []; }
  }),
  eventNode({libraryPanel: "shared"}, {
    hidden: true,
    querySelectorAll(selector) { return selector === "[data-library-folder]" ? [sHistory] : []; }
  })
];
const root = {
  querySelectorAll(selector) {
    return selector === "[data-library-tab]" ? tabs :
      selector === "[data-library-panel]" ? panels : [];
  }
};
const search = eventNode({}, {value: ""});
const message = eventNode({}, {hidden: true, textContent: ""});
const elements = {
  documentLibrary: root, documentLibrarySearch: search,
  librarySearchStatus: message
};
const document = {
  readyState: "complete",
  getElementById(id) { return elements[id] || null; },
  addEventListener() { throw new Error("DOMContentLoaded not expected"); }
};
vm.runInNewContext(
  fs.readFileSync("static/js/document_library.js", "utf8"),
  {document, window: {location: {search: ""}}, URLSearchParams},
  {filename: "static/js/document_library.js"}
);
assert.strictEqual(tabs[0].attrs["aria-selected"], "true");
assert.strictEqual(tabs[1].attrs["aria-selected"], "false");
assert.strictEqual(panels[0].hidden, false);
assert.strictEqual(panels[1].hidden, true);
search.value = "lich su";
search.handlers.input();
assert.strictEqual(pHistory.hidden, false);
assert.strictEqual(pHistory.open, true);
assert.strictEqual(pMath.hidden, true);
assert.strictEqual(message.hidden, false);
assert.strictEqual(message.textContent.includes("1 môn"), true);
search.value = "bai giang";
search.handlers.input();
assert.strictEqual(file1.hidden, true);
assert.strictEqual(file2.hidden, false);
tabs[1].handlers.click();
assert.strictEqual(panels[1].hidden, false);
assert.strictEqual(panels[0].hidden, true);
search.value = "";
search.handlers.input();
assert.strictEqual(pMath.open, true);
assert.strictEqual(pHistory.open, false);
assert.strictEqual(message.hidden, true);
let prevented = false;
tabs[1].handlers.keydown({key:"ArrowLeft", preventDefault() {prevented = true;}});
assert.strictEqual(prevented, true);
assert.strictEqual(tabs[0].attrs["aria-selected"], "true");
assert.strictEqual(tabs[0].focused, true);
console.log("Document library UI PASS: tabs, keyboard, accent search, folder expansion and reset");
