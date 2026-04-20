"""Tests for footprint_editor.py — load, resolve_notes, commit_edits."""

from unittest.mock import MagicMock

from footprint_editor import FootprintRow, commit_edits, load_footprints, resolve_notes

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_field(name, value):
    f = MagicMock()
    f.name = name
    f.text = MagicMock()
    f.text.value = value
    return f


def _make_fp(ref, value, fields=None, fp_id="Device:Generic", layer=None):
    fp = MagicMock()
    fp.reference_field.text.value = ref
    fp.value_field.text.value = value
    fp.definition.id.library = fp_id.split(":")[0]
    fp.definition.id.name = fp_id.split(":")[1]
    fp.texts_and_fields = [_make_field(k, v) for k, v in (fields or {}).items()]
    fp.attributes.exclude_from_bill_of_materials = False
    fp.attributes.exclude_from_position_files = False
    fp.attributes.do_not_populate = False
    if layer is not None:
        fp.layer = layer
    return fp


def _make_board(fps):
    board = MagicMock()
    board.get_footprints.return_value = fps
    return board


# ── resolve_notes ─────────────────────────────────────────────────────────────


def test_resolve_notes_prefers_notes_field():
    fp = _make_fp("R1", "10k", {"Notes": "Metal film", "Description": "Resistor"})
    assert resolve_notes(fp) == "Metal film"


def test_resolve_notes_falls_back_to_description():
    fp = _make_fp("R1", "10k", {"Description": "Resistor, 1/4W"})
    assert resolve_notes(fp) == "Resistor, 1/4W"


def test_resolve_notes_falls_back_to_datasheet():
    fp = _make_fp("R1", "10k", {"Datasheet": "https://example.com/ds.pdf"})
    assert resolve_notes(fp) == "https://example.com/ds.pdf"


def test_resolve_notes_truncates_datasheet():
    long_url = "https://example.com/" + "x" * 100
    fp = _make_fp("R1", "10k", {"Datasheet": long_url})
    assert len(resolve_notes(fp)) <= 80


def test_resolve_notes_takes_first_line_of_datasheet():
    fp = _make_fp("R1", "10k", {"Datasheet": "line one\nline two"})
    assert resolve_notes(fp) == "line one"


def test_resolve_notes_returns_empty_when_nothing():
    fp = _make_fp("R1", "10k")
    assert resolve_notes(fp) == ""


def test_resolve_notes_skips_empty_notes_field():
    fp = _make_fp("R1", "10k", {"Notes": "", "Description": "Resistor"})
    assert resolve_notes(fp) == "Resistor"


# ── load_footprints ───────────────────────────────────────────────────────────


def test_load_footprints_returns_rows():
    fps = [_make_fp("R1", "10k", {"Description": "Resistor"})]
    rows = load_footprints(_make_board(fps))
    assert len(rows) == 1
    assert rows[0].ref == "R1"
    assert rows[0].description == "Resistor"


def test_load_footprints_skips_placeholder_refs():
    fps = [
        _make_fp("REF**", "val"),
        _make_fp("~1", "val"),
        _make_fp("", "val"),
        _make_fp("R1", "10k"),
    ]
    rows = load_footprints(_make_board(fps))
    assert len(rows) == 1
    assert rows[0].ref == "R1"


def test_load_footprints_sorted_by_value_then_ref():
    fps = [
        _make_fp("R10", "10k"),
        _make_fp("C1", "100nF"),
        _make_fp("R2", "10k"),
    ]
    rows = load_footprints(_make_board(fps))
    assert [r.ref for r in rows] == ["C1", "R2", "R10"]


def test_load_footprints_excludes_dnp():
    fp = _make_fp("R1", "10k")
    fp.attributes.do_not_populate = True
    rows = load_footprints(_make_board([fp]))
    assert len(rows) == 0


def test_load_footprints_excludes_no_bom():
    fp = _make_fp("R1", "10k")
    fp.attributes.exclude_from_bill_of_materials = True
    rows = load_footprints(_make_board([fp]))
    assert len(rows) == 0


def test_load_footprints_keeps_dnp_control():
    fp = _make_fp("RV1", "B100K", {"Control": "Volume"})
    fp.attributes.do_not_populate = True
    rows = load_footprints(_make_board([fp]))
    assert len(rows) == 1


