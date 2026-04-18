"""Helpers for working with kipy footprint objects."""
from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple


def get_board_path(board) -> str:
    """Return the full absolute path to the board .kicad_pcb file.

    kipy's board.name returns DocumentSpecifier.board_filename which may be
    just a bare filename. If it isn't already an absolute path on disk,
    resolve it via the project directory from board.get_project().path.
    """
    name = board.name
    if name and os.path.isabs(name) and os.path.exists(name):
        return name
    try:
        project_dir = board.get_project().path
        if project_dir:
            candidate = os.path.join(project_dir, os.path.basename(name))
            if os.path.exists(candidate):
                return candidate
    except Exception:
        pass
    return name


def get_field(fp, name: str) -> str:
    """Return the text of a footprint field by name, or '' if absent."""
    name_lower = name.lower()
    for item in fp.texts_and_fields:
        item_name = getattr(item, "name", None)
        if item_name is not None and item_name.lower() == name_lower:
            text = getattr(item, "text", None)
            if text is not None:
                return str(getattr(text, "value", "")).strip()
    return ""


def get_fp_id(fp) -> str:
    """Return 'LibNickname:LibItemName' for a footprint."""
    lib_id = fp.definition.id
    return "{}:{}".format(lib_id.library, lib_id.name)


def ref_sort_key(ref: str) -> Tuple[str, int]:
    """Sort key that orders references alphabetically by prefix then numerically."""
    m = re.match(r"([A-Za-z_]+)(\d*)", ref)
    prefix = m.group(1).upper() if m else ref
    num = int(m.group(2)) if m and m.group(2) else 0
    return (prefix, num)


def friendly_footprint_type(ref: str, fp_name: str) -> str:
    """Map a reference designator prefix to a human-friendly component type string."""
    prefix = re.match(r"[A-Za-z_]+", ref)
    p = prefix.group(0).upper() if prefix else ""
    mapping = {
        "R": "Resistor, 1/4W",
        "C": "Capacitor",
        "D": "Diode",
        "Q": "Transistor",
        "U": "IC",
        "IC": "IC",
        "L": "Inductor",
        "SW": "Switch",
        "RV": "Potentiometer",
        "J": "Connector / Jack",
        "LED": "LED",
        "T": "Transformer",
        "F": "Fuse",
        "FB": "Ferrite Bead",
        "X": "Crystal / Oscillator",
        "Y": "Crystal",
        "TP": "Test Point",
        "CLR": "Resistor, 1/4W",
        "TRIM": "Trimmer potentiometer",
    }
    return mapping.get(p, fp_name or "Component")


def extract_controls(board, external_ids: set) -> Dict[str, List]:
    """
    Return {'external': [...], 'internal': [...]} where each entry is
    {'ref', 'label', 'value'}.  External = footprint in external_ids;
    internal = everything else with a Control field.
    LEDs and diodes (D*, LED*) are excluded entirely.
    """
    exclude_prefix = re.compile(r"^(D|LED)\d*$", re.IGNORECASE)

    external: List[dict] = []
    internal: List[dict] = []
    seen: set = set()

    for fp in board.get_footprints():
        ref = fp.reference_field.text.value
        if ref.startswith("~") or ref in ("REF**", ""):
            continue
        if exclude_prefix.match(ref):
            continue
        label = get_field(fp, "Control")
        if not label or label in seen:
            continue
        seen.add(label)

        entry = {"ref": ref, "label": label, "value": fp.value_field.text.value}
        if get_fp_id(fp) in external_ids:
            external.append(entry)
        else:
            internal.append(entry)

    external.sort(key=lambda c: ref_sort_key(c["ref"]))
    internal.sort(key=lambda c: ref_sort_key(c["ref"]))
    return {"external": external, "internal": internal}
