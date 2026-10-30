/* Regression for desktop floating-chat sizing; no live API or DOM packages. */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "static/js/ai_bubble.js"), "utf8");
const css = fs.readFileSync(path.join(root, "static/css/ai_bubble.css"), "utf8");
const html = fs.readFileSync(path.join(root, "templates/base.html"), "utf8");
for (const name of ["floatingAiExpand", "floatingAiResetSize", "floatingAiResize"]) {
  assert.match(html, new RegExp('id="' + name + '"'));
}
assert.match(css, /\.chat-table-scroll\{[^}]*overflow-x:auto/);
assert.match(css, /width:max\(100%,640px\)/);
assert.match(css, /@media\(max-width:600px\)[\s\S]*floating-ai-resize-handle/);
assert.match(html, /aria-label="Đổi kích thước Chat AI/);

const state = new Map();
function storage() {
  return {
    getItem(key) { return state.get(key) ?? null; },
    setItem(key, value) { state.set(key, String(value)); }
  };
}
function fixture(width=1600, height=900) {
  const elements = new Map();
  function element(name) {
    const listeners = {};
    const attributes = {};
    const style = {
      width: "", height: "",
      removeProperty(name) { this[name] = ""; }
    };
    const node = {
      id: name, listeners, attributes, style, dataset: {}, hidden: true,
      classList: {toggle() {}},
      offsetWidth: 62, offsetHeight: 62, disabled: false,
      addEventListener(event, callback) { (listeners[event] ||= []).push(callback); },
      setAttribute(name, value) { attributes[name] = value; },
      getBoundingClientRect() {
        return {width: Number.parseFloat(style.width) || 420,
                height: Number.parseFloat(style.height) || 640};
      },
      setPointerCapture() {}, hasPointerCapture() { return false; },
      focus() {}, querySelectorAll() { return []; },
    };
    elements.set(name, node);
    return node;
  }
  for (const id of [
    "floatingAiRoot", "floatingAiBubble", "floatingAiPanel", "floatingAiClose",
    "floatingAiExpand", "floatingAiResetSize", "floatingAiResize",
    "floatingAiResizeHorizontal", "floatingAiResizeVertical",
    "floatingAiTabStudy", "floatingAiTabSupport",
    "floatingAiStudyView", "floatingAiSupportView", "floatingAiSupportResults",
    "floatingAiScheduleButton",
    "floatingAiScope", "floatingAiMode", "floatingAiCourseLabel",
    "floatingAiCourse", "floatingAiMessages", "floatingAiForm",
    "floatingAiInput", "floatingAiSend", "floatingAiStatus",
    "floatingAiFullChat"
  ]) element(id);
  elements.get("floatingAiRoot").dataset.side = "right";
  const documentListeners = {};
  const document = {
    getElementById(name) { return elements.get(name) || null; },
    querySelectorAll() { return []; },
    addEventListener(event, callback) { (documentListeners[event] ||= []).push(callback); }
  };
  const windowListeners = {};
  const win = {
    innerWidth: width, innerHeight: height,
    addEventListener(event, callback) { (windowListeners[event] ||= []).push(callback); },
    requestAnimationFrame() {},
  };
  const sandbox = {
    document, window: win, innerWidth: width, innerHeight: height,
    innerHeight: height, innerWidth: width,
    localStorage: storage(), sessionStorage: {
      getItem(key) { return state.get("session:"+key) ?? null; },
      setItem(key, value) { state.set("session:"+key, String(value)); }
    },
    location: {pathname: "/", search: ""},
    URLSearchParams,
    fetch() { throw Error("Resize test must not call the network"); },
    console
  };
  vm.runInNewContext(source, sandbox, {filename: "ai_bubble.js"});
  documentListeners.DOMContentLoaded[0]();

  function emit(id, event, payload={}) {
    for (const handler of (elements.get(id).listeners[event] || [])) {
      handler({preventDefault() {}, ...payload});
    }
  }
  function screenResize(w, h) {
    win.innerWidth = w; win.innerHeight = h;
    sandbox.innerWidth = w; sandbox.innerHeight = h;
    for (const callback of windowListeners.resize) callback();
  }
  return {elements, emit, screenResize, win};
}

state.clear();
let test = fixture();
const panel = test.elements.get("floatingAiPanel");
const expand = test.elements.get("floatingAiExpand");
const handle = test.elements.get("floatingAiResize");
assert.equal(panel.style.width, "420px");
assert.equal(panel.style.height, "640px");
test.emit("floatingAiResize", "pointerdown",
  {button:0,pointerId:1,clientX:400,clientY:750});
test.emit("floatingAiResize", "pointermove",
  {pointerId:1,clientX:180,clientY:670});
test.emit("floatingAiResize", "pointerup", {pointerId:1});
assert.equal(panel.style.width, "640px", "Dragging toward left widens right-anchored popup");
assert.equal(panel.style.height, "720px", "Dragging upward increases popup height");
assert.equal(JSON.parse(state.get("ai-study-floating-size-v1")).width, 640);
assert.equal(handle.attributes["aria-label"], undefined, "ARIA markup is server-owned");

// Saved dimensions survive navigation/re-render.
test = fixture();
const restored = test.elements.get("floatingAiPanel");
assert.equal(restored.style.width, "640px");
assert.equal(restored.style.height, "720px");
test.emit("floatingAiExpand", "click");
assert.equal(restored.style.width, "1100px");
assert.equal(restored.style.height, "868px");
assert.equal(test.elements.get("floatingAiExpand").attributes["aria-pressed"], "true");
test.emit("floatingAiExpand", "click");
assert.equal(restored.style.width, "640px");
assert.equal(restored.style.height, "720px");
test.emit("floatingAiResize", "keydown", {key:"ArrowRight"});
assert.equal(restored.style.width, "664px");
test.emit("floatingAiResize", "keydown", {key:"ArrowUp",shiftKey:true});
assert.equal(restored.style.height, "784px");
test.emit("floatingAiResetSize", "click");
assert.equal(restored.style.width, "420px");
assert.equal(restored.style.height, "640px");

// Viewport bounds are applied to the displayed window without destroying the
// stored custom desktop preference; fullscreen CSS owns the mobile size.
test.screenResize(700, 480);
assert.equal(restored.style.width, "420px");
assert.equal(restored.style.height, "448px");
test.screenResize(390, 740);
assert.equal(restored.style.width, "");
assert.equal(restored.style.height, "");
test.screenResize(1600, 900);
assert.equal(restored.style.width, "420px");
assert.equal(restored.style.height, "640px");

// A left-docked floating button should reverse horizontal drag direction.
state.clear();
test = fixture();
const left = test.elements.get("floatingAiPanel");
test.elements.get("floatingAiRoot").dataset.side = "left";
test.emit("floatingAiResize", "pointerdown",
  {button:0,pointerId:3,clientX:400,clientY:750});
test.emit("floatingAiResize", "pointermove",
  {pointerId:3,clientX:530,clientY:750});
test.emit("floatingAiResize", "pointerup", {pointerId:3});
assert.equal(left.style.width, "550px");



// Separate Học tập/Hỗ trợ views must keep the same user-sized window.
state.clear();
test = fixture();
const twoTabsPanel = test.elements.get("floatingAiPanel");
const learn = test.elements.get("floatingAiStudyView");
const help = test.elements.get("floatingAiSupportView");
assert.equal(learn.hidden,false);
assert.equal(help.hidden,true);
test.emit("floatingAiTabSupport","click");
assert.equal(learn.hidden,true);
assert.equal(help.hidden,false);
assert.equal(test.elements.get("floatingAiTabSupport").attributes["aria-selected"],"true");
test.emit("floatingAiResizeHorizontal","pointerdown",
  {button:0,pointerId:7,clientX:400,clientY:420});
test.emit("floatingAiResizeHorizontal","pointermove",
  {pointerId:7,clientX:280,clientY:390});
test.emit("floatingAiResizeHorizontal","pointerup",{pointerId:7});
assert.equal(twoTabsPanel.style.width,"540px");
assert.equal(twoTabsPanel.style.height,"640px",
  "Dragging a side must not change the other axis");
test.emit("floatingAiResizeVertical","pointerdown",
  {button:0,pointerId:8,clientX:520,clientY:100});
test.emit("floatingAiResizeVertical","pointermove",
  {pointerId:8,clientX:520,clientY:40});
test.emit("floatingAiResizeVertical","pointerup",{pointerId:8});
assert.equal(twoTabsPanel.style.width,"540px");
assert.equal(twoTabsPanel.style.height,"700px");
test.emit("floatingAiTabStudy","click");
assert.equal(learn.hidden,false);
assert.equal(help.hidden,true);
assert.equal(twoTabsPanel.style.width,"540px");
assert.equal(twoTabsPanel.style.height,"700px");
test.emit("floatingAiTabSupport","click");
test = fixture();
assert.equal(test.elements.get("floatingAiSupportView").hidden,false,
  "Support tab choice is stored in the session");
assert.equal(test.elements.get("floatingAiPanel").style.width,"540px",
  "Custom width survives navigation");
assert.equal(test.elements.get("floatingAiPanel").style.height,"700px",
  "Custom height survives navigation");

console.log("Floating chat: resize mouse, keyboard, expand/reset, save, viewport/mobile bounds and left/right docking PASS");
