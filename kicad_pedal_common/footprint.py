"""Footprint iteration helpers wrapping the kipy board API.

Provides a kipy-independent dict representation of footprints so plugin code
doesn't call kipy directly everywhere.

The heavy lifting now lives in :mod:`kicad_pedal_common.board_adapter`;
these functions are thin backward-compatible wrappers kept so that existing
callers in bom_export / footprint_export / tests don't need to change.

Python 3.9 compatible — no match/case, no |union syntax, no tomllib.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from kicad_pedal_common.board_adapter import KipyBoardAdapter

NM_PER_MM = 1_000_000  # kipy uses nanometres


def get_footprints(board) -> List[Dict]:
    """Return footprints from a kipy board as a list of plain dicts.

    Each dict has the keys:
        ref             (str)   reference designator
        value           (str)   value field
        footprint_id    (str)   "LibName:FootprintName"
        layer           (str)   "F" or "B"
        pos_x           (float) mm
        pos_y           (float) mm
        rotation        (float) degrees, 0-360 (CCW)
        dnp             (bool)
        exclude_from_bom (bool)

    Footprints with empty or placeholder refs (REF**, ~*) are skipped.

    .. note::
        This is a backward-compatible wrapper around
        :class:`~kicad_pedal_common.board_adapter.KipyBoardAdapter`.
        New code should use the adapter directly.
    """
    adapter = KipyBoardAdapter(board)
    return [
        {
            "ref": fp.ref,
            "value": fp.value,
            "footprint_id": fp.footprint_id,
            "layer": fp.layer,
            "pos_x": fp.pos_x,
            "pos_y": fp.pos_y,
            "rotation": fp.rotation,
            "dnp": fp.dnp,
            "exclude_from_bom": fp.exclude_from_bom,
        }
        for fp in adapter.get_footprints()
    ]


def get_bounding_box(fp) -> Dict[str, float]:
    """Return {"w": float, "h": float} bounding box in mm for a footprint.

    Tries courtyard bounding box first, then pads bounding box, then
    falls back to a default 5x5 mm box.
    """
    _DEFAULT: Dict[str, float] = {"w": 5.0, "h": 5.0}

    # Try to get courtyard or general bounding box from kipy
    try:
        bb = fp.bounding_box
        if bb is not None:
            w = abs(bb.width) / NM_PER_MM
            h = abs(bb.height) / NM_PER_MM
            if w > 0 and h > 0:
                return {"w": w, "h": h}
    except Exception:
        pass

    # Try pads bounding box
    try:
        pads = list(fp.definition.pads)
        if pads:
            xs = [p.position.x for p in pads]
            ys = [p.position.y for p in pads]
            # Estimate pad extents using pad size if available
            pad_ws = []
            pad_hs = []
            for p in pads:
                try:
                    pad_ws.append(p.size.x)
                    pad_hs.append(p.size.y)
                except Exception:
                    pad_ws.append(0)
                    pad_hs.append(0)
            min_x = min(xs[i] - pad_ws[i] / 2 for i in range(len(pads)))
            max_x = max(xs[i] + pad_ws[i] / 2 for i in range(len(pads)))
            min_y = min(ys[i] - pad_hs[i] / 2 for i in range(len(pads)))
            max_y = max(ys[i] + pad_hs[i] / 2 for i in range(len(pads)))
            w = (max_x - min_x) / NM_PER_MM
            h = (max_y - min_y) / NM_PER_MM
            if w > 0 and h > 0:
                return {"w": w, "h": h}
    except Exception:
        pass

    return _DEFAULT


def get_footprint_bbox_center_offset(board, fp) -> Optional[Tuple[float, float]]:
    """Return (cx_local_mm, cy_local_mm) — offset of the footprint's bounding-box
    centre from its origin, in footprint-LOCAL (unrotated) mm coordinates.

    Uses board.get_item_bounding_box (include_text=False) to get the physical
    footprint bbox (pads, courtyard, fab outlines), then un-rotates the offset
    to footprint-local coordinates.

    NOTE: board.get_item_bounding_box does not perfectly match the viewBox that
    kicad-cli uses for standalone fp-export svg. For footprints with asymmetric
    text placement this can cause small overlay offsets. A proper fix requires
    deriving the anchor from the exported SVG itself — see manifest-w96.

    Returns None if the bounding box is unavailable.

    .. note::
        This wrapper constructs a one-off :class:`FootprintData` with ``_raw``
        set to *fp* and delegates to
        :class:`~kicad_pedal_common.board_adapter.KipyBoardAdapter`.  The
        returned ``BBoxCenter`` offsets are then un-rotated into footprint-local
        coordinates here (same logic as before) so callers see no change.
    """
    from kicad_pedal_common.board_adapter import FootprintData  # local import avoids circulars

    try:
        adapter = KipyBoardAdapter(board)
        # Build a minimal FootprintData so get_item_bounding_box can use _raw.
        fp_data = FootprintData(
            ref="",
            value="",
            footprint_id="",
            layer="F",
            pos_x=0.0,
            pos_y=0.0,
            rotation=0.0,
            dnp=False,
            exclude_from_bom=False,
            _raw=fp,
        )
        bbox_center = adapter.get_item_bounding_box(fp_data)
        if bbox_center is None:
            return None

        dx = bbox_center.cx_mm
        dy = bbox_center.cy_mm

        # Un-rotate from board coords to footprint-local coords.
        # KiCad visual CCW in Y-down = R(θ) = [[cos θ, sin θ], [-sin θ, cos θ]].
        # Inverse: R⁻¹(θ) = [[cos θ, -sin θ], [sin θ, cos θ]] (use +rot, not -rot).
        rot = fp.orientation.to_radians()
        cx_local = dx * math.cos(rot) - dy * math.sin(rot)
        cy_local = dx * math.sin(rot) + dy * math.cos(rot)

        return (cx_local, cy_local)
    except Exception:
        return None
