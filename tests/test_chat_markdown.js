"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("static/js/chat_format.js", "utf8");
vm.runInThisContext(source);
const render = globalThis.ChatMarkdown.render;

const bold = render("Đây là **danh sách liên kết** và *node*.");
assert.match(bold, /<strong>danh sách liên kết<\/strong>/);
assert.match(bold, /<em>node<\/em>/);
assert.doesNotMatch(bold, /\*\*danh sách/);
assert.match(render("**Quan trọng**"), /<strong>Quan trọng<\/strong>/);

const injected = render('**<img src=x onerror="alert(1)">**');
assert.doesNotMatch(injected, /<img\b/);
assert.match(injected, /&lt;img src=x/);
assert.match(injected, /<strong>/);

const ticks = String.fromCharCode(96);
const literalCode = render("Thử " + ticks + "**đừng định dạng**" + ticks);
assert.match(literalCode, /<code>\*\*đừng định dạng\*\*<\/code>/);
assert.doesNotMatch(literalCode, /<strong>đừng định dạng<\/strong>/);

const codeBlock = render(ticks.repeat(3) + "js\nconst a = '<script>';\n" +
  ticks.repeat(3));
assert.match(codeBlock, /<pre><code>/);
assert.match(codeBlock, /&lt;script&gt;/);
assert.doesNotMatch(codeBlock, /<script>/);

const list = render("- **Mảng**\n- Danh sách\n\n1. Thứ nhất\n2. Thứ hai");
assert.match(list, /<ul>/);
assert.match(list, /<ol>/);
assert.match(list, /<strong>Mảng<\/strong>/);

const preexisting = render("# Chương 2\n\n**Mục tiêu:** Hiểu node và next.");
assert.match(preexisting, /<h4>Chương 2<\/h4>/);
assert.match(preexisting, /<strong>Mục tiêu:<\/strong>/);

console.log("Chat Markdown: safe bold, code, lists, headings and escaped HTML OK");
