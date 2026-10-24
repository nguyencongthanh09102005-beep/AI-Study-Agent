"use strict";
const assert = require("node:assert/strict");
const { setupPasswordToggles } = require("../static/js/auth-password.js");

function makeButton(target, label) {
  const attrs = { "data-target": target, "data-label": label, "aria-pressed": "false" };
  const listeners = {};
  const classes = new Set();
  return {
    dataset: {},
    listeners,
    getAttribute: (name) => attrs[name] || null,
    setAttribute: (name, value) => { attrs[name] = String(value); },
    classList: {
      toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
      contains: (name) => classes.has(name),
    },
    click: () => { assert.ok(listeners.click); listeners.click(); },
    addEventListener: (name, fn) => {
      assert.equal(listeners[name], undefined, "Button must bind only once");
      listeners[name] = fn;
    },
  };
}

const targets = {
  loginPassword: { type: "password", value: "hello-login" },
  signupPassword: { type: "password", value: "hello-signup" },
  confirmPassword: { type: "password", value: "hello-confirm" },
};
const buttons = [
  makeButton("loginPassword", "mật khẩu"),
  makeButton("signupPassword", "mật khẩu"),
  makeButton("confirmPassword", "mật khẩu xác nhận"),
  makeButton("absentPassword", "mật khẩu"),
];
const fakeDocument = {
  querySelectorAll: (selector) => {
    assert.equal(selector, ".auth-password-field .password-toggle");
    return buttons;
  },
  getElementById: (id) => targets[id] || null,
};
setupPasswordToggles(fakeDocument);
setupPasswordToggles(fakeDocument);
assert.equal(buttons[3].listeners.click, undefined, "Missing input ignored");

for (let i = 0; i < 3; i++) {
  const button = buttons[i];
  const target = targets[button.getAttribute("data-target")];
  const original = target.value;

  button.click();
  assert.equal(target.type, "text");
  assert.equal(target.value, original, "Must not edit typed password");
  assert.equal(button.getAttribute("aria-pressed"), "true");
  assert.equal(button.classList.contains("is-visible"), true);
  assert.equal(button.getAttribute("aria-label"), "Ẩn " + button.getAttribute("data-label"));

  button.click();
  assert.equal(target.type, "password");
  assert.equal(target.value, original);
  assert.equal(button.getAttribute("aria-pressed"), "false");
  assert.equal(button.classList.contains("is-visible"), false);
  assert.equal(button.getAttribute("aria-label"), "Hiện " + button.getAttribute("data-label"));
}
assert.deepEqual(Object.values(targets).map((input) => input.type), ["password", "password", "password"]);
console.log("Auth password eye toggle tests passed (login, signup and confirm)");
