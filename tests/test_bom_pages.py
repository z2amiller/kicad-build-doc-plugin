from unittest.mock import MagicMock

from bom_pages import collect_bom


def _make_fp(
    ref,
    value,
    control="",
    excluded_bom=False,
    excluded_pos=False,
    dnp=False,
):
    """Build a minimal mock footprint."""
    fp = MagicMock()
    fp.GetReference.return_value = ref
    fp.GetValue.return_value = value
    fp.IsExcludedFromBOM.return_value = excluded_bom
    fp.IsExcludedFromPosFiles.return_value = excluded_pos
    fp.IsDNP.return_value = dnp

    # Fields: only populate Control if non-empty
    fields = []
    if control:
        f = MagicMock()
        f.GetName.return_value = "Control"
        f.GetText.return_value = control
        fields.append(f)
    fp.GetFields.return_value = fields

    fp_id_mock = MagicMock()
    fp_id_mock.GetLibItemName.return_value = MagicMock(__str__=lambda s: "Generic")
    fp.GetFPID.return_value = fp_id_mock
    return fp


def _make_board(fps):
    board = MagicMock()
    board.GetFootprints.return_value = fps
    return board


def test_excludes_dnp():
    bom = collect_bom(_make_board([_make_fp("R1", "10k", dnp=True)]))
    assert bom == []


def test_excludes_excluded_from_bom():
    bom = collect_bom(_make_board([_make_fp("R1", "10k", excluded_bom=True)]))
    assert bom == []


def test_controls_always_included_despite_exclusion_flags():
    fp = _make_fp("RV1", "B100K", control="Volume", excluded_bom=True)
    bom = collect_bom(_make_board([fp]))
    rows = [r for r in bom if not r.get("separator")]
    assert len(rows) == 1
    assert rows[0]["ref"] == "Volume"
    assert rows[0]["is_control"] is True


def test_controls_sort_after_parts():
    fps = [
        _make_fp("RV1", "B100K", control="Volume"),
        _make_fp("R1", "10k"),
    ]
    bom = collect_bom(_make_board(fps))
    non_sep = [r for r in bom if not r.get("separator")]
    assert non_sep[0]["ref"] == "R1"
    assert non_sep[1]["ref"] == "Volume"


def test_separator_inserted_between_parts_and_controls():
    fps = [_make_fp("R1", "10k"), _make_fp("RV1", "B100K", control="Volume")]
    bom = collect_bom(_make_board(fps))
    assert any(r.get("separator") for r in bom)


def test_no_separator_when_only_controls():
    fps = [_make_fp("RV1", "B100K", control="Volume")]
    bom = collect_bom(_make_board(fps))
    assert not any(r.get("separator") for r in bom)


def test_no_separator_when_no_controls():
    fps = [_make_fp("R1", "10k"), _make_fp("C1", "100nF")]
    bom = collect_bom(_make_board(fps))
    assert not any(r.get("separator") for r in bom)


def test_numeric_sort_order():
    fps = [_make_fp(f"R{i}", "10k") for i in [10, 2, 1]]
    bom = collect_bom(_make_board(fps))
    refs = [r["ref"] for r in bom]
    assert refs == ["R1", "R2", "R10"]


def test_skips_placeholder_refs():
    fps = [_make_fp("REF**", "val"), _make_fp("~1", "val"), _make_fp("R1", "10k")]
    bom = collect_bom(_make_board(fps))
    assert len(bom) == 1
    assert bom[0]["ref"] == "R1"
