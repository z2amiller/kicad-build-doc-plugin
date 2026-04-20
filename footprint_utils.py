"""Helpers for working with kipy footprint objects."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

_WEBVIEW_AVAILABLE: Optional[bool] = None


def check_webview() -> bool:
    """Return True if wx.html2 WebView is available (cached after first call)."""
    global _WEBVIEW_AVAILABLE
    if _WEBVIEW_AVAILABLE is None:
        try:
            import wx.html2  # noqa: F401

            _WEBVIEW_AVAILABLE = True
        except Exception:
            _WEBVIEW_AVAILABLE = False
    return _WEBVIEW_AVAILABLE


@dataclass
class ControlEntry:
    ref: str
    label: str
    value: str


@dataclass
class Controls:
    external: List[ControlEntry]
    internal: List[ControlEntry]


def safe_get_footprints(board, log: Optional[Callable] = None) -> List:
    """Return board.get_footprints() as a list, or [] if the IPC API raises."""
    try:
        return list(board.get_footprints())
    except Exception as exc:
        if log:
            log(f"  Warning: could not retrieve footprints: {exc}")
        return []


def safe_get_shapes(board, log: Optional[Callable] = None) -> List:
    """Return board.get_shapes() as a list, or [] if the IPC API raises."""
    try:
        return list(board.get_shapes())
    except Exception as exc:
        if log:
            log(f"  Warning: could not retrieve board shapes: {exc}")
        return []


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


_EXCLUDE_ALL_RE = re.compile(r"^(D|LED)\d*$", re.IGNORECASE)
_EXCLUDE_INTERNAL_RE = re.compile(r"^(D|LED|TP)\d*$", re.IGNORECASE)

# Footprint library prefixes that indicate LED/diode indicators regardless of ref prefix.
# Catches SMD LEDs whose refs don't follow D*/LED* convention.
_LED_LIBRARY_RE = re.compile(r"^(LED_SMD|LED_THT|Diode_SMD|Diode_THT)", re.IGNORECASE)


def _is_led_footprint(fp) -> bool:
    try:
        library = fp.definition.id.library
        return bool(_LED_LIBRARY_RE.match(library))
    except Exception:
        return False


def _is_single_pad(fp) -> bool:
    try:
        return len(fp.pads) <= 1
    except Exception:
        return False


def extract_controls(board, external_ids: set) -> Controls:
    """Return Controls with external and internal ControlEntry lists.

    External = footprint ID in external_ids; internal = everything else
    with a Control field.

    Global exclusions (external and internal): D*, LED* (diodes/LEDs).
    Internal-only additional exclusions: TP* (test points), single-pad
    footprints, and any footprint whose ref looks like an LED indicator.
    """
    external: List[ControlEntry] = []
    internal: List[ControlEntry] = []
    seen: set = set()

    for fp in safe_get_footprints(board):
        ref = fp.reference_field.text.value
        if ref.startswith("~") or ref in ("REF**", ""):
            continue
        if _EXCLUDE_ALL_RE.match(ref) or _is_led_footprint(fp):
            continue
        label = get_field(fp, "Control")
        if not label or label in seen:
            continue
        seen.add(label)

        entry = ControlEntry(ref=ref, label=label, value=fp.value_field.text.value)
        if get_fp_id(fp) in external_ids:
            external.append(entry)
        elif not _EXCLUDE_INTERNAL_RE.match(ref) and not _is_single_pad(fp):
            internal.append(entry)

    external.sort(key=lambda c: ref_sort_key(c.ref))
    internal.sort(key=lambda c: ref_sort_key(c.ref))
    return Controls(external=external, internal=internal)
