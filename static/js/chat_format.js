/* Safely render Markdown returned by AI, without injecting raw HTML. */
(function (global) {
  "use strict";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function inline(value) {
    const codeTokens = [];
    let safe = escapeHtml(value);
    safe = safe.replace(/`([^`\n]+)`/g, (_match, code) => {
      const marker = "\uE000" + codeTokens.length + "\uE001";
      codeTokens.push("<code>" + code + "</code>");
      return marker;
    });
    safe = safe.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
               .replace(/__([^_\n]+?)__/g, "<strong>$1</strong>")
               .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
    return safe.replace(/\uE000(\d+)\uE001/g, (_match, i) => codeTokens[Number(i)]);
  }

  function tableRow(value) {
    let line = String(value).trim();
    if (!line.includes("|")) return null;
    if (line.startsWith("|")) line = line.slice(1);
    if (line.endsWith("|") && !line.endsWith("\\|")) line = line.slice(0, -1);
    const cells = [];
    let cell = "", isCode = false;
    for (let i = 0; i < line.length; i += 1) {
      if (line[i] === "\\" && line[i + 1] === "|") {
        cell += "|"; i += 1;
      } else if (line[i] === "`") {
        isCode = !isCode; cell += line[i];
      } else if (line[i] === "|" && !isCode) {
        cells.push(cell.trim()); cell = "";
      } else cell += line[i];
    }
    cells.push(cell.trim());
    return cells;
  }

  function tableBlock(lines, start) {
    const header = tableRow(lines[start]);
    const rule = tableRow(lines[start + 1] || "");
    if (!header || !rule || header.length < 2 ||
        header.length !== rule.length || header.length > 12 ||
        !rule.every(c => /^:?-{3,}:?$/.test(c.replace(/\s/g, "")))) return null;
    let index = start + 2;
    let html = '<div class="chat-table-scroll" role="region" tabindex="0" aria-label="Bảng trả lời của AI">' +
      '<table class="chat-data-table"><thead><tr>' +
      header.map(c => "<th>" + inline(c) + "</th>").join("") +
      "</tr></thead><tbody>";
    for (; index < lines.length && index < start + 85; index += 1) {
      if (!lines[index].trim() || !lines[index].includes("|")) break;
      const cells = tableRow(lines[index]);
      if (!cells || cells.length < 2) break;
      html += "<tr>" + header.map((_c, n) =>
        "<td>" + inline(cells[n] || "") + "</td>").join("") + "</tr>";
    }
    return { html: html + "</tbody></table></div>", next: index };
  }

  function prose(value) {
    const out = [];
    let list = "";
    let paragraph = [];
    const flush = () => {
      if (!paragraph.length) return;
      out.push("<p>" + paragraph.map(inline).join("<br>") + "</p>");
      paragraph = [];
    };
    const closeList = () => {
      if (list) out.push("</" + list + ">");
      list = "";
    };
    for (const row of String(value || "").split("\n")) {
      const text = row.trim();
      if (!text) { flush(); closeList(); continue; }
      const title = text.match(/^#{1,4}\s+(.+)$/);
      if (title) {
        flush(); closeList();
        out.push("<h4>" + inline(title[1]) + "</h4>");
        continue;
      }
      const bullet = text.match(/^[-*•]\s+(.+)$/);
      const ordinal = text.match(/^\d+[.)]\s+(.+)$/);
      if (bullet || ordinal) {
        flush();
        const tag = ordinal ? "ol" : "ul";
        if (list !== tag) {
          closeList(); out.push("<" + tag + ">"); list = tag;
        }
        out.push("<li>" + inline((bullet || ordinal)[1]) + "</li>");
        continue;
      }
      closeList();
      paragraph.push(row);
    }
    flush();
    closeList();
    return out.join("");
  }

  function renderMarkdown(raw) {
    const value = String(raw == null ? "" : raw).replace(/\r\n?/g, "\n");
    const sections = value.split(/(^```[^\n]*\n[\s\S]*?^```\s*$)/gm);
    return sections.map(part => {
      const code = part.match(/^```[^\n]*\n([\s\S]*?)^```\s*$/m);
      if (code) {
        return "<pre><code>" + escapeHtml(code[1]).replace(/\n$/, "") + "</code></pre>";
      }
      return prose(part);
    }).join("");
  }

  global.ChatMarkdown = { render: renderMarkdown };
})(typeof window !== "undefined" ? window : globalThis);
