"use strict";
const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function mockNode() {
  const handlers = {};
  const classes = new Set();
  return {
    handlers,
    classList: {
      add(v) { classes.add(v); },
      remove(v) { classes.delete(v); },
      contains(v) { return classes.has(v); }
    },
    addEventListener(event, handler) { handlers[event] = handler; },
    contains() { return false; },
    click() { this.clicks = (this.clicks || 0) + 1; },
    dispatchEvent(event) {
      this.changes = (this.changes || 0) + 1;
      if (handlers[event.type]) handlers[event.type](event);
    }
  };
}

const zone = mockNode();
const input = Object.assign(mockNode(), {files: [], value: ""});
const form = mockNode();
const error = {hidden: true, textContent: ""};
const elements = {documentDropzone:zone, documentFileInput:input,
                  uploadForm:form, uploadSizeError:error};
const document = {
  readyState: "complete",
  getElementById(id) {return elements[id] || null;}
};
const window = mockNode();
function DataTransfer() {
  this.files = [];
  this.items = {add: file => this.files.push(file)};
}
function Event(name) {this.type = name;}
vm.runInNewContext(
  fs.readFileSync("static/js/document_dropzone.js", "utf8"),
  {document,window,DataTransfer,Event},
  {filename:"static/js/document_dropzone.js"}
);
let prevented = false;
zone.handlers.keydown({key:"Enter", preventDefault() {prevented = true;}});
assert.strictEqual(prevented,true);
assert.strictEqual(input.clicks,1);
zone.handlers.dragover({preventDefault() {},dataTransfer:{dropEffect:""}});
assert.strictEqual(zone.classList.contains("is-drag-over"),true);
const uploaded = {name:"Đề cương.docx",size:60000};
zone.handlers.drop({preventDefault(){},dataTransfer:{files:[uploaded]}});
assert.strictEqual(zone.classList.contains("is-drag-over"),false);
assert.strictEqual(input.files[0],uploaded);
assert.strictEqual(input.changes,1);
zone.handlers.drop({preventDefault(){},dataTransfer:{files:[{name:"virus.exe"}]}});
assert.strictEqual(input.value,"");
assert.strictEqual(error.hidden,false);
assert.strictEqual(error.textContent.includes("PDF, DOCX, TXT hoặc MD"),true);
assert.strictEqual(input.changes,2);
window.handlers.dragend();
console.log("Document drag-drop UI PASS: browse keyboard, drag highlight, file selection, invalid type");
