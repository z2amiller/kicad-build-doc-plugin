"""Business logic for bulk-editing footprint Description and Notes fields.

No wx imports. No top-level kipy import (kipy is only available inside KiCad).
Accept the live board object as a parameter so tests can pass a mock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from footprint_utils import get_field, get_fp_id, ref_sort_key, safe_get_footprints


@dataclass
class FootprintRow:
    ref: str
    value: str
    fp_type: str          # human-friendly type string (e.g. "Resistor, 1/4W")
    fp_id: str            # "Lib:Part" identifier
    description: str      # editable — maps to the Description footprint field
    notes: str            # editable — maps to the Notes footprint field
    _fp: Any = field(repr=False, compare=False)  # live kipy footprint object
    _orig_description: str = field(repr=False, compare=False, default="")
    _orig_notes: str = field(repr=False, compare=False, default="")

    def description_changed(self) -> bool:
        return self.description != self._orig_description

    def notes_changed(self) -> bool:
        return self.notes != self._orig_notes

    def is_modified(self) -> bool:
        return self.description_changed() or self.notes_changed()


def resolve_notes(fp) -> str:
    """Return the best available notes string for a footprint.

    Resolution order:
      1. 'Notes' custom field
      2. 'Description' field
      3. 'Datasheet' field (first line, truncated to 80 chars)
      4. Empty string
    """
    notes = get_field(fp, "Notes")
    if notes:
        return notes
    desc = get_field(fp, "Description")
    if desc:
        return desc
    datasheet = get_field(fp, "Datasheet")
    if datasheet:
        first_line = datasheet.split("\n")[0].strip()
        return first_line[:80]
    return ""


def load_footprints(board) -> List[FootprintRow]:
    """Return all non-placeholder footprints as FootprintRow objects.

    Sorted by (value, ref) so similar components are adjacent.
    DNP and excluded-from-BOM footprints are included — users may still
    want to document them.
    """
    from footprint_utils import friendly_footprint_type

    rows: List[FootprintRow] = []
    for fp in safe_get_footprints(board):
        ref = fp.reference_field.text.value
        if not ref or ref.startswith("~") or ref in ("REF**", ""):
            continue

        control = get_field(fp, "Control")
        if not control:
            attrs = fp.attributes
            if (attrs.exclude_from_bill_of_materials
                    or attrs.exclude_from_position_files
                    or attrs.do_not_populate):
                continue

        desc = get_field(fp, "Description")
        notes = get_field(fp, "Notes")
        fp_id = get_fp_id(fp)
        fp_type = friendly_footprint_type(ref, fp.definition.id.name)

        row = FootprintRow(
            ref=ref,
            value=fp.value_field.text.value,
            fp_type=fp_type,
            fp_id=fp_id,
            description=desc,
            notes=notes,
            _fp=fp,
            _orig_description=desc,
            _orig_notes=notes,
        )
        rows.append(row)

    import re as _re
    def _prefix(ref: str) -> str:
        m = _re.match(r"[A-Za-z_]+", ref)
        return m.group(0).upper() if m else ref

    rows.sort(key=lambda r: (_prefix(r.ref), r.value.lower(), ref_sort_key(r.ref)))
    return rows


def _get_or_create_field(fp, field_name: str) -> Any:
    """Return the existing field object for field_name, or create and add it.

    New fields are added to fp.definition.items (the custom-fields list) with
    visible=False so they don't clutter the board canvas.
    """
    name_lower = field_name.lower()
    for item in fp.texts_and_fields:
        item_name = getattr(item, "name", None)
        if item_name is not None and item_name.lower() == name_lower:
            return item

    # Field absent — create a new kipy Field and attach it to the definition.
    from kipy.board_types import Field as KipyField
    new_field = KipyField()
    new_field.name = field_name
    new_field.visible = False
    fp.definition.add_item(new_field)
    return new_field


def commit_edits(
    board,
    rows: List[FootprintRow],
    log: Optional[Callable] = None,
) -> int:
    """Write modified Description and Notes fields back to the board.

    Groups all changes into a single undo step via begin_commit/push_commit.
    Returns the number of footprints actually updated.
    """
    _log = log or (lambda msg: None)

    modified = [r for r in rows if r.is_modified()]
    if not modified:
        _log("  No changes to write.")
        return 0

    commit = board.begin_commit()
    fps_to_update = []

    for row in modified:
        fp = row._fp

        if row.description_changed():
            for item in fp.texts_and_fields:
                item_name = getattr(item, "name", None)
                if item_name is not None and item_name.lower() == "description":
                    item.text.value = row.description
                    break
            else:
                new_field = _get_or_create_field(fp, "Description")
                new_field.text.value = row.description

        if row.notes_changed():
            for item in fp.texts_and_fields:
                item_name = getattr(item, "name", None)
                if item_name is not None and item_name.lower() == "notes":
                    item.text.value = row.notes
                    break
            else:
                new_field = _get_or_create_field(fp, "Notes")
                new_field.text.value = row.notes

        fps_to_update.append(fp)
        _log(f"  Updated {row.ref}: description={row.description!r}, notes={row.notes!r}")

    board.update_items(fps_to_update)
    board.push_commit(commit, "Update component descriptions")
    _log(f"  Committed {len(fps_to_update)} footprint(s) to board.")
    return len(fps_to_update)
