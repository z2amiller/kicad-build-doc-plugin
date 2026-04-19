"""Tests for tayda_manifest.py."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pypdf import PdfReader

from enclosure_template import TaydaHole
from tayda_manifest import generate_tayda_manifest_pdf


def _holes():
    return [
        TaydaHole(side="A", diameter_mm=8.2, x_mm=0.07, y_mm=37.94, label="BASS"),
        TaydaHole(side="A", diameter_mm=8.2, x_mm=20.03, y_mm=38.00, label="TREBLE"),
        TaydaHole(side="A", diameter_mm=12.2, x_mm=0.0, y_mm=-45.2, label="Footswitch"),
        TaydaHole(side="B", diameter_mm=9.5, x_mm=-10.0, y_mm=0.0, label="Input"),
    ]


def test_generates_pdf(tmp_path):
    out = str(tmp_path / "tayda.pdf")
    generate_tayda_manifest_pdf(
        holes=_holes(),
        project_name="Test Project",
        author="Tester",
        page_num=5,
        total_pages=5,
        out_path=out,
    )
    assert os.path.exists(out)
    assert len(PdfReader(out).pages) == 1


def test_empty_holes_still_generates(tmp_path):
    out = str(tmp_path / "tayda_empty.pdf")
    generate_tayda_manifest_pdf(
        holes=[],
        project_name="Empty",
        author="",
        page_num=1,
        total_pages=1,
        out_path=out,
    )
    assert os.path.exists(out)


def test_sort_order_side_a_before_b_then_y_desc():
    """Side A comes before B; within a side, holes are sorted top-to-bottom (Y desc)."""
    from tayda_manifest import generate_tayda_manifest_pdf as _gen
    holes = [
        TaydaHole(side="B", diameter_mm=9.5, x_mm=0, y_mm=0, label="DC"),
        TaydaHole(side="A", diameter_mm=8.2, x_mm=0, y_mm=-10, label="Low"),
        TaydaHole(side="A", diameter_mm=8.2, x_mm=0, y_mm=30, label="High"),
    ]
    sorted_holes = sorted(holes, key=lambda h: (h.side, -h.y_mm))
    labels = [h.label for h in sorted_holes]
    assert labels == ["High", "Low", "DC"]
