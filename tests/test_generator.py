"""Integration tests for BuildDocGenerator with a mock kipy Board."""
import os
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfReader

from build_doc_generator import BuildDocGenerator


# ── Mock board fixture ────────────────────────────────────────────────────────

def _make_fp(ref, value):
    fp = MagicMock()
    fp.reference_field.text.value = ref
    fp.value_field.text.value = value
    fp.attributes.exclude_from_bill_of_materials = False
    fp.attributes.exclude_from_position_files = False
    fp.attributes.do_not_populate = False
    fp.texts_and_fields = []
    fp.definition.id.name = "Generic"
    fp.definition.id.library = "Device"
    return fp


def _make_board(tmp_path):
    board = MagicMock()
    board.name = str(tmp_path / "test.kicad_pcb")
    board.get_project.return_value.path = str(tmp_path)
    board.get_footprints.return_value = [
        _make_fp("R1", "10k"),
        _make_fp("C1", "100nF"),
    ]
    board.get_shapes.return_value = []
    return board


def _make_params(tmp_path, **flags):
    defaults = {
        "include_cover": False,
        "include_bom": False,
        "include_enclosure": False,
        "include_sch": False,
    }
    defaults.update(flags)
    return {
        "project_name": "Test Project",
        "author": "Tester",
        "revision": "1.0",
        "output_path": str(tmp_path / "out.pdf"),
        "sch_path": "",
        **defaults,
    }


# Patches applied to every generator test so we don't need kicad-cli or kipy
_PATCHES = [
    patch("board_image.export_board_pdf", return_value=None),
    patch("enclosure_template.board_size_mm", return_value=None),
    patch("enclosure_template._board_bbox", return_value=None),
    patch("panel_config.load_panel_config", return_value={
        "enclosure": {
            "width_mm": 125, "height_mm": 50,
            "top_jack_row_mm": 12, "top_pot_row_mm": 25,
            "margin_mm": 7,
        },
        "footprints": {},
    }),
]


def _apply_patches(fn):
    for p in reversed(_PATCHES):
        fn = p(fn)
    return fn


def _fake_enclosure_pdf(board, config, project_name, author,
                         total_pages, page_num, out_path, log=None):
    """Write a minimal single-page PDF so the generator can merge it."""
    from reportlab.pdfgen import canvas as rl_canvas
    c = rl_canvas.Canvas(out_path)
    c.drawString(50, 750, "Enclosure placeholder")
    c.showPage()
    c.save()


@pytest.mark.parametrize("flags,expected_pages", [
    ({"include_cover": True},  1),
    ({"include_bom": True},    1),
    ({"include_cover": True, "include_bom": True}, 2),
    ({"include_cover": True, "include_bom": True, "include_enclosure": True}, 3),
    ({"include_enclosure": True}, 1),
])
def test_generate_page_count(flags, expected_pages, tmp_path):
    board = _make_board(tmp_path)
    params = _make_params(tmp_path, **flags)

    with patch("board_image.export_board_pdf", return_value=None), \
         patch("build_doc_generator.board_size_mm", return_value=None), \
         patch("build_doc_generator.generate_enclosure_pdf", side_effect=_fake_enclosure_pdf), \
         patch("build_doc_generator.load_panel_config", return_value={"enclosure": {}, "footprints": {}}):
        gen = BuildDocGenerator(board, params)
        gen.generate()

    out = params["output_path"]
    assert os.path.exists(out)
    assert len(PdfReader(out).pages) == expected_pages


def test_generate_raises_when_no_sections(tmp_path):
    board = _make_board(tmp_path)
    params = _make_params(tmp_path)  # all flags False

    gen = BuildDocGenerator(board, params)
    with pytest.raises(RuntimeError, match="No pages"):
        gen.generate()


def test_output_pdf_exists(tmp_path):
    board = _make_board(tmp_path)
    params = _make_params(tmp_path, include_bom=True)

    with patch("board_image.export_board_pdf", return_value=None), \
         patch("build_doc_generator.board_size_mm", return_value=None):
        BuildDocGenerator(board, params).generate()

    assert os.path.exists(params["output_path"])
