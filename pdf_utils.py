"""Shared PDF constants and low-level helpers."""

from typing import Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle

PAGE_W, PAGE_H = letter
MARGIN = 0.65 * inch

COL_HEADER_BG = colors.HexColor("#1a1a2e")
COL_HEADER_FG = colors.white
COL_ROW_ALT = colors.HexColor("#f0f4ff")
COL_ACCENT = colors.HexColor("#4a6fa5")
COL_RULE = colors.HexColor("#cccccc")


def merge_pdfs(pdf_paths: list, output: str) -> None:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for path in pdf_paths:
        for page in PdfReader(path).pages:
            writer.add_page(page)
    with open(output, "wb") as fh:
        writer.write(fh)


def hr(width: float) -> Table:
    tbl = Table([[""]], colWidths=[width], rowHeights=[1])
    tbl.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.75, COL_ACCENT),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return tbl


def cell_style(bold: bool = False, fg: colors.Color = colors.black) -> ParagraphStyle:
    return ParagraphStyle(
        f"cell_{'b' if bold else 'n'}",
        fontSize=8.5,
        fontName="Helvetica-Bold" if bold else "Helvetica",
        textColor=fg,
        leading=11,
    )


def make_page_footer(project_name: str, author: str, total_pages: int) -> Callable:
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.grey)
        footer_text = project_name
        if author:
            footer_text += f"  \u00b7  {author}"
        page_text = f"Page {doc.page} of {total_pages}" if total_pages else f"Page {doc.page}"
        canvas.drawString(MARGIN, 0.45 * inch, footer_text)
        canvas.drawRightString(PAGE_W - MARGIN, 0.45 * inch, page_text)
        canvas.setStrokeColor(COL_RULE)
        canvas.setLineWidth(0.4)
        canvas.line(MARGIN, 0.55 * inch, PAGE_W - MARGIN, 0.55 * inch)
        canvas.restoreState()

    return _footer
