import math
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kipy.board import BoardLayer
from enclosure_template import _pad_centroid_offset_mm

NM = 1_000_000  # nanometres per mm


def _make_pad(abs_x_nm, abs_y_nm):
    p = MagicMock()
    p.position.x = abs_x_nm
    p.position.y = abs_y_nm
    return p


def _make_fp(fp_x_nm, fp_y_nm, pads, orientation_deg=0.0, layer=BoardLayer.BL_F_Cu):
    fp = MagicMock()
    fp.position.x = fp_x_nm
    fp.position.y = fp_y_nm
    fp.definition.pads = pads
    angle = MagicMock()
    angle.to_radians.return_value = math.radians(orientation_deg)
    fp.orientation = angle
    fp.layer = layer
    return fp


def test_centroid_at_origin_two_pads():
    # Footprint at origin; pad1 at (0,0), pad2 at (2.54mm, 0).
    # Centroid offset = (1.27mm, 0).
    fp = _make_fp(0, 0, [_make_pad(0, 0), _make_pad(2_540_000, 0)])
    dx, dy = _pad_centroid_offset_mm(fp)
    assert abs(dx - 1.27) < 1e-6
    assert abs(dy) < 1e-6


def test_centroid_with_fp_offset():
    # Footprint at (108.76mm, 100.73mm) — kipy gives absolute pad positions.
    # Pad1 at fp origin, pad2 at fp_x + 2.54mm.
    fp_x = int(108.76 * NM)
    fp_y = int(100.73 * NM)
    fp = _make_fp(fp_x, fp_y, [
        _make_pad(fp_x, fp_y),
        _make_pad(fp_x + 2_540_000, fp_y),
    ])
    dx, dy = _pad_centroid_offset_mm(fp)
    assert abs(dx - 1.27) < 1e-6
    assert abs(dy) < 1e-6


def test_centroid_rotated_90():
    # Footprint at origin, rotated 90°: local (1.27mm, 0) → PCB offset (0, 1.27mm).
    fp = _make_fp(0, 0, [_make_pad(0, 0), _make_pad(2_540_000, 0)], orientation_deg=90.0)
    dx, dy = _pad_centroid_offset_mm(fp)
    assert abs(dx) < 1e-6
    assert abs(dy - 1.27) < 1e-6


def test_centroid_b_cu_negates_x():
    # B_Cu footprint: local X is mirrored, so dx is negated.
    fp = _make_fp(0, 0,
        [_make_pad(0, 0), _make_pad(2_540_000, 0)],
        layer=BoardLayer.BL_B_Cu,
    )
    dx, dy = _pad_centroid_offset_mm(fp)
    assert abs(dx - (-1.27)) < 1e-6
    assert abs(dy) < 1e-6


def test_centroid_symmetric_pads_zero_offset():
    # Pads symmetric around fp origin → centroid = fp origin → offset (0, 0).
    fp = _make_fp(0, 0, [_make_pad(-1_270_000, 0), _make_pad(1_270_000, 0)], orientation_deg=45.0)
    dx, dy = _pad_centroid_offset_mm(fp)
    assert abs(dx) < 1e-6
    assert abs(dy) < 1e-6


def test_centroid_no_pads_returns_zero():
    fp = _make_fp(0, 0, [])
    dx, dy = _pad_centroid_offset_mm(fp)
    assert dx == 0.0
    assert dy == 0.0


def test_centroid_missing_definition_returns_zero():
    fp = MagicMock(spec=["position", "orientation", "layer"])
    dx, dy = _pad_centroid_offset_mm(fp)
    assert dx == 0.0
    assert dy == 0.0
