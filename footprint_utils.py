"""Helpers for working with pcbnew footprint objects."""

import re
from typing import Dict, List, Tuple


def get_field(fp, name: str) -> str:
    """Return the text of a footprint field by name, or '' if absent."""
    for field in fp.GetFields():
        try:
            if field.GetName() == name:
                return field.GetText().strip()
        except Exception:
            pass
    return ""


def get_fp_id(fp) -> str:
    """Return 'LibNickname:LibItemName' for a footprint."""
    return "{}:{}".format(fp.GetFPID().GetLibNickname(), fp.GetFPID().GetLibItemName())


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

    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref.startswith("~") or ref in ("REF**", ""):
            continue
        if exclude_prefix.match(ref):
            continue
        label = get_field(fp, "Control")
        if not label or label in seen:
            continue
        seen.add(label)

        entry = {"ref": ref, "label": label, "value": fp.GetValue()}
        if get_fp_id(fp) in external_ids:
            external.append(entry)
        else:
            internal.append(entry)

    external.sort(key=lambda c: ref_sort_key(c["ref"]))
    internal.sort(key=lambda c: ref_sort_key(c["ref"]))
    return {"external": external, "internal": internal}
