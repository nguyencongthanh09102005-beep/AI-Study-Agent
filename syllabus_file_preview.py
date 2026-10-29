"""Safe, self-hosted DOCX text/table preview; never contacts Office/Google cloud.

PDF files use the browser's built-in viewer. DOCX is a faithful-enough
reading preview for basic paragraphs, tables and character formatting, not
a pixel-identical Word page: complex layouts and images stay in the original.
"""
from html import escape
from pathlib import Path
import base64
import zipfile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


def _safe_docx(path):
    # Reject compressed documents with excessive uncompressed payload.
    with zipfile.ZipFile(str(path)) as archive:
        members = archive.infolist()
        if len(members) > 3000 or sum(m.file_size for m in members) > 150 * 1024 * 1024:
            raise ValueError("DOCX contains too much uncompressed content")
    return Document(str(path))


def extract_docx_text(path, max_chars=100000):
    doc = _safe_docx(path)
    chunks = []
    total = 0
    for child in doc.element.body.iterchildren():
        if total >= max_chars:
            break
        if child.tag == qn("w:p"):
            part = Paragraph(child, doc).text.strip()
        elif child.tag == qn("w:tbl"):
            tbl = Table(child, doc)
            part = "\n".join(" | ".join(cell.text.strip() for cell in row.cells)
                             for row in tbl.rows[:200])
        else:
            continue
        if part:
            chunks.append(part[:max_chars - total])
            total += min(len(part), max_chars - total) + 1
    return "\n".join(chunks)[:max_chars]


def _paragraph_html(paragraph, doc_part, image_budget):
    heading = str(paragraph.style.name or "").lower()
    tag = "h2" if "heading 1" in heading or "title" == heading else (
        "h3" if "heading 2" in heading else "p"
    )
    spans = []
    for run in paragraph.runs:
        content = escape(run.text)
        if content:
            if run.bold:
                content = "<strong>" + content + "</strong>"
            if run.italic:
                content = "<em>" + content + "</em>"
            if run.underline:
                content = "<u>" + content + "</u>"
            spans.append(content)
        for blip in run._r.xpath(".//a:blip"):
            relation_id = blip.get(qn("r:embed"))
            part = doc_part.related_parts.get(relation_id) if relation_id else None
            mime = part.content_type if part is not None else ""
            blob = part.blob if part is not None else b""
            if (mime in ("image/png", "image/jpeg", "image/gif", "image/webp")
                    and 0 < len(blob) <= 2 * 1024 * 1024
                    and image_budget[0] >= len(blob)):
                image_budget[0] -= len(blob)
                encoded = base64.b64encode(blob).decode("ascii")
                spans.append("<img alt='Hình trong tài liệu' src='data:" +
                             mime + ";base64," + encoded + "'>")
    body = "".join(spans) or escape(paragraph.text)
    return f"<{tag}>{body}</{tag}>" if body.strip() else ""


def render_docx_preview(path: Path, name: str):
    doc = _safe_docx(path)
    nodes = []
    image_budget = [8 * 1024 * 1024]
    for child in list(doc.element.body.iterchildren())[:500]:
        if child.tag == qn("w:p"):
            markup = _paragraph_html(Paragraph(child, doc), doc.part, image_budget)
            if markup:
                nodes.append(markup)
        elif child.tag == qn("w:tbl"):
            tbl = Table(child, doc)
            rows = []
            for row in tbl.rows[:150]:
                cells = "".join("<td>" + escape(cell.text) + "</td>"
                                for cell in row.cells[:20])
                rows.append("<tr>" + cells + "</tr>")
            nodes.append("<div class='table-wrap'><table>" + "".join(rows) +
                         "</table></div>")
    title = escape(name)
    body = "\n".join(nodes) or "<p>Tệp này không chứa văn bản có thể hiển thị.</p>"
    return ("""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + title + """</title><style>
*{box-sizing:border-box}body{margin:0;background:#e9edf5;color:#22365f;
font:15px/1.65 Arial,sans-serif;padding:18px}main{background:white;
margin:auto;max-width:820px;padding:clamp(20px,5vw,60px);min-height:650px;
box-shadow:0 5px 25px #9aa6c14d}h1,h2,h3{color:#1a2b51;line-height:1.35}
p{margin:0 0 12px;white-space:pre-wrap;overflow-wrap:anywhere}
.table-wrap{overflow:auto;max-width:100%;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:14px}img{max-width:100%;height:auto;display:block;margin:12px 0}
td{border:1px solid #94a2b9;padding:8px 10px;white-space:pre-wrap;
vertical-align:top;overflow-wrap:anywhere}
.notice{max-width:820px;margin:0 auto 12px;color:#415779;font-size:13px}
@media(max-width:600px){body{padding:8px}main{padding:18px}}
</style></head><body><div class="notice">Bản xem trước Word: chữ, bảng và ảnh thông dụng được hiển thị để đọc.
Font đặc biệt, biểu đồ và ngắt trang phức tạp có thể khác file gốc;
tải file gốc để xem chính xác.</div>
<main><h1>""" + title + """</h1>""" + body +
            "</main></body></html>")


def preview_mime(path):
    return path.suffix.lower() in (".pdf", ".docx")
