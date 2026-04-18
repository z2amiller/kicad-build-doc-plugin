"""BOM (Parts List) page generation."""

from typing import Callable, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from footprint_utils import friendly_footprint_type, get_field, ref_sort_key, safe_get_footprints
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
)


def build_bom_story(
    board,
    project_name: str,
    styles,
    log: Optional[Callable] = None,
) -> List:
    story: List = []
    inner_w = PAGE_W - 2 * MARGIN

    story.append(
        Paragraph(
            project_name,
            ParagraphStyle(
                "BomTitle",
                fontSize=20,
                fontName="Helvetica-Bold",
                textColor=COL_HEADER_BG,
                spaceAfter=6,
            ),
        )
    )
    story.append(
        Paragraph(
            "Parts List",
            ParagraphStyle(
                "BomSub",
                fontSize=13,
                fontName="Helvetica",
                textColor=COL_ACCENT,
                spaceAfter=10,
            ),
        )
    )
    story.append(hr(inner_w))
    story.append(Spacer(1, 0.15 * inch))

    bom = collect_bom(board)

    if not bom:
        story.append(Paragraph("No components found on board.", styles["Normal"]))
        return story

    col_widths = [0.9 * inch, 1.1 * inch, 2.5 * inch, 2.2 * inch]
    header = [
        Paragraph("<b>LOCATION</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
        Paragraph("<b>VALUE</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
        Paragraph("<b>TYPE</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
        Paragraph("<b>NOTES</b>", cell_style(bold=True, fg=COL_HEADER_FG)),
    ]
    data = [header]
    extra_styles: List = []

    for row in bom:
        idx = len(data)
        if row.get("separator"):
            data.append([""] * 4)
            extra_styles += [
                ("BACKGROUND", (0, idx), (-1, idx), colors.white),
                ("LINEABOVE", (0, idx), (-1, idx), 0.75, COL_ACCENT),
                ("TOPPADDING", (0, idx), (-1, idx), 1),
                ("BOTTOMPADDING", (0, idx), (-1, idx), 1),
                ("GRID", (0, idx), (-1, idx), 0, colors.white),
            ]
        else:
            data.append(
                [
                    Paragraph(row["ref"], cell_style()),
                    Paragraph(row["value"], cell_style()),
                    Paragraph(row["type"], cell_style()),
                    Paragraph(row["notes"], cell_style()),
                ]
            )

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
            + extra_styles
        )
    )
    story.append(tbl)
    return story


def collect_bom(board) -> List[Dict]:
    """Extract BOM rows from board footprints.

    Controls (footprints with a Control field) are always included regardless of
    KiCad exclusion flags — they're user-populated parts.  Everything else respects
    exclude_from_bill_of_materials, exclude_from_position_files, and do_not_populate.
    Controls sort after regular parts, separated by a thin rule row.
    """
    rows: List[Dict] = []
    for fp in safe_get_footprints(board):
        ref = fp.reference_field.text.value
        if ref.startswith("~") or ref in ("REF**", ""):
            continue

        control = get_field(fp, "Control")
        location = control if control else ref

        if not control:
            attrs = fp.attributes
            if attrs.exclude_from_bill_of_materials or attrs.exclude_from_position_files or attrs.do_not_populate:
                continue

        val = fp.value_field.text.value

        desc = get_field(fp, "Description")
        if not desc:
            fp_name = fp.definition.id.name
            desc = friendly_footprint_type(ref, fp_name)

        notes = get_field(fp, "Notes")

        rows.append(
            {
                "ref": location,
                "value": val,
                "type": desc,
                "notes": notes,
                "is_control": bool(control),
            }
        )

    parts = [r for r in rows if not r["is_control"]]
    ctrl_rows = [r for r in rows if r["is_control"]]
    parts.sort(key=lambda r: ref_sort_key(r["ref"]))
    ctrl_rows.sort(key=lambda r: r["ref"].upper())

    if parts and ctrl_rows:
        return parts + [{"separator": True}] + ctrl_rows
    return parts + ctrl_rows
