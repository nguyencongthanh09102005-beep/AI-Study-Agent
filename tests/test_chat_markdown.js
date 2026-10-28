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
assert.match(codeBlock, /chat-code-title/);
assert.match(codeBlock, />js<\/div>/);
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

const table = render("| Cấu trúc | Truy cập | Chèn giữa |\n| --- | --- | --- |\n| **Mảng** | O(1) | O(n) |\n| Linked list | O(n) | O(1)* |");
assert.match(table, /<table class="chat-data-table">/);
assert.match(table, /<th>Cấu trúc<\/th>/);
assert.match(table, /<td><strong>Mảng<\/strong><\/td>/);
assert.match(table, /<td>O\(1\)<\/td>/);
assert.doesNotMatch(table, /\|\s*---\s*\|/);

const safeTable = render("| Nội dung | Kiểm thử |\n| --- | --- |\n| <svg onload=alert(1)> | \`a|b\` |");
assert.doesNotMatch(safeTable, /<svg\b/);
assert.match(safeTable, /&lt;svg onload/);
assert.match(safeTable, /<code>a\|b<\/code>/);

const nonTable = render("Mảng | Danh sách\nTruy cập | Thao tác");
assert.doesNotMatch(nonTable, /<table\b/);

const mathInline = render("Độ phức tạp $O(n^2)$ và chỉ số \\(a_i\\).");
assert.match(mathInline, /<sup>2<\/sup>/);
assert.match(mathInline, /<sub>i<\/sub>/);
const mathBlock = render("$\n\\frac{1}{n}\n$");
assert.match(mathBlock, /chat-math-block/);
assert.match(mathBlock, /chat-math-fraction/);
const mathUnsafe = render("$\\frac{<img>}{2}$");
assert.doesNotMatch(mathUnsafe, /<img>/);
assert.match(mathUnsafe, /&lt;img&gt;/);

// Regression for the exact Markdown/LaTeX symptoms users reported.
const escapedBold = render("AI nói \\*\\*Danh sách liên kết\\*\\* là cấu trúc...");
assert.match(escapedBold, /<strong>Danh sách liên kết<\/strong>/);
assert.doesNotMatch(escapedBold, /\\\*\*/);
const mathText = render("Biểu diễn: $\\text{head} \\rightarrow [5|\\text{next}]$.");
assert.match(mathText, /chat-math-text/);
assert.match(mathText, /head/);
assert.match(mathText, /→/);
assert.doesNotMatch(mathText, /\\text/);
const comparison = render("| Cấu trúc | Độ phức tạp |\n| --- | --- |\n| **Mảng** | $O(1)$ |");
assert.match(comparison, /<table class="chat-data-table">/);
assert.match(comparison, /<strong>Mảng<\/strong>/);
assert.match(comparison, /chat-formula-fallback/);
assert.doesNotMatch(comparison, /<img\b/);
const blockTex = render("$\n\\frac{1}{n}\n$");
assert.match(blockTex, /chat-math-fraction/);
assert.doesNotMatch(blockTex, /\\frac/);
const adversarialMath = render("$\\text{<img src=x onerror=alert(1)>}$");
assert.doesNotMatch(adversarialMath, /<img\b/);
assert.match(adversarialMath, /&lt;img/);

console.log("Chat output: responsive tables, safe math, code, lists, HTML escaping OK");
