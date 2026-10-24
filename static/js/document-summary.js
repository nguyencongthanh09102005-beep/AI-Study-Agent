// Trình bày Markdown cơ bản từ Gemini mà không phụ thuộc CDN/thư viện ngoài.
// Quan trọng: luôn escape HTML của nội dung AI trước khi thêm thẻ trình bày.
(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (char) {
      return {
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"
      }[char];
    });
  }

  function inlineMarkdown(value) {
    var safe = escapeHtml(value);
    safe = safe.replace(/\x60([^\x60\n]+)\x60/g, "<code>$1</code>");
    safe = safe.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
    safe = safe.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    return safe;
  }

  function renderStudyMarkdown(source) {
    var lines = String(source == null ? "" : source).replace(/\r\n?/g, "\n").split("\n");
    var result = [];
    var paragraph = [];
    var activeList = null;
    var codeLines = [];
    var inCode = false;

    function flushParagraph() {
      if (paragraph.length) {
        result.push("<p>" + paragraph.map(inlineMarkdown).join(" ") + "</p>");
        paragraph = [];
      }
    }
    function closeList() {
      if (activeList) {
        result.push("</" + activeList + ">");
        activeList = null;
      }
    }
    function beginList(type) {
      flushParagraph();
      if (activeList !== type) {
        closeList();
        result.push("<" + type + ">");
        activeList = type;
      }
    }
    function flushCode() {
      result.push("<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>");
      codeLines = [];
    }

    lines.forEach(function (line) {
      var trimmed = line.trim();

      if (/^\x60{3,}/.test(trimmed)) {
        if (inCode) {
          flushCode();
          inCode = false;
        } else {
          flushParagraph();
          closeList();
          inCode = true;
        }
        return;
      }
      if (inCode) {
        codeLines.push(line);
        return;
      }
      if (!trimmed) {
        flushParagraph();
        closeList();
        return;
      }
      if (/^(?:-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
        flushParagraph();
        closeList();
        result.push("<hr>");
        return;
      }
      var heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        closeList();
        // Tiêu đề tài liệu đã là h2, nên nội dung bắt đầu từ h3.
        var level = Math.min(6, Math.max(3, heading[1].length));
        result.push("<h" + level + ">" + inlineMarkdown(heading[2]) + "</h" + level + ">");
        return;
      }
      var unordered = line.match(/^\s*[-*+•]\s+(.+)$/);
      if (unordered) {
        beginList("ul");
        result.push("<li>" + inlineMarkdown(unordered[1]) + "</li>");
        return;
      }
      var ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (ordered) {
        beginList("ol");
        result.push("<li>" + inlineMarkdown(ordered[1]) + "</li>");
        return;
      }
      closeList();
      paragraph.push(trimmed);
    });

    if (inCode) flushCode();
    flushParagraph();
    closeList();
    return result.join("\n");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { renderStudyMarkdown: renderStudyMarkdown };
  }

  if (typeof document !== "undefined") {
    var mount = function () {
      var summaryElement = document.getElementById("documentSummary");
      if (!summaryElement) return;
      var originalContent = summaryElement.textContent || "";
      summaryElement.innerHTML = renderStudyMarkdown(originalContent);
      summaryElement.classList.add("is-rendered");
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", mount);
    } else {
      mount();
    }
  }
})();
