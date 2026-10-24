"use strict";
const assert = require("node:assert/strict");
const { renderStudyMarkdown } = require("../static/js/document-summary.js");

const sample = [
  "Dưới đây là tóm tắt tài liệu **Bài 2: Lỗ hổng bảo mật**.",
  "",
  "---",
  "",
  "### Ý CHÍNH",
  "* Tài liệu trình bày **tấn công mạng**.",
  "* Phân loại các hình thức tấn công.",
  "",
  "### KHÁI NIỆM QUAN TRỌNG",
  "* **Hệ thống thông tin:** tập hợp các thành phần.",
  "1. Nhận diện",
  "2. Phòng ngừa",
  "",
  "Nội dung *cần nhớ*."
].join("\n");

const actual = renderStudyMarkdown(sample);
assert.match(actual, /<h3>Ý CHÍNH<\/h3>/);
assert.match(actual, /<h3>KHÁI NIỆM QUAN TRỌNG<\/h3>/);
assert.match(actual, /<strong>Bài 2: Lỗ hổng bảo mật<\/strong>/);
assert.match(actual, /<ul>\s*<li>Tài liệu trình bày <strong>tấn công mạng<\/strong>\.<\/li>/);
assert.match(actual, /<li><strong>Hệ thống thông tin:<\/strong>/);
assert.match(actual, /<ol>\s*<li>Nhận diện<\/li>/);
assert.match(actual, /<em>cần nhớ<\/em>/);
assert.match(actual, /<hr>/);
assert.ok(!actual.includes("### "));
assert.ok(!actual.includes("**"));

const plain = renderStudyMarkdown("Tóm tắt bình thường.\nDòng nội dung tiếp theo.");
assert.match(plain, /<p>Tóm tắt bình thường\. Dòng nội dung tiếp theo\.<\/p>/);

// Text từ Gemini/tệp PDF không được phép biến thành HTML/script thực thi.
const attack = renderStudyMarkdown(
  '### <img src=x onerror=alert(1)>\n' +
  '* **<script>alert(1)</script>**\n' +
  'Dòng chứa "quote" & dấu <b>HTML</b>.\n' +
  '\x60<script>evil()</script>\x60'
);
assert.ok(attack.includes("&lt;img src=x onerror=alert(1)&gt;"));
assert.ok(attack.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
assert.ok(!attack.includes("<script>"));
assert.ok(!attack.includes("<img "));
assert.ok(!attack.includes("<b>HTML</b>"));
assert.match(attack, /&amp;/);
assert.match(attack, /<code>&lt;script&gt;evil\(\)&lt;\/script&gt;<\/code>/);

const fence = renderStudyMarkdown("Dữ liệu:\n\x60\x60\x60python\nprint('<script>')\n\x60\x60\x60");
assert.match(fence, /<pre><code>print\('&lt;script&gt;'\)<\/code><\/pre>/);
assert.equal(renderStudyMarkdown(""), "");

console.log("Markdown document-summary rendering and XSS regression tests passed");
