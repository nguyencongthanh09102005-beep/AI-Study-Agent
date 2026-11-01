"use strict";
/* Regression: one branded confirmation system works for original POST forms
   and async timetable/timer prompts. No browser-native dialogs survive in
   student/admin JS/templates. This test makes no network requests. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const read = p => fs.readFileSync(path.join(root, p), "utf8");

class Element {
  constructor() {
    this.listeners = {};
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this.disabled = false;
    const values = new Set();
    this.classList = {
      add: x => values.add(x),
      remove: x => values.delete(x),
      contains: x => values.has(x)
    };
    this.isConnected = true;
  }
  addEventListener(event, callback) { (this.listeners[event] ||= []).push(callback); }
  emit(event, data) {
    for (const callback of this.listeners[event] || []) callback(data);
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  focus() { document.activeElement = this; }
}
class FakeForm extends Element {
  constructor() { super(); this.submissions = []; this.fields = {csrf_token:"kept", confirm_code:"CODE"}; }
  matches(selector) { return selector === "form[data-confirm-message]"; }
  requestSubmit(button) {
    const event = {target:this, submitter:button, prevented:false,
      preventDefault() { this.prevented=true; }};
    document.emit("submit",event);
    if (!event.prevented) this.submissions.push({button, fields:{...this.fields}});
  }
}
const modal = new Element(), confirmForm = new Element(), heading = new Element(),
  message = new Element(), confirmButton = new Element(), icon = new Element(),
  dialog = new Element(), cancelButton = new Element(), firstFocus = new Element();
const byId = {
  appConfirmModal:modal, appConfirmForm:confirmForm,
  appConfirmTitle:heading, appConfirmMessage:message,
  appConfirmDeleteButton:confirmButton
};
modal.querySelector = selector => ({
  ".app-confirm-icon":icon, ".app-confirm-dialog":dialog,
  ".app-confirm-cancel":cancelButton
})[selector];
modal.querySelectorAll = selector => selector === "[data-confirm-close]" ? [cancelButton] : [];
const document = {
  activeElement:firstFocus, body:{style:{overflow:"scroll"}},
  listeners:{},
  getElementById:id=>byId[id],
  addEventListener(event, callback) { (this.listeners[event] ||= []).push(callback); },
  emit(event,data) { for (const f of this.listeners[event] || []) f(data); }
};
const window = {requestAnimationFrame:f=>f()};
const source=read("static/js/confirm-modal.js");
vm.runInNewContext(source,{document,window,HTMLFormElement:FakeForm,WeakSet,Promise});
document.emit("DOMContentLoaded");
assert.equal(typeof window.AppDialogs?.confirm,"function");
const flush=async()=>{await Promise.resolve();await Promise.resolve();};
async function check() {
  const form = new FakeForm(), submitter = new Element();
  submitter.form = form;
  form.dataset = {
    confirmTitle:"Xóa môn chung?", confirmMessage:"Giữ nguyên dữ liệu cá nhân",
    confirmLabel:"Xóa môn", confirmKind:"danger"
  };
  form.requestSubmit(submitter);
  assert.equal(form.submissions.length,0,"Pre-confirmation must not submit");
  assert.equal(heading.textContent,"Xóa môn chung?");
  assert.equal(message.textContent,"Giữ nguyên dữ liệu cá nhân");
  assert.equal(confirmButton.textContent,"Xóa môn");
  cancelButton.emit("click",{});
  await flush();
  assert.equal(form.submissions.length,0,"Cancel must not submit");
  assert.equal(document.body.style.overflow,"scroll","Restore prior scroll state");
  assert.equal(document.activeElement,firstFocus,"Restore focus");

  form.requestSubmit(submitter);
  confirmForm.emit("submit",{preventDefault(){}});
  await flush();
  assert.equal(form.submissions.length,1,"Confirm must submit original form exactly once");
  assert.equal(form.submissions[0].button,submitter,"Preserve submitter button");
  assert.deepEqual(form.submissions[0].fields,{csrf_token:"kept",confirm_code:"CODE"});
  assert.equal(modal.classList.contains("show"),false);

  const decision=window.AppDialogs.confirm({
    title:"Lịch học trùng giờ", message:"Có 1 buổi trùng giờ.",
    confirmLabel:"Giữ khung giờ",kind:"warning"
  });
  assert.equal(modal.dataset.kind,"warning");
  assert.equal(heading.textContent,"Lịch học trùng giờ");
  confirmForm.emit("submit",{preventDefault(){}});
  assert.equal(await decision,true);
  const rejected=window.AppDialogs.confirm({title:"Hoàn thành buổi học?"});
  document.emit("keydown",{key:"Escape",preventDefault(){}});
  assert.equal(await rejected,false,"Escape cancels");

  const pages=fs.readdirSync(path.join(root,"templates")).filter(x=>x.endsWith(".html"));
  const scripts=fs.readdirSync(path.join(root,"static/js")).filter(x=>x.endsWith(".js"));
  const nativeCall=/(?<![\w.])(?:window\.)?(?:alert|confirm|prompt)\s*\(/g;
  const remaining=[];
  for(const file of [...pages.map(x=>"templates/"+x), ...scripts.map(x=>"static/js/"+x)]){
    const lines=read(file).split("\n");
    lines.forEach((line,index)=>{
      const cleaned=line.replace(/\/\/.*$/,"");
      if(nativeCall.test(cleaned))remaining.push(file+":"+(index+1));
      nativeCall.lastIndex=0;
    });
  }
  assert.deepEqual(remaining,[],"Browser-native popup calls remain: "+remaining.join(", "));
  assert.match(read("static/js/study_plan.js"),/AppDialogs\.confirm/);
  assert.match(read("static/js/study_session_timer.js"),/AppDialogs\.confirm/);
  assert.match(read("templates/admin.html"),/data-confirm-kind="danger"/);
  console.log("Shared dialogs PASS: approve/cancel/escape, CSRF, styles, no native JS popups");
}
check().catch(err=>{console.error(err);process.exitCode=1;});
