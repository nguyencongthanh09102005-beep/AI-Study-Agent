"use strict";
// Do not restore an extracted-text screen in place of original file previews.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const app = fs.readFileSync("mobile/App.js", "utf8");
const api = fs.readFileSync("mobile/src/api.js", "utf8");
const viewer = fs.readFileSync("mobile/src/originalDocumentPreview.js", "utf8");
const server = fs.readFileSync("app.py", "utf8");

assert(app.includes("api.personalDocumentFile(doc.id)"));
assert(app.includes("api.sharedDocumentFile(doc.id)"));
assert(app.includes("await openOriginalDocument(payload,"));
assert(app.includes("↗ Mở file gốc"));
assert(app.includes("✦ Tóm tắt AI"));
assert(app.includes("mode === 'summary'"));
assert(!app.includes("Văn bản đã trích xuất"));
assert(!app.includes("Nội dung trích xuất"));
assert(!app.includes("mode === 'shared-preview'"));
assert(!app.includes("mode === 'preview'"));
assert(api.includes("/api/mobile/documents/${id}/file"));
assert(api.includes("/api/mobile/shared-documents/${id}/file"));
assert(viewer.includes("await file.write(payload.base64"));
assert(viewer.includes("await file.preview({title:name, mimeType:payload.type})"));
assert(viewer.includes("Sharing.shareAsync(file.uri"));
assert(server.includes('def api_mobile_personal_document_file(doc_id):'));
assert(server.includes('def api_mobile_shared_document_file(doc_id):'));
assert(server.includes('def _mobile_original_file_payload(stored_name, original_name):'));
console.log("Mobile source preview UI PASS: native viewer, summary retained, no text dump");
