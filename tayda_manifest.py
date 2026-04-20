"""Tayda drill manifest page — PDF table of Side/Diameter/X/Y for custom drilling."""

from __future__ import annotations

from typing import Callable, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from enclosure_template import TaydaHole
from pdf_utils import (
    COL_ACCENT,
    COL_HEADER_BG,
    COL_HEADER_FG,
    COL_ROW_ALT,
    COL_RULE,
    MARGIN,
    PAGE_W,
    cell_style,
    hr,
    make_page_footer,
)


def generate_tayda_manifest_pdf(
    holes: List[TaydaHole],
    project_name: str,
    author: str,
    page_num: int,
    total_pages: int,
    out_path: str,
    log: Optional[Callable] = None,
    enclosure_label: Optional[str] = None,
) -> str:
    """Render a Tayda-compatible drill table as a single PDF page.

    Columns: Side | Diameter (mm) | X (mm) | Y (mm)
    Sort order: Side A before B, then by Y descending (top of enclosure first).
    Returns out_path.
    """
    _log = log or (lambda msg: None)

    sorted_holes = sorted(
        holes,
        key=lambda h: (h.side, -h.y_mm),
    )

    story: List = []
    inner_w = PAGE_W - 2 * MARGIN

    story.append(
        Paragraph(
            project_name,
            ParagraphStyle(
                "ManifestTitle",
                fontSize=20,
                fontName="Helvetica-Bold",
                textColor=COL_HEADER_BG,
                spaceAfter=6,
            ),
        )
    )
    sub_text = "Tayda Drill Manifest"
    if enclosure_label:
        sub_text += f"  \u2014  {enclosure_label}"
    story.append(
        Paragraph(
            sub_text,
            ParagraphStyle(
                "ManifestSub",
                fontSize=13,
                fontName="Helvetica",
                textColor=COL_ACCENT,
                spaceAfter=4,
            ),
        )
    )
    story.append(
        Paragraph(
            "X/Y are mm from the centre of each face (positive Y = toward front). "
            "Side A = front face. Side B = top face. "
            "Side C = left face (rotated -R enclosures).",
            ParagraphStyle(
                "ManifestNote",
                fontSize=8,
                fontName="Helvetica",
                textColor=colors.HexColor("#666666"),
                spaceAfter=10,
            ),
        )
    )
    story.append(hr(inner_w))
    story.append(Spacer(1, 0.15 * inch))

    col_widths = [0.7 * inch, 1.4 * inch, 1.6 * inch, 1.6 * inch, 2.4 * inch]
    header = [
        Paragraph("<b>SIDE</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
        Paragraph("<b>DIAMETER (mm)</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
        Paragraph("<b>X (mm)</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
        Paragraph("<b>Y (mm)</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
        Paragraph("<b>LABEL</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
    ]
    data = [header]

    for hole in sorted_holes:
        data.append(
            [
                Paragraph(hole.side, cell_style()),
                Paragraph(f"{hole.diameter_mm:.1f}", cell_style()),
                Paragraph(f"{hole.x_mm:.1f}", cell_style()),
                Paragraph(f"{hole.y_mm:.1f}", cell_style()),
                Paragraph(hole.label, cell_style()),
            ]
        )

    if len(data) == 1:
        data.append([Paragraph("No holes defined.", cell_style())] + [""] * 4)

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COL_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), COL_HEADER_FG),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COL_ROW_ALT]),
                ("GRID", (0, 0), (-1, -1), 0.4, COL_RULE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(tbl)

    footer_fn = make_page_footer(project_name, author, total_pages)
    doc = SimpleDocTemplate(
        out_path,
        pagesize=letter,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )
    doc.build(story, onFirstPage=footer_fn, onLaterPages=footer_fn)
    _log(f"  Tayda manifest written ({len(sorted_holes)} hole(s)).")
    return out_path
