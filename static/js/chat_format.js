/* Safely render Markdown returned by AI, without injecting raw HTML. */
(function (global) {
  "use strict";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function mathHtml(expression, display) {
    const tex = String(expression || "").trim();
    if (!tex || tex.length > 2000) return escapeHtml(expression);
    if (global.katex && typeof global.katex.renderToString === "function") {
      try {
        return '<span class="chat-formula">' +
          global.katex.renderToString(tex, {
            displayMode: !!display, throwOnError: false, trust: false,
            strict: "ignore", maxExpand: 400, maxSize: 8
          }) + "</span>";
      } catch (_error) {
        // Keep the source expression visible when a symbol is unsupported.
      }
    }
    // Lightweight local fallback: support common math even without KaTeX.
    // Everything is escaped before adding our own fixed safe markup.
    let content = escapeHtml(tex);
    content = content.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g,
      (_m, top, bottom) => '<span class="chat-math-fraction"><span>' +
        top + '</span><span>' + bottom + '</span></span>');
    content = content.replace(/\\sqrt\{([^{}]+)\}/g,
      (_m, inner) => '√<span class="chat-math-root">' + inner + '</span>');
    const symbols = {
      alpha: "α", beta: "β", gamma: "γ", delta: "δ", theta: "θ",
      lambda: "λ", pi: "π", sigma: "σ", sum: "∑", prod: "∏",
      infty: "∞", times: "×", cdot: "·", leq: "≤", geq: "≥",
      neq: "≠", approx: "≈", rightarrow: "→", to: "→", in: "∈"
    };
    content = content.replace(/\\([A-Za-z]+)\b/g, (_m, name) =>
      symbols[name] || "\\" + name);
    content = content.replace(/\^\{([^{}]{1,32})\}/g, "<sup>$1</sup>")
      .replace(/\^([a-zA-Z0-9+-])/g, "<sup>$1</sup>")
      .replace(/_\{([^{}]{1,32})\}/g, "<sub>$1</sub>")
      .replace(/_([a-zA-Z0-9])/g, "<sub>$1</sub>");
    return '<span class="chat-formula-fallback">' + content + "</span>";
  }

  function inline(value) {
    const tokens = [];
    let raw = String(value == null ? "" : value)
      .replace(/[\uE000\uE001]/g, "");
    const reserve = html => "\uE000" + (tokens.push(html) - 1) + "\uE001";
    raw = raw.replace(/`([^`\n]+)`/g,
      (_m, code) => reserve("<code>" + escapeHtml(code) + "</code>"));
    raw = raw.replace(/\\\((.+?)\\\)|(?<!\\)\$([^$\n]+)\$/g,
      (_m, paren, dollar) => reserve(mathHtml(paren === undefined ? dollar : paren, false)));
    let safe = escapeHtml(raw);
    safe = safe.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
      .replace(/__([^_\n]+?)__/g, "<strong>$1</strong>")
      .replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "<em>$1</em>");
    return safe.replace(/\uE000(\d+)\uE001/g, (_m, i) => tokens[Number(i)] || "");
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
    const lines = String(value || "").split("\n");
    for (let index = 0; index < lines.length; index += 1) {
      const row = lines[index];
      const trimmed = row.trim();
      if (trimmed === "$" || trimmed === "\\[") {
        flush(); closeList();
        const close = trimmed === "$" ? "$" : "\\]";
        const mathLines = [];
        index += 1;
        while (index < lines.length && lines[index].trim() !== close) {
          mathLines.push(lines[index]); index += 1;
        }
        out.push('<div class="chat-math-block">' +
          mathHtml(mathLines.join("\n"), true) + "</div>");
        continue;
      }
      const sameLine = trimmed.match(/^\$\$(.+)\$\$/) ||
        trimmed.match(/^\\\[(.+)\\\]$/);
      if (sameLine) {
        flush(); closeList();
        out.push('<div class="chat-math-block">' + mathHtml(sameLine[1], true) + "</div>");
        continue;
      }
      const table = tableBlock(lines, index);
      if (table) {
        flush(); closeList(); out.push(table.html);
        index = table.next - 1;
        continue;
      }
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