def test_load_footprints_orig_description_captured():
    fps = [_make_fp("R1", "10k", {"Description": "Original"})]
    rows = load_footprints(_make_board(fps))
    rows[0].description = "Changed"
    assert rows[0].description_changed()
    assert rows[0]._orig_description == "Original"


# ── FootprintRow state ────────────────────────────────────────────────────────


def test_footprint_row_not_modified_initially():
    fp = _make_fp("R1", "10k", {"Description": "Resistor"})
    row = FootprintRow(
        ref="R1",
        value="10k",
        fp_type="Resistor, 1/4W",
        fp_id="D:G",
        description="Resistor",
        notes="",
        _fp=fp,
        _orig_description="Resistor",
        _orig_notes="",
    )
    assert not row.is_modified()


def test_footprint_row_modified_after_description_change():
    fp = _make_fp("R1", "10k")
    row = FootprintRow(
        ref="R1",
        value="10k",
        fp_type="Resistor, 1/4W",
        fp_id="D:G",
        description="Old",
        notes="",
        _fp=fp,
        _orig_description="Old",
        _orig_notes="",
    )
    row.description = "New"
    assert row.description_changed()
    assert row.is_modified()


# ── commit_edits ──────────────────────────────────────────────────────────────


def _make_row(ref, value, orig_desc, new_desc, orig_notes="", new_notes=""):
    desc_field = _make_field("Description", orig_desc)
    notes_field = _make_field("Notes", orig_notes)
    fp = _make_fp(ref, value)
    fp.texts_and_fields = [desc_field, notes_field]
    row = FootprintRow(
        ref=ref,
        value=value,
        fp_type="",
        fp_id="D:G",
        description=new_desc,
        notes=new_notes,
        _fp=fp,
        _orig_description=orig_desc,
        _orig_notes=orig_notes,
    )
    return row


def test_commit_edits_no_changes_returns_zero():
    board = MagicMock()
    row = _make_row("R1", "10k", "Resistor", "Resistor")
    count = commit_edits(board, [row])
    assert count == 0
    board.update_items.assert_not_called()
    board.begin_commit.assert_not_called()


def test_commit_edits_calls_update_items_for_changed_rows():
    board = MagicMock()
    row = _make_row("R1", "10k", "Old", "New")
    commit_edits(board, [row])
    board.update_items.assert_called_once()
    updated = board.update_items.call_args[0][0]
    assert row._fp in updated


def test_commit_edits_skips_unchanged_rows():
    board = MagicMock()
    changed = _make_row("R1", "10k", "Old", "New")
    unchanged = _make_row("R2", "10k", "Same", "Same")
    commit_edits(board, [changed, unchanged])
    updated = board.update_items.call_args[0][0]
    assert unchanged._fp not in updated


def test_commit_edits_single_undo_step():
    board = MagicMock()
    rows = [_make_row("R1", "10k", "Old", "New")]
    commit_edits(board, rows)
    board.begin_commit.assert_called_once()
    board.push_commit.assert_called_once()
    # commit object from begin_commit passed to push_commit
    assert board.push_commit.call_args[0][0] == board.begin_commit.return_value


def test_commit_edits_sets_description_field_value():
    board = MagicMock()
    row = _make_row("R1", "10k", "Old", "New Metal Film Resistor")
    commit_edits(board, [row])
    desc_field = next(f for f in row._fp.texts_and_fields if f.name == "Description")
    assert desc_field.text.value == "New Metal Film Resistor"


def test_commit_edits_sets_notes_field_value():
    board = MagicMock()
    row = _make_row("R1", "10k", "Resistor", "Resistor", "", "New note")
    commit_edits(board, [row])
    notes_field = next(f for f in row._fp.texts_and_fields if f.name == "Notes")
    assert notes_field.text.value == "New note"


def test_commit_edits_returns_count():
    board = MagicMock()
    rows = [
        _make_row("R1", "10k", "Old", "New"),
        _make_row("R2", "10k", "Old", "New"),
        _make_row("R3", "10k", "Same", "Same"),
    ]
    assert commit_edits(board, rows) == 2
