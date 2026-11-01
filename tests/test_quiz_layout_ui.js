"use strict";
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

function node(opts = {}) {
  const listeners = {};
  const classes = new Set(opts.classes || []);
  return Object.assign({
    dataset: {}, hidden: false, listeners, attrs: {},
    textContent: "",
    classList: {
      toggle(name, value) {
        const add = value === undefined ? !classes.has(name) : !!value;
        if (add) classes.add(name); else classes.delete(name);
        return add;
      },
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); }
    },
    addEventListener(type, callback) { listeners[type] = callback; },
    setAttribute(name, value) { this.attrs[name] = String(value); }
  }, opts);
}
const label = node({textContent:"Mở"});
const toggle = node({attrs:{"aria-expanded":"false"},querySelector(sel) {
  return sel === ".quiz-create-toggle-label" ? label : null;
}});
const body = node({hidden:true});
const picker = node({dataset:{quizTarget:"quiz-work-1"}});
const tabs = ["subject", "document", "weakness"].map(name=>node({dataset:{createMode:name}}));
const panels = ["subject", "document", "weakness"].map(name=>node({dataset:{createPanel:name}}));
const selected = node({value:"20"});
const hub = node({
  dataset:{initialMode:"document"},
  querySelectorAll(sel) {
    return sel === "[data-create-mode]" ? tabs :
      sel === "[data-create-panel]" ? panels : [];
  }
});
panels[1].querySelector = ()=>selected;
const els = {quizCreateModes:hub,quizCreateToggle:toggle,quizCreateBody:body};
const document = {
  body: {classList:node().classList},
  events:{},
  getElementById(id) {return els[id] || null;},
  querySelectorAll(sel) {
    if (sel === ".quiz-picker") return [picker];
    return [];
  },
  addEventListener(event, callback) {this.events[event]=callback;}
};
const window={};
vm.runInNewContext(fs.readFileSync("static/js/quiz.js","utf8"),
                   {document,window,console,Date,Math,setTimeout}, {filename:"quiz.js"});
document.events.DOMContentLoaded();
assert.strictEqual(panels[1].hidden, false);
assert.strictEqual(panels[0].hidden,true);
toggle.listeners.click();
assert.strictEqual(body.hidden, false);
assert.strictEqual(toggle.attrs["aria-expanded"], "true");
assert.strictEqual(label.textContent,"Thu gọn");
toggle.listeners.click();
assert.strictEqual(body.hidden,true);
assert.strictEqual(selected.value,"20","Collapsing must not reset form selection");
toggle.listeners.click();
picker.listeners.click();
assert.strictEqual(body.hidden,true,"Selecting quiz should collapse creator");
assert.strictEqual(label.textContent,"Mở");
console.log("Quiz layout UI PASS: mode selection, collapse, auto-collapse on quiz, form values retained");
