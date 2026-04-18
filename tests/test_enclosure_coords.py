"""Unit tests for enclosure coordinate math (no pcbnew needed)."""

TOP_ROW_MM = 38.0


def _make_fp_to_enc(board_cx: float, top_pcb_y: float):
    """Return a fp_to_enc closure matching the one in enclosure_template.py."""

    def fp_to_enc(pcb_x: float, pcb_y: float, off_x: float = 0.0, off_y: float = 0.0):
        return (
            -(pcb_x - board_cx) + off_x,
            (TOP_ROW_MM + top_pcb_y - pcb_y) + off_y,
        )

    return fp_to_enc


def test_centre_x_maps_to_zero():
    f = _make_fp_to_enc(board_cx=100.0, top_pcb_y=50.0)
    ex, _ = f(100.0, 50.0)
    assert ex == 0.0


def test_topmost_control_maps_to_top_row():
    f = _make_fp_to_enc(board_cx=0.0, top_pcb_y=20.0)
    _, ey = f(0.0, 20.0)
    assert ey == TOP_ROW_MM


def test_control_below_top_shifts_down():
    f = _make_fp_to_enc(board_cx=0.0, top_pcb_y=20.0)
    _, ey = f(0.0, 30.0)  # 10 mm below the anchor
    assert ey == TOP_ROW_MM - 10.0


def test_x_mirror():
    f = _make_fp_to_enc(board_cx=100.0, top_pcb_y=0.0)
    ex, _ = f(105.0, 0.0)  # 5 mm right of centre
    assert ex == -5.0


def test_offset_applied_after_mirror():
    f = _make_fp_to_enc(board_cx=100.0, top_pcb_y=0.0)
    ex, ey = f(100.0, 0.0, off_x=2.0, off_y=3.0)
    assert ex == 2.0
    assert ey == TOP_ROW_MM + 3.0


def test_pot_offset_y_lifts_hole():
    """A 16 mm offset_y (pot shaft above footprint origin) raises the enc Y."""
    f = _make_fp_to_enc(board_cx=0.0, top_pcb_y=0.0)
    _, ey_no_offset = f(0.0, 0.0)
    _, ey_with_offset = f(0.0, 0.0, off_y=16.0)
    assert ey_with_offset - ey_no_offset == 16.0
