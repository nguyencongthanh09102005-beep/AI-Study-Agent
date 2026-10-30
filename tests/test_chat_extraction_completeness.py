"""Extraction regression: no silent 80-page / 100k-character text cutoff."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def check():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        txt=root/"long.txt"
        txt.write_text("A"*110000+"TEXT_AT_END",encoding="utf-8")
        extracted=project.extract_text(txt)
        assert extracted.endswith("TEXT_AT_END") and len(extracted)>100000

        doc=Document()
        doc.add_paragraph("B"*104000+"DOCX_AT_END")
        path=root/"long.docx"
        doc.save(path)
        docx_text=project.extract_text(path)
        assert "DOCX_AT_END" in docx_text and len(docx_text)>100000

        class FakePage:
            def __init__(self,number):
                self.number=number
            def extract_text(self):
                return ("C"*120000 if self.number==1 else
                        "LAST_PDF_PAGE_83" if self.number==83 else f"PAGE_{self.number}")
        class FakeReader:
            def __init__(self,path):
                self.pages=[FakePage(i) for i in range(1,84)]
        with patch.object(project,"PdfReader",FakeReader):
            pdf_text=project.extract_text(root/"fake.pdf")
        assert "LAST_PDF_PAGE_83" in pdf_text
        assert len(pdf_text)>100000

    print("Extraction completeness PASS: DOCX/TXT over 100k chars and PDF page 83 preserved")


if __name__=="__main__":
    check()
